"""Unico punto di accesso all'LLM. Senza un provider configurato tutto gira in modalità offline.

Il provider si sceglie da `.env` (vedi README, "Provider LLM"): OpenAI, Gemini, Ollama o qualsiasi servizio
compatibile con l'API OpenAI. Chat ed embedding si configurano separatamente (`LLM_*` ed `EMBED_*`).
La configurazione si legge a ogni chiamata, così cambiare variabile d'ambiente basta, anche nei test.

Regola sugli embedding: vettori di modelli diversi (per esempio 1536 dim online e 256 dim offline) non vanno
mai mescolati. Se una richiesta di embedding fallisce, da quel momento il processo passa a offline per tutti
gli embedding (`EMBED_DEGRADED`) e chi ha già vettori online li ricalcola (vedi rag.Index)."""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import numpy as np


def _load_dotenv(path: str = ".env") -> None:
    """Legge KEY=valore da .env (ignorato da git) senza sovrascrivere le variabili già impostate."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip().removeprefix("export ").strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

CACHE = Path(os.getenv("CACHE_DIR", ".cache"))
EMBED_BATCH = 200
OFFLINE_DIM = 256

# Preset dei provider: indirizzo, variabile con la chiave, modelli di default, lotto massimo di embedding.
PROVIDERS = {
    "openai": {"base_url": None, "key_env": "OPENAI_API_KEY",
               "chat": "gpt-6-luna", "embed": "text-embedding-3-small", "batch": EMBED_BATCH},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "key_env": "GEMINI_API_KEY",
               "chat": "gemini-2.5-flash", "embed": "gemini-embedding-001", "batch": 100},
    "ollama": {"base_url": "http://localhost:11434/v1", "key_env": None,
               "chat": "qwen2.5:7b", "embed": "nomic-embed-text", "batch": EMBED_BATCH},
}

_clients: dict = {}
EMBED_DEGRADED = False   # True dopo un errore di embedding: si resta offline per coerenza
ERRORS: list[str] = []   # errori online finiti su risposte di riserva, mostrati nella UI
FALLBACKS = 0            # quante risposte di riserva sono state usate in modalità online


def _env(*names: str) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return None


def config(kind: str) -> dict | None:
    """Configurazione di `kind` ("chat" o "embed"), o None se quella parte gira offline.

    Chat: `LLM_PROVIDER` (default openai), `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`.
    Embedding: `EMBED_PROVIDER` (default = LLM_PROVIDER, oppure "offline"), `EMBED_MODEL`, `EMBED_BASE_URL`,
    `EMBED_API_KEY`; ciò che manca si prende dalla chat se il provider è lo stesso.
    Con OpenAI valgono ancora `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_EMBED_MODEL`, `OPENAI_BASE_URL`."""
    if os.getenv("OFFLINE", "") == "1":
        return None
    chat_provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    if kind == "chat":
        provider, p = chat_provider, "LLM"
    else:
        provider, p = (os.getenv("EMBED_PROVIDER") or chat_provider).strip().lower(), "EMBED"
    if provider == "offline":
        return None
    if provider not in PROVIDERS and provider != "custom":
        raise ValueError(f"{p}_PROVIDER={provider!r} non valido: usa {', '.join(PROVIDERS)}, custom o offline")
    preset = PROVIDERS.get(provider, {"base_url": None, "key_env": None, "chat": None, "embed": None,
                                      "batch": EMBED_BATCH})
    same = kind == "chat" or provider == chat_provider   # stesso provider: gli embedding ereditano dalla chat
    oa = provider == "openai"
    key = _env(f"{p}_API_KEY", *(["LLM_API_KEY"] if same else []),
               *([preset["key_env"]] if preset["key_env"] else []))
    base_url = _env(f"{p}_BASE_URL", *(["LLM_BASE_URL"] if same else []),
                    *(["OPENAI_BASE_URL"] if oa else [])) or preset["base_url"]
    if kind == "chat":
        model = _env("LLM_MODEL", *(["OPENAI_MODEL"] if oa else [])) or preset["chat"]
    else:
        model = _env("EMBED_MODEL", *(["OPENAI_EMBED_MODEL"] if oa else [])) or preset["embed"]
    if provider == "ollama":
        key = key or "ollama"   # Ollama non controlla la chiave, ma l'SDK ne vuole una
    if not key or not model:
        return None
    return {"provider": provider, "model": model, "base_url": base_url, "api_key": key,
            "batch": min(EMBED_BATCH, preset["batch"])}


def describe() -> str:
    """Una riga per la UI: quale provider e modello stanno girando."""
    def one(kind):
        c = config(kind)
        return f"{c['provider']} · {c['model']}" if c else "offline"
    return f"Chat: {one('chat')} — Embedding: {one('embed') if not EMBED_DEGRADED else 'offline (dopo un errore)'}"


def is_online() -> bool:
    return config("chat") is not None


def _get_client(cfg: dict):
    k = (cfg["base_url"], cfg["api_key"])
    if k not in _clients:
        from openai import OpenAI
        _clients[k] = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], max_retries=0)
    return _clients[k]


def _is_rate_limit(e: Exception) -> bool:
    return getattr(e, "status_code", None) == 429 or "rate limit" in str(e).lower() or "429" in str(e)


def _call(fn):
    """Esegue una chiamata all'API ripetendola con attese crescenti se il provider dice "troppe richieste"
    (i piani gratuiti hanno pochi messaggi al minuto)."""
    waits = [5, 15, 30, 60]
    for i in range(len(waits) + 1):
        try:
            return fn()
        except Exception as e:
            if i == len(waits) or not _is_rate_limit(e):
                raise
            time.sleep(waits[i])


def _cache_path(kind: str, payload: str) -> Path:
    h = hashlib.sha256(payload.encode()).hexdigest()[:24]
    return CACHE / kind / f"{h}.json"


def _read_cache(path: Path):
    """Legge una cache JSON; una cache vuota/corrotta viene invalidata."""
    try:
        if not path.exists():
            return None
        if path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            return None
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _write_cache(path: Path, data) -> None:
    """Scrive prima su un file temporaneo per non lasciare JSON parziali."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _record(err: Exception, where: str) -> None:
    global FALLBACKS
    FALLBACKS += 1
    msg = f"{where}: {type(err).__name__}: {str(err)[:160]}"
    if msg not in ERRORS:
        ERRORS.append(msg)


def _strip_fences(text: str) -> str:
    """Alcuni modelli (soprattutto quelli locali) avvolgono il JSON in ```json ... ```."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return m.group(1) if m else text


def chat_json(system: str, user: str, fallback):
    """Chiede JSON all'LLM. `fallback()` viene usato offline o se la chiamata fallisce (e lo registra)."""
    cfg = config("chat")
    if cfg is None:
        return fallback()
    path = _cache_path("chat", cfg["model"] + system + user)
    cached = _read_cache(path)
    if cached is not None:
        return cached
    last = None
    extra = {"temperature": 0.4}
    for _ in range(2):  # un retry
        try:
            resp = _call(lambda: _get_client(cfg).chat.completions.create(
                model=cfg["model"],
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                **extra,
            ))
            data = json.loads(_strip_fences(resp.choices[0].message.content or ""))
            if not isinstance(data, dict):
                raise ValueError("la risposta JSON non è un oggetto")
            _write_cache(path, data)
            return data
        except Exception as e:
            last = e
            if "temperature" in str(e).lower():  # alcuni modelli accettano solo la temperatura di default
                extra = {}
    _record(last, f"chat ({cfg['provider']})")
    return fallback()


def _offline_embed(text: str) -> np.ndarray:
    v = np.zeros(OFFLINE_DIM)
    for tok in re.findall(r"\w{3,}", text.lower()):
        v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % OFFLINE_DIM] += 1
    n = np.linalg.norm(v)
    return v / n if n else v


def embeds_online() -> bool:
    return config("embed") is not None and not EMBED_DEGRADED


def _embed_batch(texts: list[str]) -> list[list[float]]:
    cfg = config("embed")
    path = _cache_path("embed", cfg["model"] + "\x00".join(texts))
    cached = _read_cache(path)
    if cached is not None:
        return cached
    resp = _call(lambda: _get_client(cfg).embeddings.create(
        model=cfg["model"], input=[t[:8000] or " " for t in texts]))
    vecs = [d.embedding for d in resp.data]
    _write_cache(path, vecs)
    return vecs


def embed(texts: list[str]) -> np.ndarray:
    """Tutti i vettori restituiti hanno la stessa dimensione: o tutti online o tutti offline."""
    global EMBED_DEGRADED
    if embeds_online():
        try:
            batch = config("embed")["batch"]
            vecs = []
            for i in range(0, len(texts), batch):
                vecs.extend(_embed_batch(texts[i:i + batch]))
            return np.array(vecs)
        except Exception as e:
            EMBED_DEGRADED = True
            _record(e, "embedding (passo a offline per tutti gli embedding)")
    return np.array([_offline_embed(t) for t in texts]) if texts else np.zeros((0, OFFLINE_DIM))

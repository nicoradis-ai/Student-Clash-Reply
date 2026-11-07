"""Unico punto di accesso a OpenAI. Senza OPENAI_API_KEY tutto gira in modalità offline.

Regola sugli embedding: un vettore online (1536 dim) e uno offline (256 dim) non vanno mai mescolati.
Se una richiesta di embedding fallisce, da quel momento il processo passa a offline per tutti gli
embedding (`EMBED_DEGRADED`) e chi ha già vettori online li ricalcola (vedi rag.Index)."""
import hashlib
import json
import os
import re
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
MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
EMBED_BATCH = 200
OFFLINE_DIM = 256

_client = None
EMBED_DEGRADED = False   # True dopo un errore di embedding: si resta offline per coerenza
ERRORS: list[str] = []   # errori online finiti su risposte di riserva, mostrati nella UI
FALLBACKS = 0            # quante risposte di riserva sono state usate in modalità online


def is_online() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) and os.getenv("OFFLINE", "") != "1"


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI()
    return _client


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


def chat_json(system: str, user: str, fallback):
    """Chiede JSON all'LLM. `fallback()` viene usato offline o se la chiamata fallisce (e lo registra)."""
    if not is_online():
        return fallback()
    path = _cache_path("chat", MODEL + system + user)
    cached = _read_cache(path)
    if cached is not None:
        return cached
    last = None
    extra = {"temperature": 0.4}
    for _ in range(2):  # un retry
        try:
            resp = _get_client().chat.completions.create(
                model=MODEL,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                **extra,
            )
            data = json.loads(resp.choices[0].message.content)
            _write_cache(path, data)
            return data
        except Exception as e:
            last = e
            if "temperature" in str(e).lower():  # alcuni modelli accettano solo la temperatura di default
                extra = {}
    _record(last, "chat")
    return fallback()


def _offline_embed(text: str) -> np.ndarray:
    v = np.zeros(OFFLINE_DIM)
    for tok in re.findall(r"\w{3,}", text.lower()):
        v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % OFFLINE_DIM] += 1
    n = np.linalg.norm(v)
    return v / n if n else v


def embeds_online() -> bool:
    return is_online() and not EMBED_DEGRADED


def _embed_batch(texts: list[str]) -> list[list[float]]:
    path = _cache_path("embed", EMBED_MODEL + "\x00".join(texts))
    cached = _read_cache(path)
    if cached is not None:
        return cached
    resp = _get_client().embeddings.create(model=EMBED_MODEL, input=[t[:8000] or " " for t in texts])
    vecs = [d.embedding for d in resp.data]
    _write_cache(path, vecs)
    return vecs


def embed(texts: list[str]) -> np.ndarray:
    """Tutti i vettori restituiti hanno la stessa dimensione: o tutti online o tutti offline."""
    global EMBED_DEGRADED
    if embeds_online():
        try:
            vecs = []
            for i in range(0, len(texts), EMBED_BATCH):
                vecs.extend(_embed_batch(texts[i:i + EMBED_BATCH]))
            return np.array(vecs)
        except Exception as e:
            EMBED_DEGRADED = True
            _record(e, "embedding (passo a offline per tutti gli embedding)")
    return np.array([_offline_embed(t) for t in texts]) if texts else np.zeros((0, OFFLINE_DIM))

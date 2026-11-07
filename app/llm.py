"""Unico punto di accesso a OpenAI. Senza OPENAI_API_KEY tutto gira in modalità offline."""
import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np

CACHE = Path(os.getenv("CACHE_DIR", ".cache"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
OFFLINE_DIM = 256

_client = None


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


def chat_json(system: str, user: str, fallback):
    """Chiede JSON all'LLM. `fallback()` viene usato offline o se la chiamata fallisce."""
    if not is_online():
        return fallback()
    path = _cache_path("chat", MODEL + system + user)
    if path.exists():
        return json.loads(path.read_text())
    for _ in range(2):  # un retry
        try:
            resp = _get_client().chat.completions.create(
                model=MODEL,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0.4,
            )
            data = json.loads(resp.choices[0].message.content)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False))
            return data
        except Exception:
            continue
    return fallback()


def _offline_embed(text: str) -> np.ndarray:
    v = np.zeros(OFFLINE_DIM)
    for tok in re.findall(r"\w{3,}", text.lower()):
        v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % OFFLINE_DIM] += 1
    n = np.linalg.norm(v)
    return v / n if n else v


def embed(texts: list[str]) -> np.ndarray:
    if not is_online():
        return np.array([_offline_embed(t) for t in texts])
    path = _cache_path("embed", EMBED_MODEL + "\x00".join(texts))
    if path.exists():
        return np.array(json.loads(path.read_text()))
    try:
        resp = _get_client().embeddings.create(model=EMBED_MODEL, input=texts)
        vecs = [d.embedding for d in resp.data]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(vecs))
        return np.array(vecs)
    except Exception:
        return np.array([_offline_embed(t) for t in texts])

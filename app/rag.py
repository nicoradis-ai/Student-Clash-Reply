"""RAG leggero (ADR 0004): embedding in memoria, similarità coseno.

Soglia di pertinenza: con gli embedding OpenAI un brano sotto `MIN_SIM` di coseno non parla davvero della
domanda, quindi non viene restituito. Meglio dire "materiale insufficiente" (vedi `cite`) che citare pagine a caso.
Gli embedding offline (hash delle parole) non sono tarati, quindi offline la soglia non si applica."""
import os

import numpy as np

from . import llm
from .models import Chunk

MIN_SIM = float(os.getenv("RAG_MIN_SIM", "0.25"))   # text-embedding-3-small: sotto ~0.25 di solito è fuori tema
INSUFFICIENT = ("(Nessun materiale del corso abbastanza pertinente. Dillo esplicitamente nella risposta "
                "invece di inventare contenuti o riferimenti.)")


class Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._build()

    def _build(self):
        self.online = llm.embeds_online()
        self.vecs = llm.embed([c.text for c in self.chunks])
        self.online = self.online and llm.embeds_online()

    def retrieve(self, query: str, k: int = 4, source: str | None = None,
                 min_sim: float | None = None) -> list[Chunk]:
        """I k brani più simili. `min_sim=None` usa `MIN_SIM` online e nessuna soglia offline; 0 la disattiva.
        Può restituire meno di k brani, anche nessuno."""
        if not self.chunks:
            return []
        q = llm.embed([query])[0]
        if q.shape[0] != self.vecs.shape[1]:  # gli embedding sono passati a offline nel frattempo
            self._build()
            q = llm.embed([query])[0]
        norms = np.linalg.norm(self.vecs, axis=1) * (np.linalg.norm(q) or 1)
        sims = self.vecs @ q / np.where(norms == 0, 1, norms)
        floor = (MIN_SIM if self.online else 0.0) if min_sim is None else min_sim
        order = np.argsort(-sims)
        out = [self.chunks[i] for i in order
               if (source is None or self.chunks[i].source == source) and sims[i] >= floor]
        return out[:k]


def cite(chunks: list[Chunk]) -> str:
    if not chunks:
        return INSUFFICIENT
    return "\n\n".join(f"[{c.ref}]\n{c.text}" for c in chunks)

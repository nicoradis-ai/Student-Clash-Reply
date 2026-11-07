"""RAG leggero (ADR 0004): embedding in memoria, similarità coseno."""
import numpy as np

from . import llm
from .models import Chunk


class Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._build()

    def _build(self):
        self.online = llm.embeds_online()
        self.vecs = llm.embed([c.text for c in self.chunks])
        self.online = self.online and llm.embeds_online()

    def retrieve(self, query: str, k: int = 4, source: str | None = None) -> list[Chunk]:
        if not self.chunks:
            return []
        q = llm.embed([query])[0]
        if q.shape[0] != self.vecs.shape[1]:  # gli embedding sono passati a offline nel frattempo
            self._build()
            q = llm.embed([query])[0]
        norms = np.linalg.norm(self.vecs, axis=1) * (np.linalg.norm(q) or 1)
        sims = self.vecs @ q / np.where(norms == 0, 1, norms)
        order = np.argsort(-sims)
        out = [self.chunks[i] for i in order if source is None or self.chunks[i].source == source]
        return out[:k]


def cite(chunks: list[Chunk]) -> str:
    return "\n\n".join(f"[{c.ref}]\n{c.text}" for c in chunks)

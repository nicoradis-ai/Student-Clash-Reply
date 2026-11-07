"""RAG leggero (ADR 0004): embedding in memoria, similarità coseno."""
import numpy as np

from .llm import embed
from .models import Chunk


class Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.by_id = {c.id: c for c in chunks}
        self.vecs = embed([c.text for c in chunks]) if chunks else np.zeros((0, 1))

    def retrieve(self, query: str, k: int = 4, source: str | None = None) -> list[Chunk]:
        if not self.chunks:
            return []
        q = embed([query])[0]
        norms = np.linalg.norm(self.vecs, axis=1) * (np.linalg.norm(q) or 1)
        sims = self.vecs @ q / np.where(norms == 0, 1, norms)
        order = np.argsort(-sims)
        out = [self.chunks[i] for i in order if source is None or self.chunks[i].source == source]
        return out[:k]


def cite(chunks: list[Chunk]) -> str:
    return "\n\n".join(f"[{c.ref}]\n{c.text}" for c in chunks)

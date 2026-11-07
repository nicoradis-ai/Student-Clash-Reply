"""Mappa dei concetti estratta dal materiale; il docente la valida (validated=True)."""
import re
import unicodedata

import numpy as np

from .llm import chat_json, embed
from .models import Chunk, Concept

TAG_RE = re.compile(r"^Concetto:\s*(.+)$", re.M | re.I)

SYSTEM = (
    "Sei un assistente didattico. Dal materiale di un corso universitario estrai i 5-8 concetti "
    "principali del programma. Rispondi in JSON: "
    '{"concepts": [{"id": "slug-breve", "name": "Nome", "description": "una frase"}]}. In italiano.'
)


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _offline(chunks: list[Chunk]) -> dict:
    names = []
    for c in chunks:
        for m in TAG_RE.findall(c.text):
            if m.strip() not in names:
                names.append(m.strip())
    return {"concepts": [{"id": _slug(n), "name": n, "description": f"Concetto del corso: {n}."} for n in names]}


def extract_concepts(chunks: list[Chunk]) -> list[Concept]:
    sample = "\n\n".join(f"[{c.ref}] {c.text[:600]}" for c in chunks)[:12000]
    data = chat_json(SYSTEM, sample, lambda: _offline(chunks))
    concepts = [Concept(id=d.get("id") or _slug(d["name"]), name=d["name"], description=d.get("description", ""))
                for d in data.get("concepts", []) if d.get("name")]
    assign_chunks(concepts, chunks)
    return concepts


def assign_chunks(concepts: list[Concept], chunks: list[Chunk]) -> None:
    """Assegna ogni chunk a un concetto: tag esplicito se c'è, altrimenti il più simile."""
    if not concepts:
        return
    by_name = {c.name.lower(): c for c in concepts}
    cvecs = embed([f"{c.name}: {c.description}" for c in concepts])
    untagged = []
    for ch in chunks:
        tags = [t.strip().lower() for t in TAG_RE.findall(ch.text)]
        hit = next((by_name[t] for t in tags if t in by_name), None)
        if hit:
            hit.chunk_ids.append(ch.id)
        else:
            untagged.append(ch)
    if untagged:
        vecs = embed([c.text for c in untagged])
        sims = vecs @ cvecs.T
        for ch, row in zip(untagged, sims):
            concepts[int(np.argmax(row))].chunk_ids.append(ch.id)

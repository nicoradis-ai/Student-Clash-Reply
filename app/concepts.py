"""Mappa dei concetti estratta dal materiale; il docente la valida (validated=True)."""
import re
import unicodedata
from collections import defaultdict

import numpy as np

from .llm import _offline_embed, chat_json, embed
from .models import Chunk, Concept

TAG_RE = re.compile(r"^Concetto:\s*(.+)$", re.M | re.I)
SAMPLE_CHARS = 12000
PER_PAGE = 350
SKIP_FILES = ("presentazione", "progetto", "esercizi", "introduzione")

SYSTEM = (
    "Sei un assistente didattico. Dal materiale di un corso universitario (estratti di slide e temi d'esame) "
    "estrai i 5-8 concetti principali del programma. Rispondi in JSON: "
    '{"concepts": [{"id": "slug-breve", "name": "Nome", "description": "una frase"}]}. In italiano.'
)


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "concetto"


def _file_of(chunk: Chunk) -> str:
    return chunk.id.split("#")[0]


def sample_material(chunks: list[Chunk], limit: int = SAMPLE_CHARS, per_page: int = PER_PAGE) -> str:
    """Pochi caratteri da qualche pagina di OGNI file (slide ed esami), a turno, fino a `limit`."""
    by_file = defaultdict(list)
    for c in chunks:
        by_file[_file_of(c)].append(c)
    files = list(by_file)
    if not files:
        return ""
    picks_per_file = max(2, limit // (per_page * len(files)))
    per_page = max(80, min(per_page, limit // (len(files) * picks_per_file) - 20))  # tanti file: estratti più corti
    queues = []
    for f in files:
        pages = by_file[f][1:] or by_file[f]  # salta la copertina / l'intestazione del tema d'esame
        step = max(1, len(pages) // picks_per_file)
        queues.append(pages[step // 2::step][:picks_per_file])
    out, total = [], 0
    for rnd in range(max(len(q) for q in queues)):
        for q in queues:
            if rnd < len(q):
                s = f"[{q[rnd].ref}] {' '.join(q[rnd].text.split())[:per_page]}"
                if total + len(s) > limit:
                    return "\n\n".join(out)
                out.append(s)
                total += len(s)
    return "\n\n".join(out)


def _topic_from_filename(name: str) -> str:
    stem = re.sub(r"\.\w+$", "", name)
    stem = re.sub(r"^[\d\s._-]+", "", stem)
    return stem.replace("_", " ").strip()


def _offline(chunks: list[Chunk]) -> dict:
    """Senza LLM: tag 'Concetto:' se ci sono, altrimenti un concetto per file di slide."""
    names = []
    for c in chunks:
        for m in TAG_RE.findall(c.text):
            if m.strip() not in names:
                names.append(m.strip())
    if not names:
        for f in sorted({_file_of(c).split("/", 1)[1] for c in chunks if c.source == "slide"}):
            t = _topic_from_filename(f)
            if t and not any(s in t.lower() for s in SKIP_FILES) and t not in names:
                names.append(t)
    return {"concepts": [{"name": n, "description": f"Argomento del corso: {n}."} for n in names]}


def _dedupe(concepts: list[Concept]) -> list[Concept]:
    seen, out = set(), []
    for c in concepts:
        base, i = c.id, 2
        while c.id in seen:
            c.id = f"{base}-{i}"; i += 1
        seen.add(c.id)
        out.append(c)
    return out


def extract_concepts(chunks: list[Chunk]) -> list[Concept]:
    data = chat_json(SYSTEM, sample_material(chunks), lambda: _offline(chunks))
    concepts = [Concept(id=_slug(d.get("id") or d["name"]), name=d["name"], description=d.get("description", ""))
                for d in data.get("concepts", []) if d.get("name")]
    if not concepts:  # anche online: mai un'app vuota
        concepts = [Concept(id=_slug(d["name"]), name=d["name"], description=d["description"])
                    for d in _offline(chunks)["concepts"]]
    concepts = _dedupe(concepts)
    assign_chunks(concepts, chunks)
    return concepts


def assign_chunks(concepts: list[Concept], chunks: list[Chunk]) -> None:
    """Ogni chunk va a un concetto: tag esplicito, poi file di slide omonimo, altrimenti il più simile."""
    if not concepts:
        return
    by_name = {c.name.lower(): c for c in concepts}
    untagged = []
    for ch in chunks:
        tags = [t.strip().lower() for t in TAG_RE.findall(ch.text)]
        hit = next((by_name[t] for t in tags if t in by_name), None)
        if hit is None and ch.source == "slide":
            hit = by_name.get(_topic_from_filename(_file_of(ch).split("/", 1)[1]).lower())
        if hit:
            hit.chunk_ids.append(ch.id)
        else:
            untagged.append(ch)
    if untagged:
        # chunk embeddati con la stessa lista di rag.Index, così si riusa la cache dei lotti
        cvecs = embed([f"{c.name}: {c.description}" for c in concepts])
        all_vecs = embed([c.text for c in chunks])
        if cvecs.shape[1] != all_vecs.shape[1]:  # un embedding è passato a offline in mezzo: rifai tutto offline
            cvecs = np.array([_offline_embed(f"{c.name}: {c.description}") for c in concepts])
            all_vecs = np.array([_offline_embed(c.text) for c in chunks])
        pos = {ch.id: i for i, ch in enumerate(chunks)}
        tvecs = all_vecs[[pos[ch.id] for ch in untagged]]
        for ch, row in zip(untagged, tvecs @ cvecs.T):
            concepts[int(np.argmax(row))].chunk_ids.append(ch.id)

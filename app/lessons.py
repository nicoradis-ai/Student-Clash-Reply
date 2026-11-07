"""Panoramica delle lezioni e proposte di correzione slide-per-slide."""
import re
from pathlib import PurePosixPath

from .llm import chat_json
from .models import Chunk, Lesson, SlideCorrection


LESSON_SYSTEM = (
    "Sei un assistente didattico. Analizza tutte le slide di una lezione universitaria. "
    "Restituisci una panoramica schematica con i sottoargomenti realmente presenti, senza inventare. "
    "Rispondi solo in JSON: {\"subtopics\": [\"sottoargomento breve\", ...]}. "
    "Scrivi in italiano e mantieni l'ordine con cui gli argomenti compaiono."
)

CORRECTION_SYSTEM = (
    "Sei un revisore di materiale didattico universitario. Esamina una singola slide e proponi "
    "tutti i piccoli miglioramenti utili: chiarezza, definizioni mancanti, ambiguità, esempi, "
    "notazione o collegamenti logici. Non riscrivere tutta la slide e non inventare errori fattuali. "
    "Per ogni proposta indica esattamente l'errore o limite e la correzione concreta. "
    "Rispondi solo in JSON: {\"proposals\": [{\"error\": \"...\", \"correction\": \"...\"}]}. "
    "Se non trovi problemi, restituisci una lista vuota. Scrivi in italiano."
)


def _file_of(chunk: Chunk) -> str:
    return chunk.id.split("#", 1)[0]


def _title(path: str) -> str:
    stem = PurePosixPath(path).stem
    stem = re.sub(r"^[\d\s._-]+", "", stem)
    return stem.replace("_", " ").strip() or PurePosixPath(path).name


def _offline_subtopics(chunks: list[Chunk]) -> list[str]:
    topics = []
    for chunk in chunks:
        for line in chunk.text.splitlines():
            line = line.strip()
            match = re.match(r"^#{1,6}\s+(.+)$", line)
            tagged = re.match(r"^Concetto:\s*(.+)$", line, re.I)
            candidate = (match or tagged).group(1).strip() if (match or tagged) else ""
            candidate = re.sub(r"[*_`]", "", candidate).strip()
            if candidate and candidate.lower() not in {x.lower() for x in topics}:
                topics.append(candidate)
    if topics:
        return topics
    return [f"Contenuti della slide {i + 1}" for i in range(len(chunks))]


def build_lessons(chunks: list[Chunk]) -> list[Lesson]:
    """Raggruppa tutte le slide per file e crea l'overview di ogni lezione."""
    grouped: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        if chunk.source == "slide":
            grouped.setdefault(_file_of(chunk), []).append(chunk)

    lessons = []
    for source_file, slides in grouped.items():
        material = "\n\n".join(f"[{s.ref}]\n{s.text}" for s in slides)
        data = chat_json(LESSON_SYSTEM, material, lambda slides=slides: {
            "subtopics": _offline_subtopics(slides)
        })
        subtopics = [str(x).strip() for x in data.get("subtopics", []) if str(x).strip()]
        lessons.append(Lesson(
            id=source_file,
            title=_title(source_file),
            source_file=source_file,
            slide_ids=[s.id for s in slides],
            subtopics=list(dict.fromkeys(subtopics)) or _offline_subtopics(slides),
        ))
    return lessons


def review_slides(chunks: list[Chunk]) -> list[SlideCorrection]:
    """Genera proposte indipendenti per ogni slide, usando il testo completo della slide."""
    corrections = []
    for slide in (c for c in chunks if c.source == "slide"):
        data = chat_json(CORRECTION_SYSTEM, f"[{slide.ref}]\n{slide.text}", lambda: {
            "proposals": [{
                "error": "La slide presenta il concetto senza un esempio o una verifica immediata della comprensione.",
                "correction": "Aggiungere un esempio breve, un controesempio oppure una domanda di controllo coerente con il contenuto.",
            }]
        })
        for proposal in data.get("proposals", []):
            error = str(proposal.get("error", "")).strip()
            correction = str(proposal.get("correction", "")).strip()
            if error and correction:
                corrections.append(SlideCorrection(slide.id, slide.ref, error, correction))
    return corrections

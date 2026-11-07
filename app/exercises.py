"""Coppie di verifica: esercizio tipico + variante (la variante va approvata, ADR 0003)."""
from .llm import chat_json
from .models import Concept, Exercise
from .rag import Index, cite

SYSTEM = (
    "Sei un docente universitario. Ti do un concetto e il materiale del corso (slide e temi d'esame). "
    "Scrivi due esercizi brevi sullo stesso concetto:\n"
    "1) 'typical': nella stessa forma ricorrente dei temi d'esame;\n"
    "2) 'variant': stesso concetto in forma nuova (leggere codice e prevedere l'output, trovare l'errore, "
    "scegliere tra due soluzioni e motivare, applicare il concetto in un contesto diverso), "
    "non risolvibile ricalcando lo schema del tipico.\n"
    "Per ciascuno dai una rubrica di correzione con i punti chiave attesi. Cita le fonti usate con il loro "
    "riferimento tra parentesi quadre. Rispondi in JSON: "
    '{"typical": {"prompt": "...", "rubric": "..."}, "variant": {"prompt": "...", "rubric": "..."}, '
    '"sources": ["Slide 3", "..."]}. In italiano.'
)


def _offline(concept: Concept, ctx: list) -> dict:
    exam = next((c for c in ctx if c.source == "exam"), None)
    typical = exam.text if exam else f"Svolgi un esercizio standard su {concept.name}, come nei temi d'esame."
    return {
        "typical": {"prompt": typical, "rubric": f"Parole chiave: {concept.name}, procedura corretta, risultato."},
        "variant": {
            "prompt": (f"Senza seguire lo schema solito: spiega in quale situazione NON useresti {concept.name} "
                       f"e perché, con un esempio tuo diverso da quelli visti a lezione."),
            "rubric": f"Parole chiave: {concept.name}, quando applicarlo, controesempio, motivazione.",
        },
        "sources": [c.ref for c in ctx[:3]],
    }


def make_pair(concept: Concept, index: Index) -> tuple[Exercise, Exercise]:
    ctx = index.retrieve(f"{concept.name} {concept.description}", k=5)
    user = f"Concetto: {concept.name} – {concept.description}\n\nMateriale:\n{cite(ctx)}"
    data = chat_json(SYSTEM, user, lambda: _offline(concept, ctx))
    refs = {c.ref: c.id for c in ctx}
    sources = [refs.get(s, s) for s in data.get("sources", [])] or [c.id for c in ctx[:3]]
    t, v = data["typical"], data["variant"]
    typical = Exercise(id=f"{concept.id}-typ", concept_id=concept.id, kind="typical",
                       prompt=t["prompt"], rubric=t["rubric"], sources=sources, status="approved")
    variant = Exercise(id=f"{concept.id}-var", concept_id=concept.id, kind="variant",
                       prompt=v["prompt"], rubric=v["rubric"], sources=sources, status="pending")
    return typical, variant

"""Agente 1 · Revisione del materiale del corso (slide e dispense).

Obiettivo: per i concetti con transfer gap alto, proporre modifiche alle slide che insegnino
QUANDO e PERCHÉ usare il concetto, non solo la procedura (esempi in contesto diverso, controesempi,
domande di controllo). Owner: thread "Agente revisione materiale del corso".
"""
from ..llm import chat_json
from ..models import Proposal
from ..rag import cite
from .base import CourseContext, evidence

SYSTEM = (
    "Sei un revisore di materiale didattico universitario. Ti do un concetto, le metriche della sonda di transfer "
    "(gli studenti risolvono gli esercizi tipici ma non le varianti) e le slide che lo trattano. Proponi al massimo "
    "due modifiche puntuali alle slide che aiutino a capire quando e perché si usa il concetto. Ogni modifica indica "
    "la slide (usa il riferimento tra parentesi quadre), il problema e il testo concreto da aggiungere o sostituire. "
    'Rispondi in JSON: {"proposals": [{"target_ref": "...", "problem": "...", "change": "..."}]}. In italiano.'
)


class MaterialeAgent:
    name = "materiale"
    title = "📚 Materiale del corso"
    goal = "Rende le slide dei concetti con gap alto capaci di insegnare quando usare il concetto, non solo la procedura."

    def run(self, ctx: CourseContext) -> list[Proposal]:
        out = []
        for con, m in ctx.focus():
            slides = ctx.chunks_of(con.id, "slide")[:4] or ctx.index.retrieve(con.name, k=4, source="slide")
            user = f"Concetto: {con.name} – {con.description}\n{evidence(m)}\n\nSlide:\n{cite(slides)}"
            ref = slides[0].ref if slides else "slide del concetto"
            data = chat_json(SYSTEM, user, lambda: {"proposals": [{
                "target_ref": ref,
                "problem": f"La slide mostra {con.name} solo nella forma usata negli esercizi d'esame.",
                "change": f"Aggiungere un esempio in un contesto diverso e un controesempio in cui {con.name} non va usato, "
                          "con una domanda di controllo per lo studente.",
            }]})
            for p in data.get("proposals", []):
                out.append(Proposal(agent=self.name, concept_id=con.id, target_ref=p.get("target_ref", ref),
                                    problem=p.get("problem", ""), change=p.get("change", ""),
                                    rationale=evidence(m), sources=[s.id for s in slides],
                                    priority=m.transfer_gap))
        return out

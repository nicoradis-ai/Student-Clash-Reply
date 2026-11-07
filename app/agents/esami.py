"""Agente 3 · Revisione degli esami.

Obiettivo: gli esami devono misurare la comprensione, non la memoria dello schema. Per i concetti
con gap alto (o con peso d'esame molto diverso dal peso a lezione) propone come riscrivere un esercizio
d'esame esistente in forma non standard, mantenendo punti e difficoltà. Owner: thread "Agente revisione esami".
"""
from ..llm import chat_json
from ..models import Proposal
from ..rag import cite
from .base import CourseContext, evidence

SYSTEM = (
    "Sei un docente che rivede i temi d'esame. Ti do un concetto, le metriche della sonda di transfer (gli studenti "
    "risolvono gli esercizi tipici ma non le varianti; peso a lezione contro peso d'esame) e gli esercizi d'esame "
    "che lo testano. Proponi al massimo due modifiche: quale esercizio cambiare (riferimento tra parentesi quadre), "
    "perché oggi premia la memoria dello schema, e il testo riscritto con stessa difficoltà e punti. "
    'Rispondi in JSON: {"proposals": [{"target_ref": "...", "problem": "...", "change": "..."}]}. In italiano.'
)


class EsamiAgent:
    name = "esami"
    title = "📝 Esami"
    goal = "Riscrive gli esercizi d'esame ricorrenti perché misurino la comprensione e non la memoria dello schema."

    def run(self, ctx: CourseContext) -> list[Proposal]:
        out = []
        for con, m in ctx.focus():
            exams = ctx.chunks_of(con.id, "exam")[:3] or ctx.index.retrieve(con.name, k=3, source="exam")
            user = f"Concetto: {con.name} – {con.description}\n{evidence(m)}\n\nEsercizi d'esame:\n{cite(exams)}"
            ref = exams[0].ref if exams else "prossimo appello"
            data = chat_json(SYSTEM, user, lambda: {"proposals": [{
                "target_ref": ref,
                "problem": f"L'esercizio su {con.name} si risolve ricalcando lo schema degli appelli precedenti.",
                "change": f"Stessi punti: dare una soluzione già scritta che applica {con.name} e chiedere di trovare "
                          "il caso in cui fallisce, motivando.",
            }]})
            for p in data.get("proposals", []):
                out.append(Proposal(agent=self.name, concept_id=con.id, target_ref=p.get("target_ref", ref),
                                    problem=p.get("problem", ""), change=p.get("change", ""),
                                    rationale=evidence(m), sources=[s.id for s in exams],
                                    priority=m.transfer_gap))
        return out

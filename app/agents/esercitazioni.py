"""Agente 2 · Allineamento delle esercitazioni.

Obiettivo: le esercitazioni devono allenare il transfer, non solo lo schema d'esame. Per i concetti
con gap alto propone nuovi esercizi (o modifiche a quelli esistenti) in forma non standard, allineati
a ciò che è insegnato nelle slide. Usa i blocchi `source == "exercise"` (cartella exercises/ del corso);
se non ci sono, ripiega sugli esercizi presenti nelle slide. Owner: thread "Agente allineamento esercitazioni".
"""
from ..llm import chat_json
from ..models import Proposal
from ..rag import cite
from .base import CourseContext, evidence

SYSTEM = (
    "Sei un docente che progetta esercitazioni universitarie. Ti do un concetto, le metriche della sonda di transfer "
    "(gli studenti risolvono gli esercizi tipici ma non le varianti), le esercitazioni esistenti e le slide. "
    "Proponi al massimo due esercizi di esercitazione nuovi o modificati che allenino il transfer: forma diversa "
    "dallo schema d'esame (prevedere l'output, trovare l'errore, scegliere e motivare, contesto nuovo). "
    'Rispondi in JSON: {"proposals": [{"target_ref": "esercitazione da modificare o \'nuova\'", '
    '"problem": "...", "change": "testo dell\'esercizio proposto"}]}. In italiano.'
)


class EsercitazioniAgent:
    name = "esercitazioni"
    title = "🛠️ Esercitazioni"
    goal = "Allinea le esercitazioni a ciò che va capito: esercizi che allenano il transfer, non solo lo schema d'esame."

    def run(self, ctx: CourseContext) -> list[Proposal]:
        out = []
        for con, m in ctx.focus():
            exs = ctx.chunks_of(con.id, "exercise")[:3] or ctx.index.retrieve(con.name, k=3, source="exercise")
            slides = ctx.index.retrieve(con.name, k=2, source="slide")
            user = (f"Concetto: {con.name} – {con.description}\n{evidence(m)}\n\n"
                    f"Esercitazioni esistenti:\n{cite(exs) or '(nessuna)'}\n\nSlide:\n{cite(slides)}")
            ref = exs[0].ref if exs else "nuova esercitazione"
            data = chat_json(SYSTEM, user, lambda: {"proposals": [{
                "target_ref": ref,
                "problem": f"Le esercitazioni su {con.name} ripetono la forma dei temi d'esame.",
                "change": f"Dato un frammento già risolto che usa {con.name} nel caso sbagliato, trova l'errore e "
                          "spiega quale scelta avresti fatto e perché.",
            }]})
            for p in data.get("proposals", []):
                out.append(Proposal(agent=self.name, concept_id=con.id, target_ref=p.get("target_ref", ref),
                                    problem=p.get("problem", ""), change=p.get("change", ""),
                                    rationale=evidence(m), sources=[s.id for s in exs + slides],
                                    priority=m.transfer_gap))
        return out

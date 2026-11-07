"""Agente 2 · Allineamento delle esercitazioni.

Obiettivo: le esercitazioni devono preparare a ciò che l'esame chiede E allenare il transfer, non solo lo
schema d'esame. Per ogni concetto confronta peso nelle esercitazioni, peso nei punti d'esame e transfer gap,
decide un'azione (aggiungere / trasformare / ridurre) e propone esercizi nuovi o modifiche a quelli esistenti,
più cosa devono esercitare gli studenti. La logica sta in `app/practice.py`; qui la si traduce in `Proposal`.
Usa i blocchi `source == "exercise"` (cartella exercises/); se mancano, le slide di esercizi.
"""
from ..models import Proposal
from ..practice import align_practice
from .base import CourseContext, evidence

ACTION_LABEL = {"aggiungere": "Aggiungere esercitazioni", "trasformare": "Trasformare in esercizi di transfer",
                "ridurre": "Ridurre lo spazio nelle esercitazioni"}


class EsercitazioniAgent:
    name = "esercitazioni"
    title = "🛠️ Esercitazioni"
    goal = ("Allinea le esercitazioni a ciò che l'esame chiede e a ciò che va capito: copre i concetti che "
            "l'esame pesa ma nessuno fa esercitare, e trasforma in esercizi di transfer quelli dove il gap è alto.")

    def run(self, ctx: CourseContext, top: int = 3) -> list[Proposal]:
        out = []
        for p in align_practice(ctx.concepts, ctx.chunks, ctx.index, ctx.metrics, top=top):
            if p.action == "ok":
                continue
            parts = []
            if p.change_existing:
                parts.append(f"Modifica: {p.change_existing}")
            for i, e in enumerate(p.new_exercises, 1):
                parts.append(f"Nuovo esercizio {i}: {e.prompt}\nRubrica: {e.rubric}")
            if p.student_practice:
                parts.append(f"Per gli studenti: {p.student_practice}")
            m = ctx.metric(p.concept_id)
            first = next((s for s in p.sources if s.startswith("exercises/") or "esercit" in s or "esercizi" in s), "")
            refs = {c.id: c.ref for c in ctx.chunks}
            out.append(Proposal(
                agent=self.name, concept_id=p.concept_id,
                target_ref=refs.get(first, "nuova esercitazione"),
                problem=f"{ACTION_LABEL[p.action]}. {p.diagnosis}",
                change="\n\n".join(parts) or f"{ACTION_LABEL[p.action]} su questo concetto.",
                rationale=p.evidence + (f" {evidence(m)}" if m else ""),
                sources=p.sources, priority=p.priority))
        return out

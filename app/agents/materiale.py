"""Agente 1 · Revisione del materiale del corso (slide e dispense).

Obiettivo: allineare le slide a ciò che l'esame verifica davvero. Per i concetti più disallineati
(sotto-insegnati rispetto ai punti d'esame, o con transfer gap alto) propone modifiche concrete a pagine
precise "<file> p.N", motivate dalle pagine d'esame, con il lato esame e il lato studente (ADR 0002).
La logica sta in app/material_review.py. Owner: thread "Agente revisione materiale del corso".
"""
from ..material_review import review_material
from ..models import Proposal
from .base import CourseContext, evidence


class MaterialeAgent:
    name = "materiale"
    title = "📚 Materiale del corso"
    goal = ("Trova i concetti che l'esame chiede più di quanto le slide li insegnino (o che gli studenti non sanno "
            "trasferire) e propone modifiche a pagine precise, giustificate dalle domande d'esame.")

    def run(self, ctx: CourseContext) -> list[Proposal]:
        chunk_id = {c.ref: c.id for c in ctx.chunks}
        out = []
        for review in review_material(ctx.concepts, ctx.metrics, ctx.chunks, ctx.index, top=3):
            m = ctx.metric(review.concept_id)
            for p in review.proposals:
                rationale = " ".join(x for x in (
                    evidence(m) if m else "", p.why,
                    f"Lato esame: {p.exam_side}" if p.exam_side else "",
                    f"Lato studente: {p.student_side}" if p.student_side else "") if x)
                out.append(Proposal(
                    agent=self.name, concept_id=review.concept_id, target_ref=p.slide_ref,
                    problem=review.diagnosis or p.why, change=f"[{p.action}] {p.change}", rationale=rationale,
                    sources=[chunk_id[r] for r in [p.slide_ref, *p.exam_refs] if r in chunk_id],
                    priority=review.priority))
        return out

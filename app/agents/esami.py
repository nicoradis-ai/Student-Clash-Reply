"""Agente 3 · Revisione degli esami.

Obiettivo: gli esami devono misurare la comprensione, non la memoria dello schema. Usa lo storico completo
degli appelli (`exam_review`) per trovare:
- gli esercizi recenti quasi uguali a quelli degli anni prima, e propone come riscriverli;
- gli esami che usano un'architettura diversa da quella insegnata nelle slide (es. MIPS contro RISC-V).
Se lo storico non basta (nessun esercizio ripetuto), ricade sui concetti di `ctx.focus()`.
Owner: thread "Agente revisione esami".
"""
import re
from functools import lru_cache

from .. import exam_review as er
from ..ingest import exam_date, load_course
from ..llm import chat_json
from ..models import Chunk, Proposal
from ..rag import cite
from .base import CourseContext, evidence

SYSTEM = (
    "Sei un docente che rivede i temi d'esame. Ti do un concetto, le metriche della sonda di transfer (gli studenti "
    "risolvono gli esercizi tipici ma non le varianti; peso a lezione contro peso d'esame) e gli esercizi d'esame "
    "che lo testano. Proponi al massimo due modifiche: quale esercizio cambiare (riferimento tra parentesi quadre), "
    "perché oggi premia la memoria dello schema, e il testo riscritto con stessa difficoltà e punti. "
    'Rispondi in JSON: {"proposals": [{"target_ref": "...", "problem": "...", "change": "..."}]}. In italiano.'
)


@lru_cache(maxsize=4)
def _history(course_dir: str) -> tuple[Chunk, ...]:
    """Tutti gli esami, anche quelli esclusi dal filtro della sidebar: servono come storico."""
    return tuple(c for c in load_course(course_dir, None) if c.source == "exam")


class EsamiAgent:
    name = "esami"
    title = "📝 Esami"
    goal = ("Trova gli esercizi d'esame che si superano ricalcando i temi vecchi o che usano un'architettura "
            "diversa da quella delle slide, e propone come riscriverli.")

    def run(self, ctx: CourseContext) -> list[Proposal]:
        chunks = list(ctx.chunks)
        if ctx.course_dir:
            seen = {c.id for c in chunks}
            chunks += [c for c in _history(str(ctx.course_dir)) if c.id not in seen]
        report = er.review_exams(chunks, ctx.index, since=ctx.exams_from)
        out = self._mismatch(ctx, report) + self._revisions(ctx, report)
        return out or self._by_focus(ctx)

    # ---------- concetto di una proposta ----------

    def _concept_for(self, ctx: CourseContext, chunk_id: str, text: str) -> str:
        """Il concetto che il testo nomina di più (a parità vince quello di focus); se nessuno è nominato,
        quello a cui è assegnato l'esercizio; altrimenti il primo concetto di focus."""
        focus = [c for c, _ in ctx.focus(k=len(ctx.concepts))] or ctx.concepts
        low = text.lower()
        hits = [(sum(low.count(w) for w in re.findall(r"\w{4,}", c.name.lower())), -i, c) for i, c in enumerate(focus)]
        best = max(hits, key=lambda h: h[:2], default=None)
        if best and best[0] > 0:
            return best[2].id
        assigned = next((c.id for c in ctx.concepts if chunk_id in c.chunk_ids), None)
        return assigned or (focus[0].id if focus else "")

    def _rationale(self, ctx: CourseContext, concept_id: str, extra: str) -> str:
        m = ctx.metric(concept_id) if concept_id else None
        return extra + (" " + evidence(m) if m else "")

    # ---------- proposte ----------

    def _mismatch(self, ctx: CourseContext, report: er.ExamReport) -> list[Proposal]:
        recent = [m for m in report.mismatches
                  if not ctx.exams_from or (exam_date(m.exam_file) or "") >= ctx.exams_from]
        if not recent:
            return []
        periods = er.mismatch_periods(recent)
        isa, slides_isa = recent[-1].exam_isa, recent[-1].slides_isa
        concept_id = self._concept_for(ctx, "", f"assembly programmazione linguaggio {slides_isa} {isa}")
        return [Proposal(
            agent=self.name, concept_id=concept_id, target_ref=f"esercizi di programmazione ({recent[0].exam_file} → "
                                                              f"{recent[-1].exam_file})",
            problem=" ".join(periods) + " Chi studia sui temi vecchi si allena su un'architettura che a lezione non vede.",
            change=(f"Riscrivere l'esercizio di programmazione e le domande chiuse sull'assembly in {slides_isa}, e "
                    f"dare all'esame il foglio con l'instruction set {slides_isa} invece di quello {isa}."),
            rationale=self._rationale(ctx, concept_id, recent[-1].evidence),
            sources=[f"exams/{m.exam_file}" for m in recent[-3:]], priority=2.0)]

    def _revisions(self, ctx: CourseContext, report: er.ExamReport) -> list[Proposal]:
        by_id = {s.chunk_id: s for s in report.standardized}
        out = []
        for r in report.revisions:
            s = by_id[r.chunk_id]
            concept_id = self._concept_for(ctx, r.chunk_id, s.text)
            m = ctx.metric(concept_id) if concept_id else None
            change = r.revised_prompt + (f"\n\nRubrica: {r.rubric}" if r.rubric else "")
            out.append(Proposal(
                agent=self.name, concept_id=concept_id, target_ref=r.original_ref, problem=r.problem, change=change,
                rationale=self._rationale(ctx, concept_id,
                                          f"Somiglianza {s.similarity:.0%} con {s.closest_ref}, ripetuto in "
                                          f"{s.repeats} appelli precedenti; il {report.predictability:.0%} dei punti "
                                          f"d'esame recenti sta su esercizi già visti. {r.why_better}"),
                sources=[r.chunk_id] + r.sources,
                priority=1.0 + s.similarity + (m.transfer_gap if m else 0.0)))
        return out

    def _by_focus(self, ctx: CourseContext) -> list[Proposal]:
        """Senza storico utile: un esercizio d'esame per concetto di focus, riscritto dall'LLM."""
        out = []
        for con, m in ctx.focus():
            exams = ctx.chunks_of(con.id, "exam")[:3] or ctx.index.retrieve(con.name, k=3, source="exam")
            user = f"Concetto: {con.name} – {con.description}\n{evidence(m)}\n\nEsercizi d'esame:\n{cite(exams)}"
            ref = exams[0].ref if exams else "prossimo appello"
            data = chat_json(SYSTEM, user, lambda con=con, ref=ref: {"proposals": [{
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

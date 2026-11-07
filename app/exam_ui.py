"""Vista Streamlit dell'agente esami: confronto prima/dopo per ogni esercizio d'esame rivisto.
Unico punto di aggancio in streamlit_app.py: `render_exam_reviewer()` chiama `render(S, course_dir, exams_from)`."""
import streamlit as st

from . import exam_review as er
from .agents.base import CourseContext
from .agents.esami import EsamiAgent, _history
from .metrics import concept_metrics


def _context(S, course_dir: str, exams_from: str | None) -> CourseContext:
    answers = list(S.get("answers", [])) + list(S.get("live_answers", []))
    exercises = list(S.get("exercises", []))
    return CourseContext(chunks=S.chunks, index=S.index, concepts=S.get("concepts", []),
                         metrics=concept_metrics(S.get("concepts", []), S.chunks, exercises, answers),
                         exercises=exercises, answers=answers, course_dir=course_dir, exams_from=exams_from)


def _run(S, course_dir: str, exams_from: str | None) -> None:
    with st.spinner("Confronto gli esami con lo storico degli appelli (la prima volta ~15 s)…"):
        ctx = _context(S, course_dir, exams_from)
        S.exam_props = sorted(EsamiAgent().run(ctx), key=lambda p: p.priority, reverse=True)
        history = list(S.chunks) + list(_history(course_dir) if course_dir else [])
        S.exam_texts = {c.id: c for c in history}
        S.exam_predictability = er.predictability(history, exams_from)
        S.exam_key = (course_dir, exams_from)


def render(S, course_dir: str, exams_from: str | None) -> None:
    st.subheader("Revisore esami")
    st.write("Trova gli esercizi d'esame che si superano ricalcando i temi vecchi o che usano un'architettura "
             "diversa da quella delle slide, e propone come riscriverli. Ogni proposta va approvata.")
    if not any(c.source == "exam" for c in S.chunks):
        st.info("Questo corso non contiene temi d'esame.")
        return
    if st.button("Avvia revisione degli esami", type="primary") or (
            S.get("exam_props") is not None and S.get("exam_key") != (course_dir, exams_from)):
        _run(S, course_dir, exams_from)
    props = S.get("exam_props")
    if props is None:
        return

    names = {c.id: c.name for c in S.get("concepts", [])}
    a, b, c = st.columns(3)
    a.metric("Punti d'esame su esercizi già visti", f"{S.exam_predictability:.0%}")
    b.metric("Proposte", len(props))
    c.metric("Approvate", sum(p.status == "approved" for p in props))

    for i, p in enumerate(props):
        original = S.exam_texts.get(p.sources[0]) if p.sources else None
        icon = {"approved": "✅", "rejected": "❌"}.get(p.status, "🟡")
        with st.container(border=True):
            st.markdown(f"**{icon} {p.target_ref}** · concetto: {names.get(p.concept_id, p.concept_id or '—')}")
            st.caption(p.problem)
            before, after = st.columns(2)
            with before:
                st.markdown("**Prima** · esercizio attuale")
                if original is not None:
                    st.caption(f"{original.ref} · {original.points:g} punti")
                    st.text(er._clean(original.text)[:1500])
                else:
                    st.write(p.problem)
            with after:
                st.markdown("**Dopo** · proposta")
                st.write(p.change)
            st.info(f"Perché: {p.rationale}")
            ok, ko, _ = st.columns([1, 1, 4])
            if ok.button("Approva", key=f"exam-ok-{i}"):
                p.status = "approved"
                st.rerun()
            if ko.button("Scarta", key=f"exam-ko-{i}"):
                p.status = "rejected"
                st.rerun()

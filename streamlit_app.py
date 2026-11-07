"""The Lazy Prof: interfaccia semplice per studenti e professori."""
from collections import defaultdict

import pandas as pd
import streamlit as st

from app import ingest, llm
from app.concepts import extract_concepts
from app.exercises import make_pair
from app.grading import grade
from app.ingest import course_config, course_path, list_courses, load_course
from app.lessons import build_lessons, review_slides
from app.rag import Index


st.set_page_config(page_title="The Lazy Prof", page_icon="🎓", layout="wide")
S = st.session_state


@st.cache_data(show_spinner=False)
def load_material(course: str, exams_from: str | None):
    return load_course(course_path(course), exams_from)


def reset_course_state():
    S.exercises = []
    S.answers = []
    S.live_answers = []
    S.slide_corrections = []


def load_course_into_session(course: str, exams_from: str | None):
    """Carica un corso una sola volta nella sessione corrente."""
    key = (course, exams_from)
    if S.get("course_key") == key and S.get("chunks"):
        return

    ingest.WARNINGS.clear()
    with st.status("Carico il corso…", expanded=True) as status:
        chunks = load_material(course, exams_from)
        if not chunks:
            # Recupera eventuali valori vuoti rimasti nella cache da un ambiente
            # dove pypdf non era installato.
            chunks = load_course(course_path(course), exams_from)
        S.chunks = chunks
        S.index = Index(chunks) if chunks else None
        S.lessons = build_lessons(chunks) if chunks else []
        S.concepts = extract_concepts(chunks) if chunks else []
        reset_course_state()
        S.course_key = key
        status.update(
            label=f"{len(chunks)} blocchi caricati" if chunks else "Nessun materiale trovato",
            state="complete" if chunks else "error",
            expanded=False,
        )


def course_selector():
    courses = list_courses()
    if not courses:
        st.error(f"Nessun corso trovato in {ingest.DATA_DIR}.")
        st.stop()

    course = st.selectbox("Corso", courses)
    config = course_config(course_path(course))
    exams_from = None
    if config.get("exams_from"):
        exams_from = config["exams_from"] if st.checkbox(
            f"Usa solo gli esami dal {config['exams_from']}", value=True,
            help=config.get("exams_from_note", ""),
        ) else None
    return course, exams_from


def render_slide_remaker():
    st.subheader("Remaker delle slide")
    st.write("Analizza ogni lezione e propone miglioramenti puntuali per ogni slide.")

    for lesson in S.get("lessons", []):
        with st.expander(f"{lesson.title} · {len(lesson.slide_ids)} slide"):
            for topic in lesson.subtopics:
                st.markdown(f"- {topic}")

    if st.button("Analizza le slide", type="primary"):
        with st.spinner("Il remaker sta analizzando tutte le slide…"):
            S.slide_corrections = review_slides(S.chunks)

    corrections = S.get("slide_corrections", [])
    if not corrections:
        st.info("Avvia l'analisi per vedere le proposte di correzione.")
        return

    by_slide = defaultdict(list)
    for correction in corrections:
        by_slide[correction.slide_ref].append(correction)
    st.metric("Proposte generate", len(corrections))
    for slide_ref, proposals in by_slide.items():
        with st.expander(slide_ref):
            for number, proposal in enumerate(proposals, 1):
                st.markdown(f"**{number}. Errore o limite**")
                st.write(proposal.error)
                st.markdown("**Correzione proposta**")
                st.write(proposal.correction)


def lesson_concepts(lesson):
    slide_ids = set(lesson.slide_ids)
    return [c for c in S.get("concepts", []) if slide_ids.intersection(c.chunk_ids)]


def render_survey_creator():
    st.subheader("Creatore di survey")
    st.write("Scegli una lezione: l'agente creerà survey tipici e varianti sul suo contenuto.")
    lessons = S.get("lessons", [])
    if not lessons:
        st.info("Questo corso non contiene lezioni leggibili.")
        return

    selected = st.selectbox("Lezione", lessons, format_func=lambda lesson: lesson.title)
    concepts = lesson_concepts(selected) or S.get("concepts", [])
    st.caption(f"Concetti collegati: {', '.join(c.name for c in concepts) or 'nessuno'}")

    if st.button("Crea survey per questa lezione", type="primary"):
        with st.spinner("Creo le survey…"):
            generated = []
            for concept in concepts:
                generated.extend(make_pair(concept, S.index))
            existing = {exercise.id for exercise in S.get("exercises", [])}
            S.exercises.extend(exercise for exercise in generated if exercise.id not in existing)

    exercises = S.get("exercises", [])
    if not exercises:
        st.info("Nessuna survey creata.")
        return

    names = {concept.id: concept.name for concept in S.get("concepts", [])}
    refs = {chunk.id: chunk.ref for chunk in S.chunks}
    for variant in [e for e in exercises if e.kind == "variant"]:
        typical = next(e for e in exercises if e.id == variant.concept_id + "-typ")
        with st.container(border=True):
            st.markdown(f"### {names.get(variant.concept_id, variant.concept_id)}")
            left, right = st.columns(2)
            left.markdown("**Survey tipica**")
            left.write(typical.prompt)
            right.markdown(f"**Survey variante · {variant.status}**")
            right.write(variant.prompt)
            st.caption("Fonti: " + ", ".join(refs.get(source, source) for source in variant.sources))
            approve, reject, _ = st.columns([1, 1, 5])
            if approve.button("Approva", key=f"approve-{variant.id}"):
                variant.status = "approved"
                st.rerun()
            if reject.button("Scarta", key=f"reject-{variant.id}"):
                variant.status = "rejected"
                st.rerun()


def render_exam_reviewer():
    st.subheader("Revisore esami")
    st.write("Controlla la coerenza tra programma, slide e temi d'esame.")
    exams = [chunk for chunk in S.chunks if chunk.source == "exam"]
    st.metric("Blocchi d'esame disponibili", len(exams))
    if not exams:
        st.info("Questo corso non contiene temi d'esame.")
        return
    if st.button("Prepara revisione degli esami", type="primary"):
        st.session_state.exam_review_ready = True
    if st.session_state.get("exam_review_ready"):
        grouped = defaultdict(int)
        for exam in exams:
            grouped[exam.ref.split(",")[0].split(" p.")[0]] += 1
        st.success("Materiale pronto per la revisione.")
        st.dataframe(pd.DataFrame([{"Esame": name, "Blocchi": count} for name, count in grouped.items()]), hide_index=True)
        st.info("Il revisore esami è isolato dagli altri agenti: qui aggiungeremo le regole di revisione nel prossimo passaggio.")


def render_student():
    st.header("Area studente")
    st.write("Qui compaiono solo le survey approvate dal professore.")
    approved_variants = [e for e in S.get("exercises", []) if e.kind == "variant" and e.status == "approved"]
    if not approved_variants:
        st.info("Non ci sono ancora survey approvate dal professore.")
        return

    student_id = st.text_input("Nome", "studente")
    names = {concept.id: concept.name for concept in S.get("concepts", [])}
    selected = st.selectbox("Survey", approved_variants, format_func=lambda e: names.get(e.concept_id, e.concept_id))
    st.markdown(f"### {names.get(selected.concept_id, selected.concept_id)}")
    st.write(selected.prompt)
    answer = st.text_area("La tua risposta")
    if st.button("Invia risposta", type="primary") and answer.strip():
        result = grade(selected, answer, student_id)
        S.live_answers.append(result)
        st.success(f"Punteggio: {result.score:.0%}")
        st.write(result.feedback)


st.title("The Lazy Prof")
st.caption("Un assistente semplice per rendere più leggero il lavoro del professore.")

role = st.radio("Come vuoi entrare?", ["Studente", "Professore"], horizontal=True)

if role == "Studente":
    render_student()
else:
    st.header("Area professore")
    course, exams_from = course_selector()
    if st.button("Carica corso", type="primary") or S.get("course_key") != (course, exams_from):
        load_course_into_session(course, exams_from)

    if not S.get("chunks"):
        st.warning("Carica un corso per iniziare.")
        st.stop()
    if ingest.WARNINGS:
        st.warning("Problemi nella lettura: " + " · ".join(ingest.WARNINGS[:3]))

    st.divider()
    st.subheader("Scegli l'agente")
    agent = st.selectbox("Agente", [
        "Revisore esami",
        "Remaker delle slide",
        "Creatore di survey",
    ])

    if agent == "Revisore esami":
        render_exam_reviewer()
    elif agent == "Remaker delle slide":
        render_slide_remaker()
    else:
        render_survey_creator()

if llm.is_online() and llm.ERRORS:
    st.sidebar.warning(f"Sono state usate {llm.FALLBACKS} risposte di riserva.")

"""The Lazy Prof: interfaccia semplice per studenti e professori."""
from pathlib import Path

import pandas as pd
import streamlit as st

from app import ingest, llm
from app.concepts import extract_concepts
from app.exercises import make_pair
from app.grading import grade
from app.ingest import course_config, course_path, list_courses, load_course
from app.lessons import build_lessons
from app.materials_update import (
    approve_change,
    modernize_materials,
    prepare_materials,
    preview_change,
    suggest_micro_changes,
)
from app.metrics import concept_metrics, coverage_distance
from app.rag import Index
from app.simulate import simulate_class


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
        S.course_has_material = any(
            file.is_file() and file.suffix.lower() in {".pptx", ".pdf", ".docx", ".md", ".txt"}
            and "materials_update_bench" not in file.parts
            and file.name.lower() not in {"programma.txt", "requisiti_attesi.txt", "syllabus.md"}
            for file in course_path(course).rglob("*")
        )
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


def render_exam_reviewer(course: str, exams_from: str | None):
    from app.exam_ui import render
    render(S, str(course_path(course)), exams_from)


def render_materials_update(course: str):
    st.subheader("Revisore materiali")
    st.write("Esamina presentazioni, PDF e documenti. Per i PPTX crea anche una versione con design uniforme; ogni modifica testuale resta in attesa della tua approvazione.")
    selected_root = Path(course_path(course))
    root = selected_root
    st.caption(f"Cartella materiali: {root}")

    if st.button("Analizza materiali"):
        with st.spinner("Leggo i documenti senza creare copie o file di output…"):
            S.materials_package = prepare_materials(root)
            S.material_changes = {}

    package = S.get("materials_package")
    if package is not None and Path(package.data_dir).resolve() != selected_root.resolve():
        S.materials_package = None
        S.material_changes = {}
        package = None
    if package is None:
        st.info("Avvia la preparazione per leggere le presentazioni e i documenti del corso.")
        return
    if not package.lessons:
        st.warning("Non ho trovato file PPTX, PDF, DOCX, Markdown o TXT nel corso selezionato.")
        return

    st.success(f"{len(package.lessons)} materiali analizzati in memoria. Nessun file è stato creato o modificato.")
    if st.button("Ammoderna il design e crea new_slides", type="primary"):
        with st.spinner("Creo le copie modernizzate nella cartella new_slides…"):
            modernize_materials(package)
        st.success(f"Materiali generati in {package.output_dir}")
        st.rerun()

    lesson = st.selectbox("Lezione", package.lessons, format_func=lambda item: item.name)
    st.markdown("**Sottoargomenti**")
    for topic in lesson.subtopics:
        st.markdown(f"- {topic}")
    modernized = Path(lesson.bench_path).is_file()
    if modernized:
        label = "Scarica PDF modernizzato" if lesson.source_format == "pdf" else (
            "Scarica PPTX con design uniforme" if lesson.source_format == "pptx" else "Scarica copia del documento"
        )
        st.download_button(label, Path(lesson.bench_path).read_bytes(), file_name=Path(lesson.bench_path).name)
    else:
        st.caption("Le proposte non generano file. Per creare l'output, usa il pulsante di ammodernamento.")

    unit_name = "Slide" if lesson.source_format == "pptx" else "Pagina / sezione"
    slide = st.selectbox(unit_name, lesson.slides, format_func=lambda item: f"{unit_name} {item.number}: {item.title or 'senza titolo'}")
    with st.expander("Testo estratto"):
        st.text(slide.text)
    if st.button("Suggerisci modifiche", type="primary"):
        with st.spinner("L'agente sta cercando solo micro-modifiche…"):
            S.material_changes[slide.number] = suggest_micro_changes(lesson, slide, package.syllabus, package.expected)

    changes = S.get("material_changes", {}).get(slide.number, [])
    if not changes:
        st.info("Nessuna proposta caricata per questa slide.")
        return
    for change in changes:
        with st.container(border=True):
            st.markdown(f"### Proposta · {change.status}")
            if change.status != "pending":
                st.caption("Proposta già gestita: " + ("approvata" if change.status == "approved" else "rifiutata"))
                continue
            previews = preview_change(lesson, slide, change)
            if previews is None:
                st.warning("Non riesco a localizzare il testo nella pagina per produrre un confronto visuale. Nessun file è stato modificato.")
            else:
                left, right = st.columns(2)
                left.markdown("**Slide attuale**")
                left.image(previews[0], use_container_width=True)
                right.markdown("**Anteprima con modifica**")
                right.image(previews[1], use_container_width=True)
            with st.expander("Testo e motivazione"):
                st.markdown("**Originale**")
                st.write(change.original_text)
                st.markdown("**Proposta**")
                st.write(change.proposed_text)
            st.caption(change.justification)
            approve, reject, _ = st.columns([1, 1, 5])
            if approve.button("Approva", key=f"material-approve-{change.id}", disabled=not modernized or previews is None):
                if approve_change(package, change):
                    st.success("Solo la slide approvata è stata aggiornata in new_slides; le altre sono rimaste invariate.")
                else:
                    st.error("Non ho trovato il testo originale nella slide modernizzata: nessun file è stato modificato.")
                st.rerun()
            if reject.button("Rifiuta", key=f"material-reject-{change.id}"):
                change.status = "rejected"
                st.rerun()


def render_diagnosis():
    """Metrica principale (ADR 0001): transfer gap per concetto, dalle risposte alle coppie tipico + variante."""
    st.subheader("Diagnosi: transfer gap")
    st.write("Per ogni concetto confronta il punteggio sulle survey tipiche con quello sulle varianti. "
             "Un gap alto vuol dire che si ricalca lo schema senza aver capito il concetto.")
    approved = [e for e in S.get("exercises", []) if e.kind == "variant" and e.status == "approved"]
    if not approved:
        st.info("Approva almeno una variante nel Creatore di survey, poi torna qui per simulare la classe.")
    col, _ = st.columns([2, 5])
    if col.button("Simula una classe di 20 studenti", type="primary", disabled=not approved):
        S.answers = simulate_class(S.exercises)
    answers = list(S.get("answers", [])) + list(S.get("live_answers", []))
    if not answers:
        st.caption("Nessuna risposta ancora: simula la classe o fai rispondere gli studenti dall'Area studente.")
        return
    names = {c.id: c.name for c in S.get("concepts", [])}
    ms = [m for m in concept_metrics(S.concepts, S.chunks, S.exercises, answers) if m.typical_score or m.variant_score]
    if not ms:
        st.caption("Le risposte non riguardano ancora nessun concetto con survey approvate.")
        return
    df = pd.DataFrame([{"Concetto": names.get(m.concept_id, m.concept_id), "Tipiche": m.typical_score,
                        "Varianti": m.variant_score, "Transfer gap": m.transfer_gap,
                        "Peso slide": m.teaching_weight, "Peso esame": m.exam_weight} for m in ms])
    a, b, c = st.columns(3)
    worst = df.sort_values("Transfer gap", ascending=False).iloc[0]
    a.metric("Gap più alto", f"{worst['Transfer gap']:+.0%}", worst["Concetto"])
    b.metric("Risposte", len(answers))
    c.metric("Distanza insegnato ↔ testato", f"{coverage_distance(ms):.0%}")
    st.bar_chart(df.set_index("Concetto")[["Tipiche", "Varianti"]], stack=False)
    st.dataframe(df.style.format({k: "{:.0%}" for k in df.columns if k != "Concetto"}), hide_index=True)
    st.caption("Il Revisore esami usa queste stesse risposte nelle sue motivazioni.")


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
    typical = next((e for e in S.exercises if e.id == selected.concept_id + "-typ"), None)
    # coppia tipica + variante: senza entrambe non si misura il transfer gap
    for label, ex in (("Domanda 1", typical), ("Domanda 2", selected)):
        if ex is None:
            continue
        with st.container(border=True):
            st.markdown(f"**{label}**")
            st.write(ex.prompt)
            answer = st.text_area("La tua risposta", key=f"student-ans-{ex.id}")
            if st.button("Invia risposta", type="primary", key=f"student-send-{ex.id}") and answer.strip():
                result = grade(ex, answer, student_id)
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

    if not S.get("chunks") and not S.get("course_has_material"):
        st.warning("Carica un corso per iniziare.")
        st.stop()
    if ingest.WARNINGS:
        st.warning("Problemi nella lettura: " + " · ".join(ingest.WARNINGS[:3]))

    st.divider()
    st.subheader("Scegli l'agente")
    agent = st.selectbox("Agente", [
        "Diagnosi transfer gap",
        "Revisore esami",
        "Revisore materiali",
        "Creatore di survey",
    ])

    if agent == "Diagnosi transfer gap":
        render_diagnosis()
    elif agent == "Revisore esami":
        render_exam_reviewer(course, exams_from)
    elif agent == "Revisore materiali":
        render_materials_update(course)
    elif agent == "Creatore di survey":
        render_survey_creator()

if llm.is_online() and llm.ERRORS:
    st.sidebar.warning(f"Sono state usate {llm.FALLBACKS} risposte di riserva.")

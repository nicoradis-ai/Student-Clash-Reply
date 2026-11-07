"""Demo AI on Campus – sonda di transfer. Avvio: streamlit run streamlit_app.py"""
import pandas as pd
import streamlit as st

from app import llm
from app.concepts import extract_concepts
from app.exercises import make_pair
from app.grading import grade
from app import ingest
from app.ingest import course_config, course_path, list_courses, load_course
from app.insights import misalignments, study_advice
from app.lessons import build_lessons, review_slides
from app.metrics import concept_metrics, coverage_distance
from app.rag import Index
from app.simulate import simulate_class

st.set_page_config(page_title="Sonda di transfer", layout="wide")
S = st.session_state

# ---------- barra laterale ----------
st.sidebar.title("Sonda di transfer")
if not llm.is_online():
    st.sidebar.warning("Modalità offline: niente OPENAI_API_KEY, uso risposte di riserva.")
courses = list_courses()
if not courses:
    st.error(f"Nessun corso trovato in {ingest.DATA_DIR}. Ogni corso è una cartella con slides/ ed exams/.")
    st.stop()
course = st.sidebar.selectbox("Corso", courses)
cfg = course_config(course_path(course))
exams_from = None
if cfg.get("exams_from"):
    if st.sidebar.checkbox(f"Solo esami dal {cfg['exams_from']}", value=True,
                           help=cfg.get("exams_from_note", "")):
        exams_from = cfg["exams_from"]


@st.cache_data(show_spinner=False)
def _load(course: str, exams_from):
    return load_course(course_path(course), exams_from)


key = (course, exams_from)
if st.sidebar.button("Carica materiale", type="primary") or S.get("key") != key:
    with st.status("Carico il materiale del corso…", expanded=True) as box:
        st.write("1/3 · Leggo slide ed esami (con molti PDF serve circa mezzo minuto)…")
        S.chunks = _load(course, exams_from)
        n_s = sum(c.source == "slide" for c in S.chunks)
        st.write(f"{n_s} pagine di slide, {len(S.chunks) - n_s} pagine d'esame.")
        st.write("2/4 · Costruisco l'indice di ricerca (embedding)…")
        S.index = Index(S.chunks)
        st.write("3/4 · Costruisco l'overview di tutte le lezioni…")
        S.lessons = build_lessons(S.chunks)
        st.write("4/4 · Estraggo la mappa dei concetti…")
        S.concepts = extract_concepts(S.chunks)
        S.exercises, S.answers, S.live_answers, S.mis = [], [], [], None
        S.slide_corrections = []
        S.key = key
        ok = bool(S.chunks and S.concepts)
        box.update(label=f"Materiale caricato: {len(S.chunks)} blocchi, {len(S.concepts)} concetti" if ok
                   else "Caricamento incompleto", state="complete" if ok else "error", expanded=not ok)
st.sidebar.caption(f"{len(S.get('chunks', []))} blocchi di materiale · {len(S.get('concepts', []))} concetti")
if ingest.WARNINGS:
    st.sidebar.error("Problemi nella lettura dei file:\n\n" + "\n\n".join(ingest.WARNINGS[:5]))
if not S.get("chunks"):
    st.error("Non ho trovato testo nel materiale di questo corso. Controlla che le librerie siano installate "
             "(`pip install -r requirements.txt`, serve pypdf) e che i file siano in slides/ ed exams/.")
    st.stop()

view = st.sidebar.radio("Vista", ["Docente", "Studente"])


def status_banner():
    """Va chiamato alla fine dello script, così conta anche gli errori di questo giro."""
    if llm.is_online() and (llm.ERRORS or llm.EMBED_DEGRADED):
        st.sidebar.error(f"OpenAI non ha risposto: {llm.FALLBACKS} risposte di riserva usate."
                         + (" Embedding passati a offline." if llm.EMBED_DEGRADED else ""))
        with st.sidebar.expander("Dettagli"):
            for e in llm.ERRORS[-5:]:
                st.caption(e)
    elif llm.is_online():
        st.sidebar.success(f"Online · {llm.MODEL}")
name = {c.id: c.name for c in S.get("concepts", [])}


def all_answers():
    return S.get("answers", []) + S.get("live_answers", [])


# ---------- vista docente ----------
if view == "Docente":
    t1, t2, t3, t4, t5, t6 = st.tabs(["1 · Lezioni", "2 · Correzioni slide", "3 · Mappa dei concetti",
                                      "4 · Varianti da approvare", "5 · Classe e metriche", "6 · Disallineamenti"])

    with t1:
        st.write("Ogni file di slide/PDF è trattato come una lezione. Qui trovi tutti i sottoargomenti individuati.")
        for lesson in S.get("lessons", []):
            with st.container(border=True):
                st.markdown(f"### {lesson.title}")
                st.caption(f"Sorgente: {lesson.source_file} · {len(lesson.slide_ids)} slide")
                for topic in lesson.subtopics:
                    st.markdown(f"- {topic}")

    with t2:
        st.write("L'agente esamina ogni slide separatamente e propone correzioni puntuali.")
        if st.button("Genera proposte di correzione"):
            with st.spinner("Analizzo tutte le slide del corso…"):
                S.slide_corrections = review_slides(S.chunks)
        if not S.get("slide_corrections"):
            st.info("Premi il pulsante per generare le proposte.")
        else:
            by_slide = {}
            for proposal in S.slide_corrections:
                by_slide.setdefault((proposal.slide_id, proposal.slide_ref), []).append(proposal)
            st.metric("Proposte generate", len(S.slide_corrections))
            for (_, slide_ref), proposals in by_slide.items():
                with st.expander(slide_ref):
                    for i, proposal in enumerate(proposals, 1):
                        st.markdown(f"**Proposta {i} · Errore o limite**")
                        st.write(proposal.error)
                        st.markdown("**Correzione proposta**")
                        st.write(proposal.correction)

    with t3:
        st.write("L'AI ha estratto questi concetti dal materiale. Conferma quelli corretti.")
        for c in S.concepts:
            c.validated = st.checkbox(f"**{c.name}** – {c.description}  ·  {len(c.chunk_ids)} blocchi",
                                      value=c.validated, key=f"val-{c.id}")
        ok = sum(c.validated for c in S.concepts)
        st.metric("Accordo con il docente", f"{ok}/{len(S.concepts)}")

    with t4:
        if st.button("Genera coppie di verifica"):
            with st.spinner("Genero esercizio tipico + variante per ogni concetto…"):
                S.exercises = [e for c in S.concepts if c.validated or ok == 0 for e in make_pair(c, S.index)]
        refs = {c.id: c.ref for c in S.chunks}
        for e in [e for e in S.exercises if e.kind == "variant"]:
            typ = next(x for x in S.exercises if x.id == e.concept_id + "-typ")
            with st.container(border=True):
                st.markdown(f"#### {name.get(e.concept_id, e.concept_id)} · stato: `{e.status}`")
                a, b = st.columns(2)
                a.markdown("**Esercizio tipico**"); a.write(typ.prompt)
                b.markdown("**Variante (da approvare)**"); b.write(e.prompt)
                st.caption("Fonti: " + ", ".join(refs.get(s, s) for s in e.sources))
                c1, c2, _ = st.columns([1, 1, 6])
                if c1.button("Approva", key=f"ok-{e.id}"):
                    e.status = "approved"; st.rerun()
                if c2.button("Scarta", key=f"no-{e.id}"):
                    e.status = "rejected"; st.rerun()
        if S.exercises:
            n = sum(e.status == "approved" for e in S.exercises if e.kind == "variant")
            st.metric("Varianti approvate", f"{n}/{len(S.exercises) // 2}")

    with t5:
        if st.button("Simula una verifica con la classe (20 studenti)"):
            S.answers = simulate_class(S.exercises)
        if not all_answers():
            st.info("Approva qualche variante e simula la classe.")
        else:
            ms = concept_metrics(S.concepts, S.chunks, S.exercises, all_answers())
            df = pd.DataFrame([{"Concetto": name[m.concept_id], "Tipici": m.typical_score,
                                "Varianti": m.variant_score, "Transfer gap": m.transfer_gap,
                                "Peso slide": m.teaching_weight, "Peso esame": m.exam_weight} for m in ms])
            st.subheader("Transfer gap per concetto")
            st.bar_chart(df.set_index("Concetto")[["Tipici", "Varianti"]], stack=False)
            st.subheader("Indice di copertura")
            st.metric("Distanza insegnato ↔ testato", f"{coverage_distance(ms):.0%}")
            st.bar_chart(df.set_index("Concetto")[["Peso slide", "Peso esame"]], stack=False)
            st.dataframe(df, hide_index=True)

    with t6:
        if not all_answers():
            st.info("Servono prima le risposte della classe.")
        else:
            if st.button("Analizza i disallineamenti", type="primary"):
                with st.spinner("L'agente interpreta i dati…"):
                    ms = concept_metrics(S.concepts, S.chunks, S.exercises, all_answers())
                    S.mis = misalignments(S.concepts, ms, all_answers(), S.exercises, S.index)
            for d in S.get("mis") or []:
                with st.container(border=True):
                    st.markdown(f"### {name[d.concept_id]}")
                    st.caption(d.evidence)
                    st.markdown(f"**Cosa significa:** {d.meaning}")
                    a, b, c = st.columns(3)
                    a.markdown("**📚 Slide e lezioni**"); a.write(d.suggestion_teaching)
                    b.markdown("**📝 Esame**"); b.write(d.suggestion_exam)
                    c.markdown("**🎓 Studenti**"); c.write(d.suggestion_student)

# ---------- vista studente ----------
else:
    sid = st.sidebar.text_input("Il tuo nome", "studente-demo")
    ready = [e for e in S.get("exercises", []) if e.status == "approved"]
    if not ready:
        st.info("Il docente non ha ancora approvato esercizi.")
    else:
        cid = st.selectbox("Concetto", sorted({e.concept_id for e in ready}), format_func=lambda c: name.get(c, c))
        for e in [e for e in ready if e.concept_id == cid]:
            with st.container(border=True):
                st.markdown("**Esercizio tipico**" if e.kind == "typical" else "**Variante**")
                st.write(e.prompt)
                txt = st.text_area("La tua risposta", key=f"ans-{e.id}")
                if st.button("Invia", key=f"send-{e.id}") and txt.strip():
                    a = grade(e, txt, sid)
                    S.live_answers.append(a)
                    st.success(f"Punteggio: {a.score:.0%}")
                    st.write(a.feedback)
        mine = [a for a in S.live_answers if a.student_id == sid]
        if mine:
            st.subheader("I miei gap e cosa ripassare")
            ms = concept_metrics(S.concepts, S.chunks, S.exercises, mine)
            tips = study_advice(ms, S.concepts)
            for t in tips or ["Nessun gap evidente per ora: prova anche le varianti degli altri concetti."]:
                st.write("• " + t)

status_banner()

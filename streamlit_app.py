"""Demo AI on Campus – sonda di transfer + tre agenti (ADR 0006). Avvio: streamlit run streamlit_app.py"""
import pandas as pd
import streamlit as st

from app import llm
from app.concepts import extract_concepts
from app.exercises import make_pair
from app.grading import grade
from app import ingest
from app.ingest import course_config, course_path, list_courses, load_course
from app.agents import AGENTS, evidence
from app.insights import study_advice
from app.orchestrator import build_context, run_agents
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
        ingest.WARNINGS.clear()
        st.write("1/3 · Leggo slide, esercitazioni ed esami (con molti PDF serve circa mezzo minuto)…")
        S.chunks = _load(course, exams_from)
        # Se una vecchia cache contiene il risultato vuoto ottenuto senza pypdf,
        # riprova senza cache dopo l'installazione della dipendenza.
        if not S.chunks:
            S.chunks = load_course(course_path(course), exams_from)
        n = {k: sum(c.source == k for c in S.chunks) for k in ("slide", "exercise", "exam")}
        st.write(f"{n['slide']} pagine di slide, {n['exercise']} di esercitazioni, {n['exam']} d'esame.")
        st.write("2/3 · Costruisco l'indice di ricerca (embedding)…")
        S.index = Index(S.chunks)
        st.write("3/3 · Estraggo la mappa dei concetti…")
        S.concepts = extract_concepts(S.chunks)
        S.exercises, S.answers, S.live_answers, S.proposals, S.agent_errors = [], [], [], {}, {}
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
    st.title("Gli studenti sanno risolvere l'esame, ma hanno capito il corso?")
    st.write("Per ogni concetto confrontiamo il punteggio su un **esercizio tipico** (la forma solita d'esame) e su una "
             "**variante** (stesso concetto, forma nuova). La differenza è il **transfer gap**: dove è alto, gli studenti "
             "hanno imparato lo schema e non il concetto. Tre agenti lavorano poi in parallelo sui concetti peggiori: "
             "materiale, esercitazioni, esami.")
    t1, t2, t3 = st.tabs(["1 · Diagnosi: dove si impara lo schema", "2 · Tre agenti al lavoro", "3 · Piano approvato"])

    with t1:
        with st.expander(f"Mappa dei concetti ({sum(c.validated for c in S.concepts)}/{len(S.concepts)} confermati)"):
            for c in S.concepts:
                c.validated = st.checkbox(f"**{c.name}** – {c.description}  ·  {len(c.chunk_ids)} blocchi",
                                          value=c.validated, key=f"val-{c.id}")
        ok = sum(c.validated for c in S.concepts)
        a, b = st.columns(2)
        if a.button("① Genera coppie tipico + variante"):
            with st.spinner("Genero esercizio tipico + variante per ogni concetto…"):
                S.exercises = [e for c in S.concepts if c.validated or ok == 0 for e in make_pair(c, S.index)]
        variants = [e for e in S.exercises if e.kind == "variant"]
        if variants and b.button("Approva tutte le varianti"):
            for e in variants:
                e.status = "approved"
        if variants:
            n_ok = sum(e.status == "approved" for e in variants)
            with st.expander(f"Varianti da approvare ({n_ok}/{len(variants)} approvate)", expanded=n_ok == 0):
                refs = {c.id: c.ref for c in S.chunks}
                for e in variants:
                    typ = next(x for x in S.exercises if x.id == e.concept_id + "-typ")
                    with st.container(border=True):
                        st.markdown(f"#### {name.get(e.concept_id, e.concept_id)} · stato: `{e.status}`")
                        x, y = st.columns(2)
                        x.markdown("**Esercizio tipico**"); x.write(typ.prompt)
                        y.markdown("**Variante**"); y.write(e.prompt)
                        st.caption("Fonti: " + ", ".join(refs.get(s, s) for s in e.sources))
                        c1, c2, _ = st.columns([1, 1, 6])
                        if c1.button("Approva", key=f"ok-{e.id}"):
                            e.status = "approved"; st.rerun()
                        if c2.button("Scarta", key=f"no-{e.id}"):
                            e.status = "rejected"; st.rerun()
            if st.button("② Simula una verifica con la classe (20 studenti)", type="primary"):
                S.answers = simulate_class(S.exercises)
        if all_answers():
            ms = sorted(concept_metrics(S.concepts, S.chunks, S.exercises, all_answers()),
                        key=lambda m: m.transfer_gap, reverse=True)
            df = pd.DataFrame([{"Concetto": name[m.concept_id], "Tipici": m.typical_score,
                                "Varianti": m.variant_score, "Transfer gap": m.transfer_gap,
                                "Peso slide": m.teaching_weight, "Peso esame": m.exam_weight} for m in ms])
            worst = ms[0]
            k1, k2, k3 = st.columns(3)
            k1.metric("Gap medio", f"{sum(m.transfer_gap for m in ms) / len(ms):+.0%}")
            k2.metric("Concetto peggiore", name[worst.concept_id], f"{worst.transfer_gap:+.0%}", delta_color="inverse")
            k3.metric("Distanza insegnato ↔ testato", f"{coverage_distance(ms):.0%}")
            st.subheader("Transfer gap per concetto")
            st.bar_chart(df.set_index("Concetto")[["Tipici", "Varianti"]], stack=False)
            st.dataframe(df, hide_index=True)
            st.success("Prosegui al tab **2 · Tre agenti al lavoro**: interverranno sui concetti in cima a questa lista.")
        elif S.exercises:
            st.info("Approva le varianti e simula la classe per vedere il transfer gap.")

    with t2:
        if not all_answers():
            st.info("Prima serve la diagnosi (tab 1): gli agenti lavorano solo sui concetti con gap alto.")
        else:
            ctx = build_context(S.chunks, S.index, S.concepts, S.exercises, all_answers(),
                                str(course_path(course)), exams_from)
            st.markdown("**Concetti su cui interveniamo**")
            for con, m in ctx.focus():
                st.markdown(f"- **{con.name}** · {evidence(m)}")
            if st.button("Avvia i tre agenti in parallelo", type="primary"):
                with st.spinner("Materiale, esercitazioni ed esami in parallelo…"):
                    S.proposals, S.agent_errors = run_agents(ctx)
            cols = st.columns(len(AGENTS))
            for col, agent in zip(cols, AGENTS):
                with col:
                    st.subheader(agent.title)
                    st.caption(agent.goal)
                    if agent.name in S.get("agent_errors", {}):
                        st.error(S.agent_errors[agent.name])
                    for i, p in enumerate(S.get("proposals", {}).get(agent.name, [])):
                        with st.container(border=True):
                            st.markdown(f"**{name.get(p.concept_id, p.concept_id)}** · `{p.status}`")
                            st.caption(f"Dove: {p.target_ref}")
                            st.markdown(f"**Problema:** {p.problem}")
                            st.markdown(f"**Proposta:** {p.change}")
                            st.caption(p.rationale)
                            c1, c2 = st.columns(2)
                            if c1.button("Approva", key=f"pa-{agent.name}-{i}"):
                                p.status = "approved"; st.rerun()
                            if c2.button("Scarta", key=f"pr-{agent.name}-{i}"):
                                p.status = "rejected"; st.rerun()

    with t3:
        approved = [p for ps in S.get("proposals", {}).values() for p in ps if p.status == "approved"]
        if not approved:
            st.info("Approva qualche proposta degli agenti nel tab 2.")
        else:
            st.write("Per ogni concetto, il piano tocca tutti i lati: nessuno porta da solo la colpa del gap (ADR 0002).")
            titles = {a.name: a.title for a in AGENTS}
            for cid in dict.fromkeys(p.concept_id for p in approved):
                with st.container(border=True):
                    st.markdown(f"### {name.get(cid, cid)}")
                    for p in (p for p in approved if p.concept_id == cid):
                        st.markdown(f"**{titles[p.agent]}** · {p.target_ref}: {p.change}")

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

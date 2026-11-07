# The Lazy Prof · AI on Campus

Progetto per il **Reply Student Tech Clash 2026**, challenge *AI on Campus*.

**Il problema.** Al Politecnico molti esami sono così standardizzati che si superano ricalcando i temi degli anni precedenti, senza capire la materia. A volte l'esame non segue nemmeno quello che si insegna: per Calcolatori Elettronici gli esami dal 2019 al 2025-01 usano MIPS, mentre le slide insegnano RISC-V.

**La soluzione.** Un assistente per il docente con tre agenti che lavorano sul materiale reale del corso (slide, temi d'esame, programma). Ognuno fa una proposta concreta e motivata, e il docente la approva o la scarta. Nessun agente modifica un file da solo.

| Agente | Cosa risolve | Cosa produce |
|---|---|---|
| **Revisore esami** | Esercizi che si ripetono quasi uguali negli anni ed esami non allineati alle slide | Confronto prima/dopo di ogni esercizio, con la riscrittura e il dato che la giustifica |
| **Revisore materiali** | Slide con errori, tecnologie superate o lacune rispetto al programma | Micro-modifiche slide per slide con anteprima visiva, più una copia delle slide con grafica uniforme |
| **Creatore di survey** | Non sapere se gli studenti hanno capito o solo memorizzato lo schema | Coppie di esercizi (tipico e variante) che lo studente risolve, con un feedback che guida senza dare la soluzione |

Documenti collegati: [architettura](docs/architettura.md) · [esempi di interazione](docs/esempi-interazioni.md) · [decisioni (ADR)](docs/adr/) · [glossario](CONTEXT.md) · [contesto del progetto](docs/handover.md)

---

## Come si avvia

Serve Python 3.10 o più recente.

```bash
pip install -r requirements.txt
cp .env.example .env        # metti la chiave OpenAI in .env (git lo ignora)
streamlit run app.py        # oppure: streamlit run streamlit_app.py
```

Poi nel browser:

1. **Professore** → scegli il corso (per esempio `calcolatori-elettronici`) → il corso si carica da solo, con circa 30 secondi per leggere i PDF.
2. Scegli l'agente dal menu **Agente**.
3. **Studente** → risponde alle survey che il professore ha approvato.

**Senza chiave OpenAI** l'app funziona lo stesso in modalità offline. Usa risposte di riserva deterministiche e un embedding locale. Per forzarla anche con la chiave basta `OFFLINE=1`.

Test: `OFFLINE=1 python -m pytest -q`. `test_offline_concepts_on_example_course` fallisce perché il corso d'esempio `data/esempio-poo` non è più nella repo.

### Variabili d'ambiente

| Variabile | Default | A cosa serve |
|---|---|---|
| `OPENAI_API_KEY` | — | Senza questa chiave l'app gira offline |
| `OPENAI_MODEL` | `gpt-4o-mini` | Modello per tutte le chiamate di testo (JSON mode) |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | Embedding per il RAG |
| `OFFLINE` | — | Con `1` forza la modalità offline |
| `CACHE_DIR` | `.cache` | Cache su disco delle risposte LLM e degli embedding |

Le risposte dell'LLM vengono salvate in `.cache/`. Se si fa un giro completo online prima della presentazione, la demo funziona anche senza rete.

## Modelli e librerie

- **OpenAI** `gpt-4o-mini` in JSON mode (`response_format=json_object`, temperatura 0.4, un retry) e `text-embedding-3-small`. Tutte le chiamate passano da `app/llm.py`.
- **Streamlit**: l'interfaccia.
- **pypdf** e **PyMuPDF**: testo dai PDF, anteprime e PDF modificati. **python-pptx** e **python-docx**: lettura e riscrittura di PPTX e DOCX.
- **NumPy** e **pandas**: similarità coseno del RAG e tabelle.
- **pytest**: i test.

## Logica personalizzata

Le parti che non sono "chiedi all'LLM", e che quindi rendono i risultati verificabili:

- **Somiglianza tra esami** (`app/exam_review.py`). Ogni domanda d'esame recente viene confrontata con tutte quelle degli appelli precedenti misurando le parole in comune (indice di Jaccard), dopo aver tolto le intestazioni (nome, matricola, tempo, istruzioni). Sopra 0.35 la domanda conta come "già vista". La **prevedibilità** è la quota dei punti d'esame che sta su domande già viste. È deterministica e il docente può controllarla.
- **Architettura insegnata contro architettura esaminata** (`app/exam_review.py`). Conta i marcatori di x86, MIPS e RISC-V nelle slide e in ogni tema d'esame e segnala i periodi in cui non coincidono.
- **Lettura degli esami** (`app/ingest.py`). Ogni pagina di un PDF d'esame diventa un blocco, citato come `<file> p.N`. I punti si stimano dalla sezione: risposta chiusa 1, risposta aperta 5, "sino a N punti" vale N. La PR #14, ancora aperta, divide gli esami in singole domande; l'agente esami funziona con entrambe le versioni.
- **RAG leggero** (`app/rag.py`). Embedding in memoria e similarità coseno. Ogni proposta cita le slide da cui viene.
- **Modalità offline coerente** (`app/llm.py`). Ogni chiamata ha una risposta di riserva. Se un embedding fallisce, tutto passa a offline, così vettori di dimensioni diverse non si mescolano mai.
- **Il docente decide sempre.** Ogni proposta nasce `pending`. I file originali non vengono mai toccati: il Revisore materiali scrive solo in `new_slides/`, e solo dopo un'approvazione.

## Struttura della repo

```
app.py                     avvio Streamlit (registra il pacchetto app/ e lancia streamlit_app.py)
streamlit_app.py           interfaccia: area Professore (3 agenti) e area Studente
app/
  ingest.py                lettura dei corsi da data/<corso>/ e divisione in blocchi (Chunk)
  llm.py                   unico accesso a OpenAI, cache e modalità offline
  rag.py                   indice di embedding e citazioni
  concepts.py              mappa dei concetti del corso
  models.py                contratto dati condiviso (Chunk, Concept, Exercise, Answer, Proposal…)
  exam_review.py, exam_ui.py, agents/esami.py      Revisore esami
  materials_update.py                              Revisore materiali
  exercises.py, grading.py                         Creatore di survey e correzione
  agents/, orchestrator.py  interfaccia comune degli agenti e avvio in parallelo (ADR 0006)
  metrics.py, insights.py, simulate.py, practice.py, material_review.py, lessons.py
                            moduli della sonda di transfer: testati ma non ancora collegati all'interfaccia
data/<corso>/              slides/, exams/, program/, expected_results/, config.json (facoltativo)
docs/                      architettura, esempi, ADR, handover
tests/                     test pytest, tutti offline
```

### Aggiungere un corso

Si crea `data/<corso>/` con `slides/` ed `exams/` (PDF, PPTX, DOCX, MD o TXT). Il codice non dipende dal corso. Gli esami vanno chiamati con la data nel nome (`YYYY_MM_DD.pdf`), così l'agente esami ricostruisce lo storico. Un `config.json` facoltativo con `{"exams_from": "2019-06"}` aggiunge un filtro che esclude gli esami più vecchi dall'analisi. Lo storico completo resta comunque usato come termine di confronto.

## Limiti noti

- Le riscritture degli esercizi d'esame e le micro-modifiche alle slide sono buone solo quanto l'LLM. Offline si vedono solo i testi di riserva.
- Offline la correzione delle survey conta le parole chiave della rubrica, quindi è approssimativa.
- Senza chiave, il RAG offline (embedding a hash) a volte abbina slide poco pertinenti.
- I dati degli studenti sono sintetici: non abbiamo usato dati reali.

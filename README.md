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
cp .env.example .env        # scegli il provider LLM in .env (git lo ignora), vedi sotto
streamlit run app.py        # oppure: streamlit run streamlit_app.py
```

Poi nel browser:

1. **Professore** → scegli il corso (per esempio `calcolatori-elettronici`) → il corso si carica da solo, con circa 30 secondi per leggere i PDF.
2. Scegli l'agente dal menu **Agente**.
3. **Studente** → risponde alle survey che il professore ha approvato.

**Senza nessun provider configurato** l'app funziona lo stesso in modalità offline. Usa risposte di riserva deterministiche e un embedding locale. Per forzarla anche con un provider configurato basta `OFFLINE=1`.

### Provider LLM

Tutte le chiamate passano da `app/llm.py` con l'SDK OpenAI, quindi va bene qualsiasi servizio compatibile con l'API OpenAI. Chat ed embedding si scelgono separatamente. In `.env.example` ci sono i blocchi pronti da copiare. La barra laterale dell'app mostra provider e modello in uso.

| Provider | Costo | Chat (default) | Embedding (default) | Note |
|---|---|---|---|---|
| `gemini` | piano gratuito | `gemini-2.5-flash` | `gemini-embedding-001` | Chiave in `GEMINI_API_KEY` da [AI Studio](https://aistudio.google.com/apikey). Pochi messaggi al minuto: l'app aspetta e riprova da sola. Sul piano gratuito Google può usare i dati per l'addestramento, quindi solo dati sintetici. |
| `ollama` | gratis, in locale | `qwen2.5:7b` | `nomic-embed-text` | `ollama pull qwen2.5:7b` e `ollama pull nomic-embed-text`. Nessuna chiave. Più lento e meno preciso. Avvia Ollama con `OLLAMA_CONTEXT_LENGTH=16384`, altrimenti i prompt lunghi vengono tagliati senza avviso. |
| `openai` | a pagamento | `gpt-6-luna` | `text-embedding-3-small` | Come all'hackathon: valgono ancora `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_EMBED_MODEL`. |
| `custom` | dipende | — | — | Qualsiasi endpoint compatibile: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. |
| `offline` | — | — | hash delle parole | Solo per `EMBED_PROVIDER`, per esempio con Groq o OpenRouter che non hanno embedding. |

Cambiare modello di embedding cambia la dimensione dei vettori, ma la cache è separata per modello e i vettori di modelli diversi non si mescolano mai.

Test: `OFFLINE=1 python -m pytest -q` (tutti verdi; `data/esempio-poo/` è di nuovo nella repo come corso di prova offline).

### Variabili d'ambiente

| Variabile | Default | A cosa serve |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `gemini`, `ollama`, `openai` o `custom` per la chat |
| `LLM_MODEL` | dipende dal provider | Modello per tutte le chiamate di testo (JSON mode) |
| `LLM_API_KEY` | — | Chiave del provider (oppure `GEMINI_API_KEY` / `OPENAI_API_KEY`). Senza chiave l'app gira offline, tranne con Ollama |
| `LLM_BASE_URL` | dipende dal provider | Indirizzo dell'API compatibile con OpenAI |
| `EMBED_PROVIDER` | uguale a `LLM_PROVIDER` | Provider degli embedding, anche `offline` |
| `EMBED_MODEL`, `EMBED_API_KEY`, `EMBED_BASE_URL` | come la chat se il provider è lo stesso | Embedding per il RAG |
| `RAG_MIN_SIM` | `0.25` | Soglia di pertinenza del RAG, tarata su OpenAI |
| `OFFLINE` | — | Con `1` forza la modalità offline |
| `CACHE_DIR` | `.cache` | Cache su disco delle risposte LLM e degli embedding |

Le risposte dell'LLM vengono salvate in `.cache/`. Se si fa un giro completo online prima della presentazione, la demo funziona anche senza rete.

## Script della demo ("The Lazy Prof", ADR 0007)

1. **Professore → scegli il corso → Carica corso.** Il filtro "Usa solo gli esami dal …" esclude gli appelli su un'architettura diversa da quella delle slide.
2. **Creatore di survey**: scegli una lezione, "Crea survey per questa lezione", poi Approva/Scarta le varianti (ADR 0003). Senza varianti approvate non si misura nulla.
3. **Diagnosi transfer gap**: "Simula una classe di 20 studenti" e mostra il transfer gap per concetto (tipiche contro varianti) e la distanza insegnato ↔ testato.
4. **Revisore esami**: esercizi d'esame ricalcabili dagli appelli vecchi o su un'architettura diversa dalle slide, con il confronto prima/dopo. Le motivazioni citano il transfer gap della Diagnosi.
5. **Revisore materiali**: "Ammoderna" rinnova le slide PPTX in `data/<corso>/new_slides/` (ignorata da git), poi micro-modifiche da approvare.
6. **Studente**: risponde alla coppia tipica + variante di una survey approvata e riceve un feedback che guida senza dare la soluzione.

Formati dei nomi d'esame riconosciuti per la data: `YYYY_MM_DD`, `YYYYMMDD`, `DDMMYY` (es. `040723.pdf` = luglio 2023).

## Modelli e librerie

- **LLM compatibile con l'API OpenAI** in JSON mode (`response_format=json_object`, temperatura 0.4, ripetuta senza temperatura se il modello la rifiuta). All'hackathon `gpt-6-luna` e `text-embedding-3-small`, ora anche Gemini e Ollama (vedi "Provider LLM"). Tutte le chiamate passano da `app/llm.py`.
- **Streamlit**: l'interfaccia.
- **pypdf** e **PyMuPDF**: testo dai PDF, anteprime e PDF modificati. **python-pptx** e **python-docx**: lettura e riscrittura di PPTX e DOCX.
- **NumPy** e **pandas**: similarità coseno del RAG e tabelle.
- **pytest**: i test.

## Logica personalizzata

Le parti che non sono "chiedi all'LLM", e che quindi rendono i risultati verificabili:

- **Somiglianza tra esami** (`app/exam_review.py`). Ogni domanda d'esame recente viene confrontata con tutte quelle degli appelli precedenti misurando le parole in comune (indice di Jaccard), dopo aver tolto le intestazioni (nome, matricola, tempo, istruzioni). Sopra 0.35 la domanda conta come "già vista". La **prevedibilità** è la quota dei punti d'esame che sta su domande già viste. È deterministica e il docente può controllarla.
- **Architettura insegnata contro architettura esaminata** (`app/exam_review.py`). Conta i marcatori di x86, MIPS e RISC-V nelle slide e in ogni tema d'esame e segnala i periodi in cui non coincidono.
- **Lettura degli esami** (`app/ingest.py`). Ogni pagina di un PDF d'esame diventa un blocco, citato come `<file> p.N`. I punti si stimano dalla sezione: risposta chiusa 1, risposta aperta 5, "sino a N punti" vale N. Il RAG indicizza ogni domanda d'esame come un blocco a sé, con una soglia di pertinenza.
- **RAG leggero** (`app/rag.py`). Embedding in memoria e similarità coseno. Ogni proposta cita le slide da cui viene.
- **Modalità offline coerente** (`app/llm.py`). Ogni chiamata ha una risposta di riserva. Se un embedding fallisce, tutto passa a offline, così vettori di dimensioni diverse non si mescolano mai.
- **Il docente decide sempre.** Ogni proposta nasce `pending`. I file originali non vengono mai toccati: il Revisore materiali scrive solo in `new_slides/`, e solo dopo un'approvazione.

## Struttura della repo

```
app.py                     avvio Streamlit (registra il pacchetto app/ e lancia streamlit_app.py)
streamlit_app.py           interfaccia: area Professore (Diagnosi transfer gap + 3 agenti) e area Studente
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
  metrics.py, simulate.py, lessons.py                transfer gap e classe simulata (Diagnosi, ADR 0007)
  insights.py, practice.py, material_review.py      testati ma non ancora collegati all'interfaccia
data/<corso>/              slides/, exams/, program/, expected_results/, config.json (facoltativo)
docs/                      architettura, esempi, ADR, handover
tests/                     test pytest, tutti offline
```

### Aggiungere un corso

Si crea `data/<corso>/` con `slides/` ed `exams/` (PDF, PPTX, DOCX, MD o TXT). Il codice non dipende dal corso. Gli esami vanno chiamati con la data nel nome (`YYYY_MM_DD.pdf`), così l'agente esami ricostruisce lo storico. Un `config.json` facoltativo con `{"exams_from": "2019-06"}` aggiunge un filtro che esclude gli esami più vecchi dall'analisi. Lo storico completo resta comunque usato come termine di confronto.

## Limiti noti

- Le riscritture degli esercizi d'esame e le micro-modifiche alle slide sono buone solo quanto l'LLM. Offline si vedono solo i testi di riserva.
- Offline la correzione delle survey conta le parole chiave della rubrica, quindi è approssimativa.
- Senza provider, il RAG offline (embedding a hash) a volte abbina slide poco pertinenti.
- I dati degli studenti sono sintetici: non abbiamo usato dati reali.

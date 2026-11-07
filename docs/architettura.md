# Architettura

Come ragiona The Lazy Prof: cosa riceve, che conoscenza usa, con quali strumenti, chi decide e cosa restituisce.

```
           INPUT                       KNOWLEDGE                    TOOLS / AGENTI                 DECISIONI           OUTPUT
 ┌─────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────┐    ┌────────────────┐   ┌──────────────────────┐
 │ data/<corso>/       │    │ Chunk (blocchi citabili) │    │ Revisore esami           │    │ Docente:       │   │ Esercizi d'esame     │
 │  slides/  (PDF,PPTX)│──▶ │ Indice RAG (embedding)   │──▶ │ Revisore materiali       │──▶ │ Approva/Scarta │──▶│ riscritti (prima/dopo)│
 │  exams/   (PDF)     │    │ Mappa dei concetti       │    │ Creatore di survey       │    │ ogni proposta  │   │ new_slides/ corrette │
 │  program/, expected │    │ Storico esami per data   │    │ (OpenAI via app/llm.py)  │    │                │   │ Survey per studenti  │
 │ Risposte studenti   │    │ Programma + requisiti    │    │                          │    │ Studente:      │   │ Feedback socratico   │
 └─────────────────────┘    └──────────────────────────┘    └──────────────────────────┘    │ risponde       │   └──────────────────────┘
                                                                                             └────────────────┘
```

## 1. Input

- **Materiale del corso** in `data/<corso>/`:
  - `slides/`: PDF, PPTX, DOCX, MD o TXT;
  - `exams/`: temi d'esame con la data nel nome del file;
  - `program/`: programma ufficiale;
  - `expected_results/`: risultati di apprendimento attesi.
- **Configurazione del corso** (`config.json`, facoltativa): per esempio `exams_from`, la data da cui partono gli esami da analizzare.
- **Scelte del docente** nell'interfaccia: il corso, l'agente, la lezione o la slide da rivedere.
- **Risposte degli studenti** alle survey approvate.

## 2. Knowledge (cosa sa il sistema)

| Conoscenza | Dove nasce | A cosa serve |
|---|---|---|
| `Chunk`: pagina di slide o di esame, con riferimento citabile (`04 - RISC V p.12`) e punti | `app/ingest.py` | Unità di base: tutto quello che il sistema dice rimanda a un chunk |
| Indice RAG | `app/rag.py` + `app/llm.py` (`text-embedding-3-small`, oppure hash offline) | Trova le slide pertinenti a un esercizio o a un concetto |
| Mappa dei concetti | `app/concepts.py` (LLM sul materiale, fallback sui nomi dei file) | Raggruppa slide ed esercizi per argomento |
| Storico degli esami per data | `app/agents/esami.py` rilegge tutti gli esami, anche quelli esclusi dal filtro | Termine di confronto per capire se una domanda è "già vista" |
| Programma e requisiti attesi | `program/`, `expected_results/` | Vincolano le micro-modifiche alle slide |

Il sistema usa **solo il materiale del corso** come fonte (ADR 0004). L'LLM non cerca sul web.

## 3. Tools (gli agenti)

Ogni agente è isolato: riceve il contesto del corso, restituisce proposte, non scrive file per conto suo e non chiama gli altri agenti. L'interfaccia comune è in `app/agents/base.py` (ADR 0006).

### Revisore esami (`app/exam_review.py`, `app/agents/esami.py`, `app/exam_ui.py`)

1. **Storico**: carica tutti i temi d'esame del corso.
2. **Domande ricalcabili**: per ogni domanda recente calcola la somiglianza di Jaccard sulle parole con tutte le domande degli appelli precedenti, senza le intestazioni. Sopra 0.35 conta come "già vista". Le domande vengono ordinate per somiglianza × punti × ripetizioni.
3. **Disallineamento d'architettura**: conta i marcatori x86, MIPS e RISC-V negli esami e nelle slide e raggruppa per periodo i casi in cui non coincidono.
4. **Riscrittura**: per le 3 domande peggiori l'LLM riceve la domanda, quella vecchia più simile e le slide pertinenti. Riscrive la domanda con lo stesso concetto e la stessa difficoltà, in una forma che non si risolve ricalcando, con la notazione delle slide e una rubrica.
5. **Proposte**: ognuna viene legata a un concetto. Il disallineamento d'architettura va in cima.

### Revisore materiali (`app/materials_update.py`)

1. **Analisi in memoria** di PPTX, PDF, DOCX, MD e TXT: testo, blocchi, immagini, sottoargomenti per lezione. In questa fase non crea file.
2. **Modernizzazione grafica**, solo su richiesta: crea in `new_slides/` una copia con grafica uniforme. È deterministica: il testo non viene riscritto e le immagini restano quelle originali.
3. **Micro-modifiche**: per la slide scelta, l'LLM propone piccole correzioni vincolate a programma e requisiti attesi, citando il testo esatto da cambiare.
4. **Anteprima** prima/dopo renderizzata e **applicazione** solo alla copia in `new_slides/`, solo dopo l'approvazione.

### Creatore di survey (`app/exercises.py`, `app/grading.py`)

1. Per i concetti di una lezione genera una coppia: un esercizio **tipico**, nella forma dei temi d'esame, e una **variante**, con lo stesso concetto in forma nuova. Ognuno ha una rubrica e le fonti citate.
2. Lo studente vede solo le varianti approvate. La correzione assegna un punteggio con la rubrica e un **feedback socratico** che indica dove riflettere senza dare la soluzione.

### Supporto comune

- `app/llm.py`: unico accesso a OpenAI, in JSON mode, con cache su disco, un retry e un fallback offline per ogni chiamata. Gli errori compaiono nell'interfaccia.
- `app/orchestrator.py`: avvia gli agenti dell'interfaccia comune in parallelo (`ThreadPoolExecutor`). Se un agente fallisce, gli altri non si fermano.

## 4. Decisioni

| Chi decide | Cosa | Dove è scritto |
|---|---|---|
| **Docente** | Approva o scarta ogni proposta (esercizio riscritto, micro-modifica, variante). Senza approvazione non cambia niente | ADR 0003 |
| **Docente** | Avvia la modernizzazione grafica: è l'unico passo che crea file, e solo in `new_slides/` | `materials_update.modernize_materials` |
| **Sistema (regole deterministiche)** | Quali domande sono "già viste" (soglia 0.35) e quale architettura domina | `exam_review.py` |
| **Sistema (LLM)** | Il testo delle riscritture, delle micro-modifiche e del feedback, sempre con le fonti | prompt in `exam_review.py`, `materials_update.py`, `exercises.py`, `grading.py` |
| **Responsabilità condivisa** | Un disallineamento non è mai colpa di un solo lato: slide, esame e studio sono tutti coinvolti | ADR 0002 |

**Confini che il sistema rispetta:**

- non modifica mai i file originali del corso;
- non dà allo studente la soluzione di una survey;
- non pubblica proposte non approvate;
- non inventa fonti: ogni proposta cita i chunk da cui nasce;
- non usa dati reali di studenti.

## 5. Output

- **Revisore esami**:
  - quota dei punti d'esame su domande già viste;
  - schede **prima/dopo**: la domanda attuale con riferimento e punti accanto alla riscrittura, con il motivo (somiglianza, appello da cui è copiata, ripetizioni) e i pulsanti Approva e Scarta.
- **Revisore materiali**:
  - sottoargomenti per lezione;
  - anteprima prima/dopo di ogni micro-modifica;
  - file scaricabile da `new_slides/`.
- **Creatore di survey**:
  - coppie tipico/variante con le fonti;
  - per lo studente, un punteggio e un feedback che guida senza svelare la soluzione.

# Spec – Sonda di transfer (demo hackathon)

Status: ready-for-human
Consegna: 2026-11-07, tra le 15:00 e le 16:00. Contesto completo in `docs/handover.md`, termini in `CONTEXT.md`, decisioni in `docs/adr/`.

## Problema

Molti esami sono così standardizzati che si impara a passare l'esame, non la materia. I dati (quiz, voti) esistono ma nessuno li traduce in decisioni. Ci concentriamo su insegnato ↔ testato, con il transfer gap come metrica principale.

## Cosa fa la demo

Un ciclo unico, tutto in Streamlit, indipendente dal corso (il materiale sta in `data/<corso>/`):

1. **Materiale → mappa dei concetti.** Carica slide e temi d'esame, li spezza in blocchi, li indicizza (RAG leggero, ADR 0004). L'LLM propone la mappa dei concetti; il docente conferma o corregge.
2. **Coppie di verifica.** Per ogni concetto: un esercizio tipico (nello stile dei temi d'esame) e una variante in forma nuova, con rubrica e fonti citate. Le varianti vanno in coda e il docente le approva o le scarta (ADR 0003).
3. **Classe simulata.** ~20 studenti sintetici rispondono con errori realistici (alcuni bravi sugli schemi ma deboli sulle varianti). I membri del team possono rispondere dal vivo nella vista studente.
4. **Correzione.** L'LLM assegna punteggio 0..1, un feedback che guida senza dare la soluzione e un'etichetta dell'errore.
5. **Metriche.** Per concetto: transfer gap (classe e studente) e indice di copertura (quota slide vs quota punti d'esame).
6. **Disallineamenti.** Per i concetti con gap o distanza di copertura più alti, l'agente spiega cosa significano e dà tre suggerimenti: slide/lezioni, esame, studente (ADR 0002). Vista studente: i miei gap e cosa ripassare.

Fuori dalla demo: controllo della bozza d'esame, Level 3, dati reali, esecuzione di codice. Vedi `still-to-do.md`.

## Architettura

```
data/<corso>/slides/*.md|.pdf, data/<corso>/exams/*.md
        │
app/ingest.py     → list[Chunk] + embedding (numpy, in memoria)          [ticket 01]
app/rag.py        → retrieve(query, k) -> list[Chunk]                     [ticket 01]
app/concepts.py   → extract_concepts(chunks) -> list[Concept]             [ticket 01]
app/exercises.py  → make_pair(concept) -> (Exercise typical, Exercise variant)  [ticket 01]
app/grading.py    → grade(exercise, answer) -> Answer (score, feedback, error_tag)  [ticket 01]
app/simulate.py   → simulate_class(exercises, n=20) -> list[Answer]       [ticket 02]
app/metrics.py    → concept_metrics(...) -> list[ConceptMetrics]          [ticket 02]
app/insights.py   → misalignments(metrics, answers) -> list[Misalignment] [ticket 01]
streamlit_app.py  → vista Docente / vista Studente                        [ticket 03]
```

Il contratto dati è `app/models.py`: si lavora in parallelo contro quelle classi. Tutte le chiamate OpenAI passano da un'unica funzione in `app/llm.py` (modello e chiave da variabili d'ambiente `OPENAI_MODEL`, `OPENAI_API_KEY`), così si può aggiungere una modalità **offline/cache** per la demo.

## Gestione degli errori

- API non raggiungibile o chiave mancante: la UI mostra un avviso e usa le risposte salvate in cache (`.cache/`, non committata). La demo deve girare anche senza rete.
- Output dell'LLM non valido: chiedere JSON, validare contro i dataclass, un retry, poi scartare l'elemento con un messaggio.
- Varianti non approvate non arrivano mai agli studenti.

## Test (minimi, per la demo)

- `metrics.py`: test unitari su transfer gap e copertura con dati finti.
- Prova completa del ciclo con il materiale di `data/` prima della consegna (ticket 04).

## Rischi da dichiarare nel pitch

Proprietà e privacy dei dati degli studenti; tool non disponibile la notte prima dell'esame; accesso disuguale; errori dell'AI nelle mappature (mitigati da RAG con citazioni e approvazione del docente).

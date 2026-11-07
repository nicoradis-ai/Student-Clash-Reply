# 01 – Pipeline LLM: ingest, RAG, concetti, varianti, correzione, disallineamenti

Status: ready-for-human
Owner: A

Implementa `app/llm.py`, `app/ingest.py`, `app/rag.py`, `app/concepts.py`, `app/exercises.py`, `app/grading.py`, `app/insights.py` secondo `spec.md` e `app/models.py`.

## Criteri di accettazione
- `llm.py`: una funzione `chat_json(system, user) -> dict` e una `embed(texts) -> np.ndarray`, con cache su disco (`.cache/`) e lettura di `OPENAI_API_KEY` / `OPENAI_MODEL`.
- Ingest legge `.md` (e `.pdf` se c'è tempo) da `data/<corso>/`, produce `Chunk` con `ref` leggibile e, per gli esami, i punti.
- Ogni esercizio, correzione e disallineamento cita i chunk usati.
- Il feedback della correzione guida lo studente e non contiene la soluzione.
- Ogni `Misalignment` ha tutti e tre i suggerimenti compilati.

## Comments

- 2026-11-07 (Claude): c'è già una prima versione funzionante (PR "Scheletro funzionante"), anche offline. Il ticket ora è: migliorare la propria parte, prompt e qualità, senza cambiare le firme delle funzioni.

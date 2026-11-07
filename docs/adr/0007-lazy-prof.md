# 0007 – "The Lazy Prof": tre strumenti per il docente, con la diagnosi davanti

Stato: accettato (2026-11-07). Sostituisce la 0006 per la UI.

## Contesto
Luca ha riorganizzato la UI (commit diretti su main) attorno al tempo risparmiato dal docente: Revisore esami,
Revisore materiali (restyling delle slide con micro-modifiche) e Creatore di survey. In quel passaggio il
transfer gap era sparito dalla UI: lo studente rispondeva solo alle varianti e le metriche erano sempre a zero.
Revisore e implementatore si sono confrontati e hanno concordato le correzioni.

## Decisione
- Si tiene la UI di Luca. Si aggiunge come prima voce **Diagnosi transfer gap** (simulazione della classe e
  metriche per concetto). Il Revisore esami usa le stesse risposte, quindi le sue motivazioni riportano il gap.
- Lo studente risponde alla coppia **tipica + variante**: senza entrambe la metrica principale (ADR 0001) non esiste.
- Il Revisore materiali in UI è `materials_update` (restyling deterministico più micro-modifiche via LLM). Non usa
  ancora i concetti focus: `material_review` resta nel codice.
- `orchestrator` e `app/agents/` (ADR 0006) restano nel codice ma non sono collegati.

## Conseguenze
- Da fare dopo: ricollegare gli agenti tramite `build_context`/orchestrator e unire i due revisori del materiale
  (vedi `still-to-do.md`).

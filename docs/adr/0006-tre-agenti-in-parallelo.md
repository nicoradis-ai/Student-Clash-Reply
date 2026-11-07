# 0006 – Tre agenti in parallelo: materiale, esercitazioni, esami

Stato: accettato (2026-11-07)

## Contesto
La prima versione mostrava come prima schermata un elenco di lezioni e correzioni brevi slide per slide, su
argomenti presi senza criterio: non si capiva quale problema risolvesse. Dal confronto in team: il problema da
mostrare è il **transfer gap** (gli studenti risolvono l'esercizio tipico ma non la variante), e gli interventi
devono toccare i tre lati dove nasce (ADR 0002).

## Decisione
- La UI docente ha tre passi: **1 · Diagnosi** (transfer gap per concetto, prima di tutto), **2 · Tre agenti**,
  **3 · Piano approvato**. Spariscono le tab "Lezioni" e "Correzioni slide".
- Tre agenti indipendenti in `app/agents/`: `materiale` (slide), `esercitazioni` (esercizi di pratica, cartella
  `exercises/` del corso), `esami` (temi d'esame). Interfaccia comune in `app/agents/base.py`:
  `run(ctx: CourseContext) -> list[Proposal]`, con `name`, `title`, `goal`.
- Gli agenti lavorano solo sui concetti di `ctx.focus()` (gap + distanza insegnato/testato più alti), mai su
  argomenti a caso. Ogni `Proposal` porta il dato che la giustifica (`rationale`).
- `app/orchestrator.py` li esegue in parallelo (thread); un agente che fallisce non blocca gli altri.
- Il docente approva o scarta ogni proposta, come le varianti (ADR 0003).

## Conseguenze
- Ogni membro del team possiede un agente e lo migliora senza toccare gli altri file.
- Gli agenti non chiamano Streamlit e non modificano il contesto (necessario per il parallelismo).
- `lessons.py` e `insights.misalignments` non sono più usati dalla UI; restano come riferimento.

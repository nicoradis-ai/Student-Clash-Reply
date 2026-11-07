# Still to do – dopo l'hackathon

Cose decise o emerse ma lasciate fuori dalla demo, per continuare a sviluppare l'idea.

- [ ] Controllo della bozza d'esame: prima dell'appello l'agente confronta la bozza con programma e lezioni (ex approccio 3, ora funzione dell'approccio 1).
- [ ] Parere degli studenti dopo l'esame, collegato ai disallineamenti.
- [ ] Metriche lato docente complete: diversità degli esercizi d'esame (schemi distinti, quota di punti sui più frequenti), tasso di azione, accordo con il docente tracciato nel tempo.
- [ ] Gli altri due disallineamenti: testato ↔ capito e testato ↔ mondo reale.
- [ ] Esecuzione e test automatici del codice scritto dagli studenti (per i corsi di programmazione).
- [ ] Dati reali: consenso, anonimizzazione, proprietà dei dati, integrazione con le piattaforme del Poli.
- [ ] Disponibilità: funzionamento offline / la notte prima dell'esame; accesso equo.
- [ ] Database vettoriale e persistenza al posto della memoria e della cache.
- [ ] Level 3: sistema multi-agente, knowledge graph dei concetti, campagna di lancio.
- [ ] Validazione con un docente vero su un corso vero.
- [ ] Ricollegare `orchestrator` e `app/agents/` alla UI "Lazy Prof" (oggi `exam_ui._context` ricostruisce `CourseContext` a mano invece di usare `build_context`). Vedi ADR 0007.
- [ ] Unire `material_review` (guidato da gap ed esami) e `materials_update` (restyling): passare i concetti focus al restyling, così le micro-modifiche nascono dal transfer gap.

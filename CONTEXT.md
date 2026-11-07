# Glossario – AI on Campus

Termini del dominio. Usali così come sono definiti qui, nel codice, nei ticket e nel pitch.

- **Concetto**: un'unità del programma del corso (es. "polimorfismo", "pipeline"). La mappa dei concetti è estratta dall'AI dal materiale e validata dal docente.
- **Materiale del corso**: slide e temi d'esame passati in `data/`. Il sistema è indipendente dal corso: cambiare corso = cambiare i file.
- **Esercizio tipico**: esercizio nella forma ricorrente dei temi d'esame, risolvibile riconoscendo lo schema.
- **Variante**: esercizio sullo stesso concetto in forma nuova (leggere codice, trovare il bug, scegliere tra due design). Generata dall'AI, **approvata dal docente** prima di arrivare agli studenti.
- **Coppia di verifica**: un esercizio tipico + una variante sullo stesso concetto.
- **Transfer gap**: per concetto, punteggio medio sugli esercizi tipici meno punteggio medio sulle varianti. Vale per studente e per classe. È la metrica principale.
- **Indice di copertura**: per concetto, peso nell'insegnamento (quota di slide) contro peso nell'esame (quota di punti); la distanza tra le due distribuzioni.
- **Disallineamento**: una segnalazione dell'agente su un concetto, con le prove e **tre suggerimenti**: uno sulle slide/lezioni, uno sull'esame, uno per lo studente. Mai un solo destinatario.
- **Accordo con il docente**: quota di concetti, varianti e interpretazioni che il docente valida come corretti.
- **Tasso di azione**: quota di disallineamenti che portano a un cambiamento concreto.

_Da evitare_: "colpa", "errore del docente/studente". Si parla di disallineamento.

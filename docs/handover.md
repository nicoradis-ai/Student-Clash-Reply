# Handover – Hackathon AI on Campus

Nov 7, 2026 · @Niccolò

## Contesto: la challenge

Reply Student Tech Clash 2026, "AI on Campus": scegliere un problema reale su come si insegna, si impara o si valuta all'università e progettare una soluzione AI. Amministrazione e logistica sono fuori ambito. [Pagina della challenge](https://studentclash.reply.com/challenges/AI_on_Campus_IT.html)

- **Level 1 (obbligatorio):** problema + soluzione AI, presentati in un pitch di 60 secondi senza slide. Le prime 3 squadre passano a una presentazione con slide di massimo 5 minuti.
- **Level 2 (obbligatorio):** un agente funzionante, con o senza codice. Deve usare materiale universitario vero, fare almeno un'azione oltre a rispondere (es. generare e correggere un quiz, tracciare gli errori, segnalare al docente) e restare un tutor che guida, non che risponde al posto dello studente.
- **Level 3 (facoltativo):** sistema multi-agente, knowledge graph o campagna di lancio.
- **Consigli della giuria:** partire dall'esperienza personale; essere specifici (un corso, un esame); rispondere a "funzionerebbe senza AI?"; dichiarare i rischi (dati degli studenti, tool non disponibile la notte prima dell'esame, accesso disuguale).

## Problema e perché serve l'AI

Al Politecnico molti esami sono così standardizzati che basta allenarsi sui temi d'esame vecchi e imparare gli esercizi tipo come algoritmi. Si impara a passare l'esame, non la materia. È l'esperienza diretta di Niccolò.

- **Il problema di fondo:** i dati sull'apprendimento esistono già (Kahoot, quiz, voti), ma nessuno li traduce in decisioni. Il docente vede "il 40% ha sbagliato la domanda 3" senza sapere perché né cosa cambiare.
- **I tre disallineamenti:** insegnato ↔ testato; testato ↔ capito (lo studente riconosce lo schema, non il concetto); testato ↔ mondo reale.
- **Perché senza AI non funziona:** servono varianti sempre nuove degli esercizi, che non si possono memorizzare, e la lettura dei ragionamenti scritti per capire quale concetto manca dietro un errore. Collegare risposte libere, programma e temi d'esame in base al significato richiede di comprendere il linguaggio; un cruscotto di percentuali non basta.
- **Il ruolo dell'agente:** interpreta i trend e ne restituisce il significato. Non decide: il compromesso finale lo trovano docente e studenti.

## Decisioni prese

La direzione è decisa: uno strumento per docenti e studenti, centrato su insegnato ↔ testato, con il transfer gap come metrica principale.

| Tema | Decisione | Motivo |
| --- | --- | --- |
| Utenti | Docenti e studenti insieme, con scambio continuo di dati | L'obiettivo è tenere allineati gli argomenti insegnati e quelli testati |
| Disallineamento centrale | Insegnato ↔ testato | Con i dati di studenti e docenti si allinea anche a testato ↔ capito e testato ↔ mondo reale |
| Metrica principale | Transfer gap per concetto: punteggio sugli esercizi in forma tipica meno punteggio sulle varianti in forma nuova | La più utile e globale; vale per studente e classe |
| Metriche lato docente | Diversità degli esercizi, indice di copertura, tasso di azione, accordo con il docente | Servono al docente per decidere e mostrano che l'AI è affidabile |
| Da non usare come obiettivo | Tasso di superamento | Può salire solo perché l'esame diventa più facile |

- **Indice di copertura:** per ogni concetto, peso nell'insegnamento (tempo, slide) contro peso nell'esame (punti); la distanza tra le due distribuzioni. Si calcola già nel prototipo.
- **Diversità degli esercizi:** numero di schemi distinti negli esercizi d'esame passati e quota di punti sui più frequenti.
- **Tasso di azione:** quota di segnalazioni dell'agente che portano a un cambiamento concreto.
- **Accordo con il docente:** quota di mappature e interpretazioni che il docente valida come corrette.

## Il ciclo proposto

&#91;embedded content: ciclo docente–agente–studenti · 5 fasi\]

Il cuore è la fase 4: l'agente non si ferma alle percentuali ma dice cosa significano, per esempio "hanno imparato la procedura, non quando applicarla". Al docente propone cosa riprendere o come riformulare un esercizio; allo studente indica dove sta usando lo schema.

## Approcci proposti

La raccomandazione è l'approccio 1, "sonda di transfer": è l'unico in cui il transfer gap è il motore stesso del prodotto. Niccolò non ha ancora scelto.

| Approccio | Come funziona | Pro | Contro |
| --- | --- | --- | --- |
| 1. Sonda di transfer (raccomandato) | Mappa dei concetti dal materiale; brevi verifiche con esercizio tipico + variante generata dall'AI, al posto del Kahoot; transfer gap spiegato a docente e studente | Il ciclo è continuo; si dimostra bene nel Level 2 (quiz generato e corretto, errori tracciati, segnalazione al docente) | Serve che gli studenti partecipino con costanza |
| 2. Tutor per lo studente + dati aggregati | Tutor socratico con varianti; dati anonimi al docente | Adozione facile, lo studente ci guadagna subito | Insegnato ↔ testato diventa secondario; simile a molti altri progetti |
| 3. Revisione dell'esame con il docente | Prima dell'appello l'agente confronta la bozza con programma e lezioni; dopo, raccoglie il parere degli studenti | Semplice, impatto diretto sull'esame | Ciclo lento (a ogni appello); transfer gap solo a posteriori |

L'approccio 3 può diventare una funzione dell'1 ("controlla la bozza d'esame").

## Questioni aperte e prossimi passi

La prossima decisione è la scelta dell'approccio. Il brainstorming segue il percorso "architetturale": niente costruzione prima di un design scritto e approvato.

- [ ] Scegliere l'approccio (1, 2, 3 o una combinazione)
- [ ] Capire se si riesce a recuperare un corso vero del Poli con slide e temi d'esame vecchi; in alternativa si usano esempi generici
- [ ] Presentare il design per sezioni: architettura, componenti, flusso dei dati, gestione degli errori, test
- [ ] Scegliere la strada per il Level 2: senza codice o con codice
- [ ] Elencare i rischi per il pitch: proprietà dei dati degli studenti, tool non disponibile prima dell'esame, accesso disuguale, errori dell'AI nelle mappature
- [ ] Scrivere e approvare il design, poi il piano di implementazione
- [ ] Preparare il pitch di 60 secondi: problema, soluzione, impatto

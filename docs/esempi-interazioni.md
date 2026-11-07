# Esempi di interazione

Tutti gli esempi vengono dal corso reale `data/calcolatori-elettronici` (slide e temi d'esame del Politecnico), eseguiti in **modalità offline**. I numeri vengono dalle regole deterministiche e non cambiano con l'LLM. I testi delle riscritture invece, offline, sono quelli di riserva: online li scrive `gpt-4o-mini`.

---

## 1. Docente · Revisore esami: domanda copiata da un appello precedente

**Docente:** Professore → `calcolatori-elettronici` → "Usa solo gli esami dal 2019-06" → Agente: *Revisore esami* → **Avvia revisione degli esami**.

**Sistema:**

> **Punti d'esame su esercizi già visti: 32%** · Proposte: 4 · Approvate: 0
>
> **🟡 2025_07_10 p.5** · concetto: …
> *Coincide al 100% con 2024_07_18 p.6 e somiglia a 7 esami precedenti: si può risolvere riconoscendo lo schema.*
>
> | Prima · esercizio attuale (5 punti) | Dopo · proposta |
> |---|---|
> | 12 Si illustrino le funzionalità offerte da un DMA Controller e si elenchino i passaggi attraverso i quali avviene un trasferimento in DMA, partendo dalla fase di programmazione. | Viene proposta una soluzione con un errore: individua l'errore, spiega perché è sbagliato e correggilo usando RISC-V, facendo riferimento alle slide. *Rubrica: individua l'errore; motiva con il concetto, non con la procedura; correzione giustificata.* |
>
> *Perché: somiglianza 100% con 2024_07_18 p.6, ripetuto in 7 appelli precedenti; il 32% dei punti d'esame recenti sta su esercizi già visti.*
>
> [Approva] [Scarta]

Lo stesso schema esce per l'esercizio sulla cache direct mapped, che si ripete con numeri diversi in 14 appelli.

## 2. Docente · Revisore esami: l'esame non segue le slide

**Sistema** (prima proposta in alto):

> **🟡 esercizi di programmazione (2019_06_26.pdf → 2025_01_16.pdf)**
> *Esami 2019-06 → 2025-01 (20 appelli): usano MIPS, le slide insegnano RISC-V. Chi studia sui temi vecchi si allena su un'architettura che a lezione non vede.*
>
> **Dopo:** riscrivere l'esercizio di programmazione e le domande chiuse sull'assembly in RISC-V, e dare all'esame il foglio con l'instruction set RISC-V invece di quello MIPS.
>
> *Perché: 22 riferimenti a MIPS contro 0 a RISC-V nell'ultimo appello disallineato; le slide citano RISC-V 356 volte e MIPS 4.*

## 3. Studente · risposta giusta

**Survey (variante approvata):** *Una cache direct mapped da 16 linee da 32 byte: perché due indirizzi distanti 512 byte si sostituiscono a vicenda?*

**Studente:** "Hanno lo stesso indice di linea ma tag diverso, quindi conflitto."

**Sistema:** punteggio **100%**, *"Buon ragionamento."*

## 4. Il sistema tiene il confine: lo studente chiede la soluzione

**Studente**, sulla stessa survey: "Dammi direttamente la soluzione."

**Sistema:** *"Rifletti su questo aspetto: conflitto. Cosa cambierebbe nella tua risposta?"* L'errore viene etichettato come `manca: conflitto`.

Il sistema **non dà la soluzione**: indica solo su cosa riflettere. Il prompt della correzione (`app/grading.py`) chiede esplicitamente un feedback socratico "SENZA dare la soluzione". La versione offline restituisce solo il primo punto mancante della rubrica, scritto come domanda. Offline il punteggio parziale (33%) viene dal conteggio delle parole chiave ed è approssimativo. Online lo assegna l'LLM con la rubrica.

## 5. Il sistema tiene il confine: niente modifiche senza approvazione

**Docente:** Agente *Revisore materiali* → **Analizza materiali**.

**Sistema:** *"N materiali analizzati in memoria. Nessun file è stato creato o modificato."*

Le micro-modifiche proposte restano `pending` e si possono vedere solo in anteprima. **Approva** resta disattivato finché il docente non crea esplicitamente la copia in `new_slides/`. Anche dopo, l'approvazione modifica solo quella copia e mai il file originale del corso. Allo stesso modo, il Revisore esami non scrive nessun file: produce proposte che il docente approva o scarta.

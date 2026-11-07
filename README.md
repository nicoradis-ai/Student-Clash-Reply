# Sonda di transfer – AI on Campus

Demo per il Reply Student Tech Clash 2026. Contesto in `docs/handover.md`, design in `.scratch/ai-on-campus/spec.md`.

## Avvio

```bash
pip install -r requirements.txt
cp .env.example .env              # poi metti la chiave in .env (git lo ignora); senza chiave gira offline
# facoltativi: OPENAI_MODEL (default gpt-4o-mini), OPENAI_EMBED_MODEL, OFFLINE=1
streamlit run streamlit_app.py
```

Test: `OFFLINE=1 python -m pytest -q`

## Corsi

Ogni corso è una cartella `data/<corso>/` con `slides/` e `exams/` (`.md` o `.pdf`). Nei `.md` le slide sono separate da `---`, gli esercizi d'esame da titoli `## Esercizio N (X punti)`. Una riga `Concetto: Nome` è facoltativa: aiuta la modalità offline, online i concetti li estrae l'LLM. `data/esempio-poo/` è un corso fittizio di Programmazione ad oggetti.

Nei PDF ogni pagina è un blocco (citato come `<file> p.N`). Per i temi d'esame PDF i punti si stimano dalla sezione: risposta chiusa 1, risposta aperta 5, "sino a N punti" N.

`data/<corso>/config.json` (facoltativo) può contenere `exams_from` (`"YYYY-MM"`): nella barra laterale compare un filtro che esclude gli esami più vecchi, riconosciuti dalla data nel nome del file (`YYYY_MM_...`). Per Calcolatori Elettronici è `2019-06`, perché prima gli esami erano su x86 e le slide sono su RISC-V. I file non vengono cancellati.

Se OpenAI non risponde, l'app usa le risposte di riserva e lo dice in rosso nella barra laterale. Lo stato (errori, embedding passati a offline) vale per tutto il processo: **se cambi chiave o torna la rete, riavvia streamlit**.

## Script della demo ("The Lazy Prof", ADR 0007)

1. **Professore → scegli il corso → Carica corso.** Il filtro "Usa solo gli esami dal …" esclude gli appelli su un'architettura diversa da quella delle slide.
2. **Creatore di survey**: scegli una lezione, "Crea survey per questa lezione", poi Approva/Scarta le varianti (ADR 0003). Senza varianti approvate non si misura nulla.
3. **Diagnosi transfer gap**: "Simula una classe di 20 studenti" e mostra il transfer gap per concetto (tipiche contro varianti) e la distanza insegnato ↔ testato.
4. **Revisore esami**: esercizi d'esame ricalcabili dagli appelli vecchi o su un'architettura diversa dalle slide, con il confronto prima/dopo. Le motivazioni citano il transfer gap della Diagnosi.
5. **Revisore materiali**: "Ammoderna" rinnova le slide in `data/<corso>/new_slides/` (ignorata da git), poi micro-modifiche da approvare.
6. **Studente**: risponde alla coppia tipica + variante di una survey approvata e riceve un feedback che guida senza dare la soluzione.

Il corso `data/esempio-poo/` (fittizio, in markdown) è il piano B: funziona anche offline e senza PDF.

Formati dei nomi d'esame riconosciuti per la data: `YYYY_MM_DD`, `YYYYMMDD`, `DDMMYY` (es. `040723.pdf` = luglio 2023).

Nota: `app/orchestrator.py` e `app/agents/` (ADR 0006) restano nel codice ma la UI attuale non li usa; vedi `.scratch/ai-on-campus/still-to-do.md`.

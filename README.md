# Sonda di transfer – AI on Campus

Demo per il Reply Student Tech Clash 2026. Contesto in `docs/handover.md`, design in `.scratch/ai-on-campus/spec.md`.

## Avvio

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=...        # senza chiave gira in modalità offline
# facoltativi: OPENAI_MODEL (default gpt-4o-mini), OPENAI_EMBED_MODEL, OFFLINE=1
streamlit run streamlit_app.py
```

Test: `OFFLINE=1 python -m pytest -q`

## Corsi

Ogni corso è una cartella `data/<corso>/` con `slides/` e `exams/` (`.md` o `.pdf`). Nei `.md` le slide sono separate da `---`, gli esercizi d'esame da titoli `## Esercizio N (X punti)`. Una riga `Concetto: Nome` è facoltativa: aiuta la modalità offline, online i concetti li estrae l'LLM. `data/esempio-poo/` è un corso fittizio di Programmazione ad oggetti.

## Script della demo

1. **Docente · Mappa dei concetti**: conferma i concetti estratti (accordo con il docente).
2. **Varianti da approvare**: "Genera coppie di verifica", poi Approva/Scarta ogni variante (con le fonti citate).
3. **Classe e metriche**: "Simula una verifica", poi mostra il transfer gap (tipici contro varianti) e l'indice di copertura (slide contro punti d'esame).
4. **Disallineamenti**: "Analizza": per ogni concetto critico, cosa significa e tre suggerimenti (slide, esame, studenti).
5. **Studente**: rispondi a una variante, ricevi un feedback che guida senza dare la soluzione e vedi cosa ripassare.

Le risposte dell'LLM sono salvate in `.cache/`: fai un giro completo online prima della presentazione e la demo regge anche senza rete.

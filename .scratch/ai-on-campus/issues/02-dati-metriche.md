# 02 – Classe simulata e metriche

Status: ready-for-human
Owner: B

Implementa `app/simulate.py` e `app/metrics.py`.

## Criteri di accettazione
- `simulate_class` genera ~20 studenti con profili diversi (es. "memorizza gli schemi": bravo sui tipici, debole sulle varianti; "solido"; "in difficoltà"). Può usare l'LLM per scrivere le risposte o template con errori realistici; serve un seed fisso per la demo.
- `concept_metrics` calcola per concetto: punteggio tipico, punteggio varianti, transfer gap, quota di slide, quota di punti d'esame. Anche per singolo studente.
- Test unitari su `metrics.py` con dati finti.
- Se il materiale di Luca non arriva entro le 13:30, preparare un mini corso fittizio in `data/esempio/` (5–6 slide, 2 temi d'esame).

## Comments

- 2026-11-07 (Claude): c'è già una prima versione funzionante (PR "Scheletro funzionante"), anche offline. Il ticket ora è: migliorare la propria parte, prompt e qualità, senza cambiare le firme delle funzioni.

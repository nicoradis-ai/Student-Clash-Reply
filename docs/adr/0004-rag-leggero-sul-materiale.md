# 0004 – RAG leggero, solo sul materiale del corso

Stato: accettato (2026-11-07)

Il materiale (slide, temi d'esame) viene spezzato in blocchi, indicizzato con gli embedding OpenAI e tenuto in memoria (numpy, similarità coseno). Le richieste di mappa, varianti, correzione e suggerimenti recuperano i blocchi pertinenti e li citano ("slide 12"). Riduce gli errori dell'AI e velocizza l'approvazione del docente.

Niente database vettoriale per la demo. Le risposte degli studenti **non** passano dal RAG: sono dati strutturati aggregati per concetto; all'LLM si passa solo un campione degli errori più frequenti.

import numpy as np

from app import rag
from app.ingest import split_questions
from app.models import Chunk

PAGE1 = """Nome, cognome, matricola ..........
Calcolatori Elettronici (12AGA) – esame del 2.7.2024
Domande a risposta chiusa (è necessario rispondere correttamente ad almeno 6 domande).
1 Si consideri una RAM con 1024 parole. Quante linee di parola?
2 Quale vantaggio offre un sommatore carry lookahead?
È più veloce A
3 Si consideri una memoria di microcodice da 1000 parole. Quanti bit compongono il PC?
10 A
1000 B
52 C
6 D
"""
PAGE2 = """che cosa succede dopo?
4 Quale registro contiene l'indirizzo di ritorno?
Risposte corrette
1 Cinque
2 A
"""


def test_una_domanda_per_chunk_senza_intestazione_ne_opzioni():
    qs = split_questions([PAGE1, PAGE2])
    assert [(p, n) for p, n, _ in qs] == [(0, 1), (0, 2), (0, 3), (1, 4)]
    assert "matricola" not in qs[0][2]
    assert "10 A" in qs[2][2] and "che cosa succede dopo?" in qs[2][2]   # opzioni e continuazione restano nella 3
    assert "Cinque" not in qs[3][2]                                        # griglia delle risposte tagliata


def test_pagina_senza_domande_resta_un_blocco():
    qs = split_questions(["Esercizio di programmazione\nSi scriva una procedura in assembler RISC-V."])
    assert [(p, n) for p, n, _ in qs] == [(0, None)]


def test_soglia_online_e_materiale_insufficiente(monkeypatch):
    chunks = [Chunk("slides/a.pdf#0", "slide", "a p.1", "cache"), Chunk("slides/a.pdf#1", "slide", "a p.2", "bus")]
    vecs = {"cache": [1.0, 0.0], "bus": [0.0, 1.0], "java": [0.1, 0.1], "memoria cache": [0.9, 0.1]}
    monkeypatch.setattr(rag.llm, "embeds_online", lambda: True)
    monkeypatch.setattr(rag.llm, "embed", lambda texts: np.array([vecs[t] for t in texts]))
    idx = rag.Index(chunks)
    assert [c.ref for c in idx.retrieve("memoria cache", k=2)] == ["a p.1"]   # "bus" è sotto soglia
    assert idx.retrieve("java", k=2, min_sim=0.9) == []
    assert len(idx.retrieve("java", k=2, min_sim=0)) == 2
    assert rag.cite([]) == rag.INSUFFICIENT

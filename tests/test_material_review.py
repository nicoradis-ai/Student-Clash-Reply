"""Agente revisione materiale: priorità dai dati e citazioni vincolate alle pagine viste."""
from app import material_review as mr
from app.models import Chunk, Concept, ConceptMetrics


def _course():
    chunks = [Chunk("slides/bus.pdf#0", "slide", "bus p.1", "Bus sincrono e asincrono"),
              Chunk("slides/bus.pdf#1", "slide", "bus p.2", "Arbitraggio del bus"),
              Chunk("exams/2024.pdf#3", "exam", "2024 p.4", "Calcolare la banda del bus", points=5)]
    con = Concept("bus", "Bus", "Bus di sistema", chunk_ids=[c.id for c in chunks])
    m = ConceptMetrics("bus", 0.8, 0.4, 0.4, teaching_weight=0.05, exam_weight=0.3)
    return chunks, con, m


def test_priorita_sotto_insegnato_prima():
    under = ConceptMetrics("a", 0, 0, 0.0, teaching_weight=0.05, exam_weight=0.25)
    over = ConceptMetrics("b", 0, 0, 0.0, teaching_weight=0.25, exam_weight=0.05)
    assert mr.priority(under) > mr.priority(over)


def test_citazioni_inventate_scartate(monkeypatch):
    chunks, con, m = _course()
    fake = {"diagnosis": "x", "proposals": [
        {"action": "aggiungere", "slide_ref": "bus p.99", "change": "inventata", "why": ""},
        {"action": "esempio", "slide_ref": "[bus p.2]", "change": "esempio di arbitraggio", "why": "vedi [2024 p.4]",
         "exam_side": "e", "student_side": "s"}]}
    monkeypatch.setattr(mr, "chat_json", lambda s, u, fb: fake)
    r = mr.review_concept(con, m, chunks)
    assert [p.slide_ref for p in r.proposals] == ["bus p.2"]
    assert r.proposals[0].exam_refs == ["2024 p.4"]


def test_offline_tre_lati_e_pagine_reali():
    chunks, con, m = _course()
    r = mr.review_concept(con, m, chunks)  # senza chiave: fallback deterministico
    refs = {c.ref for c in chunks if c.source == "slide"}
    assert r.proposals and all(p.slide_ref in refs and p.exam_side and p.student_side for p in r.proposals)

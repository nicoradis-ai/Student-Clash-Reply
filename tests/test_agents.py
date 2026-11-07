"""Contratto dei tre agenti (ADR 0006): girano in parallelo e lavorano solo sui concetti con gap alto."""
from app.agents import AGENTS
from app.models import Chunk, Concept, ConceptMetrics
from app.orchestrator import run_agents
from app.agents.base import CourseContext
from app.rag import Index


def _ctx():
    chunks = [Chunk("s#0", "slide", "S1", "cache"), Chunk("e#0", "exercise", "E1", "esercizio cache"),
              Chunk("x#0", "exam", "X1", "esame cache", points=10), Chunk("s#1", "slide", "S2", "pipeline")]
    concepts = [Concept("cache", "Cache", "memorie cache", ["s#0", "e#0", "x#0"]),
                Concept("pipe", "Pipeline", "pipeline", ["s#1"]),
                Concept("bus", "Bus", "bus", [])]
    metrics = [ConceptMetrics("cache", 0.85, 0.40, 0.45, 0.3, 0.6),
               ConceptMetrics("pipe", 0.80, 0.78, 0.02, 0.3, 0.3),
               ConceptMetrics("bus", 0.70, 0.65, 0.05, 0.4, 0.1)]
    return CourseContext(chunks=chunks, index=Index(chunks), concepts=concepts, metrics=metrics)


def test_focus_prefers_high_gap():
    assert _ctx().focus(k=1)[0][0].id == "cache"


def test_three_agents_run_in_parallel_offline(monkeypatch):
    monkeypatch.setenv("OFFLINE", "1")
    results, errors = run_agents(_ctx())
    assert not errors
    assert set(results) == {"materiale", "esercitazioni", "esami"} == {a.name for a in AGENTS}
    for name, props in results.items():
        assert props and all(p.agent == name and p.change and p.rationale for p in props)
        assert props[0].concept_id == "cache"

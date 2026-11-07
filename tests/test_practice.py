from app.models import Chunk, Concept, ConceptMetrics
from app.practice import align_practice, decide, is_practice
from app.rag import Index


def _course():
    chunks = [
        Chunk("slides/03 - cache.pdf#0", "slide", "cache p.1", "cache associativa"),
        Chunk("slides/esercizi UC.pdf#0", "slide", "esercizi p.1", "esercizio pipeline"),
        Chunk("slides/esercizi UC.pdf#1", "slide", "esercizi p.2", "esercizio pipeline hazard"),
        Chunk("exams/2024.pdf#0", "exam", "2024 p.1", "domanda cache", points=12),
        Chunk("exams/2024.pdf#1", "exam", "2024 p.2", "domanda pipeline", points=4),
    ]
    cache = Concept("cache", "Cache", "memorie cache", chunk_ids=["slides/03 - cache.pdf#0", "exams/2024.pdf#0"])
    pipe = Concept("pipeline", "Pipeline", "pipeline RISC-V",
                   chunk_ids=["slides/esercizi UC.pdf#0", "slides/esercizi UC.pdf#1", "exams/2024.pdf#1"])
    return chunks, [cache, pipe]


def test_is_practice_by_filename():
    chunks, _ = _course()
    assert [is_practice(c) for c in chunks] == [False, True, True, False, False]


def test_decide_rules():
    assert decide(0.0, 0.3, None)[0] == "aggiungere"
    assert decide(0.3, 0.3, 0.4)[0] == "trasformare"
    assert decide(0.6, 0.1, 0.0)[0] == "ridurre"
    assert decide(0.3, 0.3, 0.05)[0] == "ok"


def test_align_practice_offline_ranks_uncovered_exam_concept_first(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    chunks, concepts = _course()
    out = align_practice(concepts, chunks, Index(chunks))
    assert out[0].concept_id == "cache" and out[0].action == "aggiungere"
    assert out[0].new_exercises and all(e.status == "pending" for e in out[0].new_exercises)
    assert out[0].student_practice


def test_align_practice_uses_transfer_gap(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    chunks, concepts = _course()
    ms = [ConceptMetrics("cache", 0.8, 0.8, 0.0, 0, 0), ConceptMetrics("pipeline", 0.9, 0.3, 0.6, 0, 0)]
    out = {p.concept_id: p for p in align_practice(concepts, chunks, Index(chunks), metrics=ms)}
    assert out["pipeline"].action == "trasformare"
    assert out["pipeline"].transfer_gap == 0.6

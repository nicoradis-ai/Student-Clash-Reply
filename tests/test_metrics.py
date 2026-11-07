from app.metrics import concept_metrics, coverage_distance
from app.models import Answer, Chunk, Concept, Exercise


def _setup():
    chunks = [Chunk("s1", "slide", "Slide 1", "a"), Chunk("s2", "slide", "Slide 2", "b"),
              Chunk("e1", "exam", "Es 1", "c", points=10)]
    concepts = [Concept("a", "A", "", ["s1", "e1"]), Concept("b", "B", "", ["s2"])]
    exs = [Exercise("a-typ", "a", "typical", "", "", status="approved"),
           Exercise("a-var", "a", "variant", "", "", status="approved")]
    ans = [Answer("x", "a-typ", "", 0.9), Answer("x", "a-var", "", 0.3),
           Answer("y", "a-typ", "", 0.7), Answer("y", "a-var", "", 0.5)]
    return concepts, chunks, exs, ans


def test_transfer_gap():
    m = {m.concept_id: m for m in concept_metrics(*_setup())}
    assert m["a"].typical_score == 0.8 and m["a"].variant_score == 0.4
    assert m["a"].transfer_gap == 0.4
    assert m["b"].transfer_gap == 0.0  # nessuna risposta


def test_transfer_gap_per_student():
    m = {m.concept_id: m for m in concept_metrics(*_setup(), student_id="x")}
    assert m["a"].transfer_gap == 0.6


def test_coverage():
    ms = concept_metrics(*_setup())
    m = {x.concept_id: x for x in ms}
    assert m["a"].teaching_weight == 0.5 and m["a"].exam_weight == 1.0
    assert coverage_distance(ms) == 0.5

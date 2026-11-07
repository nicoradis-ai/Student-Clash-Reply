"""Transfer gap e indice di copertura per concetto."""
from collections import Counter

from .models import Answer, Chunk, Concept, ConceptMetrics, Exercise


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def concept_metrics(concepts: list[Concept], chunks: list[Chunk], exercises: list[Exercise],
                    answers: list[Answer], student_id: str | None = None) -> list[ConceptMetrics]:
    by_chunk = {c.id: c for c in chunks}
    ex_by_id = {e.id: e for e in exercises}
    slides_tot = sum(1 for c in chunks if c.source == "slide") or 1
    points_tot = sum(c.points for c in chunks if c.source == "exam") or 1
    out = []
    for con in concepts:
        mine = [by_chunk[i] for i in con.chunk_ids if i in by_chunk]
        scores = {"typical": [], "variant": []}
        for a in answers:
            ex = ex_by_id.get(a.exercise_id)
            if ex is None or ex.concept_id != con.id or a.score is None:
                continue
            if student_id is not None and a.student_id != student_id:
                continue
            scores[ex.kind].append(a.score)
        t, v = _mean(scores["typical"]), _mean(scores["variant"])
        out.append(ConceptMetrics(
            concept_id=con.id, typical_score=round(t, 3), variant_score=round(v, 3),
            transfer_gap=round(t - v, 3) if scores["typical"] and scores["variant"] else 0.0,
            teaching_weight=round(sum(1 for c in mine if c.source == "slide") / slides_tot, 3),
            exam_weight=round(sum(c.points for c in mine if c.source == "exam") / points_tot, 3),
        ))
    return out


def coverage_distance(metrics: list[ConceptMetrics]) -> float:
    """Distanza (variazione totale, 0..1) tra peso nell'insegnamento e peso nell'esame."""
    return round(0.5 * sum(abs(m.teaching_weight - m.exam_weight) for m in metrics), 3)


def top_errors(answers: list[Answer], exercises: list[Exercise], concept_id: str, k: int = 3):
    ids = {e.id for e in exercises if e.concept_id == concept_id}
    return Counter(a.error_tag for a in answers if a.exercise_id in ids and a.error_tag).most_common(k)

"""Interfaccia comune dei tre agenti (ADR 0006).

Ogni agente riceve lo stesso `CourseContext` (materiale, indice RAG, concetti e metriche della sonda
di transfer) e restituisce una lista di `Proposal`. Gli agenti NON scelgono gli argomenti a caso:
lavorano sui concetti di `ctx.focus()`, cioè quelli con transfer gap e disallineamento più alti.
Un agente non chiama Streamlit e non modifica il contesto: così l'orchestratore li fa girare in parallelo.
"""
from dataclasses import dataclass, field
from typing import Protocol

from ..models import AgentName, Answer, Chunk, Concept, ConceptMetrics, Exercise, Proposal
from ..rag import Index


@dataclass
class CourseContext:
    chunks: list[Chunk]
    index: Index
    concepts: list[Concept]
    metrics: list[ConceptMetrics]        # una per concetto, da metrics.concept_metrics
    exercises: list[Exercise] = field(default_factory=list)   # coppie tipico/variante della sonda
    answers: list[Answer] = field(default_factory=list)       # risposte (simulate + reali)
    course_dir: str = ""                 # cartella del corso: per rileggere ad es. tutti gli esami storici
    exams_from: str | None = None        # filtro esami scelto nella sidebar ("YYYY-MM")

    def concept(self, concept_id: str) -> Concept:
        return next(c for c in self.concepts if c.id == concept_id)

    def metric(self, concept_id: str) -> ConceptMetrics | None:
        return next((m for m in self.metrics if m.concept_id == concept_id), None)

    def chunks_of(self, concept_id: str, source: str | None = None) -> list[Chunk]:
        """Blocchi assegnati al concetto (slide, esercitazioni o esami)."""
        ids = set(self.concept(concept_id).chunk_ids)
        return [c for c in self.chunks if c.id in ids and (source is None or c.source == source)]

    def focus(self, k: int = 3, min_gap: float = 0.0) -> list[tuple[Concept, ConceptMetrics]]:
        """I k concetti su cui vale la pena intervenire: gap alto + distanza insegnato/testato."""
        def score(m: ConceptMetrics) -> float:
            return m.transfer_gap + abs(m.teaching_weight - m.exam_weight)
        ranked = sorted((m for m in self.metrics if m.transfer_gap >= min_gap), key=score, reverse=True)
        return [(self.concept(m.concept_id), m) for m in ranked[:k]]


def evidence(m: ConceptMetrics) -> str:
    """Frase standard con i numeri della sonda, da mettere in `Proposal.rationale`."""
    return (f"Transfer gap {m.transfer_gap:+.0%} (tipici {m.typical_score:.0%}, varianti {m.variant_score:.0%}); "
            f"peso nelle slide {m.teaching_weight:.0%} contro peso nei punti d'esame {m.exam_weight:.0%}.")


class Agent(Protocol):
    name: AgentName      # "materiale" | "esercitazioni" | "esami"
    title: str           # etichetta per la UI
    goal: str            # una frase: che problema risolve, mostrata in UI

    def run(self, ctx: CourseContext) -> list[Proposal]: ...

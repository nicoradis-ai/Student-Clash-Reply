"""Contratto dati condiviso tra i quattro ticket. Cambialo solo d'accordo con il team."""
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Chunk:
    """Un pezzo di materiale del corso, indicizzato per il RAG."""
    id: str                      # es. "slides/03.md#2"
    source: Literal["slide", "exam"]
    ref: str                     # citazione leggibile, es. "Slide 12" o "Esame 2024-06, es. 2"
    text: str
    points: float = 0.0          # solo per i temi d'esame: punti dell'esercizio


@dataclass
class Concept:
    id: str                      # slug, es. "polimorfismo"
    name: str
    description: str
    chunk_ids: list[str] = field(default_factory=list)
    validated: bool = False      # confermato dal docente


@dataclass
class Exercise:
    id: str
    concept_id: str
    kind: Literal["typical", "variant"]
    prompt: str
    rubric: str                  # criteri di correzione per l'LLM
    sources: list[str] = field(default_factory=list)   # chunk ids citati
    status: Literal["pending", "approved", "rejected"] = "pending"  # varianti: ADR 0003


@dataclass
class Answer:
    student_id: str              # "sim-07" per gli studenti simulati
    exercise_id: str
    text: str
    score: float | None = None   # 0..1, assegnato dalla correzione
    feedback: str = ""           # guida socratica, non la soluzione
    error_tag: str = ""          # breve etichetta dell'errore, es. "confonde overload e override"


@dataclass
class ConceptMetrics:
    concept_id: str
    typical_score: float
    variant_score: float
    transfer_gap: float          # typical_score - variant_score
    teaching_weight: float       # quota di slide sul concetto
    exam_weight: float           # quota di punti d'esame sul concetto


@dataclass
class Misalignment:
    """Una segnalazione: sempre tre suggerimenti (ADR 0002)."""
    concept_id: str
    evidence: str
    meaning: str                 # es. "hanno imparato la procedura, non quando applicarla"
    suggestion_teaching: str     # slide / lezioni
    suggestion_exam: str         # esercizio d'esame
    suggestion_student: str      # cosa ripassare
    sources: list[str] = field(default_factory=list)

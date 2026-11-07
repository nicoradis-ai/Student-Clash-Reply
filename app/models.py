"""Contratto dati condiviso tra i quattro ticket. Cambialo solo d'accordo con il team."""
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Chunk:
    """Un pezzo di materiale del corso, indicizzato per il RAG."""
    id: str                      # es. "slides/03.md#2"
    source: Literal["slide", "exercise", "exam"]   # exercise = esercitazioni
    ref: str                     # citazione leggibile, es. "Slide 12" o "Esame 2024-06, es. 2"
    text: str
    points: float = 0.0          # solo per i temi d'esame: punti dell'esercizio


@dataclass
class Lesson:
    """Una lezione corrisponde a un file di slide/PDF e contiene i suoi sottoargomenti."""
    id: str
    title: str
    source_file: str
    slide_ids: list[str] = field(default_factory=list)
    subtopics: list[str] = field(default_factory=list)


@dataclass
class SlideCorrection:
    """Una proposta puntuale di miglioramento riferita a una singola slide."""
    slide_id: str
    slide_ref: str
    error: str
    correction: str


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


AgentName = Literal["materiale", "esercitazioni", "esami"]


@dataclass
class Proposal:
    """Una proposta di modifica prodotta da uno dei tre agenti (ADR 0006).

    Ogni proposta parte da un concetto con transfer gap alto: dice cosa cambiare, dove, e perché
    i dati lo giustificano. Il docente la approva o la scarta, come le varianti (ADR 0003)."""
    agent: AgentName
    concept_id: str
    target_ref: str              # dove intervenire, es. "04 - RISC V p.12" o "2024_07_18 p.2"
    problem: str                 # cosa non va, legato al gap: "le slide mostrano solo la procedura"
    change: str                  # la modifica concreta proposta (testo da aggiungere/sostituire)
    rationale: str               # il dato che la giustifica, es. "gap +38%: tipici 82%, varianti 44%"
    sources: list[str] = field(default_factory=list)   # chunk ids citati
    priority: float = 0.0        # più alto = più urgente; di default il transfer gap del concetto
    status: Literal["pending", "approved", "rejected"] = "pending"

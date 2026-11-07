"""I tre agenti che lavorano in parallelo sullo stesso CourseContext (ADR 0006)."""
from .base import Agent, CourseContext, evidence
from .esami import EsamiAgent
from .esercitazioni import EsercitazioniAgent
from .materiale import MaterialeAgent

AGENTS: list[Agent] = [MaterialeAgent(), EsercitazioniAgent(), EsamiAgent()]

__all__ = ["AGENTS", "Agent", "CourseContext", "evidence"]

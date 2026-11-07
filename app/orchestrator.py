"""Fa girare i tre agenti in parallelo sullo stesso contesto (ADR 0006)."""
from concurrent.futures import ThreadPoolExecutor

from .agents import AGENTS, Agent, CourseContext
from .metrics import concept_metrics
from .models import Answer, Chunk, Concept, Exercise, Proposal
from .rag import Index


def build_context(chunks: list[Chunk], index: Index, concepts: list[Concept],
                  exercises: list[Exercise], answers: list[Answer],
                  course_dir: str = "", exams_from: str | None = None) -> CourseContext:
    return CourseContext(chunks=chunks, index=index, concepts=concepts,
                         metrics=concept_metrics(concepts, chunks, exercises, answers),
                         exercises=exercises, answers=answers,
                         course_dir=course_dir, exams_from=exams_from)


def run_agents(ctx: CourseContext, agents: list[Agent] | None = None) -> tuple[dict[str, list[Proposal]], dict[str, str]]:
    """Ritorna (proposte per agente, errori per agente). Un agente che fallisce non blocca gli altri."""
    agents = agents or AGENTS
    results: dict[str, list[Proposal]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(agents)) as pool:
        futures = {a.name: pool.submit(a.run, ctx) for a in agents}
        for name, fut in futures.items():
            try:
                results[name] = sorted(fut.result(), key=lambda p: p.priority, reverse=True)
            except Exception as e:  # noqa: BLE001 – in demo mostriamo l'errore invece di crashare
                results[name] = []
                errors[name] = f"{type(e).__name__}: {e}"
    return results, errors

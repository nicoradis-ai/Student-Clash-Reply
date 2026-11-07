"""Disallineamenti con tre suggerimenti, mai un solo destinatario (ADR 0002)."""
from .llm import chat_json
from .metrics import top_errors
from .models import Answer, Concept, ConceptMetrics, Exercise, Misalignment
from .rag import Index, cite

SYSTEM = (
    "Sei un agente che aiuta docente e studenti a riallineare insegnamento ed esame. Ti do le metriche di un "
    "concetto (transfer gap = punteggio sugli esercizi tipici meno punteggio sulle varianti; peso nelle slide "
    "contro peso nei punti d'esame), gli errori più frequenti e il materiale. Spiega cosa significano i dati in una "
    "frase (es. 'hanno imparato la procedura, non quando applicarla'). Poi dai TRE suggerimenti concreti, uno per "
    "ciascun lato, senza attribuire la colpa a uno solo: slide/lezioni, esercizio d'esame, studio dello studente. "
    "Cita le slide pertinenti tra parentesi quadre. Rispondi in JSON: "
    '{"evidence": "...", "meaning": "...", "suggestion_teaching": "...", "suggestion_exam": "...", '
    '"suggestion_student": "..."}. In italiano.'
)


def _score(m: ConceptMetrics) -> float:
    return m.transfer_gap + abs(m.teaching_weight - m.exam_weight)


def _offline(con: Concept, m: ConceptMetrics, errs, slides) -> dict:
    ref = slides[0].ref if slides else "le slide del concetto"
    more_exam = m.exam_weight > m.teaching_weight
    return {
        "evidence": (f"Transfer gap {m.transfer_gap:+.0%} (tipici {m.typical_score:.0%}, varianti "
                     f"{m.variant_score:.0%}); peso slide {m.teaching_weight:.0%} vs punti d'esame "
                     f"{m.exam_weight:.0%}. Errori frequenti: " + (", ".join(e for e, _ in errs) or "nessuno")),
        "meaning": ("Molti hanno imparato la procedura d'esame su questo concetto, non quando applicarla."
                    if m.transfer_gap > 0.2 else "Il concetto è capito in modo abbastanza trasferibile."),
        "suggestion_teaching": (f"Aggiungere a {ref} un esempio in cui {con.name} non va usato"
                                + (", e dedicargli più tempo: pesa di più all'esame che a lezione." if more_exam else ".")),
        "suggestion_exam": f"Inserire nel prossimo appello almeno una domanda su {con.name} in forma non standard.",
        "suggestion_student": f"Ripassare {con.name} partendo dal perché, poi provare le varianti invece dei temi vecchi.",
    }


def misalignments(concepts: list[Concept], metrics: list[ConceptMetrics], answers: list[Answer],
                  exercises: list[Exercise], index: Index, top: int = 3) -> list[Misalignment]:
    by_id = {c.id: c for c in concepts}
    out = []
    for m in sorted(metrics, key=_score, reverse=True)[:top]:
        con = by_id[m.concept_id]
        errs = top_errors(answers, exercises, con.id)
        slides = index.retrieve(con.name, k=3, source="slide")
        user = (f"Concetto: {con.name}\nMetriche: {m}\nErrori frequenti: {errs}\n\nMateriale:\n{cite(slides)}")
        d = chat_json(SYSTEM, user, lambda: _offline(con, m, errs, slides))
        out.append(Misalignment(concept_id=con.id, evidence=d.get("evidence", ""), meaning=d.get("meaning", ""),
                                suggestion_teaching=d.get("suggestion_teaching", ""),
                                suggestion_exam=d.get("suggestion_exam", ""),
                                suggestion_student=d.get("suggestion_student", ""),
                                sources=[s.id for s in slides]))
    return out


def study_advice(student_metrics: list[ConceptMetrics], concepts: list[Concept], k: int = 3) -> list[str]:
    by_id = {c.id: c for c in concepts}
    worst = sorted((m for m in student_metrics if m.typical_score or m.variant_score),
                   key=lambda m: m.transfer_gap, reverse=True)[:k]
    return [f"{by_id[m.concept_id].name}: tipici {m.typical_score:.0%}, varianti {m.variant_score:.0%}. "
            f"Prova a spiegare quando si usa e quando no." for m in worst if m.transfer_gap > 0.1]

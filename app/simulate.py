"""Classe simulata con profili diversi (ADR 0005: solo dati sintetici)."""
import random

from .models import Answer, Exercise

# (media sugli esercizi tipici, media sulle varianti, quota della classe)
PROFILES = {
    "memorizza gli schemi": (0.85, 0.35, 0.45),
    "solido": (0.85, 0.75, 0.30),
    "in difficoltà": (0.45, 0.30, 0.25),
}
ERRORS_VARIANT = [
    "applica la procedura senza riconoscere quando serve",
    "ricalca lo schema dell'esercizio d'esame",
    "non sa motivare la scelta",
]
ERRORS_TYPICAL = ["errore di sintassi o di calcolo", "passaggio della procedura mancante"]


def simulate_class(exercises: list[Exercise], n: int = 20, seed: int = 42) -> list[Answer]:
    """Risponde solo agli esercizi approvati. Ogni concetto ha una difficoltà propria."""
    rng = random.Random(seed)
    concepts = sorted({e.concept_id for e in exercises})
    difficulty = {c: rng.uniform(-0.15, 0.15) for c in concepts}
    variant_extra = {c: rng.uniform(0.0, 0.25) for c in concepts}  # alcuni concetti hanno un gap più grande
    names, weights = list(PROFILES), [p[2] for p in PROFILES.values()]
    answers = []
    for i in range(n):
        sid = f"sim-{i + 1:02d}"
        typ_mu, var_mu, _ = PROFILES[rng.choices(names, weights)[0]]
        for ex in exercises:
            if ex.status != "approved":
                continue
            mu = typ_mu if ex.kind == "typical" else var_mu - variant_extra[ex.concept_id]
            score = min(1.0, max(0.0, rng.gauss(mu - difficulty[ex.concept_id], 0.12)))
            tag = ""
            if score < 0.6:
                tag = rng.choice(ERRORS_VARIANT if ex.kind == "variant" else ERRORS_TYPICAL)
            answers.append(Answer(student_id=sid, exercise_id=ex.id, text="(risposta simulata)",
                                  score=round(score, 2), error_tag=tag))
    return answers

"""Correzione con rubrica. Il feedback guida senza dare la soluzione."""
import re

from .llm import chat_json
from .models import Answer, Exercise

SYSTEM = (
    "Sei un tutor universitario. Correggi la risposta dello studente con la rubrica. "
    "Dai un punteggio da 0 a 1, un feedback socratico che indica dove riflettere SENZA dare la soluzione, "
    "e un'etichetta breve dell'errore principale (vuota se corretta). "
    'Rispondi in JSON: {"score": 0.0, "feedback": "...", "error_tag": "..."}. In italiano.'
)


def _offline(ex: Exercise, text: str) -> dict:
    keys = [k.strip().lower() for k in re.split(r"[,;]", ex.rubric.split(":", 1)[-1]) if k.strip()]
    hits = sum(1 for k in keys if any(w in text.lower() for w in k.split()))
    score = round(hits / len(keys), 2) if keys else 0.0
    missing = [k for k in keys if not any(w in text.lower() for w in k.split())]
    fb = ("Buon ragionamento." if not missing
          else f"Rifletti su questo aspetto: {missing[0]}. Cosa cambierebbe nella tua risposta?")
    return {"score": score, "feedback": fb, "error_tag": "" if not missing else f"manca: {missing[0]}"}


def grade(ex: Exercise, text: str, student_id: str) -> Answer:
    user = f"Esercizio:\n{ex.prompt}\n\nRubrica:\n{ex.rubric}\n\nRisposta dello studente:\n{text}"
    d = chat_json(SYSTEM, user, lambda: _offline(ex, text))
    score = min(1.0, max(0.0, float(d.get("score", 0))))
    return Answer(student_id=student_id, exercise_id=ex.id, text=text, score=score,
                  feedback=d.get("feedback", ""), error_tag=d.get("error_tag", ""))

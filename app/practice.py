"""Agente esercitazioni: allinea le esercitazioni a ciò che si insegna e a ciò che l'esame chiede.

Domanda a cui risponde, per ogni concetto: "le esercitazioni preparano davvero a questo concetto,
come lo chiede l'esame e in modo trasferibile?". Mette a confronto tre segnali:

- peso nelle esercitazioni (quota dei blocchi di esercitazione sul concetto),
- peso nell'esame (quota dei punti d'esame sul concetto),
- transfer gap (tipici meno varianti, se la classe ha già risposto).

Da lì decide un'azione (aggiungere, trasformare, ridurre, va bene), propone esercizi nuovi o modificati
(sempre `pending`: li approva il docente, ADR 0003) e dice agli studenti cosa esercitare.
Funziona anche offline e anche senza risposte della classe (in quel caso guarda solo la copertura)."""
from dataclasses import dataclass, field
from typing import Literal

from .llm import chat_json
from .models import Chunk, Concept, ConceptMetrics, Exercise
from .rag import Index, cite

# file di slide che sono esercitazioni, riconosciuti dal nome
PRACTICE_KEYS = ("esercizi", "esercitazion", "exercise", "lab")
GAP_HIGH = 0.2          # sopra questa soglia gli esercizi vanno resi trasferibili
COVERAGE_MARGIN = 0.05  # differenza di peso esame/esercitazioni da considerare

Action = Literal["aggiungere", "trasformare", "ridurre", "ok"]


@dataclass
class PracticeProposal:
    """Una proposta per le esercitazioni di un concetto."""
    concept_id: str
    action: Action
    practice_weight: float
    exam_weight: float
    transfer_gap: float | None       # None se la classe non ha ancora risposto
    priority: float
    evidence: str                    # i numeri, in una frase
    diagnosis: str                   # cosa significano
    change_existing: str             # come cambiare un'esercitazione che c'è già ("" se non ce ne sono)
    new_exercises: list[Exercise] = field(default_factory=list)  # pending, da approvare
    student_practice: str = ""       # cosa esercitare, per gli studenti
    sources: list[str] = field(default_factory=list)


def is_practice(chunk: Chunk) -> bool:
    """Blocchi della cartella exercises/; in mancanza, slide di esercizi riconosciute dal nome."""
    if chunk.source == "exercise":
        return True
    name = chunk.id.split("#", 1)[0].lower()
    return chunk.source == "slide" and any(k in name for k in PRACTICE_KEYS)


def practice_weights(concepts: list[Concept], chunks: list[Chunk]) -> dict[str, float]:
    practice = {c.id for c in chunks if is_practice(c)}
    tot = len(practice) or 1
    return {con.id: round(sum(1 for i in con.chunk_ids if i in practice) / tot, 3) for con in concepts}


def exam_weights(concepts: list[Concept], chunks: list[Chunk]) -> dict[str, float]:
    pts = {c.id: c.points for c in chunks if c.source == "exam"}
    tot = sum(pts.values()) or 1
    return {con.id: round(sum(pts.get(i, 0) for i in con.chunk_ids) / tot, 3) for con in concepts}


def decide(practice_w: float, exam_w: float, gap: float | None) -> tuple[Action, float]:
    """Regola trasparente, così il docente capisce perché un concetto è in cima."""
    under = exam_w - practice_w
    g = max(0.0, gap or 0.0)
    if exam_w > 0 and practice_w == 0:
        action: Action = "aggiungere"
    elif under > COVERAGE_MARGIN:
        action = "aggiungere"
    elif g > GAP_HIGH:
        action = "trasformare"
    elif practice_w - exam_w > 2 * COVERAGE_MARGIN and g <= GAP_HIGH:
        action = "ridurre"
    else:
        action = "ok"
    return action, round(max(0.0, under) + g, 3)


SYSTEM = (
    "Sei l'agente che allinea le ESERCITAZIONI di un corso universitario a ciò che si insegna e a ciò che "
    "l'esame chiede. Ti do un concetto, l'azione decisa (aggiungere / trasformare / ridurre / ok), i numeri "
    "(peso nelle esercitazioni, peso nei punti d'esame, transfer gap = tipici meno varianti), estratti delle "
    "esercitazioni esistenti e dei temi d'esame. Rispondi con:\n"
    "- diagnosis: una frase su cosa non funziona nelle esercitazioni per questo concetto;\n"
    "- change_existing: come modificare UNA esercitazione esistente citata (vuoto se non ce ne sono);\n"
    "- new_exercises: 1 o 2 esercizi NUOVI da esercitazione sullo stesso concetto, in forma di transfer "
    "(prevedere un risultato, trovare l'errore, scegliere tra due soluzioni e motivare, contesto diverso), "
    "che NON si risolvono ricalcando lo schema dei temi d'esame, ciascuno con rubrica;\n"
    "- student_practice: cosa dovrebbe esercitare lo studente, concreto, in una o due frasi.\n"
    "Cita le fonti tra parentesi quadre. JSON: "
    '{"diagnosis": "...", "change_existing": "...", '
    '"new_exercises": [{"prompt": "...", "rubric": "..."}], "student_practice": "...", "sources": ["..."]}. '
    "In italiano."
)


def _evidence(name: str, pw: float, ew: float, gap: float | None) -> str:
    g = "transfer gap non ancora misurato" if gap is None else f"transfer gap {gap:+.0%}"
    return f"{name}: {pw:.0%} delle esercitazioni, {ew:.0%} dei punti d'esame, {g}."


def _offline(con: Concept, action: Action, practice: list[Chunk], exams: list[Chunk]) -> dict:
    ex_ref = practice[0].ref if practice else ""
    diag = {
        "aggiungere": f"L'esame chiede {con.name} più di quanto lo facciano esercitare le esercitazioni.",
        "trasformare": (f"Le esercitazioni su {con.name} allenano lo schema d'esame: gli studenti lo ripetono "
                        "ma non lo applicano a casi nuovi."),
        "ridurre": f"Le esercitazioni dedicano a {con.name} più spazio di quanto pesi all'esame.",
        "ok": f"Le esercitazioni su {con.name} sono in linea con insegnamento ed esame.",
    }[action]
    change = (f"In [{ex_ref}] sostituire una ripetizione dello stesso schema con una domanda "
              f"'cosa cambia se…' su {con.name}." if practice and action != "ok" else "")
    news = [] if action in ("ok", "ridurre") else [
        {"prompt": (f"Ti viene dato un esercizio su {con.name} già svolto da un collega, con un errore. "
                    "Trova l'errore, spiega perché è sbagliato e correggilo."),
         "rubric": f"Parole chiave: {con.name}, individua l'errore, motivazione, correzione."},
        {"prompt": (f"Descrivi una situazione nuova (non vista a lezione) in cui {con.name} serve, e una in cui "
                    "non serve. Motiva la differenza."),
         "rubric": f"Parole chiave: {con.name}, quando si applica, controesempio, motivazione."},
    ]
    return {
        "diagnosis": diag,
        "change_existing": change,
        "new_exercises": news,
        "student_practice": (f"Su {con.name}: dopo un tema d'esame svolto, cambia un dato e prevedi cosa succede "
                             "prima di rifarlo; poi prova a spiegare perché il metodo funziona."),
        "sources": [c.ref for c in (practice[:1] + exams[:2])],
    }


def align_practice(concepts: list[Concept], chunks: list[Chunk], index: Index,
                   metrics: list[ConceptMetrics] | None = None, top: int = 5,
                   use_llm_for_ok: bool = False) -> list[PracticeProposal]:
    """Proposte per i `top` concetti con priorità più alta. `metrics` facoltativo (dalla classe simulata)."""
    pw, ew = practice_weights(concepts, chunks), exam_weights(concepts, chunks)
    gaps = {m.concept_id: m.transfer_gap for m in (metrics or []) if m.typical_score or m.variant_score}
    by_chunk = {c.id: c for c in chunks}
    ranked = []
    for con in concepts:
        action, prio = decide(pw[con.id], ew[con.id], gaps.get(con.id))
        ranked.append((prio, con, action))
    ranked.sort(key=lambda r: r[0], reverse=True)

    out = []
    for prio, con, action in ranked[:top]:
        mine = [by_chunk[i] for i in con.chunk_ids if i in by_chunk]
        practice = [c for c in mine if is_practice(c)][:3]
        exams = [c for c in mine if c.source == "exam"][:3] or index.retrieve(con.name, k=3, source="exam")
        gap = gaps.get(con.id)
        evidence = _evidence(con.name, pw[con.id], ew[con.id], gap)
        fallback = lambda con=con, action=action, practice=practice, exams=exams: _offline(con, action, practice, exams)
        if action == "ok" and not use_llm_for_ok:
            d = fallback()
        else:
            user = (f"Concetto: {con.name} – {con.description}\nAzione: {action}\nNumeri: {evidence}\n\n"
                    f"Esercitazioni esistenti:\n{cite(practice) or '(nessuna)'}\n\nTemi d'esame:\n{cite(exams)}")
            d = chat_json(SYSTEM, user, fallback)
        news = [Exercise(id=f"{con.id}-prat-{i + 1}", concept_id=con.id, kind="variant",
                         prompt=e.get("prompt", ""), rubric=e.get("rubric", ""),
                         sources=[c.id for c in practice + exams], status="pending")
                for i, e in enumerate(d.get("new_exercises") or []) if e.get("prompt")]
        out.append(PracticeProposal(
            concept_id=con.id, action=action, practice_weight=pw[con.id], exam_weight=ew[con.id],
            transfer_gap=gap, priority=prio, evidence=evidence, diagnosis=d.get("diagnosis", ""),
            change_existing=d.get("change_existing", ""), new_exercises=news,
            student_practice=d.get("student_practice", ""), sources=[c.id for c in practice + exams]))
    return out

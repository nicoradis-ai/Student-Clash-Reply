"""Agente revisione esami: trova dove l'esame si supera ricalcando i temi vecchi o chiede cose che le
slide non insegnano più, e propone esercizi d'esame rivisti (il docente li approva, ADR 0003).

Tre passi, i primi due deterministici (girano anche offline e sono spiegabili al docente):
1. `standardized_exercises`: per ogni esercizio recente, quanto testo coincide con un esame precedente
   (Jaccard sulle parole). Alto = si passa riconoscendo lo schema, non capendo il concetto.
2. `coverage_mismatches`: l'architettura (ISA) usata negli esami contro quella delle slide, per esempio
   esami su x86 o con il foglio MIPS mentre le slide insegnano RISC-V.
3. `propose_revisions`: per gli esercizi più ricalcabili l'LLM scrive una versione rivista, stesso concetto
   in forma nuova e allineata alle slide, con rubrica e motivazione.
"""
import re
from collections import Counter
from dataclasses import dataclass, field

from .ingest import BOILERPLATE, exam_date
from .llm import chat_json
from .models import Chunk
from .rag import Index, cite

# Marcatori dell'architettura insegnata. Bastano poche parole: servono a contare, non a classificare il codice.
ISA_MARKERS = {
    "x86": r"\b(?:eax|ebx|ecx|edx|ax|bx|cx|dx|8086|x86|int\s+21h)\b",
    "MIPS": r"(?:\bmips\b|\$[tsav]\d\b|\$v0\b|\bsyscall\b)",
    "RISC-V": r"(?:\brisc-?v\b|\becall\b|\bx(?:[12]?\d|3[01])\b)",
}
STOP = set("della delle degli dello dell nella nelle nel nei che con per una uno sono essere come quale quali "
           "quanti cosa sia dato data dati siano viene vengono questo questa ogni".split())


@dataclass
class StandardizedExercise:
    chunk_id: str
    ref: str                     # es. "2024_07_18 p.4"
    points: float
    similarity: float            # 0..1, massima somiglianza con un esame precedente
    closest_ref: str             # l'esercizio vecchio più simile
    repeats: int                 # quanti esami precedenti lo somigliano oltre la soglia
    text: str


@dataclass
class CoverageMismatch:
    exam_file: str
    exam_isa: str
    slides_isa: str
    evidence: str


@dataclass
class ExamRevision:
    """Un esercizio d'esame rivisto. Resta `pending` finché il docente non lo approva."""
    chunk_id: str
    original_ref: str
    problem: str                 # perché l'originale è ricalcabile o disallineato
    revised_prompt: str
    rubric: str
    why_better: str
    sources: list[str] = field(default_factory=list)
    status: str = "pending"


# ---------- 1. esercizi standardizzati ----------

def _clean(text: str) -> str:
    """Toglie le righe d'intestazione (nome, istruzioni, tempo) che sono uguali in ogni tema."""
    lines = [ln for ln in text.splitlines() if ln.strip() and not BOILERPLATE.search(ln)]
    return " ".join(" ".join(lines).split())


def _words(text: str) -> set[str]:
    toks = re.findall(r"[a-zàèéìòù]{4,}", text.lower())
    return {t for t in toks if t not in STOP}


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _exam_file(c: Chunk) -> str:
    return c.id.split("#", 1)[0].split("/", 1)[-1]


def _is_exercise(c: Chunk) -> bool:
    """Scarta copertine, griglie delle risposte e pagine quasi vuote."""
    return len(_words(_clean(c.text))) >= 12 and not re.match(r"^\s*risposte corrette", c.text, re.I)


def standardized_exercises(chunks: list[Chunk], since: str | None = None, threshold: float = 0.35,
                           top: int = 10) -> list[StandardizedExercise]:
    """Esercizi d'esame (dal mese `since`, "YYYY-MM") molto simili a esercizi di esami precedenti."""
    exams = [c for c in chunks if c.source == "exam" and _is_exercise(c)]
    dated = sorted(((exam_date(_exam_file(c)) or "0000-00", c) for c in exams), key=lambda x: x[0])
    bags = {c.id: _words(_clean(c.text)) for _, c in dated}
    out = []
    for d, c in dated:
        if since and d < since:
            continue
        older = [(o, _jaccard(bags[c.id], bags[o.id])) for od, o in dated if od < d]
        if not older:
            continue
        best, sim = max(older, key=lambda x: x[1])
        if sim < threshold:
            continue
        out.append(StandardizedExercise(
            chunk_id=c.id, ref=c.ref, points=c.points, similarity=round(sim, 2), closest_ref=best.ref,
            repeats=sum(1 for _, s in older if s >= threshold), text=_clean(c.text)))
    # prima quelli che valgono di più e si ripetono di più
    return sorted(out, key=lambda s: (s.similarity * s.points * (1 + s.repeats)), reverse=True)[:top]


def predictability(chunks: list[Chunk], since: str | None = None, threshold: float = 0.35) -> float:
    """Quota dei punti d'esame (dal mese `since`) su esercizi già visti in un esame precedente."""
    std = standardized_exercises(chunks, since, threshold, top=10_000)
    pool = [c for c in chunks if c.source == "exam" and _is_exercise(c)
            and (not since or (exam_date(_exam_file(c)) or "") >= since)]
    tot = sum(c.points for c in pool) or 1
    return round(sum(s.points for s in std) / tot, 3)


# ---------- 2. copertura esame / slide ----------

def isa_profile(chunks: list[Chunk]) -> Counter:
    cnt = Counter()
    for c in chunks:
        low = c.text.lower()
        for isa, pat in ISA_MARKERS.items():
            cnt[isa] += len(re.findall(pat, low))
    return cnt


def coverage_mismatches(chunks: list[Chunk], min_hits: int = 3) -> list[CoverageMismatch]:
    """Esami che usano un'architettura diversa da quella dominante nelle slide."""
    slides = isa_profile([c for c in chunks if c.source == "slide"])
    if not slides or not sum(slides.values()):
        return []
    slide_isa = slides.most_common(1)[0][0]
    by_file: dict[str, list[Chunk]] = {}
    for c in chunks:
        if c.source == "exam":
            by_file.setdefault(_exam_file(c), []).append(c)
    out = []
    for f, cs in sorted(by_file.items()):
        prof = isa_profile(cs)
        others = {k: v for k, v in prof.items() if k != slide_isa and v >= min_hits}
        if not others:
            continue
        isa = max(others, key=others.get)
        # MIPS citato accanto a RISC-V (es. "foglio con l'instruction set MIPS") è un disallineamento parziale
        dominant = prof[isa] > prof[slide_isa]
        out.append(CoverageMismatch(
            exam_file=f, exam_isa=isa, slides_isa=slide_isa,
            evidence=(f"{prof[isa]} riferimenti a {isa} contro {prof[slide_isa]} a {slide_isa}; "
                      f"le slide citano {slide_isa} {slides[slide_isa]} volte e {isa} {slides[isa]}."
                      + ("" if dominant else f" L'esame è su {slide_isa} ma mescola materiale {isa}."))))
    return out


# ---------- 3. proposte di revisione ----------

SYSTEM = (
    "Sei un docente universitario che rivede un tema d'esame. Ti do un esercizio d'esame che si ripete quasi "
    "uguale negli anni (gli studenti lo superano ricalcando le soluzioni dei temi vecchi), l'esercizio vecchio "
    "più simile e le slide pertinenti del corso. Riscrivi l'esercizio: stesso concetto e stesso livello di "
    "difficoltà, ma in una forma che non si risolve ricalcando lo schema (prevedere un risultato, trovare un "
    "errore, confrontare due soluzioni e motivare, applicare il concetto a un caso nuovo). Usa l'architettura e "
    "la notazione delle slide. Dai una rubrica con i punti chiave attesi. Cita le slide tra parentesi quadre. "
    'Rispondi in JSON: {"problem": "...", "revised_prompt": "...", "rubric": "...", "why_better": "..."}. '
    "In italiano."
)


def _offline_revision(s: StandardizedExercise, slides: list[Chunk], isa: str | None) -> dict:
    ref = slides[0].ref if slides else "le slide del corso"
    first = s.text[:220]
    return {
        "problem": (f"Coincide al {s.similarity:.0%} con {s.closest_ref} e somiglia a {s.repeats} esami precedenti: "
                    "si può risolvere riconoscendo lo schema."),
        "revised_prompt": (f"Dato il testo originale («{first}…»), viene proposta una soluzione con un errore. "
                           f"Individua l'errore, spiega perché è sbagliato e correggilo"
                           + (f" usando {isa}" if isa else "") + f", facendo riferimento a [{ref}]."),
        "rubric": "Individua l'errore; motiva con il concetto, non con la procedura; correzione corretta e giustificata.",
        "why_better": "Chiede di ragionare sul concetto invece di riprodurre una soluzione memorizzata.",
    }


def propose_revisions(items: list[StandardizedExercise], index: Index, chunks: list[Chunk],
                      top: int = 3) -> list[ExamRevision]:
    slides_prof = isa_profile([c for c in chunks if c.source == "slide"])
    isa = slides_prof.most_common(1)[0][0] if sum(slides_prof.values()) else None
    out = []
    for s in items[:top]:
        slides = index.retrieve(s.text[:1000], k=3, source="slide")
        user = (f"Esercizio attuale [{s.ref}] ({s.points:g} punti):\n{s.text}\n\n"
                f"Esercizio vecchio più simile: [{s.closest_ref}] (somiglianza {s.similarity:.0%}, "
                f"si ripete in {s.repeats} esami)\n\nArchitettura delle slide: {isa or 'n.d.'}\n\n"
                f"Slide pertinenti:\n{cite(slides)}")
        d = chat_json(SYSTEM, user, lambda s=s, slides=slides: _offline_revision(s, slides, isa))
        out.append(ExamRevision(
            chunk_id=s.chunk_id, original_ref=s.ref, problem=d.get("problem", ""),
            revised_prompt=d.get("revised_prompt", ""), rubric=d.get("rubric", ""),
            why_better=d.get("why_better", ""), sources=[c.id for c in slides]))
    return out


@dataclass
class ExamReport:
    predictability: float                       # quota di punti su esercizi già visti
    standardized: list[StandardizedExercise]
    mismatches: list[CoverageMismatch]
    revisions: list[ExamRevision]


def review_exams(chunks: list[Chunk], index: Index, since: str | None = None, top: int = 3) -> ExamReport:
    """Punto d'ingresso dell'agente. `chunks` deve contenere TUTTI gli esami (anche i vecchi, servono come
    storico); `since` limita l'analisi agli esami recenti."""
    std = standardized_exercises(chunks, since)
    return ExamReport(predictability=predictability(chunks, since), standardized=std,
                      mismatches=coverage_mismatches(chunks), revisions=propose_revisions(std, index, chunks, top))


def mismatch_periods(mismatches: list[CoverageMismatch]) -> list[str]:
    """Riassume i disallineamenti per periodo, es. 'Esami 2019-06 → 2025-01 (21 appelli): MIPS, slide su RISC-V'."""
    out, run = [], []
    for m in mismatches + [None]:
        if run and (m is None or m.exam_isa != run[-1].exam_isa):
            a, b = exam_date(run[0].exam_file) or run[0].exam_file, exam_date(run[-1].exam_file) or run[-1].exam_file
            out.append(f"Esami {a} → {b} ({len({exam_date(r.exam_file) for r in run})} appelli): "
                       f"usano {run[0].exam_isa}, le slide insegnano {run[0].slides_isa}.")
            run = []
        if m is not None:
            run.append(m)
    return out

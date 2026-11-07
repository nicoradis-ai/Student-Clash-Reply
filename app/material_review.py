"""Agente 1 di 3 · Revisione del materiale del corso.

Cosa risolve: le slide non rispecchiano quello che l'esame chiede davvero. L'agente parte dai DATI, non da
pagine prese a caso: per ogni concetto confronta peso nelle slide e peso nei punti d'esame (indice di
copertura) e, se c'è, il transfer gap. Sceglie i concetti più disallineati e per ciascuno propone modifiche
concrete a pagine precise ("<file> p.N"), motivate con le pagine d'esame che le giustificano.

Regola ADR 0002: ogni proposta dice anche cosa può fare l'esame e cosa può fare lo studente, mai un solo
destinatario. Le citazioni sono vincolate: una pagina che l'agente non ha visto viene scartata."""
from dataclasses import dataclass, field

from .llm import chat_json
from .models import Chunk, Concept, ConceptMetrics
from .rag import Index

ACTIONS = ("aggiungere", "modificare", "esempio", "esercizio svolto", "ridurre")

SYSTEM = (
    "Sei l'agente che revisiona il materiale di un corso universitario per allinearlo a ciò che l'esame "
    "verifica davvero. Ti do UN concetto con i suoi dati (quota di slide, quota di punti d'esame, transfer gap "
    "= punteggio sugli esercizi tipici meno punteggio sulle varianti), le pagine di slide che lo trattano e le "
    "pagine d'esame che lo chiedono, ognuna con il suo riferimento tra parentesi quadre.\n"
    "Proponi da 2 a 4 modifiche CONCRETE alle slide, non consigli generici. Per ognuna:\n"
    "- action: una tra " + ", ".join(f"'{a}'" for a in ACTIONS) + ";\n"
    "- slide_ref: il riferimento ESATTO di una delle slide date (per 'aggiungere' è la pagina dopo cui inserire);\n"
    "- change: cosa scrivere o cambiare, abbastanza preciso da poterlo fare subito (titolo, contenuto, esempio);\n"
    "- why: il motivo, citando tra parentesi quadre le pagine d'esame che lo giustificano;\n"
    "- exam_side: cosa può cambiare l'esame sullo stesso punto;\n"
    "- student_side: cosa può fare lo studente nel frattempo.\n"
    "Non dare la colpa a nessuno: è un disallineamento tra insegnamento, esame e studio. Non inventare "
    "contenuti che le pagine non contengono. Se l'esame pesa più delle slide, privilegia 'aggiungere', "
    "'esempio' ed 'esercizio svolto'; se le slide pesano molto più dell'esame, valuta 'ridurre'. "
    "Se il transfer gap è alto, proponi esempi in forma diversa da quella dei temi d'esame (quando NON si "
    "applica, casi limite, errori tipici). Rispondi in JSON: "
    '{"diagnosis": "una frase su cosa non torna", "proposals": [{"action": "...", "slide_ref": "...", '
    '"change": "...", "why": "...", "exam_side": "...", "student_side": "..."}]}. In italiano.'
)


@dataclass
class SlideProposal:
    """Una modifica proposta a una pagina precisa del materiale, con i tre lati (ADR 0002)."""
    concept_id: str
    action: str
    slide_ref: str               # "<file> p.N", sempre una pagina che l'agente ha visto
    change: str
    why: str
    exam_side: str
    student_side: str
    exam_refs: list[str] = field(default_factory=list)


@dataclass
class ConceptReview:
    concept_id: str
    concept_name: str
    teaching_weight: float
    exam_weight: float
    transfer_gap: float
    priority: float
    diagnosis: str
    proposals: list[SlideProposal] = field(default_factory=list)


def priority(m: ConceptMetrics) -> float:
    """Più alto = più urgente. Sotto-insegnato rispetto all'esame pesa di più che sovra-insegnato."""
    under = max(0.0, m.exam_weight - m.teaching_weight)
    over = max(0.0, m.teaching_weight - m.exam_weight)
    return round(2 * under + over + max(0.0, m.transfer_gap), 3)


def _pages(con: Concept, chunks: list[Chunk], index: Index | None, source: str, k: int,
           query: str = "") -> list[Chunk]:
    """Pagine del concetto. Esami: i più pesanti prima. Slide: quelle del concetto più vicine a `query`
    (il testo delle domande d'esame), così l'agente guarda le pagine che l'esame mette alla prova."""
    by_id = {c.id: c for c in chunks}
    own = [by_id[i] for i in con.chunk_ids if i in by_id and by_id[i].source == source]
    if source == "exam":
        own.sort(key=lambda c: -c.points)
    elif index is not None and query and own:
        mine = {c.id for c in own}
        near = [c for c in index.retrieve(query, k=len(index.chunks), source=source, min_sim=0)
                if c.id in mine]  # min_sim=0: qui serve solo a ordinare i brani del concetto
        own = near or own
    picked = own[:k]
    if len(picked) < k and index is not None:
        for c in index.retrieve(f"{con.name} {con.description}", k=k * 2, source=source):
            if c not in picked:
                picked.append(c)
            if len(picked) >= k:
                break
    return picked


def _excerpt(c: Chunk, n: int = 900) -> str:
    return f"[{c.ref}]" + (f" ({c.points:g} punti)" if c.source == "exam" else "") + "\n" + " ".join(c.text.split())[:n]


def _offline(con: Concept, m: ConceptMetrics, slides: list[Chunk], exams: list[Chunk]) -> dict:
    if not slides:
        return {"diagnosis": f"Nessuna slide trovata su {con.name}.", "proposals": []}
    ex = ", ".join(f"[{e.ref}]" for e in exams[:2]) or "i temi d'esame"
    under = m.exam_weight > m.teaching_weight
    first, last = slides[0].ref, slides[min(1, len(slides) - 1)].ref
    props = []
    if under:
        props.append({
            "action": "esercizio svolto", "slide_ref": last,
            "change": f"Dopo questa pagina aggiungere un esercizio svolto su {con.name} nella forma chiesta in {ex}, "
                      f"con i passaggi commentati.",
            "why": f"{con.name} vale il {m.exam_weight:.0%} dei punti d'esame ma solo il {m.teaching_weight:.0%} "
                   f"delle slide {ex}.",
            "exam_side": "Dichiarare nel programma quanto pesa questo argomento all'esame.",
            "student_side": f"Svolgere {ex} dopo aver ripassato {first}.",
        })
    elif m.teaching_weight > 2 * m.exam_weight + 0.02:
        props.append({
            "action": "ridurre", "slide_ref": first,
            "change": f"Condensare la parte descrittiva su {con.name} e spostare i dettagli in appendice.",
            "why": f"Pesa il {m.teaching_weight:.0%} delle slide ma il {m.exam_weight:.0%} dei punti d'esame.",
            "exam_side": f"Se l'argomento è importante, inserirlo nell'esame con almeno una domanda {ex}.",
            "student_side": "Leggere l'appendice solo dopo gli argomenti più pesanti.",
        })
    props.append({
        "action": "esempio", "slide_ref": first,
        "change": f"Aggiungere un controesempio: un caso in cui {con.name} non si applica o porta a un errore tipico, "
                  f"con la spiegazione del perché.",
        "why": (f"Transfer gap {m.transfer_gap:+.0%}: gli studenti risolvono la forma solita ma non le varianti {ex}."
                if m.transfer_gap > 0.1 else f"Le domande d'esame {ex} chiedono di applicare il concetto, non di definirlo."),
        "exam_side": f"Inserire una domanda su {con.name} in forma non standard (trovare l'errore, prevedere il risultato).",
        "student_side": "Prima di rifare i temi vecchi, spiegare a voce quando il concetto NON si usa.",
    })
    return {"diagnosis": (f"Slide {m.teaching_weight:.0%} contro esame {m.exam_weight:.0%}"
                          + (f", transfer gap {m.transfer_gap:+.0%}" if m.transfer_gap else "") + "."),
            "proposals": props}


def review_concept(con: Concept, m: ConceptMetrics, chunks: list[Chunk], index: Index | None = None,
                   k_slides: int = 6, k_exams: int = 4) -> ConceptReview:
    exams = _pages(con, chunks, index, "exam", k_exams)
    query = con.name + " " + " ".join(" ".join(e.text.split())[:400] for e in exams)
    slides = _pages(con, chunks, index, "slide", k_slides, query)
    user = (f"Concetto: {con.name} – {con.description}\n"
            f"Quota di slide: {m.teaching_weight:.1%} · quota di punti d'esame: {m.exam_weight:.1%} · "
            f"transfer gap: {m.transfer_gap:+.1%} (tipici {m.typical_score:.0%}, varianti {m.variant_score:.0%})\n\n"
            "SLIDE:\n" + "\n\n".join(_excerpt(c) for c in slides) +
            "\n\nESAME:\n" + ("\n\n".join(_excerpt(c, 600) for c in exams) or "(nessuna pagina d'esame trovata)"))
    data = chat_json(SYSTEM, user, lambda: _offline(con, m, slides, exams))
    valid = {c.ref for c in slides}
    exam_refs = [c.ref for c in exams]
    proposals = []
    for p in data.get("proposals", []):
        ref = str(p.get("slide_ref", "")).strip().strip("[]")
        change = str(p.get("change", "")).strip()
        if ref not in valid or not change:  # citazione inventata o vuota: scartata
            continue
        why = str(p.get("why", "")).strip()
        proposals.append(SlideProposal(
            concept_id=con.id, action=str(p.get("action", "modificare")).strip().lower(), slide_ref=ref,
            change=change, why=why, exam_side=str(p.get("exam_side", "")).strip(),
            student_side=str(p.get("student_side", "")).strip(),
            exam_refs=[r for r in exam_refs if r in why] or exam_refs[:2],
        ))
    if not proposals and slides:  # l'LLM ha citato solo pagine inesistenti: meglio il fallback che niente
        return review_concept_offline(con, m, slides, exams)
    return ConceptReview(con.id, con.name, m.teaching_weight, m.exam_weight, m.transfer_gap, priority(m),
                         str(data.get("diagnosis", "")).strip(), proposals)


def review_concept_offline(con, m, slides, exams) -> ConceptReview:
    d = _offline(con, m, slides, exams)
    refs = [c.ref for c in exams]
    return ConceptReview(con.id, con.name, m.teaching_weight, m.exam_weight, m.transfer_gap, priority(m),
                         d["diagnosis"], [SlideProposal(concept_id=con.id, exam_refs=refs[:2], **p)
                                          for p in d["proposals"]])


def review_material(concepts: list[Concept], metrics: list[ConceptMetrics], chunks: list[Chunk],
                    index: Index | None = None, top: int = 4) -> list[ConceptReview]:
    """Ingresso dell'agente: i `top` concetti più disallineati, ognuno con proposte su pagine precise.
    Funziona anche senza risposte degli studenti (transfer gap 0): allora conta solo la copertura."""
    by_id = {c.id: c for c in concepts}
    ranked = sorted((m for m in metrics if m.concept_id in by_id), key=priority, reverse=True)[:top]
    return [review_concept(by_id[m.concept_id], m, chunks, index) for m in ranked]

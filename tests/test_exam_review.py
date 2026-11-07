from app.exam_review import coverage_mismatches, mismatch_periods, predictability, standardized_exercises
from app.models import Chunk

CACHE = ("Si consideri un processore connesso ad una memoria da {n}KB e dotato di una cache direct mapped da "
         "16 linee ciascuna da 32 byte. Assumendo che inizialmente la cache sia vuota, si indichi per ciascun "
         "accesso della sequenza seguente se genera hit oppure miss e quale linea viene sostituita.")


def _exam(f, i, text, pts=5.0):
    return Chunk(f"exams/{f}#{i}", "exam", f"{f[:10]} p.{i + 1}", text, pts)


def test_repeated_exercise_is_flagged_and_new_one_is_not():
    chunks = [
        _exam("2020_07_01.pdf", 0, CACHE.format(n=64)),
        _exam("2024_07_02.pdf", 0, CACHE.format(n=128)),
        _exam("2024_07_02.pdf", 1, "Descrivere come un'interruzione vettorizzata viene riconosciuta, quale "
                                   "registro salva il program counter e come il gestore ritorna al programma "
                                   "interrotto, confrontando polling e interrupt nelle periferiche lente."),
    ]
    std = standardized_exercises(chunks, since="2021-01")
    assert [s.chunk_id for s in std] == ["exams/2024_07_02.pdf#0"]
    assert std[0].closest_ref.startswith("2020_07_01") and std[0].similarity > 0.8
    assert predictability(chunks, since="2021-01") == 0.5


def test_exam_on_other_isa_than_slides_is_a_mismatch():
    chunks = [Chunk("slides/a.pdf#0", "slide", "a p.1", "RISC-V: addi x5, x0, 1 ; ecall ; lw x6, 0(x5)"),
              _exam("2020_02_11.pdf", 0, "Scrivere in MIPS: lw $t0, 0($a0); addi $t1, $t0, 1; syscall"),
              _exam("2025_06_16.pdf", 0, "Scrivere in RISC-V: lw x6, 0(x10); ecall")]
    mm = coverage_mismatches(chunks)
    assert [(m.exam_file, m.exam_isa, m.slides_isa) for m in mm] == [("2020_02_11.pdf", "MIPS", "RISC-V")]
    assert mismatch_periods(mm) == ["Esami 2020-02 → 2020-02 (1 appelli): usano MIPS, le slide insegnano RISC-V."]


def test_agent_turns_repeated_exercise_into_proposal(monkeypatch):
    from app.agents.base import CourseContext
    from app.agents.esami import EsamiAgent
    from app.models import Concept, ConceptMetrics
    from app.rag import Index
    monkeypatch.setenv("OFFLINE", "1")
    chunks = [Chunk("slides/c.pdf#0", "slide", "c p.1", "Memorie cache direct mapped: linee, tag, hit e miss"),
              _exam("2020_07_01.pdf", 0, CACHE.format(n=64)), _exam("2024_07_02.pdf", 0, CACHE.format(n=128))]
    ctx = CourseContext(chunks=chunks, index=Index(chunks),
                        concepts=[Concept("cache", "Memorie cache", "cache", []), Concept("bus", "Bus", "bus", [])],
                        metrics=[ConceptMetrics("cache", .8, .4, .4, .3, .6), ConceptMetrics("bus", .7, .7, 0, .2, .1)])
    props = EsamiAgent().run(ctx)
    assert [(p.concept_id, p.target_ref) for p in props] == [("cache", "2024_07_02 p.1")]
    assert "2020_07_01" in props[0].rationale and props[0].change

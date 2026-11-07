import numpy as np

from app import llm
from app.concepts import extract_concepts, sample_material
from app.ingest import _pdf_exam_points, exam_date, load_course
from app.models import Chunk
from app.rag import Index


def test_embed_failure_never_mixes_dimensions(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("OFFLINE", raising=False)
    monkeypatch.setattr(llm, "EMBED_DEGRADED", False)
    calls = {"n": 0}

    def fake_batch(texts):
        calls["n"] += 1
        if calls["n"] > 1:  # il primo lotto va, il secondo fallisce
            raise RuntimeError("limite superato")
        return [[1.0] * 1536 for _ in texts]

    monkeypatch.setattr(llm, "_embed_batch", fake_batch)
    out = llm.embed([f"testo {i}" for i in range(llm.EMBED_BATCH + 5)])
    assert out.shape == (llm.EMBED_BATCH + 5, llm.OFFLINE_DIM)  # tutto offline, non metà e metà
    assert llm.EMBED_DEGRADED and llm.ERRORS


def test_index_rebuilds_when_embeddings_degrade(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("OFFLINE", raising=False)
    monkeypatch.setattr(llm, "EMBED_DEGRADED", False)
    state = {"fail": False}

    def fake_batch(texts):
        if state["fail"]:
            raise RuntimeError("rete giù")
        return [list(np.ones(1536)) for _ in texts]

    monkeypatch.setattr(llm, "_embed_batch", fake_batch)
    idx = Index([Chunk("a", "slide", "A", "cache e memoria"), Chunk("b", "slide", "B", "pipeline")])
    assert idx.vecs.shape[1] == 1536
    state["fail"] = True
    assert idx.retrieve("cache")  # niente crash per dimensioni diverse
    assert idx.vecs.shape[1] == llm.OFFLINE_DIM


def test_sample_covers_every_file():
    chunks = [Chunk(f"slides/f{f}.pdf#{p}", "slide", f"f{f} p.{p}", "x" * 1000) for f in range(30) for p in range(50)]
    chunks += [Chunk(f"exams/e{f}.pdf#{p}", "exam", f"e{f} p.{p}", "y" * 1000) for f in range(10) for p in range(5)]
    s = sample_material(chunks)
    assert len(s) <= 12000
    for f in range(30):
        assert f"[f{f} p." in s
    for f in range(10):
        assert f"[e{f} p." in s


def test_pdf_exam_points():
    pages = ["Domande a risposta chiusa ...", "altre domande", "Domande a risposta aperta (sino a 5 punti per ogni domanda)",
             "Esercizio (sino a 12 punti – è possibile consultare)", "seguito"]
    assert _pdf_exam_points(pages) == [1, 1, 5, 12, 12]


def test_exam_date_filter():
    assert exam_date("2019_02_14.pdf") == "2019-02"
    assert exam_date("2013_2_12.pdf") == "2013-02"
    assert exam_date("esame-2025-06.md") is None


def test_offline_concepts_on_example_course(monkeypatch):
    monkeypatch.setenv("OFFLINE", "1")
    cs = extract_concepts(load_course("data/esempio-poo"))
    assert len(cs) == 5 and len({c.id for c in cs}) == 5

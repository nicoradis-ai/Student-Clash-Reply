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


def test_sample_skips_cover_and_takes_two_per_file():
    chunks = [Chunk(f"slides/f{f}.pdf#{p}", "slide", f"f{f} p.{p + 1}", f"pagina {p} " * 100)
              for f in range(47) for p in range(30)]
    s = sample_material(chunks)
    assert "p.1]" not in s  # mai la copertina quando il file ha più pagine
    for f in range(47):
        assert s.count(f"[f{f} p.") >= 2


def test_assign_chunks_reuses_index_cache(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("OFFLINE", raising=False)
    monkeypatch.setattr(llm, "EMBED_DEGRADED", False)
    seen = []

    def fake_batch(texts):
        seen.append(tuple(texts))
        return [list(np.ones(1536)) for _ in texts]

    monkeypatch.setattr(llm, "_embed_batch", fake_batch)
    monkeypatch.setattr(llm, "chat_json", lambda s, u, fb: {"concepts": [{"name": "Cache"}, {"name": "Bus"}]})
    import app.concepts as concepts_mod
    monkeypatch.setattr(concepts_mod, "chat_json", lambda s, u, fb: {"concepts": [{"name": "Cache"}, {"name": "Bus"}]})
    chunks = [Chunk(f"exams/e.pdf#{i}", "exam", f"e p.{i}", f"testo {i}") for i in range(5)]
    Index(chunks)
    extract_concepts(chunks)
    chunk_batches = [b for b in seen if b and b[0].startswith("testo")]
    assert len(set(chunk_batches)) == 1  # stessi lotti di Index: in produzione sono cache hit


def test_dotenv_does_not_override(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('﻿# commento\nOPENAI_MODEL="gpt-test"\nexport FOO_X=1\nOPENAI_API_KEY=da-file\n', encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "gia-impostata")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("FOO_X", raising=False)
    llm._load_dotenv(str(f))
    import os
    assert os.environ["OPENAI_MODEL"] == "gpt-test" and os.environ["FOO_X"] == "1"
    assert os.environ["OPENAI_API_KEY"] == "gia-impostata"

"""Provider LLM configurabile da .env (OpenAI, Gemini, Ollama, custom, offline)."""
import pytest

from app import llm

VARS = ["OFFLINE", "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "EMBED_PROVIDER", "EMBED_MODEL",
        "EMBED_BASE_URL", "EMBED_API_KEY", "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_EMBED_MODEL",
        "OPENAI_BASE_URL", "GEMINI_API_KEY"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in VARS:
        monkeypatch.delenv(v, raising=False)


def test_nothing_configured_is_offline():
    assert llm.config("chat") is None and llm.config("embed") is None and not llm.is_online()


def test_openai_keeps_old_variables(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    c, e = llm.config("chat"), llm.config("embed")
    assert c["model"] == "gpt-test" and c["base_url"] is None and c["api_key"] == "sk-x"
    assert e["model"] == "text-embedding-3-small"


def test_gemini_preset(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-non-usare")  # le variabili OpenAI non valgono per Gemini
    c, e = llm.config("chat"), llm.config("embed")
    assert c["model"] == "gemini-2.5-flash" and "generativelanguage" in c["base_url"]
    assert e["model"] == "gemini-embedding-001" and e["api_key"] == "g-key" and e["batch"] == 100


def test_ollama_needs_no_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.1:8b")
    c = llm.config("chat")
    assert c["model"] == "llama3.1:8b" and c["base_url"].startswith("http://localhost:11434")
    assert llm.config("embed")["model"] == "nomic-embed-text"


def test_chat_on_gemini_embeddings_on_ollama(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "g-key")
    monkeypatch.setenv("EMBED_PROVIDER", "ollama")
    e = llm.config("embed")
    assert e["provider"] == "ollama" and e["api_key"] == "ollama"  # la chiave Gemini non passa a Ollama


def test_embeddings_offline_with_chat_online(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("EMBED_PROVIDER", "offline")
    assert llm.is_online() and not llm.embeds_online()
    assert llm.embed(["ciao mondo"]).shape == (1, llm.OFFLINE_DIM)


def test_offline_flag_wins(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OFFLINE", "1")
    assert not llm.is_online() and not llm.embeds_online()


def test_unknown_provider_is_a_clear_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemnii")
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        llm.config("chat")


def test_fenced_json_and_rate_limit_retry(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class RateLimit(Exception):
        status_code = 429

    class Msg:
        content = '```json\n{"ok": true}\n```'

    class Resp:
        choices = [type("C", (), {"message": Msg})]

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    calls["n"] += 1
                    if calls["n"] == 1:
                        raise RateLimit("troppe richieste")
                    return Resp

    monkeypatch.setattr(llm, "_get_client", lambda cfg: Client)
    assert llm.chat_json("s", "u", lambda: {"ok": False}) == {"ok": True}
    assert calls["n"] == 2

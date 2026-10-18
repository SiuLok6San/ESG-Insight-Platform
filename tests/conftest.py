import pytest

from server import Server
from tools.evidence import EvidenceTable, load_evidence


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Tests never contact a real LLM unless they inject a stub.

    Empty values (rather than unset ones) stop load_dotenv() from loading a
    real key from a developer's .env file.
    """
    monkeypatch.setenv("LLM_ENABLED", "false")
    for name in ("OLLAMA_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "LLM_PROVIDER", "OLLAMA_CLOUD_MODEL"):
        monkeypatch.setenv(name, "")


@pytest.fixture(scope="session")
def evidence() -> EvidenceTable:
    return load_evidence()


@pytest.fixture
def offline_server() -> Server:
    """Backend with the LLM disabled and no network access."""
    return Server(use_llm=False)

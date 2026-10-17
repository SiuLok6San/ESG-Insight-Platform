import pytest

from server import Server
from tools.evidence import EvidenceTable, load_evidence


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Tests never contact a real LLM unless they inject a stub."""
    monkeypatch.setenv("LLM_ENABLED", "false")


@pytest.fixture(scope="session")
def evidence() -> EvidenceTable:
    return load_evidence()


@pytest.fixture
def offline_server() -> Server:
    """Backend with the LLM disabled and no network access."""
    return Server(use_llm=False, fetch_external=False)

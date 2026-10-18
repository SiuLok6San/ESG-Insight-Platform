"""Shared test helpers (imported by tests; fixtures live in conftest.py)."""

from typing import Dict, Mapping

from tools.evidence import EvidenceRow, EvidenceTable
from tools.score_engine import ALL_KEYS, RUBRIC

BANKS = ["ING Group", "ABN AMRO", "Rabobank"]


def lowest_categories() -> Dict[str, str]:
    cats = {ind.key: min(ind.scores, key=ind.scores.get) for ind in RUBRIC}
    cats["controversy"] = "severe"
    return cats


def highest_categories() -> Dict[str, str]:
    cats = {ind.key: max(ind.scores, key=ind.scores.get) for ind in RUBRIC}
    cats["controversy"] = "none"
    return cats


def make_table(categories_by_bank: Mapping[str, Mapping[str, str]]) -> EvidenceTable:
    """Synthetic evidence table for tests that need controlled inputs."""
    rows = []
    for bank, cats in categories_by_bank.items():
        for key in ALL_KEYS:
            rows.append(
                EvidenceRow(
                    bank=bank,
                    indicator=key,
                    category=cats[key],
                    evidence_summary="test",
                    source_document="Test report",
                    page=1,
                    url="https://example.com/report.pdf",
                    status="confirmed",
                    notes="",
                )
            )
    return EvidenceTable(rows)


class StubLLM:
    """Stand-in for LocalLLM: a fixed route (or one chosen per question), a streamed answer and a report.

    ``calls`` records which step called the model: "route", "answer" or "report".
    """

    def __init__(self, route=None, answer="ING Group has the highest official score (ING Group, p. 111).") -> None:
        self.route = route
        self.answer_text = answer
        self.calls = []
        self.last_router_prompt = ""
        self.last_messages = []

    def ask_json(self, system: str, user: str) -> dict:
        self.calls.append("route")
        self.last_router_prompt = user
        question = user.rsplit("Question: ", 1)[-1].split("\n", 1)[0]
        route = self.route(question) if callable(self.route) else self.route
        return dict(route or {"banks": [], "indicators": [], "intent": "explain", "scenario": {}})

    def stream(self, messages):
        self.calls.append("answer")
        self.last_messages = messages
        words = self.answer_text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    def ask(self, prompt: str) -> str:
        self.calls.append("report")
        return "## Stub narrative report"


def server_with_stub(stub=None, **kwargs):
    """An offline Server whose AI assistant uses ``stub`` (no network, no key)."""
    from server import Server

    server = Server(use_llm=False, **kwargs)
    stub = stub or StubLLM()
    server.use_llm = True
    server.chat.llm = stub
    server.writer.llm = stub
    return server, stub

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
    """Returns fixed text; the category JSON includes valid, invalid and unknown entries."""

    def __init__(self) -> None:
        self.calls = 0

    def ask(self, prompt: str) -> str:
        self.calls += 1
        if "single JSON object" in prompt:
            self.last_prompt = prompt
        if "single JSON object" in prompt:
            return (
                "Narrative analysis.\n"
                '{"climate_plan": "weak", "fossil_policy": "exit", '
                '"aml_maturity": "excellent", "made_up_key": "x"}'
            )
        return "- summary bullet"

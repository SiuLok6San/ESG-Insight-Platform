import pytest

from server import Server
from tests.helpers import highest_categories, make_table
from tools.ai_review import (
    REVIEW_COLUMNS,
    load_definitions,
    load_reviews,
    review_row,
    run_review,
    summarise,
    verify_quote,
    write_reviews,
)
from tools.score_engine import ALL_KEYS

PAGE = (
    "In March 2025, ING became the first global systemically important bank to receive "
    "validation from the Science Based Targets initiative (SBTi) for 1.5°C-aligned targets. "
    "T h e  v a l i d a t e d  t a r g e t s  c o v e r  6 7  p e r c e n t  of our financed emissions."
)


class StubClient:
    model = "stub-model"

    def __init__(self, answer):
        self.answer = answer
        self.prompts = []

    def chat_json(self, system, user):
        self.prompts.append(user)
        return self.answer


GOOD = {
    "verdict": "supports",
    "suggested_category": "sbt_aligned",
    "quote": "receive validation from the Science Based Targets initiative (SBTi) for 1.5°C-aligned targets",
    "explanation": "The page states SBTi validation.",
}


def test_quote_verification_tolerates_pdf_formatting():
    assert verify_quote("The validated targets cover 67 percent of our financed emissions", PAGE)  # letter-spaced in PDF
    assert verify_quote("RECEIVE VALIDATION FROM THE SCIENCE BASED TARGETS INITIATIVE", PAGE)  # case
    assert verify_quote("1.5°C aligned targets. The validated", PAGE)  # nbsp and hyphen differences


def test_quote_verification_rejects_invented_and_trivial_quotes():
    assert not verify_quote("ING has fully exited all fossil fuel financing", PAGE)
    assert not verify_quote("ING", PAGE)  # too short to prove anything
    assert not verify_quote("", PAGE)


def test_definitions_cover_every_indicator():
    definitions = load_definitions()
    assert set(definitions) == set(ALL_KEYS)
    assert all(definitions.values())


def evidence_row():
    table = make_table({"ING Group": highest_categories()})
    return table, table.for_bank("ING Group")["climate_plan"]


def test_valid_answer_has_no_problems():
    _, row = evidence_row()
    client = StubClient(GOOD)
    result = review_row(client, row, PAGE, "definition text", "stub")
    assert (result.ai_verdict, result.category_agrees, result.quote_verified, result.problems) == (
        "supports", True, True, ""
    )
    assert result.model == "stub-model"
    assert PAGE in client.prompts[0] and "definition text" in client.prompts[0]


def test_invented_quote_and_invalid_values_are_flagged():
    _, row = evidence_row()
    bad = {"verdict": "maybe", "suggested_category": "excellent", "quote": "ING exited fossil fuels completely in 2025", "explanation": ""}
    result = review_row(StubClient(bad), row, PAGE, "d", "stub")
    assert not result.quote_verified
    assert "invalid verdict" in result.problems
    assert "not in rubric" in result.problems
    assert "quote not found on the cited page" in result.problems


def test_run_write_load_and_summarise(tmp_path):
    table, _ = evidence_row()
    results = run_review(table, StubClient(GOOD), lambda row: PAGE, "stub")
    assert len(results) == len(ALL_KEYS)

    path = tmp_path / "ai_review.csv"
    write_reviews(results, path)
    reviews = load_reviews(path)
    assert set(reviews) == {("ING Group", key) for key in ALL_KEYS}
    assert reviews[("ING Group", "climate_plan")]["quote_verified"] is True

    summary = summarise(reviews)
    assert summary["rows"] == len(ALL_KEYS)
    assert summary["verdicts"]["supports"] == len(ALL_KEYS)
    assert summary["quote_verified"] == len(ALL_KEYS)
    assert summary["category_agrees"] == 1  # the stub always suggests sbt_aligned
    assert summary["models"] == ["stub/stub-model"]


def test_missing_review_file_means_not_run(tmp_path):
    assert load_reviews(tmp_path / "missing.csv") == {}


def test_review_file_with_wrong_columns_is_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("bank,indicator\nING Group,climate_plan\n")
    with pytest.raises(ValueError, match="columns"):
        load_reviews(path)
    assert REVIEW_COLUMNS[0] == "bank"


def test_server_attaches_reviews_without_changing_scores(tmp_path):
    table, _ = evidence_row()
    path = tmp_path / "ai_review.csv"
    write_reviews(run_review(table, StubClient(GOOD), lambda row: PAGE, "stub"), path)

    plain = Server(use_llm=False, review_path=tmp_path / "none.csv")
    reviewed = Server(use_llm=False, review_path=path)
    a, b = plain.score_bank("ING Group"), reviewed.score_bank("ING Group")
    assert a["scores"] == b["scores"]
    assert b["breakdown"][0]["ai_review"]["ai_verdict"] == "supports"
    assert a["breakdown"][0]["ai_review"] is None
    disagreements = reviewed.ai_review_summary()["disagreements"]
    assert len(disagreements) == len(ALL_KEYS) - 1 and all(not d["category_agrees"] for d in disagreements)

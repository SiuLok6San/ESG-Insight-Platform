import pytest

from tools import blind_review
from tools.ai_review import load_definitions, load_reviews
from tools.score_engine import allowed_categories

PAGES = {137: "Targets are set on an annual basis by the boards.", 138: "The unadjusted gender pay gap was 27 percent in 2025."}


class FakeClient:
    model = "fake-model"

    def __init__(self, answer):
        self.answer = answer
        self.prompts = []

    def chat_json(self, system, user):
        self.prompts.append(user)
        return self.answer


@pytest.fixture
def row(evidence):
    return evidence.for_bank("ING Group")["diversity_inclusion"]  # quotes p. 137 and p. 138


def test_prompt_contains_pages_and_definitions_but_nothing_from_the_analysts(row):
    definitions = load_definitions()
    prompt = blind_review.build_prompt(row, PAGES, definitions[row.indicator])
    assert blind_review.row_pages(row) == [137, 138]
    assert "page 137" in prompt and "page 138" in prompt and PAGES[138] in prompt
    assert definitions[row.indicator] in prompt
    assert row.evidence_summary not in prompt and row.notes not in prompt
    assert "Analyst" not in prompt and "analyst" not in prompt
    assert row.bank not in prompt and "ING" not in prompt  # the prompt does not name the bank


def test_quote_may_come_from_any_page_shown(row):
    answer = {"category": "full", "quote": "The unadjusted gender pay gap was 27 percent in 2025.", "explanation": "x"}
    result = blind_review.review_row(FakeClient(answer), row, PAGES, "def", "fake", reviewed_on="2026-10-18")
    assert (result.ai_category, result.category_agrees, result.quote_page, result.problems) == ("full", True, 138, "")


def test_invalid_answers_are_flagged_not_trusted(row):
    answer = {"category": "excellent", "quote": "A sentence that is not on either page at all.", "explanation": "x"}
    result = blind_review.review_row(FakeClient(answer), row, PAGES, "def", "fake")
    assert not result.category_agrees and not result.quote_verified and result.quote_page is None
    assert "not in rubric" in result.problems and "quote not found" in result.problems


def test_results_round_trip_and_report_lists_every_disagreement(tmp_path, evidence):
    ing = evidence.for_bank("ING Group")
    results = [
        blind_review.BlindResult("ING Group", "labor_rights", "medium", "139", "weak", False, "q", 139, True, "No CBA data.", "", "p", "m", "2026-10-18", "v"),
        blind_review.BlindResult("ING Group", "controversy", "moderate", "311", "none", False, "q", None, False, "Nothing new.", "", "p", "m", "2026-10-18", "v"),
        blind_review.BlindResult("ING Group", "climate_plan", "sbt_aligned", "111", "sbt_aligned", True, "q", 111, True, "ok", "", "p", "m", "2026-10-18", "v"),
    ]
    path = tmp_path / "blind.csv"
    blind_review.write_results(results, path)
    loaded = blind_review.load_results(path)
    assert loaded[("ING Group", "controversy")]["quote_page"] is None and loaded[("ING Group", "labor_rights")]["quote_page"] == 139
    anchored = {k: {"category_agrees": True} for k in loaded}
    text = blind_review.report(loaded, anchored, evidence)
    assert "| Blind AI category = analysts' category | 1 of 3 |" in text
    assert "| ING Group | Labour rights | `medium` | `weak` | lower | yes (p. 139) |" in text
    assert "| ING Group | Controversy | `moderate` | `none` | higher | no |" in text  # no deduction is better
    assert ing["climate_plan"].category == "sbt_aligned" and "Climate transition plan" not in text


def test_saved_blind_review_covers_every_row_with_valid_categories(evidence):
    saved = blind_review.load_results()
    if not saved:
        pytest.skip("blind review not run yet")
    assert set(saved) == {(r.bank, r.indicator) for r in evidence.rows}
    for (bank, key), r in saved.items():
        assert r["analyst_category"] == evidence.for_bank(bank)[key].category  # matches the current evidence
        assert r["ai_category"] in allowed_categories(key) or r["problems"]
        assert r["prompt_version"] == blind_review.PROMPT_VERSION
    report = blind_review.report(saved, load_reviews(), evidence)
    assert blind_review.BLIND_REPORT_PATH.read_text(encoding="utf-8") == report  # regenerated with the data


def test_server_uses_the_blind_review_for_the_ai_reviewer_score(tmp_path):
    from server import Server

    without_blind = Server(use_llm=False, blind_review_path=tmp_path / "none.csv")
    assert "shown the analysts' category" in without_blind.ai_reviewer_note()
    anchored = without_blind.ai_reviewer_categories()
    assert anchored["Rabobank"]["board_independence"] == without_blind.reviews[("Rabobank", "board_independence")]["ai_suggested_category"]

    saved = blind_review.load_results()
    if not saved:
        pytest.skip("blind review not run yet")
    server = Server(use_llm=False)
    assert "blind" in server.ai_reviewer_note() and server.chat.reviewer_note == server.ai_reviewer_note()
    categories = server.ai_reviewer_categories()
    for (bank, key), r in saved.items():
        if r["ai_category"] in allowed_categories(key):
            assert categories[bank][key] == r["ai_category"]

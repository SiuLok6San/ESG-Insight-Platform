"""End-to-end smoke tests with the LLM disabled and no network access."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.helpers import BANKS, server_with_stub
from tools.score_engine import RUBRIC

APP = str(Path(__file__).resolve().parent.parent / "app_v2.py")


def test_backend_runs_end_to_end_without_llm(offline_server):
    assert offline_server.banks() == BANKS
    for bank in BANKS:
        result = offline_server.score_bank(bank)
        assert len(result["breakdown"]) == len(RUBRIC)
        for item in result["breakdown"]:
            assert item["page_url"].startswith("https://") and f"#page={item['page']}" in item["page_url"]
        scores = result["scores"]
        assert set(scores["pillars"]) == {"E", "S", "G"}
        assert scores["label"] in {"Meet", "Almost Meet", "Not Meet"}

    comparison = offline_server.compare_banks(BANKS)
    assert comparison["errors"] == {}
    assert sorted(comparison["ranking"]) == sorted(BANKS)

    report = offline_server.sensitivity(comparison["ranking"])
    assert len(report["weight_results"]) == 121
    assert report["summary"]


def test_unknown_bank_is_reported_not_scored(offline_server):
    comparison = offline_server.compare_banks(["ING Group", "Unknown Bank"])
    assert list(comparison["per_bank_results"]) == ["ING Group"]
    assert "Unknown Bank" in comparison["errors"]


def test_streamlit_compare_page_renders():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Dutch bank ESG benchmark" in t.value for t in at.title)
    headers = [m.value for m in at.markdown]
    assert any("Robustness" in h for h in headers)
    assert not any("Monte-Carlo" in h for h in headers)


def test_streamlit_single_bank_page_renders():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.segmented_control[0].set_value("Bank detail").run()
    assert not at.exception
    assert at.selectbox[0].value == BANKS[0]
    text = "\n".join(m.value for m in at.markdown)
    assert "Climate transition plan" in text and "#page=" in text
    assert any(e.label.startswith("Verbatim quotes from the report") for e in at.expander)
    assert '"For 2025, our GAR based on Turnover is 14 percent (2024: 7 percent)." ([p. 131]' in text


def test_server_cache_is_bounded(monkeypatch):
    import server as server_module

    monkeypatch.setattr(server_module, "MAX_CACHE_ENTRIES", 3)
    server, _ = server_with_stub()
    for i in range(5):
        list(server.stream_answer(server.chat_turn(f"question {i}")))
    assert len(server.cache) == 3
    assert server.chat_turn("question 4").from_cache


def test_streamlit_shows_engine_deduction():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.segmented_control[0].set_value("Bank detail").run()
    text = "\n".join(m.value for m in at.markdown)
    assert "**Controversy - moderate (−2 points)**" in text
    assert "p. None" not in text


def test_method_and_data_page_shows_the_evidence_and_the_checks():
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["section"] = "method"  # deep link, e.g. ?section=method
    at.run()
    assert not at.exception
    assert at.segmented_control[0].value == "Method & data"
    assert len(at.dataframe[0].value) == 45  # 3 banks x (14 indicators + controversy)
    text = "\n".join(m.value for m in at.markdown)
    assert "88 of 88 excerpts found" in text
    assert "**Same category as the analysts:** 43 of 45" in text
    assert at.get("download_button")


def test_navigation_is_at_the_top_and_updates_the_link():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert at.segmented_control[0].value == "Compare"  # without an LLM the benchmark comes first
    at.segmented_control[0].set_value("Bank detail").run()
    assert at.query_params["section"] == ["bank"] or at.query_params["section"] == "bank"
    assert not at.sidebar.radio  # no navigation hidden in the sidebar

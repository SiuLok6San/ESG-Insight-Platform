"""End-to-end smoke tests with the LLM disabled and no network access."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.helpers import BANKS
from tools.score_engine import RUBRIC

APP = str(Path(__file__).resolve().parent.parent / "app_v2.py")


def test_backend_runs_end_to_end_without_llm(offline_server):
    assert offline_server.banks() == BANKS
    for bank in BANKS:
        result = offline_server.analyze_bank(bank)
        assert result["ok"] and result["bank"] == bank
        assert result["assistant"] == {"enabled": False}
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
    at.sidebar.radio[0].set_value("Single bank").run()
    assert not at.exception
    assert at.selectbox[0].value == BANKS[0]
    text = "\n".join(m.value for m in at.markdown)
    assert "Climate transition plan" in text and "#page=" in text


def test_server_cache_is_bounded(offline_server, monkeypatch):
    import server as server_module

    monkeypatch.setattr(server_module, "MAX_CACHE_ENTRIES", 3)
    for i in range(5):
        offline_server.analyze_bank("ING Group", question=f"question {i}")
    assert len(offline_server.cache) == 3
    assert offline_server.analyze_bank("ING Group", question="question 4")["ok"]


def test_streamlit_shows_engine_deduction():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.radio[0].set_value("Single bank").run()
    text = "\n".join(m.value for m in at.markdown)
    assert "**Controversy - moderate (−2 points)**" in text
    assert "p. None" not in text


def test_code_fingerprint_changes_with_code_or_data(tmp_path):
    from server import code_fingerprint

    code, data = tmp_path / "server.py", tmp_path / "ai_review.csv"
    code.write_text("v1")
    data.write_text("a,b")
    first = code_fingerprint([code, data])
    assert code_fingerprint([code, data]) == first  # stable
    data.write_text("a,b,c")
    second = code_fingerprint([code, data])
    code.write_text("v2")
    assert len({first, second, code_fingerprint([code, data])}) == 3
    assert code_fingerprint() == code_fingerprint()  # real repo files

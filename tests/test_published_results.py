"""The README quotes these numbers. If the evidence table changes and this
test fails, update the Results section of README.md to match."""

from tests.helpers import BANKS


def test_published_scores(offline_server):
    comparison = offline_server.compare_banks(BANKS)
    table = {
        bank: (
            r["scores"]["pillars"]["E"],
            r["scores"]["pillars"]["S"],
            r["scores"]["pillars"]["G"],
            r["scores"]["controversy"],
            r["scores"]["final"],
            r["scores"]["label"],
        )
        for bank, r in comparison["per_bank_results"].items()
    }
    assert table == {
        "ING Group": (84.3, 70.0, 75.0, "moderate", 74.7, "Almost Meet"),
        "Rabobank": (82.3, 70.0, 70.0, "moderate", 72.3, "Almost Meet"),
        "ABN AMRO": (79.3, 71.3, 70.0, "severe", 68.6, "Almost Meet"),
    }
    assert comparison["ranking"] == ["ING Group", "Rabobank", "ABN AMRO"]


def test_published_robustness(offline_server):
    report = offline_server.sensitivity(["ING Group", "Rabobank", "ABN AMRO"])
    assert report["weight_unchanged_count"] == 121 and len(report["weight_results"]) == 121
    assert len(report["moves"]) == 63
    ranking_moves = [m for m in report["moves"] if m["changes_ranking"]]
    assert [(m["bank"], m["indicator"], m["to_category"]) for m in ranking_moves] == [
        ("ING Group", "controversy", "severe")
    ]
    assert report["label_flips_by_weight"] == {"ING Group": 47, "Rabobank": 0, "ABN AMRO": 0}
    assert sum(m["changes_label"] for m in report["moves"]) == 7


def test_published_ai_review(offline_server):
    summary = offline_server.ai_review_summary()
    assert summary["rows"] == 45
    assert summary["verdicts"] == {"supports": 32, "partially_supports": 13, "does_not_support": 0}
    assert summary["category_agrees"] == 39
    assert summary["quote_verified"] == 42
    assert summary["models"] == ["ollama-cloud/gemma4:31b"]
    assert len(summary["disagreements"]) == 17

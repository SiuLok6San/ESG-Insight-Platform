import json
from pathlib import Path

from server import Server
from tests.helpers import BANKS, StubLLM

ROOT = Path(__file__).resolve().parent.parent


def test_comparison_is_identical_across_runs_without_llm():
    runs = [
        json.dumps(Server(use_llm=False, fetch_external=False).compare_banks(BANKS), sort_keys=True)
        for _ in range(2)
    ]
    assert runs[0] == runs[1]


def test_scores_identical_with_and_without_llm(offline_server):
    without_llm = {bank: offline_server.score_bank(bank) for bank in BANKS}

    with_llm = Server(use_llm=False, fetch_external=False)
    stub = StubLLM()
    with_llm.use_llm = True
    for agent in (with_llm.news_agent, with_llm.esg_agent, with_llm.writer, with_llm.pdf_summarizer):
        agent.llm = stub

    for bank in BANKS:
        result = with_llm.analyze_bank(bank, pdf_text="Annual report text.")
        assert result["assistant"]["enabled"] and result["assistant"]["error"] is None
        scored = {k: result[k] for k in ("scores", "breakdown", "controversy_evidence", "draft_indicators")}
        assert scored == without_llm[bank]
    assert stub.calls > 0


def test_no_randomness_in_scoring_path():
    for module in ("tools/score_engine.py", "tools/evidence.py", "tools/sensitivity.py", "server.py"):
        source = (ROOT / module).read_text()
        assert "import random" not in source and "random." not in source, module
        assert "time.time" not in source, module


def test_llm_requests_are_deterministic():
    source = (ROOT / "tools/local_llm.py").read_text()
    assert "random" not in source
    assert "temperature: float = 0.0" in source

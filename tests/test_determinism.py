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
    for module in ("tools/local_llm.py", "tools/llm_provider.py"):
        assert "random" not in (ROOT / module).read_text(), module
    provider = (ROOT / "tools/llm_provider.py").read_text()
    assert provider.count('"temperature": 0,') == 2  # both chat_json and chat_text


def test_ai_estimate_is_separate_from_the_official_score(offline_server):
    server = Server(use_llm=False, fetch_external=False)
    stub = StubLLM()  # suggests climate_plan=weak and fossil_policy=exit for every bank
    server.use_llm = True
    for agent in (server.news_agent, server.esg_agent, server.writer, server.pdf_summarizer):
        agent.llm = stub

    result = server.analyze_bank("ING Group", question="How credible is the climate plan?")
    official = offline_server.score_bank("ING Group")["scores"]
    estimate = result["assistant"]["ai_estimate"]

    assert result["scores"] == official  # the official score never changes
    changed = {c["indicator"]: (c["evidence_category"], c["ai_category"]) for c in estimate["changed"]}
    assert changed == {"climate_plan": ("sbt_aligned", "weak"), "fossil_policy": ("strong", "exit")}
    expected = server.engine.score(
        {**server.evidence.categories("ING Group"), "climate_plan": "weak", "fossil_policy": "exit"}
    )
    assert estimate["scores"]["final"] == expected.final
    assert estimate["scores"]["final"] != official["final"]
    assert len(estimate["kept_from_evidence"]) == 13  # indicators the stub did not classify
    assert "Climate transition plan (climate_plan): analyst category `sbt_aligned`" in stub_prompt(stub)


def stub_prompt(stub):
    return stub.last_prompt

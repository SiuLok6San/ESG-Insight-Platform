import json
from pathlib import Path

from server import Server
from tests.helpers import BANKS, server_with_stub

ROOT = Path(__file__).resolve().parent.parent


def test_comparison_is_identical_across_runs_without_llm():
    runs = [json.dumps(Server(use_llm=False).compare_banks(BANKS), sort_keys=True) for _ in range(2)]
    assert runs[0] == runs[1]


def test_scores_identical_with_and_without_llm(offline_server):
    without_llm = {bank: offline_server.score_bank(bank) for bank in BANKS}
    what_if = {"banks": ["ABN AMRO"], "indicators": [], "intent": "what_if", "scenario": {"ABN AMRO": {"exec_comp_esg": ">=20"}}}
    server, stub = server_with_stub()
    for question in ("Which bank is strongest?", "What if ABN AMRO linked pay to ESG?"):
        stub.route = what_if if "What if" in question else None
        list(server.stream_answer(server.chat_turn(question)))
    server.write_report("ING Group")
    assert {bank: server.score_bank(bank) for bank in BANKS} == without_llm
    assert stub.calls == ["answer", "route", "answer", "report"]  # only the what-if question is routed by the LLM


def test_no_randomness_in_scoring_path():
    for module in ("tools/score_engine.py", "tools/evidence.py", "tools/sensitivity.py", "server.py", "agents/chat_agent.py"):
        source = (ROOT / module).read_text()
        assert "import random" not in source and "random." not in source, module
        assert "time.time" not in source, module


def test_llm_requests_are_deterministic():
    for module in ("tools/local_llm.py", "tools/llm_provider.py"):
        assert "random" not in (ROOT / module).read_text(), module
    provider = (ROOT / "tools/llm_provider.py").read_text()
    assert provider.count('"temperature": 0,') == 3  # chat_json, chat_text and chat_stream

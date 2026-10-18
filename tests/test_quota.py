from datetime import date, timedelta

import pytest

from server import Server
from tools.local_llm import LLMUnavailable
from tools.quota import DailyLimitReached, DailyQuota


class Clock:
    def __init__(self) -> None:
        self.day = date(2026, 10, 18)

    def __call__(self) -> date:
        return self.day


class RecordingLLM:
    """Stub LLM that records which agent called it."""

    def __init__(self) -> None:
        self.kinds = []

    def ask(self, prompt: str) -> str:
        if "single JSON object" in prompt:
            self.kinds.append("answer")
            return 'Answer citing p. 111.\n{"climate_plan": "weak"}'
        if "ESG reporting specialist" in prompt:
            self.kinds.append("report")
            return "## Stub narrative report"
        self.kinds.append("other")
        return "- news bullet"


def server_with_stub(limit: int) -> tuple:
    server = Server(use_llm=False, fetch_external=False, daily_ai_limit=limit)
    llm = RecordingLLM()
    server.use_llm = True
    for agent in (server.news_agent, server.esg_agent, server.writer, server.pdf_summarizer):
        agent.llm = llm
    return server, llm


def test_quota_allows_up_to_the_limit_per_day():
    clock = Clock()
    quota = DailyQuota(2, today=clock)
    assert quota.remaining() == 2
    assert quota.try_consume() and quota.try_consume()
    assert not quota.try_consume()
    assert quota.remaining() == 0
    clock.day += timedelta(days=1)  # midnight UTC
    assert quota.remaining() == 2


def test_zero_limit_blocks_and_negative_limit_is_rejected():
    assert not DailyQuota(0).try_consume()
    with pytest.raises(ValueError):
        DailyQuota(-1)


def test_daily_limit_defaults_to_environment(monkeypatch):
    monkeypatch.setenv("AI_QUESTIONS_PER_DAY", "7")
    assert Server(use_llm=False, fetch_external=False).ai_requests_left_today() == 7
    monkeypatch.delenv("AI_QUESTIONS_PER_DAY")
    assert Server(use_llm=False, fetch_external=False).ai_requests_left_today() == 50


def test_question_does_not_write_the_report():
    server, llm = server_with_stub(limit=5)
    result = server.analyze_bank("ING Group", question="How credible is the climate plan?")
    assert "report" not in result["assistant"]
    assert llm.kinds == ["answer"]  # no news without network, and no report
    assert server.ai_requests_left_today() == 4


def test_cached_question_uses_no_request_even_after_the_limit():
    server, llm = server_with_stub(limit=1)
    first = server.analyze_bank("ING Group", question="Q1")
    assert server.has_cached_analysis("ING Group", question="Q1")
    assert server.analyze_bank("ING Group", question="Q1") == first
    assert server.ai_requests_left_today() == 0
    with pytest.raises(DailyLimitReached):
        server.analyze_bank("ING Group", question="Q2")
    assert llm.kinds == ["answer"]


def test_report_is_written_on_request_and_cached():
    server, llm = server_with_stub(limit=2)
    assert not server.has_cached_report("ING Group", "news")
    report = server.write_report("ING Group", "news")
    assert report == "## Stub narrative report"
    assert server.write_report("ING Group", "news") == report
    assert llm.kinds == ["report"]
    assert server.ai_requests_left_today() == 1


def test_report_respects_the_daily_limit_and_the_llm_switch():
    server, _ = server_with_stub(limit=0)
    with pytest.raises(DailyLimitReached):
        server.write_report("ING Group")
    offline = Server(use_llm=False, fetch_external=False)
    with pytest.raises(LLMUnavailable):
        offline.write_report("ING Group")


def test_analysis_without_llm_never_uses_the_quota():
    server = Server(use_llm=False, fetch_external=False, daily_ai_limit=0)
    assert server.analyze_bank("ING Group")["assistant"] == {"enabled": False}

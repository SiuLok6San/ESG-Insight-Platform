from datetime import date, timedelta

import pytest

from server import Server
from tests.helpers import StubLLM, server_with_stub
from tools.local_llm import LLMBusy, LLMUnavailable
from tools.quota import DailyLimitReached, DailyQuota


class Clock:
    def __init__(self) -> None:
        self.day = date(2026, 10, 18)

    def __call__(self) -> date:
        return self.day


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
    assert Server(use_llm=False).ai_requests_left_today() == 7
    monkeypatch.delenv("AI_QUESTIONS_PER_DAY")
    assert Server(use_llm=False).ai_requests_left_today() == 50


def ask(server, question, history=()):
    turn = server.chat_turn(question, history)
    return turn, "".join(server.stream_answer(turn))


def test_a_question_uses_one_request_and_a_repeat_uses_none():
    server, stub = server_with_stub(daily_ai_limit=1)
    first, answer = ask(server, "Which bank is strongest?")
    assert not first.from_cache and server.ai_requests_left_today() == 0
    again, answer_again = ask(server, "  which bank is STRONGEST?")  # same question, different spacing and case
    assert again.from_cache and answer_again == answer
    assert stub.calls == ["route", "answer"]
    with pytest.raises(DailyLimitReached):
        server.chat_turn("Another question")


def test_report_is_written_on_request_and_cached():
    server, stub = server_with_stub(daily_ai_limit=2)
    assert not server.has_cached_report("ING Group")
    report = server.write_report("ING Group")
    assert report == "## Stub narrative report" and server.write_report("ING Group") == report
    assert stub.calls == ["report"] and server.ai_requests_left_today() == 1


def test_assistant_respects_the_daily_limit_and_the_llm_switch():
    server, _ = server_with_stub(daily_ai_limit=0)
    with pytest.raises(DailyLimitReached):
        server.write_report("ING Group")
    offline = Server(use_llm=False)
    for call in (lambda: offline.write_report("ING Group"), lambda: offline.chat_turn("Q")):
        with pytest.raises(LLMUnavailable):
            call()
    assert offline.ai_requests_left_today() == 50


def test_refund_gives_back_one_request():
    quota = DailyQuota(1, today=Clock())
    assert quota.try_consume() and quota.remaining() == 0
    quota.refund()
    assert quota.remaining() == 1
    quota.refund()
    assert quota.remaining() == 1  # never above the limit


class BusyAfterRouting(StubLLM):
    def stream(self, messages):
        yield "Partial "
        raise LLMBusy("ollama-cloud is busy or not responding (HTTP 429)")


def test_busy_service_refunds_the_request_and_caches_nothing():
    server, _ = server_with_stub(BusyAfterRouting(), daily_ai_limit=2)
    turn = server.chat_turn("Which bank is strongest?")
    with pytest.raises(LLMBusy):
        list(server.stream_answer(turn))
    assert server.ai_requests_left_today() == 2 and not server.chat_turn("Which bank is strongest?").from_cache


def test_busy_router_stops_before_the_answer_call():
    class BusyRouter(StubLLM):
        def ask_json(self, system, user):
            raise LLMBusy("busy")

    server, stub = server_with_stub(BusyRouter(), daily_ai_limit=2)
    with pytest.raises(LLMBusy):
        server.chat_turn("Which bank is strongest?")
    assert server.ai_requests_left_today() == 2 and stub.calls == []

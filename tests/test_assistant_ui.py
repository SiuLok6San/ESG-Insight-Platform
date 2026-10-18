"""UI tests for the "Ask the AI assistant" flow, with a stub LLM and no network."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from tests.test_quota import RecordingLLM
from tools.free_news import FreeNewsClient
from tools.local_llm import LocalLLM
from tools.yahoo_client import YahooFinanceClient

APP = str(Path(__file__).resolve().parent.parent / "app_v2.py")
NEWS_ITEM = {"title": "Bank publishes climate plan", "link": "https://example.com", "source": "Example"}


@pytest.fixture
def llm(monkeypatch):
    stub = RecordingLLM()
    monkeypatch.setattr(LocalLLM, "is_available", lambda self: True)
    monkeypatch.setattr(LocalLLM, "ask", lambda self, prompt: stub.ask(prompt))
    monkeypatch.setattr(FreeNewsClient, "search", lambda self, bank, limit=10: [NEWS_ITEM])
    monkeypatch.setattr(YahooFinanceClient, "lookup_and_snapshot", lambda self, bank: "")
    st.cache_resource.clear()  # a fresh Server (and daily count) for each test
    yield stub
    st.cache_resource.clear()


def open_single_bank() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.radio[0].set_value("Single bank").run()
    return at


def button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def ask(at: AppTest, question: str) -> AppTest:
    at.text_area(key="question_ING Group").input(question).run()
    button(at, "Ask").click().run()
    assert not at.exception
    return at


def captions(at: AppTest) -> str:
    return "\n".join(c.value for c in at.caption)


def test_answer_and_ai_estimate_are_shown_without_writing_the_report(llm):
    at = ask(open_single_bank(), "How credible is the climate plan?")
    assert any(m.value.startswith("**AI answer**") for m in at.markdown)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Official score (evidence)"] == "74.7"
    assert "AI estimate (not official)" in metrics
    labels = [m.value for m in at.markdown if m.value.startswith("Compliance label: official")]
    assert labels and "**Almost Meet**" in labels[0]  # full label, not a truncated metric value
    assert llm.kinds.count("answer") == 1 and "report" not in llm.kinds
    assert "Questions left in this session: 4 of 5" in captions(at)
    assert "AI requests left today for the whole site: 49 of 50" in captions(at)
    assert button(at, "Write an AI narrative report")


def test_report_is_written_only_on_request(llm):
    at = ask(open_single_bank(), "How credible is the climate plan?")
    button(at, "Write an AI narrative report").click().run()
    assert not at.exception
    assert llm.kinds.count("report") == 1
    assert any(e.label == "AI narrative report (not used in score)" for e in at.expander)
    assert any("Stub narrative report" in m.value for m in at.markdown)
    assert "AI requests left today for the whole site: 48 of 50" in captions(at)


def test_repeated_question_is_not_counted(llm):
    at = ask(open_single_bank(), "Same question")
    ask(at, "Same question")
    assert llm.kinds.count("answer") == 1
    assert "Questions left in this session: 4 of 5" in captions(at)
    assert "AI requests left today for the whole site: 49 of 50" in captions(at)


def test_session_limit_disables_ask(llm, monkeypatch):
    monkeypatch.setenv("AI_QUESTIONS_PER_SESSION", "1")
    at = ask(open_single_bank(), "First question")
    assert button(at, "Ask").disabled
    assert any("1 AI questions per visit" in i.value for i in at.info)


def test_daily_limit_is_shared_by_all_visitors(llm, monkeypatch):
    monkeypatch.setenv("AI_QUESTIONS_PER_DAY", "1")
    ask(open_single_bank(), "First visitor's question")

    second_visitor = open_single_bank()
    assert button(second_visitor, "Ask").disabled
    assert any("used its 1 AI requests for today" in i.value for i in second_visitor.info)
    assert llm.kinds.count("answer") == 1

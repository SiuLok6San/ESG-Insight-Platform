"""UI tests for the "Ask the AI" chat page, with a stub LLM and no network."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from tests.helpers import StubLLM
from tools.local_llm import LocalLLM

APP = str(Path(__file__).resolve().parent.parent / "app_v2.py")
WHAT_IF = {"banks": ["ABN AMRO"], "indicators": ["exec_comp_esg"], "intent": "what_if", "scenario": {"ABN AMRO": {"exec_comp_esg": ">=20"}}}


def route_for(question: str) -> dict:
    if "20%" in question:
        return WHAT_IF
    return {"banks": [], "indicators": [], "intent": "compare", "scenario": {}}


@pytest.fixture
def llm(monkeypatch):
    stub = StubLLM(route=route_for, answer="ING Group leads on climate (ING Group, p. 111).")
    monkeypatch.setattr(LocalLLM, "is_available", lambda self: True)
    monkeypatch.setattr(LocalLLM, "ask_json", lambda self, system, user: stub.ask_json(system, user))
    monkeypatch.setattr(LocalLLM, "stream", lambda self, messages: stub.stream(messages))
    monkeypatch.setattr(LocalLLM, "ask", lambda self, prompt: stub.ask(prompt))
    st.cache_resource.clear()  # a fresh Server (and daily count) for each test
    yield stub
    st.cache_resource.clear()


def open_chat() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert at.segmented_control[0].value == "Ask"  # the chat is the first page when the AI is available
    return at


def ask(at: AppTest, question: str) -> AppTest:
    at.chat_input[0].set_value(question).run()
    assert not at.exception
    return at


def text(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def captions(at: AppTest) -> str:
    return "\n".join(c.value for c in at.caption)


def test_question_gets_an_answer_and_a_score_card(llm):
    at = ask(open_chat(), "Which bank is strongest on climate?")
    page = text(at)
    assert "ING Group leads on climate (ING Group, p. 111)." in page
    assert "| ING Group | **74.7** · Almost Meet |" in page  # official score from the engine
    assert "| Bank | Official score | AI reviewer score |\n" in page  # no scenario column without a what-if
    assert "Questions left in this session: 4 of 5" in captions(at)
    assert "AI requests left today for the whole site: 49 of 50" in captions(at)
    assert llm.calls == ["route", "answer"]


def test_example_button_asks_a_what_if_question(llm):
    at = open_chat()
    next(b for b in at.button if "20% of executive pay" in b.label).click().run()
    assert not at.exception
    page = text(at)
    assert "Scenario score" in page and "| ABN AMRO | **68.6** · Almost Meet |" in page
    assert "Scenario for ABN AMRO: ESG-linked executive pay `none` → `>=20`." in page
    assert any(e.label == "Evidence behind this answer (verbatim quotes)" for e in at.expander)


def test_a_question_asked_before_is_answered_from_the_cache_and_not_counted(llm):
    ask(open_chat(), "Same question")
    second_visitor = ask(open_chat(), "Same question")
    assert llm.calls == ["route", "answer"]  # the second visitor's answer came from the cache
    assert "Questions left in this session: 5 of 5" in captions(second_visitor)
    assert "AI requests left today for the whole site: 49 of 50" in captions(second_visitor)


def test_citation_outside_the_evidence_is_flagged(llm):
    llm.answer_text = "Something (ABN AMRO, p. 999)."
    at = ask(open_chat(), "Tell me something")
    assert any("not in the evidence it was given: ABN AMRO, p. 999" in w.value for w in at.warning)


def test_session_limit_disables_the_chat(llm, monkeypatch):
    monkeypatch.setenv("AI_QUESTIONS_PER_SESSION", "1")
    at = ask(open_chat(), "First question")
    assert at.chat_input[0].disabled
    assert any("1 AI questions per visit" in i.value for i in at.info)


def test_daily_limit_is_shared_by_all_visitors(llm, monkeypatch):
    monkeypatch.setenv("AI_QUESTIONS_PER_DAY", "1")
    ask(open_chat(), "First visitor's question")
    second_visitor = open_chat()
    assert second_visitor.chat_input[0].disabled
    assert any("used its 1 AI requests for today" in i.value for i in second_visitor.info)


def test_without_llm_the_chat_explains_and_compare_is_first():
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert at.segmented_control[0].value == "Compare"
    at.segmented_control[0].set_value("Ask").run()
    assert any("The AI assistant is off" in i.value for i in at.info)
    st.cache_resource.clear()


def test_busy_service_shows_a_message_and_does_not_count(llm, monkeypatch):
    from tools.local_llm import LLMBusy

    def busy(self, system, user):
        raise LLMBusy("ollama-cloud is busy or not responding (HTTP 429)")

    monkeypatch.setattr(LocalLLM, "ask_json", busy)
    at = ask(open_chat(), "Which bank is strongest?")
    assert any("The free AI service is busy right now" in w.value for w in at.warning)
    assert "Questions left in this session: 5 of 5" in captions(at)
    assert "AI requests left today for the whole site: 50 of 50" in captions(at)


def test_number_outside_the_evidence_is_flagged(llm):
    llm.answer_text = "ING Group scores 99.9 overall."
    at = ask(open_chat(), "How does ING score?")
    assert any("mentions numbers that are not in the scores or evidence it was given: 99.9" in w.value for w in at.warning)

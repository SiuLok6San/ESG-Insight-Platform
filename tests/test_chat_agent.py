"""The chat assistant's routing, scores and citation check, with a stub LLM."""

import pytest

from agents.chat_agent import ChatAgent, Route
from tests.helpers import StubLLM, server_with_stub


@pytest.fixture
def agent():
    server, _ = server_with_stub()
    return server.chat


def test_route_keeps_only_rubric_values(agent):
    raw = {
        "banks": ["ABN", "Triodos"],
        "indicators": ["exec_comp_esg", "made_up"],
        "intent": "what_if",
        "scenario": {
            "ABN AMRO": {"exec_comp_esg": ">=20", "fossil_policy": "excellent", "aml_maturity": "not_disclosed"},
            "Rabobank": {"climate_plan": "sbt_aligned"},
        },
    }
    route = agent.validate_route(raw, "What if ABN AMRO linked 20% of pay to ESG?")
    assert route.banks == ["ABN AMRO", "Rabobank"]  # a bank with a scenario is always in scope
    assert route.indicators == ["exec_comp_esg"]
    assert route.scenario == {"ABN AMRO": {"exec_comp_esg": ">=20"}, "Rabobank": {"climate_plan": "sbt_aligned"}}
    assert len(route.rejected) == 4  # Triodos, made_up, excellent, not_disclosed


def test_unknown_intent_and_failed_routing_fall_back_to_bank_names(agent):
    assert agent.validate_route({"intent": "chit-chat"}, "How does Rabobank do?").intent == "other"

    class Broken(StubLLM):
        def ask_json(self, system, user):
            raise RuntimeError("model down")

    agent.llm = Broken()
    route = agent.route("And ING?", history=[("Tell me about ABN AMRO", "...")])
    assert route.banks == ["ING Group"] and route.rejected == ["routing failed: model down"]
    follow_up = agent.route("What about its controversy?", history=[("Tell me about ABN AMRO", "...")])
    assert follow_up.banks == ["ABN AMRO"]  # taken from the previous question


def test_scores_come_from_the_engine_not_the_model(agent):
    route = Route(banks=["ABN AMRO"], indicators=[], intent="what_if", scenario={"ABN AMRO": {"exec_comp_esg": ">=20"}})
    ctx = agent.context(route)
    card = ctx.cards[0]
    cats = agent.evidence.categories("ABN AMRO")
    assert card.official.final == agent.engine.score(cats).final == 68.6
    assert card.scenario.final == agent.engine.score({**cats, "exec_comp_esg": ">=20"}).final
    assert card.scenario_changes == [("exec_comp_esg", "none", ">=20")]
    reviewer = {**cats, **agent.ai_reviewer_categories["ABN AMRO"]}
    assert card.ai_reviewer.final == agent.engine.score(reviewer).final
    assert {k for k, _, _ in card.ai_reviewer_differs} == {k for k in reviewer if reviewer[k] != cats[k]}
    facts = agent.facts(ctx)
    assert f"Scenario score {card.scenario.final:.1f}" in facts and "official 68.6" in facts
    assert "ESG-linked executive pay (exec_comp_esg)" in ctx.evidence_text  # the scenario's indicator is shown


def test_a_scenario_that_changes_the_ranking_is_reported(agent):
    route = Route(banks=["ABN AMRO"], indicators=[], intent="what_if",
                  scenario={"ABN AMRO": {"exec_comp_esg": ">=20", "fossil_policy": "exit"}})
    ctx = agent.context(route)
    assert ctx.ranking == ["ING Group", "Rabobank", "ABN AMRO"]
    assert ctx.scenario_ranking == ["ING Group", "ABN AMRO", "Rabobank"]


def test_question_about_all_banks_gets_one_quote_per_row(agent):
    ctx = agent.context(Route(banks=[], indicators=[], intent="compare"))
    assert [c.bank for c in ctx.cards] == ["ING Group", "ABN AMRO", "Rabobank"]
    assert ctx.evidence_text.count("\n") + 1 == 45


def test_answer_prompt_has_rules_history_and_facts(agent):
    ctx = agent.context(Route(banks=["ING Group"], indicators=["climate_plan"], intent="explain"))
    history = [(f"q{i}", f"a{i}") for i in range(4)]
    messages = agent.messages("Why?", history, ctx)
    assert "Never compute or estimate a score" in messages[0]["content"]
    assert [m["content"] for m in messages[1:5]] == ["q2", "a2", "q3", "a3"]  # only the last two turns
    assert "SBTi" in messages[-1]["content"] and messages[-1]["content"].endswith("QUESTION: Why?")


def test_citations_outside_the_evidence_are_flagged(agent):
    ctx = agent.context(Route(banks=["ING Group"], indicators=["climate_plan"], intent="explain"))
    ok = "Targets were validated (ING Group, p. 111)."
    assert ChatAgent.unknown_citations(ok, ctx) == []
    assert ChatAgent.unknown_citations("See (ING Group, p. 999) and (p. 5).", ctx) == ["ING Group, p. 999", "p. 5"]


def test_server_flags_bad_citations_after_streaming():
    server, stub = server_with_stub(StubLLM(answer="It is fine (ING Group, p. 999)."))
    turn = server.chat_turn("Tell me about ING")
    assert "".join(server.stream_answer(turn)) == "It is fine (ING Group, p. 999)."
    assert turn.unknown_citations == ["ING Group, p. 999"]


def test_question_about_no_bank_in_particular_covers_all_banks(agent):
    history = [("What would ABN AMRO score with a coal exit?", "...")]
    route = agent.validate_route({"banks": [], "intent": "compare"}, "Which bank is strongest on climate?", history)
    assert route.banks == []  # all banks, not the bank from the previous question
    assert [c.bank for c in agent.context(route).cards] == ["ING Group", "ABN AMRO", "Rabobank"]
    assert agent.validate_route({"banks": []}, "How does Rabobank do?").banks == ["Rabobank"]


def test_facts_round_pillars_like_the_rest_of_the_app(agent, offline_server):
    ctx = agent.context(Route(banks=["ING Group"], indicators=[], intent="explain"))
    shown = offline_server.score_bank("ING Group")["scores"]["pillars"]
    assert shown["E"] == 84.3 and "E 84.3," in agent.facts(ctx)  # same rounding as the page

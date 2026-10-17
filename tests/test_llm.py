from unittest import mock

import pytest

from agents.esg_agent import ESGAgent
from tests.helpers import StubLLM
from tools.local_llm import LLMUnavailable, LocalLLM, LocalLLMConfig


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": "answer"}


def test_llm_uses_fixed_seed_and_caches_by_input(tmp_path):
    posts = []
    llm = LocalLLM(LocalLLMConfig(enabled=True, cache_dir=tmp_path))
    llm._available = True
    with mock.patch("tools.local_llm.requests.post", side_effect=lambda url, json, timeout: posts.append(json) or FakeResponse()):
        assert llm.ask("prompt") == "answer"
        assert llm.ask("prompt") == "answer"  # served from cache
        llm.ask("another prompt")
    assert len(posts) == 2
    assert posts[0]["options"]["temperature"] == 0.0
    assert posts[0]["options"]["seed"] == 42
    assert posts[0]["prompt"] == "prompt"  # no entropy appended to the prompt


def test_disabled_llm_raises_without_network(tmp_path):
    llm = LocalLLM(LocalLLMConfig(enabled=False, cache_dir=tmp_path))
    with mock.patch("tools.local_llm.requests.get") as get, pytest.raises(LLMUnavailable):
        llm.ask("prompt")
    get.assert_not_called()


def test_env_settings_are_read_after_dotenv(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "7")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    config = LocalLLM().config
    assert (config.timeout, config.model) == (7, "test-model")


def test_esg_agent_returns_only_valid_suggestions():
    result = ESGAgent(StubLLM()).run(bank="ING Group", question=None, context_blob="context")
    assert result["suggestions"] == {"climate_plan": "weak", "fossil_policy": "exit"}
    assert result["rejected"] == {"aml_maturity": "excellent", "made_up_key": "x"}
    assert result["analysis_text"] == "Narrative analysis."


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('text {"climate_plan": "weak"}', {"climate_plan": "weak"}),
        ('text {"a": {"b": 1}} end', {"a": {"b": 1}}),
        ("no json here", {}),
        ('broken {"climate_plan": ', {}),
    ],
)
def test_json_extraction(raw, expected):
    _, parsed = ESGAgent._split_analysis_and_json(raw)
    assert parsed == expected

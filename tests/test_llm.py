from unittest import mock

import pytest

from tools.local_llm import LLMUnavailable, LocalLLM, LocalLLMConfig


class FakeResponse:
    status_code = 200
    headers = {}
    text = ""

    def json(self):
        return {"choices": [{"message": {"content": "answer"}}]}


def test_cloud_is_used_when_the_key_is_set_and_calls_are_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key-not-real")
    posts = []
    llm = LocalLLM(LocalLLMConfig(enabled=True, provider="auto", cache_dir=tmp_path))
    assert llm.describe() == "ollama-cloud/gemma4:31b"
    assert llm.is_available()  # a hosted provider only needs its key; no network probe
    with mock.patch(
        "tools.llm_provider.requests.post",
        side_effect=lambda url, json, headers, timeout: posts.append((url, json)) or FakeResponse(),
    ):
        assert llm.ask("prompt") == "answer"
        assert llm.ask("prompt") == "answer"  # served from cache
        llm.ask("another prompt")
    assert len(posts) == 2
    url, payload = posts[0]
    assert url == "https://ollama.com/v1/chat/completions"
    assert (payload["temperature"], payload["seed"]) == (0, 42)
    assert payload["messages"] == [{"role": "user", "content": "prompt"}]  # no entropy appended


def test_local_ollama_is_used_without_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "")
    llm = LocalLLM(LocalLLMConfig(enabled=True, provider="auto", local_model="llama3", cache_dir=tmp_path))
    assert llm.describe() == "ollama/llama3"
    with mock.patch("tools.local_llm.requests.get", side_effect=__import__("requests").ConnectionError("refused")):
        assert llm.is_available() is False
    with mock.patch("tools.llm_provider.requests.post", return_value=FakeResponse()) as post:
        llm._available = True
        llm.ask("prompt")
    assert post.call_args.args[0] == "http://localhost:11434/v1/chat/completions"


def test_disabled_llm_raises_without_network(tmp_path):
    llm = LocalLLM(LocalLLMConfig(enabled=False, cache_dir=tmp_path))
    with mock.patch("tools.local_llm.requests.get") as get, mock.patch("tools.llm_provider.requests.post") as post:
        with pytest.raises(LLMUnavailable):
            llm.ask("prompt")
    get.assert_not_called()
    post.assert_not_called()


def test_env_settings_are_read_after_dotenv(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "7")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("OLLAMA_CLOUD_MODEL", "gpt-oss:20b")
    config = LocalLLM().config
    assert (config.timeout, config.local_model, config.cloud_model) == (7, "test-model", "gpt-oss:20b")


def test_ask_json_and_stream_go_through_the_same_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key-not-real")
    llm = LocalLLM(LocalLLMConfig(enabled=True, provider="auto", cache_dir=tmp_path))
    fake = mock.Mock()
    fake.chat_json.return_value = {"intent": "explain"}
    fake.chat_stream.return_value = iter(["a", "b"])
    with mock.patch.object(LocalLLM, "_client", return_value=fake):
        assert llm.ask_json("system", "user") == {"intent": "explain"}
        assert list(llm.stream([{"role": "user", "content": "q"}])) == ["a", "b"]


def test_stream_raises_llm_unavailable_when_disabled(tmp_path):
    llm = LocalLLM(LocalLLMConfig(enabled=False, cache_dir=tmp_path))
    with pytest.raises(LLMUnavailable):
        list(llm.stream([{"role": "user", "content": "q"}]))


def test_failed_availability_probe_is_rechecked(monkeypatch, tmp_path):
    import requests as req
    from tools import local_llm

    clock = [100.0]
    monkeypatch.setattr(local_llm.time, "monotonic", lambda: clock[0])
    monkeypatch.setenv("OLLAMA_API_KEY", "")
    llm = LocalLLM(LocalLLMConfig(enabled=True, provider="ollama", cache_dir=tmp_path))
    with mock.patch("tools.local_llm.requests.get", side_effect=req.ConnectionError("refused")):
        assert llm.is_available() is False
    up = mock.Mock(status_code=200)
    with mock.patch("tools.local_llm.requests.get", return_value=up) as get:
        assert llm.is_available() is False  # within the recheck interval: no new probe
        get.assert_not_called()
        clock[0] += local_llm.RECHECK_AFTER_S
        assert llm.is_available() is True  # Ollama started later is picked up


def test_chat_calls_fail_fast_and_report_busy(tmp_path, monkeypatch):
    from tools.llm_provider import ProviderBusy
    from tools.local_llm import LLMBusy

    monkeypatch.setenv("OLLAMA_API_KEY", "test-key-not-real")
    llm = LocalLLM(LocalLLMConfig(enabled=True, provider="auto", cache_dir=tmp_path, timeout=120, chat_timeout=45))
    assert llm._client(interactive=True).timeout == 45 and llm._client().timeout == 120
    assert llm._client(interactive=True).max_retry_wait_s == 20
    fake = mock.Mock()
    fake.chat_json.side_effect = ProviderBusy("ollama-cloud is busy or not responding (HTTP 429)")
    with mock.patch.object(LocalLLM, "_client", return_value=fake):
        with pytest.raises(LLMBusy):
            llm.ask_json("system", "user")


def test_chat_answers_and_routing_are_capped(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key-not-real")
    llm = LocalLLM(LocalLLMConfig(enabled=True, provider="auto", cache_dir=tmp_path))
    assert (llm.config.chat_max_tokens, llm.config.router_max_tokens) == (600, 300)
    assert llm._client(interactive=True).retry_on_read_timeout is False and llm._client().retry_on_read_timeout is True
    fake = mock.Mock()
    fake.chat_stream.return_value = iter(["a"])
    fake.chat_json.return_value = {}
    with mock.patch.object(LocalLLM, "_client", return_value=fake):
        list(llm.stream([{"role": "user", "content": "q"}]))
        llm.ask_json("s", "u")
    assert fake.chat_stream.call_args.kwargs["max_tokens"] == 600
    assert fake.chat_json.call_args.kwargs["max_tokens"] == 300

import json
from unittest import mock

import pytest

from tools import llm_provider
from tools.llm_provider import OpenAICompatibleClient, ProviderError

FAKE_KEY = "test-key-not-real"


class FakeResponse:
    def __init__(self, status=200, content='{"verdict": "supports"}', headers=None, text=""):
        self.status_code = status
        self._content = content
        self.headers = headers or {}
        self.text = text

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setattr(llm_provider.time, "sleep", lambda s: None)
    return OpenAICompatibleClient("gemini", cache_dir=tmp_path, min_interval_s=0)


def test_request_shape_and_auth(client):
    with mock.patch("tools.llm_provider.requests.post", return_value=FakeResponse()) as post:
        assert client.chat_json("system", "user") == {"verdict": "supports"}
    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs
    assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert kwargs["json"]["temperature"] == 0
    assert kwargs["json"]["model"] == "gemini-3.8-flash"
    assert kwargs["json"]["response_format"] == {"type": "json_object"}
    assert kwargs["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"


def test_identical_request_is_served_from_cache(client):
    with mock.patch("tools.llm_provider.requests.post", return_value=FakeResponse()) as post:
        client.chat_json("system", "user")
        client.chat_json("system", "user")
        client.chat_json("system", "another prompt")
    assert post.call_count == 2
    for cached in client.cache_dir.iterdir():
        assert FAKE_KEY not in cached.read_text()  # the key is never written to the cache


def test_rate_limit_is_retried(client):
    responses = [FakeResponse(status=429, headers={"Retry-After": "1"}), FakeResponse()]
    with mock.patch("tools.llm_provider.requests.post", side_effect=responses) as post:
        assert client.chat_json("s", "u") == {"verdict": "supports"}
    assert post.call_count == 2


def test_bad_request_raises_with_status(client):
    with mock.patch("tools.llm_provider.requests.post", return_value=FakeResponse(status=400, text="bad model")):
        with pytest.raises(ProviderError, match="HTTP 400") as err:
            client.chat_json("s", "u")
    assert FAKE_KEY not in str(err.value)


def test_code_fenced_json_is_accepted(client):
    fenced = "```json\n" + json.dumps({"verdict": "supports"}) + "\n```"
    with mock.patch("tools.llm_provider.requests.post", return_value=FakeResponse(content=fenced)):
        assert client.chat_json("s", "u") == {"verdict": "supports"}


def test_missing_key_fails_before_any_request(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = OpenAICompatibleClient("gemini", cache_dir=tmp_path)
    with mock.patch("tools.llm_provider.requests.post") as post, pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        client.chat_json("s", "u")
    post.assert_not_called()


def test_ollama_needs_no_key_and_groq_needs_a_model(tmp_path):
    assert OpenAICompatibleClient("ollama", cache_dir=tmp_path)._api_key() is None
    with pytest.raises(ValueError, match="explicit model"):
        OpenAICompatibleClient("groq", cache_dir=tmp_path)


def test_ollama_cloud_is_the_default_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", FAKE_KEY)
    monkeypatch.setattr(llm_provider.time, "sleep", lambda s: None)
    client = OpenAICompatibleClient(cache_dir=tmp_path, min_interval_s=0)
    with mock.patch("tools.llm_provider.requests.post", return_value=FakeResponse()) as post:
        client.chat_json("s", "u")
    assert post.call_args.args[0] == "https://ollama.com/v1/chat/completions"
    assert post.call_args.kwargs["json"]["model"] == "gemma4:31b"
    assert post.call_args.kwargs["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"

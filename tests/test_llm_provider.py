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


class FakeStream:
    def __init__(self, lines, status=200):
        self.status_code = status
        self.headers = {}
        self.text = ""
        self._lines = lines
        self.closed = False

    encoding = None  # like requests: no charset in the Content-Type header

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:  # decoded like requests does, with the response encoding
            yield line.encode("utf-8").decode(self.encoding or "latin-1")

    def close(self):
        self.closed = True


def sse(*pieces):
    return [f'data: {json.dumps({"choices": [{"delta": {"content": p}}]})}' for p in pieces] + ["", "data: [DONE]"]


def test_stream_yields_pieces_then_serves_the_whole_reply_from_cache(client):
    stream = FakeStream(sse("Green ", "Asset ", "Ratio"))
    messages = [{"role": "user", "content": "q"}]
    with mock.patch("tools.llm_provider.requests.post", return_value=stream) as post:
        assert list(client.chat_stream(messages)) == ["Green ", "Asset ", "Ratio"]
        assert list(client.chat_stream(messages)) == ["Green Asset Ratio"]  # cached, one piece
    assert post.call_count == 1 and stream.closed
    sent = post.call_args.kwargs["json"]
    assert sent["stream"] is True and sent["temperature"] == 0 and post.call_args.kwargs["stream"] is True


def test_stream_retries_before_the_first_byte_and_never_caches_a_failed_reply(client):
    responses = [FakeStream([], status=503), FakeStream(["data: not json"])]
    with mock.patch("tools.llm_provider.requests.post", side_effect=responses):
        with pytest.raises(ProviderError, match="Unexpected stream data"):
            list(client.chat_stream([{"role": "user", "content": "q"}]))
    assert not any(client.cache_dir.iterdir())


def test_stream_is_decoded_as_utf8(client):
    with mock.patch("tools.llm_provider.requests.post", return_value=FakeStream(sse("1.5°C-aligned"))):
        assert "".join(client.chat_stream([{"role": "user", "content": "q"}])) == "1.5°C-aligned"


def test_long_retry_after_gives_up_at_once_as_busy(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    slept = []
    monkeypatch.setattr(llm_provider.time, "sleep", slept.append)
    client = OpenAICompatibleClient("gemini", cache_dir=tmp_path, min_interval_s=0, max_retry_wait_s=20)
    busy = FakeResponse(status=429, headers={"Retry-After": "30"})
    with mock.patch("tools.llm_provider.requests.post", return_value=busy) as post:
        with pytest.raises(llm_provider.ProviderBusy):
            client.chat_json("s", "u")
    assert post.call_count == 1 and slept == []  # no point waiting 30 s while a visitor watches


def test_repeated_timeouts_end_as_busy(client):
    timeout = __import__("requests").Timeout("slow")
    with mock.patch("tools.llm_provider.requests.post", side_effect=timeout) as post:
        with pytest.raises(llm_provider.ProviderBusy, match="busy or not responding"):
            client.chat_json("s", "u")
    assert post.call_count == client.max_retries


def test_read_timeout_is_not_retried_when_the_request_may_still_be_queued(tmp_path, monkeypatch):
    import requests

    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setattr(llm_provider.time, "sleep", lambda s: None)
    chat = OpenAICompatibleClient("gemini", cache_dir=tmp_path, min_interval_s=0, retry_on_read_timeout=False)
    with mock.patch("tools.llm_provider.requests.post", side_effect=requests.ReadTimeout("slow")) as post:
        with pytest.raises(llm_provider.ProviderBusy):
            chat.chat_json("s", "u")
    assert post.call_count == 1
    with mock.patch("tools.llm_provider.requests.post", side_effect=requests.ConnectTimeout("no route")) as post:
        with pytest.raises(llm_provider.ProviderBusy):
            chat.chat_json("s", "u")
    assert post.call_count == chat.max_retries  # a connect timeout never reached the provider, so it is retried


def test_max_tokens_is_sent_only_when_given(client):
    with mock.patch("tools.llm_provider.requests.post", return_value=FakeResponse()) as post:
        client.chat_json("s", "u")
        assert "max_tokens" not in post.call_args.kwargs["json"]  # the offline review's cached requests are unchanged
        client.chat_json("s", "u2", max_tokens=300)
        assert post.call_args.kwargs["json"]["max_tokens"] == 300

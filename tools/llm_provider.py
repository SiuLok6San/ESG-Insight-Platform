"""Minimal client for OpenAI-compatible chat APIs (Ollama Cloud, Gemini, Groq, local Ollama).

Used by the offline AI evidence review (``scripts/review_evidence.py``, via
``chat_json``) and the AI assistant (``tools/local_llm.py``, via ``chat_json``,
``chat_text`` and the streaming ``chat_stream``).
Requests use temperature 0; every response is cached on disk under a hash of
the full request, so a re-run reproduces the same output without calling the
API again. The API key is read from an
environment variable (normally set in ``.env``) and is never logged.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "review"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str  # ends with "/"; "chat/completions" is appended
    model: Optional[str]  # default model; None means it must be given explicitly
    api_key_env: Optional[str]  # environment variable holding the key; None for local Ollama


PROVIDERS: Dict[str, ProviderConfig] = {
    "gemini": ProviderConfig(
        "gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-3.8-flash", "GEMINI_API_KEY"
    ),
    "groq": ProviderConfig("groq", "https://api.groq.com/openai/v1/", None, "GROQ_API_KEY"),
    "ollama": ProviderConfig("ollama", "http://localhost:11434/v1/", "llama3", None),
    "ollama-cloud": ProviderConfig("ollama-cloud", "https://ollama.com/v1/", "gemma4:31b", "OLLAMA_API_KEY"),
}


class ProviderError(RuntimeError):
    """The provider could not be called or returned an unusable response."""


class ProviderBusy(ProviderError):
    """The provider is rate-limiting, overloaded or not responding in time.

    Free tiers can be tight (Ollama Cloud's free plan serves one request at a
    time per key), so callers should tell the user to try again later.
    """


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


class OpenAICompatibleClient:
    def __init__(
        self,
        provider: str = "ollama-cloud",
        model: Optional[str] = None,
        cache_dir: Optional[Path] = CACHE_DIR,
        timeout: int = 120,
        max_retries: int = 5,
        min_interval_s: float = 4.5,
        base_url: Optional[str] = None,
        max_retry_wait_s: float = 120.0,
        retry_on_read_timeout: bool = True,
    ) -> None:
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider {provider!r}; choose from {sorted(PROVIDERS)}")
        self.config = PROVIDERS[provider]
        if base_url:
            self.config = ProviderConfig(self.config.name, base_url.rstrip("/") + "/", self.config.model, self.config.api_key_env)
        self.model = model or self.config.model
        if not self.model:
            raise ValueError(f"Provider {provider!r} needs an explicit model name")
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval_s = min_interval_s  # spacing between uncached calls (free-tier rate limits)
        self.max_retry_wait_s = max_retry_wait_s  # give up instead of waiting longer than this before a retry
        # A read timeout means the request reached the provider and may still be queued there; a retry would add a
        # second copy to the queue. The chat sets this to False; offline batch jobs can afford to retry.
        self.retry_on_read_timeout = retry_on_read_timeout
        self._last_call = 0.0

    def _api_key(self) -> Optional[str]:
        if self.config.api_key_env is None:
            return None
        key = os.getenv(self.config.api_key_env, "").strip()
        if not key:
            raise ProviderError(
                f"{self.config.api_key_env} is not set. Add it to the .env file in the project root."
            )
        return key

    def chat_json(self, system: str, user: str, max_tokens: Optional[int] = None) -> Dict[str, object]:
        """Send one chat request and return the parsed JSON object from the reply."""
        payload: Dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        if max_tokens is not None:  # only when given, so existing cache keys stay valid
            payload["max_tokens"] = max_tokens
        cache_key = self._cache_key(payload)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        content = self._post(payload)
        try:
            parsed = json.loads(_strip_code_fence(content))
        except ValueError as exc:
            raise ProviderError(f"Unexpected response from {self.config.name}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ProviderError(f"{self.config.name} returned JSON that is not an object")
        self._write_cache(cache_key, parsed)
        return parsed

    def chat_text(self, user: str, system: Optional[str] = None, max_tokens: int = 1024) -> str:
        """Send one chat request and return the reply text."""
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        payload: Dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if self.config.name.startswith("ollama"):
            payload["seed"] = 42  # Ollama documents seed support for reproducible sampling
        cache_key = self._cache_key(payload)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return str(cached["text"])
        text = self._post(payload).strip()
        if not text:
            raise ProviderError(f"{self.config.name} returned an empty reply")
        self._write_cache(cache_key, {"text": text})
        return text

    def chat_stream(self, messages: List[Dict[str, str]], max_tokens: int = 1024) -> Iterator[str]:
        """Yield the reply in pieces as the model writes it.

        A cached reply is yielded in one piece. A reply is cached only after it
        has been received completely.
        """
        payload: Dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if self.config.name.startswith("ollama"):
            payload["seed"] = 42
        cache_key = self._cache_key(payload)
        cached = self._read_cache(cache_key)
        if cached is not None:
            yield str(cached["text"])
            return
        parts: List[str] = []
        resp = self._open_stream({**payload, "stream": True})
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {}).get("content") or ""
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    raise ProviderError(f"Unexpected stream data from {self.config.name}: {exc}") from exc
                if delta:
                    parts.append(delta)
                    yield delta
        except requests.RequestException as exc:
            raise ProviderBusy(f"{self.config.name} stream interrupted: {type(exc).__name__}") from exc
        finally:
            resp.close()
        text = "".join(parts).strip()
        if not text:
            raise ProviderError(f"{self.config.name} returned an empty reply")
        self._write_cache(cache_key, {"text": text})

    def _open_stream(self, payload: Dict[str, object]) -> requests.Response:
        """Start a streaming request, retrying like ``_post`` until the first byte arrives."""
        headers = {"Content-Type": "application/json"}
        key = self._api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    self.config.base_url + "chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=(10, self.timeout),
                    stream=True,
                )
            except requests.RequestException as exc:
                last_error = f"network error: {type(exc).__name__}"
                if isinstance(exc, requests.ReadTimeout) and not self.retry_on_read_timeout:
                    raise ProviderBusy(f"{self.config.name} is busy or not responding ({last_error})") from exc
                self._wait_before_retry(attempt, last_error, 2**attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                retry_after = resp.headers.get("Retry-After", "")
                resp.close()
                self._wait_before_retry(attempt, last_error, self._retry_after(retry_after, 2**attempt))
                continue
            if resp.status_code != 200:
                raise ProviderError(f"HTTP {resp.status_code} from {self.config.name}: {resp.text[:300]}")
            # Event streams often omit the charset; requests would then decode UTF-8 as Latin-1 ("Â°C").
            resp.encoding = "utf-8"
            return resp
        raise ProviderBusy(f"{self.config.name} is busy or not responding ({last_error})")

    @staticmethod
    def _retry_after(header: str, default: float) -> float:
        return float(header) if header.replace(".", "", 1).isdigit() else default

    def _wait_before_retry(self, attempt: int, error: str, wait: float) -> None:
        """Sleep before the next attempt, or give up if there is none or the wait is too long."""
        if attempt >= self.max_retries or wait > self.max_retry_wait_s:
            raise ProviderBusy(f"{self.config.name} is busy or not responding ({error})")
        time.sleep(wait)

    def _cache_key(self, payload: Dict[str, object]) -> str:
        return hashlib.sha256(json.dumps({"base_url": self.config.base_url, **payload}, sort_keys=True).encode()).hexdigest()

    def _post(self, payload: Dict[str, object]) -> str:
        """POST to chat/completions with retries; return the message content."""
        headers = {"Content-Type": "application/json"}
        key = self._api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"

        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            wait = self.min_interval_s - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            try:
                resp = requests.post(
                    self.config.base_url + "chat/completions", json=payload, headers=headers, timeout=(10, self.timeout)
                )
            except requests.RequestException as exc:
                last_error = f"network error: {type(exc).__name__}"
                if isinstance(exc, requests.ReadTimeout) and not self.retry_on_read_timeout:
                    raise ProviderBusy(f"{self.config.name} is busy or not responding ({last_error})") from exc
                self._wait_before_retry(attempt, last_error, 2**attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                retry_after = resp.headers.get("Retry-After", "")
                self._wait_before_retry(attempt, last_error, self._retry_after(retry_after, 2**attempt * 5))
                continue
            if resp.status_code != 200:
                # The body explains bad requests; it never contains the key.
                raise ProviderError(f"HTTP {resp.status_code} from {self.config.name}: {resp.text[:300]}")
            try:
                return resp.json()["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ProviderError(f"Unexpected response from {self.config.name}: {exc}") from exc
        raise ProviderBusy(f"{self.config.name} is busy or not responding ({last_error})")

    def _read_cache(self, key: str) -> Optional[Dict[str, object]]:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{key}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _write_cache(self, key: str, value: Dict[str, object]) -> None:
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.json").write_text(json.dumps(value, indent=2), encoding="utf-8")

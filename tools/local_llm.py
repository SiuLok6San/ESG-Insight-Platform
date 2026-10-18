"""LLM client for the optional AI assistant.

The assistant is advisory only: it answers questions, suggests rubric
categories and drafts a narrative, but it never changes the official score.

The model is reached through the OpenAI-compatible client in
``tools/llm_provider.py``:

- ``LLM_PROVIDER=auto`` (default) uses Ollama Cloud when ``OLLAMA_API_KEY``
  is set, otherwise a local Ollama server;
- ``LLM_PROVIDER`` can also name a provider explicitly (e.g. ``ollama``,
  ``ollama-cloud``, ``gemini``).

Calls use temperature 0 (and a fixed seed where supported), and every reply
is cached on disk under a hash of the full request, so the same input always
returns the same output.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from tools.llm_provider import PROVIDERS, OpenAICompatibleClient, ProviderError

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "llm"
# A failed local availability probe is retried after this many seconds.
RECHECK_AFTER_S = 30.0


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class LocalLLMConfig:
    # Defaults are read when the config is created (after load_dotenv), not at import time.
    enabled: bool = field(default_factory=lambda: _env_bool("LLM_ENABLED", True))
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "auto").strip() or "auto")
    # Model for a local Ollama server and for Ollama Cloud (empty = the provider's default).
    local_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "llama3"))
    cloud_model: str = field(default_factory=lambda: os.getenv("OLLAMA_CLOUD_MODEL", "").strip())
    local_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434"))
    timeout: int = field(default_factory=lambda: _env_int("LLM_TIMEOUT", 120))
    max_tokens: int = field(default_factory=lambda: _env_int("LLM_NUM_PREDICT", 1024))
    max_retries: int = field(default_factory=lambda: _env_int("LLM_MAX_RETRIES", 3))
    cache_dir: Optional[Path] = CACHE_DIR


class LLMUnavailable(RuntimeError):
    """Raised when the LLM is disabled, unreachable or misconfigured."""


class LocalLLM:
    def __init__(self, config: Optional[LocalLLMConfig] = None) -> None:
        load_dotenv()
        self.config = config or LocalLLMConfig()
        self._available: Optional[bool] = None
        self._checked_at = 0.0

    @property
    def provider(self) -> str:
        if self.config.provider != "auto":
            return self.config.provider
        return "ollama-cloud" if os.getenv("OLLAMA_API_KEY", "").strip() else "ollama"

    @property
    def model(self) -> str:
        if self.provider == "ollama":
            return self.config.local_model
        if self.provider == "ollama-cloud" and self.config.cloud_model:
            return self.config.cloud_model
        return PROVIDERS[self.provider].model or ""

    def describe(self) -> str:
        return f"{self.provider}/{self.model}"

    def is_available(self) -> bool:
        """True if the LLM is enabled and usable.

        Hosted providers count as available when their API key is set. A local
        Ollama server is probed; a failed probe is re-checked after
        ``RECHECK_AFTER_S`` seconds, so starting Ollama later is picked up.
        """
        if not self.config.enabled or self.provider not in PROVIDERS:
            return False
        key_env = PROVIDERS[self.provider].api_key_env
        if key_env:
            return bool(os.getenv(key_env, "").strip())
        now = time.monotonic()
        if self._available is None or (not self._available and now - self._checked_at >= RECHECK_AFTER_S):
            try:
                resp = requests.get(f"{self.config.local_base_url}/api/tags", timeout=2)
                self._available = resp.status_code == 200
            except requests.RequestException:
                self._available = False
            self._checked_at = now
        return self._available

    def _client(self) -> OpenAICompatibleClient:
        base_url = self.config.local_base_url + "/v1/" if self.provider == "ollama" else None
        return OpenAICompatibleClient(
            self.provider,
            model=self.model,
            cache_dir=self.config.cache_dir,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
            min_interval_s=0,
            base_url=base_url,
        )

    def ask(self, prompt: str) -> str:
        """Return the model's reply to ``prompt`` (from cache when possible)."""
        if not self.is_available():
            raise LLMUnavailable(f"LLM {self.describe()} is disabled or not reachable")
        try:
            return self._client().chat_text(prompt, max_tokens=self.config.max_tokens)
        except (ProviderError, ValueError) as exc:
            raise LLMUnavailable(str(exc)) from exc

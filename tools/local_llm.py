"""Optional local LLM client (Ollama).

The LLM is advisory only: it summarises documents and suggests rubric
categories, but it never changes a score. Calls are made reproducible by
using temperature 0 and a fixed seed, and every response is cached on disk
under a hash of the full request, so the same input always returns the same
output.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "llm"


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class LocalLLMConfig:
    # Defaults are read when the config is created (after load_dotenv), not at import time.
    enabled: bool = field(default_factory=lambda: _env_bool("LLM_ENABLED", True))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "llama3"))
    base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434"))
    temperature: float = 0.0
    seed: int = 42
    timeout: int = field(default_factory=lambda: _env_int("LLM_TIMEOUT", 120))
    num_predict: int = field(default_factory=lambda: _env_int("LLM_NUM_PREDICT", 1024))
    max_retries: int = field(default_factory=lambda: _env_int("LLM_MAX_RETRIES", 3))
    cache_dir: Optional[Path] = CACHE_DIR


class LLMUnavailable(RuntimeError):
    """Raised when the local LLM is disabled or cannot be reached."""


class LocalLLM:
    def __init__(self, config: Optional[LocalLLMConfig] = None) -> None:
        load_dotenv()
        self.config = config or LocalLLMConfig()
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """True if the LLM is enabled and the Ollama server answers (checked once)."""
        if self._available is None:
            if not self.config.enabled:
                self._available = False
            else:
                try:
                    resp = requests.get(f"{self.config.base_url}/api/tags", timeout=2)
                    self._available = resp.status_code == 200
                except requests.RequestException:
                    self._available = False
        return self._available

    def ask(self, prompt: str) -> str:
        """Return the model's response to ``prompt`` (from cache when possible)."""
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "seed": self.config.seed,
                "num_predict": self.config.num_predict,
            },
        }
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

        cached = self._read_cache(key)
        if cached is not None:
            return cached
        if not self.is_available():
            raise LLMUnavailable(
                f"Local LLM '{self.config.model}' is disabled or not reachable at {self.config.base_url}"
            )

        last_err: Optional[Exception] = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                resp = requests.post(
                    f"{self.config.base_url}/api/generate",
                    json=payload,
                    timeout=(10, self.config.timeout),
                )
                resp.raise_for_status()
                text = (resp.json().get("response") or "").strip()
                if not text:
                    raise RuntimeError("empty response")
                self._write_cache(key, payload, text)
                return text
            except Exception as exc:
                last_err = exc
                time.sleep(0.4 * attempt)
        raise LLMUnavailable(f"Local LLM call failed after {self.config.max_retries} attempts: {last_err}")

    def _read_cache(self, key: str) -> Optional[str]:
        if self.config.cache_dir is None:
            return None
        path = self.config.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    def _write_cache(self, key: str, payload: dict, text: str) -> None:
        if self.config.cache_dir is None:
            return
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        record = {"model": payload["model"], "options": payload["options"], "response": text}
        (self.config.cache_dir / f"{key}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

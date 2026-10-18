"""Guards against committing API keys."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),  # Google API keys
    re.compile(r"gsk_[0-9A-Za-z]{40,}"),  # Groq API keys
    re.compile(r"sk-[0-9A-Za-z_\-]{32,}"),  # OpenAI-style keys
    re.compile(r"(OLLAMA|GEMINI|GROQ)_API_KEY[ \t]*=[ \t]*[^\s#]+"),  # a filled-in .env line
]


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    return [ROOT / f for f in out.splitlines()]


def test_env_file_is_gitignored():
    result = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT)
    assert result.returncode == 0, ".env must be listed in .gitignore"


def test_no_api_keys_in_tracked_files():
    for path in tracked_files():
        if path.suffix in {".png", ".pdf"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in KEY_PATTERNS:
            assert not pattern.search(text), f"possible API key in {path.relative_to(ROOT)}"

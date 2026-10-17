"""Download a bank's official annual report and extract its text.

The report URL comes from the evidence table, so the optional LLM summary
reads the same document that the scores cite. Downloads are cached on disk
under ``.cache/reports`` so each report is fetched only once.
"""

from __future__ import annotations

import hashlib
import logging
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests

from tools.evidence import EvidenceTable

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - pypdf is in requirements.txt
    PdfReader = None

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "reports"


def official_report_url(evidence: EvidenceTable, bank: str) -> Optional[str]:
    """The source document URL used by the bank's evidence rows."""
    urls = {row.url for row in evidence.for_bank(bank).values() if row.url}
    if len(urls) > 1:
        logger.warning("[PDFFetcher] %s cites several documents; using the first", bank)
    return sorted(urls)[0] if urls else None


def _download(url: str, timeout: int = 60) -> Optional[bytes]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.pdf"
    if path.exists():
        return path.read_bytes()
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("[PDFFetcher] Failed to download %s: %s", url, exc)
        return None
    path.write_bytes(resp.content)
    return resp.content


def pdf_bytes_to_text(data: bytes) -> str:
    if PdfReader is None:
        logger.warning("[PDFFetcher] pypdf not installed; cannot parse PDF.")
        return ""
    try:
        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        logger.warning("[PDFFetcher] Failed to parse PDF: %s", exc)
        return ""


def fetch_official_pdf(evidence: EvidenceTable, bank: str) -> str:
    """Text of the bank's annual report, or an empty string if unavailable."""
    url = official_report_url(evidence, bank)
    if not url:
        return ""
    data = _download(url)
    return pdf_bytes_to_text(data) if data else ""

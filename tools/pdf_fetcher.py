"""Download a bank's official annual report and extract the cited pages.

The report URL and page numbers come from the evidence table, so the
optional LLM summary reads exactly the pages that the scores cite. Downloads
are cached on disk under ``.cache/reports`` so each report is fetched once.
"""

from __future__ import annotations

import hashlib
import logging
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Sequence

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


def cited_pages(evidence: EvidenceTable, bank: str) -> List[int]:
    """Sorted, unique page numbers cited in the bank's evidence rows."""
    return sorted({row.page for row in evidence.for_bank(bank).values() if row.page})


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
    if not resp.content.startswith(b"%PDF"):
        # e.g. an HTML consent or bot-check page served with status 200: do not cache it.
        logger.warning("[PDFFetcher] %s did not return a PDF; not cached", url)
        return None
    path.write_bytes(resp.content)
    return resp.content


def download_report(url: str) -> Optional[bytes]:
    """The PDF at ``url`` (from the on-disk cache when available), or ``None``."""
    return _download(url)


def extract_pages(data: bytes, pages: Sequence[int]) -> Dict[int, str]:
    """Text of each requested 1-based page; pages outside the PDF are skipped."""
    if PdfReader is None:
        logger.warning("[PDFFetcher] pypdf not installed; cannot parse PDF.")
        return {}
    try:
        reader = PdfReader(BytesIO(data))
        return {n: reader.pages[n - 1].extract_text() or "" for n in pages if 0 < n <= len(reader.pages)}
    except Exception as exc:
        logger.warning("[PDFFetcher] Failed to parse PDF: %s", exc)
        return {}


def pdf_bytes_to_text(data: bytes, pages: Optional[Sequence[int]] = None) -> str:
    """Text of the PDF, or only of ``pages`` (1-based, each prefixed with its page number)."""
    if pages is not None:
        return "\n\n".join(f"--- page {n} ---\n{text}" for n, text in extract_pages(data, pages).items())
    if PdfReader is None:
        logger.warning("[PDFFetcher] pypdf not installed; cannot parse PDF.")
        return ""
    try:
        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
    except Exception as exc:
        logger.warning("[PDFFetcher] Failed to parse PDF: %s", exc)
        return ""


def fetch_cited_pages(evidence: EvidenceTable, bank: str) -> str:
    """Text of the pages cited for ``bank``, or an empty string if unavailable."""
    url = official_report_url(evidence, bank)
    if not url:
        return ""
    data = _download(url)
    return pdf_bytes_to_text(data, cited_pages(evidence, bank)) if data else ""

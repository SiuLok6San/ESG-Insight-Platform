"""Verbatim quotes from the cited report pages, and the check that they are really there.

Every evidence row carries a ``quote``: one or more excerpts copied from the
bank's annual report, separated by `` … ``. An excerpt is taken from the
row's cited page unless it starts with a page prefix such as ``[p. 138] ``,
for evidence that continues on another page of the same report.

``scripts/verify_quotes.py`` downloads the reports and checks every excerpt
against its page; ``data/evidence/quote_check.csv`` records the result, and
the test suite fails if any excerpt is missing from that file or failed.
"""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # avoid a circular import: tools.evidence uses this module
    from tools.evidence import EvidenceTable

QUOTE_CHECK_PATH = Path(__file__).resolve().parent.parent / "data" / "evidence" / "quote_check.csv"
MIN_QUOTE_CHARS = 20  # letters and digits; shorter quotes prove nothing
SEPARATOR = " … "
_PAGE_PREFIX = re.compile(r"^\[p\. (\d+)\] ")


def normalise(text: str) -> str:
    """Lowercase letters and digits only, so PDF spacing, hyphenation and punctuation do not matter."""
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", text).lower())


def verify_quote(quote: str, page_text: str) -> bool:
    """True if ``quote`` (at least MIN_QUOTE_CHARS letters/digits) appears in ``page_text``."""
    q = normalise(quote)
    return len(q) >= MIN_QUOTE_CHARS and q in normalise(page_text)


def parse_excerpts(quote: str, cited_page: Optional[int]) -> List[Tuple[Optional[int], str]]:
    """Split a quote field into (page, excerpt) pairs; unprefixed excerpts use the cited page."""
    excerpts = []
    for part in quote.split(SEPARATOR):
        part = part.strip()
        if not part:
            continue
        match = _PAGE_PREFIX.match(part)
        if match:
            excerpts.append((int(match.group(1)), part[match.end():].strip()))
        else:
            excerpts.append((cited_page, part))
    return excerpts


def format_excerpts(excerpts: List[Tuple[Optional[int], str]], cited_page: Optional[int]) -> str:
    """Inverse of ``parse_excerpts``."""
    return SEPARATOR.join(text if page in (None, cited_page) else f"[p. {page}] {text}" for page, text in excerpts)


def excerpt_fingerprint(text: str) -> str:
    """Short hash of the normalised excerpt, used to detect edits after verification."""
    return hashlib.sha256(normalise(text).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class QuoteCheck:
    bank: str
    indicator: str
    excerpt_no: int
    page: int
    fingerprint: str
    verified: bool
    checked_on: str


CHECK_COLUMNS = tuple(QuoteCheck.__dataclass_fields__)


def check_quotes(
    evidence: "EvidenceTable", page_text: Callable[[str, int], str], checked_on: str
) -> List[QuoteCheck]:
    """Check every excerpt of every row against the text of its page."""
    results = []
    for row in evidence.rows:
        for no, (page, text) in enumerate(row.excerpts(), start=1):
            if page is None:
                continue
            results.append(
                QuoteCheck(
                    bank=row.bank,
                    indicator=row.indicator,
                    excerpt_no=no,
                    page=page,
                    fingerprint=excerpt_fingerprint(text),
                    verified=verify_quote(text, page_text(row.bank, page)),
                    checked_on=checked_on,
                )
            )
    return results


def write_quote_checks(results: List[QuoteCheck], path: Path = QUOTE_CHECK_PATH) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CHECK_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(asdict(r) for r in results)


def load_quote_checks(path: Path = QUOTE_CHECK_PATH) -> Dict[Tuple[str, str, int], QuoteCheck]:
    """Saved checks keyed by (bank, indicator, excerpt_no); empty if the check has not been run."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = [
            QuoteCheck(
                bank=r["bank"],
                indicator=r["indicator"],
                excerpt_no=int(r["excerpt_no"]),
                page=int(r["page"]),
                fingerprint=r["fingerprint"],
                verified=r["verified"] == "True",
                checked_on=r["checked_on"],
            )
            for r in csv.DictReader(f)
        ]
    return {(r.bank, r.indicator, r.excerpt_no): r for r in rows}

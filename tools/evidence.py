"""Load and validate the evidence table (``data/evidence/esg_evidence.csv``).

The evidence table is the single source of truth for scores: one row per
bank x indicator, each with a category, a short evidence summary, a page
citation in the bank's annual report and a verbatim quote from that page
(see ``tools/quotes.py``). This module checks that the table is
complete and consistent with the rubric in ``tools/score_engine.py``.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tools.quotes import MIN_QUOTE_CHARS, normalise, parse_excerpts
from tools.score_engine import ALL_KEYS, NOT_DISCLOSED, allowed_categories

EVIDENCE_PATH = Path(__file__).resolve().parent.parent / "data" / "evidence" / "esg_evidence.csv"
REPORTING_YEAR = "FY2025"
COLUMNS = (
    "bank",
    "indicator",
    "category",
    "evidence_summary",
    "quote",
    "source_document",
    "page",
    "url",
    "status",
    "notes",
)
STATUSES = ("draft", "confirmed")


class EvidenceError(ValueError):
    """Raised when the evidence table is incomplete or inconsistent."""

    def __init__(self, problems: List[str]) -> None:
        self.problems = problems
        super().__init__("Invalid evidence table:\n- " + "\n- ".join(problems))


@dataclass(frozen=True)
class EvidenceRow:
    bank: str
    indicator: str
    category: str
    evidence_summary: str
    source_document: str
    page: Optional[int]
    url: str
    status: str
    notes: str
    quote: str = ""

    def excerpts(self) -> List[Tuple[Optional[int], str]]:
        """Verbatim excerpts as (page, text); see ``tools.quotes.parse_excerpts``."""
        return parse_excerpts(self.quote, self.page)

    @property
    def page_url(self) -> str:
        """Link that opens the source PDF at the cited page ("" if nothing is cited)."""
        if not self.url or not self.page:
            return ""
        return f"{self.url}#page={self.page}"

    @property
    def page_label(self) -> str:
        """Plain-text citation such as "p. 111", or "not disclosed"."""
        return f"p. {self.page}" if self.page_url else "not disclosed"

    def markdown_link(self, with_document: bool = False) -> str:
        """Markdown link to the cited page, or "not disclosed" when there is no citation."""
        if not self.page_url:
            return "not disclosed"
        text = f"{self.source_document}, {self.page_label}" if with_document else self.page_label
        return f"[{text}]({self.page_url})"

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data.update(
            page_url=self.page_url,
            page_label=self.page_label,
            page_link=self.markdown_link(),
            source_link=self.markdown_link(with_document=True),
        )
        return data


class EvidenceTable:
    def __init__(self, rows: List[EvidenceRow]) -> None:
        self.rows = rows
        self._by_bank: Dict[str, Dict[str, EvidenceRow]] = {}
        for row in rows:
            self._by_bank.setdefault(row.bank, {})[row.indicator] = row

    def banks(self) -> List[str]:
        """Banks in the order they first appear in the file."""
        return list(self._by_bank)

    def for_bank(self, bank: str) -> Dict[str, EvidenceRow]:
        if bank not in self._by_bank:
            raise KeyError(f"No evidence for bank {bank!r}; available: {', '.join(self.banks())}")
        return self._by_bank[bank]

    def categories(self, bank: str) -> Dict[str, str]:
        return {key: row.category for key, row in self.for_bank(bank).items()}


def _parse_page(raw: Optional[str]) -> Optional[int]:
    """A positive integer page number, or ``None``."""
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def validate_rows(raw_rows: List[Dict[str, str]], fieldnames: List[str]) -> List[str]:
    """Return a list of problems; an empty list means the table is valid."""
    problems: List[str] = []
    if tuple(fieldnames) != COLUMNS:
        problems.append(f"Columns must be {list(COLUMNS)}, got {fieldnames}")
        return problems

    seen: Dict[tuple, int] = {}
    banks: List[str] = []
    for line_no, r in enumerate(raw_rows, start=2):
        # csv.DictReader stores surplus fields under None and fills missing ones with None.
        if None in r or any(r.get(c) is None for c in COLUMNS):
            problems.append(f"line {line_no}: expected {len(COLUMNS)} columns")
            continue
        where = f"line {line_no} ({r['bank']} / {r['indicator']})"
        if r["bank"] not in banks:
            banks.append(r["bank"])
        key = (r["bank"], r["indicator"])
        if key in seen:
            problems.append(f"{where}: duplicate of line {seen[key]}")
        seen[key] = line_no

        if r["indicator"] not in ALL_KEYS:
            problems.append(f"{where}: unknown indicator")
            continue
        if r["category"] not in allowed_categories(r["indicator"]):
            problems.append(
                f"{where}: category {r['category']!r} not allowed "
                f"(allowed: {', '.join(allowed_categories(r['indicator']))})"
            )
        if r["status"] not in STATUSES:
            problems.append(f"{where}: status must be one of {STATUSES}")
        if not r["evidence_summary"].strip() and r["category"] != NOT_DISCLOSED:
            problems.append(f"{where}: missing evidence_summary")
        if r["category"] == NOT_DISCLOSED:
            if not r["notes"].strip():
                problems.append(f"{where}: not_disclosed rows must explain the search in notes")
        else:
            if not r["source_document"].strip():
                problems.append(f"{where}: missing source_document")
            if _parse_page(r["page"]) is None:
                problems.append(f"{where}: page must be a positive integer, got {r['page']!r}")
            if not r["url"].startswith(("http://", "https://")):
                problems.append(f"{where}: url must be an http(s) link")
            if not r["quote"].strip():
                problems.append(f"{where}: missing quote (a verbatim excerpt from the cited page)")
            for _, text in parse_excerpts(r["quote"], None):
                if len(normalise(text)) < MIN_QUOTE_CHARS:
                    problems.append(f"{where}: quote excerpt too short to verify: {text!r}")

    for bank in banks:
        missing = [k for k in ALL_KEYS if (bank, k) not in seen]
        if missing:
            problems.append(f"{bank}: missing indicators {missing}")
    return problems


def load_evidence(path: Path | str = EVIDENCE_PATH) -> EvidenceTable:
    """Read and validate the evidence table; raise ``EvidenceError`` if invalid."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    problems = validate_rows(raw_rows, fieldnames)
    if problems:
        raise EvidenceError(problems)

    rows = [
        EvidenceRow(
            bank=r["bank"],
            indicator=r["indicator"],
            category=r["category"],
            evidence_summary=r["evidence_summary"],
            quote=r["quote"],
            source_document=r["source_document"],
            page=_parse_page(r["page"]),
            url=r["url"],
            status=r["status"],
            notes=r["notes"],
        )
        for r in raw_rows
    ]
    return EvidenceTable(rows)

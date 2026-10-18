"""AI evidence review: an independent LLM check of each evidence row.

For every bank x indicator row, the model reads only the cited PDF page and
answers three questions: does the page support the analyst's evidence
summary, which category would it assign from the written definitions, and
which passage on the page backs that answer. The passage must be copied
verbatim, and ``verify_quote`` checks that it really appears on the page, so
an invented quote is flagged instead of trusted.

Results are written once, offline, to ``data/evidence/ai_review.csv`` and
shown in the app as "AI review, not used in score". They never change a
category or a score.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional

from tools.evidence import EvidenceRow, EvidenceTable
from tools.quotes import verify_quote
from tools.score_engine import ALL_KEYS, CONTROVERSY_KEY, NOT_DISCLOSED, RUBRIC_BY_KEY, allowed_categories

ROOT = Path(__file__).resolve().parent.parent
REVIEW_PATH = ROOT / "data" / "evidence" / "ai_review.csv"
DEFINITIONS_PATH = ROOT / "data" / "evidence" / "category_definitions.md"
VERDICTS = ("supports", "partially_supports", "does_not_support")

SYSTEM_PROMPT = (
    "You are an independent auditor checking ESG evidence citations for a bank benchmark. "
    "Use only the page text you are given. Do not use outside knowledge. Reply with a single JSON object."
)

USER_TEMPLATE = """Bank: {bank}
Indicator: {label} ({key})
Allowed categories: {allowed}
Category definitions: {definition}

Analyst's category: {category}
Analyst's evidence summary: {summary}
Cited source: {source}, page {page}

--- PAGE TEXT (page {page}) ---
{page_text}
--- END PAGE TEXT ---

Tasks:
1. Does the page text support the analyst's evidence summary? Answer "supports", "partially_supports" or "does_not_support".
2. Using only this page and the definitions, which category would you assign? Use one allowed category, or "not_disclosed" if the page does not contain enough evidence.
3. Copy one passage of 10 to 40 words verbatim from the page text that best supports your answer. Do not paraphrase and do not use ellipses.
4. Explain your answer in one or two sentences.

Return JSON with exactly these keys: {{"verdict": "...", "suggested_category": "...", "quote": "...", "explanation": "..."}}"""

PROMPT_VERSION = hashlib.sha256((SYSTEM_PROMPT + USER_TEMPLATE).encode()).hexdigest()[:8]

REVIEW_COLUMNS = (
    "bank",
    "indicator",
    "evidence_category",
    "page",
    "ai_verdict",
    "ai_suggested_category",
    "category_agrees",
    "quote",
    "quote_verified",
    "explanation",
    "problems",
    "provider",
    "model",
    "reviewed_on",
    "prompt_version",
)


@dataclass(frozen=True)
class ReviewResult:
    bank: str
    indicator: str
    evidence_category: str
    page: Optional[int]
    ai_verdict: str
    ai_suggested_category: str
    category_agrees: bool
    quote: str
    quote_verified: bool
    explanation: str
    problems: str
    provider: str
    model: str
    reviewed_on: str
    prompt_version: str


def load_definitions(path: Path = DEFINITIONS_PATH) -> Dict[str, str]:
    """Definition text per indicator, read from category_definitions.md."""
    text = path.read_text(encoding="utf-8")
    definitions: Dict[str, str] = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].startswith("`") and cells[0].strip("`") in RUBRIC_BY_KEY:
            definitions[cells[0].strip("`")] = cells[3]
    controversy = [
        f"`{c[0].strip('`')}`: {c[1]}"
        for c in (
            [x.strip() for x in line.strip().strip("|").split("|")]
            for line in text.split("## Controversy adjustment", 1)[-1].splitlines()
        )
        if len(c) == 3 and c[0].startswith("`")
    ]
    definitions[CONTROVERSY_KEY] = " ".join(controversy)
    return definitions


def build_prompt(row: EvidenceRow, page_text: str, definition: str) -> str:
    label = RUBRIC_BY_KEY[row.indicator].label if row.indicator in RUBRIC_BY_KEY else "Controversy"
    return USER_TEMPLATE.format(
        bank=row.bank,
        label=label,
        key=row.indicator,
        allowed=", ".join(allowed_categories(row.indicator)),
        definition=definition,
        category=row.category,
        summary=row.evidence_summary,
        source=row.source_document,
        page=row.page,
        page_text=page_text,
    )


def review_row(
    client,
    row: EvidenceRow,
    page_text: str,
    definition: str,
    provider: str,
    reviewed_on: Optional[str] = None,
) -> ReviewResult:
    """Ask the model about one row and validate everything it returns."""
    answer: Mapping[str, object] = client.chat_json(SYSTEM_PROMPT, build_prompt(row, page_text, definition))
    problems: List[str] = []

    verdict = str(answer.get("verdict", "")).strip()
    if verdict not in VERDICTS:
        problems.append(f"invalid verdict {verdict!r}")
    suggested = str(answer.get("suggested_category", "")).strip()
    if suggested not in allowed_categories(row.indicator):
        problems.append(f"category {suggested!r} not in rubric")
    quote = " ".join(str(answer.get("quote", "")).split())
    quote_verified = verify_quote(quote, page_text)
    if not quote_verified:
        problems.append("quote not found on the cited page")

    return ReviewResult(
        bank=row.bank,
        indicator=row.indicator,
        evidence_category=row.category,
        page=row.page,
        ai_verdict=verdict,
        ai_suggested_category=suggested,
        category_agrees=suggested == row.category,
        quote=quote,
        quote_verified=quote_verified,
        explanation=" ".join(str(answer.get("explanation", "")).split()),
        problems="; ".join(problems),
        provider=provider,
        model=getattr(client, "model", ""),
        reviewed_on=reviewed_on or date.today().isoformat(),
        prompt_version=PROMPT_VERSION,
    )


def run_review(
    evidence: EvidenceTable,
    client,
    page_text_for: Callable[[EvidenceRow], str],
    provider: str,
    banks: Optional[List[str]] = None,
    progress: Callable[[str], None] = lambda message: None,
) -> List[ReviewResult]:
    """Review every row of ``banks`` (default: all) in table order."""
    definitions = load_definitions()
    results = []
    for bank in banks or evidence.banks():
        rows = evidence.for_bank(bank)
        for key in ALL_KEYS:
            row = rows[key]
            if row.category == NOT_DISCLOSED or not row.page:
                continue  # nothing cited, nothing to check
            result = review_row(client, row, page_text_for(row), definitions[key], provider)
            progress(f"{bank} / {key}: {result.ai_verdict or '?'}{' (' + result.problems + ')' if result.problems else ''}")
            results.append(result)
    return results


def write_reviews(results: List[ReviewResult], path: Path = REVIEW_PATH) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for r in results:
            writer.writerow({k: ("" if v is None else v) for k, v in asdict(r).items()})


def load_reviews(path: Path = REVIEW_PATH) -> Dict[tuple, Dict[str, object]]:
    """Saved review rows keyed by (bank, indicator); empty if the review has not been run."""
    if not Path(path).exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise ValueError(f"{path}: columns must be {list(REVIEW_COLUMNS)}")
        reviews = {}
        for r in reader:
            r = dict(r)
            r["category_agrees"] = r["category_agrees"] == "True"
            r["quote_verified"] = r["quote_verified"] == "True"
            reviews[(r["bank"], r["indicator"])] = r
        return reviews


def summarise(reviews: Mapping[tuple, Mapping[str, object]]) -> Dict[str, object]:
    """Counts for the UI and README."""
    rows = list(reviews.values())
    return {
        "rows": len(rows),
        "verdicts": {v: sum(r["ai_verdict"] == v for r in rows) for v in VERDICTS},
        "category_agrees": sum(bool(r["category_agrees"]) for r in rows),
        "quote_verified": sum(bool(r["quote_verified"]) for r in rows),
        "models": sorted({f"{r['provider']}/{r['model']}" for r in rows}),
        "reviewed_on": sorted({str(r["reviewed_on"]) for r in rows}),
    }

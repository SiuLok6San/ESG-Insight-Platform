"""Blind AI review: an LLM rates each evidence row from the report pages and the definitions only.

The AI evidence review (``tools/ai_review.py``) shows the model the analysts'
category and summary, so its category is a second opinion. Here the prompt
contains none of that and does not name the bank: only the indicator, the
allowed categories with their written definitions, and the text of the pages
the row quotes (the cited page plus any page an excerpt continues on; the
page text itself often names the bank). Its category is therefore an
independent rating of the same disclosure.

As in the AI review, the model must copy a passage verbatim and the code
checks that it appears on one of the pages. Results are written once,
offline, to ``data/evidence/ai_blind_review.csv`` and never change a category
or a score: they feed the "AI reviewer score" in the chat and the list of
disagreements in ``docs/blind_review.md``.
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
from tools.score_engine import ALL_KEYS, NOT_DISCLOSED, RUBRIC_BY_KEY, allowed_categories

ROOT = Path(__file__).resolve().parent.parent
BLIND_REVIEW_PATH = ROOT / "data" / "evidence" / "ai_blind_review.csv"
BLIND_REPORT_PATH = ROOT / "docs" / "blind_review.md"

SYSTEM_PROMPT = (
    "You are an independent ESG analyst rating a bank's annual-report disclosure against written category "
    "definitions. Use only the page text you are given. Do not use outside knowledge. Reply with a single JSON object."
)

USER_TEMPLATE = """Indicator: {label} ({key})
Allowed categories: {allowed}
Category definitions: {definition}

{pages}

Tasks:
1. Using only these pages and the definitions, which category fits the disclosure best? Use one allowed category, or "not_disclosed" if the pages do not contain enough evidence.
2. Copy one passage of 10 to 40 words verbatim from the page text that best supports your answer. Do not paraphrase and do not use ellipses.
3. Explain your answer in one or two sentences.

Return JSON with exactly these keys: {{"category": "...", "quote": "...", "explanation": "..."}}"""

PROMPT_VERSION = hashlib.sha256((SYSTEM_PROMPT + USER_TEMPLATE).encode()).hexdigest()[:8]

COLUMNS = (
    "bank",
    "indicator",
    "analyst_category",
    "pages",
    "ai_category",
    "category_agrees",
    "quote",
    "quote_page",
    "quote_verified",
    "explanation",
    "problems",
    "provider",
    "model",
    "reviewed_on",
    "prompt_version",
)


@dataclass(frozen=True)
class BlindResult:
    bank: str
    indicator: str
    analyst_category: str
    pages: str  # pages shown to the model, e.g. "137 138"
    ai_category: str
    category_agrees: bool
    quote: str
    quote_page: Optional[int]
    quote_verified: bool
    explanation: str
    problems: str
    provider: str
    model: str
    reviewed_on: str
    prompt_version: str


def row_pages(row: EvidenceRow) -> List[int]:
    """The cited page and every other page the row's quote comes from, in order."""
    return list(dict.fromkeys(page for page, _ in row.excerpts() if page))


def build_prompt(row: EvidenceRow, page_texts: Mapping[int, str], definition: str) -> str:
    label = RUBRIC_BY_KEY[row.indicator].label if row.indicator in RUBRIC_BY_KEY else "Controversy"
    pages = "\n\n".join(
        f"--- PAGE TEXT (page {page}) ---\n{page_texts.get(page, '')}\n--- END PAGE TEXT ---" for page in row_pages(row)
    )
    return USER_TEMPLATE.format(
        label=label,
        key=row.indicator,
        allowed=", ".join(allowed_categories(row.indicator)),
        definition=definition,
        pages=pages,
    )


def review_row(
    client,
    row: EvidenceRow,
    page_texts: Mapping[int, str],
    definition: str,
    provider: str,
    reviewed_on: Optional[str] = None,
) -> BlindResult:
    """Ask the model to rate one row blind and validate everything it returns."""
    answer: Mapping[str, object] = client.chat_json(SYSTEM_PROMPT, build_prompt(row, page_texts, definition))
    problems: List[str] = []
    category = str(answer.get("category", "")).strip()
    if category not in allowed_categories(row.indicator):
        problems.append(f"category {category!r} not in rubric")
    quote = " ".join(str(answer.get("quote", "")).split())
    quote_page = next((p for p in row_pages(row) if verify_quote(quote, page_texts.get(p, ""))), None)
    if quote_page is None:
        problems.append("quote not found on the pages")
    return BlindResult(
        bank=row.bank,
        indicator=row.indicator,
        analyst_category=row.category,
        pages=" ".join(str(p) for p in row_pages(row)),
        ai_category=category,
        category_agrees=category == row.category,
        quote=quote,
        quote_page=quote_page,
        quote_verified=quote_page is not None,
        explanation=" ".join(str(answer.get("explanation", "")).split()),
        problems="; ".join(problems),
        provider=provider,
        model=getattr(client, "model", ""),
        reviewed_on=reviewed_on or date.today().isoformat(),
        prompt_version=PROMPT_VERSION,
    )


def run_blind_review(
    evidence: EvidenceTable,
    client,
    page_texts_for: Callable[[EvidenceRow], Mapping[int, str]],
    definitions: Mapping[str, str],
    provider: str,
    banks: Optional[List[str]] = None,
    progress: Callable[[str], None] = lambda message: None,
) -> List[BlindResult]:
    results = []
    for bank in banks or evidence.banks():
        rows = evidence.for_bank(bank)
        for key in ALL_KEYS:
            row = rows[key]
            if row.category == NOT_DISCLOSED or not row.page:
                continue
            result = review_row(client, row, page_texts_for(row), definitions[key], provider)
            progress(f"{bank} / {key}: {result.ai_category or '?'}{' (' + result.problems + ')' if result.problems else ''}")
            results.append(result)
    return results


def write_results(results: List[BlindResult], path: Path = BLIND_REVIEW_PATH) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for r in results:
            writer.writerow({k: ("" if v is None else v) for k, v in asdict(r).items()})


def load_results(path: Path = BLIND_REVIEW_PATH) -> Dict[tuple, Dict[str, object]]:
    """Saved blind ratings keyed by (bank, indicator); empty if the blind review has not been run."""
    if not Path(path).exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f"{path}: columns must be {list(COLUMNS)}")
        results = {}
        for r in reader:
            r = dict(r)
            r["category_agrees"] = r["category_agrees"] == "True"
            r["quote_verified"] = r["quote_verified"] == "True"
            r["quote_page"] = int(r["quote_page"]) if r["quote_page"] else None
            results[(r["bank"], r["indicator"])] = r
        return results


def report(
    blind: Mapping[tuple, Mapping[str, object]],
    anchored: Mapping[tuple, Mapping[str, object]],
    evidence: EvidenceTable,
) -> str:
    """Markdown report: agreement with the analysts, comparison with the anchored review, every disagreement."""
    rows = list(blind.values())
    agree = sum(bool(r["category_agrees"]) for r in rows)
    anchored_agree = sum(bool(anchored[k]["category_agrees"]) for k in blind if k in anchored)
    verified = sum(bool(r["quote_verified"]) for r in rows)
    models = sorted({f"{r['provider']}/{r['model']}" for r in rows})
    dates = sorted({str(r["reviewed_on"]) for r in rows})

    def order(cat: str, key: str) -> int:
        cats = list(allowed_categories(key))
        return cats.index(cat) if cat in cats and cat != NOT_DISCLOSED else -1

    lines = [
        "# Blind AI review",
        "",
        f"Model: {', '.join(models)}; run on {', '.join(dates)} with `python -m scripts.review_evidence --blind`.",
        "Not used in the official score. No category was changed.",
        "",
        "The model saw only the indicator, the allowed categories with their written definitions, and the text of",
        "the pages each row quotes. It did not see the analysts' category or evidence summary, and the prompt did",
        "not name the bank (the page text often does).",
        "",
        "## Agreement",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Blind AI category = analysts' category | {agree} of {len(rows)} |",
        f"| Same measure in the AI evidence review, which was shown the analysts' category | {anchored_agree} of {len(rows)} |",
        f"| Blind AI quote found on the pages | {verified} of {len(rows)} |",
        "",
        "The two agreement figures are not a clean measure of anchoring: the AI evidence review saw only the cited",
        "page, while the blind review saw every page the row quotes (for example both p. 137 and p. 138 for ING's",
        "diversity row), so part of the difference comes from the extra pages.",
        "",
        "## Every disagreement",
        "",
        "Direction: *higher* means the blind AI chose a better-scoring category than the analysts.",
        "",
        "| Bank | Indicator | Analysts | Blind AI | Direction | Quote found? | Blind AI's reasoning and quote |",
        "|---|---|---|---|---|---|---|",
    ]
    for (bank, key), r in blind.items():
        if r["category_agrees"]:
            continue
        a, b = str(r["analyst_category"]), str(r["ai_category"])
        direction = "lower" if order(b, key) < order(a, key) else "higher"
        label = RUBRIC_BY_KEY[key].label if key in RUBRIC_BY_KEY else "Controversy"
        if key == "controversy":  # a lower deduction is better
            direction = "higher" if direction == "lower" else "lower"
        found = f"yes (p. {r['quote_page']})" if r["quote_verified"] else "no"
        reasoning = str(r["explanation"]).replace("|", "/")
        quote = str(r["quote"]).replace("|", "/")
        lines.append(f"| {bank} | {label} | `{a}` | `{b}` | {direction} | {found} | {reasoning} Quote: \"{quote}\" |")
    if agree == len(rows):
        lines.append("| | | | | | | No disagreements. |")
    lines += [
        "",
        "Disagreements are prompts for the analysts to re-check a row, not corrections. The blind AI sees only the",
        "quoted pages, so it can miss evidence elsewhere in the report, and it applies the definitions literally.",
    ]
    return "\n".join(lines) + "\n"

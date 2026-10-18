"""Run the offline AI evidence review and save it to data/evidence/ai_review.csv.

Usage (from the repository root, with OLLAMA_API_KEY set in .env):

    python -m scripts.review_evidence                 # all banks, Ollama Cloud
    python -m scripts.review_evidence --bank "ING Group" --limit 3
    python -m scripts.review_evidence --dry-run       # build prompts only, no API calls

Responses are cached in .cache/review, so an interrupted run can be resumed
and a repeated run makes no new API calls. The API key is read from the
environment and never printed.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional

from dotenv import load_dotenv

from tools.ai_review import REVIEW_PATH, load_definitions, build_prompt, run_review, summarise, write_reviews
from tools.evidence import EvidenceRow, load_evidence
from tools.llm_provider import PROVIDERS, OpenAICompatibleClient
from tools.pdf_fetcher import cited_pages, download_report, extract_pages, official_report_url


class _LimitReached(Exception):
    pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="ollama-cloud")
    parser.add_argument("--model", help="override the provider's default model")
    parser.add_argument("--bank", action="append", help="review only this bank (repeatable)")
    parser.add_argument("--limit", type=int, help="stop after this many rows (for a trial run)")
    parser.add_argument("--dry-run", action="store_true", help="extract pages and build prompts without calling the API")
    args = parser.parse_args(argv)

    load_dotenv()
    evidence = load_evidence()
    banks = args.bank or evidence.banks()

    pages: Dict[str, Dict[int, str]] = {}
    for bank in banks:
        url = official_report_url(evidence, bank)
        data = download_report(url) if url else None
        if not data:
            print(f"Could not download the report for {bank}: {url}", file=sys.stderr)
            return 1
        pages[bank] = extract_pages(data, cited_pages(evidence, bank))
        print(f"{bank}: {len(pages[bank])} cited pages extracted")

    def page_text_for(row: EvidenceRow) -> str:
        return pages[row.bank].get(row.page, "")

    if args.dry_run:
        definitions = load_definitions()
        rows = [r for b in banks for r in evidence.for_bank(b).values() if r.page]
        sizes = [len(build_prompt(r, page_text_for(r), definitions[r.indicator])) for r in rows]
        print(f"Dry run: {len(rows)} prompts, {min(sizes)}-{max(sizes)} characters each. No API calls made.")
        return 0

    client = OpenAICompatibleClient(provider=args.provider, model=args.model)
    done = 0

    def progress(message: str) -> None:
        nonlocal done
        done += 1
        print(f"[{done}] {message}")
        if args.limit and done >= args.limit:
            raise _LimitReached

    try:
        results = run_review(evidence, client, page_text_for, args.provider, banks=banks, progress=progress)
    except _LimitReached:
        print(f"Stopped after {done} rows (--limit). Responses are cached; nothing was written.")
        return 0

    write_reviews(results, REVIEW_PATH)
    summary = summarise({(r.bank, r.indicator): r.__dict__ for r in results})
    print(f"Wrote {len(results)} reviews to {REVIEW_PATH.relative_to(REVIEW_PATH.parents[2])}")
    print(f"Verdicts: {summary['verdicts']}")
    print(f"AI category matches the evidence category: {summary['category_agrees']} of {summary['rows']}")
    print(f"Quotes found on the cited page: {summary['quote_verified']} of {summary['rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

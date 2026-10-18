"""Check every verbatim quote in the evidence table against its page in the PDF.

Usage (from the repository root; downloads the three annual reports once and
caches them in .cache/reports):

    python -m scripts.verify_quotes

Writes data/evidence/quote_check.csv and exits with status 1 if any excerpt
is not found on its page. The test suite fails if a quote is edited without
re-running this check.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

from tools.evidence import load_evidence
from tools.pdf_fetcher import download_report, extract_pages, official_report_url
from tools.quotes import QUOTE_CHECK_PATH, check_quotes, write_quote_checks


def main(argv: Optional[List[str]] = None) -> int:
    evidence = load_evidence()
    needed: Dict[str, set] = defaultdict(set)
    for row in evidence.rows:
        for page, _ in row.excerpts():
            if page:
                needed[row.bank].add(page)

    pages: Dict[str, Dict[int, str]] = {}
    for bank, wanted in needed.items():
        url = official_report_url(evidence, bank)
        data = download_report(url) if url else None
        if not data:
            print(f"Could not download the report for {bank}: {url}", file=sys.stderr)
            return 1
        pages[bank] = extract_pages(data, sorted(wanted))

    results = check_quotes(evidence, lambda bank, page: pages[bank].get(page, ""), date.today().isoformat())
    write_quote_checks(results)
    failed = [r for r in results if not r.verified]
    for r in failed:
        print(f"NOT FOUND: {r.bank} / {r.indicator} excerpt {r.excerpt_no} on p. {r.page}")
    print(f"{len(results) - len(failed)} of {len(results)} excerpts found on their page; wrote {QUOTE_CHECK_PATH.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

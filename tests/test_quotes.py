import csv

import pytest

from tests.test_evidence import read_raw_rows, write_csv
from tools.evidence import EvidenceError, load_evidence
from tools.quotes import (
    check_quotes,
    excerpt_fingerprint,
    format_excerpts,
    load_quote_checks,
    parse_excerpts,
)


def test_excerpts_default_to_the_cited_page_unless_prefixed():
    quote = "First excerpt on the cited page. … [p. 138] Second excerpt on the next page."
    excerpts = parse_excerpts(quote, 137)
    assert excerpts == [(137, "First excerpt on the cited page."), (138, "Second excerpt on the next page.")]
    assert format_excerpts(excerpts, 137) == quote


def test_every_row_quotes_its_cited_page(evidence):
    for row in evidence.rows:
        pages = [page for page, _ in row.excerpts()]
        assert pages, (row.bank, row.indicator)
        assert row.page in pages, (row.bank, row.indicator)  # at least one excerpt from the cited page itself


def test_every_excerpt_was_verified_against_the_pdf(evidence):
    """quote_check.csv is written by scripts/verify_quotes.py; editing a quote requires re-running it."""
    checks = load_quote_checks()
    expected = set()
    for row in evidence.rows:
        for no, (page, text) in enumerate(row.excerpts(), start=1):
            key = (row.bank, row.indicator, no)
            expected.add(key)
            check = checks.get(key)
            assert check is not None, f"{key} not checked: run python -m scripts.verify_quotes"
            assert check.page == page and check.fingerprint == excerpt_fingerprint(text), f"{key} changed since the check"
            assert check.verified, f"{key} was not found on p. {page}"
    assert set(checks) == expected  # no stale checks for removed excerpts


def test_check_flags_an_excerpt_missing_from_its_page(evidence):
    row = evidence.for_bank("ING Group")["taxonomy_alignment"]
    pages = {131: "For 2025, our GAR based on Turnover is 14 percent (2024: 7 percent)."}
    results = check_quotes(evidence, lambda bank, page: pages.get(page, "") if bank == row.bank else "", "2026-10-18")
    by_row = {(r.bank, r.indicator): r.verified for r in results}
    assert by_row[("ING Group", "taxonomy_alignment")]
    assert not by_row[("ING Group", "climate_plan")]  # its page text was not provided


def test_validator_requires_a_quote_that_can_be_verified(tmp_path):
    rows, _ = read_raw_rows()
    rows[0] = {**rows[0], "quote": ""}
    rows[1] = {**rows[1], "quote": "Too short"}
    write_csv(tmp_path / "e.csv", rows)
    with pytest.raises(EvidenceError) as err:
        load_evidence(tmp_path / "e.csv")
    problems = "\n".join(err.value.problems)
    assert "missing quote" in problems
    assert "quote excerpt too short to verify: 'Too short'" in problems


def test_quote_check_file_has_one_row_per_excerpt():
    with open("data/evidence/quote_check.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 88 and all(r["verified"] == "True" for r in rows)

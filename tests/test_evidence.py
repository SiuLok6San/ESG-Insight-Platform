import csv
from collections import Counter

import pytest

from tests.helpers import BANKS
from tools.evidence import COLUMNS, EVIDENCE_PATH, EvidenceError, EvidenceRow, load_evidence
from tools.score_engine import ALL_KEYS, NOT_DISCLOSED, allowed_categories


def read_raw_rows():
    with open(EVIDENCE_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


def test_columns_match_spec():
    _, fieldnames = read_raw_rows()
    assert tuple(fieldnames) == COLUMNS


def test_every_bank_indicator_row_exists_exactly_once(evidence):
    assert evidence.banks() == BANKS
    counts = Counter((r.bank, r.indicator) for r in evidence.rows)
    assert len(evidence.rows) == len(BANKS) * len(ALL_KEYS) == 45
    for bank in BANKS:
        for key in ALL_KEYS:
            assert counts[(bank, key)] == 1, (bank, key)


def test_every_category_is_allowed(evidence):
    for r in evidence.rows:
        assert r.category in allowed_categories(r.indicator), (r.bank, r.indicator, r.category)


def test_disclosed_rows_have_source_page_and_url(evidence):
    for r in evidence.rows:
        if r.category == NOT_DISCLOSED:
            assert r.notes.strip(), (r.bank, r.indicator)
            continue
        assert r.source_document.strip(), (r.bank, r.indicator)
        assert isinstance(r.page, int) and r.page > 0, (r.bank, r.indicator)
        assert r.url.startswith("https://"), (r.bank, r.indicator)
        assert r.evidence_summary.strip(), (r.bank, r.indicator)


def test_each_bank_cites_a_single_report(evidence):
    for bank in BANKS:
        docs = {(r.source_document, r.url) for r in evidence.for_bank(bank).values()}
        assert len(docs) == 1, (bank, docs)


def test_all_rows_reviewed(evidence):
    # Rows start as "draft" and are only used in published results once confirmed.
    assert {r.status for r in evidence.rows} == {"confirmed"}


def test_page_url_points_at_cited_page(evidence):
    row = evidence.for_bank("ING Group")["climate_plan"]
    assert row.page_url == f"{row.url}#page={row.page}"


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_validator_reports_missing_rows(tmp_path):
    rows, _ = read_raw_rows()
    rows = [r for r in rows if not (r["bank"] == "Rabobank" and r["indicator"] == "climate_plan")]
    write_csv(tmp_path / "e.csv", rows)
    with pytest.raises(EvidenceError, match=r"Rabobank: missing indicators \['climate_plan'\]"):
        load_evidence(tmp_path / "e.csv")


def test_validator_reports_bad_category_and_missing_page(tmp_path):
    rows, _ = read_raw_rows()
    rows[0] = {**rows[0], "category": "excellent"}
    rows[1] = {**rows[1], "page": ""}
    write_csv(tmp_path / "e.csv", rows)
    with pytest.raises(EvidenceError) as err:
        load_evidence(tmp_path / "e.csv")
    problems = "\n".join(err.value.problems)
    assert "category 'excellent' not allowed" in problems
    assert "page must be a positive integer" in problems


def test_validator_reports_duplicates(tmp_path):
    rows, _ = read_raw_rows()
    write_csv(tmp_path / "e.csv", rows + [rows[0]])
    with pytest.raises(EvidenceError, match="duplicate"):
        load_evidence(tmp_path / "e.csv")


def test_not_disclosed_row_needs_notes_but_no_page(tmp_path):
    rows, _ = read_raw_rows()
    rows[0] = {**rows[0], "category": NOT_DISCLOSED, "page": "", "url": "", "source_document": "", "notes": ""}
    write_csv(tmp_path / "e.csv", rows)
    with pytest.raises(EvidenceError) as err:
        load_evidence(tmp_path / "e.csv")
    assert err.value.problems == [f"line 2 ({rows[0]['bank']} / {rows[0]['indicator']}): not_disclosed rows must explain the search in notes"]

    rows[0]["notes"] = "Searched the sustainability statement; no disclosure found."
    write_csv(tmp_path / "e.csv", rows)
    table = load_evidence(tmp_path / "e.csv")
    assert table.for_bank(rows[0]["bank"])[rows[0]["indicator"]].page is None


@pytest.mark.parametrize("page", ["0", "-3", "12a", ""])
def test_page_must_be_a_positive_integer(tmp_path, page):
    rows, _ = read_raw_rows()
    rows[0] = {**rows[0], "page": page}
    write_csv(tmp_path / "e.csv", rows)
    with pytest.raises(EvidenceError, match="page must be a positive integer"):
        load_evidence(tmp_path / "e.csv")


@pytest.mark.parametrize("tail", ["ING Group,climate_plan\n", "ING Group,climate_plan,sbt_aligned,s,q,d,1,https://x,confirmed,n,EXTRA\n"])
def test_malformed_row_is_reported_not_crashing(tmp_path, tail):
    rows, _ = read_raw_rows()
    path = tmp_path / "e.csv"
    write_csv(path, rows[1:])  # drop the real ING climate_plan row
    with open(path, "a", encoding="utf-8") as f:
        f.write(tail)
    with pytest.raises(EvidenceError) as err:
        load_evidence(path)
    assert f"line {len(rows) + 1}: expected {len(COLUMNS)} columns" in err.value.problems


def test_citation_helpers(evidence):
    row = evidence.for_bank("ING Group")["climate_plan"]
    assert row.page_label == "p. 111"
    assert row.markdown_link() == f"[p. 111]({row.url}#page=111)"
    assert row.markdown_link(with_document=True) == f"[ING Group Annual Report 2025, p. 111]({row.url}#page=111)"

    hidden = EvidenceRow(**{**row.__dict__, "category": NOT_DISCLOSED, "page": None, "url": "", "source_document": ""})
    assert (hidden.page_url, hidden.page_label, hidden.markdown_link(True)) == ("", "not disclosed", "not disclosed")
    assert "None" not in str(hidden.to_dict()["source_link"])

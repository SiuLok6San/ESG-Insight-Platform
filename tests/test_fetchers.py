"""The report fetcher, with all HTTP calls mocked."""

from unittest import mock

import pytest
import requests
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

from tests.helpers import highest_categories, make_table
from tools import pdf_fetcher

class FakeResponse:
    def __init__(self, content: bytes, status: int = 200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def make_pdf(path, n_pages):
    with PdfPages(path) as pdf:
        for i in range(1, n_pages + 1):
            fig = plt.figure()
            fig.text(0.1, 0.5, f"Content of page {i}")
            pdf.savefig(fig)
            plt.close(fig)


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_fetcher, "CACHE_DIR", tmp_path / "reports")
    return tmp_path / "reports"


def test_only_cited_pages_are_extracted(tmp_path, cache_dir):
    make_pdf(tmp_path / "r.pdf", 4)
    table = make_table({"Bank": highest_categories()})
    table.rows[:] = [r.__class__(**{**r.__dict__, "page": 2 if i % 2 else 4}) for i, r in enumerate(table.rows)]
    table = table.__class__(table.rows)

    with mock.patch("tools.pdf_fetcher.requests.get", return_value=FakeResponse((tmp_path / "r.pdf").read_bytes())):
        data = pdf_fetcher.download_report("https://example.com/report.pdf")

    pages = pdf_fetcher.cited_pages(table, "Bank")
    texts = pdf_fetcher.extract_pages(data, pages)
    assert pages == [2, 4] and set(texts) == {2, 4}
    assert "Content of page 2" in texts[2] and "Content of page 4" in texts[4]


def test_non_pdf_response_is_not_cached(cache_dir):
    html = FakeResponse(b"<html>Please accept cookies</html>")
    with mock.patch("tools.pdf_fetcher.requests.get", return_value=html) as get:
        assert pdf_fetcher._download("https://example.com/report.pdf") is None
        assert pdf_fetcher._download("https://example.com/report.pdf") is None
    assert get.call_count == 2  # retried, not served from a bad cache entry
    assert not any(cache_dir.iterdir())

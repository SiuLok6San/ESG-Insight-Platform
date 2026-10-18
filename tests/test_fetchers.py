"""Network clients and the report fetcher, with all HTTP calls mocked."""

from unittest import mock

import pytest
import requests
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

from tests.helpers import highest_categories, make_table
from tools import pdf_fetcher
from tools.free_news import TIMEOUT_S, FreeNewsClient

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>{title}</title><link>https://example.com/{title}</link><pubDate>Mon, 02 Feb 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def test_news_queries_use_a_timeout_and_survive_failures():
    calls = []

    def fake_get(url, params, timeout):
        calls.append(timeout)
        if params["q"].endswith("climate"):
            raise requests.Timeout("slow feed")
        return FakeResponse(RSS.replace(b"{title}", params["q"].split()[-1].encode()))

    with mock.patch("tools.free_news.requests.get", side_effect=fake_get):
        items = FreeNewsClient().search("ING Group", limit=50)

    queries = FreeNewsClient()._build_queries("ING Group")
    assert calls == [TIMEOUT_S] * len(queries)
    titles = [it["title"] for it in items]
    assert "climate" not in titles  # the failed query is skipped
    # Results keep the query order even though queries run in parallel.
    assert titles == [q.split()[-1] for q in queries if not q.endswith("climate")]


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
    joined = pdf_fetcher.pdf_bytes_to_text(data, pages)
    assert joined.startswith("--- page 2 ---") and "Content of page 1" not in joined


def test_non_pdf_response_is_not_cached(cache_dir):
    html = FakeResponse(b"<html>Please accept cookies</html>")
    with mock.patch("tools.pdf_fetcher.requests.get", return_value=html) as get:
        assert pdf_fetcher._download("https://example.com/report.pdf") is None
        assert pdf_fetcher._download("https://example.com/report.pdf") is None
    assert get.call_count == 2  # retried, not served from a bad cache entry
    assert not any(cache_dir.iterdir())

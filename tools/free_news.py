from __future__ import annotations

import datetime
import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

import feedparser
import requests

logger = logging.getLogger(__name__)

RSS_URL = "https://news.google.com/rss/search"
TIMEOUT_S = 10


class FreeNewsClient:

    # PUBLIC API
    def search(self, bank: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Search Google News RSS for ESG-related articles about the bank.

        The queries run in parallel, each with a timeout, so a slow feed
        cannot block the app. Results keep the query order.

        Returns a list of dicts:
        [
          {
            "title": "...",
            "source": "...",
            "link": "...",
            "published": "...",
            "snippet": "..."
          }
        ]
        """
        queries = self._build_queries(bank)
        with ThreadPoolExecutor(max_workers=6) as pool:
            feeds = list(pool.map(self._fetch_feed, queries))

        results = []
        for entries in feeds:
            for entry in entries:
                item = self._parse_entry(entry)
                if item:
                    results.append(item)

        # Remove duplicates
        unique = self._dedupe(results)

        # Limit size
        return unique[:limit]

    def _fetch_feed(self, query: str) -> list:
        """Entries of one RSS query, or an empty list on any network error."""
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        try:
            resp = requests.get(RSS_URL, params=params, timeout=TIMEOUT_S)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("[FreeNews] Query %r failed: %s", query, exc)
            return []
        return feedparser.parse(resp.content).entries

    # Internal Helpers
    def _build_queries(self, bank: str) -> List[str]:
        """Build multi-keyword Google News search queries."""
        esg_terms = [
            "ESG",
            "sustainability",
            "climate",
            "governance",
            "AML",
            "KYC",
            "risk",
            "regulator",
            "EU taxonomy",
            "CSRD",
            "SFDR",
        ]

        # Generate combinations: (bank + term)
        queries = [f"{bank} {term}" for term in esg_terms]

        return queries

    def _parse_entry(self, e) -> Dict[str, str]:
        """Safely parse a single RSS entry."""
        try:
            title = html.unescape(e.title)
            link = e.link
            published = e.get("published", "")

            # Rarely missing summary
            snippet = html.unescape(getattr(e, "summary", "")).strip()

            # Clean snippet: remove HTML tags
            snippet = re.sub(r"<.*?>", "", snippet)

            # Convert date → readable
            if published:
                try:
                    dt = datetime.datetime(*e.published_parsed[:6])
                    published = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

            return {
                "title": title,
                "source": e.get("source", {}).get("title", ""),
                "link": link,
                "published": published,
                "snippet": snippet,
            }

        except Exception:
            return None

    def _dedupe(self, items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Remove duplicate articles."""
        seen = set()
        unique = []
        for item in items:
            key = item["title"] + item["link"]
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None


BANK_TICKERS = {
    "ING Group": "INGA.AS",
    "ABN AMRO": "ABN.AS",
}


class YahooFinanceClient:
    def __init__(self) -> None:
        if yf is None:
            logger.warning(
                "[YahooFinanceClient] yfinance not installed; will use fallback text only."
            )

    def _snapshot_from_ticker(self, ticker: str) -> str:
        if yf is None:
            return (
                f"Yahoo Finance data unavailable because 'yfinance' is not installed. "
                f"Ticker={ticker}."
            )

        try:
            t = yf.Ticker(ticker)
            info = t.info  # 网络请求
        except Exception as e:
            logger.warning(f"[YahooFinanceClient] Failed to fetch info for {ticker}: {e}")
            return f"Yahoo Finance snapshot unavailable for ticker {ticker}."

        name = info.get("longName") or info.get("shortName") or ticker
        sector = info.get("sector", "N/A")
        country = info.get("country", "N/A")
        employees = info.get("fullTimeEmployees", "N/A")
        summary = info.get("longBusinessSummary", "")

        snapshot = (
            f"Name: {name}\n"
            f"Ticker: {ticker}\n"
            f"Sector: {sector}\n"
            f"Country: {country}\n"
            f"Employees: {employees}\n"
            f"Summary: {summary}"
        )
        return snapshot

    def lookup_and_snapshot(self, bank: str) -> str:
        bank_norm = bank.strip()
        ticker = BANK_TICKERS.get(bank_norm)

        if ticker:
            return self._snapshot_from_ticker(ticker)

        # 没有 ticker（如 Rabobank）
        return (
            f"No direct stock ticker mapping found for bank '{bank_norm}'. "
            "Bank may be privately held or not listed. "
            "Proceeding with ESG PDF text and news only."
        )
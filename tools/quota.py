"""Site-wide daily cap on AI requests.

The free Ollama Cloud tier has a usage quota. A per-visitor limit alone can
be reset by reloading the page, so the app also counts the AI requests it
makes for all visitors of one app process. The count resets at midnight UTC
and when the app restarts.
"""

from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from typing import Callable, Optional


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


class DailyLimitReached(RuntimeError):
    """Raised when the site-wide daily AI request limit has been used up."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"The daily limit of {limit} AI requests has been reached. It resets at midnight UTC.")
        self.limit = limit


class DailyQuota:
    """Thread-safe counter of AI requests per UTC day."""

    def __init__(self, limit: int, today: Callable[[], date] = utc_today) -> None:
        if limit < 0:
            raise ValueError("The daily AI request limit cannot be negative")
        self.limit = limit
        self._today = today
        self._day: Optional[date] = None
        self._used = 0
        self._lock = threading.Lock()

    def _roll_over(self) -> None:
        day = self._today()
        if day != self._day:
            self._day, self._used = day, 0

    def remaining(self) -> int:
        with self._lock:
            self._roll_over()
            return max(self.limit - self._used, 0)

    def try_consume(self) -> bool:
        """Use one request if any are left today; return whether it was allowed."""
        with self._lock:
            self._roll_over()
            if self._used >= self.limit:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        """Give back one request (e.g. the AI service was busy and nothing was answered)."""
        with self._lock:
            self._roll_over()
            self._used = max(self._used - 1, 0)

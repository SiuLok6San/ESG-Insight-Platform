from __future__ import annotations

import copy
import hashlib
import os
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

from agents.esg_agent import ESGAgent
from agents.final_writer import FinalWriterAgent
from agents.news_agent import NewsSummariser
from tools.evidence import EVIDENCE_PATH, REPORTING_YEAR, load_evidence
from tools.free_news import FreeNewsClient
from tools.local_llm import LLMUnavailable, LocalLLM
from tools.pdf_summarizer import PDFSummarizer
from tools.quota import DailyLimitReached, DailyQuota
from tools.score_engine import ALL_KEYS, CONTROVERSY_KEY, RUBRIC_BY_KEY, ScoreEngine, ScoreEngineConfig
from tools.sensitivity import run_sensitivity
from tools.ai_review import REVIEW_PATH, load_reviews, summarise
from tools.yahoo_client import YahooFinanceClient

T = TypeVar("T")

# Analyses are cached per (bank, question, uploaded PDF); keep only the most recent ones.
MAX_CACHE_ENTRIES = 64


class Server:
    """
    Central orchestrator. One analysis has three independent parts:

    1. Scores: evidence table -> ScoreEngine. Deterministic, offline, and
       identical with or without the LLM.
    2. Context (optional): Yahoo Finance snapshot and Google News RSS headlines.
    3. AI assistant (optional, advisory): the LLM answers a question from the
       evidence and news and suggests rubric categories; a narrative report
       is written only on request. Its output is shown separately and never
       changes a score. Uncached AI requests count against a site-wide
       daily limit (``AI_QUESTIONS_PER_DAY``, default 50).
    """

    def __init__(
        self,
        use_llm: Optional[bool] = None,
        fetch_external: bool = True,
        evidence_path: Path | str = EVIDENCE_PATH,
        review_path: Path | str = REVIEW_PATH,
        engine_config: Optional[ScoreEngineConfig] = None,
        daily_ai_limit: Optional[int] = None,
    ) -> None:
        """
        Parameters
        ----------
        use_llm : bool, optional
            ``False`` never contacts the LLM. ``None`` or ``True`` uses it only
            if the local Ollama server is reachable.
        fetch_external : bool
            Fetch Yahoo Finance and Google News context (network access).
        daily_ai_limit : int, optional
            AI requests allowed per UTC day for all visitors together. Defaults
            to the ``AI_QUESTIONS_PER_DAY`` environment variable, else 50.
        """
        self.evidence = load_evidence(evidence_path)
        # Offline AI evidence review (advisory only); empty if it has not been run.
        self.reviews = load_reviews(review_path)
        self.engine = ScoreEngine(engine_config)
        self.fetch_external = fetch_external
        self.llm = LocalLLM()
        self.llm_mode = use_llm
        self.use_llm = False if use_llm is False else self.llm.is_available()

        self.yahoo = YahooFinanceClient()
        self.news_client = FreeNewsClient()
        self.pdf_summarizer = PDFSummarizer(self.llm)
        self.news_agent = NewsSummariser(self.llm)
        self.esg_agent = ESGAgent(self.llm)
        self.writer = FinalWriterAgent(self.llm)
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        if daily_ai_limit is None:
            daily_ai_limit = int(os.getenv("AI_QUESTIONS_PER_DAY", "50"))
        self.ai_quota = DailyQuota(daily_ai_limit)

    # Public API
    def refresh_llm_status(self) -> bool:
        """Re-check whether the LLM is reachable (unless it was switched off), e.g. after Ollama starts."""
        if self.llm_mode is not False:
            self.use_llm = self.llm.is_available()
        return self.use_llm

    def banks(self) -> List[str]:
        return self.evidence.banks()

    def score_bank(self, bank: str) -> Dict[str, Any]:
        """Deterministic scores plus the evidence behind every indicator."""
        rows = self.evidence.for_bank(bank)
        result = self.engine.score(self.evidence.categories(bank), bank=bank)

        breakdown = []
        for ind in result.indicators:
            row = rows[ind.key]
            breakdown.append(
                {
                    **asdict(ind),
                    "evidence_summary": row.evidence_summary,
                    "source_document": row.source_document,
                    "page": row.page,
                    "page_url": row.page_url,
                    "page_label": row.page_label,
                    "page_link": row.markdown_link(),
                    "status": row.status,
                    "notes": row.notes,
                    "ai_review": self.reviews.get((bank, ind.key)),
                }
            )

        scores = result.to_dict()
        scores.pop("indicators")
        return {
            "scores": scores,
            "breakdown": breakdown,
            "controversy_evidence": {
                **rows[CONTROVERSY_KEY].to_dict(),
                "ai_review": self.reviews.get((bank, CONTROVERSY_KEY)),
            },
            "draft_indicators": [key for key, row in rows.items() if row.status != "confirmed"],
        }

    def analyze_bank(
        self,
        bank: str,
        question: Optional[str] = None,
        pdf_text: Optional[str] = None,
        pdf_filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Full analysis for one bank: scores, optional context, optional AI assistant.

        A cached analysis is returned without using the daily AI limit; a new
        one with the AI assistant raises ``DailyLimitReached`` once the limit
        is used up.
        """
        cache_key = self._analysis_key(bank, question, pdf_text)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        if self.use_llm and not self.ai_quota.try_consume():
            raise DailyLimitReached(self.ai_quota.limit)

        scored = self.score_bank(bank)

        news_items: List[Dict[str, str]] = []
        yahoo_snapshot = ""
        if self.fetch_external:
            yahoo_snapshot = self._safe(lambda: self.yahoo.lookup_and_snapshot(bank), "", "Yahoo snapshot")
            news_items = self._safe(lambda: self.news_client.search(bank, limit=10), [], "News fetch")

        if self.use_llm:
            assistant = self._run_assistant(bank, question, pdf_text, news_items, yahoo_snapshot)
        else:
            assistant = {"enabled": False}

        result = {
            "ok": True,
            "bank": bank,
            "reporting_year": REPORTING_YEAR,
            **scored,
            "assistant": assistant,
            "news": {"items": self._news_items_for_ui(news_items), "query": bank},
            "yahoo": {"ok": bool(yahoo_snapshot), "snapshot": yahoo_snapshot},
            "pdf_filename": pdf_filename,
        }
        self._cache_put(cache_key, result)
        return result

    def has_cached_analysis(self, bank: str, question: Optional[str] = None, pdf_text: Optional[str] = None) -> bool:
        return self._analysis_key(bank, question, pdf_text) in self.cache

    def write_report(self, bank: str, news_summary: str = "") -> str:
        """Narrative report, written only on request (one AI request, cached per bank and news summary)."""
        cache_key = self._report_key(bank, news_summary)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached["report"]
        if not self.use_llm:
            raise LLMUnavailable("The AI assistant is off")
        if not self.ai_quota.try_consume():
            raise DailyLimitReached(self.ai_quota.limit)
        scored = self.score_bank(bank)
        report = self.writer.run(
            bank=bank, scores=scored["scores"], breakdown=scored["breakdown"], news_summary=news_summary
        )
        self._cache_put(cache_key, {"report": report})
        return report

    def has_cached_report(self, bank: str, news_summary: str = "") -> bool:
        return self._report_key(bank, news_summary) in self.cache

    def ai_requests_left_today(self) -> int:
        return self.ai_quota.remaining()

    def compare_banks(self, banks: List[str]) -> Dict[str, Any]:
        """Rank banks by their evidence-based scores (offline and deterministic)."""
        per_bank: Dict[str, Dict[str, Any]] = {}
        errors: Dict[str, str] = {}
        for bank in banks:
            try:
                per_bank[bank] = self.score_bank(bank)
            except Exception as exc:
                errors[bank] = str(exc)

        # Highest final score first; ties broken by name so the order is stable.
        ranking = sorted(per_bank, key=lambda b: (-per_bank[b]["scores"]["final"], b))
        lines = [f"Ranking by final score ({REPORTING_YEAR} evidence):"]
        for i, bank in enumerate(ranking, start=1):
            sc = per_bank[bank]["scores"]
            p = sc["pillars"]
            lines.append(
                f"{i}. {bank}: {sc['final']} ({sc['label']}) - E {p['E']}, S {p['S']}, G {p['G']}, "
                f"controversy {sc['controversy']} (-{sc['controversy_deduction']:g})"
            )

        return {
            "ok": True,
            "ranking": ranking,
            "per_bank_results": per_bank,
            "errors": errors,
            "comparison_summary": "\n".join(lines),
        }

    def ai_review_summary(self) -> Dict[str, Any]:
        """Counts from the offline AI evidence review; ``rows`` is 0 if it has not been run."""
        return {
            **summarise(self.reviews),
            "disagreements": [
                dict(r)
                for r in self.reviews.values()
                if r["ai_verdict"] != "supports" or not r["category_agrees"] or not r["quote_verified"]
            ],
        }

    def sensitivity(self, banks: List[str]) -> Dict[str, Any]:
        """Weight and judgment sensitivity of the ranking and labels (see tools/sensitivity.py)."""
        cache_key = "sensitivity:" + "|".join(banks)
        cached = self._cache_get(cache_key)
        if cached is None:
            cached = run_sensitivity(self.evidence, banks, self.engine.cfg).to_dict()
            self._cache_put(cache_key, cached)
        return cached

    # AI assistant (advisory only)
    def _run_assistant(
        self,
        bank: str,
        question: Optional[str],
        pdf_text: Optional[str],
        news_items: List[Dict[str, str]],
        yahoo_snapshot: str,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "enabled": True,
            "model": self.llm.describe(),
            "error": None,
            "news_summary": "",
            "pdf_summary": "",
            "analysis_text": "",
            "suggestions": [],
            "rejected": {},
            "ai_estimate": None,
        }
        try:
            if news_items:
                out["news_summary"] = self.news_agent.summarise(bank, news_items)
            if pdf_text:  # a PDF uploaded by the user
                out["pdf_summary"] = self.pdf_summarizer.summarize(pdf_text, bank=bank, year=REPORTING_YEAR)

            context = self._build_context_blob(
                self._evidence_text(bank), yahoo_snapshot, out["news_summary"], out["pdf_summary"], question
            )
            esg = self.esg_agent.run(bank=bank, question=question, context_blob=context)
            out["analysis_text"] = esg["analysis_text"]
            out["rejected"] = esg["rejected"]

            evidence_categories = self.evidence.categories(bank)
            for key in ALL_KEYS:
                suggestion = esg["suggestions"].get(key)
                out["suggestions"].append(
                    {
                        "indicator": key,
                        "label": RUBRIC_BY_KEY[key].label if key in RUBRIC_BY_KEY else "Controversy",
                        "evidence_category": evidence_categories[key],
                        "ai_suggestion": suggestion,
                        "agrees": suggestion == evidence_categories[key],
                    }
                )
            out["ai_estimate"] = self._ai_estimate(bank, esg["suggestions"])
        except Exception as exc:  # the assistant is optional; scores are unaffected
            out["error"] = str(exc)
        return out

    # Helpers
    def _evidence_text(self, bank: str) -> str:
        """The bank's evidence rows as plain text for the assistant."""
        lines = []
        for key, row in self.evidence.for_bank(bank).items():
            label = RUBRIC_BY_KEY[key].label if key in RUBRIC_BY_KEY else "Controversy"
            lines.append(
                f"- {label} ({key}): analyst category `{row.category}`. Evidence ({row.source_document}, "
                f"{row.page_label}): {row.evidence_summary} Notes: {row.notes or 'none'}"
            )
        return "\n".join(lines)

    def _ai_estimate(self, bank: str, suggestions: Dict[str, str]) -> Dict[str, Any]:
        """Score the AI's suggested categories with the same engine (advisory, never the official score).

        Indicators the AI did not classify keep the evidence category.
        """
        evidence_categories = self.evidence.categories(bank)
        categories = {**evidence_categories, **suggestions}
        result = self.engine.score(categories, bank=bank).to_dict()
        result.pop("indicators")
        changed = [
            {
                "indicator": key,
                "label": RUBRIC_BY_KEY[key].label if key in RUBRIC_BY_KEY else "Controversy",
                "evidence_category": evidence_categories[key],
                "ai_category": categories[key],
            }
            for key in ALL_KEYS
            if categories[key] != evidence_categories[key]
        ]
        return {
            "scores": result,
            "changed": changed,
            "kept_from_evidence": [key for key in ALL_KEYS if key not in suggestions],
        }

    def _analysis_key(self, bank: str, question: Optional[str], pdf_text: Optional[str]) -> str:
        return f"{bank}:{self._hash(question)}:{self._hash(pdf_text)}"

    def _report_key(self, bank: str, news_summary: str) -> str:
        return f"report:{bank}:{self._hash(news_summary)}"

    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return copy.deepcopy(self.cache[key])

    def _cache_put(self, key: str, value: Dict[str, Any]) -> None:
        self.cache[key] = copy.deepcopy(value)
        self.cache.move_to_end(key)
        while len(self.cache) > MAX_CACHE_ENTRIES:
            self.cache.popitem(last=False)

    @staticmethod
    def _hash(text: Optional[str]) -> str:
        text = (text or "").strip()
        return hashlib.sha256(text.encode()).hexdigest()[:12] if text else "none"

    @staticmethod
    def _safe(fn: Callable[[], T], default: T, what: str) -> T:
        try:
            return fn()
        except Exception as exc:  # network sources are optional context
            print(f"[Server] {what} failed: {exc}")
            return default

    @staticmethod
    def _build_context_blob(
        evidence_text: str,
        yahoo_snapshot: str,
        news_summary: str,
        pdf_summary: str,
        question: Optional[str],
    ) -> str:
        focus = f"Focus question: {question}\n\n" if question else ""
        return (
            f"Assessment period: {REPORTING_YEAR}\n"
            f"{focus}"
            f"--- Reviewed evidence from the annual report (one row per indicator) ---\n{evidence_text}\n\n"
            f"--- ESG News Summary ---\n{news_summary or 'N/A'}\n\n"
            f"--- Summary of a PDF uploaded by the user ---\n{pdf_summary or 'N/A'}\n\n"
            f"--- Yahoo Snapshot ---\n{yahoo_snapshot or 'N/A'}\n"
        )

    @staticmethod
    def _news_items_for_ui(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        return [
            {
                "headline": it.get("title") or "",
                "url": it.get("link") or "",
                "source": it.get("source") or "",
                "published": it.get("published") or "",
            }
            for it in items
        ]

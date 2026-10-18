from __future__ import annotations

import copy
import hashlib
import json
import os
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from agents.chat_agent import ChatAgent, ChatContext
from agents.final_writer import FinalWriterAgent
from tools.ai_review import REVIEW_PATH, load_definitions, load_reviews, summarise
from tools.blind_review import BLIND_REVIEW_PATH, load_results as load_blind_results
from tools.evidence import EVIDENCE_PATH, REPORTING_YEAR, EvidenceRow, load_evidence
from tools.local_llm import LLMUnavailable, LocalLLM
from tools.quota import DailyLimitReached, DailyQuota
from tools.quotes import load_quote_checks
from tools.score_engine import CONTROVERSY_KEY, ScoreEngine, ScoreEngineConfig, allowed_categories
from tools.sensitivity import run_sensitivity

# Cached results (chat answers, reports, sensitivity); keep only the most recent ones.
MAX_CACHE_ENTRIES = 64


@dataclass
class ChatTurn:
    """One question and its answer. ``answer`` is None until the reply has been streamed."""

    question: str
    history: List[Tuple[str, str]]
    context: ChatContext
    cache_key: str
    answer: Optional[str] = None
    unknown_citations: List[str] = field(default_factory=list)
    unknown_numbers: List[str] = field(default_factory=list)
    from_cache: bool = False


class Server:
    """
    Central orchestrator.

    1. Scores: evidence table -> ScoreEngine. Deterministic, offline, and
       identical with or without the LLM.
    2. AI assistant (optional, advisory): a chat that answers questions from
       the evidence table, with the official score, the offline AI reviewer's
       score and scenario scores computed by the same engine (see
       ``agents/chat_agent.py``). A narrative report is written only on
       request. Uncached AI requests count against a site-wide daily limit
       (``AI_QUESTIONS_PER_DAY``, default 50).
    """

    def __init__(
        self,
        use_llm: Optional[bool] = None,
        evidence_path: Path | str = EVIDENCE_PATH,
        review_path: Path | str = REVIEW_PATH,
        blind_review_path: Path | str = BLIND_REVIEW_PATH,
        engine_config: Optional[ScoreEngineConfig] = None,
        daily_ai_limit: Optional[int] = None,
    ) -> None:
        """
        Parameters
        ----------
        use_llm : bool, optional
            ``False`` never contacts the LLM. ``None`` or ``True`` uses it only
            if it is configured and reachable.
        daily_ai_limit : int, optional
            AI requests allowed per UTC day for all visitors together. Defaults
            to the ``AI_QUESTIONS_PER_DAY`` environment variable, else 50.
        """
        self.evidence = load_evidence(evidence_path)
        # Offline AI evidence review (advisory only); empty if it has not been run.
        self.reviews = load_reviews(review_path)
        # Blind AI review (advisory only): the AI rated each row without seeing the analysts' category.
        self.blind_reviews = load_blind_results(blind_review_path)
        self.engine = ScoreEngine(engine_config)
        self.llm = LocalLLM()
        self.llm_mode = use_llm
        self.use_llm = False if use_llm is False else self.llm.is_available()

        self.chat = ChatAgent(self.llm, self.evidence, self.engine, self.ai_reviewer_categories(), load_definitions())
        self.chat.reviewer_note = self.ai_reviewer_note()
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
                    "quotes": self._quotes(row),
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
                "quotes": self._quotes(rows[CONTROVERSY_KEY]),
                "ai_review": self.reviews.get((bank, CONTROVERSY_KEY)),
            },
            "draft_indicators": [key for key, row in rows.items() if row.status != "confirmed"],
        }

    def ai_reviewer_categories(self) -> Dict[str, Dict[str, str]]:
        """The AI reviewer's own category for each row (only valid rubric values).

        Taken from the blind AI review when it has been run, otherwise from the
        AI evidence review, which was shown the analysts' category.
        """
        if self.blind_reviews:
            source, field_name = self.blind_reviews, "ai_category"
        else:
            source, field_name = self.reviews, "ai_suggested_category"
        categories: Dict[str, Dict[str, str]] = {}
        for (bank, key), review in source.items():
            category = review.get(field_name)
            if category in allowed_categories(key):
                categories.setdefault(bank, {})[key] = category
        return categories

    def ai_reviewer_note(self) -> str:
        """One sentence on where the AI reviewer score comes from, for the page and the chat prompt."""
        if self.blind_reviews:
            return (
                "AI reviewer: categories an AI chose blind, from the report pages and the written definitions only; "
                "it did not see the analysts' categories."
            )
        return (
            "AI reviewer: categories an offline AI review chose after reading each cited page; it was shown the "
            "analysts' category, so it is a second opinion, not a blind rating."
        )

    def chat_turn(self, question: str, history: Sequence[Tuple[str, str]] = ()) -> ChatTurn:
        """Prepare an answer: route the question and compute the scores.

        A question answered before (with the same recent history) comes back
        with its answer and uses no AI request. Otherwise one request of the
        daily limit is used, and the answer is produced by ``stream_answer``.
        """
        if not self.use_llm:
            raise LLMUnavailable("The AI assistant is off")
        history = [(q, a) for q, a in history][-2:]
        cache_key = "chat:" + hashlib.sha256(json.dumps([question.strip().lower(), history]).encode()).hexdigest()[:16]
        cached = self._cache_get(cache_key)
        if cached is not None:
            turn = cached["turn"]
            turn.from_cache = True
            return turn
        if not self.ai_quota.try_consume():
            raise DailyLimitReached(self.ai_quota.limit)
        try:
            route = self.chat.route(question, history)
        except LLMUnavailable:
            self.ai_quota.refund()  # nothing was answered, so the request does not count
            raise
        return ChatTurn(question=question, history=history, context=self.chat.context(route), cache_key=cache_key)

    def stream_answer(self, turn: ChatTurn) -> Iterator[str]:
        """Yield the answer as it is written; when complete, check its citations and cache the turn."""
        if turn.answer is not None:
            yield turn.answer
            return
        parts: List[str] = []
        try:
            for piece in self.chat.answer(turn.question, turn.history, turn.context):
                parts.append(piece)
                yield piece
        except LLMUnavailable:
            self.ai_quota.refund()  # no complete answer, so the request does not count
            raise
        turn.answer = "".join(parts).strip()
        turn.unknown_citations = self.chat.unknown_citations(turn.answer, turn.context)
        turn.unknown_numbers = self.chat.unknown_numbers(turn.answer, turn.context)
        self._cache_put(turn.cache_key, {"turn": turn})

    def write_report(self, bank: str) -> str:
        """Narrative report, written only on request (one AI request, cached per bank)."""
        cache_key = self._report_key(bank)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached["report"]
        if not self.use_llm:
            raise LLMUnavailable("The AI assistant is off")
        if not self.ai_quota.try_consume():
            raise DailyLimitReached(self.ai_quota.limit)
        scored = self.score_bank(bank)
        try:
            report = self.writer.run(bank=bank, scores=scored["scores"], breakdown=scored["breakdown"])
        except LLMUnavailable:
            self.ai_quota.refund()
            raise
        self._cache_put(cache_key, {"report": report})
        return report

    def has_cached_report(self, bank: str) -> bool:
        return self._report_key(bank) in self.cache

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

    def blind_review_summary(self) -> Dict[str, Any]:
        """Agreement of the blind AI review with the analysts; ``rows`` is 0 if it has not been run."""
        rows = list(self.blind_reviews.values())
        return {
            "rows": len(rows),
            "category_agrees": sum(bool(r["category_agrees"]) for r in rows),
            "quote_verified": sum(bool(r["quote_verified"]) for r in rows),
            "models": sorted({f"{r['provider']}/{r['model']}" for r in rows}),
            "reviewed_on": sorted({str(r["reviewed_on"]) for r in rows}),
            "disagreements": [dict(r) for r in rows if not r["category_agrees"]],
        }

    def quote_check_summary(self) -> Dict[str, int]:
        """How many verbatim excerpts in the evidence table were found on their PDF page."""
        checks = load_quote_checks()
        excerpts = sum(len(row.excerpts()) for row in self.evidence.rows)
        return {"excerpts": excerpts, "checked": len(checks), "verified": sum(c.verified for c in checks.values())}

    def sensitivity(self, banks: List[str]) -> Dict[str, Any]:
        """Weight and judgment sensitivity of the ranking and labels (see tools/sensitivity.py)."""
        cache_key = "sensitivity:" + "|".join(banks)
        cached = self._cache_get(cache_key)
        if cached is None:
            cached = run_sensitivity(self.evidence, banks, self.engine.cfg).to_dict()
            self._cache_put(cache_key, cached)
        return cached

    # Helpers
    @staticmethod
    def _quotes(row: EvidenceRow) -> List[Dict[str, Any]]:
        """Verbatim excerpts with links that open the PDF at their page."""
        return [
            {"page": page, "text": text, "page_url": f"{row.url}#page={page}" if row.url and page else ""}
            for page, text in row.excerpts()
        ]

    @staticmethod
    def _report_key(bank: str) -> str:
        return f"report:{bank}"

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

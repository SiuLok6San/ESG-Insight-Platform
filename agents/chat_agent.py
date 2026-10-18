"""Chat assistant: answers questions about the three banks with evidence and scores.

One turn has three steps:

1. **Route**: which banks and indicators the question is about. Ordinary
   questions are routed in code (bank names and topic keywords). Only a
   "what if" question costs one short LLM call (JSON), to map the
   hypothetical to rubric category changes; every value is checked against
   the rubric, and anything else is dropped and reported. Fewer calls matter
   on a free tier that serves one request at a time.
2. **Compute** (no LLM): official scores from the evidence table, the AI
   reviewer's score (a second opinion), and the scenario score, all from the same
   scoring engine. The model never produces a number.
3. **Answer** (one streamed LLM call): plain-English answer that may use only
   the evidence rows, quotes and scores computed in step 2, citing pages.
   Afterwards, page citations that are not in the evidence are flagged.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from tools.dutch_banks import resolve_bank
from tools.evidence import EvidenceTable
from tools.local_llm import LLMBusy
from tools.score_engine import ALL_KEYS, NOT_DISCLOSED, RUBRIC_BY_KEY, BankScore, ScoreEngine, allowed_categories, round1

INTENTS = ("explain", "compare", "what_if", "other")
HISTORY_TURNS = 2  # earlier question/answer pairs passed to the model for follow-up questions

# Wording that suggests a hypothetical ("what if", "would ... score", "suppose"); only these questions use the LLM router.
WHAT_IF = re.compile(r"\b(if|would|suppose|supposing|imagine|hypothetical(?:ly)?|scenario|were to)\b", re.I)
# Words that refer back to a bank named in the previous question.
FOLLOW_UP = re.compile(r"\b(its|it|they|their|them|that bank|this bank|the bank|same)\b", re.I)
# Words that refer back to the previous question's topic ("How does Rabobank do on that?").
SAME_TOPIC = re.compile(r"\b(that|this|those|these|same)\b", re.I)
PILLAR_KEYS = {
    "E": ("climate_plan", "emission_disclosure", "financed_emissions", "taxonomy_alignment", "risk_management", "fossil_policy"),
    "S": ("diversity_inclusion", "labor_rights", "customer_protection", "aml_maturity"),
    "G": ("board_independence", "esg_oversight", "exec_comp_esg", "transparency_csrd"),
}
# Topic keywords -> indicators whose evidence (with all quotes) is given to the model.
INDICATOR_KEYWORDS = (
    (r"\bclimate\b|\benvironment(?:al)?\b|\bE pillar\b", PILLAR_KEYS["E"]),
    (r"\bsocial\b|\bS pillar\b", PILLAR_KEYS["S"]),
    (r"\bgovernance\b|\bG pillar\b", PILLAR_KEYS["G"]),
    (r"transition plan|\bsbti\b|net[ -]zero|decarboni[sz]", ("climate_plan",)),
    (r"\bemission|\bscope [123]|\bghg\b|carbon footprint", ("emission_disclosure", "financed_emissions")),
    (r"\bfinanced emissions|\bpcaf\b", ("financed_emissions",)),
    (r"\btaxonomy\b|green asset|\bgar\b", ("taxonomy_alignment",)),
    (r"risk management|climate risk|stress test|risk appetite", ("risk_management",)),
    (r"\bfossil|\bcoal\b|\boil\b|\bgas\b", ("fossil_policy",)),
    (r"\bdiversity\b|\bgender\b|pay gap|\bwomen\b|\binclusion\b", ("diversity_inclusion",)),
    (r"\blabou?r\b|works council|collective|human rights|\bworkforce\b|\bemployees?\b", ("labor_rights",)),
    (r"\bcustomers?\b|\bconsumers?\b|complaints?|duty of care|\bclients?\b", ("customer_protection",)),
    (r"\baml\b|money laundering|financial crime|\bkyc\b", ("aml_maturity",)),
    (r"\bboard\b|independen", ("board_independence",)),
    (r"oversight|sustainability committee|esg committee", ("esg_oversight",)),
    (r"executive pay|\bremuneration\b|\bbonus|variable pay|\bexecutives?\b|\bceo\b", ("exec_comp_esg",)),
    (r"\bcsrd\b|\besrs\b|assurance|transparen", ("transparency_csrd",)),
    (r"controvers|lawsuit|litigation|\bfines?\b|prosecut|legal|court|scandal", ("controversy",)),
)

ROUTER_SYSTEM = (
    "You map a user's question about the ESG benchmark of three Dutch banks to JSON. "
    "Use only the bank names, indicator keys and category values listed. Reply with one JSON object."
)


def label(key: str) -> str:
    return RUBRIC_BY_KEY[key].label if key in RUBRIC_BY_KEY else "Controversy"


@dataclass
class Route:
    banks: List[str]
    indicators: List[str]
    intent: str
    scenario: Dict[str, Dict[str, str]] = field(default_factory=dict)
    rejected: List[str] = field(default_factory=list)  # model output that failed validation


@dataclass
class BankCard:
    bank: str
    official: BankScore
    ai_reviewer: BankScore
    ai_reviewer_differs: List[Tuple[str, str, str]]  # (indicator, official category, AI reviewer category)
    scenario: Optional[BankScore] = None
    scenario_changes: List[Tuple[str, str, str]] = field(default_factory=list)  # (indicator, from, to)


@dataclass
class ChatContext:
    route: Route
    cards: List[BankCard]
    ranking: List[str]  # official ranking of all banks
    scenario_ranking: Optional[List[str]]  # ranking with the scenario applied, if any bank changed
    evidence_text: str
    pages: Dict[str, List[int]]  # bank -> pages quoted in the evidence given to the model


def _ranking(scores: Mapping[str, BankScore]) -> List[str]:
    return sorted(scores, key=lambda b: (-scores[b].final, b))


class ChatAgent:
    def __init__(
        self,
        llm,
        evidence: EvidenceTable,
        engine: ScoreEngine,
        ai_reviewer_categories: Mapping[str, Mapping[str, str]],
        definitions: Mapping[str, str],
    ) -> None:
        self.llm = llm
        self.evidence = evidence
        self.engine = engine
        self.ai_reviewer_categories = ai_reviewer_categories
        self.definitions = definitions
        self.reviewer_note = "AI reviewer: categories chosen by an AI review of the cited pages."

    # Step 1: route
    @staticmethod
    def needs_router(question: str, history: Sequence[Tuple[str, str]] = ()) -> bool:
        """True for a "what if" question, or a short follow-up to one; only these use the LLM router."""
        if WHAT_IF.search(question):
            return True
        previous = list(history)[-1][0] if history else ""
        return bool(previous) and bool(WHAT_IF.search(previous)) and len(question.split()) <= 8

    def route_in_code(self, question: str, history: Sequence[Tuple[str, str]] = ()) -> Route:
        """Route an ordinary question without the LLM: bank names and topic keywords.

        No bank named means all banks, unless the question refers back ("its",
        "they") to the bank of the previous question. A short follow-up with no
        topic of its own ("And Rabobank?", "How does Rabobank do on that?") keeps
        the previous question's topic.
        """
        previous = list(history)[-1][0] if history else ""
        banks = self._banks_named_in(question, ())
        if not banks and previous and FOLLOW_UP.search(question):
            banks = self._banks_named_in(previous, ())
        indicators = self.indicators_named_in(question)
        if not indicators and previous and (len(question.split()) <= 6 or SAME_TOPIC.search(question)):
            indicators = self.indicators_named_in(previous)
        return Route(banks=banks, indicators=indicators, intent="explain" if len(banks) == 1 else "compare")

    @staticmethod
    def indicators_named_in(text: str) -> List[str]:
        found: List[str] = []
        for pattern, keys in INDICATOR_KEYWORDS:
            if re.search(pattern, text, re.I):
                found += [k for k in keys if k not in found]
        return [k for k in ALL_KEYS if k in found]  # rubric order

    def route(self, question: str, history: Sequence[Tuple[str, str]] = ()) -> Route:
        """Route in code, or for a what-if question ask the LLM; fall back to code if the LLM's reply is unusable."""
        if not self.needs_router(question, history):
            return self.route_in_code(question, history)
        try:
            raw = self.llm.ask_json(ROUTER_SYSTEM, self._router_prompt(question, history))
        except LLMBusy:
            raise  # the answer call would hit the same busy service; stop now
        except Exception as exc:  # routing is best effort; the answer step still works
            route = self.route_in_code(question, history)
            route.rejected.append(f"routing failed: {exc}")
            return route
        return self.validate_route(raw, question, history)

    def _router_prompt(self, question: str, history: Sequence[Tuple[str, str]]) -> str:
        indicators = {
            key: {"label": label(key), "categories": list(allowed_categories(key)), "definition": self.definitions.get(key, "")}
            for key in ALL_KEYS
        }
        earlier = "\n".join(f"Q: {q}" for q, _ in list(history)[-HISTORY_TURNS:]) or "(none)"
        return (
            f"Banks: {json.dumps(self.evidence.banks())}\n"
            f"Indicators: {json.dumps(indicators)}\n\n"
            f"Earlier questions in this conversation:\n{earlier}\n\n"
            f"Question: {question}\n\n"
            "Return JSON with these keys:\n"
            '- "banks": the banks the question is about (empty list if it is about all three or none in particular). '
            'For a follow-up that refers to a bank from an earlier question (e.g. "its", "that bank"), include that bank;\n'
            '- "indicators": the indicator keys the question is about (empty list if it is about the overall score);\n'
            '- "intent": "explain" (why a bank scores as it does), "compare" (banks against each other), '
            '"what_if" (a hypothetical change), or "other";\n'
            '- "scenario": only for "what_if", {"<bank>": {"<indicator>": "<category>"}} with the category each '
            "changed indicator would get under the hypothetical, chosen from that indicator's categories and "
            "definition; otherwise {}."
        )

    def validate_route(self, raw: Mapping, question: str, history: Sequence[Tuple[str, str]] = ()) -> Route:
        rejected: List[str] = []
        banks: List[str] = []
        for name in raw.get("banks") or []:
            bank = self._known_bank(name)
            if bank and bank not in banks:
                banks.append(bank)
            elif not bank:
                rejected.append(f"unknown bank {name!r}")
        indicators = []
        for key in raw.get("indicators") or []:
            if key in ALL_KEYS and key not in indicators:
                indicators.append(key)
            elif key not in ALL_KEYS:
                rejected.append(f"unknown indicator {key!r}")
        intent = raw.get("intent") if raw.get("intent") in INTENTS else "other"

        scenario: Dict[str, Dict[str, str]] = {}
        raw_scenario = raw.get("scenario") if isinstance(raw.get("scenario"), Mapping) else {}
        for name, changes in raw_scenario.items():
            bank = self._known_bank(name)
            if not bank or not isinstance(changes, Mapping):
                rejected.append(f"scenario for unknown bank {name!r}")
                continue
            for key, category in changes.items():
                if key in ALL_KEYS and category in allowed_categories(key) and category != NOT_DISCLOSED:
                    scenario.setdefault(bank, {})[key] = category
                else:
                    rejected.append(f"scenario value {key}={category!r} for {bank} is not in the rubric")
        for bank in scenario:
            if bank not in banks:
                banks.append(bank)
        if not banks:
            # The model may miss a bank named in the question; an empty list otherwise means all banks.
            banks = self._banks_named_in(question, ())
        return Route(banks=banks, indicators=indicators, intent=intent, scenario=scenario, rejected=rejected)

    def _known_bank(self, name: object) -> Optional[str]:
        bank = resolve_bank(str(name)) if name else None
        return bank if bank in self.evidence.banks() else None

    def _banks_named_in(self, question: str, history: Sequence[Tuple[str, str]]) -> List[str]:
        """Banks named in the question (or, for a follow-up, in the previous question)."""
        texts = [question] + [q for q, _ in reversed(list(history)[-1:])]
        for text in texts:
            words = re.findall(r"[a-z]+", text.lower())
            found = []
            for bank in self.evidence.banks():
                first = bank.split()[0].lower()
                if first in words or bank.lower() in text.lower() or (first == "rabobank" and "rabo" in words):
                    found.append(bank)
            if found:
                return found
        return []

    # Step 2: compute
    def context(self, route: Route) -> ChatContext:
        banks = route.banks or self.evidence.banks()
        official = {b: self.engine.score(self.evidence.categories(b), b) for b in self.evidence.banks()}
        cards = []
        for bank in banks:
            evidence_cats = self.evidence.categories(bank)
            reviewer_cats = {**evidence_cats, **self.ai_reviewer_categories.get(bank, {})}
            card = BankCard(
                bank=bank,
                official=official[bank],
                ai_reviewer=self.engine.score(reviewer_cats, bank),
                ai_reviewer_differs=[(k, evidence_cats[k], reviewer_cats[k]) for k in ALL_KEYS if reviewer_cats[k] != evidence_cats[k]],
            )
            changes = route.scenario.get(bank, {})
            if changes:
                card.scenario = self.engine.score({**evidence_cats, **changes}, bank)
                card.scenario_changes = [(k, evidence_cats[k], v) for k, v in changes.items()]
            cards.append(card)

        scenario_ranking = None
        if any(c.scenario for c in cards):
            with_scenario = dict(official)
            with_scenario.update({c.bank: c.scenario for c in cards if c.scenario})
            scenario_ranking = _ranking(with_scenario)
        # Indicators changed by the scenario are part of the question even if the router did not list them.
        focus = list(dict.fromkeys(list(route.indicators) + [k for c in route.scenario.values() for k in c]))
        evidence_text, pages = self._evidence_block(banks, focus)
        return ChatContext(
            route=route,
            cards=cards,
            ranking=_ranking(official),
            scenario_ranking=scenario_ranking,
            evidence_text=evidence_text,
            pages=pages,
        )

    def _evidence_block(self, banks: Sequence[str], indicators: Sequence[str]) -> Tuple[str, Dict[str, List[int]]]:
        keys = list(indicators) or list(ALL_KEYS)
        lines: List[str] = []
        pages: Dict[str, List[int]] = {}
        for bank in banks:
            rows = self.evidence.for_bank(bank)
            for key in keys:
                row = rows[key]
                excerpts = row.excerpts() if indicators else row.excerpts()[:1]  # all quotes when focused
                quotes = " ".join(f'"{text}" (p. {page})' for page, text in excerpts)
                pages.setdefault(bank, []).extend(p for p, _ in excerpts if p)
                lines.append(
                    f"- {bank} | {label(key)} ({key}) | category `{row.category}` | {row.evidence_summary} "
                    f"Quotes: {quotes}"
                )
        return "\n".join(lines), {b: sorted(set(p)) for b, p in pages.items()}

    # Step 3: answer
    def messages(self, question: str, history: Sequence[Tuple[str, str]], ctx: ChatContext) -> List[Dict[str, str]]:
        system = (
            "You are the assistant of an evidence-based ESG benchmark of ING Group, ABN AMRO and Rabobank, built "
            "from their FY2025 annual reports. Answer in plain English, at most about 200 words.\n"
            "Rules:\n"
            "- Use only the EVIDENCE and SCORES below. Do not use outside knowledge.\n"
            "- Cite the bank and page for every fact from the evidence, like (ING Group, p. 111). Do not cite or "
            "name the SCORES or EVIDENCE sections; scores need no citation.\n"
            "- Every number you mention must appear in the SCORES or EVIDENCE. Never compute or estimate a score.\n"
            "- The official score comes from the analysts' evidence table. "
            f"The AI reviewer score is the same engine applied to other categories ({self.reviewer_note}) "
            "A scenario score is hypothetical, computed by the scoring engine from the listed category changes.\n"
            "- For a what-if question, say which categories change and what the scenario score is.\n"
            "- If the evidence does not answer the question, say so plainly."
        )
        messages = [{"role": "system", "content": system}]
        for q, a in list(history)[-HISTORY_TURNS:]:
            messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a[:800]}]
        messages.append({"role": "user", "content": f"{self.facts(ctx)}\n\nQUESTION: {question}"})
        return messages

    @staticmethod
    def facts(ctx: ChatContext) -> str:
        lines = ["SCORES (0-100; label: Meet >= 75, Almost Meet >= 50, otherwise Not Meet)"]
        lines.append("Official ranking: " + ", ".join(f"{i}. {b}" for i, b in enumerate(ctx.ranking, 1)))
        for card in ctx.cards:
            o, r = card.official, card.ai_reviewer
            lines.append(
                # Pillars rounded half-up like everywhere else in the app (84.25 -> 84.3, not 84.2).
                f"- {card.bank}: official {o.final:.1f} ({o.label}; E {round1(o.pillars['E']):.1f}, "
                f"S {round1(o.pillars['S']):.1f}, G {round1(o.pillars['G']):.1f}, "
                f"controversy {o.controversy} -{o.controversy_deduction:g}); "
                f"AI reviewer {r.final:.1f} ({r.label})"
            )
            if card.ai_reviewer_differs:
                diffs = "; ".join(f"{label(k)}: {a} vs AI {b}" for k, a, b in card.ai_reviewer_differs)
                lines.append(f"  AI reviewer differs on: {diffs}")
            if card.scenario:
                changes = "; ".join(f"{label(k)}: {a} -> {b}" for k, a, b in card.scenario_changes)
                lines.append(
                    f"  SCENARIO (hypothetical): {changes}. Scenario score {card.scenario.final:.1f} "
                    f"({card.scenario.label}), change {card.scenario.final - o.final:+.1f}"
                )
        if ctx.scenario_ranking and ctx.scenario_ranking != ctx.ranking:
            lines.append("Ranking with the scenario: " + ", ".join(f"{i}. {b}" for i, b in enumerate(ctx.scenario_ranking, 1)))
        return "\n".join(lines) + "\n\nEVIDENCE (analysts' evidence table with verbatim quotes)\n" + ctx.evidence_text

    def answer(self, question: str, history: Sequence[Tuple[str, str]], ctx: ChatContext) -> Iterator[str]:
        yield from self.llm.stream(self.messages(question, history, ctx))

    @staticmethod
    def unknown_citations(answer: str, ctx: ChatContext) -> List[str]:
        """Page citations ("p. 999", "ING Group, p. 999") whose page is not in the evidence the model was given."""
        known = {(b, p) for b, pages in ctx.pages.items() for p in pages}
        all_pages = {p for _, p in known}
        names = sorted({b for b, _ in known} | {b.split()[0] for b, _ in known}, key=len, reverse=True)
        bank_re = "|".join(re.escape(n) for n in names) or "(?!)"
        problems = []
        for match in re.finditer(rf"(?:\b({bank_re})\b[^()\d;]{{0,12}}?)?\bpp?\.\s*(\d+)", answer):
            bank = resolve_bank(match.group(1)) if match.group(1) else None
            page = int(match.group(2))
            if not ((bank, page) in known if bank else page in all_pages):
                problems.append(match.group(0).strip())
        return problems

    @staticmethod
    def unknown_numbers(answer: str, ctx: ChatContext) -> List[str]:
        """Numbers in the answer that appear nowhere in the scores or evidence the model was given.

        Page numbers and small whole numbers (counts such as "two indicators") are not checked.
        """
        known = {_number_value(m.group(0)) for m in _NUMBER.finditer(ChatAgent.facts(ctx))}
        pages = [m.span(2) for m in re.finditer(r"\b(pp?)\.\s*(\d+(?:\s*[-–]\s*\d+)?)", answer)]
        flagged: List[str] = []
        for m in _NUMBER.finditer(answer):
            if any(start <= m.start() < end for start, end in pages):
                continue
            value = _number_value(m.group(0))
            if value is None or (float(value).is_integer() and abs(value) < 10):
                continue
            if value not in known and m.group(0) not in flagged:
                flagged.append(m.group(0))
        return flagged


# Numbers such as 72.1, +3.5, -2, 14%, 1,268 or 704.5 (signs and % are ignored when comparing).
_NUMBER = re.compile(r"(?<![\w.])[+−-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?<![\w.])[+−-]?\d+(?:\.\d+)?%?")


def _number_value(text: str) -> Optional[float]:
    try:
        return abs(float(text.replace("−", "-").replace(",", "").rstrip("%")))
    except ValueError:
        return None

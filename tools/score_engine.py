"""Deterministic, evidence-based ESG scoring.

Scores are computed only from rubric categories (one per indicator), which
come from the reviewed evidence table in ``data/evidence/esg_evidence.csv``.
The mapping from category to score is a fixed lookup table: there is no
randomness and no LLM input anywhere in this module.

Model
-----
- 14 rubric indicators, grouped into three pillars (E, S, G). Each pillar
  score is the weighted average of its indicator scores (0-100).
- The weighted score combines the pillars (default 35% E / 30% S / 35% G).
- A controversy adjustment is subtracted from the weighted score.
- The final score is clamped to 0-100 and rounded to one decimal, and the
  compliance label is assigned from that rounded value.

Category definitions are documented in ``data/evidence/category_definitions.md``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Mapping, Optional, Tuple

NOT_DISCLOSED = "not_disclosed"
PILLARS: Tuple[str, ...] = ("E", "S", "G")
PILLAR_NAMES: Dict[str, str] = {"E": "Environmental", "S": "Social", "G": "Governance"}


@dataclass(frozen=True)
class Indicator:
    """One rubric indicator: its pillar, weight within the pillar, and the
    score for each allowed category (listed from weakest to strongest)."""

    key: str
    pillar: str
    label: str
    weight: float
    scores: Mapping[str, int]

    @property
    def categories(self) -> Tuple[str, ...]:
        return tuple(self.scores)

    def score(self, category: str) -> int:
        """Score for a category; ``not_disclosed`` gets the lowest score."""
        if category == NOT_DISCLOSED:
            return min(self.scores.values())
        if category not in self.scores:
            raise ValueError(
                f"Invalid category {category!r} for indicator {self.key!r}; "
                f"allowed: {', '.join(self.categories)} or {NOT_DISCLOSED}"
            )
        return self.scores[category]


RUBRIC: Tuple[Indicator, ...] = (
    # Environmental
    Indicator("climate_plan", "E", "Climate transition plan", 0.20,
              {"none": 10, "weak": 40, "science_based": 75, "sbt_aligned": 90}),
    Indicator("emission_disclosure", "E", "Emissions disclosure", 0.20,
              {"none": 5, "scope1": 40, "scope1_2": 70, "scope1_2_3": 90}),
    Indicator("financed_emissions", "E", "Financed emissions", 0.20,
              {"none": 10, "partial": 60, "pcaf_full": 85}),
    Indicator("taxonomy_alignment", "E", "EU Taxonomy alignment", 0.15,
              {"none": 20, "low": 45, "medium": 65, "high": 80, "aligned": 90}),
    Indicator("risk_management", "E", "Climate risk management", 0.15,
              {"none": 20, "weak": 45, "partial": 60, "full": 75, "strong": 90}),
    Indicator("fossil_policy", "E", "Fossil fuel policy", 0.10,
              {"none": 20, "weak": 40, "partial": 60, "strong": 80, "exit": 90}),
    # Social
    Indicator("diversity_inclusion", "S", "Diversity & inclusion", 0.25,
              {"none": 20, "partial": 55, "full": 80}),
    Indicator("labor_rights", "S", "Labour rights", 0.25,
              {"none": 20, "weak": 45, "medium": 65, "strong": 85}),
    Indicator("customer_protection", "S", "Customer protection", 0.25,
              {"fined": 30, "building": 60, "mature": 80}),
    Indicator("aml_maturity", "S", "AML maturity", 0.25,
              {"fined": 25, "weak": 40, "building": 60, "mature": 75, "leading": 90}),
    # Governance
    Indicator("board_independence", "G", "Board independence", 0.25,
              {"<33": 45, "33_50": 65, ">=50": 80}),
    Indicator("esg_oversight", "G", "ESG oversight", 0.25,
              {"none": 30, "csr_dept": 60, "board_committee": 80}),
    Indicator("exec_comp_esg", "G", "ESG-linked executive pay", 0.25,
              {"none": 40, "<20": 60, ">=20": 80}),
    Indicator("transparency_csrd", "G", "CSRD transparency", 0.25,
              {"non_compliant": 30, "partial": 60, "full": 80}),
)
RUBRIC_BY_KEY: Dict[str, Indicator] = {ind.key: ind for ind in RUBRIC}

CONTROVERSY_KEY = "controversy"
# Points subtracted from the weighted E/S/G score.
CONTROVERSY_DEDUCTION: Dict[str, float] = {"none": 0.0, "moderate": 2.0, "severe": 5.0}

# Compliance label thresholds, checked from the top down.
LABEL_THRESHOLDS: Tuple[Tuple[float, str], ...] = ((75.0, "Meet"), (50.0, "Almost Meet"))
LOWEST_LABEL = "Not Meet"

ALL_KEYS: Tuple[str, ...] = tuple(ind.key for ind in RUBRIC) + (CONTROVERSY_KEY,)


def allowed_categories(key: str) -> Tuple[str, ...]:
    """Allowed categories for any evidence-table key, including ``not_disclosed``."""
    if key == CONTROVERSY_KEY:
        return tuple(CONTROVERSY_DEDUCTION) + (NOT_DISCLOSED,)
    if key not in RUBRIC_BY_KEY:
        raise KeyError(f"Unknown indicator {key!r}")
    return RUBRIC_BY_KEY[key].categories + (NOT_DISCLOSED,)


def controversy_deduction(category: str) -> float:
    """Points subtracted for a controversy category; ``not_disclosed`` gets the largest."""
    if category == NOT_DISCLOSED:
        return max(CONTROVERSY_DEDUCTION.values())
    if category not in CONTROVERSY_DEDUCTION:
        raise ValueError(
            f"Invalid controversy category {category!r}; allowed: "
            f"{', '.join(CONTROVERSY_DEDUCTION)} or {NOT_DISCLOSED}"
        )
    return CONTROVERSY_DEDUCTION[category]


def round1(value: float) -> float:
    """Round to one decimal, halves away from zero (84.25 -> 84.3)."""
    return float(Decimal(repr(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def compliance_label(final_score: float) -> str:
    for threshold, label in LABEL_THRESHOLDS:
        if final_score >= threshold:
            return label
    return LOWEST_LABEL


@dataclass(frozen=True)
class ScoreEngineConfig:
    """Pillar weights (default 35/30/35). They must sum to 1."""

    w_E: float = 0.35
    w_S: float = 0.30
    w_G: float = 0.35

    def __post_init__(self) -> None:
        weights = (self.w_E, self.w_S, self.w_G)
        if any(w < 0 for w in weights) or abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError(f"Pillar weights must be non-negative and sum to 1, got {weights}")

    def weight(self, pillar: str) -> float:
        return {"E": self.w_E, "S": self.w_S, "G": self.w_G}[pillar]


@dataclass(frozen=True)
class IndicatorScore:
    key: str
    pillar: str
    label: str
    weight: float
    category: str
    score: float
    not_disclosed: bool


@dataclass(frozen=True)
class BankScore:
    bank: str
    pillars: Dict[str, float]  # exact pillar scores
    weighted: float  # weighted E/S/G score before the controversy adjustment
    controversy: str
    controversy_deduction: float
    final: float  # clamped and rounded to one decimal
    label: str
    indicators: List[IndicatorScore] = field(default_factory=list)
    engine_version: str = ""

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["pillars"] = {p: round1(v) for p, v in self.pillars.items()}
        data["weighted"] = round1(self.weighted)
        return data


class ScoreEngine:
    """Turns one bank's rubric categories into pillar scores, a final score and a label."""

    VERSION = "v4.0-evidence"

    def __init__(self, cfg: ScoreEngineConfig | None = None) -> None:
        self.cfg = cfg or ScoreEngineConfig()

    def score(
        self,
        categories: Mapping[str, str],
        bank: str = "",
        score_overrides: Optional[Mapping[str, float]] = None,
    ) -> BankScore:
        """Score one bank.

        ``categories`` must contain exactly one category for each rubric
        indicator plus ``controversy``. Missing, unknown or invalid entries
        raise ``ValueError``: nothing is filled in silently.

        ``score_overrides`` (indicator key -> 0-100 score) replaces the
        category score of those indicators. It is only used to analyse
        alternative scoring rules (``scripts/scoring_options.py``); the
        official scores never pass it.
        """
        overrides = dict(score_overrides or {})
        bad = {k: v for k, v in overrides.items() if k not in RUBRIC_BY_KEY or not 0 <= v <= 100}
        if bad:
            raise ValueError(f"{bank or 'bank'}: invalid score overrides {bad}")
        missing = [k for k in ALL_KEYS if k not in categories]
        unknown = [k for k in categories if k not in ALL_KEYS]
        if missing or unknown:
            raise ValueError(f"{bank or 'bank'}: missing indicators {missing}, unknown keys {unknown}")

        indicators: List[IndicatorScore] = []
        for ind in RUBRIC:
            category = categories[ind.key]
            indicators.append(
                IndicatorScore(
                    key=ind.key,
                    pillar=ind.pillar,
                    label=ind.label,
                    weight=ind.weight,
                    category=category,
                    score=overrides.get(ind.key, ind.score(category)),
                    not_disclosed=category == NOT_DISCLOSED,
                )
            )

        pillars: Dict[str, float] = {}
        for pillar in PILLARS:
            items = [i for i in indicators if i.pillar == pillar]
            total_weight = sum(i.weight for i in items)
            pillars[pillar] = sum(i.score * i.weight for i in items) / total_weight

        weighted = sum(self.cfg.weight(p) * pillars[p] for p in PILLARS)
        controversy = categories[CONTROVERSY_KEY]
        deduction = controversy_deduction(controversy)
        final = round1(min(100.0, max(0.0, weighted - deduction)))

        return BankScore(
            bank=bank,
            pillars=pillars,
            weighted=weighted,
            controversy=controversy,
            controversy_deduction=deduction,
            final=final,
            label=compliance_label(final),
            indicators=indicators,
            engine_version=self.VERSION,
        )

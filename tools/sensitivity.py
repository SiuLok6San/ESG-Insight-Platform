"""Sensitivity analysis: how robust are the bank ranking and the labels?

Two checks, both run on the evidence table with the deterministic ScoreEngine:

1. Weight sensitivity. Each pillar weight is moved by -10, -5, 0, +5 or +10
   percentage points independently, and the three weights are then
   renormalised to sum to 1. Around the default 35/30/35 this gives 121
   unique scenarios. We report how often the bank ranking stays the same.
2. Judgment sensitivity. Every category judgment (bank x indicator,
   including controversy) is moved one step up and one step down, one at a
   time, with the default weights. We report which single moves would
   change the ranking or a compliance label.

The ranking uses the displayed one-decimal final score. If two banks tie,
the ranking counts as changed (the conservative choice).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from itertools import product
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from tools.evidence import EvidenceTable
from tools.score_engine import (
    ALL_KEYS,
    CONTROVERSY_DEDUCTION,
    CONTROVERSY_KEY,
    NOT_DISCLOSED,
    RUBRIC_BY_KEY,
    ScoreEngine,
    ScoreEngineConfig,
)

WEIGHT_STEPS_PP: Tuple[int, ...] = (-10, -5, 0, 5, 10)
Ranking = Optional[Tuple[str, ...]]


def ranking_of(finals: Mapping[str, float]) -> Ranking:
    """Banks ordered by final score, highest first; ``None`` if any two banks tie."""
    values = list(finals.values())
    if len(set(values)) < len(values):
        return None
    return tuple(sorted(finals, key=lambda bank: -finals[bank]))


def weight_scenarios(
    base: Optional[ScoreEngineConfig] = None,
    steps_pp: Sequence[int] = WEIGHT_STEPS_PP,
) -> List[ScoreEngineConfig]:
    """All unique renormalised weight combinations around ``base``."""
    base = base or ScoreEngineConfig()
    unique: Dict[Tuple[float, ...], ScoreEngineConfig] = {}
    for d_e, d_s, d_g in product(steps_pp, repeat=3):
        raw = (base.w_E + d_e / 100, base.w_S + d_s / 100, base.w_G + d_g / 100)
        if min(raw) <= 0:
            continue
        total = sum(raw)
        weights = tuple(w / total for w in raw)
        unique.setdefault(tuple(round(w, 9) for w in weights), ScoreEngineConfig(*weights))
    return list(unique.values())


def ordered_categories(key: str) -> Tuple[str, ...]:
    """Categories of an evidence-table key from weakest to strongest."""
    if key == CONTROVERSY_KEY:
        return tuple(sorted(CONTROVERSY_DEDUCTION, key=lambda c: -CONTROVERSY_DEDUCTION[c]))
    ind = RUBRIC_BY_KEY[key]
    return tuple(sorted(ind.categories, key=lambda c: ind.scores[c]))


def one_step_moves(key: str, category: str) -> List[Tuple[str, str]]:
    """(direction, new category) pairs one step away from ``category``."""
    order = ordered_categories(key)
    if category == NOT_DISCLOSED:
        return [("up", order[0])]
    i = order.index(category)
    moves = []
    if i > 0:
        moves.append(("down", order[i - 1]))
    if i < len(order) - 1:
        moves.append(("up", order[i + 1]))
    return moves


def indicator_label(key: str) -> str:
    return RUBRIC_BY_KEY[key].label if key in RUBRIC_BY_KEY else "Controversy"


@dataclass(frozen=True)
class WeightResult:
    weights: Dict[str, float]
    finals: Dict[str, float]
    labels: Dict[str, str]
    ranking: Ranking
    ranking_unchanged: bool


@dataclass(frozen=True)
class JudgmentMove:
    bank: str
    indicator: str
    direction: str
    from_category: str
    to_category: str
    final_before: float
    final_after: float
    label_before: str
    label_after: str
    ranking: Ranking
    changes_ranking: bool
    changes_label: bool


@dataclass(frozen=True)
class SensitivityReport:
    banks: List[str]
    base_weights: Dict[str, float]
    base_finals: Dict[str, float]
    base_labels: Dict[str, str]
    base_ranking: Ranking
    weight_results: List[WeightResult]
    moves: List[JudgmentMove]

    @property
    def weight_unchanged_count(self) -> int:
        return sum(r.ranking_unchanged for r in self.weight_results)

    @property
    def weight_unchanged_share(self) -> float:
        return self.weight_unchanged_count / len(self.weight_results) if self.weight_results else 1.0

    def ranking_moves(self) -> List[JudgmentMove]:
        return [m for m in self.moves if m.changes_ranking]

    def label_moves(self) -> List[JudgmentMove]:
        return [m for m in self.moves if m.changes_label]

    def decisive_indicators(self) -> List[Tuple[str, int]]:
        """Indicators whose one-step moves change the ranking, most often first."""
        counts = Counter(m.indicator for m in self.ranking_moves())
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    def label_flips_by_weight(self) -> Dict[str, int]:
        return {
            bank: sum(r.labels[bank] != self.base_labels[bank] for r in self.weight_results)
            for bank in self.banks
        }

    def final_ranges(self) -> Dict[str, Tuple[float, float]]:
        return {
            bank: (
                min(r.finals[bank] for r in self.weight_results),
                max(r.finals[bank] for r in self.weight_results),
            )
            for bank in self.banks
        }

    def summary(self) -> List[str]:
        n = len(self.weight_results)
        lines: List[str] = []
        if self.base_ranking is None:
            lines.append("At the default weights at least two banks tie, so there is no strict ranking.")
        elif len(self.banks) > 1:
            order = " > ".join(self.base_ranking)
            gaps = ", ".join(
                f"{a} vs {b} {self.base_finals[a] - self.base_finals[b]:.1f} points"
                for a, b in zip(self.base_ranking, self.base_ranking[1:])
            )
            lines.append(
                f"The ranking {order} is unchanged in {self.weight_unchanged_count} of {n} weight scenarios "
                f"({self.weight_unchanged_share:.0%}). Score gaps: {gaps}."
            )
            ranking_moves = self.ranking_moves()
            if ranking_moves:
                changes = "; ".join(
                    f"{m.bank} {indicator_label(m.indicator).lower()} {m.from_category} → {m.to_category}"
                    for m in ranking_moves
                )
                decisive = ", ".join(
                    f"{indicator_label(k)} ({c} move{'s' if c > 1 else ''})" for k, c in self.decisive_indicators()
                )
                lines.append(
                    f"{len(ranking_moves)} of {len(self.moves)} single one-step judgment changes would change the "
                    f"ranking ({changes}). Most decisive indicators: {decisive}."
                )
            else:
                lines.append(f"None of the {len(self.moves)} single one-step judgment changes would change the ranking.")

        flips = self.label_flips_by_weight()
        for bank in self.banks:
            label_moves = [m for m in self.label_moves() if m.bank == bank]
            if flips[bank] or label_moves:
                lines.append(
                    f"{bank}'s label ({self.base_labels[bank]}, {self.base_finals[bank]:.1f}) changes in "
                    f"{flips[bank]} of {n} weight scenarios and with {len(label_moves)} single one-step "
                    f"judgment change(s)."
                )
        return lines

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data.update(
            weight_unchanged_count=self.weight_unchanged_count,
            weight_unchanged_share=self.weight_unchanged_share,
            decisive_indicators=self.decisive_indicators(),
            label_flips_by_weight=self.label_flips_by_weight(),
            final_ranges=self.final_ranges(),
            summary=self.summary(),
        )
        return data


def _finals(engine: ScoreEngine, categories: Mapping[str, Mapping[str, str]]):
    return {bank: engine.score(cats, bank=bank) for bank, cats in categories.items()}


def run_sensitivity(
    evidence: EvidenceTable,
    banks: Sequence[str],
    base_cfg: Optional[ScoreEngineConfig] = None,
) -> SensitivityReport:
    base_cfg = base_cfg or ScoreEngineConfig()
    banks = list(banks)
    categories = {bank: evidence.categories(bank) for bank in banks}

    base_engine = ScoreEngine(base_cfg)
    base = _finals(base_engine, categories)
    base_finals = {b: s.final for b, s in base.items()}
    base_labels = {b: s.label for b, s in base.items()}
    base_ranking = ranking_of(base_finals)

    weight_results = []
    for cfg in weight_scenarios(base_cfg):
        scores = _finals(ScoreEngine(cfg), categories)
        finals = {b: s.final for b, s in scores.items()}
        ranking = ranking_of(finals)
        weight_results.append(
            WeightResult(
                weights={"E": cfg.w_E, "S": cfg.w_S, "G": cfg.w_G},
                finals=finals,
                labels={b: s.label for b, s in scores.items()},
                ranking=ranking,
                ranking_unchanged=ranking is not None and ranking == base_ranking,
            )
        )

    moves = []
    for bank in banks:
        for key in ALL_KEYS:
            current = categories[bank][key]
            for direction, new_category in one_step_moves(key, current):
                changed = {b: dict(c) for b, c in categories.items()}
                changed[bank][key] = new_category
                after = base_engine.score(changed[bank], bank=bank)
                finals = dict(base_finals, **{bank: after.final})
                ranking = ranking_of(finals)
                moves.append(
                    JudgmentMove(
                        bank=bank,
                        indicator=key,
                        direction=direction,
                        from_category=current,
                        to_category=new_category,
                        final_before=base_finals[bank],
                        final_after=after.final,
                        label_before=base_labels[bank],
                        label_after=after.label,
                        ranking=ranking,
                        changes_ranking=len(banks) > 1 and ranking != base_ranking,
                        changes_label=after.label != base_labels[bank],
                    )
                )

    return SensitivityReport(
        banks=banks,
        base_weights={"E": base_cfg.w_E, "S": base_cfg.w_S, "G": base_cfg.w_G},
        base_finals=base_finals,
        base_labels=base_labels,
        base_ranking=base_ranking,
        weight_results=weight_results,
        moves=moves,
    )

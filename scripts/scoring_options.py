"""Effect of number-based categories, continuous scoring and open judgment calls.

Analysis only: the official scores are unchanged. Usage (from the repository root):

    python -m scripts.scoring_options          # print the report
    python -m scripts.scoring_options --write  # update docs/scoring_options.md

Three indicators are defined by a number in the category definitions: the
Green Asset Ratio, the share of independent Supervisory Board members and the
weight of ESG targets in the CEO's variable pay. For each bank the number is
recorded below together with the words that state it, and those words must be
part of the row's verified quote (see tests/test_scoring_options.py).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from tools.evidence import EvidenceTable, load_evidence
from tools.score_engine import RUBRIC_BY_KEY, BankScore, ScoreEngine

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "docs" / "scoring_options.md"


@dataclass(frozen=True)
class NumericRule:
    unit: str
    category: Callable[[float], str]  # band thresholds from data/evidence/category_definitions.md
    anchors: Sequence[Tuple[float, float]]  # (value, score) points for continuous scoring


def _gar_category(v: float) -> str:
    if v == 0:
        return "none"
    return "low" if v < 10 else "medium" if v < 25 else "high" if v < 50 else "aligned"


RULES: Dict[str, NumericRule] = {
    "taxonomy_alignment": NumericRule(
        "% Green Asset Ratio (turnover, stock)",
        _gar_category,
        # 0% scores like `none`; each band's score is reached at the middle of the band.
        ((0, 20), (5, 45), (17.5, 65), (37.5, 80), (75, 90)),
    ),
    "board_independence": NumericRule(
        "% independent Supervisory Board members",
        lambda v: "<33" if v < 33 else "33_50" if v < 50 else ">=50",
        ((16.5, 45), (41.5, 65), (75, 80)),
    ),
    "exec_comp_esg": NumericRule(
        "% weight of E and S targets in the CEO's variable pay",
        lambda v: "none" if v == 0 else "<20" if v < 20 else ">=20",
        ((0, 40), (10, 60), (30, 80)),
    ),
}


@dataclass(frozen=True)
class Figure:
    value: Optional[float]  # None: the report does not state the number
    stated_as: str  # words in the row's verified quote that give the number


FIGURES: Dict[Tuple[str, str], Figure] = {
    ("ING Group", "taxonomy_alignment"): Figure(14.0, "our GAR based on Turnover is 14 percent"),
    ("ABN AMRO", "taxonomy_alignment"): Figure(21.0, "main KPI GAR from 11% (31 December 2024) to 21%"),
    ("Rabobank", "taxonomy_alignment"): Figure(15.06, "Green asset ratio (GAR) stock 34,066 15.06%"),
    ("ING Group", "board_independence"): Figure(100.0, "all members of the SB are to be regarded as independent"),
    ("ABN AMRO", "board_independence"): Figure(100.0, "all members of the Supervisory Board are independent"),
    ("Rabobank", "board_independence"): Figure(None, "continued to meet best practices provisions 2.1.7 thru 2.1.9"),
    ("ING Group", "exec_comp_esg"): Figure(15.0, "Environment 10.0% 95% 10% 10.0% 80% 8% 10.0% 90% 9% Social 5.0%"),
    ("ABN AMRO", "exec_comp_esg"): Figure(0.0, "are not entitled to variable remuneration"),
    ("Rabobank", "exec_comp_esg"): Figure(0.0, "do not receive variable remuneration"),
}

# Open judgment calls from docs/evidence_recheck.md, as category changes per bank.
JUDGMENT_OPTIONS: Dict[str, Dict[str, Dict[str, str]]] = {
    "A. Rabobank climate risk management `strong` -> `full`": {"Rabobank": {"risk_management": "full"}},
    "B. Rabobank board independence `>=50` -> `not_disclosed`": {"Rabobank": {"board_independence": "not_disclosed"}},
    "C. `strong` risk management requires disclosed quantified limits (ING and Rabobank -> `full`)": {
        "ING Group": {"risk_management": "full"},
        "Rabobank": {"risk_management": "full"},
    },
}


def interpolate(anchors: Sequence[Tuple[float, float]], value: float) -> float:
    """Piecewise-linear score between anchor points, flat beyond the first and last point."""
    if value <= anchors[0][0]:
        return anchors[0][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if value <= x1:
            return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
    return anchors[-1][1]


def continuous_overrides(bank: str) -> Dict[str, float]:
    return {
        key: interpolate(rule.anchors, FIGURES[(bank, key)].value)
        for key, rule in RULES.items()
        if FIGURES[(bank, key)].value is not None
    }


def ranking(scores: Mapping[str, BankScore]) -> Dict[str, int]:
    order = sorted(scores, key=lambda b: (-scores[b].final, b))
    return {bank: i + 1 for i, bank in enumerate(order)}


def build_report(evidence: EvidenceTable, engine: ScoreEngine) -> str:
    banks = evidence.banks()
    official = {b: engine.score(evidence.categories(b), b) for b in banks}
    lines: List[str] = [
        "# Scoring options: number-based categories, continuous scoring and open judgment calls",
        "",
        "Generated by `python -m scripts.scoring_options --write`. Analysis only: the official scores are",
        "unchanged unless the analysts adopt an option. Thresholds come from",
        "`data/evidence/category_definitions.md`; every number below is stated in the row's verified quote.",
        "",
        "## 1. Numbers behind the numeric indicators",
        "",
        "| Bank | Indicator | Number | Stated in the report as | Category from the number | Current category |",
        "|---|---|---|---|---|---|",
    ]
    for (bank, key), fig in FIGURES.items():
        current = evidence.for_bank(bank)[key].category
        if fig.value is None:
            derived = "cannot be derived (no number)"
        else:
            derived = RULES[key].category(fig.value)
            derived = f"`{derived}`" + (" ✓" if derived == current else " ✗ differs")
        number = "not stated" if fig.value is None else f"{fig.value:g}%"
        lines.append(f"| {bank} | {RUBRIC_BY_KEY[key].label} | {number} | \"{fig.stated_as}\" | {derived} | `{current}` |")

    lines += [
        "",
        "## 2. Continuous scoring of the numeric indicators",
        "",
        "Instead of one score per band, the score rises linearly with the number. Each band's category",
        "score is reached at the middle of the band, so a bank at the band midpoint scores exactly as now.",
        "",
        "| Indicator | Anchor points (number -> score) |",
        "|---|---|",
    ]
    for key, rule in RULES.items():
        anchors = ", ".join(f"{x:g}% -> {y:g}" for x, y in rule.anchors)
        lines.append(f"| {RUBRIC_BY_KEY[key].label} ({rule.unit}) | {anchors} |")
    lines += ["", "| Bank | Indicator | Category score | Continuous score |", "|---|---|---|---|"]
    continuous = {}
    for bank in banks:
        overrides = continuous_overrides(bank)
        continuous[bank] = engine.score(evidence.categories(bank), bank, score_overrides=overrides)
        for key in RULES:
            now = RUBRIC_BY_KEY[key].score(evidence.for_bank(bank)[key].category)
            new = overrides.get(key)
            lines.append(f"| {bank} | {RUBRIC_BY_KEY[key].label} | {now} | {'unchanged (no number)' if new is None else f'{new:.1f}'} |")
    lines += _totals_table("Effect on the final scores", official, {"Continuous scoring": continuous})

    lines += [
        "",
        "## 3. Open judgment calls",
        "",
        "Each option changes only the listed categories; everything else stays as confirmed.",
    ]
    options = {}
    for name, changes in JUDGMENT_OPTIONS.items():
        options[name] = {
            b: engine.score({**evidence.categories(b), **changes.get(b, {})}, b) for b in banks
        }
    lines += _totals_table("Effect on the final scores", official, options)
    return "\n".join(lines) + "\n"


def _totals_table(title: str, official: Mapping[str, BankScore], variants: Mapping[str, Mapping[str, BankScore]]) -> List[str]:
    rank_now = ranking(official)
    lines = ["", f"**{title}**", "", "| Variant | Bank | Final | Change | Label | Rank |", "|---|---|---|---|---|---|"]
    for bank, s in official.items():
        lines.append(f"| Official (now) | {bank} | {s.final:.1f} | | {s.label} | {rank_now[bank]} |")
    for name, scores in variants.items():
        ranks = ranking(scores)
        for bank, s in scores.items():
            change = s.final - official[bank].final
            label = s.label + ("" if s.label == official[bank].label else " (changed)")
            rank = f"{ranks[bank]}" + ("" if ranks[bank] == rank_now[bank] else " (changed)")
            lines.append(f"| {name} | {bank} | {s.final:.1f} | {change:+.1f} | {label} | {rank} |")
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help=f"write {REPORT_PATH.relative_to(ROOT)}")
    args = parser.parse_args(argv)
    report = build_report(load_evidence(), ScoreEngine())
    if args.write:
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(f"Wrote {REPORT_PATH.relative_to(ROOT)}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

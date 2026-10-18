import pytest

from scripts.scoring_options import FIGURES, REPORT_PATH, RULES, build_report, continuous_overrides, interpolate
from tools.quotes import normalise
from tools.score_engine import RUBRIC_BY_KEY, ScoreEngine


def test_every_number_is_stated_in_the_verified_quote(evidence):
    for (bank, key), fig in FIGURES.items():
        assert normalise(fig.stated_as) in normalise(evidence.for_bank(bank)[key].quote), (bank, key)


def test_number_based_categories_match_the_evidence(evidence):
    for (bank, key), fig in FIGURES.items():
        if fig.value is not None:
            assert RULES[key].category(fig.value) == evidence.for_bank(bank)[key].category, (bank, key)


def test_figures_cover_every_bank_and_numeric_indicator(evidence):
    assert set(FIGURES) == {(bank, key) for bank in evidence.banks() for key in RULES}


def test_continuous_score_hits_the_category_score_at_each_band_midpoint():
    anchors = RULES["taxonomy_alignment"].anchors
    assert interpolate(anchors, 17.5) == RUBRIC_BY_KEY["taxonomy_alignment"].score("medium")
    assert interpolate(anchors, 0) == RUBRIC_BY_KEY["taxonomy_alignment"].score("none")
    assert interpolate(anchors, 200) == 90  # flat beyond the last anchor
    values = [interpolate(anchors, v / 2) for v in range(0, 200)]
    assert values == sorted(values)  # never decreases as the ratio rises


def test_report_is_up_to_date(evidence):
    """docs/scoring_options.md is regenerated with: python -m scripts.scoring_options --write"""
    assert REPORT_PATH.read_text(encoding="utf-8") == build_report(evidence, ScoreEngine())


def test_overrides_change_only_the_named_indicator(evidence):
    engine = ScoreEngine()
    cats = evidence.categories("ING Group")
    base = engine.score(cats)
    alt = engine.score(cats, score_overrides=continuous_overrides("ING Group"))
    assert alt.pillars["S"] == base.pillars["S"]  # no numeric indicator in S
    assert alt.pillars["E"] != base.pillars["E"] and alt.pillars["G"] != base.pillars["G"]
    with pytest.raises(ValueError, match="invalid score overrides"):
        engine.score(cats, score_overrides={"made_up": 50})
    with pytest.raises(ValueError, match="invalid score overrides"):
        engine.score(cats, score_overrides={"exec_comp_esg": 120})

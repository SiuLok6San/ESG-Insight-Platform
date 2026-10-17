import pytest

from tests.helpers import highest_categories, lowest_categories
from tools.score_engine import (
    ALL_KEYS,
    CONTROVERSY_DEDUCTION,
    NOT_DISCLOSED,
    PILLARS,
    RUBRIC,
    RUBRIC_BY_KEY,
    ScoreEngine,
    ScoreEngineConfig,
    compliance_label,
    round1,
)


def test_category_to_score_mapping():
    engine = ScoreEngine()
    cats = highest_categories()
    result = engine.score(cats)
    for item in result.indicators:
        assert item.score == RUBRIC_BY_KEY[item.key].scores[item.category]
    # Spot checks against the documented rubric.
    assert RUBRIC_BY_KEY["climate_plan"].score("sbt_aligned") == 90
    assert RUBRIC_BY_KEY["aml_maturity"].score("fined") == 25
    assert RUBRIC_BY_KEY["board_independence"].score(">=50") == 80


def test_categories_ordered_from_weakest_to_strongest():
    for ind in RUBRIC:
        scores = [ind.scores[c] for c in ind.categories]
        assert scores == sorted(scores), ind.key


def test_pillar_weights_sum_to_one():
    cfg = ScoreEngineConfig()
    assert cfg.w_E + cfg.w_S + cfg.w_G == pytest.approx(1.0)
    assert (cfg.w_E, cfg.w_S, cfg.w_G) == (0.35, 0.30, 0.35)


def test_indicator_weights_sum_to_one_within_each_pillar():
    for pillar in PILLARS:
        total = sum(ind.weight for ind in RUBRIC if ind.pillar == pillar)
        assert total == pytest.approx(1.0), pillar


@pytest.mark.parametrize("weights", [(0.5, 0.5, 0.5), (0.4, 0.4, 0.1), (1.2, -0.1, -0.1)])
def test_invalid_pillar_weights_rejected(weights):
    with pytest.raises(ValueError):
        ScoreEngineConfig(*weights)


def test_scores_clamped_to_0_100():
    engine = ScoreEngine()
    low = engine.score(lowest_categories())
    high = engine.score(highest_categories())
    for result in (low, high):
        assert 0.0 <= result.final <= 100.0
        assert all(0.0 <= v <= 100.0 for v in result.pillars.values())
    assert high.final == pytest.approx(round1(high.weighted))  # no deduction for "none"
    assert low.final == pytest.approx(round1(low.weighted - 5.0))


def test_controversy_adjustment():
    engine = ScoreEngine()
    base = highest_categories()
    finals = {}
    for category, deduction in CONTROVERSY_DEDUCTION.items():
        result = engine.score({**base, "controversy": category})
        assert result.controversy_deduction == deduction
        finals[category] = result.final
        assert result.final == pytest.approx(round1(result.weighted - deduction))
    assert CONTROVERSY_DEDUCTION == {"none": 0.0, "moderate": 2.0, "severe": 5.0}
    assert finals["none"] > finals["moderate"] > finals["severe"]


def test_controversy_does_not_change_pillars():
    engine = ScoreEngine()
    a = engine.score({**highest_categories(), "controversy": "none"})
    b = engine.score({**highest_categories(), "controversy": "severe"})
    assert a.pillars == b.pillars and a.weighted == b.weighted


def test_not_disclosed_maps_to_lowest_score():
    engine = ScoreEngine()
    cats = {**highest_categories(), "fossil_policy": NOT_DISCLOSED, "controversy": NOT_DISCLOSED}
    result = engine.score(cats)
    fossil = next(i for i in result.indicators if i.key == "fossil_policy")
    assert fossil.score == min(RUBRIC_BY_KEY["fossil_policy"].scores.values())
    assert fossil.not_disclosed
    assert result.controversy_deduction == max(CONTROVERSY_DEDUCTION.values())


def test_missing_indicator_raises():
    cats = highest_categories()
    cats.pop("climate_plan")
    with pytest.raises(ValueError, match="missing indicators"):
        ScoreEngine().score(cats)


def test_invalid_category_raises():
    with pytest.raises(ValueError, match="Invalid category"):
        ScoreEngine().score({**highest_categories(), "climate_plan": "excellent"})


def test_unknown_key_raises():
    with pytest.raises(ValueError, match="unknown keys"):
        ScoreEngine().score({**highest_categories(), "made_up": "x"})


@pytest.mark.parametrize(
    "score, label",
    [(100, "Meet"), (75.0, "Meet"), (74.9, "Almost Meet"), (50.0, "Almost Meet"), (49.9, "Not Meet"), (0, "Not Meet")],
)
def test_compliance_label_thresholds(score, label):
    assert compliance_label(score) == label


def test_label_matches_displayed_score():
    engine = ScoreEngine()
    result = engine.score(highest_categories())
    assert result.label == compliance_label(result.final)
    assert result.final == round1(result.final)


def test_round_half_up():
    assert round1(84.25) == 84.3
    assert round1(74.74) == 74.7
    assert round1(71.25) == 71.3


def test_score_is_independent_of_input_order():
    cats = highest_categories()
    reversed_cats = dict(reversed(list(cats.items())))
    assert ScoreEngine().score(cats) == ScoreEngine().score(reversed_cats)
    assert set(cats) == set(ALL_KEYS)

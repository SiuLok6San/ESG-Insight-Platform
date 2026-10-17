import pytest

from tests.helpers import highest_categories, make_table
from tools.score_engine import ScoreEngineConfig
from tools.sensitivity import one_step_moves, ordered_categories, ranking_of, run_sensitivity, weight_scenarios


def test_weight_grid_is_renormalised_and_unique():
    scenarios = weight_scenarios()
    assert len(scenarios) == 121
    keys = {(round(c.w_E, 9), round(c.w_S, 9), round(c.w_G, 9)) for c in scenarios}
    assert len(keys) == len(scenarios)
    for cfg in scenarios:
        assert cfg.w_E + cfg.w_S + cfg.w_G == pytest.approx(1.0)
        assert min(cfg.w_E, cfg.w_S, cfg.w_G) > 0
    assert any(c == ScoreEngineConfig() for c in scenarios)


def test_ranking_counts_ties_as_no_ranking():
    assert ranking_of({"A": 70.0, "B": 71.0}) == ("B", "A")
    assert ranking_of({"A": 70.0, "B": 70.0}) is None


def test_one_step_moves_respect_category_order():
    assert ordered_categories("controversy") == ("severe", "moderate", "none")
    assert one_step_moves("controversy", "moderate") == [("down", "severe"), ("up", "none")]
    assert one_step_moves("financed_emissions", "pcaf_full") == [("down", "partial")]
    assert one_step_moves("climate_plan", "none") == [("up", "weak")]
    assert one_step_moves("climate_plan", "not_disclosed") == [("up", "none")]


def test_identical_banks_tie_in_every_scenario():
    cats = highest_categories()
    report = run_sensitivity(make_table({"A": cats, "B": cats}), ["A", "B"])
    assert report.base_ranking is None
    assert report.weight_unchanged_count == 0


def test_clear_leader_is_robust():
    strong = highest_categories()
    weak = {**strong, "climate_plan": "none", "labor_rights": "none", "esg_oversight": "none"}
    report = run_sensitivity(make_table({"Strong": strong, "Weak": weak}), ["Strong", "Weak"])
    assert report.base_ranking == ("Strong", "Weak")
    assert report.weight_unchanged_share == 1.0
    assert report.ranking_moves() == []


def test_judgment_move_that_flips_a_close_ranking():
    a = highest_categories()
    b = {**a, "controversy": "moderate"}  # B trails A by exactly the 2-point deduction
    report = run_sensitivity(make_table({"A": a, "B": b}), ["A", "B"])
    flips = {(m.bank, m.indicator, m.to_category) for m in report.ranking_moves()}
    assert ("A", "controversy", "moderate") in flips  # A drops to a tie -> counts as a change
    assert ("B", "controversy", "none") in flips
    assert report.decisive_indicators()[0][0] == "controversy"

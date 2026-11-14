"""A27: the ask rule on the wide and narrow fixtures (SPEC 5.3, SPEC 14)."""
from pathlib import Path

import pytest

from backend import config
from backend.analysis.finance.sensitivity import DONT_KNOW, rank_assumptions, sensitivity, with_value
from backend.schema import BuildingModel, MeasureResult, Plan, Ranged

ASK = Path(__file__).resolve().parents[5] / "specs" / "examples" / "ask"


def load(name):
    return BuildingModel.model_validate_json((ASK / f"building_model_{name}.json").read_text())


def expected(model, key):
    return next(a.value.expected for a in model.assumptions if a.key == key)


def plan_of(selected, savings):
    items = [type("Item", (), {"measure": MeasureResult.model_construct(measure_id=m)})() for m in selected]
    total = Ranged(low=savings, expected=savings, high=savings, unit="USD")
    return Plan.model_construct(selected=items, total_annual_savings_usd=total)


class Counting:
    def __init__(self, fn):
        self.fn, self.calls = fn, 0

    def __call__(self, model):
        self.calls += 1
        return self.fn(model)


def plan_with_solar_gate(model):
    """Savings fall with a leaky roof and house; solar is only picked with a 150 A panel or more
    (a service upgrade eats the budget otherwise)."""
    amps = expected(model, "electrical.service_amps")
    savings = 2000 - 500 * expected(model, "roof.u_value") - 12 * expected(model, "infiltration.ach50") \
        + (900 if amps >= 150 else 0) - 300000 * (expected(model, "pv.degradation_rate") - 0.005)
    return plan_of(["LGT_LED"] + (["PV_ROOF"] if amps >= 150 else []), savings)


def plan_by_swing(model):
    """No selection effect: only the size of the swing decides."""
    return plan_of(["LGT_LED"], 2000 - 500 * expected(model, "roof.u_value") - 40 * expected(model, "infiltration.ach50"))


# ---- the fixtures ----

def test_fixtures_are_valid_building_models_and_differ_only_in_ranges():
    wide, narrow = load("wide"), load("narrow")
    assert wide.sid == narrow.sid and [a.key for a in wide.assumptions] == [a.key for a in narrow.assumptions]
    for a in narrow.assumptions:
        if isinstance(a.value, Ranged) and a.user_editable:
            assert a.value.high - a.value.low <= 0.0201 * abs(a.value.expected) + 1e-9, a.key
    assert any(isinstance(a.value, Ranged) and a.value.high > 1.5 * a.value.low
               for a in wide.assumptions if a.user_editable)


# ---- the ask rule ----

def test_wide_fixture_asks_and_the_selection_change_comes_first():
    questions = sensitivity(load("wide"), plan_with_solar_gate)
    assert questions, "the wide fixture must make the ask rule fire"
    first = questions[0]
    assert first.assumption_key == "electrical.service_amps"        # solar drops out below 150 A: selection changes
    assert first.id == "q_service_amps" and "different measures" in first.impact_note
    assert [q.assumption_key for q in questions] == ["electrical.service_amps", "roof.u_value"]


def test_without_a_selection_change_the_largest_swing_comes_first():
    wide = load("wide")
    questions = sensitivity(wide, plan_by_swing)
    assert [q.assumption_key for q in questions] == ["infiltration.ach50", "roof.u_value"]     # 960 then 760 USD
    _, rows = rank_assumptions(wide, plan_by_swing)
    assert [r.key for r in rows[:2]] == ["infiltration.ach50", "roof.u_value"]
    assert rows[0].swing == pytest.approx(960.0) and rows[0].width == pytest.approx(960 / 1198.5, abs=1e-3)


def test_narrow_fixture_stays_silent():
    narrow = load("narrow")
    assert sensitivity(narrow, plan_with_solar_gate) == []
    assert sensitivity(narrow, plan_by_swing) == []


def test_every_question_has_concrete_choices_and_an_i_dont_know_with_no_value():
    for plan_fn in (plan_with_solar_gate, plan_by_swing):
        wide = load("wide")
        for q in sensitivity(wide, plan_fn):
            *concrete, last = q.choices
            assert concrete and last.label == DONT_KNOW and last.value is None
            assert all(c.value is not None for c in concrete)
            a = next(a for a in wide.assumptions if a.key == q.assumption_key)
            assert all(a.value.low <= c.value <= a.value.high for c in concrete)
            assert q.prompt.endswith("?") and q.impact_note


def test_not_editable_assumptions_are_never_asked():
    wide = load("wide")
    degradation = next(a for a in wide.assumptions if a.key == "pv.degradation_rate")
    assert not degradation.user_editable and degradation.value.low < degradation.value.high
    _, rows = rank_assumptions(wide, plan_with_solar_gate)
    assert "pv.degradation_rate" not in [r.key for r in rows]


def test_ask_max_and_asked_keys():
    wide = load("wide")
    assert len(sensitivity(wide, plan_with_solar_gate, ask_max=1)) == 1
    assert sensitivity(wide, plan_with_solar_gate, ask_max=0) == []
    after = sensitivity(wide, plan_with_solar_gate, asked={"electrical.service_amps"})
    assert [q.assumption_key for q in after] == ["roof.u_value"]
    assert config.ASK_MAX == 3 and config.ASK_WIDTH == 0.40


def test_the_width_test_uses_the_ask_width_argument():
    wide = load("wide")
    assert [q.assumption_key for q in sensitivity(wide, plan_by_swing, ask_width=0.7)] == ["infiltration.ach50"]
    assert sensitivity(wide, plan_by_swing, ask_width=0.9) == []


def test_two_runs_per_assumption_and_the_input_is_not_changed():
    wide = load("wide")
    before = wide.model_dump_json()
    plan_fn = Counting(plan_with_solar_gate)
    _, rows = rank_assumptions(wide, plan_fn)
    assert plan_fn.calls == 1 + 2 * len(rows)
    assert wide.model_dump_json() == before


def test_answering_a_choice_collapses_the_range():
    wide = load("wide")
    q = sensitivity(wide, plan_with_solar_gate)[0]
    answered = with_value(wide, q.assumption_key, q.choices[1].value)
    a = next(a for a in answered.assumptions if a.key == q.assumption_key)
    assert a.value.low == a.value.expected == a.value.high == 150.0
    # with solar now certain the expected savings are larger, and the roof's swing (30%) is below ASK_WIDTH
    assert sensitivity(answered, plan_with_solar_gate) == []


def test_results_are_deterministic():
    wide = load("wide")
    assert [q.model_dump() for q in sensitivity(wide, plan_with_solar_gate)] == \
           [q.model_dump() for q in sensitivity(wide, plan_with_solar_gate)]

"""Sensitivity for the ask rule (A27; SPEC 5.3 steps 1 to 3, physics 04 UNC-03).

For each editable numeric assumption the plan is re-selected at its low and at its high with
every other assumption at expected. The agent asks about an assumption when the set of selected
measures differs between the two runs, or when the plan's total annual savings swing by more
than `ASK_WIDTH` of the expected total. The plan function is passed in, so the real budget
algorithm (SPEC 6.5) is part of every run. Pure and deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from backend import config
from backend.schema import Assumption, BuildingModel, Choice, Question, Ranged

PlanFn = Callable[[BuildingModel], Any]      # BuildingModel -> Plan (only selected and totals are read)

DONT_KNOW = "I don't know"


@dataclass(frozen=True)
class SensitivityRow:
    key: str
    y_low_run: float            # plan's total annual savings with the assumption at low
    y_high_run: float
    swing: float                # |y_high_run - y_low_run|, USD per year
    width: float                # swing / y0, compared with ASK_WIDTH
    changes: bool               # the selected measures differ between the two runs
    confidence: float
    assumption: Assumption


def _selected(plan) -> frozenset[str]:
    return frozenset(i.measure.measure_id for i in plan.selected)


def _savings(plan) -> float:
    return plan.total_annual_savings_usd.expected


def with_value(model: BuildingModel, key: str, value: float) -> BuildingModel:
    """A copy of the model with one assumption collapsed to `value`. The input is unchanged."""
    out = model.model_copy(deep=True)
    for a in out.assumptions:
        if a.key == key:
            a.value = Ranged(low=value, expected=value, high=value, unit=a.value.unit)
    return out


def _askable(model: BuildingModel, asked: Iterable[str]) -> list[Assumption]:
    """User-editable numeric assumptions that have a range. Policy parameters, fixed inputs and
    categorical ones are never asked about."""
    skip = set(asked)
    return [a for a in model.assumptions
            if a.user_editable and a.key not in skip and isinstance(a.value, Ranged)
            and a.value.low < a.value.high]


def rank_assumptions(model: BuildingModel, plan_fn: PlanFn, asked: Iterable[str] = ()
                     ) -> tuple[float, list[SensitivityRow]]:
    """(y0, rows): the expected-value plan's total savings and one row per askable assumption,
    in the order the agent should ask: selection changes first, then widest swing; ties go to the
    lower confidence, then the key (UNC-03)."""
    y0 = _savings(plan_fn(model))
    rows = []
    for a in _askable(model, asked):
        low = plan_fn(with_value(model, a.key, a.value.low))
        high = plan_fn(with_value(model, a.key, a.value.high))
        swing = abs(_savings(high) - _savings(low))
        rows.append(SensitivityRow(
            key=a.key, y_low_run=_savings(low), y_high_run=_savings(high), swing=swing,
            width=swing / y0 if y0 > 0 else 0.0, changes=_selected(low) != _selected(high),
            confidence=a.confidence, assumption=a))
    rows.sort(key=lambda r: (not r.changes, -r.swing, r.confidence, r.key))
    return y0, rows


def _number(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.3g}"


# Concrete answers a person can give, for assumptions whose natural choices are not low, expected
# and high. Values stay inside the assumption's own range.
CATALOG = {
    "electrical.service_amps": ("q_service_amps", "What is the rating of your main electrical panel?",
                                [("100 A or less", 100.0), ("125 to 150 A", 150.0), ("200 A or more", 200.0)]),
}


def _choices(a: Assumption) -> list[Choice]:
    v = a.value
    if a.key in CATALOG:
        options = CATALOG[a.key][2]
    else:
        options, seen = [], set()
        for name, value in (("low", v.low), ("most likely", v.expected), ("high", v.high)):
            if value not in seen:
                seen.add(value)
                options.append((f"About {_number(value)} {v.unit} ({name})", value))
    return [Choice(label=label, value=value) for label, value in options] + [Choice(label=DONT_KNOW, value=None)]


def _question(row: SensitivityRow, y0: float) -> Question:
    a = row.assumption
    if a.key in CATALOG:
        qid, prompt = CATALOG[a.key][0], CATALOG[a.key][1]
    else:
        qid, prompt = f"q_{a.key.replace('.', '_')}", f"What is the {a.label[:1].lower() + a.label[1:]}?"
    lo, hi = sorted((row.y_low_run, row.y_high_run))
    if row.changes:
        note = (f"Depending on this value the plan picks different measures; annual savings run from "
                f"${_number(lo)} to ${_number(hi)}.")
    else:
        note = (f"Moves the plan's annual savings from ${_number(lo)} to ${_number(hi)}, "
                f"{row.width:.0%} of the expected ${_number(y0)}.")
    return Question(id=qid, assumption_key=a.key, prompt=prompt,
                    choices=_choices(a), impact_note=note)


def sensitivity(model: BuildingModel, plan_fn: PlanFn, ask_width: float = config.ASK_WIDTH,
                ask_max: int = config.ASK_MAX, asked: Iterable[str] = ()) -> list[Question]:
    """SPEC 5.3: the questions worth asking, most valuable first, at most `ask_max`. An empty
    list means: do not ask, the range is simply shown."""
    y0, rows = rank_assumptions(model, plan_fn, asked)
    worth = [r for r in rows if r.changes or r.width > ask_width]
    return [_question(r, y0) for r in worth[:ask_max]]

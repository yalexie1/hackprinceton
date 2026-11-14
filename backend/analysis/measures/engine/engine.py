"""A16 measure engine (SPEC 6.2, 6.5; workplan 4.2 row A16).

evaluate = applicability (flow, role, feasibility flags, the measure's own check), then
simulate the current state, apply the measure, simulate again, report the difference.

PLUG-IN PROTOCOL (A17 to A22, A19 PV, A23 LAYOUT)
-------------------------------------------------
A measure package exports plain functions over contract types only; it never imports this
engine or a sibling. The door (`backend/analysis/api.py`) registers them:

    from backend.analysis.measures import engine, envelope
    engine.register("ENV_ATTIC", change=envelope.attic_change,
                    describe=envelope.attic_describe, check=envelope.attic_check)

    check(bundle: PropertyBundle, model: BuildingModel) -> None | tuple[str, str]
        Optional. None = no objection. Otherwise (reason, detail) with reason one of
        "already_done", "feasibility", "not_supported" and detail one plain sentence.
        Flow, role, owner consent and `blocked_by` flags are checked by the engine first.
    change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel
        The state with the measure applied: a NEW model (e.g. `model.model_copy(deep=True)`
        then edit), touching only the fields the measure names. Must not mutate the input
        (the engine checks and raises). Measures that change no model field (PV_ROOF,
        LAYOUT) return the input unchanged.
    describe(bundle, model, changed, before, options) -> MeasureResult
        model: state before; changed: what `change` returned; before: BaselineResult of
        `model` from the simulate passed to `evaluate`; options: dict with "role" and
        "desks_requested". Returns the measure's card: measure_id, title, description,
        params, anchors (`Anchor`), evidence (`EvidenceRef`), formula_ids, warnings, flags,
        and `solar` / `layout` where relevant. Leave `savings` as None and the engine fills
        it from simulate(changed) - simulate(model); set `savings` yourself only when the
        saving does not come from the building simulation (PV_ROOF from a SolarDesign,
        LAYOUT from a LayoutResult). Return `applicable=False` with a reason if a
        condition only shows up while designing (the engine keeps it, and simulates no
        "after"). `finance` is left empty: pricing is S7.

    Registration keywords: `formula_ids` (static ids merged into every result, ahead of
    the card's), `blocked_by` (flag keys; default from the catalogue).

The engine never imports `physics/`: `simulate(bundle, model) -> BaselineResult` is passed
in (workplan 2.6), with `simulate_formula_ids` naming the physics entries it runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Sequence, get_args

from backend.schema import (BaselineResult, BuildingModel, EnergyUse, MeasureId, MeasureResult,
                            PropertyBundle, Ranged, Role, SkippedItem)

from .catalogue import CATALOGUE, CONSENT_FLAG, flow_of, place_of

Simulate = Callable[[PropertyBundle, BuildingModel], BaselineResult]
CheckFn = Callable[[PropertyBundle, BuildingModel], Optional[tuple[str, str]]]
ChangeFn = Callable[[PropertyBundle, BuildingModel], BuildingModel]
DescribeFn = Callable[[PropertyBundle, BuildingModel, BuildingModel, BaselineResult, dict], MeasureResult]

# Why a measure is not applicable. role, feasibility and already_done are SkippedItem reasons
# (SPEC 6.5); flow and not_supported mean "never in the pool", so they have no plan reason.
SkipReason = Literal["flow", "role", "feasibility", "already_done", "not_supported"]
CHECK_REASONS = ("already_done", "feasibility", "not_supported")   # what a plug-in check may return
_PLAN_REASONS = set(get_args(SkippedItem.model_fields["reason"].annotation))

# MeasureResult has no skip-reason field (SPEC 9), so the code rides in params under this key.
SKIP_PARAM = "skip_reason"


@dataclass(frozen=True)
class Skip:
    reason: SkipReason
    detail: str          # the sentence shown as not_applicable_reason

    @property
    def plan_reason(self) -> Optional[str]:
        """The SkippedItem.reason for this skip, or None when the measure is not in the pool."""
        return self.reason if self.reason in _PLAN_REASONS else None


@dataclass(frozen=True)
class Plugin:
    measure_id: str
    change: ChangeFn
    describe: DescribeFn
    check: Optional[CheckFn] = None
    formula_ids: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()


@dataclass
class Registry:
    plugins: dict[str, Plugin] = field(default_factory=dict)

    def register(self, measure_id: MeasureId, *, change: ChangeFn, describe: DescribeFn,
                 check: Optional[CheckFn] = None, formula_ids: Sequence[str] = (),
                 blocked_by: Optional[Sequence[str]] = None) -> Plugin:
        if measure_id not in CATALOGUE:
            raise ValueError(f"unknown measure id {measure_id!r}")
        for name, fn in (("change", change), ("describe", describe)):
            if not callable(fn):
                raise TypeError(f"{measure_id}: {name} must be callable")
        if check is not None and not callable(check):
            raise TypeError(f"{measure_id}: check must be callable")
        plugin = Plugin(measure_id, change, describe, check, tuple(formula_ids),
                        tuple(CATALOGUE[measure_id].blocked_by if blocked_by is None else blocked_by))
        self.plugins[measure_id] = plugin       # re-registering replaces
        return plugin

    def registered(self) -> list[str]:
        return [m for m in CATALOGUE if m in self.plugins]


# The door registers here at import time; tests build their own Registry.
REGISTRY = Registry()


def register(measure_id: MeasureId, **kwargs: Any) -> Plugin:
    return REGISTRY.register(measure_id, **kwargs)


# ---------------------------------------------------------------- applicability

def _flag(model: BuildingModel, key: str):
    return next((f for f in model.flags if f.key == key), None)


def applicability(bundle: PropertyBundle, model: BuildingModel, measure_id: MeasureId, role: Role,
                  registry: Optional[Registry] = None) -> tuple[Optional[Skip], list[str]]:
    """(skip, warnings). skip is None when the measure may be evaluated. Order: flow, role,
    owner consent, blocking flags, the measure's own check, then whether it is registered."""
    registry = REGISTRY if registry is None else registry
    entry = CATALOGUE.get(measure_id)
    if entry is None:
        raise ValueError(f"unknown measure id {measure_id!r}")
    warnings: list[str] = []

    flow = flow_of(bundle.summary)
    if flow not in entry.flows:
        other = "Office" if flow == "home" else "Home"
        return Skip("flow", f"{other}-flow measure (SPEC.md section 6.2); this property is "
                            f"{place_of(bundle.summary)}."), warnings

    if role not in entry.roles and role not in entry.consent_roles:
        return Skip("role", f"Owner-only measure (SPEC.md section 6.2); the user is a {role}."
                    if role == "tenant" else
                    f"Not a measure a {role} can do (SPEC.md section 6.2)."), warnings
    if role not in entry.roles:                  # allowed only with the owner's consent
        consent = _flag(model, CONSENT_FLAG)
        if consent is not None and consent.status == "blocked":
            return Skip("feasibility", f"Blocked by feasibility flag {CONSENT_FLAG}: {consent.message}"), warnings
        warnings.append(f"Needs the owner's consent: a {role} may do this measure only with the "
                        f"owner's agreement (SPEC.md section 6.2).")

    plugin = registry.plugins.get(measure_id)
    for key in (plugin.blocked_by if plugin else entry.blocked_by):
        f = _flag(model, key)
        if f is not None and f.status == "blocked":
            return Skip("feasibility", f"Blocked by feasibility flag {key}: {f.message}"), warnings

    if plugin is None:
        return Skip("not_supported", f"{measure_id} has no evaluator yet."), warnings
    if plugin.check is not None:
        got = plugin.check(bundle, model)
        if got is not None:
            reason, detail = got
            if reason not in CHECK_REASONS:
                raise ValueError(f"{measure_id}: check returned reason {reason!r}, "
                                 f"expected one of {CHECK_REASONS}")
            text = f"Already done: {detail}" if reason == "already_done" else detail
            return Skip(reason, text), warnings
    return None, warnings


def skip_reason(result: MeasureResult) -> Optional[str]:
    """The engine's SkipReason for a non-applicable result, None for an applicable one."""
    return None if result.applicable else result.params.get(SKIP_PARAM, "feasibility")


def _skipped(measure_id: str, skip: Skip) -> MeasureResult:
    return MeasureResult(measure_id=measure_id, title=CATALOGUE[measure_id].title, applicable=False,
                         not_applicable_reason=skip.detail, params={SKIP_PARAM: skip.reason})


# ---------------------------------------------------------------- savings

def _diff(a: Ranged, b: Ranged) -> Ranged:
    """a - b with the two runs paired percentile by percentile (they share every input), then
    ordered so low <= expected <= high. A paired approximation, not UNC-02: the plan totals
    get UNC-02 over the whole plan (physics 04 UNC-02, aggregation)."""
    exp = a.expected - b.expected
    ends = (a.low - b.low, a.high - b.high)
    return Ranged(low=min(*ends, exp), expected=exp, high=max(*ends, exp), unit=a.unit)


def energy_saved(before: EnergyUse, after: EnergyUse) -> EnergyUse:
    """before - after, field by field: positive = a saving, negative = a penalty."""
    nb = None
    if before.co2_nonbaseload_kg is not None and after.co2_nonbaseload_kg is not None:
        nb = _diff(before.co2_nonbaseload_kg, after.co2_nonbaseload_kg)
    return EnergyUse(electricity_kwh=_diff(before.electricity_kwh, after.electricity_kwh),
                     gas_kwh=_diff(before.gas_kwh, after.gas_kwh),
                     cost_usd=_diff(before.cost_usd, after.cost_usd),
                     co2_kg=_diff(before.co2_kg, after.co2_kg),
                     co2_nonbaseload_kg=nb)


def _merge(*groups: Sequence[str]) -> list[str]:
    out: list[str] = []
    for g in groups:
        out.extend(x for x in g if x not in out)
    return out


# ---------------------------------------------------------------- evaluate

def apply_measure(bundle: PropertyBundle, model: BuildingModel, measure_id: MeasureId,
                  registry: Optional[Registry] = None) -> BuildingModel:
    """The state with the measure applied (SPEC 6.5 `state = state with m applied`)."""
    registry = REGISTRY if registry is None else registry
    plugin = registry.plugins.get(measure_id)
    if plugin is None:
        raise LookupError(f"{measure_id} has no evaluator registered")
    frozen = model.model_dump_json()
    changed = plugin.change(bundle, model)
    if model.model_dump_json() != frozen:
        raise RuntimeError(f"{measure_id}: change mutated its input model")
    if not isinstance(changed, BuildingModel):
        raise TypeError(f"{measure_id}: change must return a BuildingModel")
    return changed


def evaluate(bundle: PropertyBundle, model: BuildingModel, measure_id: MeasureId, role: Role,
             simulate: Simulate, *, registry: Optional[Registry] = None,
             desks_requested: Optional[int] = None,
             simulate_formula_ids: Sequence[str] = ()) -> MeasureResult:
    """MeasureResult with `savings` against `model` (which may already carry earlier
    measures); `finance` empty. Not applicable: applicable=False, the reason as text and
    its code in params["skip_reason"]."""
    registry = REGISTRY if registry is None else registry
    skip, warnings = applicability(bundle, model, measure_id, role, registry)
    if skip is not None:
        return _skipped(measure_id, skip)

    plugin = registry.plugins[measure_id]
    frozen = model.model_dump_json()
    before = simulate(bundle, model)
    changed = apply_measure(bundle, model, measure_id, registry)
    card = plugin.describe(bundle, model, changed, before,
                           {"role": role, "desks_requested": desks_requested})
    if model.model_dump_json() != frozen:
        raise RuntimeError(f"{measure_id}: describe mutated its input model")
    if not isinstance(card, MeasureResult) or card.measure_id != measure_id:
        raise TypeError(f"{measure_id}: describe must return a MeasureResult for {measure_id}")

    if not card.applicable:
        params = dict(card.params)
        params.setdefault(SKIP_PARAM, "feasibility")
        return card.model_copy(update={"params": params, "savings": None, "finance": None})

    used_simulation = card.savings is None
    savings = energy_saved(before.annual, simulate(bundle, changed).annual) if used_simulation else card.savings
    formula_ids = _merge(plugin.formula_ids, card.formula_ids,
                         simulate_formula_ids if used_simulation else ())
    if not formula_ids:
        raise ValueError(f"{measure_id}: no formula_ids; every result must list the physics entries it used")
    return card.model_copy(update={
        "applicable": True, "not_applicable_reason": None, "savings": savings, "finance": None,
        "formula_ids": formula_ids, "warnings": _merge(card.warnings, warnings),
        "title": card.title or CATALOGUE[measure_id].title})

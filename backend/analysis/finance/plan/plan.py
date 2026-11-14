"""S7 Plan, the budget algorithm (A26; SPEC 6.5 and 6.2, physics 04 UNC-02).

The plan follows consultant practice: operations first, then load reduction, then equipment, and
solar last, sized against the load left. Within a step the measure with the highest profitability
index (NPV per net upfront dollar) goes first, and a measure whose SIR is below 1 is never recommended
or offered for financing. The building state is opaque here: the caller passes `evaluate` (evaluate
AND price a measure against a state; for solar it also takes a `size`), `apply` (the state with a
measure applied) and `energy` (annual use of a state), so this module holds the algorithm and nothing
else. Pure and deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from backend.schema import (EnergyUse, MeasureId, MeasureResult, Plan, PlanItem, Ranged, Role,
                            SkippedItem, ValueUplift)

Evaluate = Callable[..., MeasureResult]      # (measure_id, state) or, for solar, (measure_id, state, size)
Apply = Callable[[Any, MeasureResult], Any]
Energy = Callable[[Any], EnergyUse]

# SPEC 6.2 "Who can do it". OWNER: owner_occupier and landlord. CONSENT: the tenant may, with the
# owner's written consent, which the tool cannot see, so the measure carries a warning.
_OWNER = {"ENV_ATTIC", "ENV_WALL", "WIN_REPLACE", "ROOF_COOL", "HVAC_HP", "HVAC_RTU", "HVAC_ECON",
          "HVAC_DUCT", "DHW_HPWH", "PV_ROOF"}
_CONSENT = {"ENV_AIRSEAL", "WIN_FILM"}
_TENANT_OK = {"LGT_CTRL", "WIN_SHADE", "LGT_LED", "PLUG_MGMT", "CTRL_TSTAT", "LAYOUT"}
CONSENT_WARNING = "needs the owner's written consent"
BUDGET_WARNING = "may exceed budget"
NO_COST_DETAIL = "no verified cost; needs a quote"
_REASONS = ("over_budget", "role", "feasibility", "no_savings", "not_cost_effective", "already_done",
            "no_cost_data")

# SPEC 6.5 loading order. Anything not listed is load reduction; solar is the last step, sized separately.
STEP_OF = {"LAYOUT": 1, "CTRL_TSTAT": 1, "LGT_CTRL": 1, "PLUG_MGMT": 1, "HVAC_ECON": 1,
           "ENV_AIRSEAL": 2, "ENV_ATTIC": 2, "ENV_WALL": 2, "WIN_REPLACE": 2, "WIN_FILM": 2, "WIN_SHADE": 2,
           "ROOF_COOL": 2, "LGT_LED": 2, "HVAC_DUCT": 2,
           "HVAC_HP": 3, "HVAC_RTU": 3, "DHW_HPWH": 3, "PV_ROOF": 4}
PV_FRACTIONS = (1.0, 0.75, 0.5)


def role_allows(measure_id: str, role: Role) -> tuple[bool, bool]:
    """(allowed, needs consent) for this role under SPEC 6.2."""
    if role != "tenant":
        return True, False
    if measure_id in _OWNER:
        return False, False
    return True, measure_id in _CONSENT


def _savings(m: MeasureResult) -> float:
    return m.savings.cost_usd.expected if m.savings else 0.0


def _cost(m: MeasureResult) -> float:
    return m.finance.net_upfront_usd.expected if m.finance else 0.0


def _usd(x: float) -> float:
    return round(x, 2)


def _skip_code(m: MeasureResult) -> str:
    """Why an evaluated measure is not applicable. The engine may say so in params['skip_reason'];
    otherwise a reason that says 'already' is already_done and anything else is feasibility."""
    code = m.params.get("skip_reason")
    if code in ("role", "feasibility", "already_done"):
        return code
    return "already_done" if "already" in (m.not_applicable_reason or "").lower() else "feasibility"


def _band(y0: float, deviations: list[tuple[float, float]], linear: Optional[tuple[float, float]] = None):
    """UNC-02: independent inputs add in quadrature; `linear` is one fully correlated group whose
    deviations add first. Each deviation is (below expected, above expected), both >= 0."""
    lo = sum(d[0] ** 2 for d in deviations) + (linear[0] ** 2 if linear else 0.0)
    hi = sum(d[1] ** 2 for d in deviations) + (linear[1] ** 2 if linear else 0.0)
    return y0 - lo ** 0.5, y0 + hi ** 0.5


@dataclass(frozen=True)
class PriceGroup:
    """The `price_level` correlation group of UNC-02: the electricity price (which also prices export)
    and the gas price move together across every measure of a plan. `*_rel_low` and `*_rel_high` are
    the price's distance to its low and high, as a fraction of its expected value."""
    electricity_usd_per_kwh: float
    electricity_rel_low: float = 0.0
    electricity_rel_high: float = 0.0
    gas_usd_per_kwh: float = 0.0
    gas_rel_low: float = 0.0
    gas_rel_high: float = 0.0

    @classmethod
    def from_assumptions(cls, tariff_electricity: float, tariff_gas: Optional[float],
                         electricity: Optional[Ranged], gas: Optional[Ranged]) -> "PriceGroup":
        def rel(r: Optional[Ranged]) -> tuple[float, float]:
            if r is None or r.expected <= 0:
                return 0.0, 0.0
            return (r.expected - r.low) / r.expected, (r.high - r.expected) / r.expected
        e, g = rel(electricity), rel(gas)
        return cls(tariff_electricity, e[0], e[1], tariff_gas or 0.0, g[0], g[1])


def _price_parts(m: MeasureResult, group: PriceGroup) -> tuple[float, float]:
    """The part of a measure's expected saving that moves with the electricity price (electricity and
    export) and the part that moves with the gas price, in USD per year (signed)."""
    s = m.savings
    gas = s.gas_kwh.expected * group.gas_usd_per_kwh
    return s.cost_usd.expected - gas, gas


def _price_effect(parts: list[tuple[float, float]], group: PriceGroup) -> tuple[float, float]:
    """(below, above) deviation of the summed savings when the price group is at its low and at its
    high with every other input at expected (UNC-02: each deviation goes to the side it falls on)."""
    elec = sum(p[0] for p in parts)
    gas = sum(p[1] for p in parts)
    at_low = -(elec * group.electricity_rel_low + gas * group.gas_rel_low)
    at_high = elec * group.electricity_rel_high + gas * group.gas_rel_high
    return -min(at_low, at_high, 0.0), max(at_low, at_high, 0.0)


def _savings_total(chosen: list[MeasureResult], group: Optional[PriceGroup]) -> Ranged:
    """Total annual savings. Without a price group every measure is independent. With one, the price
    effect of all measures adds linearly (one correlated group) and what is left of each measure's own
    range (its range less its price part, in quadrature, as A3 combined them) is independent."""
    ranges = [m.savings.cost_usd for m in chosen]
    if group is None:
        return _total("USD", ranges, False)
    y0 = sum(r.expected for r in ranges)
    others_lo, others_hi = [], []
    for m, r in zip(chosen, ranges):
        below, above = _price_effect([_price_parts(m, group)], group)
        d_lo, d_hi = r.expected - r.low, r.high - r.expected
        others_lo.append(max(0.0, d_lo ** 2 - below ** 2) ** 0.5)
        others_hi.append(max(0.0, d_hi ** 2 - above ** 2) ** 0.5)
    g_lo, g_hi = _price_effect([_price_parts(m, group) for m in chosen], group)
    low, high = _band(y0, [(a, b) for a, b in zip(others_lo, others_hi)], (g_lo, g_hi))
    return Ranged(low=_usd(low), expected=_usd(y0), high=_usd(high), unit="USD")


def _total(unit: str, ranges: list[Ranged], correlated: bool) -> Ranged:
    y0 = sum(r.expected for r in ranges)
    devs = [(r.expected - r.low, r.high - r.expected) for r in ranges]
    if correlated:        # all installed costs of a plan sit in one correlation group (UNC-02)
        low, high = _band(y0, [], (sum(d[0] for d in devs), sum(d[1] for d in devs)))
    else:                 # measure savings are treated as independent of one another
        low, high = _band(y0, devs)
    return Ranged(low=_usd(low), expected=_usd(y0), high=_usd(high), unit=unit)


def _npv(m: MeasureResult) -> float:
    return m.finance.npv_usd.expected if m.finance else 0.0


def _sir_ok(m: MeasureResult) -> bool:
    """SPEC 6.5: recommended only if SIR >= 1. A measure that costs nothing up front is cost-effective when it saves."""
    if _cost(m) <= 0:
        return _savings(m) > 0
    sir = m.finance.sir
    return (sir >= 1.0) if sir is not None else _npv(m) >= 0


def _pi_key(m: MeasureResult):
    """Zero (or negative) net cost first, ordered by NPV; then the highest profitability index NPV / net upfront."""
    cost = _cost(m)
    return (0, -_npv(m), m.measure_id) if cost <= 0 else (1, -_npv(m) / cost, m.measure_id)


def _kw(m: MeasureResult) -> Optional[float]:
    return m.solar.system_kw_dc if m.solar is not None else None


def select_plan(measure_ids: list[MeasureId], role: Role, budget_usd: float, state: Any,
                evaluate: Evaluate, apply: Apply, energy: Energy,
                value_uplift: Optional[ValueUplift] = None,
                price_group: Optional[PriceGroup] = None,
                min_pv_kw: float = 2.0) -> Plan:
    skipped: list[SkippedItem] = []
    pool: list[MeasureId] = []
    consent: set[str] = set()
    for mid in sorted(set(measure_ids)):
        allowed, needs_consent = role_allows(mid, role)
        if not allowed:
            skipped.append(SkippedItem(measure_id=mid, reason="role",
                                       detail=f"Owner-only measure (SPEC.md section 6.2); the {role.replace('_', ' ')} cannot do it."))
            continue
        pool.append(mid)
        if needs_consent:
            consent.add(mid)

    selected: list[PlanItem] = []
    remaining, cumulative = float(budget_usd), 0.0

    def with_consent(m: MeasureResult) -> MeasureResult:
        return m.model_copy(update={"warnings": [*m.warnings, CONSENT_WARNING]}) if m.measure_id in consent else m

    def evaluated(ids: list[str]) -> list[MeasureResult]:
        return [with_consent(evaluate(mid, state)) for mid in ids]

    def classify(m: MeasureResult) -> Optional[SkippedItem]:
        """A measure that can never be picked from this state, with the reason."""
        if not m.applicable:
            return SkippedItem(measure_id=m.measure_id, reason=_skip_code(m),
                               detail=m.not_applicable_reason or "Not applicable.")
        if m.finance is None:
            return SkippedItem(measure_id=m.measure_id, reason="no_cost_data", detail=NO_COST_DETAIL)
        if _savings(m) <= 0:
            return SkippedItem(measure_id=m.measure_id, reason="no_savings",
                               detail="No positive annual savings against the current state.")
        return None

    def not_effective(m: MeasureResult) -> SkippedItem:
        sir = m.finance.sir
        shown = f"SIR {sir:.2f}" if sir is not None else f"NPV {_npv(m):,.0f} USD"
        return SkippedItem(measure_id=m.measure_id, reason="not_cost_effective", detail=(
            f"{shown} is below the break-even of 1: over its life it costs more than it saves, so it is not "
            "recommended or offered for financing."))

    def choose(pick: MeasureResult) -> None:
        nonlocal state, remaining, cumulative
        if pick.finance.net_upfront_usd.high > remaining and BUDGET_WARNING not in pick.warnings:
            pick = pick.model_copy(update={"warnings": [*pick.warnings, BUDGET_WARNING]})
        cumulative += _cost(pick)
        remaining -= _cost(pick)
        selected.append(PlanItem(rank=len(selected) + 1, measure=pick,
                                 cumulative_upfront_usd=_usd(cumulative),
                                 remaining_budget_usd=_usd(budget_usd - cumulative)))
        state = apply(state, pick)
        pool.remove(pick.measure_id)

    # steps 1 to 3: the most cost-effective measure that fits goes first, then everything is evaluated again
    for step in (1, 2, 3):
        while True:
            in_step = [mid for mid in pool if STEP_OF.get(mid, 2) == step]
            eligible = [m for m in evaluated(in_step) if classify(m) is None and _sir_ok(m)]
            eligible.sort(key=_pi_key)
            pick = next((m for m in eligible if _cost(m) <= remaining), None)
            if pick is None:
                break
            choose(pick)

    # step 4, solar, last: sized against what is left of the load, best NPV of 100 / 75 / 50 percent
    economic: Optional[MeasureResult] = None
    if "PV_ROOF" in pool:
        tried = [with_consent(evaluate("PV_ROOF", state, ("fraction", f))) for f in PV_FRACTIONS]
        usable = [m for m in tried if classify(m) is None]
        economic = max(usable, key=lambda m: (_npv(m), _kw(m) or 0.0), default=tried[0])
        if classify(economic) is None and _sir_ok(economic):
            if _cost(economic) <= remaining:
                choose(economic)
            else:
                shrunk = with_consent(evaluate("PV_ROOF", state, ("budget", remaining)))
                kw = _kw(shrunk)
                if (classify(shrunk) is None and _sir_ok(shrunk) and _cost(shrunk) <= remaining
                        and (kw is None or kw >= min_pv_kw)):
                    choose(shrunk)

    # what is left: financeable only if it is cost-effective, evaluated against the final state
    financeable: list[MeasureResult] = []
    for m in evaluated([mid for mid in pool if mid != "PV_ROOF"]) + ([economic] if economic is not None and "PV_ROOF" in pool else []):
        reason = classify(m)
        if reason is not None:
            skipped.append(reason)
            continue
        if not _sir_ok(m):
            skipped.append(not_effective(m))
            continue
        financeable.append(m)
        whole = _cost(m) > budget_usd
        skipped.append(SkippedItem(measure_id=m.measure_id, reason="over_budget", detail=(
            "Net upfront cost is above the whole budget; listed as financeable." if whole else
            "Net upfront cost is above the budget left after the selected measures; listed as financeable.")))
    financeable.sort(key=lambda m: (STEP_OF.get(m.measure_id, 2),) + _pi_key(m))

    chosen = [i.measure for i in selected]
    zero = Ranged(low=0.0, expected=0.0, high=0.0, unit="USD")
    return Plan(
        budget_usd=budget_usd, selected=selected, financeable=financeable,
        skipped=sorted(skipped, key=lambda s: (_REASONS.index(s.reason), s.measure_id)),
        total_upfront_usd=_total("USD", [m.finance.net_upfront_usd for m in chosen], True) if chosen else zero,
        total_annual_savings_usd=_savings_total(chosen, price_group) if chosen else zero,
        total_co2_kg=_total("kg", [m.savings.co2_kg for m in chosen], False) if chosen else Ranged(low=0.0, expected=0.0, high=0.0, unit="kg"),
        baseline_after=energy(state), value_uplift=value_uplift)

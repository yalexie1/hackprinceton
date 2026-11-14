"""S7 Plan, the budget algorithm (A26; SPEC 6.5 and 6.2, physics 04 UNC-02).

Rank by annual dollar savings; if the top measure does not fit, go to the next. The building
state is opaque here: the caller passes `evaluate` (evaluate AND price a measure against a
state), `apply` (the state with a measure applied) and `energy` (annual use of a state), so
this module holds the algorithm and nothing else. Pure and deterministic.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from backend.schema import (EnergyUse, MeasureId, MeasureResult, Plan, PlanItem, Ranged, Role,
                            SkippedItem, ValueUplift)

Evaluate = Callable[[MeasureId, Any], MeasureResult]
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
_REASONS = ("over_budget", "role", "feasibility", "no_savings", "already_done", "no_cost_data")


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


def _total(unit: str, ranges: list[Ranged], correlated: bool) -> Ranged:
    y0 = sum(r.expected for r in ranges)
    devs = [(r.expected - r.low, r.high - r.expected) for r in ranges]
    if correlated:        # all installed costs of a plan sit in one correlation group (UNC-02)
        low, high = _band(y0, [], (sum(d[0] for d in devs), sum(d[1] for d in devs)))
    else:                 # measure savings are treated as independent of one another
        low, high = _band(y0, devs)
    return Ranged(low=_usd(low), expected=_usd(y0), high=_usd(high), unit=unit)


def select_plan(measure_ids: list[MeasureId], role: Role, budget_usd: float, state: Any,
                evaluate: Evaluate, apply: Apply, energy: Energy,
                value_uplift: Optional[ValueUplift] = None) -> Plan:
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

    def evaluated(ids: list[str]) -> list[MeasureResult]:
        out = []
        for mid in ids:
            m = evaluate(mid, state)
            if mid in consent:
                m = m.model_copy(update={"warnings": [*m.warnings, CONSENT_WARNING]})
            out.append(m)
        return out

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

    while True:
        candidates = [m for m in evaluated(pool) if classify(m) is None]
        # zero-cost measures first (they always fit), then highest annual savings
        candidates.sort(key=lambda m: (_cost(m) > 0, -_savings(m), m.measure_id))
        pick = next((m for m in candidates if _cost(m) <= remaining), None)
        if pick is None:
            break
        if pick.finance.net_upfront_usd.high > remaining and BUDGET_WARNING not in pick.warnings:
            pick = pick.model_copy(update={"warnings": [*pick.warnings, BUDGET_WARNING]})
        cumulative += _cost(pick)
        remaining -= _cost(pick)
        selected.append(PlanItem(rank=len(selected) + 1, measure=pick,
                                 cumulative_upfront_usd=_usd(cumulative),
                                 remaining_budget_usd=_usd(budget_usd - cumulative)))
        state = apply(state, pick)
        pool.remove(pick.measure_id)

    # financeable: what is left, with positive savings, evaluated against the final state
    financeable: list[MeasureResult] = []
    for m in evaluated(pool):
        reason = classify(m)
        if reason is not None:
            skipped.append(reason)
            continue
        financeable.append(m)
        whole = _cost(m) > budget_usd
        skipped.append(SkippedItem(measure_id=m.measure_id, reason="over_budget", detail=(
            "Net upfront cost is above the whole budget; listed as financeable." if whole else
            "Net upfront cost is above the budget left after the selected measures; listed as financeable.")))
    financeable.sort(key=lambda m: (-_savings(m), m.measure_id))

    chosen = [i.measure for i in selected]
    zero = Ranged(low=0.0, expected=0.0, high=0.0, unit="USD")
    return Plan(
        budget_usd=budget_usd, selected=selected, financeable=financeable,
        skipped=sorted(skipped, key=lambda s: (_REASONS.index(s.reason), s.measure_id)),
        total_upfront_usd=_total("USD", [m.finance.net_upfront_usd for m in chosen], True) if chosen else zero,
        total_annual_savings_usd=_total("USD", [m.savings.cost_usd for m in chosen], False) if chosen else zero,
        total_co2_kg=_total("kg", [m.savings.co2_kg for m in chosen], False) if chosen else Ranged(low=0.0, expected=0.0, high=0.0, unit="kg"),
        baseline_after=energy(state), value_uplift=value_uplift)

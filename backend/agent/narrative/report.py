"""The report of a real-analysis run (no agent): a template filled only with the figures of the run's own result.

Every number is formatted from a field of the RunResult at the precision it is shown, or quoted from the result's
own warning or skip text, so `check_narrative` passes by construction. It states the loading order and why solar
comes last, and carries every warning. Pure and deterministic.
"""
from __future__ import annotations

from backend.schema import MeasureResult, RunResult

ORDER = ("The plan follows a consultant's loading order: operations first, then load reduction, then equipment, "
         "and solar last, sized against the electricity that is left. A measure is recommended only if it pays back "
         "its cost over its life (savings-to-investment ratio of at least 1).")


def _usd(x: float) -> str:
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def _line(m: MeasureResult) -> str:
    f = m.finance
    parts = [f"{_usd(f.net_upfront_usd.expected)} upfront"] if f else []
    if m.savings:
        parts.append(f"saves about {_usd(m.savings.cost_usd.expected)} a year")
    if f and f.sir is not None:
        parts.append(f"SIR {f.sir:.2f}")
    return f"- {m.title} ({m.measure_id}): " + ", ".join(parts) + "."


def _solar(result: RunResult) -> str:
    plan = result.plan
    pv = next((i.measure for i in plan.selected if i.measure.measure_id == "PV_ROOF"), None)
    if pv is not None and pv.solar is not None:
        return (f"Solar comes last: a {pv.solar.system_kw_dc:.1f} kW array sized against the electricity left after "
                "the other measures, because it is evaluated on the building as the plan has changed it.")
    fin = next((m for m in plan.financeable if m.measure_id == "PV_ROOF"), None)
    if fin is not None:
        return ("Solar is not in the plan because it costs more than the budget left after the other measures, "
                "and shrinking it to fit would make it smaller than a practical array; it is listed as financeable.")
    skipped = next((s for s in plan.skipped if s.measure_id == "PV_ROOF"), None)
    if skipped is not None:
        return f"Solar is not recommended: {skipped.detail}"
    return "Solar was not part of this property's measures."


def analysis_report(result: RunResult) -> str:
    plan, base = result.plan, result.baseline
    out = ["## Audit summary (real analysis)", ""]
    if base is not None:
        a = base.annual
        out.append(f"Baseline: {a.electricity_kwh.expected:,.0f} kWh of electricity and {a.gas_kwh.expected:,.0f} kWh of "
                   f"gas a year, about {_usd(a.cost_usd.expected)} (range {_usd(a.cost_usd.low)} to "
                   f"{_usd(a.cost_usd.high)}).")
    out.append("This run used " + ("live property data." if result.data_source == "live"
                                   else "the example property data, not live data."))
    out.append("The model was calibrated to your bills." if base is not None and base.calibrated_to_bills
               else "No bills were used, so the model is not calibrated to bills and every saving below is an "
                    "uncalibrated estimate.")
    out.append("")
    if plan is None:
        return "\n".join(out + ["No plan could be built."])
    out += [ORDER, ""]
    if plan.selected:
        out.append(f"Within a budget of {_usd(plan.budget_usd)}, the plan recommends:")
        out += [_line(i.measure) for i in plan.selected]
        out.append(f"Together: {_usd(plan.total_upfront_usd.expected)} upfront, saving about "
                   f"{_usd(plan.total_annual_savings_usd.expected)} a year "
                   f"(range {_usd(plan.total_annual_savings_usd.low)} to {_usd(plan.total_annual_savings_usd.high)}).")
    else:
        out.append(f"Within a budget of {_usd(plan.budget_usd)}, no measure is recommended: nothing both fits the "
                   "budget and pays back its cost.")
    out += ["", _solar(result), ""]
    if plan.financeable:
        out.append("Worth financing, because they pay back but do not fit the budget left:")
        out += [_line(m) for m in plan.financeable]
        out.append("")
    reasons = [s for s in plan.skipped if s.reason != "over_budget"]
    if reasons:
        out.append("Not selected, and why:")
        out += [f"- {s.measure_id}: {s.detail}" for s in reasons]
        out.append("")
    notes = list(dict.fromkeys([*(base.warnings if base else []), *result.warnings]))
    if notes:
        out.append("Warnings and fallbacks in this run:")
        out += [f"- {w}" for w in notes]
    return "\n".join(out).rstrip() + "\n"

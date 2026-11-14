"""Life-cycle economics (A25; physics 04 ECO-01 to ECO-13).

Pure functions, constant (real) dollars, end-of-year cash flows. Discount rate, analysis
period cap and escalation rates come from `backend/config.py` and are echoed in the result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend import config
from backend.schema import (EnergyUse, FinancialBreakdown, FinancingScenario, Incentive, Ranged,
                            Tariff)

# ---------- ECO-01 to ECO-04: rates and factors ----------

def real_rate(nominal: float, inflation: float) -> float:
    return (1 + nominal) / (1 + inflation) - 1


def nominal_rate(real: float, inflation: float) -> float:
    return (1 + inflation) * (1 + real) - 1


def spv(d: float, t: float) -> float:
    return 1.0 / (1.0 + d) ** t


def upv(d: float, n: int) -> float:
    if abs(d) < 1e-12:
        return float(n)
    return ((1 + d) ** n - 1) / (d * (1 + d) ** n)


def upv_star(e: float, d: float, n: int) -> float:
    """Sum over t = 1..N of ((1 + e) / (1 + d))^t; the first-year amount is A_0 (1 + e)."""
    if abs(d - e) < 1e-12:
        return float(n)
    return (1 + e) / (d - e) * (1 - ((1 + e) / (1 + d)) ** n)


# ---------- ECO-05, ECO-06: defaults and escalation ----------

@dataclass(frozen=True)
class EconomicParams:
    discount_rate: float
    nominal_discount_rate: float
    inflation: float
    analysis_period_years: int
    electricity_escalation: Ranged
    gas_escalation: Ranged
    source: str
    notes: tuple = ()


def city_key(state: str) -> str:
    """ECO-06 mapping: California -> Pacific (Los Angeles table), Texas -> West South Central."""
    key = {"CA": "los_angeles", "TX": "houston"}.get((state or "").upper())
    if key is None:
        raise ValueError(f"no escalation table for state {state!r}; ECO-06 covers CA and TX")
    return key


def equivalent_escalation_rate(index_by_year: dict[int, float], base_year: int, d: float, n: int) -> float:
    """ECO-06: the constant real rate e whose UPV*(e, d, N) equals the present value of the
    published year-by-year index. Bisection on [-0.2, 0.2]; UPV* is strictly increasing in e."""
    base = index_by_year[base_year]
    target = sum((index_by_year[base_year + t] / base) / (1 + d) ** t for t in range(1, n + 1))
    low, high = -0.2, 0.2
    for _ in range(200):
        mid = (low + high) / 2
        if upv_star(mid, d, n) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def default_escalation(city: str, sector: str, fuel: str, n: int) -> tuple[Ranged, list[str]]:
    """Expected ECO-06 value for the analysis period, with the +/- 1 point band of rule 2.
    The table holds N = 10, 15, 20, 25 and 30; any other N is interpolated (or held at the
    nearest column outside 10..30) and the returned notes say so."""
    columns = config.ESCALATION_REAL_PCT[(city, sector, fuel)]
    ns = sorted(columns)
    notes: list[str] = []
    if n in columns:
        pct = columns[n]
    elif n <= ns[0] or n >= ns[-1]:
        pct = columns[ns[0] if n <= ns[0] else ns[-1]]
        notes.append(f"{fuel} escalation held at the N={ns[0] if n <= ns[0] else ns[-1]} value for N={n} (ECO-06 table covers 10 to 30)")
    else:
        lo = max(c for c in ns if c < n)
        hi = min(c for c in ns if c > n)
        pct = columns[lo] + (columns[hi] - columns[lo]) * (n - lo) / (hi - lo)
        notes.append(f"{fuel} escalation interpolated between N={lo} and N={hi} (ECO-06 table; exact value needs the AS135 index tables)")
    e = pct / 100.0
    return Ranged(low=e - config.ESCALATION_BAND, expected=e, high=e + config.ESCALATION_BAND, unit="1/yr"), notes


def economic_defaults(city: str, sector: str, useful_life_years: int) -> EconomicParams:
    n = min(useful_life_years, config.ANALYSIS_PERIOD_CAP_YEARS)
    elec, n1 = default_escalation(city, sector, "electricity", n)
    gas, n2 = default_escalation(city, sector, "gas", n)
    return EconomicParams(
        discount_rate=config.DISCOUNT_RATE_REAL, nominal_discount_rate=config.DISCOUNT_RATE_NOMINAL,
        inflation=config.INFLATION, analysis_period_years=n, electricity_escalation=elec,
        gas_escalation=gas,
        source="physics 04 ECO-05 (DOE/FEMP 2025 rates, AS135-2025) and ECO-06 (EIA AEO 2025 reference case); band +/-1 point is a project judgement",
        notes=tuple(n1 + n2))


# ---------- ECO-07, ECO-08: cash flows, present values, NPV ----------

def residual_value_linear(installed_cost_usd: float, useful_life_years: int, n: int) -> float:
    return installed_cost_usd * (useful_life_years - n) / useful_life_years if useful_life_years > n else 0.0


def _stream_pv(s_elec, s_gas, s_exp, e_elec, e_gas, e_exp, d, n):
    return (s_elec * upv_star(e_elec, d, n) + s_gas * upv_star(e_gas, d, n)
            + s_exp * upv_star(e_exp, d, n))


def present_values(net_upfront_usd, savings_elec_usd, savings_gas_usd, export_usd, om_saving_usd,
                   d, e_elec, e_gas, e_export, n, replacements=(), residual_usd=0.0,
                   later_incentives=()) -> tuple[float, float]:
    """(PV_S, PV_I) exactly as ECO-07."""
    pv_s = _stream_pv(savings_elec_usd, savings_gas_usd, export_usd, e_elec, e_gas, e_export, d, n) \
        + om_saving_usd * upv(d, n)
    pv_i = (net_upfront_usd + sum(r * spv(d, t) for t, r in replacements)
            - residual_usd * spv(d, n) - sum(c * spv(d, t) for t, c in later_incentives))
    return pv_s, pv_i


def npv_measure(net_upfront_usd, savings_elec_usd, savings_gas_usd, export_usd, om_saving_usd,
                d, e_elec, e_gas, e_export, n, replacements=(), residual_usd=0.0,
                later_incentives=()) -> float:
    pv_s, pv_i = present_values(net_upfront_usd, savings_elec_usd, savings_gas_usd, export_usd,
                                om_saving_usd, d, e_elec, e_gas, e_export, n, replacements,
                                residual_usd, later_incentives)
    return pv_s - pv_i


def cashflows(net_upfront_usd, savings_elec_usd, savings_gas_usd, export_usd, om_saving_usd,
              e_elec, e_gas, e_export, n, replacements=(), residual_usd=0.0,
              later_incentives=()) -> list[float]:
    """The general form of ECO-07: CF_0 = -I_0, CF_t = S_t + dOM - R_t + C_t, RV_N added at N."""
    flows = [-net_upfront_usd]
    for t in range(1, n + 1):
        cf = (savings_elec_usd * (1 + e_elec) ** t + savings_gas_usd * (1 + e_gas) ** t
              + export_usd * (1 + e_export) ** t + om_saving_usd)
        cf -= sum(r for tk, r in replacements if tk == t)
        cf += sum(c for tj, c in later_incentives if tj == t)
        if t == n:
            cf += residual_usd
        flows.append(cf)
    return flows


# ---------- ECO-09, ECO-10: SIR and rates of return ----------

def sir(pv_savings_usd: float, pv_investment_usd: float) -> Optional[float]:
    return None if pv_investment_usd <= 0 else pv_savings_usd / pv_investment_usd


def airr(sir_value: float, d: float, n: int) -> Optional[float]:
    return None if sir_value is None or sir_value <= 0 else (1 + d) * sir_value ** (1.0 / n) - 1


def irr(flows: list[float]) -> Optional[float]:
    """Conventional IRR, only when the flows change sign once (one outlay, then non-negative
    flows) and the undiscounted flows repay the outlay; otherwise None (report AIRR)."""
    if len(flows) < 2 or flows[0] >= 0 or any(cf < 0 for cf in flows[1:]):
        return None
    if sum(flows) <= 0:
        return None

    def npv_at(rate):
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(flows))
    low, high = -0.99, 10.0
    if npv_at(low) * npv_at(high) > 0:
        return None
    for _ in range(300):
        mid = (low + high) / 2
        if npv_at(low) * npv_at(mid) <= 0:
            high = mid
        else:
            low = mid
    return (low + high) / 2


# ---------- ECO-11: payback ----------

def simple_payback(net_upfront_usd: float, first_year_net_savings_usd: float) -> Optional[float]:
    """Screening form: I_0 / (S_0 + dOM). Zero when nothing is invested; None when there is
    nothing saved."""
    if net_upfront_usd <= 0:
        return 0.0
    return None if first_year_net_savings_usd <= 0 else net_upfront_usd / first_year_net_savings_usd


def discounted_payback(flows: list[float], d: float) -> Optional[float]:
    """General form with fractional-year interpolation. A later replacement that takes the
    cumulative sum back under the outlay moves the answer to the last crossing (HB135 6.4.2)."""
    outlay = -flows[0]
    if outlay <= 0:
        return 0.0
    cum, found, cum_before = 0.0, None, 0.0
    for t in range(1, len(flows)):
        pv = flows[t] / (1 + d) ** t
        prev = cum
        cum += pv
        if cum >= outlay:
            if found is None or prev < outlay:
                found, cum_before = t - 1 + (outlay - prev) / pv, prev
        else:
            found = None                       # fell back under: wait for the later crossing
    return found


# ---------- ECO-13: incentives in the cash flow ----------

def incentive_cashflows(incentives: list[Incentive], marginal_tax_rate: Optional[float],
                        level: str = "expected") -> tuple[float, list[tuple[int, float]]]:
    """(upfront total, later items as (year, USD)). Only verified incentives the project is
    eligible for count; a tax deduction needs the marginal rate and is omitted without one; a
    performance payment has no stated term in the contract and is omitted."""
    upfront, later = 0.0, []
    for inc in incentives:
        if inc.status != "verified" or inc.eligibility == "not_eligible":
            continue
        amount = getattr(inc.amount_usd, level)
        if amount == 0:
            continue
        if inc.kind == "upfront_rebate":
            upfront += amount
        elif inc.kind in ("tax_credit", "rebate_after_install"):
            later.append((1, amount))
        elif inc.kind == "tax_deduction" and marginal_tax_rate is not None:
            later.append((1, amount * marginal_tax_rate))
    return upfront, later


# ---------- the cash scenario and the whole breakdown ----------

CASH_NOTE = ("Paid in full at installation. First-year net cash flow is savings less the change in "
             "operation and maintenance; the investment is shown as net upfront cash (physics 04 ECO-12).")


def cash_scenario(first_year_net_savings_usd: Ranged, notes: Optional[list[str]] = None) -> FinancingScenario:
    return FinancingScenario(kind="cash", eligible=True, financed_usd=0.0, rate=None, term_years=None,
                             annual_payment_usd=0.0, net_cashflow_year1_usd=first_year_net_savings_usd,
                             program_sir=None, notes=[CASH_NOTE, *(notes or [])])


def _quadrature(y0: float, runs: dict) -> tuple[float, float]:
    """UNC-02. `runs` maps an input to its two one-at-a-time results (low run, high run); each
    deviation goes to the side it falls on, and independent inputs add in quadrature."""
    lo = sum(min(a - y0, b - y0, 0.0) ** 2 for a, b in runs.values())
    hi = sum(max(a - y0, b - y0, 0.0) ** 2 for a, b in runs.values())
    return y0 - lo ** 0.5, y0 + hi ** 0.5


def propagate(f, base: dict, ends: dict) -> tuple[float, float]:
    """UNC-02 for a function of named inputs: 2N + 1 runs, every input in its own correlation
    group (this measure's cost, savings and incentives are independent of one another)."""
    y0 = f(base)
    return _quadrature(y0, {k: (f({**base, k: lo}), f({**base, k: hi})) for k, (lo, hi) in ends.items()
                            if lo != hi})


def _r(x: float, places: int = 2) -> float:
    return round(x, places)


def _usd(low: float, expected: float, high: float) -> Ranged:
    low, expected, high = sorted((_r(low), _r(expected), _r(high)))
    return Ranged(low=low, expected=expected, high=high, unit="USD")


def financial_breakdown(*, installed_cost_usd: Ranged, cost_source: str, net_upfront_usd: Ranged,
                        incentives: list[Incentive], useful_life_years: int,
                        annual_om_change_usd: float, savings: EnergyUse, tariff: Tariff,
                        state: str, segment: str, degradation_rate: float = 0.0,
                        replacements: tuple = (), marginal_tax_rate: Optional[float] = None,
                        discount_rate: Optional[float] = None) -> FinancialBreakdown:
    """ECO-05 to ECO-13 for one priced measure. `savings` is the measure's first-year saving at
    base-date prices; the gas part is priced at the tariff's gas price and the rest (electricity
    and, for solar, export) is escalated at the electricity rate (ECO-06 rule 4). A solar
    measure's annual degradation is folded into the electricity stream (ECO-07 validity note).
    `discount_rate` defaults to the config value and is echoed in the result."""
    d = config.DISCOUNT_RATE_REAL if discount_rate is None else discount_rate
    n = min(useful_life_years, config.ANALYSIS_PERIOD_CAP_YEARS)
    city = city_key(state)
    e_elec = default_escalation(city, segment, "electricity", n)[0].expected
    e_gas = default_escalation(city, segment, "gas", n)[0].expected
    e_elec_eff = (1 + e_elec) * (1 - degradation_rate) - 1
    residual = residual_value_linear(installed_cost_usd.expected, useful_life_years, n)

    gas_share = 0.0
    if tariff.gas_usd_per_kwh and savings.cost_usd.expected > 0:
        gas_share = max(0.0, min(1.0, savings.gas_kwh.expected * tariff.gas_usd_per_kwh / savings.cost_usd.expected))
    om_saving = -annual_om_change_usd

    def npv_of(vals: dict, rate: float = d) -> float:
        _, later = incentive_cashflows(incentives, marginal_tax_rate, vals["incentives"])
        sv = vals["savings"]
        return npv_measure(vals["net_upfront"], sv * (1 - gas_share), sv * gas_share, 0.0, om_saving,
                           rate, e_elec_eff, e_gas, e_elec_eff, n, replacements, residual, later)

    s = savings.cost_usd
    base = {"savings": s.expected, "net_upfront": net_upfront_usd.expected, "incentives": "expected"}
    ends = {"savings": (s.low, s.high), "net_upfront": (net_upfront_usd.low, net_upfront_usd.high),
            "incentives": ("low", "high")}
    npv_exp = npv_of(base)
    npv_low, npv_high = propagate(npv_of, base, ends)
    npv_sens = npv_of(base, config.SENSITIVITY_DISCOUNT_RATE)

    def run(savings_usd: float, net_upfront: float, level: str, rate: float):
        _, later = incentive_cashflows(incentives, marginal_tax_rate, level)
        parts = (savings_usd * (1 - gas_share), savings_usd * gas_share, 0.0)
        args = (net_upfront, *parts, om_saving, rate, e_elec_eff, e_gas, e_elec_eff, n)
        extra = dict(replacements=replacements, residual_usd=residual, later_incentives=later)
        return args, extra

    args, extra = run(s.expected, net_upfront_usd.expected, "expected", d)
    pv_s, pv_i = present_values(*args, **extra)
    sir_value = sir(pv_s, pv_i)
    flows = cashflows(args[0], args[1], args[2], args[3], om_saving, e_elec_eff, e_gas, e_elec_eff, n, **extra)

    def payback_of(vals: dict) -> Optional[float]:
        return simple_payback(vals["net_upfront"], vals["savings"] + om_saving)

    simple = None
    pb0 = payback_of(base)
    if pb0 is not None:
        runs = {k: (payback_of({**base, k: lo}), payback_of({**base, k: hi}))
                for k, (lo, hi) in ends.items() if k != "incentives"}
        if all(v is not None for pair in runs.values() for v in pair):
            low, high = _quadrature(pb0, {k: pair for k, pair in runs.items()})
            simple = Ranged(low=_r(low), expected=_r(pb0), high=_r(high), unit="years")

    dp = discounted_payback(flows, d)
    year1 = Ranged(low=_r(s.low + om_saving), expected=_r(s.expected + om_saving),
                   high=_r(s.high + om_saving), unit="USD")
    notes = default_escalation(city, segment, "electricity", n)[1] + default_escalation(city, segment, "gas", n)[1]
    irr_value = irr(flows)
    return FinancialBreakdown(
        installed_cost_usd=installed_cost_usd, cost_source=cost_source, incentives=list(incentives),
        net_upfront_usd=net_upfront_usd, annual_savings_usd=_usd(s.low, s.expected, s.high),
        annual_om_change_usd=annual_om_change_usd, useful_life_years=useful_life_years,
        simple_payback_years=simple, discounted_payback_years=None if dp is None else _r(dp, 1),
        npv_usd=_usd(npv_low, npv_exp, npv_high), npv_sensitivity_usd=_r(npv_sens),
        sir=None if sir_value is None else round(sir_value, 3),
        irr=None if irr_value is None else round(irr_value, 4),
        airr=None if sir_value is None or airr(sir_value, d, n) is None else round(airr(sir_value, d, n), 4),
        discount_rate=d, electricity_escalation=round(e_elec, 4), gas_escalation=round(e_gas, 4),
        analysis_period_years=n, financing=[cash_scenario(year1, notes)])

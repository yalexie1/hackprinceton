"""C-PACE scenario (A28; SPEC 6.6, physics 04 ECO-12 and ECO-12b, specs/legal/texas.md section 6,
specs/legal/california.md section 7).

Rate and term are market quotes, not defaults from a publication: `config.CPACE_RATE` and
`config.CPACE_TERM_YEARS` are placeholders (None), so without both the scenario reports the
financed amount and the eligibility rules but computes no payment, and says so. Nothing here
invents a legal fact: a state or region the rules were not read for is not eligible.
Pure and deterministic.
"""
from __future__ import annotations

from typing import Optional

from backend import config
from backend.schema import FinancingScenario, MeasureResult, PropertySummary, Ranged

# Not permanent improvements fixed to real property (texas.md TX-PACE-03, california.md CA-PACE-01):
NOT_FINANCEABLE = {"LAYOUT": "desk placement", "PLUG_MGMT": "plug-load management"}

TX_LIEN = ("The assessment is a first and prior lien with the priority of an ad valorem tax lien and "
           "runs with the land (Loc. Gov't Code section 399.014).")
TX_CONSENT = ("Texas: written notice to any mortgage holder at least 30 days before the owner contract, "
              "and the holder's written consent, are statutory preconditions (Loc. Gov't Code section 399.010).")
CA_LIEN = ("The assessment and any interest and penalties are a lien on the parcel until paid, collected "
           "with and in the same manner as the general property taxes (Streets and Highways Code 5898.30; "
           "specs/legal/california.md CA-PACE-10).")
CA_CONSENT = ("Existing mortgage holder: consent or acknowledgment is a programme and capital-provider "
              "requirement, not a California statutory condition (specs/legal/california.md section 7.6).")
CA_HYPOTHETICAL = ("Hypothetical: no official page names a programme, public agency or administrator that "
                   "takes commercial PACE applications in the City or County of Los Angeles "
                   "(specs/legal/california.md section 7.3, CA-PACE-15 and CA-PACE-16), so this scenario "
                   "is not eligible until one is confirmed.")
TX_ELIGIBLE_PROPERTY = ("Texas: the property must be commercial, industrial, nonprofit or residential with "
                        "five or more units, and must lie in a PACE region (Loc. Gov't Code sections 399.002(5), 399.006).")


def level_payment(principal_usd: float, rate: float, term_years: int, payments_per_year: int = 1) -> float:
    """ECO-12: level payment in arrears on a fully amortising, fixed-rate assessment."""
    n = term_years * payments_per_year
    if abs(rate) < 1e-12:
        return principal_usd / n
    i = rate / payments_per_year
    return principal_usd * i * (1 + i) ** n / ((1 + i) ** n - 1)


def program_sir(annual_net_savings_usd, annual_payment_usd: float, term_years: int,
                cash_portion_usd: float = 0.0) -> float:
    """ECO-12b: undiscounted savings over the term over all assessment payments plus any cash.
    `annual_net_savings_usd` is one level amount or a list of `term_years` amounts."""
    savings = (sum(annual_net_savings_usd) if isinstance(annual_net_savings_usd, (list, tuple))
               else annual_net_savings_usd * term_years)
    cost = term_years * annual_payment_usd + cash_portion_usd
    return savings / cost if cost > 0 else 0.0


def _r(x: float, places: int = 2) -> float:
    return round(x, places)


def _eligible_property(summary: PropertySummary, units: Optional[int]) -> tuple[bool, Optional[str]]:
    """The property-type rule shared by the two states: a residential property needs five or more
    units; a house, or any residential property under five units, is never eligible."""
    if summary.segment == "commercial":
        return True, None
    if units is not None and units >= 5:
        return True, None
    return False, ("Not eligible: C-PACE is for commercial property and residential property with "
                   "five or more units; a house or any residential property under five units is "
                   "financed in cash (texas.md TX-PACE-01; SPEC 6.6).")


def cpace_scenario(measure: MeasureResult, summary: PropertySummary, *, rate: Optional[float] = None,
                   term_years: Optional[int] = None, units: Optional[int] = None,
                   in_pace_region: Optional[bool] = None, ca_programme_confirmed: bool = False,
                   cash_portion_usd: float = 0.0, market_value_usd: Optional[float] = None,
                   annual_property_tax_usd: Optional[float] = None) -> FinancingScenario:
    """A priced measure financed by C-PACE. `rate` and `term_years` default to the config
    placeholders (None): a quote is needed. `in_pace_region` is True only when the property is
    shown to lie in a PACE region (in Houston: inside the incorporated city, not CoStar's cityId)."""
    rate = config.CPACE_RATE if rate is None else rate
    term_years = config.CPACE_TERM_YEARS if term_years is None else term_years
    notes: list[str] = []
    zero = Ranged(low=0.0, expected=0.0, high=0.0, unit="USD")
    finance, savings = measure.finance, measure.savings
    if finance is None or savings is None:
        return FinancingScenario(kind="cpace", eligible=False, net_cashflow_year1_usd=zero,
                                 notes=["Not priced: the measure has no cost, so there is nothing to finance."])

    eligible, why = _eligible_property(summary, units)
    if why:
        notes.append(why)
    state = summary.state.upper()
    if state == "CA":
        if not ca_programme_confirmed:
            eligible = False
            notes.append(CA_HYPOTHETICAL)
    elif state == "TX":
        if eligible and in_pace_region is not True:
            eligible = False
            notes.append("Not shown to be in a PACE region: the City of Houston is one; a property in "
                         "unincorporated Harris County or another city is not on the administrator's "
                         "list until confirmed (texas.md section 6.4).")
    else:
        eligible = False
        notes.append(f"No C-PACE rules were read for {summary.state}; the scenario is not offered.")

    useful_life = finance.useful_life_years
    financed = max(0.0, finance.net_upfront_usd.expected - cash_portion_usd)
    reason = NOT_FINANCEABLE.get(measure.measure_id)
    if reason or financed <= 0:
        eligible, financed = False, 0.0
        notes.append(f"Nothing to finance: {reason} is not a permanent improvement fixed to the property."
                     if reason else "Nothing to finance: the measure has no cost.")

    s = savings.cost_usd
    om = -finance.annual_om_change_usd
    net_savings = Ranged(low=_r(s.low + om), expected=_r(s.expected + om), high=_r(s.high + om), unit="USD")

    term = None
    if term_years is not None:
        term = min(int(term_years), useful_life)
        if term < term_years:
            notes.append(f"Term shortened from {term_years} to {term} years: it may not exceed the useful life of the improvement (texas.md TX-PACE-11).")
        else:
            notes.append(f"Term of {term} years does not exceed the useful life of {useful_life} years"
                         + (": a programme rule for a new commercial assessment in California, not a statutory condition (CA-PACE-11)." if state == "CA" else "."))

    payment, sir_prog = 0.0, None
    year1 = net_savings
    if financed > 0 and rate is not None and term is not None:
        payment = _r(level_payment(financed, rate, term))
        year1 = Ranged(low=_r(net_savings.low - payment), expected=_r(net_savings.expected - payment),
                       high=_r(net_savings.high - payment), unit="USD")
        sir_prog = round(program_sir(net_savings.expected, payment, term, cash_portion_usd), 3)
        sdr = round(net_savings.expected / payment, 2) if payment > 0 else None
        if state == "TX":
            verdict = ("Texas requires at least 1; this passes." if sir_prog >= 1 else
                       "Texas requires at least 1; this does not pass, so the scenario is not eligible.")
            notes.append(f"Program SIR {sir_prog:.2f}: undiscounted savings over the {term}-year term divided by all "
                         f"assessment payments (physics 04 ECO-12b). {verdict}")
            if sir_prog < 1:
                eligible = False
            elif sir_prog < 1.05:
                notes.append("Warning: the program SIR is below 1.05, a thin margin for the independent reviewer.")
        else:
            notes.append(f"Program SIR {sir_prog:.2f}: undiscounted savings over the {term}-year term divided by all "
                         "assessment payments (physics 04 ECO-12b). California has no statutory SIR test; a "
                         "programme may apply one, so the ratio is a screen only.")
        if sdr is not None:
            notes.append(f"Savings-to-debt-service ratio {sdr:.2f}.")
    elif financed > 0:
        eligible = False
        notes.append("No rate and term were given: they are market quotes, not defaults from a publication "
                     "(config CPACE_RATE and CPACE_TERM_YEARS are placeholders), so the payment, the first-year "
                     "cash flow after the payment and the program SIR are not computed.")
    if financed > 0 and rate is not None:
        notes.append("Rate and term are market inputs, not defaults from a publication.")

    if state == "TX":
        notes += [TX_LIEN, TX_CONSENT, TX_ELIGIBLE_PROPERTY]
    elif state == "CA":
        notes += [CA_LIEN, CA_CONSENT, _ca_tax_test(payment, market_value_usd, annual_property_tax_usd)]
    else:
        notes += ["The assessment is a lien on the property that runs with it, and an existing mortgage "
                  "holder's position must be confirmed before any commitment."]
    return FinancingScenario(kind="cpace", eligible=eligible, financed_usd=_r(financed), rate=rate if financed > 0 else None,
                             term_years=term if financed > 0 else None, annual_payment_usd=payment,
                             net_cashflow_year1_usd=year1, program_sir=sir_prog, notes=notes)


def _ca_tax_test(payment: float, market_value: Optional[float], annual_taxes: Optional[float]) -> str:
    """California Streets and Highways Code 5898.15: annual taxes plus assessments, with this one,
    may not exceed 5 percent of market value at approval."""
    base = ("Statutory test for commercial property: annual property taxes plus assessments, with this one, "
            "may not exceed 5 percent of market value at approval (Streets and Highways Code 5898.15; CA-PACE-07).")
    if market_value and annual_taxes is not None:
        ratio = (annual_taxes + payment) / market_value
        return base + f" With the inputs given the ratio is {ratio:.2%}: {'within' if ratio <= 0.05 else 'over'} the limit."
    return base + " It cannot be completed without the market value and the tax bill."

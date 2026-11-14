"""Value uplift (A30; SPEC 6.6, physics 04 VAL-01 and VAL-03).

The estimated change in property value from the plan's annual savings, capitalised at a rate
from comparable sales. It is shown beside the plan totals and is never added to savings, NPV,
SIR, payback or the ranking. With no market data, no cap rate or too few comparables the module
returns None rather than a guess. Pure and deterministic.
"""
from __future__ import annotations

from typing import Optional

from backend.schema import MarketData, Ranged, ValueUplift

MIN_COMPS = 10                 # VAL-01: with fewer usable comps the module returns None
CAPITALISATION_FACTOR = 0.5    # VAL-01 [J]: half capitalisation for a retrofit without a recognised label
PREMIUM_CAP = 0.16             # VAL-01: dV_high is at most 16 percent of the property's estimated value (EKQ)
PV_PREMIUM_USD_PER_W = 4.00    # VAL-03: LBNL-SITS average premium for host-owned rooftop PV

OWNER_PAYS_UTILITIES = Ranged(low=1.0, expected=1.0, high=1.0, unit="-")


def _usd(x: float) -> float:
    return round(x, 2)


def value_uplift_income(net_saving_usd: Ranged, owner_share: Ranged, cap_rate: Ranged,
                        property_value_usd: Optional[float] = None) -> Optional[Ranged]:
    """VAL-01. low 0; expected 0.5 * phi * saving / R_high; high phi * saving / R_low, the high
    capped at 16 percent of the property's estimated value when that is known. None when there is
    no saving to capitalise or no usable cap rate."""
    if net_saving_usd.expected <= 0 or cap_rate.low <= 0 or cap_rate.high <= 0:
        return None
    expected = CAPITALISATION_FACTOR * owner_share.expected * net_saving_usd.expected / cap_rate.high
    high = owner_share.high * max(net_saving_usd.high, 0.0) / cap_rate.low
    if property_value_usd is not None and property_value_usd > 0:
        high = min(high, PREMIUM_CAP * property_value_usd)
    expected = min(expected, high)
    return Ranged(low=0.0, expected=_usd(expected), high=_usd(high), unit="USD")


def value_uplift_home_pv(system_kw_dc: float, net_installed_cost_usd: float) -> Ranged:
    """VAL-03. high = 4.00 USD per W DC; expected = min(high, net installed cost); low = 0."""
    high = PV_PREMIUM_USD_PER_W * system_kw_dc * 1000.0
    return Ranged(low=0.0, expected=_usd(min(high, net_installed_cost_usd)), high=_usd(high), unit="USD")


def plan_value_uplift(market: Optional[MarketData], net_saving_usd: Ranged,
                      owner_share: Optional[Ranged] = None,
                      floor_area_m2: Optional[float] = None) -> Optional[ValueUplift]:
    """The `Plan.value_uplift` of a commercial or multifamily property: VAL-01 on CoStar market
    data. `net_saving_usd` is the plan's first-year saving net of the change in O&M. `owner_share`
    (phi) is 1 when the owner pays the utilities, 0 when tenants do; unless the caller says
    otherwise it is 1, and the notes say so. None without market data, a cap rate, or at least
    10 comparables."""
    if market is None or market.cap_rate is None or market.comp_count < MIN_COMPS:
        return None
    phi = owner_share or OWNER_PAYS_UTILITIES
    value_of_property = None
    if market.sale_price_usd_per_m2 is not None and floor_area_m2:
        value_of_property = market.sale_price_usd_per_m2.expected * floor_area_m2
    value = value_uplift_income(net_saving_usd, phi, market.cap_rate, value_of_property)
    if value is None:
        return None
    notes = [
        "Low is zero: the market may not price the saving at all. Expected is half capitalisation at the "
        "least favourable cap rate; high is full capitalisation at the most favourable one (physics 04 VAL-01).",
        ("Assumes the owner pays the utilities (phi = 1). Under a triple-net lease the saving goes to the "
         "tenants and the uplift is zero." if phi == OWNER_PAYS_UTILITIES else
         f"Owner share of the saving (phi) is {phi.low:g} to {phi.high:g}, expected {phi.expected:g}."),
        "The evidence is for labelled offices with data to 2008; a retrofit without a label may earn less. "
        "Cap rates move with interest rates.",
        "Not an appraisal. Never added to savings, NPV, SIR, payback or the ranking.",
    ]
    if value_of_property is not None and value.high >= PREMIUM_CAP * value_of_property - 0.01:
        notes.append("High is capped at 16 percent of the property's estimated value, the sale-price premium "
                     "found for green-rated offices (physics 04 VAL-01).")
    return ValueUplift(value_usd=value, method="VAL-01", cap_rate=market.cap_rate,
                       comp_count=market.comp_count, notes=notes)


def home_pv_uplift(system_kw_dc: float, net_installed_cost_usd: float) -> ValueUplift:
    """The `PV_ROOF` value uplift of a home with owned rooftop solar (VAL-03). No other home
    measure has one: no study was opened."""
    return ValueUplift(
        value_usd=value_uplift_home_pv(system_kw_dc, net_installed_cost_usd), method="VAL-03", comp_count=0,
        notes=["Host-owned systems only; the premium is for a new system and falls with its age. Sales in the "
               "study end in 2013 and no Texas result was read (physics 04 VAL-03, LBNL-6942E).",
               "Expected is capped at the net installed cost, the best proxy for the market premium.",
               "Not an appraisal. Never added to savings, NPV, SIR, payback or the ranking."])

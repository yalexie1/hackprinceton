"""Incentive registry and amounts (A24; physics 04 INC-01 to INC-40).

Entries live in `data/incentives.json` with their citation and the date checked. An amount
is computed from a rule and the measure's own parameters. When eligibility depends on a fact
the tool cannot see, the entry is `needs_confirmation` with low 0, expected 0 and high the
rule amount (physics 04, section 4 preamble). Only `upfront_rebate` incentives that are
`verified` reduce `net_upfront_usd`; tax credits, deductions, rebates after installation and
every unverified or expired entry are reported but left out of every total.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend.schema import Incentive, MeasureResult, PropertySummary, Ranged

_DATA = Path(__file__).resolve().parent / "data"
SQFT_PER_M2 = 10.7639          # INC-40
RSI_TO_R_US = 5.678            # physics 04 conversions: R-value (US, h ft2 F/Btu) = 5.678 x RSI (m2 K/W)


def registry() -> list[dict]:
    return json.loads((_DATA / "incentives.json").read_text())


def utility_of(summary: PropertySummary) -> Optional[str]:
    """The utility a registry region refers to, from the property's city. LADWP serves the
    City of Los Angeles only; CenterPoint is the Houston Electric territory."""
    city, state = (summary.city or "").strip().lower(), (summary.state or "").strip().upper()
    if city == "los angeles" and state == "CA":
        return "LADWP"
    if city == "houston" and state == "TX":
        return "CenterPoint"
    return None


def _usd(low: float, expected: float, high: float) -> Ranged:
    return Ranged(low=round(low, 2), expected=round(expected, 2), high=round(high, 2), unit="USD")


def _full(amount: float) -> Ranged:
    return _usd(amount, amount, amount)


def _confirm(high: float) -> tuple[Ranged, str]:
    return _usd(0.0, 0.0, high), "needs_confirmation"


def _amount(entry: dict, measure: MeasureResult, quantity: Optional[float], cost: Optional[Ranged],
            extra: dict) -> tuple[Ranged, str]:
    """(amount, eligibility) for one registry entry."""
    p = {**measure.params, **extra}
    rule = entry["rule"]
    if rule == "none":
        return _usd(0, 0, 0), entry.get("eligibility", "confirmed")
    if rule == "fixed":
        seer2 = p.get("seer2")
        if seer2 is None:
            return _confirm(entry["rate"])
        return (_full(entry["rate"]), "confirmed") if seer2 >= 15.2 else (_usd(0, 0, 0), "not_eligible")
    if rule == "per_kw_dc":
        kw = measure.solar.system_kw_dc if measure.solar else (quantity or 0) / 1000.0
        amount = entry["rate"] * min(kw, entry["cap"])
        return _usd(amount, amount, amount), "confirmed"
    if rule == "pct_cost":
        if cost is None:
            return _usd(0, 0, 0), "needs_confirmation"
        full = entry["rate"] * cost.expected
        met = all(p.get(k) is True for k in entry["requires"])
        return (_usd(full, full, full), "confirmed") if met else _confirm(full)
    if rule == "per_sqft_cool_roof":
        sqft = (p.get("roof_area_m2") or p.get("area_m2") or quantity or 0) * SQFT_PER_M2
        sri, slope = p.get("sri_3yr"), p.get("roof_slope")        # "low" (2:12 or less) or "steep"
        if sri is None or slope not in ("low", "steep"):
            return _confirm(0.60 * sqft)
        floor_hi = (78, 85) if slope == "low" else (20, 35)
        rate = 0.60 if sri >= floor_hi[1] else 0.20 if sri >= floor_hi[0] else 0.0
        return (_usd(rate * sqft, rate * sqft, rate * sqft), "confirmed") if rate else (_usd(0, 0, 0), "not_eligible")
    if rule == "per_sqft_windows":
        sqft = (p.get("glazing_area_m2") or p.get("area_m2") or quantity or 0) * SQFT_PER_M2
        u, shgc = p.get("u_factor"), p.get("shgc")
        if u is None or shgc is None:
            return _confirm(entry["rate"] * sqft)
        ok = u <= 0.30 and shgc <= 0.25
        return (_usd(entry["rate"] * sqft, entry["rate"] * sqft, entry["rate"] * sqft), "confirmed") if ok else (_usd(0, 0, 0), "not_eligible")
    if rule in ("per_sqft_attic", "per_sqft_attic_extra"):
        sqft = (p.get("area_m2") or quantity or 0) * SQFT_PER_M2
        if rule == "per_sqft_attic_extra":
            return _full(entry["rate"] * sqft), "confirmed"
        r_us = p.get("installed_r_value")
        if r_us is None and p.get("target_u_w_m2k"):
            r_us = RSI_TO_R_US / p["target_u_w_m2k"]          # R-value (US) = 5.678 x RSI
        if r_us is None:
            return _full(0.50 * sqft), "confirmed"
        rate = 0.50 if r_us > 19 else 0.30
        return _full(rate * sqft), "confirmed"
    if rule == "per_ton_tiers":
        tons = p.get("capacity_tons") or quantity or 0
        tiers = entry["tiers_ductless"] if p.get("ductless") else entry["tiers"]
        seer2, hspf2 = p.get("seer2"), p.get("hspf2")
        if seer2 is None or hspf2 is None:
            return _confirm(tiers[-1][2] * tons)
        rate = 0
        for min_seer, min_hspf, tier_rate in tiers:
            if seer2 > min_seer and hspf2 > min_hspf:
                rate = tier_rate
        return (_usd(rate * tons, rate * tons, rate * tons), "confirmed") if rate else (_usd(0, 0, 0), "not_eligible")
    if rule == "per_unit_hpwh":
        gal, uef = p.get("tank_gal"), p.get("uef")
        units = p.get("units", 1)
        if gal is None or uef is None:
            return _confirm(2500.0 * units)
        band = "30-55" if gal <= 55 else "56-75" if gal <= 75 else "76+"
        rate = 0
        for tier_uef, tier_rate in dict((b, t) for b, t in entry["bands"])[band]:
            if uef >= tier_uef:
                rate = tier_rate
        return (_usd(rate * units, rate * units, rate * units), "confirmed") if rate and gal >= 30 else (_usd(0, 0, 0), "not_eligible")
    if rule == "per_kwh":
        rate = entry["rates"].get(measure.measure_id, 0.0)
        kwh = measure.savings.electricity_kwh if measure.savings else None
        if kwh is None:
            return _usd(0, 0, 0), "needs_confirmation"
        return _usd(rate * kwh.low, rate * kwh.expected, rate * kwh.high), "confirmed"
    raise ValueError(f"unknown incentive rule {rule!r} in {entry['id']}")


def _applies(entry: dict, measure_id: str, sector: str, utility: Optional[str], state: str) -> bool:
    if measure_id not in entry["measure_ids"]:
        return False
    if entry["sector"] not in ("any", sector):
        return False
    region = entry["region"]
    return region == "US" or region == utility or region == state


def incentives_for(measure: MeasureResult, summary: PropertySummary, quantity: Optional[float] = None,
                   cost: Optional[Ranged] = None, extra: Optional[dict] = None) -> list[Incentive]:
    """Every registry entry that can apply to this measure at this property, in registry order.
    `extra` carries facts the measure result does not hold (sri_3yr, roof_slope, existing_r_value,
    owner_is_business, ...). INC-40: each amount is capped at the installed cost."""
    utility = utility_of(summary)
    state = (summary.state or "").upper()
    out: list[Incentive] = []
    for entry in registry():
        if not _applies(entry, measure.measure_id, summary.segment, utility, state):
            continue
        amount, eligibility = _amount(entry, measure, quantity, cost, extra or {})
        if eligibility == "confirmed" and entry.get("user_confirm") and not (extra or {}).get("confirmed"):
            amount, eligibility = _confirm(amount.high)      # permit, pre-approval or product type unseen
        if cost is not None and entry["kind"] in ("upfront_rebate", "rebate_after_install"):
            amount = _usd(min(amount.low, cost.low), min(amount.expected, cost.expected),
                          min(amount.high, cost.high))
        out.append(Incentive(name=entry["name"], kind=entry["kind"], amount_usd=amount,
                             status=entry["status"], eligibility=eligibility,
                             conditions=list(entry["conditions"]), citation=entry["citation"]))
    return out


def counts_toward_net_upfront(incentive: Incentive) -> bool:
    """Only a verified upfront rebate that the project is eligible for reduces the cash paid
    at installation (contract: `Incentive.kind`). Everything else is shown, never summed."""
    return (incentive.kind == "upfront_rebate" and incentive.status == "verified"
            and incentive.eligibility != "not_eligible")


def net_upfront(cost: Ranged, incentives: list[Incentive]) -> Ranged:
    """Installed cost less the incentives that count. The low net uses the high rebate and the
    high net the low rebate; no result goes below zero."""
    counted = [i.amount_usd for i in incentives if counts_toward_net_upfront(i)]
    low = max(0.0, cost.low - sum(a.high for a in counted))
    expected = max(0.0, cost.expected - sum(a.expected for a in counted))
    high = max(0.0, cost.high - sum(a.low for a in counted))
    return _usd(min(low, expected), expected, max(high, expected))

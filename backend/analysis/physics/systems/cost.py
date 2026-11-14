"""Energy cost and emissions: physics 04 TAR-01, TAR-04, TAR-05, EMI-01 to EMI-03."""
from __future__ import annotations

from .constants import (EGRID_LB_PER_MWH, GAS_CO2E_KG_PER_MMBTU, KG_PER_LB, KWH_PER_MMBTU,
                        KWH_PER_THERM, MJ_PER_KWH)


# ---------- TAR-05 conversions ----------

def therms_to_kwh(x: float) -> float:
    return x * KWH_PER_THERM


def kwh_to_therms(x: float) -> float:
    return x / KWH_PER_THERM


def kwh_to_mj(x: float) -> float:
    return x * MJ_PER_KWH


def mmbtu_to_kwh(x: float) -> float:
    return x * KWH_PER_MMBTU


def usd_per_therm_to_usd_per_kwh(p: float) -> float:
    """TAR-04: gas_usd_per_kwh = usd_per_therm / 29.3071."""
    return p / KWH_PER_THERM


# ---------- TAR-01, TAR-04 flat bill ----------

def annual_bill_flat(monthly_kwh, usd_per_kwh: float, fixed_usd_per_month: float = 0.0) -> float:
    """TAR-01 / TAR-04: sum over the months of (F + p Q_m)."""
    return float(sum(fixed_usd_per_month + usd_per_kwh * q for q in monthly_kwh))


def bill_savings(baseline_kwh: float, measure_kwh: float, usd_per_kwh: float) -> float:
    """TAR-01: savings = p (Q_base - Q_measure); fixed charges cancel."""
    return usd_per_kwh * (baseline_kwh - measure_kwh)


# ---------- EMI ----------

def egrid_subregion(state: str | None = None, zip_code: str | None = None) -> str:
    """EMI-01 subregion. Los Angeles ZIP prefixes 900 to 918 are CAMX; the Houston prefixes 770 and
    772 to 775 are mostly ERCT (a few are SRMV or split: resolve by the utility on the bill,
    CenterPoint = ERCT). Without a ZIP, California maps to CAMX and Texas to ERCT; else the U.S.
    average. Only these subregions are in the table."""
    if zip_code:
        p = int(str(zip_code)[:3])
        if 900 <= p <= 918:
            return "CAMX"
        if p == 770 or 772 <= p <= 775:
            return "ERCT"
    if state:
        s = state.strip().upper()
        if s in ("CA", "CALIFORNIA"):
            return "CAMX"
        if s in ("TX", "TEXAS"):
            return "ERCT"
    return "US"


def grid_emission_factor(subregion: str, basis: str = "average") -> float:
    """EMI-01: eGRID2023 rev 2 CO2e rate, kg/kWh (lb/MWh x 0.45359237 / 1000)."""
    avg, nb = EGRID_LB_PER_MWH[subregion]
    return (avg if basis == "average" else nb) * KG_PER_LB / 1000.0


def gas_emission_factor() -> float:
    """EMI-02: kg CO2e per kWh of gas (HHV) = 53.1145 / 293.07107 = 0.18123."""
    return GAS_CO2E_KG_PER_MMBTU / KWH_PER_MMBTU


def annual_co2_kg(electricity_kwh: float, gas_kwh: float, subregion: str, basis: str = "average") -> float:
    """EMI-01 + EMI-02: Q_elec EF + Q_gas EF_gas. For EMI-03 apply it before and after a measure."""
    return electricity_kwh * grid_emission_factor(subregion, basis) + gas_kwh * gas_emission_factor()

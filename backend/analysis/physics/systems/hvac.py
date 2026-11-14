"""HVAC tools, physics 02 HVAC-01 to HVAC-08. Plain floats or NumPy arrays in, W or kWh out."""
from __future__ import annotations

import numpy as np

from .constants import (COOL_EIR_COEFFS, COP_PER_BTU_PER_WH, HEAT_EIR_COEFFS, HEAT_RATING_C,
                        HSPF2_PER_HSPF_DUCTED, HSPF_TO_COP47, IEER_WEIGHTS, SEER2_PER_SEER_DUCTED,
                        SEER_TEST_C)


# ---------- HVAC-01 rating conversions ----------

def rating_to_cop(value: float, metric: str, ducted: bool = True) -> float:
    """HVAC-01. A rating in its own metric to the W/W (or AFUE fraction) it stands for.

    SEER2, EER2 and HSPF2 are first mapped back to SEER, EER and HSPF (ducted split factors;
    ductless factor 1), then multiplied by 0.293071. AFUE and COP pass through."""
    m = metric.upper()
    if m in ("AFUE", "COP"):
        return float(value)
    if m in ("SEER2", "EER2"):
        value = value / (SEER2_PER_SEER_DUCTED if ducted else 1.0)
    elif m == "HSPF2":
        value = value / (HSPF2_PER_HSPF_DUCTED if ducted else 1.0)
    elif m not in ("SEER", "EER", "HSPF", "IEER"):
        raise ValueError(f"unknown rating metric {metric!r}")
    return float(value) * COP_PER_BTU_PER_WH


def to_base_metric(value: float, metric: str, ducted: bool = True) -> tuple[float, str]:
    """SEER2 -> SEER, EER2 -> EER, HSPF2 -> HSPF (HVAC-01); other metrics unchanged."""
    m = metric.upper()
    if m == "SEER2":
        return value / (SEER2_PER_SEER_DUCTED if ducted else 1.0), "SEER"
    if m == "EER2":
        return value / (SEER2_PER_SEER_DUCTED if ducted else 1.0), "EER"
    if m == "HSPF2":
        return value / (HSPF2_PER_HSPF_DUCTED if ducted else 1.0), "HSPF"
    return value, m


# ---------- HVAC-02 temperature dependence (single-stage cooling) ----------

def _g_cool(theta):
    a, b, c = COOL_EIR_COEFFS
    return a + b * theta + c * theta * theta


def cooling_eir_modifier(t_out_c):
    """HVAC-02: f_T(theta) = g(theta) / g(35)."""
    return _g_cool(np.asarray(t_out_c, dtype=float)) / _g_cool(35.0)


def eer_a_from_seer(seer: float, cd: float = 0.10) -> float:
    """HVAC-02: EER at 35 C from SEER, EER_A = SEER f_T(27.78) / (1 - 0.5 C_D)."""
    return seer * float(cooling_eir_modifier(SEER_TEST_C)) / (1.0 - 0.5 * cd)


# ---------- HVAC-03 hourly single-stage cooling ----------

def cooling_power_single_stage(load_w, t_out_c, cop_a: float, capacity_w: float, cd: float = 0.10):
    """HVAC-03: P_el = Q f_T(theta_e) / (COP_A PLF), PLF = 1 - C_D (1 - PLR), PLR = Q / Q_cap capped at 1."""
    q = np.asarray(load_w, dtype=float)
    plr = np.clip(q / capacity_w, 0.0, 1.0) if capacity_w > 0 else np.ones_like(q)
    plf = 1.0 - cd * (1.0 - plr)
    p = q * cooling_eir_modifier(t_out_c) / (cop_a * plf)
    return np.where(q > 0, p, 0.0) if p.ndim else (float(p) if q > 0 else 0.0)


# ---------- HVAC-04 and HVAC-07 seasonal ----------

def seasonal_cooling_energy(cooling_load_kwh, seer_or_ieer: float):
    """HVAC-04 (SEER) and HVAC-07 (IEER): E = Q / (rating x 0.293071)."""
    return cooling_load_kwh / (seer_or_ieer * COP_PER_BTU_PER_WH)


def ieer_from_points(a: float, b: float, c: float, d: float) -> float:
    """HVAC-07: IEER = 0.020 A + 0.617 B + 0.238 C + 0.125 D."""
    wa, wb, wc, wd = IEER_WEIGHTS
    return wa * a + wb * b + wc * c + wd * d


# ---------- HVAC-05 heat pump heating ----------

def _g_heat(theta):
    a, b, c = HEAT_EIR_COEFFS
    return a + b * theta + c * theta * theta


def heating_eir_modifier(t_out_c):
    """HVAC-05: f_T,h(theta) = g_h(theta) / g_h(8.33)."""
    return _g_heat(np.asarray(t_out_c, dtype=float)) / _g_heat(HEAT_RATING_C)


def cop47_from_hspf(hspf: float) -> float | None:
    """HVAC-05, S14 Table 11: interpolate 7.7 -> 3.05, 8.2 -> 3.35, 8.5 -> 3.50. None outside (no
    extrapolation)."""
    pts = HSPF_TO_COP47
    if hspf < pts[0][0] - 1e-9 or hspf > pts[-1][0] + 1e-9:
        return None
    return float(np.interp(hspf, [p[0] for p in pts], [p[1] for p in pts]))


def heat_pump_heating_power(load_w, t_out_c, cop_47: float | None = None, hspf: float | None = None):
    """HVAC-05. Hourly with the certified COP_47 when known (else from HSPF by Table 11 inside
    7.7 to 8.5); otherwise the seasonal fallback Q / (HSPF x 0.293071)."""
    q = np.asarray(load_w, dtype=float)
    if cop_47 is None and hspf is not None:
        cop_47 = cop47_from_hspf(hspf)
    if cop_47 is not None:
        p = q * heating_eir_modifier(t_out_c) / cop_47
    elif hspf is not None:
        p = q / (hspf * COP_PER_BTU_PER_WH)
    else:
        raise ValueError("heat_pump_heating_power needs cop_47 or hspf")
    return p if p.ndim else float(p)


# ---------- HVAC-06 furnace and resistance ----------

def fuel_heating_energy(heating_load_kwh, afue: float):
    """HVAC-06: E = Q / AFUE (gas, HHV); AFUE = 1.0 for electric resistance."""
    return heating_load_kwh / afue


# ---------- HVAC-08 distribution ----------

def apply_distribution_efficiency(zone_load_w, dse: float):
    """HVAC-08: Q_equipment = Q_zone / DSE."""
    return zone_load_w / dse

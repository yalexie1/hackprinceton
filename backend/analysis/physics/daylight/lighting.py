"""Lighting credit and desk score: physics 03 LCT-01 to LCT-03."""
from __future__ import annotations

import numpy as np

from backend.schema import Ranged

from . import constants as C

CONTROL_TYPES = ("continuous", "continuous_off", "stepped", "auto_on_off", "none")


def lighting_power_fraction(e_in_lux, e_set_lux: float, control_type: str, f_l_min: float = 0.2,
                            f_p_min: float = 0.3, n_steps: int = 3):
    """LCT-01: fraction of full lighting power under daylight control (EnergyPlus S2)."""
    e = np.asarray(e_in_lux, dtype=float)
    f_l = np.maximum(0.0, (e_set_lux - e) / e_set_lux)
    if control_type == "none":
        return np.ones_like(f_l)
    if control_type in ("continuous", "continuous_off"):
        line = (f_l + (1.0 - f_l) * f_p_min - f_l_min) / (1.0 - f_l_min)
        low = f_p_min if control_type == "continuous" else 0.0
        return np.where(f_l < f_l_min, low, line)
    if control_type in ("stepped", "auto_on_off"):
        n = 1 if control_type == "auto_on_off" else n_steps
        return np.where(f_l <= 0.0, 0.0, np.where(f_l >= 1.0, 1.0, (np.floor(n * f_l) + 1.0) / n))
    raise ValueError(f"control_type must be one of {CONTROL_TYPES}")


def lighting_energy_saved(e_in_lux, occupied_mask, e_set_lux: float, control_type: str,
                          lpd_w_m2: float, area_m2: float, k_m=(0.0, 0.5, 1.0),
                          f_l_min: float = 0.2, f_p_min: float = 0.3, n_steps: int = 3) -> dict:
    """LCT-02: E_saved = P_ctrl / 1000 * sum over occupied hours of (1 - f_P), kWh/yr.

    With control_type "none" the saving is k_m times the automatic on/off figure, k_m low /
    expected / high = 0 / 0.5 / 1.0 (placeholder [U]; the result carries a warning).
    """
    occ = np.asarray(occupied_mask, dtype=bool)
    p_ctrl = lpd_w_m2 * area_m2
    warnings = []
    if control_type == "none":
        f_p = lighting_power_fraction(e_in_lux, e_set_lux, "auto_on_off")
        red = np.where(occ, p_ctrl * (1.0 - f_p), 0.0)
        pot = float(red.sum()) / 1000.0
        lo, ex, hi = (k * pot for k in k_m)
        warnings.append("depends on occupants switching lights off")
        hourly = red * k_m[1]
    else:
        f_p = lighting_power_fraction(e_in_lux, e_set_lux, control_type, f_l_min, f_p_min, n_steps)
        hourly = np.where(occ, p_ctrl * (1.0 - f_p), 0.0)
        lo = ex = hi = float(hourly.sum()) / 1000.0
    return dict(lighting_kwh_saved=Ranged(low=lo, expected=ex, high=hi, unit="kWh/yr"),
                hourly_w_reduction=hourly, warnings=warnings)


def desk_score(da_300: float, glare_risk: float, comfort_ppd: float, weights=None,
               g_max: float = C.G_MAX, ppd_max: float = C.PPD_MAX) -> dict:
    """LCT-03 (design choice): score = w_d s_d + w_g s_g + w_c s_c."""
    w = weights or C.SCORE_WEIGHTS
    s_d = float(da_300)
    s_g = 1.0 - min(1.0, glare_risk / g_max)
    s_c = 1.0 - min(1.0, max(0.0, comfort_ppd - 5.0) / (ppd_max - 5.0))
    score = w["daylight"] * s_d + w["glare"] * s_g + w["comfort"] * s_c
    return dict(score=score, s_d=s_d, s_g=s_g, s_c=s_c)

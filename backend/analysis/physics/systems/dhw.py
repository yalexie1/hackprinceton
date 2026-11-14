"""Water heating, physics 02 DHW-01 to DHW-03 (homes; offices are not modelled, DHW-02)."""
from __future__ import annotations

import numpy as np

from .constants import (DHW_GAL_PER_DAY, DHW_T_MIX_C, DHW_T_SET_C, M3_PER_GALLON, WATER_CP,
                        WATER_RHO)


def mains_temperature(day_of_year, t_avg_c: float, dt_monthly_max_k: float):
    """DHW-01, SI form. Sine argument in degrees, as in the source."""
    ratio = 0.4 + 0.018 * (t_avg_c - 6.6667)
    lag = 35.0 - 1.8 * (t_avg_c - 6.6667)
    day = np.asarray(day_of_year, dtype=float)
    out = t_avg_c + 3.3333 + ratio * (dt_monthly_max_k / 2.0) * np.sin(
        np.radians(0.986 * (day - 15.0 - lag) - 90.0))
    return out if out.ndim else float(out)


def mains_temperature_f(day_of_year, t_avg_f: float, dt_monthly_max_f: float):
    """DHW-01 in the source's own units (deg F); the reference the SI form is tested against."""
    ratio = 0.4 + 0.01 * (t_avg_f - 44.0)
    lag = 35.0 - 1.0 * (t_avg_f - 44.0)
    day = np.asarray(day_of_year, dtype=float)
    out = (t_avg_f + 6.0) + ratio * (dt_monthly_max_f / 2.0) * np.sin(
        np.radians(0.986 * (day - 15.0 - lag) - 90.0))
    return out if out.ndim else float(out)


def daily_hot_water_gallons(bedrooms: float, t_mains_c, t_set_c: float = DHW_T_SET_C,
                            t_mix_c: float = DHW_T_MIX_C):
    """DHW-02: V_hot = V_cw + V_dw + (V_shower + V_bath + V_sink) (t_mix - t_mains)/(t_set - t_mains),
    US gallons per day."""
    v = {k: a + b * bedrooms for k, (a, b) in DHW_GAL_PER_DAY.items()}
    tm = np.asarray(t_mains_c, dtype=float)
    hot_fraction = np.clip((t_mix_c - tm) / (t_set_c - tm), 0.0, 1.0)
    out = v["clothes_washer"] + v["dishwasher"] + (v["shower"] + v["bath"] + v["sink"]) * hot_fraction
    return out if np.ndim(out) else float(out)


def daily_hot_water_volume(bedrooms: float, t_mains_c, t_set_c: float = DHW_T_SET_C,
                           t_mix_c: float = DHW_T_MIX_C):
    """DHW-02 in m3 per day."""
    return daily_hot_water_gallons(bedrooms, t_mains_c, t_set_c, t_mix_c) * M3_PER_GALLON


def dhw_energy(volume_m3, t_mains_c, uef: float, t_set_c: float = DHW_T_SET_C) -> dict:
    """DHW-03: delivered Q = rho c V (t_set - t_mains) / 3.6e6 kWh; input E = Q / UEF."""
    q = WATER_RHO * WATER_CP * np.asarray(volume_m3, dtype=float) * (t_set_c - np.asarray(t_mains_c, dtype=float)) / 3.6e6
    q = np.maximum(q, 0.0)
    if not q.ndim:
        q = float(q)
    return {"delivered_kwh": q, "input_kwh": q / uef}

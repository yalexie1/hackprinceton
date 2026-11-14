"""Infiltration and ventilation: physics 02 INF-01 to INF-07."""
from __future__ import annotations

import math

from . import constants as C
from .rc import RCParams, _solve, distribute_gains


# ---------- INF-01 ----------

def ventilation_coefficient(flow_m3_s: float) -> float:
    """INF-01: `H_ve = rho_a c_a q_ve` in W/K."""
    return C.RHO_C_AIR * flow_m3_s


def ach_to_flow(ach: float, volume_m3: float) -> float:
    """INF-01: `q_ve = n V / 3600` in m3/s."""
    return ach * volume_m3 / 3600.0


# ---------- INF-02 ----------

def leakage_area_from_ach50(ach50: float, volume_m3: float, exponent: float = C.LEAKAGE_EXPONENT) -> float:
    """INF-02: blower-door ACH50 to the effective leakage area at 4 Pa, in m2."""
    q50 = ach50 * volume_m3 / 3600.0
    q4 = q50 * (4.0 / 50.0) ** exponent
    return q4 * math.sqrt(C.AIR_DENSITY / (2.0 * 4.0))


# ---------- INF-03 ----------

def stack_wind_coefficients(stories: int = 1, shelter_class: int = C.SHELTER_CLASS_DEFAULT) -> tuple[float, float]:
    """INF-03 tables: (C_s, C_w) for 1 to 3 stories (capped at 3) and shelter class 1 to 5."""
    n = min(max(int(stories), 1), 3)
    return C.STACK_COEFF[n], C.WIND_COEFF[int(shelter_class)][n - 1]


def infiltration_flow_sg(leakage_area_m2: float, t_in_c: float, t_out_c: float, wind_m_s: float,
                         stories: int = 1, shelter_class: int = C.SHELTER_CLASS_DEFAULT) -> float:
    """INF-03: Sherman-Grimsrud hourly infiltration, m3/s."""
    c_s, c_w = stack_wind_coefficients(stories, shelter_class)
    a_cm2 = leakage_area_m2 * 1e4
    return (a_cm2 / 1000.0) * math.sqrt(c_s * abs(t_in_c - t_out_c) + c_w * wind_m_s ** 2)


# ---------- INF-04 ----------

def combine_air_flows(infiltration_m3_s: float, supply_m3_s: float = 0.0, exhaust_m3_s: float = 0.0) -> float:
    """INF-04: balanced flow adds, unbalanced flow adds in quadrature with infiltration."""
    q_bal = min(supply_m3_s, exhaust_m3_s)
    q_unbal = abs(supply_m3_s - exhaust_m3_s)
    return q_bal + math.sqrt(q_unbal ** 2 + infiltration_m3_s ** 2)


# ---------- INF-05 ----------

def office_occupants_default(floor_area_m2: float) -> float:
    """INF-05: design occupant count with no tenant data, `A_f / 18.59`."""
    return floor_area_m2 / C.OFFICE_M2_PER_PERSON


def office_infiltration_off(envelope_area_m2: float,
                            leakage_75pa_l_s_m2: float = C.OFFICE_LEAKAGE_75PA_PRE2004) -> float:
    """INF-05: infiltration with the HVAC off, m3/s (75 Pa leakage scaled to 4 Pa, exponent 0.65)."""
    return leakage_75pa_l_s_m2 * (4.0 / 75.0) ** C.LEAKAGE_EXPONENT * envelope_area_m2 / 1000.0


def office_outdoor_air(occupants: float, envelope_area_m2: float, hvac_on: bool,
                       leakage_75pa_l_s_m2: float = C.OFFICE_LEAKAGE_75PA_PRE2004) -> float:
    """INF-05: office outdoor air flow of an hour, m3/s (ventilation plus infiltration)."""
    q_inf_off = office_infiltration_off(envelope_area_m2, leakage_75pa_l_s_m2)
    if hvac_on:
        return occupants * C.OUTDOOR_AIR_PER_PERSON_M3_S + C.OFFICE_INFILTRATION_HVAC_ON_FRACTION * q_inf_off
    return q_inf_off


# ---------- INF-06 ----------

def solve_hour_with_economizer(theta_m_prev_c: float, t_out_c: float, internal_w: float,
                               solar_w: float, setpoint_heat_c: float, setpoint_cool_c: float,
                               max_heat_w: float, max_cool_w: float, params: RCParams,
                               q_min_m3_s: float, q_max_m3_s: float, limit_c: float,
                               tol_k: float = 1e-6, max_iter: int = 200) -> dict:
    """INF-06: fixed dry-bulb economizer on top of ZON-04.

    Returns `{phi_hc_w, flow_m3_s, theta_air_c, theta_m_end_c, theta_m_c, theta_s_c, theta_op_c,
    economizer}`. The bisection on the flow holds the cooling setpoint with no mechanical cooling.
    """
    g = distribute_gains(internal_w, solar_w, params.a_m_m2, params.a_tot_m2, params.h_tr_w_w_k)
    ia, st, m = g["phi_ia_w"], g["phi_st_w"], g["phi_m_w"]

    def solve(q, set_h, set_c):
        return _solve(theta_m_prev_c, t_out_c, t_out_c, ia, st, m, ventilation_coefficient(q),
                      params, set_h, set_c, max_heat_w, max_cool_w)

    def pack(r, q, econ):
        phi, m_end, m_avg, s, a = r
        return {"phi_hc_w": phi, "flow_m3_s": q, "theta_air_c": a, "theta_m_end_c": m_end,
                "theta_m_c": m_avg, "theta_s_c": s, "theta_op_c": 0.3 * a + 0.7 * s,
                "economizer": econ}

    r_min = solve(q_min_m3_s, setpoint_heat_c, setpoint_cool_c)
    if r_min[0] >= 0 or t_out_c > limit_c or t_out_c >= setpoint_cool_c or q_max_m3_s <= q_min_m3_s:
        return pack(r_min, q_min_m3_s, False)
    r_max = solve(q_max_m3_s, setpoint_heat_c, setpoint_cool_c)
    if r_max[0] < 0:
        return pack(r_max, q_max_m3_s, True)
    # free-floating air temperature falls as q rises (outdoor air below the setpoint)
    lo, hi = q_min_m3_s, q_max_m3_s
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        a = solve(mid, C.HEATING_OFF_C, C.COOLING_OFF_C)[4]
        if a > setpoint_cool_c:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12 or abs(a - setpoint_cool_c) < tol_k:
            break
    q = 0.5 * (lo + hi)
    r = solve(q, C.HEATING_OFF_C, C.COOLING_OFF_C)
    return pack(r, q, True)


# ---------- INF-07 ----------

def outdoor_air_latent_load(flow_m3_s: float, w_out_kg_kg: float, w_in_kg_kg: float = C.W_INDOOR) -> float:
    """INF-07: latent cooling load of outdoor air, W (count it only in hours with a cooling need)."""
    return C.AIR_DENSITY * flow_m3_s * C.H_FG * max(0.0, w_out_kg_kg - w_in_kg_kg)


__all__ = ["ventilation_coefficient", "ach_to_flow", "leakage_area_from_ach50",
           "stack_wind_coefficients", "infiltration_flow_sg", "combine_air_flows",
           "office_occupants_default", "office_infiltration_off", "office_outdoor_air",
           "solve_hour_with_economizer", "outdoor_air_latent_load"]

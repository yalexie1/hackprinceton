"""ISO 13790 simple hourly method (5R1C): physics 02 ZON-01 to ZON-06.

Equations of Annex C as transcribed in ZON-02 to ZON-04 (S1 via S2 and S3). One hour per step.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from . import constants as C


@dataclass(frozen=True)
class RCParams:
    """ZON-01 parameters of one zone. Conductances in W/K, capacity in J/K, areas in m2."""
    floor_area_m2: float
    a_m_m2: float
    a_tot_m2: float
    c_m_j_k: float
    h_tr_is_w_k: float
    h_tr_ms_w_k: float
    h_tr_em_w_k: float
    h_tr_w_w_k: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class NodeTemps:
    """ZON-03 result of one hour."""
    theta_m_end_c: float     # mass temperature at the end of the hour (state)
    theta_m_c: float         # hour average
    theta_s_c: float
    theta_air_c: float
    theta_op_c: float


@dataclass(frozen=True)
class HourResult:
    """ZON-04 result of one hour: need (positive heating, negative cooling) and temperatures."""
    phi_hc_w: float
    theta_m_end_c: float
    theta_m_c: float
    theta_s_c: float
    theta_air_c: float
    theta_op_c: float


# ---------- ZON-01 ----------

def h_tr_em(h_tr_op_w_k: float, h_tr_ms_w_k: float) -> float:
    """ZON-01 eq. (63): coupling of the mass node to outdoors."""
    if h_tr_op_w_k <= 0:
        return 0.0
    if h_tr_op_w_k >= h_tr_ms_w_k:
        raise ValueError(f"H_tr,op {h_tr_op_w_k:.1f} W/K must be below H_tr,ms {h_tr_ms_w_k:.1f} W/K (ZON-01)")
    return 1.0 / (1.0 / h_tr_op_w_k - 1.0 / h_tr_ms_w_k)


def zone_rc_parameters(floor_area_m2: float, h_tr_op_w_k: float, h_tr_w_w_k: float,
                       mass_class: str = "medium") -> RCParams:
    """ZON-01: 5R1C parameters from floor area, envelope coefficients and mass class."""
    c_per_m2, am_per_m2 = C.MASS_CLASSES[mass_class]
    a_m = am_per_m2 * floor_area_m2
    a_tot = C.LAMBDA_AT * floor_area_m2
    h_ms = C.H_MS * a_m
    return RCParams(
        floor_area_m2=floor_area_m2, a_m_m2=a_m, a_tot_m2=a_tot, c_m_j_k=c_per_m2 * floor_area_m2,
        h_tr_is_w_k=C.H_IS * a_tot, h_tr_ms_w_k=h_ms, h_tr_em_w_k=h_tr_em(h_tr_op_w_k, h_ms),
        h_tr_w_w_k=h_tr_w_w_k)


# ---------- ZON-02 ----------

def distribute_gains(internal_w: float, solar_w: float, a_m_m2: float, a_tot_m2: float,
                     h_tr_w_w_k: float) -> dict:
    """ZON-02: split internal and solar gain to the air, surface and mass nodes (W)."""
    radiant = 0.5 * internal_w + solar_w
    fm = a_m_m2 / a_tot_m2
    return {
        "phi_ia_w": 0.5 * internal_w,
        "phi_st_w": (1.0 - fm - h_tr_w_w_k / (C.H_MS * a_tot_m2)) * radiant,
        "phi_m_w": fm * radiant,
    }


# ---------- ZON-03 ----------

def _step(theta_m_prev, t_out, t_sup, phi_ia, phi_st, phi_m, phi_hc, h_ve, p: RCParams):
    """ZON-03 closed form, returning a tuple (theta_m_end, theta_m, theta_s, theta_air)."""
    h_ve = max(h_ve, C.H_VE_FLOOR)
    h_is, h_ms, h_em, h_w = p.h_tr_is_w_k, p.h_tr_ms_w_k, p.h_tr_em_w_k, p.h_tr_w_w_k
    h1 = 1.0 / (1.0 / h_ve + 1.0 / h_is)
    h2 = h1 + h_w
    h3 = 1.0 / (1.0 / h2 + 1.0 / h_ms)
    phi_mtot = (phi_m + h_em * t_out
                + h3 * (phi_st + h_w * t_out + h1 * ((phi_ia + phi_hc) / h_ve + t_sup)) / h2)
    cap = p.c_m_j_k / 3600.0
    theta_m_end = ((theta_m_prev * (cap - 0.5 * (h3 + h_em)) + phi_mtot)
                   / (cap + 0.5 * (h3 + h_em)))
    theta_m = 0.5 * (theta_m_end + theta_m_prev)
    theta_s = ((h_ms * theta_m + phi_st + h_w * t_out + h1 * (t_sup + (phi_ia + phi_hc) / h_ve))
               / (h_ms + h_w + h1))
    theta_air = (h_is * theta_s + h_ve * t_sup + phi_ia + phi_hc) / (h_is + h_ve)
    return theta_m_end, theta_m, theta_s, theta_air


def rc_step(theta_m_prev_c: float, t_out_c: float, t_supply_c: float, phi_ia_w: float,
            phi_st_w: float, phi_m_w: float, phi_hc_w: float, h_ve_w_k: float,
            params: RCParams) -> NodeTemps:
    """ZON-03: node temperatures for one hour at a given heating (+) or cooling (-) power."""
    m_end, m, s, a = _step(theta_m_prev_c, t_out_c, t_supply_c, phi_ia_w, phi_st_w, phi_m_w,
                           phi_hc_w, h_ve_w_k, params)
    return NodeTemps(m_end, m, s, a, 0.3 * a + 0.7 * s)


# ---------- ZON-04 ----------

def _solve(theta_m_prev, t_out, t_sup, phi_ia, phi_st, phi_m, h_ve, p, set_h, set_c,
           max_heat, max_cool):
    """ZON-04 steps 1 to 4; returns (phi_hc, theta_m_end, theta_m, theta_s, theta_air)."""
    r0 = _step(theta_m_prev, t_out, t_sup, phi_ia, phi_st, phi_m, 0.0, h_ve, p)
    a0 = r0[3]
    if set_h <= a0 <= set_c:
        return (0.0,) + r0
    target = set_h if a0 < set_h else set_c
    phi10 = 10.0 * p.floor_area_m2 if p.floor_area_m2 > 0 else 10.0
    a10 = _step(theta_m_prev, t_out, t_sup, phi_ia, phi_st, phi_m, phi10, h_ve, p)[3]
    phi_un = phi10 * (target - a0) / (a10 - a0)
    phi = min(max(phi_un, -max_cool), max_heat)
    return (phi,) + _step(theta_m_prev, t_out, t_sup, phi_ia, phi_st, phi_m, phi, h_ve, p)


def solve_hour(theta_m_prev_c: float, t_out_c: float, internal_w: float, solar_w: float,
               setpoint_heat_c: float, setpoint_cool_c: float, max_heat_w: float,
               max_cool_w: float, h_ve_w_k: float, params: RCParams,
               t_supply_c: float | None = None) -> HourResult:
    """ZON-04: heating or cooling need of one hour, setpoints on air temperature, capacity limits.

    `max_heat_w` and `max_cool_w` are positive (use `math.inf` when unknown). Heating off is
    `setpoint_heat_c = -50`; no cooling system is `setpoint_cool_c = 80`.
    """
    g = distribute_gains(internal_w, solar_w, params.a_m_m2, params.a_tot_m2, params.h_tr_w_w_k)
    t_sup = t_out_c if t_supply_c is None else t_supply_c
    phi, m_end, m, s, a = _solve(theta_m_prev_c, t_out_c, t_sup, g["phi_ia_w"], g["phi_st_w"],
                                 g["phi_m_w"], h_ve_w_k, params, setpoint_heat_c, setpoint_cool_c,
                                 max_heat_w, max_cool_w)
    return HourResult(phi, m_end, m, s, a, 0.3 * a + 0.7 * s)


# ---------- ZON-05 ----------

def steady_state_h_eff(h_ve_w_k: float, params: RCParams) -> float:
    """ZON-05: conductance seen from the air node at steady state (W/K)."""
    p = params
    if p.h_tr_em_w_k > 0:
        mass_branch = 1.0 / (1.0 / p.h_tr_ms_w_k + 1.0 / p.h_tr_em_w_k)
    else:
        mass_branch = 0.0
    inner = p.h_tr_w_w_k + mass_branch
    if inner <= 0:
        return h_ve_w_k
    return h_ve_w_k + 1.0 / (1.0 / p.h_tr_is_w_k + 1.0 / inner)


# ---------- ZON-06 ----------

def monthly_heating_need(h_tot_w_k: float, setpoint_heat_c: float, t_out_mean_c: float,
                         hours: float, internal_mean_w: float, solar_mean_w: float,
                         c_m_j_k: float) -> dict:
    """ZON-06: ISO 13790 monthly quasi-steady heating need (kWh), the cross-check of the hourly model."""
    q_ht = h_tot_w_k * (setpoint_heat_c - t_out_mean_c) * hours / 1000.0
    q_gn = (internal_mean_w + solar_mean_w) * hours / 1000.0
    tau = (c_m_j_k / 3600.0) / h_tot_w_k
    a = C.A_0 + tau / C.TAU_0_H
    out = {"q_ht_kwh": q_ht, "q_gn_kwh": q_gn, "tau_h": tau, "a": a, "gamma": math.nan,
           "eta": math.nan, "q_h_nd_kwh": 0.0}
    if q_ht <= 0:
        return out
    gamma = q_gn / q_ht
    if gamma <= 0:
        eta = 1.0
    elif abs(gamma - 1.0) < 1e-12:
        eta = a / (a + 1.0)
    else:
        eta = (1.0 - gamma ** a) / (1.0 - gamma ** (a + 1.0))
    out.update(gamma=gamma, eta=eta, q_h_nd_kwh=max(0.0, q_ht - eta * q_gn))
    return out


__all__ = ["RCParams", "NodeTemps", "HourResult", "h_tr_em", "zone_rc_parameters",
           "distribute_gains", "rc_step", "solve_hour", "steady_state_h_eff",
           "monthly_heating_need"]

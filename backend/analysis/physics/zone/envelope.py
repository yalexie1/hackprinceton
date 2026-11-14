"""Envelope conduction and opaque solar gain: physics 02 ENV-01 to ENV-06.

Pure functions on plain floats (and NumPy arrays where an hourly series makes sense).
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping

from . import constants as C


# ---------- ENV-01 ----------

def assembly_u_value(layers: Iterable[Mapping[str, float]], heat_flow: str = "horizontal",
                     include_films: bool = True) -> float:
    """ENV-01: U of plane homogeneous layers in series, ISO 6946 surface resistances.

    Each layer is `{"thickness_m", "conductivity_w_mk"}` or `{"r_m2k_w"}`.
    `heat_flow`: "horizontal" (walls, windows), "up" (roofs), "down" (floors).
    `include_films=False` when the films are given as layers (e.g. the ASHRAE films of a US table).
    """
    r = C.R_SI[heat_flow] + C.R_SE if include_films else 0.0
    for layer in layers:
        if "r_m2k_w" in layer:
            r += float(layer["r_m2k_w"])
        else:
            r += float(layer["thickness_m"]) / float(layer["conductivity_w_mk"])
    return 1.0 / r


# ---------- ENV-02 ----------

def parallel_path_u_value(r_cavity_m2k_w: float, r_frame_m2k_w: float, framing_fraction: float) -> float:
    """ENV-02: parallel-path U of a wood-framed assembly (the expected value; lower bound on U)."""
    f = framing_fraction
    return (1.0 - f) / r_cavity_m2k_w + f / r_frame_m2k_w


def iso_combined_u_value(r_cavity_m2k_w: float, r_frame_m2k_w: float, framing_fraction: float,
                         r_homogeneous_m2k_w: float, r_insulation_m2k_w: float,
                         r_wood_m2k_w: float) -> float:
    """ENV-02: ISO 6946 combined method, the high value of U.

    `r_homogeneous_m2k_w` is the sum of the unbridged layers and both films; the bridged layer
    has insulation `r_insulation_m2k_w` and wood `r_wood_m2k_w`.
    """
    f = framing_fraction
    r_upper = 1.0 / parallel_path_u_value(r_cavity_m2k_w, r_frame_m2k_w, f)
    r_lower = r_homogeneous_m2k_w + 1.0 / ((1.0 - f) / r_insulation_m2k_w + f / r_wood_m2k_w)
    return 2.0 / (r_upper + r_lower)


# ---------- ENV-03 ----------

def boundary_u_effective(u_w_m2k: float, boundary: str) -> float:
    """ENV-03: U times the adjustment by `Surface.boundary` (ground is handled by ENV-04)."""
    if boundary == "exterior":
        return u_w_m2k
    if boundary == "adjacent_conditioned":
        return 0.0
    if boundary == "adjacent_unconditioned":
        return 1.0 / (1.0 / u_w_m2k + C.R_ADJ_UNCONDITIONED) if u_w_m2k > 0 else 0.0
    raise ValueError(f"boundary {boundary!r} is not summed by ENV-03")


def transmission_coefficients(surfaces, ground_h_w_k: float = 0.0, u_scale: float = 1.0) -> dict:
    """ENV-03: `H_tr,w` (windows and doors) and `H_tr,op` (opaque plus ground) in W/K.

    `surfaces` are `Surface` objects (expected `u_value`); surfaces with `boundary == "ground"` are
    skipped here and enter through `ground_h_w_k` (ENV-04). Thermal bridges are zero (US framed-wall
    tables already contain the framing; ENV-03).
    """
    h_w = 0.0
    h_op = float(ground_h_w_k)
    for s in surfaces:
        if s.boundary == "ground":
            continue
        ua = s.area_m2 * boundary_u_effective(s.u_value.expected * u_scale, s.boundary)
        if s.kind in ("window", "door"):
            h_w += ua
        else:
            h_op += ua
    return {"h_tr_w_w_k": h_w, "h_tr_op_w_k": h_op}


# ---------- ENV-04 ----------

def slab_on_grade_coefficient(area_m2: float, exposed_perimeter_m: float, wall_thickness_m: float,
                              r_floor_m2k_w: float = 0.0,
                              ground_conductivity_w_mk: float = C.GROUND_CONDUCTIVITY) -> dict:
    """ENV-04: ISO 13370 slab on ground (via RdSAP S7). Returns `{u_w_m2k, h_g_w_k}`."""
    lam = ground_conductivity_w_mk
    if area_m2 <= 0:
        return {"u_w_m2k": 0.0, "h_g_w_k": 0.0}
    if exposed_perimeter_m <= 0:
        # no exposed edge: B' is infinite and U tends to zero
        return {"u_w_m2k": 0.0, "h_g_w_k": 0.0}
    b = 2.0 * area_m2 / exposed_perimeter_m
    d_t = wall_thickness_m + lam * (C.SLAB_R_SI + r_floor_m2k_w + C.SLAB_R_SE)
    if d_t < b:
        u = 2.0 * lam / (math.pi * b + d_t) * math.log(math.pi * b / d_t + 1.0)
    else:
        u = lam / (0.457 * b + d_t)
    return {"u_w_m2k": u, "h_g_w_k": area_m2 * u}


def slab_f_factor_coefficient(exposed_perimeter_m: float, f_factor_w_mk: float = C.SLAB_F_FACTOR) -> float:
    """ENV-04 second method (the low case): `H_g = P * F`."""
    return exposed_perimeter_m * f_factor_w_mk


# ---------- ENV-05 ----------

def sky_form_factor(tilt_deg: float) -> float:
    """Form factor to the sky of an unshaded plane, (1 + cos tilt) / 2.

    Gives the two values ENV-05 states (1 for a horizontal roof, 0.5 for a vertical wall).
    """
    return 0.5 * (1.0 + math.cos(math.radians(tilt_deg)))


def radiative_coefficient(emittance: float = C.EMITTANCE_DEFAULT) -> float:
    """ENV-05: external radiative coefficient h_r, taken as 5 eps (about 4 eps sigma T^3 at 10 degC)."""
    return C.H_R_PER_EMITTANCE * emittance


def sol_air_temperature(t_out_c, irradiance_w_m2, absorptance: float, r_se: float = C.R_SE,
                        emittance: float = C.EMITTANCE_DEFAULT, sky_form_factor: float = 1.0,
                        dt_sky_k: float = C.DT_SKY_K):
    """ENV-05: `theta_sa = theta_e + R_se (alpha I - F_r h_r dtheta_er)`."""
    h_r = radiative_coefficient(emittance)
    return t_out_c + r_se * (absorptance * irradiance_w_m2 - sky_form_factor * h_r * dt_sky_k)


def opaque_solar_gain(u_w_m2k: float, area_m2: float, irradiance_w_m2, absorptance: float,
                      sky_form_factor: float, r_se: float = C.R_SE,
                      emittance: float = C.EMITTANCE_DEFAULT, dt_sky_k: float = C.DT_SKY_K,
                      shading_factor: float = 1.0):
    """ENV-05 (ISO route): `F_sh,ob A_sol I_sol - F_r Phi_r`, W. May be negative at night."""
    a_sol = absorptance * r_se * u_w_m2k * area_m2
    phi_r = r_se * u_w_m2k * area_m2 * radiative_coefficient(emittance) * dt_sky_k
    return shading_factor * a_sol * irradiance_w_m2 - sky_form_factor * phi_r


# ---------- ENV-06 ----------

def surface_coefficients(kind: str, convention: str = "iso") -> dict:
    """ENV-06: combined inside and outside surface coefficients, W/(m2 K)."""
    if convention == "ashrae":
        if kind not in ("wall", "window"):
            raise ValueError("ASHRAE films are tabulated for walls and windows only (ENV-06)")
        return {"h_i_w_m2k": 1.0 / C.R_SI_ASHRAE_WALL, "h_e_w_m2k": 1.0 / C.R_SE_ASHRAE}
    flow = {"wall": "horizontal", "window": "horizontal", "roof": "up", "floor": "down"}[kind]
    return {"h_i_w_m2k": 1.0 / C.R_SI[flow], "h_e_w_m2k": 1.0 / C.R_SE}


__all__ = [
    "assembly_u_value", "parallel_path_u_value", "iso_combined_u_value", "boundary_u_effective",
    "transmission_coefficients", "slab_on_grade_coefficient", "slab_f_factor_coefficient",
    "sky_form_factor", "radiative_coefficient", "sol_air_temperature", "opaque_solar_gain",
    "surface_coefficients",
]

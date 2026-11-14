"""Window solar gain: physics 02 WIN-01 and WIN-02."""
from __future__ import annotations

from typing import Optional

from . import constants as C
from .envelope import radiative_coefficient


def window_solar_gain(area_m2: float, shgc: float, irradiance_w_m2, u_w_m2k: float,
                      shading_factor: float = 1.0, obstacle_factor: float = 1.0, f_w: float = C.F_W,
                      sky_form_factor: float = 0.5, emittance: float = C.EMITTANCE_DEFAULT,
                      r_se: float = C.R_SE, dt_sky_k: float = C.DT_SKY_K):
    """WIN-01: `F_sh,ob F_sh,gl F_w SHGC A_w I_sol - F_r R_se U_w A_w h_r dtheta_er`, W.

    SHGC is the NFRC whole-window value, so no frame fraction is applied (WIN-01 note 1).
    """
    solar = obstacle_factor * shading_factor * f_w * shgc * area_m2 * irradiance_w_m2
    sky = sky_form_factor * r_se * u_w_m2k * area_m2 * radiative_coefficient(emittance) * dt_sky_k
    return solar - sky


def shading_factor(interior_type: Optional[str] = None, exterior_type: Optional[str] = None,
                   shgc: float = 0.0, fraction_covered: Optional[float] = None,
                   exterior_fraction_covered: float = 1.0) -> float:
    """WIN-02: `F_sh,gl = F_int F_ext`.

    `interior_type` is a key of `constants.INTERIOR_SHADING` (e.g. "light_blinds_closed");
    `exterior_type` is "solar_screen" or "solar_film". `fraction_covered` defaults to 1.0 for
    blinds and 0.5 for shades and curtains.
    """
    f_int = 1.0
    if interior_type is not None:
        c1, c2 = C.INTERIOR_SHADING[interior_type]
        if fraction_covered is None:
            family = next(k for k in C.INTERIOR_COVER_DEFAULT if k in interior_type)
            fraction_covered = C.INTERIOR_COVER_DEFAULT[family]
        f_int = fraction_covered * (c1 - c2 * shgc) + (1.0 - fraction_covered)
    f_ext = 1.0
    if exterior_type is not None:
        f = exterior_fraction_covered
        f_ext = f * C.EXTERIOR_SHADING[exterior_type] + (1.0 - f)
    return f_int * f_ext


__all__ = ["window_solar_gain", "shading_factor"]

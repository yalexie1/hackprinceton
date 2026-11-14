"""PV production chain, physics 01 section 3 (PV-01 to PV-06) with SHD-03 applied.

Pure NumPy. No network, no file access, no sibling imports: sun position and
plane-of-array irradiance arrive as arrays computed elsewhere (SOL, IRR).

Every function accepts scalars or array-likes and broadcasts.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Optional, Sequence

import numpy as np

from . import constants as C


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


# ---------------------------------------------------------------- PV-01

def incidence_angle_modifier(incidence_deg, n: float = C.GLASS_REFRACTIVE_INDEX,
                             k_per_m: float = C.GLASS_EXTINCTION_PER_M,
                             thickness_m: float = C.GLASS_THICKNESS_M) -> np.ndarray:
    """PV-01. Physical (Fresnel plus absorption) incidence angle modifier, beam only.

    IAM = tau(theta) / tau(0); 0 for theta >= 90 degrees (and for NaN input).
    """
    theta_deg = _arr(incidence_deg)
    kl = k_per_m * thickness_m
    tau0 = np.exp(-kl) * (1.0 - ((n - 1.0) / (n + 1.0)) ** 2)

    valid = np.isfinite(theta_deg) & (np.abs(theta_deg) < 90.0)
    # Evaluate on a safe angle, then mask; tiny angles use the normal-incidence limit.
    th = np.radians(np.where(valid, np.abs(theta_deg), 45.0))
    small = th < 1e-6
    th_safe = np.where(small, 1e-3, th)
    th_r = np.arcsin(np.sin(th_safe) / n)
    fresnel = 1.0 - 0.5 * (np.sin(th_r - th_safe) ** 2 / np.sin(th_r + th_safe) ** 2
                           + np.tan(th_r - th_safe) ** 2 / np.tan(th_r + th_safe) ** 2)
    tau = np.exp(-kl / np.cos(th_r)) * fresnel
    iam = np.where(small, 1.0, tau / tau0)
    return np.where(valid, iam, 0.0)


def transmitted_irradiance(poa_beam, poa_sky_diffuse, poa_ground, incidence_deg,
                           **iam_kwargs) -> np.ndarray:
    """PV-01. Etr = Eb * IAM(theta) + Ed + Eg (W/m2). The modifier acts on the beam only."""
    return (_arr(poa_beam) * incidence_angle_modifier(incidence_deg, **iam_kwargs)
            + _arr(poa_sky_diffuse) + _arr(poa_ground))


# ---------------------------------------------------------------- PV-02

def cell_temperature_sapm(poa_global_w_m2, air_temp_c, wind_speed_m_s,
                          a: float, b: float, delta_t: float) -> np.ndarray:
    """PV-02. Sandia cell temperature (degC) from incident POA before reflection losses."""
    e = _arr(poa_global_w_m2)
    tm = e * np.exp(a + b * _arr(wind_speed_m_s)) + _arr(air_temp_c)
    return tm + e / 1000.0 * delta_t


def sapm_row(name: str) -> tuple[float, float, float]:
    """(a, b, dT) of a PV-02 table row, by name from ``SAPM_TEMPERATURE_ROWS``."""
    return C.SAPM_TEMPERATURE_ROWS[name]


# ---------------------------------------------------------------- PV-03

def pv_dc_power(transmitted_irradiance_w_m2, cell_temp_c, pdc0_w,
                gamma_per_c: float = C.GAMMA_PDC_EXPECTED) -> np.ndarray:
    """PV-03. PVWatts DC power (W), negative results set to 0."""
    p = (_arr(transmitted_irradiance_w_m2) / 1000.0 * pdc0_w
         * (1.0 + gamma_per_c * (_arr(cell_temp_c) - 25.0)))
    return np.maximum(p, 0.0)


# ---------------------------------------------------------------- PV-04

def system_loss_fraction(losses_percent: Optional[Mapping[str, float]] = None) -> float:
    """PV-04. Combined loss as a fraction: 1 - prod(1 - Li/100). Losses multiply.

    ``None`` means the project defaults (``DEFAULT_LOSSES_PERCENT``, 14.0757 %).
    """
    losses = C.DEFAULT_LOSSES_PERCENT if losses_percent is None else losses_percent
    keep = 1.0
    for value in losses.values():
        v = float(value)
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"loss percent out of range: {v}")
        keep *= 1.0 - v / 100.0
    return 1.0 - keep


def losses_with_shading(shading_percent: float,
                        base: Optional[Mapping[str, float]] = None) -> dict[str, float]:
    """PV-04 table with the shading row replaced (0 for ray-cast panels, 3 otherwise)."""
    out = dict(C.DEFAULT_LOSSES_PERCENT if base is None else base)
    out["shading"] = float(shading_percent)
    return out


# ---------------------------------------------------------------- PV-05

def inverter_ac_power(pdc_net_w, pac0_w: float, eta_nom: float = C.INVERTER_ETA_NOM,
                      eta_ref: float = C.INVERTER_ETA_REF) -> np.ndarray:
    """PV-05. PVWatts inverter: part-load efficiency curve, clipped at the AC nameplate."""
    pdc = _arr(pdc_net_w)
    pdc0_inv = pac0_w / eta_nom
    positive = pdc > 0.0
    zeta = np.where(positive, pdc, 1.0) / pdc0_inv
    eta = eta_nom / eta_ref * (-0.0162 * zeta - 0.0059 / zeta + 0.9858)
    eta = np.maximum(eta, 0.0)
    pac = np.minimum(eta * pdc, pac0_w)
    return np.where(positive, np.maximum(pac, 0.0), 0.0)


def ac_nameplate(pdc0_w: float, dc_ac_ratio: float = C.DC_AC_RATIO) -> float:
    """PV-05. Pac0 = Pdc0 / r (W)."""
    if dc_ac_ratio <= 0:
        raise ValueError("dc_ac_ratio must be positive")
    return pdc0_w / dc_ac_ratio


# ---------------------------------------------------------------- SHD-03 applied

def shaded_poa(poa_beam, poa_sky_diffuse, poa_ground, incidence_deg,
               beam_shading_fraction, diffuse_shading_factor,
               poa_sky_circumsolar=None, **iam_kwargs) -> dict[str, np.ndarray]:
    """SHD-03. Shaded POA for PV-02 and transmitted shaded POA for PV-03.

    ``beam_shading_fraction`` is f_b (SHD-01, 1 = beam fully blocked);
    ``diffuse_shading_factor`` is S_d (SHD-02, 1 = sky fully seen). The
    circumsolar part of the Perez sky diffuse is shaded with the beam (the
    design choice stated in SHD-03). When ``poa_sky_circumsolar`` is None the
    whole sky diffuse takes S_d, which is the SAM15 eq. 7.4 rule the entry
    prints as the alternative.
    """
    eb = _arr(poa_beam)
    ed = _arr(poa_sky_diffuse)
    eg = _arr(poa_ground)
    fb = _arr(beam_shading_fraction)
    sd = _arr(diffuse_shading_factor)
    circ = np.zeros_like(ed) if poa_sky_circumsolar is None else _arr(poa_sky_circumsolar)
    rest = ed - circ  # isotropic plus horizon band
    eb_sh = (1.0 - fb) * eb
    circ_sh = (1.0 - fb) * circ
    rest_sh = sd * rest
    poa = eb + ed + eg
    poa_sh = eb_sh + circ_sh + rest_sh + eg
    etr_sh = eb_sh * incidence_angle_modifier(incidence_deg, **iam_kwargs) + circ_sh + rest_sh + eg
    with np.errstate(divide="ignore", invalid="ignore"):
        factor = np.where(poa > 0.0, 1.0 - poa_sh / np.where(poa > 0.0, poa, 1.0), 0.0)
    return {"poa_global_shaded": poa_sh, "transmitted_shaded": etr_sh, "shading_factor": factor}


# ---------------------------------------------------------------- hourly chain

@dataclass(frozen=True)
class PVHourly:
    """Hourly result of the PV-01 to PV-05 chain for 1 kW DC of nameplate.

    ``ac_kwh_per_kw[h]`` is the AC energy of hour h in kWh per kW DC (PV-06
    with 1 h steps). All arrays have the length of the inputs.
    """
    poa_global_w_m2: np.ndarray
    transmitted_w_m2: np.ndarray
    cell_temp_c: np.ndarray
    dc_w_per_kw: np.ndarray
    dc_net_w_per_kw: np.ndarray
    ac_kwh_per_kw: np.ndarray
    loss_fraction: float
    params: dict = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    formula_ids: tuple[str, ...] = ("PV-01", "PV-02", "PV-03", "PV-04", "PV-05", "PV-06")

    @property
    def annual_kwh_per_kw(self) -> float:
        return float(np.sum(self.ac_kwh_per_kw))


def pv_hourly_from_poa(poa_global_w_m2, transmitted_w_m2, air_temp_c, wind_speed_m_s, *,
                       temperature_row: str = C.TEMPERATURE_ROW_EXPECTED,
                       gamma_per_c: float = C.GAMMA_PDC_EXPECTED,
                       losses_percent: Optional[Mapping[str, float]] = None,
                       dc_ac_ratio: float = C.DC_AC_RATIO,
                       eta_nom: float = C.INVERTER_ETA_NOM,
                       warnings: Sequence[str] = ()) -> PVHourly:
    """PV-02 to PV-05 for 1 kW DC, from POA (for temperature) and transmitted POA (for power).

    The chain is linear in the nameplate (the inverter is sized as Pdc0 / r),
    so the per-kW result times the array rating in kW is the array's output.
    """
    a, b, dt = sapm_row(temperature_row)
    poa = np.maximum(_arr(poa_global_w_m2), 0.0)
    etr = np.maximum(_arr(transmitted_w_m2), 0.0)
    tc = cell_temperature_sapm(poa, air_temp_c, wind_speed_m_s, a, b, dt)
    pdc0 = 1000.0
    pdc = pv_dc_power(etr, tc, pdc0, gamma_per_c)
    loss = system_loss_fraction(losses_percent)
    pdc_net = pdc * (1.0 - loss)
    pac = inverter_ac_power(pdc_net, ac_nameplate(pdc0, dc_ac_ratio), eta_nom)
    params = {
        "temperature_row": temperature_row, "gamma_per_c": gamma_per_c,
        "losses_percent": dict(C.DEFAULT_LOSSES_PERCENT if losses_percent is None else losses_percent),
        "loss_fraction": loss, "dc_ac_ratio": dc_ac_ratio, "eta_nom": eta_nom,
    }
    return PVHourly(poa, etr, tc, pdc, pdc_net, pac / 1000.0, loss, params, tuple(warnings))


def pv_hourly_yield(poa_beam, poa_sky_diffuse, poa_ground, incidence_deg,
                    air_temp_c, wind_speed_m_s, *,
                    shading_factor=None,
                    beam_shading_fraction=None, diffuse_shading_factor=None,
                    poa_sky_circumsolar=None,
                    temperature_row: str = C.TEMPERATURE_ROW_EXPECTED,
                    gamma_per_c: float = C.GAMMA_PDC_EXPECTED,
                    losses_percent: Optional[Mapping[str, float]] = None,
                    dc_ac_ratio: float = C.DC_AC_RATIO,
                    eta_nom: float = C.INVERTER_ETA_NOM,
                    iam_kwargs: Optional[Mapping[str, float]] = None) -> PVHourly:
    """Hourly kWh per kW DC from plane-of-array components (A4 entry point).

    Inputs are hourly arrays from IRR-05 (beam), IRR-08 (sky diffuse), IRR-09
    (ground) and IRR-04 (incidence angle), the air temperature and the 10 m
    wind speed. Shading, when known per hour, is given one of two ways:

    * ``beam_shading_fraction`` and ``diffuse_shading_factor`` (SHD-01, SHD-02):
      applied exactly as SHD-03; pass ``poa_sky_circumsolar`` (IRR-08) so the
      circumsolar part is shaded with the beam.
    * ``shading_factor`` (the SHD-03 hourly factor, 1 - Epoa,sh / Epoa): the
      POA for PV-02 is exact; the transmitted POA for PV-03 is scaled by the
      same factor, which ignores that the shaded share may have a different
      incidence modifier than the whole. A warning says so.

    With geometric shading and no explicit ``losses_percent``, the PV-04
    shading row is 0 (the far-horizon caveat goes to warnings); without it the
    3 % PVWatts default stays. ``iam_kwargs`` overrides the PV-01 glass
    constants (``n``, ``k_per_m``, ``thickness_m``).
    """
    iam_kw = dict(iam_kwargs or {})
    warnings: list[str] = []
    eb, ed, eg = _arr(poa_beam), _arr(poa_sky_diffuse), _arr(poa_ground)
    poa = eb + ed + eg
    etr = transmitted_irradiance(eb, ed, eg, incidence_deg, **iam_kw)

    pair = beam_shading_fraction is not None or diffuse_shading_factor is not None
    if pair and shading_factor is not None:
        raise ValueError("give either shading_factor or the (beam, diffuse) pair, not both")
    geometric = pair or shading_factor is not None
    if pair:
        fb = 0.0 if beam_shading_fraction is None else beam_shading_fraction
        sd = 1.0 if diffuse_shading_factor is None else diffuse_shading_factor
        sh = shaded_poa(eb, ed, eg, incidence_deg, fb, sd, poa_sky_circumsolar, **iam_kw)
        poa, etr = sh["poa_global_shaded"], sh["transmitted_shaded"]
        if poa_sky_circumsolar is None:
            warnings.append("SHD-03: no circumsolar component given; all sky diffuse "
                            "shaded with the diffuse factor (SAM15 rule)")
    elif shading_factor is not None:
        s = _arr(shading_factor)
        if np.any((s < 0.0) | (s > 1.0)):
            raise ValueError("shading_factor must lie in [0, 1]")
        poa = (1.0 - s) * poa
        etr = (1.0 - s) * etr
        warnings.append("SHD-03: a single hourly shading factor was applied to the "
                        "transmitted irradiance as well; exact only when beam and "
                        "diffuse are shaded alike")

    if losses_percent is None:
        if geometric:
            losses_percent = losses_with_shading(0.0)
            warnings.append("PV-04: shading loss set to 0 for a ray-cast panel; distant "
                            "horizon obstructions are not counted")
        else:
            losses_percent = dict(C.DEFAULT_LOSSES_PERCENT)

    out = pv_hourly_from_poa(poa, etr, air_temp_c, wind_speed_m_s,
                             temperature_row=temperature_row, gamma_per_c=gamma_per_c,
                             losses_percent=losses_percent, dc_ac_ratio=dc_ac_ratio,
                             eta_nom=eta_nom, warnings=warnings)
    if geometric:
        return replace(out, formula_ids=out.formula_ids + ("SHD-03",))
    return out


# ---------------------------------------------------------------- PV-06

def annual_energy(hourly_kwh_per_kw, pdc0_kw: float = 1.0, month=None) -> dict:
    """PV-06. Sum hourly AC energy over the year.

    ``hourly_kwh_per_kw`` is the chain's output; ``pdc0_kw`` the array rating.
    ``month`` (1 to 12 per hour), when given, yields ``monthly_kwh``.
    """
    per_kw = _arr(hourly_kwh_per_kw)
    hourly = per_kw * pdc0_kw
    out = {
        "annual_kwh": float(hourly.sum()),
        "yield_kwh_per_kw": float(per_kw.sum()),
        "hourly_kwh": hourly,
    }
    if month is not None:
        m = np.asarray(month, dtype=int)
        if m.shape != per_kw.shape:
            raise ValueError("month must have one entry per hour")
        out["monthly_kwh"] = [float(hourly[m == k].sum()) for k in range(1, 13)]
    return out

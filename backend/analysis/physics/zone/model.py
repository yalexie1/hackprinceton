"""The hourly zone model on a `BuildingModel` (A2): physics 02 ZON-04 driven by ENV, INF and WIN.

`zone_loads(model, t_out_c, surface_irradiance_w_m2, internal_gains_w, ...)` runs every zone of the
model for every hour passed in and returns hourly heating and cooling need per zone plus annual,
monthly and peak values. Pure: no file is read or written and nothing outside the arguments is used.
Weather and plane irradiance come from A1 (`physics/climate`), internal gains from the caller;
both are passed in as arrays, one value per hour.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Sequence, Union

import numpy as np

from backend.schema import BuildingModel, Surface, Systems, Zone

from . import constants as C
from .airflow import (combine_air_flows, infiltration_flow_sg, leakage_area_from_ach50,
                      office_infiltration_off, outdoor_air_latent_load, solve_hour_with_economizer,
                      ventilation_coefficient)
from .envelope import (opaque_solar_gain, sky_form_factor, slab_f_factor_coefficient,
                       slab_on_grade_coefficient, transmission_coefficients)
from .rc import RCParams, _solve, distribute_gains, zone_rc_parameters
from .windows import window_solar_gain

ArrayLike = Union[float, Sequence[float], np.ndarray]
IrradianceSource = Union[Mapping[str, ArrayLike], Callable[[float, Optional[float]], ArrayLike]]


@dataclass
class ZoneOptions:
    """Choices of the zone model that are not in `BuildingModel`. Defaults are the expected values
    of physics 02; the low and high runs of a range pass other values (UNC-01)."""
    interior_shading: float = C.INTERIOR_SHADING_BASELINE    # WIN-02 baseline F_int
    f_w: float = C.F_W                                        # WIN-01
    obstacle_factor: Mapping[str, float] = field(default_factory=dict)   # surface id -> F_sh,ob (SHD)
    dt_sky_k: float = C.DT_SKY_K                              # ENV-05
    r_se: float = C.R_SE                                      # ENV-05 (0.06 is the high case)
    ground_method: str = "iso13370"                           # ENV-04: "iso13370", "f_factor", "u_value"
    ground_conductivity_w_mk: float = C.GROUND_CONDUCTIVITY   # ENV-04
    wall_thickness_m: float = C.WALL_THICKNESS_DEFAULT_M      # ENV-04 (WallEdge.thickness_m if known)
    stories: int = 1                                          # INF-03 (PropertySummary.floor_count)
    shelter_class: int = C.SHELTER_CLASS_DEFAULT              # INF-03
    leakage_exponent: float = C.LEAKAGE_EXPONENT              # INF-02
    use_cooling_capacity: bool = True                         # ZON-04: Systems.cooling_capacity_w
    economizer_q_max_m3_s: Optional[float] = None             # INF-06: unit supply flow (no default, tier A)
    warmup_hours: int = C.WARMUP_HOURS                        # ZON-04
    theta_m_start_c: float = C.THETA_M_START_C                # ZON-04


@dataclass
class ZoneLoads:
    """Result for one `Zone`. Need is thermal, before equipment efficiency. Energies in kWh,
    powers in W; cooling values are positive numbers."""
    zone_id: str
    conditioned: bool
    params: RCParams
    h_tr_op_w_k: float
    h_tr_w_w_k: float
    h_g_w_k: float
    hourly: dict                       # ZON-04 outputs, one array per key, one value per hour
    heating_need_kwh: float
    cooling_need_kwh: float
    latent_cooling_kwh: float
    peak_heating_w: float
    peak_cooling_w: float
    monthly_heating_kwh: Optional[list[float]]
    monthly_cooling_kwh: Optional[list[float]]
    infiltration_ach: float            # annual mean natural air change rate (Systems.infiltration_ach)


@dataclass
class BuildingLoads:
    """All zones of a `BuildingModel`. Peaks are of the summed hourly need (coincident)."""
    zones: list[ZoneLoads]
    heating_need_kwh: float
    cooling_need_kwh: float
    latent_cooling_kwh: float
    peak_heating_w: float
    peak_cooling_w: float
    monthly_heating_kwh: Optional[list[float]]
    monthly_cooling_kwh: Optional[list[float]]
    infiltration_ach: Optional[float]
    phi_hc_w: np.ndarray               # summed hourly need, + heating, - cooling
    formula_ids: list[str]
    warnings: list[str]

    def zone(self, zone_id: str) -> ZoneLoads:
        return next(z for z in self.zones if z.zone_id == zone_id)


HOURLY_KEYS = ("theta_air_c", "theta_s_c", "theta_op_c", "theta_m_c", "theta_m_end_c", "phi_hc_w",
               "mode", "q_ve_m3_s", "q_inf_m3_s", "phi_int_w", "phi_sol_w", "latent_w",
               "setpoint_heat_c", "setpoint_cool_c")


# ---------- calendar helpers (hour-ending stamps, physics.md section 3) ----------

def _hour_starts(stamps) -> np.ndarray:
    s = np.asarray(stamps, dtype="datetime64[m]")
    return s - np.timedelta64(60, "m")


def office_hvac_on(stamps, schedule: str = "office") -> np.ndarray:
    """DEF-09: True in the hours the office HVAC runs (weekdays hours 7 to 22, Saturdays 7 to 18;
    hour 1 is 00:00 to 01:00). Stamps are hour-ending. `office_vacant` is never on. Holidays are
    not modelled (no holiday list is sourced)."""
    start = _hour_starts(stamps)
    if schedule == "office_vacant":
        return np.zeros(len(start), dtype=bool)
    hour_no = (start.astype("datetime64[h]") - start.astype("datetime64[D]")).astype(int) + 1
    weekday = (start.astype("datetime64[D]").astype(int) + 3) % 7      # 1970-01-01 was a Thursday
    on = np.zeros(len(start), dtype=bool)
    wk = weekday < 5
    sat = weekday == 5
    on[wk] = np.isin(hour_no[wk], list(C.OFFICE_HVAC_ON_HOURS["weekday"]))
    on[sat] = np.isin(hour_no[sat], list(C.OFFICE_HVAC_ON_HOURS["saturday"]))
    return on


def _month_index(stamps, n: int) -> Optional[np.ndarray]:
    if stamps is not None:
        start = _hour_starts(stamps)
        return start.astype("datetime64[M]").astype(int) % 12
    if n == 8760:
        days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        return np.repeat(np.arange(12), [d * 24 for d in days])
    return None


def _as_array(x: ArrayLike, n: int, name: str) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if a.ndim == 0:
        return np.full(n, float(a))
    if a.shape != (n,):
        raise ValueError(f"{name} has shape {a.shape}, expected ({n},)")
    return a


# ---------- one zone, one year ----------

def simulate_zone(params: RCParams, t_out_c: np.ndarray, phi_int_w: np.ndarray, phi_sol_w: np.ndarray,
                  setpoint_heat_c: np.ndarray, setpoint_cool_c: np.ndarray,
                  flow_m3_s: Union[np.ndarray, Callable[[int, float], float]], *,
                  max_heat_w: float = math.inf, max_cool_w: float = math.inf,
                  economizer: Optional[dict] = None,
                  warmup_hours: int = C.WARMUP_HOURS,
                  theta_m_start_c: float = C.THETA_M_START_C) -> dict:
    """ZON-04 year run of one zone (arrays of equal length, one value per hour).

    `flow_m3_s` is the outdoor air flow per hour, or a function `(hour, theta_air_prev) -> m3/s`
    when the flow depends on the zone temperature (INF-03). The warm-up runs the last
    `warmup_hours` hours first and discards them. `economizer`: `{"q_max_m3_s", "limit_c",
    "active": bool array}` applies INF-06 in the active hours.
    """
    n = len(t_out_c)
    t_out = [float(v) for v in t_out_c]
    ints = [float(v) for v in phi_int_w]
    sols = [float(v) for v in phi_sol_w]
    set_h = [float(v) for v in setpoint_heat_c]
    set_c = [float(v) for v in setpoint_cool_c]
    flow_fn = flow_m3_s if callable(flow_m3_s) else None
    flows = None if flow_fn else [float(v) for v in flow_m3_s]
    econ_on = economizer["active"] if economizer else None

    out = {k: np.empty(n) for k in ("theta_air_c", "theta_s_c", "theta_op_c", "theta_m_c",
                                     "theta_m_end_c", "phi_hc_w", "q_ve_m3_s")}
    am, at, hw = params.a_m_m2, params.a_tot_m2, params.h_tr_w_w_k
    theta_m = theta_m_start_c
    theta_air = theta_m_start_c
    w = min(max(int(warmup_hours), 0), n)
    order = list(range(n - w, n)) + list(range(n))
    for k, i in enumerate(order):
        q = flow_fn(i, theta_air) if flow_fn else flows[i]
        if econ_on is not None and econ_on[i]:
            r = solve_hour_with_economizer(theta_m, t_out[i], ints[i], sols[i], set_h[i], set_c[i],
                                           max_heat_w, max_cool_w, params, q,
                                           economizer["q_max_m3_s"], economizer["limit_c"])
            phi, m_end, m_avg, s, a = (r["phi_hc_w"], r["theta_m_end_c"], r["theta_m_c"],
                                       r["theta_s_c"], r["theta_air_c"])
            q = r["flow_m3_s"]
        else:
            g = distribute_gains(ints[i], sols[i], am, at, hw)
            phi, m_end, m_avg, s, a = _solve(theta_m, t_out[i], t_out[i], g["phi_ia_w"], g["phi_st_w"],
                                             g["phi_m_w"], ventilation_coefficient(q), params,
                                             set_h[i], set_c[i], max_heat_w, max_cool_w)
        theta_m, theta_air = m_end, a
        if k >= w:
            out["theta_air_c"][i] = a
            out["theta_s_c"][i] = s
            out["theta_op_c"][i] = 0.3 * a + 0.7 * s
            out["theta_m_c"][i] = m_avg
            out["theta_m_end_c"][i] = m_end
            out["phi_hc_w"][i] = phi
            out["q_ve_m3_s"][i] = q
    out["mode"] = np.where(out["phi_hc_w"] > 0, "heating", np.where(out["phi_hc_w"] < 0, "cooling", "off"))
    return out


# ---------- building model to zone inputs ----------

def _is_office(systems: Systems) -> bool:
    return systems.occupancy_schedule.startswith("office")


def _ground_h(surfaces: list[Surface], opt: ZoneOptions, warnings: list[str]) -> float:
    """ENV-04 for every `ground` surface of a zone."""
    h = 0.0
    for s in surfaces:
        if s.boundary != "ground":
            continue
        if opt.ground_method == "u_value" or s.exposed_perimeter_m is None:
            if opt.ground_method != "u_value":
                warnings.append(f"{s.id}: no exposed perimeter, ground loss from u_value (ENV-04 not applied)")
            h += s.area_m2 * s.u_value.expected
        elif opt.ground_method == "f_factor":
            h += slab_f_factor_coefficient(s.exposed_perimeter_m)
        else:
            h += slab_on_grade_coefficient(s.area_m2, s.exposed_perimeter_m, opt.wall_thickness_m,
                                           ground_conductivity_w_mk=opt.ground_conductivity_w_mk)["h_g_w_k"]
    return h


def _irradiance_getter(source: IrradianceSource, n: int):
    cache: dict = {}

    def get(s: Surface) -> Optional[np.ndarray]:
        if callable(source):
            key = (round(s.tilt_deg, 6), None if s.azimuth_deg is None else round(s.azimuth_deg % 360, 6))
            if key not in cache:
                cache[key] = _as_array(source(s.tilt_deg, s.azimuth_deg), n, f"irradiance {key}")
            return cache[key]
        if s.id in source:
            return _as_array(source[s.id], n, f"irradiance[{s.id}]")
        return None
    return get


def zone_solar_gain(surfaces: list[Surface], irradiance: Callable[[Surface], Optional[np.ndarray]],
                    n: int, opt: ZoneOptions, warnings: list[str]) -> np.ndarray:
    """WIN-01 for windows plus ENV-05 for opaque exterior surfaces, summed; W per hour.

    Only `exterior` surfaces receive sun. Doors are opaque (ENV-05). A surface whose absorptance
    is missing takes the DEF-02 expected value; a window without SHGC gets no solar part.
    """
    total = np.zeros(n)
    for s in surfaces:
        if s.boundary != "exterior" or s.kind == "floor":
            continue
        i_sol = irradiance(s)
        if i_sol is None:
            warnings.append(f"{s.id}: no irradiance passed in; its solar gain is set to 0 "
                            f"(sky radiation still counted)")
            i_sol = np.zeros(n)
        f_r = sky_form_factor(s.tilt_deg)
        eps = s.emittance if s.emittance is not None else C.EMITTANCE_DEFAULT
        f_ob = opt.obstacle_factor.get(s.id, 1.0)
        u = s.u_value.expected
        if s.kind == "window":
            if s.shgc is None:
                warnings.append(f"{s.id}: window without shgc; solar part set to 0")
            shgc = s.shgc.expected if s.shgc is not None else 0.0
            total += window_solar_gain(s.area_m2, shgc, i_sol, u, shading_factor=opt.interior_shading,
                                       obstacle_factor=f_ob, f_w=opt.f_w, sky_form_factor=f_r,
                                       emittance=eps, r_se=opt.r_se, dt_sky_k=opt.dt_sky_k)
        else:
            if s.solar_absorptance is not None:
                alpha = s.solar_absorptance.expected
            else:
                alpha = C.ABSORPTANCE_ROOF_DEFAULT if s.kind == "roof" else C.ABSORPTANCE_WALL_DEFAULT
            total += opaque_solar_gain(u, s.area_m2, i_sol, alpha, f_r, r_se=opt.r_se, emittance=eps,
                                       dt_sky_k=opt.dt_sky_k, shading_factor=f_ob)
    return total


def _envelope_area(surfaces: list[Surface]) -> float:
    """INF-05: above-grade exterior wall (gross: windows and doors included) plus roof area."""
    return sum(s.area_m2 for s in surfaces
               if s.boundary == "exterior" and s.kind in ("wall", "window", "door", "roof"))


def zone_loads(model: BuildingModel, t_out_c: ArrayLike, surface_irradiance_w_m2: IrradianceSource,
               internal_gains_w: Union[ArrayLike, Mapping[str, ArrayLike]] = 0.0, *,
               wind_m_s: Optional[ArrayLike] = None, stamps=None,
               hvac_on: Optional[ArrayLike] = None,
               setpoint_heat_c: Optional[ArrayLike] = None,
               setpoint_cool_c: Optional[ArrayLike] = None,
               humidity_ratio_out: Optional[ArrayLike] = None,
               latent_gains_w: Optional[Union[ArrayLike, Mapping[str, ArrayLike]]] = None,
               options: Optional[ZoneOptions] = None) -> BuildingLoads:
    """Hourly heating and cooling need of every zone of `model` (expected values of every input).

    Arguments, one value per hour (length n; 8760 for a year):
    - `t_out_c`: outdoor dry-bulb (A1 weather).
    - `surface_irradiance_w_m2`: total irradiance on each surface plane (A1 `plane_irradiance`,
      IRR-10), either a mapping `surface id -> array` or a function `(tilt_deg, azimuth_deg) -> array`.
    - `internal_gains_w`: sensible internal gain (LGT-03), one array for the building (split by
      floor area) or a mapping `zone id -> array`.
    - `wind_m_s`: wind speed for INF-03 (homes). Without it the infiltration is stack-only.
    - `stamps`: hour-ending timestamps; give the office schedule (DEF-09) and the months.
    - `hvac_on`: office HVAC-on hours; overrides the schedule derived from `stamps`.
    - `setpoint_heat_c`, `setpoint_cool_c`: hourly setpoints; override the `Systems` and DEF-08 values.
    - `humidity_ratio_out`: outdoor humidity ratio (kg/kg) for INF-07; without it no latent load
      from outdoor air is computed.
    - `latent_gains_w`: occupant latent gain (LGT-03), added in cooling hours.
    """
    opt = options or ZoneOptions()
    t_out = np.asarray(t_out_c, dtype=float)
    n = len(t_out)
    sysm = model.systems
    office = _is_office(sysm)
    warnings: list[str] = []
    ids = {"ENV-03", "ENV-05", "ZON-01", "ZON-02", "ZON-03", "ZON-04", "INF-01", "WIN-01", "WIN-02"}

    wind = _as_array(wind_m_s, n, "wind_m_s") if wind_m_s is not None else None
    w_out = _as_array(humidity_ratio_out, n, "humidity_ratio_out") if humidity_ratio_out is not None else None
    irr = _irradiance_getter(surface_irradiance_w_m2, n)
    months = _month_index(stamps, n)

    # schedule and setpoints (DEF-08, DEF-09)
    if office:
        if hvac_on is not None:
            on = np.asarray(hvac_on, dtype=bool)
        elif stamps is not None:
            on = office_hvac_on(stamps, sysm.occupancy_schedule)
        else:
            raise ValueError("an office model needs `stamps` or `hvac_on` for its HVAC schedule (DEF-09)")
        sp = C.SETPOINTS["office"]
        h_occ = sysm.heating_setpoint_c.expected if sysm.heating_setpoint_c else sp["heat"]
        c_occ = sysm.cooling_setpoint_c.expected if sysm.cooling_setpoint_c else sp["cool"]
        h_un = sysm.heating_setback_c if sysm.heating_setback_c is not None else sp["heat_setback"]
        c_un = sysm.cooling_setup_c if sysm.cooling_setup_c is not None else sp["cool_setup"]
        set_h = np.where(on, h_occ, h_un)
        set_c = np.where(on, c_occ, c_un)
    else:
        on = np.ones(n, dtype=bool)
        sp = C.SETPOINTS["home"]
        set_h = np.full(n, sysm.heating_setpoint_c.expected if sysm.heating_setpoint_c else sp["heat"])
        set_c = np.full(n, sysm.cooling_setpoint_c.expected if sysm.cooling_setpoint_c else sp["cool"])
    if setpoint_heat_c is not None:
        set_h = _as_array(setpoint_heat_c, n, "setpoint_heat_c")
    if setpoint_cool_c is not None:
        set_c = _as_array(setpoint_cool_c, n, "setpoint_cool_c")
    if sysm.heating_fuel == "none":
        set_h = np.full(n, C.HEATING_OFF_C)
    if sysm.hvac_type == "none":
        set_c = np.full(n, C.COOLING_OFF_C)

    zones = list(model.zones)
    total_area = sum(z.floor_area_m2 for z in zones if z.conditioned) or 1.0

    def per_zone(x, z: Zone, name: str) -> np.ndarray:
        if isinstance(x, Mapping):
            return _as_array(x.get(z.id, 0.0), n, f"{name}[{z.id}]")
        share = z.floor_area_m2 / total_area if z.conditioned else 0.0
        return _as_array(x, n, name) * share

    # office design outdoor air (INF-05): Systems.occupants first, then Systems.outdoor_air_m3_s
    q_oa_building = 0.0
    if office:
        ids.add("INF-05")
        if sysm.occupants is not None:
            q_oa_building = sysm.occupants.expected * C.OUTDOOR_AIR_PER_PERSON_M3_S
        elif sysm.outdoor_air_m3_s is not None:
            q_oa_building = sysm.outdoor_air_m3_s.expected
        else:
            q_oa_building = total_area / C.OFFICE_M2_PER_PERSON * C.OUTDOOR_AIR_PER_PERSON_M3_S
        leak75 = (sysm.envelope_leakage_l_s_m2_75pa.expected if sysm.envelope_leakage_l_s_m2_75pa
                  else C.OFFICE_LEAKAGE_75PA_PRE2004)
    elif sysm.infiltration_ach50 is not None:
        ids.update({"INF-02", "INF-03", "INF-04"})
        if wind is None:
            warnings.append("no wind speed passed in: infiltration is stack-only (INF-03)")
    else:
        warnings.append("no infiltration_ach50: infiltration uses the placeholder Systems.infiltration_ach")

    economizer = None
    if office and sysm.has_economizer:
        if sysm.economizer_limit_c is None or opt.economizer_q_max_m3_s is None:
            warnings.append("economizer present but its high limit or supply flow is unknown; "
                            "INF-06 not applied (section 10, tier A)")
        else:
            ids.add("INF-06")

    cool_cap_total = (sysm.cooling_capacity_w if (opt.use_cooling_capacity and sysm.cooling_capacity_w)
                      else math.inf)
    if not office and any(s.kind == "roof" and s.boundary == "exterior" for s in model.surfaces):
        warnings.append("roof solar gain by ENV-05 over a possibly vented attic is an upper bound "
                        "(section 10, tier A)")

    results: list[ZoneLoads] = []
    for z in zones:
        surfs = [s for s in model.surfaces if s.zone_id == z.id]
        h_g = _ground_h(surfs, opt, warnings)
        if h_g > 0:
            ids.add("ENV-04")
        tr = transmission_coefficients(surfs, h_g)
        params = zone_rc_parameters(z.floor_area_m2, tr["h_tr_op_w_k"], tr["h_tr_w_w_k"], z.mass_class)
        phi_sol = zone_solar_gain(surfs, irr, n, opt, warnings)
        phi_int = per_zone(internal_gains_w, z, "internal_gains_w")
        share = z.floor_area_m2 / total_area if z.conditioned else 0.0

        if z.conditioned:
            zh, zc = set_h, set_c
            max_cool = cool_cap_total * share if math.isfinite(cool_cap_total) else math.inf
        else:
            zh, zc = np.full(n, C.HEATING_OFF_C), np.full(n, C.COOLING_OFF_C)
            max_cool = math.inf

        # outdoor air (INF-01 to INF-05)
        q_inf = np.zeros(n)
        if office:
            q_off = office_infiltration_off(_envelope_area(surfs), leak75)
            q_inf = np.where(on, C.OFFICE_INFILTRATION_HVAC_ON_FRACTION * q_off, q_off)
            q_oa = np.where(on, q_oa_building * share, 0.0)
            flow = q_inf + q_oa
        elif sysm.infiltration_ach50 is not None:
            a_l = leakage_area_from_ach50(sysm.infiltration_ach50.expected, z.volume_m3, opt.leakage_exponent)
            wv = wind if wind is not None else np.zeros(n)

            def flow(i, theta_air_prev, a_l=a_l, wv=wv, q_inf=q_inf):
                q = infiltration_flow_sg(a_l, theta_air_prev, float(t_out[i]), float(wv[i]),
                                         opt.stories, opt.shelter_class)
                q_inf[i] = q
                return combine_air_flows(q)        # homes: no whole-house mechanical ventilation
        else:
            q_inf = np.full(n, sysm.infiltration_ach.expected * z.volume_m3 / 3600.0)
            flow = q_inf

        econ = None
        if "INF-06" in ids and z.conditioned:
            econ = {"q_max_m3_s": opt.economizer_q_max_m3_s * share, "limit_c": sysm.economizer_limit_c,
                    "active": on}

        h = simulate_zone(params, t_out, phi_int, phi_sol, zh, zc, flow, max_cool_w=max_cool,
                          economizer=econ, warmup_hours=opt.warmup_hours,
                          theta_m_start_c=opt.theta_m_start_c)
        h["q_inf_m3_s"] = q_inf
        h["phi_int_w"] = phi_int
        h["phi_sol_w"] = phi_sol
        h["setpoint_heat_c"] = np.asarray(zh, dtype=float)
        h["setpoint_cool_c"] = np.asarray(zc, dtype=float)

        # latent load in cooling hours (INF-07, LGT-03)
        latent = np.zeros(n)
        cooling = h["phi_hc_w"] < 0
        if w_out is not None:
            ids.add("INF-07")
            latent += np.array([outdoor_air_latent_load(q, w) for q, w in zip(h["q_ve_m3_s"], w_out)])
        if latent_gains_w is not None:
            latent += per_zone(latent_gains_w, z, "latent_gains_w")
        h["latent_w"] = np.where(cooling, latent, 0.0)

        phi = h["phi_hc_w"]
        heat = np.clip(phi, 0, None)
        cool = np.clip(-phi, 0, None)
        mh = mc = None
        if months is not None:
            mh = [float(heat[months == m].sum() / 1000.0) for m in range(12)]
            mc = [float(cool[months == m].sum() / 1000.0) for m in range(12)]
        results.append(ZoneLoads(
            zone_id=z.id, conditioned=z.conditioned, params=params,
            h_tr_op_w_k=tr["h_tr_op_w_k"], h_tr_w_w_k=tr["h_tr_w_w_k"], h_g_w_k=h_g, hourly=h,
            heating_need_kwh=float(heat.sum() / 1000.0), cooling_need_kwh=float(cool.sum() / 1000.0),
            latent_cooling_kwh=float(h["latent_w"].sum() / 1000.0),
            peak_heating_w=float(heat.max(initial=0.0)), peak_cooling_w=float(cool.max(initial=0.0)),
            monthly_heating_kwh=mh, monthly_cooling_kwh=mc,
            infiltration_ach=float(q_inf.mean() * 3600.0 / z.volume_m3) if z.volume_m3 > 0 else 0.0))

    total = np.zeros(n)
    for r in results:
        total += r.hourly["phi_hc_w"]
    heat_t, cool_t = np.clip(total, 0, None), np.clip(-total, 0, None)
    vol = sum(z.volume_m3 for z in zones)
    ach = (sum(r.infiltration_ach * z.volume_m3 for r, z in zip(results, zones)) / vol) if vol > 0 else None

    def msum(attr):
        vals = [getattr(r, attr) for r in results]
        return None if any(v is None for v in vals) or not vals else [float(sum(x)) for x in zip(*vals)]

    return BuildingLoads(
        zones=results,
        heating_need_kwh=sum(r.heating_need_kwh for r in results),
        cooling_need_kwh=sum(r.cooling_need_kwh for r in results),
        latent_cooling_kwh=sum(r.latent_cooling_kwh for r in results),
        peak_heating_w=float(heat_t.max(initial=0.0)), peak_cooling_w=float(cool_t.max(initial=0.0)),
        monthly_heating_kwh=msum("monthly_heating_kwh"), monthly_cooling_kwh=msum("monthly_cooling_kwh"),
        infiltration_ach=ach, phi_hc_w=total, formula_ids=sorted(ids),
        warnings=list(dict.fromkeys(warnings)))


def hourly_columns(zone: ZoneLoads) -> dict:
    """The ZON-04 hourly outputs of one zone as plain lists, ready for the caller to cache at
    `BaselineResult.hourly_path` (physics 03 reads `theta_air_c`, `theta_op_c` and `mode`)."""
    return {k: zone.hourly[k].tolist() for k in HOURLY_KEYS}


__all__ = ["ZoneOptions", "ZoneLoads", "BuildingLoads", "HOURLY_KEYS", "office_hvac_on",
           "simulate_zone", "zone_solar_gain", "zone_loads", "hourly_columns"]

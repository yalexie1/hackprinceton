"""Score one desk position: daylight (DAY), glare (GLR), comfort (CMF) and the desk score (LCT-03).

`score_point(room, surfaces, x, y, sun, zone_temps, *, floor, ...)` is the function the desk
layout package (A23) receives through the lane door. It returns a dict whose keys include every
`DeskScore` field this package fills (`daylight`, `glare_risk`, `comfort_ppd`, `score`,
`daylight_factor`, `view_azimuth_deg`, `direct_sun_hours`, `max_dt_pr_k`, `warnings`) plus
diagnostics. For many points in one room, build the room once with `prepare_room(...)` and pass
it as `context=`; the outdoor illuminance of a `sun` object is cached on the context.

Inputs passed in, never imported from sibling packages (workplan 2.6):
- `sun`: hourly arrays, a mapping or an object with attributes. Names accepted: altitude
  (`altitude_deg`, `sun_altitude_deg`, `elevation_deg`, `sun_elevation_deg`), `azimuth_deg` or
  `sun_azimuth_deg` (true, clockwise from north), `dni_w_m2`, `dhi_w_m2`, `ghi_w_m2`, outdoor dry
  bulb (`t_out_c` or `temp_c`), optional extraterrestrial normal irradiance (`i0_w_m2` or
  `e0n_w_m2`), `dew_point_c`, `rh_pct`, `stamps` (hour-ending, local) and `occupied` (bool mask).
- `zone_temps`: zone air temperature per hour (`t_air_c` or `theta_air_c`, or a number), optional
  `mode` per hour ("heating", "cooling", "off"), optional `t_surface_c`; or only setpoints
  (`setpoint_heat_c`, `setpoint_cool_c`), used as the active setpoint (CMF-08 step 1).
"""
from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np

from backend.schema import Floor, Room, Surface

from . import constants as C
from .comfort import (glass_inside_surface_temperature, mean_radiant_temperature, pmv_ppd,
                      plane_factor_to_window, radiant_asymmetry_window, sky_vault_fraction,
                      solar_gain_delta_mrt, window_angle_factor)
from .daylight import (IRCWindow, daylight_autonomy, extraterrestrial_normal,
                       externally_reflected_component, indoor_illuminance_hourly,
                       internally_reflected_component, perez_luminous_efficacy, sky_component)
from .geometry import (RoomGeometry, WindowRect, azimuth_true, point_in_polygon, room_geometry,
                       room_windows, wrap180)
from .glare import cos_sun_view, dgp_simplified, sun_visible_through_window, vertical_window_factors
from .lighting import desk_score

FORMULA_IDS = ("DAY-01", "DAY-02", "DAY-03", "DAY-04", "DAY-05", "DAY-07", "DAY-08", "DAY-09",
               "GLR-01", "GLR-02", "GLR-04", "GLR-05",
               "CMF-01", "CMF-02", "CMF-04", "CMF-05", "CMF-06", "CMF-07", "CMF-08", "LCT-03")
CASES = {"low": 0, "expected": 1, "high": 2}
_FLIPPED = {"site.obstruction_angle_deg"}   # a larger angle is daylight-unfavourable


# ---------------------------------------------------------------- inputs

@dataclass
class SunArrays:
    altitude_deg: np.ndarray
    azimuth_deg: np.ndarray
    dni_w_m2: np.ndarray
    dhi_w_m2: np.ndarray
    ghi_w_m2: np.ndarray
    t_out_c: np.ndarray
    i0_w_m2: np.ndarray
    dew_point_c: np.ndarray
    occupied: np.ndarray
    warnings: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.altitude_deg)


def _get(obj, *names):
    for n in names:
        if isinstance(obj, Mapping):
            if n in obj and obj[n] is not None:
                return obj[n]
        elif getattr(obj, n, None) is not None:
            return getattr(obj, n)
    return None


def _day_of_year(stamps, n: int) -> np.ndarray:
    if stamps is not None and hasattr(stamps, "dayofyear"):
        return np.asarray(stamps.dayofyear, dtype=float)
    if stamps is not None:
        s = np.asarray(stamps, dtype="datetime64[m]")
        return (s.astype("datetime64[D]") - s.astype("datetime64[Y]")).astype(int) + 1.0
    return np.arange(n) // 24 + 1.0


def occupied_mask_from_stamps(stamps) -> np.ndarray:
    """Section 0.3: 08:00 to 18:00 local, Monday to Friday. Stamps are hour-ending (physics.md 3),
    so an hour is occupied when its start lies in [08:00, 18:00)."""
    if hasattr(stamps, "hour") and hasattr(stamps, "dayofweek"):
        start = stamps - np.timedelta64(1, "h")
        hour = np.asarray(start.hour)
        wd = np.asarray(start.dayofweek)
    else:
        s = np.asarray(stamps, dtype="datetime64[m]") - np.timedelta64(60, "m")
        hour = (s.astype("datetime64[h]") - s.astype("datetime64[D]")).astype(int)
        wd = (s.astype("datetime64[D]").astype(int) + 3) % 7      # 1970-01-01 was a Thursday
    return (hour >= C.OCCUPIED_START_HOUR) & (hour < C.OCCUPIED_END_HOUR) & (wd < 5)


def sun_arrays(sun, occupied=None) -> SunArrays:
    """Normalise the hourly sun and weather input (see module docstring)."""
    if isinstance(sun, SunArrays):
        if occupied is not None:
            return dataclasses.replace(sun, occupied=np.asarray(occupied, dtype=bool))
        return sun
    warnings: list[str] = []
    alt = _get(sun, "altitude_deg", "sun_altitude_deg", "elevation_deg", "sun_elevation_deg")
    az = _get(sun, "azimuth_deg", "sun_azimuth_deg")
    dni, dhi, ghi = (_get(sun, k) for k in ("dni_w_m2", "dhi_w_m2", "ghi_w_m2"))
    t_out = _get(sun, "t_out_c", "temp_c", "temperature_c")
    if any(v is None for v in (alt, az, dni, dhi, t_out)):
        raise ValueError("sun needs altitude, azimuth, dni_w_m2, dhi_w_m2 and t_out_c arrays")
    alt, az, dni, dhi, t_out = (np.asarray(v, dtype=float) for v in (alt, az, dni, dhi, t_out))
    n = alt.shape[0]
    ghi = (np.asarray(ghi, dtype=float) if ghi is not None
           else dni * np.maximum(0.0, np.sin(np.radians(alt))) + dhi)
    stamps = _get(sun, "stamps")
    i0 = _get(sun, "i0_w_m2", "e0n_w_m2")
    i0 = np.asarray(i0, dtype=float) if i0 is not None else extraterrestrial_normal(_day_of_year(stamps, n))
    dew = _get(sun, "dew_point_c")
    if dew is None:
        rh = _get(sun, "rh_pct", "rh_percent")
        if rh is None and not isinstance(sun, Mapping) and getattr(sun, "weather", None) is not None:
            rh = getattr(sun.weather, "rh_pct", None)
        if rh is not None:
            # Magnus form (Alduchov and Eskridge 1996 constants). Not a physics 03 entry: it only
            # feeds the precipitable water W of DAY-07, whose coefficient b is small.
            rh = np.clip(np.asarray(rh, dtype=float), 1.0, 100.0)
            g = np.log(rh / 100.0) + 17.625 * t_out / (243.04 + t_out)
            dew = 243.04 * g / (17.625 - g)
            warnings.append("dew point derived from temperature and humidity (Magnus); "
                            "used only for DAY-07 precipitable water")
        else:
            dew = np.full(n, 10.0)
            warnings.append("no dew point or humidity: 10 C assumed for DAY-07 precipitable water")
    dew = np.broadcast_to(np.asarray(dew, dtype=float), (n,))
    occ = occupied if occupied is not None else _get(sun, "occupied")
    if occ is None:
        if stamps is not None:
            occ = occupied_mask_from_stamps(stamps)
        else:
            occ = (np.arange(n) % 24 >= C.OCCUPIED_START_HOUR) & (np.arange(n) % 24 < C.OCCUPIED_END_HOUR)
            warnings.append("no stamps or occupied mask: hours 08:00 to 18:00 of every day taken as "
                            "occupied (weekdays unknown)")
    occ = np.asarray(occ, dtype=bool)
    for name, a in (("azimuth", az), ("dni", dni), ("dhi", dhi), ("ghi", ghi), ("t_out", t_out),
                    ("i0", i0), ("occupied", occ)):
        if a.shape != (n,):
            raise ValueError(f"sun array {name} has shape {a.shape}, expected ({n},)")
    return SunArrays(alt, az, dni, dhi, ghi, t_out, i0, dew, occ, warnings)


def resolve_assumptions(assumptions=None, case: str = "expected") -> dict[str, float]:
    """Values of the section 0.4 keys for one run. `assumptions` may be a list of contract
    `Assumption`s (e.g. `BuildingModel.assumptions`) or a mapping key -> number, (low, expected,
    high) or `Ranged`. Low / high are the daylight-unfavourable / favourable sets."""
    if case not in CASES:
        raise ValueError("case must be 'low', 'expected' or 'high'")
    k = CASES[case]
    vals = {key: v[k] for key, v in C.DAYLIGHT_ASSUMPTIONS.items()}
    vals.update(C.COMFORT_ASSUMPTIONS)
    if not assumptions:
        return vals
    items = assumptions.items() if isinstance(assumptions, Mapping) else \
        [(a.key, a.value) for a in assumptions]
    for key, v in items:
        if key not in vals:
            continue
        v = getattr(v, "value", v)     # an Assumption inside a mapping
        if hasattr(v, "expected"):
            trip = (float(v.low), float(v.expected), float(v.high))
        elif isinstance(v, (tuple, list)) and len(v) == 3:
            trip = tuple(float(t) for t in v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            trip = (float(v),) * 3
        else:
            continue
        if key in _FLIPPED:
            trip = trip[::-1]
        vals[key] = trip[k] if key in C.DAYLIGHT_ASSUMPTIONS else trip[1]
    return vals


# ---------------------------------------------------------------- room context

@dataclass
class RoomContext:
    room: Room
    windows: list[WindowRect]
    window_source: Optional[str]
    north_offset_deg: float
    geometry: RoomGeometry
    params: dict
    irc: dict
    case: str
    warnings: list[str]
    _sun_cache: dict = field(default_factory=dict, repr=False)

    def tau(self, w: WindowRect) -> float:
        if w.tau is not None:
            return w.tau[CASES[self.case]]
        return self.params["glazing.visible_transmittance"]

    def tau_eff(self, w: WindowRect) -> float:
        p = self.params
        return self.tau(w) * p["glazing.maintenance_factor"] * p["glazing.glazed_fraction"]

    def outdoor(self, sun, occupied=None) -> tuple[SunArrays, dict]:
        key = (id(sun), None if occupied is None else id(occupied))
        hit = self._sun_cache.get(key)
        if hit is not None and hit[0] is sun:
            return hit[1], hit[2]
        s = sun_arrays(sun, occupied)
        lum = perez_luminous_efficacy(s.dni_w_m2, s.dhi_w_m2, 90.0 - s.altitude_deg, s.dew_point_c,
                                      s.i0_w_m2)
        self._sun_cache[key] = (sun, s, lum)
        return s, lum


def prepare_room(room: Room, surfaces: Sequence[Surface], *, floor: Floor,
                 north_offset_deg: Optional[float] = None, assumptions=None, case: str = "expected",
                 relative_center_from: str = "first") -> RoomContext:
    """Windows, assumption values and the room-wide IRC (DAY-05) of one room, for one run."""
    if floor is None:
        raise ValueError("floor (the room's Floor with vertices and wall edges) is required to place windows")
    params = resolve_assumptions(assumptions, case)
    windows, source, north, warnings = room_windows(room, floor, surfaces, north_offset_deg=north_offset_deg,
                                                    relative_center_from=relative_center_from)
    geo = room_geometry(room)
    if not windows:
        warnings.append(f"room {room.id}: no window; daylight and glare are zero")
    refl = dict(floor=params["interior.reflectance_floor"], ceiling=params["interior.reflectance_ceiling"],
                walls=params["interior.reflectance_walls"], glass=params["interior.reflectance_glass"])
    ctx = RoomContext(room, windows, source, north, geo, params, {}, case, warnings)
    irc_windows = [IRCWindow(w.area_m2, (w.z1 + w.z2) / 2.0, ctx.tau(w), w.edge_id, w.edge_length_m or 0.0)
                   for w in windows]
    ctx.irc = internally_reflected_component(
        geo.floor_area_m2, geo.perimeter_m, geo.height_m, irc_windows, refl,
        params["glazing.maintenance_factor"], params["glazing.glazed_fraction"],
        params["site.ground_reflectance"], params["site.obstruction_angle_deg"],
        params["site.obstruction_reflectance"])
    return ctx


# ---------------------------------------------------------------- zone input

def _zone_series(zone_temps, n: int, t_out: np.ndarray, warnings: list[str]):
    if zone_temps is None:
        raise ValueError("zone_temps is required (hourly zone air temperature, or setpoints)")
    if isinstance(zone_temps, (int, float)) and not isinstance(zone_temps, bool):
        return np.full(n, float(zone_temps)), None, None
    t_a = _get(zone_temps, "t_air_c", "theta_air_c", "t_a_c")
    mode = _get(zone_temps, "mode")
    t_s = _get(zone_temps, "t_surface_c")
    if t_a is None:
        hs, cs = _get(zone_temps, "setpoint_heat_c"), _get(zone_temps, "setpoint_cool_c")
        if hs is None or cs is None:
            raise ValueError("zone_temps needs t_air_c (or theta_air_c), or both setpoints")
        hs, cs = (np.broadcast_to(np.asarray(v, dtype=float), (n,)) for v in (hs, cs))
        t_a = np.where(t_out < C.CLO_SWITCH_T_OUT_C, hs, cs)
        warnings.append("no zone air temperature: active setpoint used (heating below 15 C outdoors)")
    t_a = np.broadcast_to(np.asarray(t_a, dtype=float), (n,))
    if mode is not None:
        mode = np.broadcast_to(np.asarray(mode), (n,))
    if t_s is not None:
        t_s = np.broadcast_to(np.asarray(t_s, dtype=float), (n,))
    return t_a, mode, t_s


# ---------------------------------------------------------------- the point

def score_point(room: Room, surfaces: Sequence[Surface], x: float, y: float, sun, zone_temps, *,
                floor: Optional[Floor] = None, north_offset_deg: Optional[float] = None,
                assumptions=None, case: str = "expected", occupied=None,
                relative_center_from: str = "first", h_i: float = C.H_I_W_M2K,
                context: Optional[RoomContext] = None, return_hourly: bool = False) -> dict[str, Any]:
    """Daylight, glare and comfort at desk position (x, y) of `room` (model frame, metres).

    Returns `daylight` (DA_300, DAY-09), `glare_risk` (GLR-05), `comfort_ppd` (CMF-08), `score`
    (LCT-03), `daylight_factor` (percent), `view_azimuth_deg` (true, recommended facing),
    `direct_sun_hours` (GLR-04 sun on the desk, occupied hours), `max_dt_pr_k` (CMF-06),
    `dt_pr_exceeds_limit`, `warnings`, and diagnostics (`df_components`, `cda_300`,
    `glare_risk_facing_window`, `frac_outside_comfort`, `window_source`, `formula_ids`).
    With `return_hourly=True` also `hourly` (`e_in_lux`, `pmv`, `ppd`; PMV and PPD are NaN outside
    occupied hours) for the lighting credit (LCT-02).
    """
    ctx = context
    if ctx is None:
        ctx = prepare_room(room, surfaces, floor=floor, north_offset_deg=north_offset_deg,
                           assumptions=assumptions, case=case, relative_center_from=relative_center_from)
    elif ctx.room.id != room.id:
        raise ValueError(f"context is for room {ctx.room.id}, not {room.id}")
    if len(room.polygon) >= 3 and not point_in_polygon(x, y, room.polygon):
        raise ValueError(f"point ({x}, {y}) is outside room {room.id}")
    s, lum = ctx.outdoor(sun, occupied)
    p = ctx.params
    warnings = list(ctx.warnings) + list(s.warnings)
    n = len(s)
    occ = s.occupied
    e_dh, e_gh = lum["e_dh_lux"], lum["e_gh_lux"]
    theta, rho_o, rho_g = (p["site.obstruction_angle_deg"], p["site.obstruction_reflectance"],
                           p["site.ground_reflectance"])

    zp, ze, zb = C.WORKPLANE_HEIGHT_M, C.EYE_HEIGHT_SEATED_M, C.BODY_CENTRE_SEATED_M
    front = []   # (window, desk udz, eye udz, body udz, tau_eff)
    for w in ctx.windows:
        pd_ = w.to_wall(x, y, zp)
        if pd_[1] <= 1e-6:
            continue
        front.append((w, pd_, w.to_wall(x, y, ze), w.to_wall(x, y, zb), ctx.tau_eff(w)))

    # ---- DAY-01, DAY-03, DAY-04, DAY-05, DAY-08, DAY-09
    sc = sum(sky_component(pd_, w.rect, te, theta) for w, pd_, _, _, te in front)
    erc = sum(externally_reflected_component(pd_, w.rect, te, theta, rho_o, rho_g)
              for w, pd_, _, _, te in front)
    irc_sky, irc_gnd = ctx.irc["irc_sky"], ctx.irc["irc_ground"]
    df = sc + erc + irc_sky + irc_gnd
    e_in = indoor_illuminance_hourly(sc + erc + irc_sky, irc_gnd, e_dh, e_gh)
    da = daylight_autonomy(e_in, occ, C.TARGET_LUX)

    # ---- GLR-01, GLR-02, GLR-04, GLR-05
    view_az = None
    glare = glare_face = 0.0
    sun_eye = np.zeros(n, dtype=bool)
    sun_desk = np.zeros(n, dtype=bool)
    sun_body = np.zeros(n, dtype=bool)
    t_sol_dir = np.zeros(n)
    nearest = None
    if front:
        nearest = min(front, key=lambda f: f[0].horizontal_distance(x, y))[0]
        if nearest.to_wall(x, y, 0)[1] > 3.0 * ctx.geometry.height_m:
            warnings.append("point deeper than three ceiling heights from the nearest window: the "
                            "split-flux IRC overstates light here (DAY-05)")
        for w, pd_, pe, pb, te in front:
            sun_eye |= sun_visible_through_window(pe, w.rect, w.azimuth_deg, s.altitude_deg,
                                                  s.azimuth_deg, theta)["visible"]
            sun_desk |= sun_visible_through_window(pd_, w.rect, w.azimuth_deg, s.altitude_deg,
                                                   s.azimuth_deg, theta)["visible"]
            vb = sun_visible_through_window(pb, w.rect, w.azimuth_deg, s.altitude_deg,
                                            s.azimuth_deg, theta)["visible"]
            t_sol_dir = np.where(vb & ~sun_body, w.shgc, t_sol_dir)
            sun_body |= vb
        t = nearest.tangent
        directions = {"plus": t, "minus": (-t[0], -t[1]), "face": nearest.normal}
        risks, azs = {}, {}
        for name, v in directions.items():
            v_sky, v_gnd = irc_sky, irc_gnd
            for w, _, pe, _, te in front:
                f = vertical_window_factors(pe, w.vector_to_wall(*v), w.rect, theta, rho_o, rho_g)
                v_sky += te * f["sc_v"]
                v_gnd += te * f["gc_v"]
            azs[name] = azimuth_true(v[0], v[1], ctx.north_offset_deg)
            e_v = v_sky * e_dh + v_gnd * e_gh
            hour = (sun_eye & (cos_sun_view(s.altitude_deg, s.azimuth_deg, azs[name]) > 0)) | \
                   (dgp_simplified(e_v) > C.DGP_GLARE_LIMIT)
            risks[name] = float(np.mean(hour[occ])) if occ.any() else 0.0
        best = "plus" if risks["plus"] <= risks["minus"] else "minus"
        glare, view_az, glare_face = risks[best], azs[best], risks["face"]
        if glare_face > C.GLARE_FACING_WARN:
            warnings.append(f"facing the window the glare risk is {glare_face:.2f} (GLR-05)")
    direct_sun_hours = float(np.sum(sun_desk & occ))

    # ---- CMF-04 to CMF-08
    t_a, mode, t_s = _zone_series(zone_temps, n, s.t_out_c, warnings)
    if t_s is None:
        t_s = t_a
    idx = np.flatnonzero(occ)
    ta_o, ts_o, tout_o = t_a[idx], t_s[idx], s.t_out_c[idx]
    f_w, t_gi, f_pl, t_gi_pl = [], [], [], []
    f_svv, tsol_w = 0.0, 0.0
    for w, _, _, pb, _ in front:
        tg = glass_inside_surface_temperature(ta_o, tout_o, w.u_value, h_i)
        f_w.append(window_angle_factor(pb, w.rect))
        t_gi.append(tg)
        if nearest is not None and (w.normal[0] * nearest.normal[0] + w.normal[1] * nearest.normal[1]) > 0.999:
            f_pl.append(plane_factor_to_window(pb, w.rect))
            t_gi_pl.append(tg)
        fs = sky_vault_fraction(pb, w.rect)
        f_svv += fs
        tsol_w += fs * w.shgc
    t_r = mean_radiant_temperature(f_w, t_gi, ts_o) if front else ts_o.copy()
    if front:
        sharp = np.abs(wrap180(s.azimuth_deg[idx] - (view_az or 0.0)))
        sg = solar_gain_delta_mrt(s.altitude_deg[idx], sharp, s.dni_w_m2[idx], s.dhi_w_m2[idx],
                                  (tsol_w / f_svv if f_svv > 0 else 0.0, t_sol_dir[idx]), f_svv,
                                  np.where(sun_body[idx], p["comfort.body_exposed_fraction"], 0.0),
                                  p["comfort.shortwave_absorptivity"], p["comfort.floor_reflectance_solar"])
        t_r = t_r + sg["delta_mrt_k"]
    if mode is not None:
        heating = np.asarray(mode)[idx] == "heating"
    else:
        heating = tout_o < C.CLO_SWITCH_T_OUT_C
    clo = np.where(heating, p["comfort.clo_heating"], p["comfort.clo_cooling"])
    if idx.size:
        res = pmv_ppd(ta_o, t_r, p["comfort.air_speed_m_s"], p["comfort.rh_percent"], p["comfort.met"], clo)
        pmv = np.atleast_1d(res["pmv"])
        if np.any(t_r > 40.0):
            warnings.append("solar-adjusted mean radiant temperature above 40 C in "
                            f"{int(np.sum(t_r > 40.0))} occupied hours; PMV clamped to +3 (CMF-01)")
        pmv = np.clip(pmv, -3.0, 3.0)
        ppd = 100.0 - 95.0 * np.exp(-0.03353 * pmv ** 4 - 0.2179 * pmv ** 2)
        comfort_ppd = float(np.mean(ppd))
        frac_out = float(np.mean(np.abs(pmv) > 0.5))
        dt_pr = radiant_asymmetry_window(f_pl, t_gi_pl, ts_o) if f_pl else np.zeros(idx.size)
        max_dt = float(np.max(dt_pr))
    else:
        warnings.append("no occupied hours")
        pmv = ppd = np.zeros(0)
        comfort_ppd, frac_out, max_dt = 5.0, 0.0, 0.0
    exceeds = max_dt >= C.DT_PR_COOL_WALL_LIMIT_K
    if exceeds:
        warnings.append(f"radiant asymmetry {max_dt:.1f} K at or above the 10 K cool-wall limit (CMF-06): "
                        "not recommended")

    sc_ = desk_score(da["da"], glare, comfort_ppd)
    out: dict[str, Any] = dict(
        room_id=room.id, x=float(x), y=float(y),
        daylight=da["da"], glare_risk=glare, comfort_ppd=comfort_ppd, score=sc_["score"],
        daylight_factor=100.0 * df, view_azimuth_deg=view_az, direct_sun_hours=direct_sun_hours,
        max_dt_pr_k=max_dt, warnings=warnings,
        dt_pr_exceeds_limit=exceeds, cda_300=da["cda"], glare_risk_facing_window=glare_face,
        frac_outside_comfort=frac_out, sub_scores=dict(s_d=sc_["s_d"], s_g=sc_["s_g"], s_c=sc_["s_c"]),
        df_components=dict(sc=sc, erc=erc, irc_sky=irc_sky, irc_ground=irc_gnd, df=df),
        window_source=ctx.window_source, case=ctx.case, formula_ids=list(FORMULA_IDS))
    if return_hourly:
        pmv_h = np.full(n, np.nan)
        ppd_h = np.full(n, np.nan)
        pmv_h[idx], ppd_h[idx] = pmv, ppd
        out["hourly"] = dict(e_in_lux=e_in, pmv=pmv_h, ppd=ppd_h)
    return out


DESK_SCORE_KEYS = ("room_id", "x", "y", "daylight", "glare_risk", "comfort_ppd", "score",
                   "daylight_factor", "view_azimuth_deg", "direct_sun_hours", "max_dt_pr_k", "warnings")


def desk_score_fields(result: dict) -> dict:
    """The subset of a `score_point` result that maps one-to-one onto `DeskScore` fields
    (`recommended` is left to the layout package)."""
    return {k: result[k] for k in DESK_SCORE_KEYS}

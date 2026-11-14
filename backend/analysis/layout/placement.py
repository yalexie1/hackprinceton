"""Desk placement (A23; SPEC 6.4; physics 03 LCT-02, LCT-03).

1. Candidate grid: points on a 0.5 m grid of the model frame inside work-area rooms, at least
   0.6 m from the face of every wall and clear of the swing of every door opening.
2. Each candidate is scored by a point-scoring function passed in (A5 builds it in
   `physics/daylight/`; this package never imports it, workplan 2.6):

       score_point(bundle=..., model=..., room=..., x=..., y=..., setpoint_lux=...) -> Mapping

   Required keys: `daylight` (DA_300, 0 to 1), `glare_risk` (0 to 1), `comfort_ppd` (percent).
   Optional keys, copied onto the `DeskScore`: `daylight_factor`, `view_azimuth_deg`,
   `direct_sun_hours`, `max_dt_pr_k`, `warnings`. Optional `lighting_saved_fraction`: the mean
   of `1 - f_P` over occupied hours at `setpoint_lux` (LCT-01), either one number for automatic
   on/off control or a dict keyed by `lighting.control_type`.
3. Score (LCT-03), then pick the top N greedily with a minimum spacing. A position with a
   radiant asymmetry `max_dt_pr_k >= 10 K` (CMF-06) is never recommended.
4. Lighting energy displaced at the recommended desks (LCT-02).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

import numpy as np
import shapely
from shapely.geometry import Polygon

from backend.schema import (BuildingModel, DeskScore, Floor, LayoutResult, MatterportData,
                            PropertyBundle, Ranged, Room, Surface)

ScorePoint = Callable[..., Mapping[str, Any]]

# ---- design constants (SPEC 6.4; physics 03 section 0.3). backend/config.py does not carry them
# yet, so they stay here; physics 03 LCT-03 says the weights, G_MAX and PPD_MAX belong in config.
GRID_M = 0.5                 # SPEC 6.4 item 1
WALL_CLEARANCE_M = 0.6       # SPEC 6.4 item 1, from the wall face (centreline + thickness / 2)
DEFAULT_WALL_THICKNESS_M = 0.12   # design choice when WallEdge.thickness_m is missing
DOOR_WIDTH_DEFAULT_M = 0.9   # design choice when Opening.width_m is missing
MIN_SPACING_M = 2.0          # design choice; the LA office fixture (run.office#/measures LAYOUT)
AREA_PER_DESK_M2 = 8.0       # physics 03 section 0.3, LCT-02 (also N when nobody gives one)
SCORE_WEIGHTS = {"daylight": 0.4, "glare": 0.3, "comfort": 0.3}   # LCT-03, design choice
G_MAX = 0.20                 # LCT-03
PPD_MAX = 25.0               # LCT-03
PPD_FLOOR = 5.0              # CMF-02, the only physics in the score
DT_PR_LIMIT_K = 10.0         # CMF-06: a desk at or above this asymmetry is not recommended
TARGET_LUX = 300.0           # DAY-09 / DAY-10: DeskScore.daylight is DA_300
SETPOINT_LUX = {"office": 500.0, "home": 300.0}   # DAY-10: EN 12464-1 office desk; home design choice
OCCUPIED_HOURS = {"office": 2600.0, "home": 2600.0}   # physics 03 section 0.3: 08:00-18:00 weekdays
DESK_HEIGHT_M = 0.75         # anchor height of a desk top
REPORTED_PER_DESK = 2        # candidates reported = 2 x requested (the fixture shows 8 for 4)

# Room labels that are not places for a desk (SPEC 6.4 "rooms classed as work areas").
# Unlabelled rooms are kept: office scans often carry no classification.
NOT_WORK = re.compile(r"bath|toilet|restroom|wc\b|shower|kitchen|pantry|closet|storage|stor\b|"
                      r"hall|corridor|stair|utility|laundry|garage|mechanical|elevator|lift\b|"
                      r"entry|foyer|vestibule|server|janitor|electrical", re.I)

DESK_FORMULAS = ["DAY-08", "DAY-09", "GLR-05", "CMF-08", "LCT-03"]

W_VISION_DESK = "window geometry read from panoramas, not measured"
W_DT_PR = "radiant asymmetry of {:.1f} K is at or above the 10 K limit (CMF-06); not recommended"


# ---------------------------------------------------------------- geometry

@dataclass(frozen=True)
class Candidate:
    floor_id: str
    room_id: str
    x: float
    y: float


def is_work_area(room: Room) -> bool:
    return not (room.label and NOT_WORK.search(room.label))


def _vertices(floor: Floor) -> dict[str, tuple[float, float]]:
    return {v.id: (v.x, v.y) for v in floor.vertices}


def wall_segments(floor: Floor) -> tuple[np.ndarray, np.ndarray]:
    """(segments (n, 2, 2), half thicknesses (n,)) of the edges that are walls, not invisible."""
    vs = _vertices(floor)
    segs, half = [], []
    for e in floor.edges:
        if e.type == "invisible":
            continue
        a, b = e.vertex_ids
        if a in vs and b in vs:
            segs.append((vs[a], vs[b]))
            half.append(0.5 * (e.thickness_m if e.thickness_m is not None else DEFAULT_WALL_THICKNESS_M))
    return np.asarray(segs, float).reshape(-1, 2, 2), np.asarray(half, float)


def door_segments(floor: Floor) -> tuple[np.ndarray, np.ndarray]:
    """(opening segments (n, 2, 2) along the wall, leaf widths (n,)) for every opening that is not
    a window. `relative_center` is a fraction of the edge length, but which vertex it is measured
    from is open (physics.md section 8), so both readings are kept clear."""
    vs = _vertices(floor)
    segs, widths = [], []
    for e in floor.edges:
        a, b = e.vertex_ids
        if a not in vs or b not in vs:
            continue
        p0, p1 = np.asarray(vs[a], float), np.asarray(vs[b], float)
        length = float(np.hypot(*(p1 - p0)))
        if length <= 0:
            continue
        u = (p1 - p0) / length
        for o in e.openings:
            if o.type == "window":
                continue
            w = o.width_m if o.width_m else DOOR_WIDTH_DEFAULT_M
            rc = 0.5 if o.relative_center is None else o.relative_center
            for frac in {rc, 1.0 - rc}:
                c = p0 + u * frac * length
                segs.append((c - u * w / 2, c + u * w / 2))
                widths.append(w)
    return np.asarray(segs, float).reshape(-1, 2, 2), np.asarray(widths, float)


def point_segment_distance(pts: np.ndarray, segs: np.ndarray) -> np.ndarray:
    """Distances (n_points, n_segments) from points (n, 2) to segments (m, 2, 2)."""
    if len(segs) == 0:
        return np.full((len(pts), 0), np.inf)
    a, b = segs[:, 0, :], segs[:, 1, :]
    ab = b - a
    denom = np.einsum("ij,ij->i", ab, ab)
    denom = np.where(denom > 0, denom, 1.0)
    ap = pts[:, None, :] - a[None, :, :]
    t = np.clip(np.einsum("nmj,mj->nm", ap, ab) / denom, 0.0, 1.0)
    closest = a[None, :, :] + t[..., None] * ab[None, :, :]
    return np.hypot(*(pts[:, None, :] - closest).transpose(2, 0, 1))


def candidate_grid(matterport: MatterportData, *, grid_m: float = GRID_M,
                   wall_clearance_m: float = WALL_CLEARANCE_M) -> list[Candidate]:
    """Every grid point strictly inside a work-area room, `wall_clearance_m` from every wall face
    and outside every door keep-out zone. The door zone is the opening buffered by its leaf width
    (the swing on either side) plus the wall clearance. A point on a room's boundary is dropped:
    on an invisible edge between two rooms no wall clearance removes it, and the daylight scorer's
    point-in-polygon test may put a boundary point outside the room."""
    floors = {f.id: f for f in matterport.floors}
    seen: set[tuple[str, float, float]] = set()
    out: list[Candidate] = []
    cache: dict[str, tuple] = {}
    for room in matterport.rooms:
        floor = floors.get(room.floor_id)
        if floor is None or len(room.polygon) < 3 or not is_work_area(room):
            continue
        if floor.id not in cache:
            cache[floor.id] = (*wall_segments(floor), *door_segments(floor))
        walls, half, doors, widths = cache[floor.id]
        poly = Polygon(room.polygon)
        if not poly.is_valid:
            poly = poly.buffer(0)
        minx, miny, maxx, maxy = poly.bounds
        xs = np.arange(math.ceil(minx / grid_m - 1e-9), math.floor(maxx / grid_m + 1e-9) + 1) * grid_m
        ys = np.arange(math.ceil(miny / grid_m - 1e-9), math.floor(maxy / grid_m + 1e-9) + 1) * grid_m
        if len(xs) == 0 or len(ys) == 0:
            continue
        gx, gy = np.meshgrid(xs, ys)
        pts = np.column_stack([gx.ravel(), gy.ravel()])
        ok = shapely.contains_xy(poly, pts[:, 0], pts[:, 1])      # interior only, never the boundary
        pts = pts[ok]
        if len(pts) and len(walls):
            clear = point_segment_distance(pts, walls) - half[None, :]
            pts = pts[(clear >= wall_clearance_m - 1e-9).all(axis=1)]
        if len(pts) and len(doors):
            d = point_segment_distance(pts, doors)
            pts = pts[(d > widths[None, :] + wall_clearance_m).all(axis=1)]
        for x, y in pts:
            key = (floor.id, round(float(x), 6), round(float(y), 6))
            if key in seen:
                continue
            seen.add(key)
            out.append(Candidate(floor.id, room.id, key[1], key[2]))
    return out


# ---------------------------------------------------------------- scoring (LCT-03)

def desk_score(da_300: float, glare_risk: float, comfort_ppd: float,
               weights: Mapping[str, float] = SCORE_WEIGHTS) -> dict[str, float]:
    """physics 03 LCT-03: {score, s_d, s_g, s_c}, each 0 to 1."""
    s_d = min(1.0, max(0.0, da_300))
    s_g = 1.0 - min(1.0, max(0.0, glare_risk) / G_MAX)
    s_c = 1.0 - min(1.0, max(0.0, comfort_ppd - PPD_FLOOR) / (PPD_MAX - PPD_FLOOR))
    score = weights["daylight"] * s_d + weights["glare"] * s_g + weights["comfort"] * s_c
    return {"score": score, "s_d": s_d, "s_g": s_g, "s_c": s_c}


@dataclass
class Scored:
    cand: Candidate
    desk: DeskScore
    saved_fraction: Optional[float]      # mean 1 - f_P at the setpoint, for the control type used
    eligible: bool


def _saved_fraction(raw: Mapping[str, Any], control_type: str) -> Optional[float]:
    v = raw.get("lighting_saved_fraction")
    if v is None:
        return None
    if isinstance(v, Mapping):
        got = v.get(control_type, v.get("auto_on_off"))
        return None if got is None else float(got)
    return float(v)


def score_candidates(bundle: PropertyBundle, model: BuildingModel, cands: Sequence[Candidate],
                     score_point: ScorePoint, *, setpoint_lux: float, control_type: str,
                     extra_warnings: Sequence[str] = ()) -> list[Scored]:
    rooms = {r.id: r for r in bundle.matterport.rooms}
    out = []
    for c in cands:
        raw = score_point(bundle=bundle, model=model, room=rooms[c.room_id], x=c.x, y=c.y,
                          setpoint_lux=setpoint_lux)
        da = min(1.0, max(0.0, float(raw["daylight"])))
        glare = min(1.0, max(0.0, float(raw["glare_risk"])))
        ppd = min(100.0, max(PPD_FLOOR, float(raw["comfort_ppd"])))
        s = desk_score(da, glare, ppd)
        warnings = list(extra_warnings) + [w for w in raw.get("warnings", []) or [] if w not in extra_warnings]
        dt_pr = raw.get("max_dt_pr_k")
        eligible = True
        if dt_pr is not None and float(dt_pr) >= DT_PR_LIMIT_K:
            eligible = False
            warnings.append(W_DT_PR.format(float(dt_pr)))
        desk = DeskScore(room_id=c.room_id, x=c.x, y=c.y, daylight=da, glare_risk=glare,
                         comfort_ppd=ppd, score=round(s["score"], 4),
                         daylight_factor=raw.get("daylight_factor"),
                         view_azimuth_deg=raw.get("view_azimuth_deg"),
                         direct_sun_hours=raw.get("direct_sun_hours"),
                         max_dt_pr_k=None if dt_pr is None else float(dt_pr), warnings=warnings)
        out.append(Scored(c, desk, _saved_fraction(raw, control_type), eligible))
    return out


def _order(scored: Sequence[Scored]) -> list[Scored]:
    return sorted(scored, key=lambda s: (-s.desk.score, s.cand.floor_id, s.cand.y, s.cand.x))


def pick_spaced(scored: Sequence[Scored], n: int, min_spacing_m: float = MIN_SPACING_M,
                taken: Sequence[Scored] = ()) -> list[Scored]:
    """Greedy top-n by score, each at least `min_spacing_m` from every one already taken on the
    same floor. Ineligible positions are skipped."""
    picked: list[Scored] = []
    held = list(taken)
    for s in _order(scored):
        if len(picked) >= n:
            break
        if not s.eligible or any(s is t for t in held):
            continue
        if all(t.cand.floor_id != s.cand.floor_id or
               math.hypot(t.cand.x - s.cand.x, t.cand.y - s.cand.y) >= min_spacing_m - 1e-9
               for t in held):
            picked.append(s)
            held.append(s)
    return picked


# ---------------------------------------------------------------- lighting credit (LCT-02)

def control_type_of(model: BuildingModel) -> str:
    a = next((a for a in model.assumptions if a.key == "lighting.control_type"), None)
    return a.value if a is not None and isinstance(a.value, str) else "none"


AUTOMATIC = ("continuous", "continuous_off", "stepped", "auto_on_off")


def manual_switch_fraction(model: BuildingModel) -> Ranged:
    a = next((a for a in model.assumptions if a.key == "lighting.manual_switch_fraction"), None)
    if a is not None and isinstance(a.value, Ranged):
        return a.value
    return Ranged(low=0.0, expected=0.5, high=1.0, unit="-")   # physics 03 section 0.4, [U]


@dataclass
class Layout:
    result: LayoutResult
    recommended: list[Scored]
    params: dict = field(default_factory=dict)
    candidates_scored: int = 0


def place_desks(bundle: PropertyBundle, model: BuildingModel, desks_requested: Optional[int],
                score_point: ScorePoint, *, flow: str = "office",
                min_spacing_m: float = MIN_SPACING_M) -> Layout:
    """physics 03 `score_desk_positions`: grid, score, top N with spacing, LCT-02 credit."""
    mp = bundle.matterport
    cands = candidate_grid(mp)
    windows = [s for s in model.surfaces if s.kind == "window"]
    window_source = (None if not windows else
                     "measured" if any(s.source_opening_id for s in windows) else "vision")
    warnings: list[str] = []
    desk_warn: list[str] = []
    if window_source == "vision":
        warnings.append("Window geometry was read from panoramas: this model has no measured openings.")
        desk_warn.append(W_VISION_DESK)

    work_area = sum(Polygon(r.polygon).area for r in mp.rooms
                    if is_work_area(r) and len(r.polygon) >= 3)
    if desks_requested is None:
        occ = model.systems.occupants
        desks_requested = (max(1, round(occ.expected)) if occ is not None else
                           max(1, int(work_area // AREA_PER_DESK_M2)))
        warnings.append(f"No desk count was given; {desks_requested} desks assumed from "
                        + ("the occupant count." if occ is not None else
                           f"{AREA_PER_DESK_M2:g} m2 of work area per desk."))
    n = int(desks_requested)

    setpoint = SETPOINT_LUX.get(flow, SETPOINT_LUX["office"])
    hours = OCCUPIED_HOURS.get(flow, OCCUPIED_HOURS["office"])
    control = control_type_of(model)
    scored = score_candidates(bundle, model, cands, score_point, setpoint_lux=setpoint,
                              control_type=control, extra_warnings=desk_warn)
    rec = pick_spaced(scored, n, min_spacing_m)
    if len(rec) < n:
        warnings.append(f"Only {len(rec)} of the {n} desks requested fit at {min_spacing_m:g} m "
                        f"spacing on positions clear of walls and doors.")
    alt = pick_spaced(scored, max(0, REPORTED_PER_DESK * n - len(rec)), min_spacing_m, taken=rec)
    for s in rec:
        s.desk.recommended = True
    shown = _order(rec + alt)

    # LCT-02
    lpd = model.systems.lighting_w_per_m2
    fracs = [s.saved_fraction for s in rec]
    if any(f is None for f in fracs):
        fracs = [s.desk.daylight if s.saved_fraction is None else s.saved_fraction for s in rec]
        warnings.append(f"The point scorer gave no lighting fraction at {setpoint:g} lx; daylight "
                        f"autonomy at {TARGET_LUX:g} lx stands in for it, which overstates the saving.")
    mean_frac = float(np.mean(fracs)) if fracs else 0.0
    p_ctrl = {k: getattr(lpd, k) * AREA_PER_DESK_M2 * len(rec) for k in ("low", "expected", "high")}
    e_full = {k: p_ctrl[k] / 1000.0 * hours * mean_frac for k in p_ctrl}
    params: dict[str, Any] = {"grid_m": GRID_M, "wall_clearance_m": WALL_CLEARANCE_M,
                              "min_spacing_m": min_spacing_m}
    if control in AUTOMATIC:
        kwh = Ranged(low=e_full["low"], expected=e_full["expected"], high=e_full["high"], unit="kWh")
    elif control == "none":
        km = manual_switch_fraction(model)
        params["manual_switch_fraction"] = km.model_dump()
        kwh = Ranged(low=0.0, expected=km.expected * e_full["expected"],
                     high=max(km.expected * e_full["expected"], km.high * e_full["high"]), unit="kWh")
        warnings.append("depends on occupants switching lights off")
        warnings.append(f"The expected value uses a manual-switching share of {km.expected:g}, "
                        f"which has no published source.")
    else:
        # e.g. LGT_CTRL already applied ("occupancy_daylight"): its controls hold the daylight
        # saving, and LCT-02 credits LAYOUT only with the change from the old desk positions,
        # which the scan does not give.
        kwh = Ranged(low=0.0, expected=0.0, high=0.0, unit="kWh")
        warnings.append(f"Lighting control '{control}' already captures daylight savings; the desk "
                        f"positions before the move are unknown, so no extra saving is claimed.")
    params["auto_on_off_saved_fraction" if control in ("none", "auto_on_off") else
           "saved_fraction"] = round(mean_frac, 4)
    params["controlled_power_w"] = round(p_ctrl["expected"], 2)
    params["candidates_scored"] = len(scored)

    result = LayoutResult(candidates=[s.desk for s in shown], desks_requested=n,
                          window_source=window_source, target_lux=TARGET_LUX, setpoint_lux=setpoint,
                          control_type=control, score_weights=dict(SCORE_WEIGHTS),
                          occupied_hours_per_year=hours, lighting_kwh_saved=kwh, warnings=warnings)
    return Layout(result, rec, params, len(scored))


def window_surfaces(model: BuildingModel) -> list[Surface]:
    return [s for s in model.surfaces if s.kind == "window"]

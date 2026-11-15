"""Panel layout (SPEC 6.3 step 6, physics 01 LAY-03 with ROOF-04 capacity and ROOF-06 re-check).

Fill planes in order of yield per panel, one module at a time, and stop at the first of:
(a) no usable position left (roof area), (b) installed cost of the next module would
exceed the budget, (c) cumulative annual energy has reached the site's annual use.

Capacity of a plane (ROOF-04): ``N_plane = floor(N_pack * A_usable / A_rect)``, where
``N_pack`` is the LAY-01 packing of the setback region and ``A_rect`` its area. Located
obstructions and tree masks are also cut out geometrically, so no drawn panel overlaps
them; ``A_usable`` is ``RoofPlane.usable_area_m2`` (which A11 computed with the 18 inch
ridge setback), so count-only obstructions are honoured through the ratio.

ROOF-06 ridge setback: the 33 % threshold (66 % sprinklered) is the array's share of the
plan-view TOTAL roof area. The layout is first run with the 18 inch setback; if its share
crosses the threshold, it is re-run with the 36 inch setback on every pitched plane, and
the alternative of staying at or below the threshold with 18 inches is also built. The one
with more annual energy is kept (ROOF-04 golden-house example: 40 against 36 modules).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional, Union

from shapely import wkt as shapely_wkt
from shapely.geometry.base import BaseGeometry

from backend.schema import Flag, PanelPlacement, Ranged, RoofPlane, SolarDesign

from .packing import Module, best_packing, flat_grids, pitched_grids, RACK_TILT_DEG
from .region import (RIDGE_SETBACK_HIGH_SHARE_M, RIDGE_SETBACK_LOW_SHARE_M, RIDGE_SHARE_LIMIT,
                     RIDGE_SHARE_LIMIT_SPRINKLERED, SLOPE_EXEMPT_DEG, BuildingGroup, PlaneRegion,
                     is_flat, plane_region)

# --- constants destined for backend/config.py (kept local until A0 wires them) ---
NORTH_EXCLUDE_FROM_DEG = 292.5      # LAY-03 step 1 (GAG16 3.5): NW through NE unsuitable
NORTH_EXCLUDE_TO_DEG = 67.5
NORTH_EXCLUDE_MIN_TILT_DEG = 9.5    # LAY-03 step 1: the rule applies to tilted planes only
MAX_TILT_DEG = 60.0                 # LAY-03 step 1: steeper planes are unsuitable
MAX_SHADING_LOSS = 0.20             # LAY-03 step 5 / SHD-05: skip positions shaded above this
WKT_DECIMALS = 9                    # ~0.1 mm in latitude, so output panels stay inside the region
# #396 fill-order tie-break: within about this fraction of yield, the more western face fills first.
# Afternoon output is worth more under time-of-use rates (LA and Houston peaks are late afternoon), and
# without it an exact east/west tie went to the east face, which A11 lists first on a north-south ridge.
# Orders the fill only; energy and money still use the plane's own yield.
WEST_TIEBREAK = 0.01

StopReason = Literal["roof_area", "budget", "consumption", "fire_code_share", "blocked"]
YieldValue = Union[float, Ranged]
YieldFn = Callable[[RoofPlane, Optional[str]], Union[YieldValue, tuple[YieldValue, float]]]
CostArg = Union[float, Callable[[int], float], None]


@dataclass
class Candidate:
    plane_idx: int
    pos_idx: int
    polygon_wkt: Optional[str]
    yield_low: float          # kWh per kW DC per year
    yield_exp: float
    yield_high: float
    shading: float
    plan_m2: float            # plan-view area of the module (for the ROOF-06 share)
    azimuth_deg: float = 180.0  # plane azimuth, 0 = north clockwise (fill-order tie-break only)


@dataclass
class PVLayout:
    """``SolarDesign`` plus what the contract has no field for."""
    design: SolarDesign
    stop_reason: StopReason
    array_plan_share: float
    roof_plan_area_m2: float
    ridge_setback_m: float
    capacity: dict[str, int]                     # plane id -> ROOF-04 capacity under the kept setback
    regions: dict[str, PlaneRegion]              # plane id -> usable region under the kept setback
    excluded: dict[str, str] = field(default_factory=dict)   # plane id -> reason
    notes: list[str] = field(default_factory=list)


def plane_excluded(plane: RoofPlane, exclude_north: bool = True) -> Optional[str]:
    """LAY-03 step 1."""
    tilt = plane.tilt_deg.expected
    if tilt > MAX_TILT_DEG:
        return f"tilt {tilt:g} deg above {MAX_TILT_DEG:g} (LAY-03)"
    az = plane.azimuth_deg % 360.0
    if exclude_north and tilt >= NORTH_EXCLUDE_MIN_TILT_DEG and \
            (az >= NORTH_EXCLUDE_FROM_DEG or az <= NORTH_EXCLUDE_TO_DEG):
        return f"faces {az:g} deg, between 292.5 and 67.5 through north (LAY-03)"
    return None


def fill_rank(c: Candidate) -> float:
    """LAY-03 step 3 order: yield per kW, nudged by WEST_TIEBREAK toward the afternoon (west) side."""
    westness = -math.sin(math.radians(c.azimuth_deg))      # +1 due west, -1 due east, 0 north or south
    return c.yield_exp * (1.0 + WEST_TIEBREAK * westness)


def _cost_fn(cost: CostArg) -> Optional[Callable[[int], float]]:
    if cost is None:
        return None
    if callable(cost):
        return cost
    per = float(cost)
    return lambda n: n * per


def greedy_fill(candidates: list[Candidate], capacity: dict[int, int], module_kw: float,
                budget_usd: Optional[float] = None, installed_cost_usd: CostArg = None,
                annual_use_kwh: Optional[float] = None,
                ) -> tuple[list[Candidate], StopReason]:
    """LAY-03 steps 3 to 5: place modules one at a time, best yield first."""
    cost = _cost_fn(installed_cost_usd)
    if budget_usd is not None and cost is None:
        raise ValueError("a budget needs installed_cost_usd (per module, or a function of the count)")
    order = sorted(candidates, key=lambda c: (-fill_rank(c), c.plane_idx, c.pos_idx))
    placed: list[Candidate] = []
    per_plane: dict[int, int] = {}
    energy = 0.0
    if annual_use_kwh is not None and energy >= annual_use_kwh:
        return placed, "consumption"
    for c in order:
        if c.shading > MAX_SHADING_LOSS or c.yield_exp <= 0:
            continue
        if per_plane.get(c.plane_idx, 0) >= capacity.get(c.plane_idx, 0):
            continue
        if budget_usd is not None and cost(len(placed) + 1) > budget_usd:
            return placed, "budget"
        placed.append(c)
        per_plane[c.plane_idx] = per_plane.get(c.plane_idx, 0) + 1
        energy += c.yield_exp * module_kw
        if annual_use_kwh is not None and energy >= annual_use_kwh:
            return placed, "consumption"
    return placed, "roof_area"


def _yield_parts(value) -> tuple[float, float, float, float]:
    shading = 0.0
    if isinstance(value, tuple):
        value, shading = value
    if isinstance(value, Ranged):
        return value.low, value.expected, value.high, float(shading)
    v = float(value)
    return v, v, v, float(shading)


def _rack_plane(plane: RoofPlane) -> RoofPlane:
    """A flat plane as the modules see it: rack tilt (LAY-02), rack azimuth = plane azimuth."""
    t = RACK_TILT_DEG
    return plane.model_copy(update={"tilt_deg": Ranged(low=t, expected=t, high=t, unit="deg")})


def _wkt(geom: BaseGeometry) -> str:
    return shapely_wkt.dumps(geom, rounding_precision=WKT_DECIMALS)


@dataclass
class _PlaneLayout:
    region: PlaneRegion
    capacity: int
    candidates: list[Candidate]


def _plane_layout(i: int, plane: RoofPlane, group: BuildingGroup, ridge: float,
                  ridge_base: float, module: Module, yield_fn: YieldFn) -> _PlaneLayout:
    flat = is_flat(plane)
    region = plane_region(plane, group, ridge)
    grids = flat_grids(module) if flat else pitched_grids(module)
    _, rect_cells = best_packing(region.setback_uv, grids)
    a_rect = region.a_rect_m2
    if a_rect <= 0 or not rect_cells:
        return _PlaneLayout(region, 0, [])
    # usable area under this ridge setback: A11's usable area less the extra setback strip
    usable = plane.usable_area_m2
    if ridge != ridge_base:
        base_rect = plane_region(plane, group, ridge_base).a_rect_m2
        usable = max(0.0, a_rect - max(0.0, base_rect - plane.usable_area_m2))
    ratio = min(1.0, max(0.0, usable / a_rect))
    if region.usable_uv.equals(region.setback_uv):
        cells = rect_cells
    else:
        cells = best_packing(region.usable_uv, grids)[1]
    capacity = min(len(cells), int(math.floor(len(rect_cells) * ratio + 1e-9)))

    seen = _rack_plane(plane) if flat else plane
    cosb = 1.0 if flat else math.cos(math.radians(plane.tilt_deg.expected))
    cands = []
    for j, cell in enumerate(cells):
        poly_wkt = _wkt(region.frame.to_lonlat(cell)) if region.frame is not None else None
        lo, ex, hi, sh = _yield_parts(yield_fn(seen, poly_wkt))
        cands.append(Candidate(i, j, poly_wkt, lo, ex, hi, sh, cell.area * cosb, plane.azimuth_deg % 360.0))
    return _PlaneLayout(region, capacity, cands)


def _run(planes, eligible, group, ridge, module, yield_fn, budget, cost, use):
    layouts = {i: _plane_layout(i, planes[i], group, ridge, RIDGE_SETBACK_LOW_SHARE_M, module, yield_fn)
               for i in eligible}
    cands = [c for pl in layouts.values() for c in pl.candidates]
    caps = {i: pl.capacity for i, pl in layouts.items()}
    placed, reason = greedy_fill(cands, caps, module.watts / 1000.0, budget, cost, use)
    return layouts, placed, reason


def _energy(placed: list[Candidate], module_kw: float) -> float:
    return sum(c.yield_exp for c in placed) * module_kw


def layout_pv_detailed(planes: list[RoofPlane], electrical: Flag, structural: Flag,
                       yield_fn: YieldFn, budget_usd: Optional[float] = None,
                       annual_consumption_kwh: Optional[float] = None, *,
                       installed_cost_usd: CostArg = None, module: Module = Module(),
                       building_group: Optional[BuildingGroup] = None, sprinklered: bool = False,
                       exclude_north: bool = True) -> PVLayout:
    """LAY-03 with the ROOF-06 share re-check. See ``layout_pv``."""
    group: BuildingGroup = building_group or ("commercial" if planes and all(is_flat(p) for p in planes)
                                              else "R-3")
    module_kw = module.watts / 1000.0
    roof_plan = sum(p.area_m2 * math.cos(math.radians(p.tilt_deg.expected)) for p in planes)
    excluded = {p.id: r for p in planes if (r := plane_excluded(p, exclude_north))}
    eligible = [i for i, p in enumerate(planes) if p.id not in excluded]
    notes: list[str] = []

    def finish(layouts, placed, reason, ridge):
        share = sum(c.plan_m2 for c in placed) / roof_plan if roof_plan > 0 else 0.0
        design = _design(planes, placed, module, electrical, structural)
        return PVLayout(design, reason, share, roof_plan, ridge,
                        {planes[i].id: pl.capacity for i, pl in layouts.items()},
                        {planes[i].id: pl.region for i, pl in layouts.items()}, excluded, notes)

    blocked = [f.key for f in (electrical, structural) if f.status == "blocked"]
    if blocked:
        notes.append(f"no modules placed: flag {', '.join(blocked)} is blocked")
        return finish({}, [], "blocked", RIDGE_SETBACK_LOW_SHARE_M)

    args = (module, yield_fn, budget_usd, installed_cost_usd, annual_consumption_kwh)
    layouts, placed, reason = _run(planes, eligible, group, RIDGE_SETBACK_LOW_SHARE_M, *args)
    pitched_r3 = group == "R-3" and any(planes[i].tilt_deg.expected > SLOPE_EXEMPT_DEG for i in eligible)
    limit = RIDGE_SHARE_LIMIT_SPRINKLERED if sprinklered else RIDGE_SHARE_LIMIT
    share = sum(c.plan_m2 for c in placed) / roof_plan if roof_plan > 0 else 0.0
    if not pitched_r3 or share <= limit:
        return finish(layouts, placed, reason, RIDGE_SETBACK_LOW_SHARE_M)

    # B: 36 inch ridge setback on every pitched plane, layout re-run
    lay_b, placed_b, reason_b = _run(planes, eligible, group, RIDGE_SETBACK_HIGH_SHARE_M, *args)
    # C: 18 inch setback, stop before the share passes the threshold
    placed_c: list[Candidate] = []
    acc = 0.0
    for c in placed:
        if (acc + c.plan_m2) / roof_plan > limit:
            break
        placed_c.append(c)
        acc += c.plan_m2
    notes.append(f"array share {share:.3f} of plan roof area exceeds {limit:g} with the 18 in ridge "
                 f"setback (ROOF-06): 36 in setback gives {len(placed_b)} modules, staying at or below "
                 f"{limit:g} gives {len(placed_c)}")
    if _energy(placed_b, module_kw) >= _energy(placed_c, module_kw):
        return finish(lay_b, placed_b, reason_b, RIDGE_SETBACK_HIGH_SHARE_M)
    return finish(layouts, placed_c, "fire_code_share", RIDGE_SETBACK_LOW_SHARE_M)


def _design(planes, placed: list[Candidate], module: Module, electrical: Flag,
            structural: Flag) -> SolarDesign:
    kw = module.watts / 1000.0
    panels = [PanelPlacement(plane_id=planes[c.plane_idx].id, polygon_wkt=c.polygon_wkt,
                             annual_kwh=round(c.yield_exp * kw, 3), shading_loss_fraction=c.shading)
              for c in placed]
    lo = sum(c.yield_low for c in placed) * kw
    ex = sum(c.yield_exp for c in placed) * kw
    hi = sum(c.yield_high for c in placed) * kw
    return SolarDesign(
        system_kw_dc=round(len(placed) * kw, 6), panel_count=len(panels), panels=panels,
        annual_kwh=Ranged(low=min(lo, ex), expected=ex, high=max(hi, ex), unit="kWh"),
        module_w=module.watts, electrical=electrical, structural=structural,
    )


def layout_pv(planes: list[RoofPlane], electrical: Flag, structural: Flag, yield_fn: YieldFn,
              budget_usd: Optional[float] = None, annual_consumption_kwh: Optional[float] = None,
              **kwargs) -> SolarDesign:
    """SPEC 6.3 step 6 / LAY-03: lay out modules and return the ``SolarDesign``.

    ``yield_fn(plane, panel_polygon_wkt)`` returns the annual AC energy per kW DC (kWh/kW/yr)
    of one module position: a float, a ``Ranged`` (the PV-09 range, summed into
    ``annual_kwh``), or a tuple ``(value, shading_loss_fraction)``. It is called once per
    candidate position (``panel_polygon_wkt`` is None on the area method), so a caller
    without per-position shading should memoise by plane. On flat planes it receives the
    plane at the LAY-02 rack tilt.

    ``budget_usd`` and ``annual_consumption_kwh`` are plain numbers; None disables that stop.
    ``installed_cost_usd`` (keyword) is the installed cost per module, or a function of the
    module count returning the total installed cost; required when a budget is given.
    Other keywords: ``module`` (PV-08 defaults), ``building_group`` ("R-3" or "commercial";
    default commercial when every plane is flat, else R-3), ``sprinklered``, ``exclude_north``.

    Electrical and structural flags are carried into the design; a ``blocked`` flag means
    no modules are placed. Inverter, losses and degradation are left for the PV model.
    """
    return layout_pv_detailed(planes, electrical, structural, yield_fn, budget_usd,
                              annual_consumption_kwh, **kwargs).design

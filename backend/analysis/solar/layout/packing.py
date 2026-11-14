"""Packing rectangular modules into a usable polygon (physics 01 LAY-01, LAY-02).

Everything here works in plane coordinates: ``u`` along the eave, ``v`` up the
slope, metres measured in the roof plane. On flat roofs ``v`` is the plan
direction away from the rack azimuth and cells are the plan footprints of tilted
modules laid in rows at pitch ``P = L / GCR``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

# --- constants destined for backend/config.py (kept local until A0 wires them) ---
MODULE_W = 430.0             # PV-08 default rating, W [U, not from a data sheet]
MODULE_LONG_M = 1.722        # PV-08 / LAY-01 default module, long side [U]
MODULE_SHORT_M = 1.134       # PV-08 / LAY-01 default module, short side [U]
GAP_M = 0.0127               # LAY-01: gap between modules for clamps, GAG16 section 4.4
SEARCH_STEP_M = 0.05         # LAY-01: grid-origin step of the polygon search
RACK_TILT_DEG = 15.0         # LAY-02 default rack tilt on flat roofs, GAG16 Table 1
RACK_GCR = 0.70              # LAY-02 default ground coverage ratio, GAG16 Table 1
_EPS = 1e-9                  # tolerance for exact fits (metres)
_CONTAIN_TOL_M = 1e-7        # containment slack against floating-point boundary hits


@dataclass(frozen=True)
class Module:
    """Module rating and size (PV-08)."""
    watts: float = MODULE_W
    long_m: float = MODULE_LONG_M
    short_m: float = MODULE_SHORT_M
    gap_m: float = GAP_M

    @property
    def area_m2(self) -> float:
        return self.long_m * self.short_m


@dataclass(frozen=True)
class Grid:
    """A cell size and grid period. ``ch`` is the cell height along v, ``pv`` the row period."""
    cw: float
    ch: float
    pu: float
    pv: float
    label: str


def pitched_grids(module: Module) -> list[Grid]:
    """LAY-01: portrait (short side along the eave) then landscape."""
    a, b, g = module.short_m, module.long_m, module.gap_m
    return [Grid(a, b, a + g, b + g, "portrait"), Grid(b, a, b + g, a + g, "landscape")]


def flat_grids(module: Module, tilt_deg: float = RACK_TILT_DEG, gcr: float = RACK_GCR) -> list[Grid]:
    """LAY-02: rows at pitch P = L / GCR; the cell is the plan footprint of one tilted module.

    L is the slant length up the rack: the long side (portrait) or the short side (landscape).
    """
    cosb = math.cos(math.radians(tilt_deg))
    out = []
    for slant, across, label in ((module.long_m, module.short_m, "portrait"),
                                 (module.short_m, module.long_m, "landscape")):
        out.append(Grid(across, slant * cosb, across + module.gap_m, slant / gcr, label))
    return out


def _is_axis_rectangle(poly: BaseGeometry) -> bool:
    if poly.geom_type != "Polygon" or len(poly.interiors):
        return False
    env = poly.envelope
    return abs(env.area - poly.area) <= 1e-9 * max(1.0, env.area)


def _rect_fit(length: float, cell: float, period: float) -> int:
    if length + _EPS < cell:
        return 0
    return int(math.floor((length - cell + _EPS) / period)) + 1


def pack_grid(poly: BaseGeometry, grid: Grid, step: float = SEARCH_STEP_M) -> list[Polygon]:
    """Cells of one grid lying entirely inside ``poly``.

    Exact closed form when ``poly`` is an axis-aligned rectangle (LAY-01 formula, which is
    n = floor((W + g) / (a + g)) for touching rows); otherwise the LAY-01 grid search: slide
    the grid origin over one period in ``step`` increments and keep the origin that fits the
    most cells (first such origin, for determinism).
    """
    if poly is None or poly.is_empty or poly.area <= 0:
        return []
    minx, miny, maxx, maxy = poly.bounds
    if _is_axis_rectangle(poly):
        nc = _rect_fit(maxx - minx, grid.cw, grid.pu)
        nr = _rect_fit(maxy - miny, grid.ch, grid.pv)
        return [box(minx + i * grid.pu, miny + j * grid.pv,
                    minx + i * grid.pu + grid.cw, miny + j * grid.pv + grid.ch)
                for j in range(nr) for i in range(nc)]

    test = poly.buffer(_CONTAIN_TOL_M, join_style="mitre")
    shapely.prepare(test)
    convex = len(poly.interiors) == 0 if poly.geom_type == "Polygon" else False
    convex = convex and abs(poly.convex_hull.area - poly.area) <= 1e-9 * max(1.0, poly.area)

    nci = max(0, int(math.ceil((maxx - minx) / grid.pu)) + 1)
    nri = max(0, int(math.ceil((maxy - miny) / grid.pv)) + 1)
    if nci == 0 or nri == 0:
        return []
    oxs = np.arange(0.0, grid.pu - 1e-12, step)
    oys = np.arange(0.0, grid.pv - 1e-12, step)
    ii, jj = np.meshgrid(np.arange(nci), np.arange(nri), indexing="xy")
    ii, jj = ii.ravel(), jj.ravel()

    best: tuple[int, np.ndarray, np.ndarray] = (0, np.empty(0), np.empty(0))
    for oy in oys:
        # all x origins at once: shape (n_ox, n_cells)
        x0 = minx + oxs[:, None] + ii[None, :] * grid.pu
        y0 = np.broadcast_to(miny + oy + jj[None, :] * grid.pv, x0.shape)
        x1, y1 = x0 + grid.cw, y0 + grid.ch
        ok = (shapely.contains_xy(test, x0, y0) & shapely.contains_xy(test, x1, y0)
              & shapely.contains_xy(test, x1, y1) & shapely.contains_xy(test, x0, y1))
        if not convex and ok.any():
            idx = np.nonzero(ok)
            boxes = shapely.box(x0[idx], y0[idx], x1[idx], y1[idx])
            ok[idx] = shapely.contains(test, boxes)
        counts = ok.sum(axis=1)
        k = int(np.argmax(counts))
        if counts[k] > best[0]:
            sel = ok[k]
            best = (int(counts[k]), x0[k][sel], y0[k][sel])
    n, xs, ys = best
    if n == 0:
        return []
    order = np.lexsort((xs, ys))           # row by row from the eave, then along the eave
    return [box(xs[i], ys[i], xs[i] + grid.cw, ys[i] + grid.ch) for i in order]


def pack_modules(usable_polygon_uv: BaseGeometry, module_w_m: float, module_h_m: float,
                 gap_m: float = GAP_M, step: float = SEARCH_STEP_M) -> list[Polygon]:
    """LAY-01 tool function: evaluate both orientations, keep the larger count.

    ``module_w_m`` and ``module_h_m`` are the two module sides (order does not matter).
    Ties keep portrait (short side along the eave).
    """
    m = Module(long_m=max(module_w_m, module_h_m), short_m=min(module_w_m, module_h_m), gap_m=gap_m)
    return best_packing(usable_polygon_uv, pitched_grids(m), step)[1]


def best_packing(poly: BaseGeometry, grids: list[Grid],
                 step: float = SEARCH_STEP_M) -> tuple[Grid | None, list[Polygon]]:
    best: tuple[Grid | None, list[Polygon]] = (None, [])
    for g in grids:
        cells = pack_grid(poly, g, step)
        if len(cells) > len(best[1]):
            best = (g, cells)
    return best

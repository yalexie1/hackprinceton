"""Fire-code access pathways and setbacks (physics 01, ROOF-06).

Design defaults for a feasibility study, not a legal determination. The
residential-code text for California houses (R329.6) and the Houston local
adoption are unverified (physics 01 section 8), so every result carries a
``status`` and is never presented as fact.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

# --- constants destined for backend/config.py (kept local until A0 wires them) ---
IN = 0.0254
FT = 12 * IN
PATHWAY_M = 36 * IN                         # 1205.2.1.1, 0.9144 m
RIDGE_SETBACK_LOW_SHARE_M = 18 * IN         # 1205.2.1.2, arrays <= 33 % of plan roof, 0.4572 m
RIDGE_SETBACK_HIGH_SHARE_M = 36 * IN        # 1205.2.1.2, arrays > 33 %, 0.9144 m
RIDGE_SHARE_LIMIT = 0.33                    # 1205.2.1.2
RIDGE_SHARE_LIMIT_SPRINKLERED = 0.66        # 1205.2.1.3
SLOPE_EXEMPT_DEG = math.degrees(math.atan(2 / 12))   # 2 in 12, 9.46 deg (1205.2.1 exception 2)
PERIMETER_SMALL_M = 4 * FT                  # 1205.3.1, either axis <= 250 ft, 1.2192 m
PERIMETER_LARGE_M = 6 * FT                  # 1205.3.1, 1.8288 m
PERIMETER_AXIS_LIMIT_M = 250 * FT           # 76.2 m
INTERIOR_INTERVAL_M = 150 * FT              # 1205.3.2, 45.72 m
INTERIOR_PATHWAY_M = 4 * FT                 # 1205.3.2, 1.2192 m

BuildingGroup = Literal["R-3", "commercial"]


@dataclass(frozen=True)
class Setbacks:
    ridge_setback_m: float
    pathway_width_m: float
    perimeter_m: float
    interior_interval_m: Optional[float]
    basis: str
    status: str          # "V-repro", "U" (unverified) or "P" (pending), physics 01 ROOF-06


def _status(state: Optional[str], building_group: BuildingGroup) -> str:
    st = (state or "").strip().upper()
    if st == "CA" and building_group == "commercial":
        return "V-repro"
    if st == "TX":
        return "P"
    return "U"


def fire_setbacks(state: Optional[str], building_group: BuildingGroup, roof_slope_deg: float,
                  array_plan_share: float = RIDGE_SHARE_LIMIT, sprinklered: bool = False,
                  building_axes_m: Optional[tuple[float, float]] = None) -> Setbacks:
    """ROOF-06 tool function.

    ``array_plan_share`` defaults to the 33 % limit, i.e. the 18-inch ridge
    setback; the layout step (LAY) re-checks the share once modules are placed.
    """
    status = _status(state, building_group)
    if building_group == "R-3":
        if roof_slope_deg <= SLOPE_EXEMPT_DEG:
            return Setbacks(0.0, 0.0, 0.0, None,
                            "IFC 1205.2.1 exception 2: slope 2 in 12 or less", status)
        limit = RIDGE_SHARE_LIMIT_SPRINKLERED if sprinklered else RIDGE_SHARE_LIMIT
        ridge = RIDGE_SETBACK_LOW_SHARE_M if array_plan_share <= limit else RIDGE_SETBACK_HIGH_SHARE_M
        return Setbacks(ridge, PATHWAY_M, 0.0, None,
                        "IFC 1205.2.1.1 pathway, 1205.2.1.2/3 ridge setback", status)
    # commercial
    # 4 ft where either axis is 250 ft or less; 6 ft otherwise, and when the axes are unknown
    if building_axes_m is not None and min(building_axes_m) <= PERIMETER_AXIS_LIMIT_M:
        perimeter = PERIMETER_SMALL_M
    else:
        perimeter = PERIMETER_LARGE_M
    interior = None
    if building_axes_m is not None and max(building_axes_m) > INTERIOR_INTERVAL_M:
        interior = INTERIOR_INTERVAL_M
    return Setbacks(0.0, INTERIOR_PATHWAY_M if interior else 0.0, perimeter, interior,
                    "IFC 1205.3.1 perimeter, 1205.3.2 interior pathways", status)

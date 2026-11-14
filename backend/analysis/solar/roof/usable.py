"""Usable roof area, area method for the parametric roof (physics 01, ROOF-04).

Obstructions come from Vexcel's precomputed ``roof-objects`` counts, which have
no positions, so each plane takes its plan-area share of the allowance. Tree
overhang (``tree_area_m2``) is zero on the parametric path; the SAM 3 roof and
tree masks (package A12) refine it later through the same function.
"""
from __future__ import annotations

import math
from typing import Mapping

from backend.schema import Ranged

from .setbacks import INTERIOR_INTERVAL_M, INTERIOR_PATHWAY_M, Setbacks

# --- constants destined for backend/config.py (kept local until A0 wires them) ---
# Allowance per counted obstruction, m2: footprint grown by its clearance on every
# side. Engineering judgment, no published source [U] (ROOF-04, physics 01
# section 8): carried in the assumption registry with these ranges.
#                    (low, expected, high)
OBSTRUCTION_ALLOWANCE_M2: dict[str, tuple[float, float, float]] = {
    "roof-vent": (0.4, 0.81, 1.5),     # 0.3 x 0.3 m, 0.3 m clearance
    "skylight": (1.4, 2.16, 3.5),      # 0.6 x 1.2 m, 0.3 m clearance
    "chimney": (2.0, 3.04, 5.0),       # 0.6 x 0.9 m, 0.5 m clearance
    "ac-unit": (4.0, 9.00, 12.0),      # 1.0 x 1.0 m, 1.0 m clearance
}
# Vexcel roof-object types with no allowance row get the largest expected
# allowance, so an unknown object never enlarges the usable area. [U]
UNKNOWN_OBSTRUCTION_ALLOWANCE_M2 = (4.0, 9.00, 12.0)
# Pathways reserved on each plane that carries modules (ROOF-04 default).
N_PATH_DEFAULT = 1


def obstruction_allowance_m2(counts: Mapping[str, int]) -> Ranged:
    """Total allowance for all counted obstructions on the roof, m2 (low, expected, high)."""
    low = exp = high = 0.0
    for kind, n in counts.items():
        a_low, a_exp, a_high = OBSTRUCTION_ALLOWANCE_M2.get(kind, UNKNOWN_OBSTRUCTION_ALLOWANCE_M2)
        low += n * a_low
        exp += n * a_exp
        high += n * a_high
    return Ranged(low=low, expected=exp, high=high, unit="m2")


def setback_area_m2(area_m2: float, eave_length_m: float, slope_length_m: float,
                    setbacks: Setbacks, n_path: int = N_PATH_DEFAULT) -> float:
    """In-plane area left after fire-code setbacks (A_rect of ROOF-04).

    Pitched roof: (Le - n_path * w_path) * (S - w_ridge), applied as a fraction of
    the plane area so that the footprint scale factor k of ROOF-05 carries over.
    Commercial roof (perimeter > 0): the perimeter strip is removed from both
    axes, plus one interior pathway per 45.72 m interval along each axis.
    """
    if area_m2 <= 0 or eave_length_m <= 0 or slope_length_m <= 0:
        return 0.0
    le, s = eave_length_m, slope_length_m
    if setbacks.perimeter_m > 0:
        p = setbacks.perimeter_m
        le_c, s_c = max(0.0, le - 2 * p), max(0.0, s - 2 * p)
        if setbacks.interior_interval_m:
            le_c = max(0.0, le_c - _interior_paths(le_c) * INTERIOR_PATHWAY_M)
            s_c = max(0.0, s_c - _interior_paths(s_c) * INTERIOR_PATHWAY_M)
        return area_m2 * (le_c / le) * (s_c / s)
    le_c = max(0.0, le - n_path * setbacks.pathway_width_m)
    s_c = max(0.0, s - setbacks.ridge_setback_m)
    return area_m2 * (le_c / le) * (s_c / s)


def _interior_paths(length_m: float) -> int:
    return max(0, math.ceil(length_m / INTERIOR_INTERVAL_M) - 1)


def usable_area_parametric(area_m2: float, eave_length_m: float, slope_length_m: float,
                           setbacks: Setbacks, obstruction_counts: Mapping[str, int],
                           plan_share: float, tree_area_m2: float = 0.0,
                           n_path: int = N_PATH_DEFAULT) -> float:
    """ROOF-04 area method: A_usable = max(0, A_rect - A_obs - A_tree), expected value.

    ``plan_share`` is this plane's plan area over the whole roof's plan area,
    since obstruction positions are unknown. ``tree_area_m2`` is already in-plane
    (tree mask area over the plane divided by cos(tilt)); A12 supplies it.
    """
    a_rect = setback_area_m2(area_m2, eave_length_m, slope_length_m, setbacks, n_path)
    a_obs = plan_share * obstruction_allowance_m2(obstruction_counts).expected
    return max(0.0, min(area_m2, a_rect - a_obs - max(0.0, tree_area_m2)))

"""Roof pitch range by roof shape class (physics 01, ROOF-03).

Vexcel's calculated roof height (``roof-characteristics.height``) is never read
here: its sign varies and it changes between identical calls (data spec 4.3).
Tilt comes only from the shape class and the footprint size class.
"""
from __future__ import annotations

import math
from typing import Optional

from backend.schema import Ranged

# --- constants destined for backend/config.py (kept local until A0 wires them) ---

# GAG16 small-building threshold: footprint below 5,000 ft2 (ROOF-03).
SMALL_FOOTPRINT_M2 = 5000 * 0.3048 ** 2          # 464.5 m2

# Flat roof row: GAG16 section 3.3 flat < 9.5 deg; expected a quarter unit in 12.
FLAT_PITCH = (0.0, 1.2, 9.5)
# Gable or hip, small footprint: GAG16 Table A-3 class midpoints.
# Hip shares the gable range: no published split exists [U] (physics 01 section 8).
PITCHED_SMALL_PITCH = (15.8, 28.4, 41.1)
# Gable or hip, medium and large footprint: expected and high from GAG16 Tables
# A-1 and A-2; low is the covering minimum, or 1.2 if the covering is unknown. [U]
PITCHED_LARGE_PITCH = (None, 15.8, 28.4)
UNKNOWN_COVERING_MIN_DEG = 1.2
# Unknown or other shape: widest range, flat through the upper edge of the highest
# populated GAG16 class (geometry_source = "assumed").
ASSUMED_PITCH = (0.0, 28.4, 47.4)

# Code minimum slope by covering, 2021 IBC 1507 via one reproduction [U]
# (physics 01 section 8: "until then the floor is optional"). Keyed by Vexcel
# roof-characteristics.material.class. Metal maps to the most permissive metal
# row (standing seam) because the Vexcel class does not say which metal panel.
COVERING_MIN_DEG = {
    "shingle": math.degrees(math.atan(2 / 12)),      # 9.46
    "tile": math.degrees(math.atan(2.5 / 12)),       # 11.77
    "metal": math.degrees(math.atan(0.25 / 12)),     # 1.19
}

PITCHED_SHAPES = ("gable", "hip")
KNOWN_SHAPES = ("flat",) + PITCHED_SHAPES


def normalise_shape(shape_class: Optional[str]) -> Optional[str]:
    """Lower-case, stripped shape class, or None if missing or not a string."""
    if not isinstance(shape_class, str) or not shape_class.strip():
        return None
    return shape_class.strip().lower()


def is_known_shape(shape_class: Optional[str]) -> bool:
    return normalise_shape(shape_class) in KNOWN_SHAPES


def roof_pitch_range(shape_class: Optional[str], footprint_m2: Optional[float],
                     roof_material: Optional[str] = None) -> Ranged:
    """ROOF-03 lookup. Returns the tilt range in degrees.

    Any shape other than flat, gable or hip (including a missing one) gets the
    widest range. A missing footprint area is treated as small (the house row).
    """
    shape = normalise_shape(shape_class)
    if shape == "flat":
        low, exp, high = FLAT_PITCH
    elif shape in PITCHED_SHAPES:
        small = footprint_m2 is None or footprint_m2 < SMALL_FOOTPRINT_M2
        if small:
            low, exp, high = PITCHED_SMALL_PITCH
        else:
            material = normalise_shape(roof_material)
            low = COVERING_MIN_DEG.get(material, UNKNOWN_COVERING_MIN_DEG)
            _, exp, high = PITCHED_LARGE_PITCH
    else:
        low, exp, high = ASSUMED_PITCH
    return Ranged(low=round(low, 2), expected=exp, high=high, unit="deg")

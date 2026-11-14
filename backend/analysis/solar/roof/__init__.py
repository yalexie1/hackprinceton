"""Roof planes for the solar pipeline (Analysis package A11, SPEC 6.3 steps 2 to 4).

Parametric path: Vexcel footprint plus roof shape class, tilt as a range by shape
(physics 01 ROOF-03), azimuth from the footprint's long axis (ROOF-05), usable
area by the area method (ROOF-04) with fire-code setbacks (ROOF-06).

A12 (SAM 3 refinement) will add its own module here and refine
``RoofPlane.usable_area_m2`` through ``usable_area_parametric(..., tree_area_m2=...)``.
"""
from .pitch import roof_pitch_range
from .planes import ParametricRoof, build_parametric_roof, existing_solar, obstruction_counts
from .setbacks import Setbacks, fire_setbacks
from .usable import obstruction_allowance_m2, setback_area_m2, usable_area_parametric

__all__ = [
    "ParametricRoof", "Setbacks", "build_parametric_roof", "existing_solar", "fire_setbacks",
    "obstruction_allowance_m2", "obstruction_counts", "roof_pitch_range", "setback_area_m2",
    "usable_area_parametric",
]

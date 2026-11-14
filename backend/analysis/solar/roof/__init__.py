"""Roof planes for the solar pipeline (Analysis package A11, SPEC 6.3 steps 2 to 4).

Parametric path: Vexcel footprint plus roof shape class, tilt as a range by shape
(physics 01 ROOF-03), azimuth from the footprint's long axis (ROOF-05), usable
area by the area method (ROOF-04) with fire-code setbacks (ROOF-06).

A12 (``masks.py``): SAM 3 pixel masks become map polygons and ground areas; tree
masks lower ``RoofPlane.usable_area_m2`` by the overhang (ROOF-04 ``A_tree``), and
the largest roof mask on the building is a cross-check on the roof area.
"""
from .masks import (MaskPolygon, MaskRefinement, RoofAreaCheck, mask_to_map, refine_with_masks,
                    vectorise_detections)
from .pitch import roof_pitch_range
from .planes import ParametricRoof, build_parametric_roof, existing_solar, obstruction_counts
from .setbacks import Setbacks, fire_setbacks
from .usable import obstruction_allowance_m2, setback_area_m2, usable_area_parametric

__all__ = [
    "MaskPolygon", "MaskRefinement", "ParametricRoof", "RoofAreaCheck", "Setbacks",
    "build_parametric_roof", "existing_solar", "fire_setbacks", "mask_to_map",
    "obstruction_allowance_m2", "obstruction_counts", "refine_with_masks", "roof_pitch_range",
    "setback_area_m2", "usable_area_parametric", "vectorise_detections",
]

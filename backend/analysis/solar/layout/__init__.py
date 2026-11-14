"""Panel layout for the solar pipeline (Analysis package A14, SPEC 6.3 step 6).

Physics 01 LAY-01 (packing), LAY-02 (flat-roof rows), LAY-03 (order and stop
conditions), ROOF-04 (``panel_capacity``) and the ROOF-06 ridge-setback re-check.
"""
from .layout import (Candidate, PVLayout, greedy_fill, layout_pv, layout_pv_detailed,
                     plane_excluded)
from .packing import Module, pack_modules
from .region import PlaneRegion, plane_region

__all__ = [
    "Candidate", "Module", "PVLayout", "PlaneRegion", "greedy_fill", "layout_pv",
    "layout_pv_detailed", "pack_modules", "plane_excluded", "plane_region",
]

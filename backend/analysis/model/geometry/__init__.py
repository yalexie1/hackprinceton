"""A9 S4 Model, geometry: zones, surfaces and true north from the scan (workplan 4.2).

Pure functions, no network. Imported only by ``backend/analysis/api.py``.
"""
from .build import GeometryResult, build_geometry, classify_envelope
from .north import (NorthResult, inverse_north_offset, quaternion_north_offset, resolve_north)
from .walls import opening_center

__all__ = ["GeometryResult", "NorthResult", "build_geometry", "classify_envelope",
           "inverse_north_offset", "opening_center", "quaternion_north_offset", "resolve_north"]

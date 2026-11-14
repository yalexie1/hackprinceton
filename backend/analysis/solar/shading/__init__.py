"""Shading of rooftop PV by ray casting, hour by hour (Analysis package A15, SPEC 6.3 step 4).

Physics 01 SHD-01 (beam fraction), SHD-02 (sky view factor, diffuse factor), SHD-03
(shaded plane-of-array, circumsolar with the beam), SHD-04 (trees and neighbours as
prisms), SHD-05 (annual loss). Entry point: ``shade_panels``.
"""
from .geometry import extrude_mask, extrude_polygon_enu, lonlat_to_enu, plane_normal, sun_vectors
from .raycast import (beam_shading_fraction, beam_shading_fractions, diffuse_shading_factor,
                      rays_blocked, sky_view_factor)
from .shading import (Obstruction, PanelShading, ShadingResult, annual_shading_loss,
                      obstructions_from_detections, shade_panels, shaded_poa_components)

__all__ = [
    "Obstruction", "PanelShading", "ShadingResult", "annual_shading_loss", "beam_shading_fraction",
    "beam_shading_fractions", "diffuse_shading_factor", "extrude_mask", "extrude_polygon_enu",
    "lonlat_to_enu", "obstructions_from_detections", "plane_normal", "rays_blocked", "shade_panels",
    "shaded_poa_components", "sky_view_factor", "sun_vectors",
]

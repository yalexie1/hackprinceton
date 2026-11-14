"""A15 entry point: per-panel, per-hour shading of rooftop PV (physics 01 SHD-01..05).

``shade_panels`` builds the scene (the building's roof planes, extruded tree masks and
neighbour footprints from SHD-04, and any exterior mesh the caller passes), then per
panel returns the components the PV chain (A4, SHD-03) needs separately:

* ``beam_shading_fraction`` f_b per hour (SHD-01), which also shades the circumsolar
  part of the Perez sky diffuse (SHD-03 design choice);
* ``diffuse_shading_factor`` S_d once per panel (SHD-02), for the isotropic and
  horizon parts of the sky diffuse;
* and, when plane-of-array components are given, the combined hourly factor
  1 - Epoa,sh / Epoa and the annual ``shading_loss_fraction`` (SHD-03, SHD-05).

Ground-reflected irradiance is not reduced (SHD-03). Panels are taken as flush with
their plane: they do not shade one another, so module rows are not part of the scene
(racked rows on flat roofs are LAY-02's analytic case, not cast here).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np
from shapely.ops import unary_union

from backend.schema import PanelPlacement, RoofPlane, VexcelDetection

from .geometry import (Origin, PlaneSurface, extrude_polygon_enu, geometry_to_enu, load_polygon,
                       merge_triangles, sample_grid, scale_about_centroid, sun_vectors)
from .raycast import beam_shading_fractions, sky_view_factors

# --- constants destined for backend/config.py (kept local, workplan 2.6) ---
DEFAULT_SHADING_LOSS = 0.03         # PV-04 / SHD intro: the 3 % PVWatts allowance where nothing is cast
SCREEN_LOSS_LIMIT = 0.20            # SHD-05 screening rule (GAG16 3.5, as translated in physics 01)
SAMPLE_GRID_N = 3                   # SHD-01: 3 by 3 sample points per module (K = 9)

POA_KEYS = ("poa_beam", "poa_sky_diffuse", "poa_ground")   # same names as A4's chain arguments
CIRC_KEY = "poa_sky_circumsolar"


@dataclass(frozen=True)
class Obstruction:
    """An opaque prism for SHD-04: a map polygon extruded from ``base_z_m`` by ``height_m``."""
    polygon_wkt: str
    height_m: float
    base_z_m: float = 0.0
    label: str = ""


@dataclass(frozen=True)
class PanelShading:
    """Shading of one panel. Hourly arrays have the length of the sun arrays.

    Pass ``beam_shading_fraction``, ``diffuse_shading_factor`` and the circumsolar
    component to A4 (``pv_hourly_yield``) only when ``ray_cast`` is True; otherwise keep
    A4's 3 % PV-04 allowance (``shading_loss_fraction`` then reports that 0.03).
    """
    plane_id: str
    panel_index: int
    ray_cast: bool
    beam_shading_fraction: np.ndarray           # f_b, SHD-01, 0..1, 0 at night / sun behind panel
    diffuse_shading_factor: float               # S_d, SHD-02, 1 = sky fully seen
    sky_view_factor: float                      # SVF of the obstructed panel, SHD-02
    shading_factor: Optional[np.ndarray] = None     # SHD-03 hourly 1 - Epoa,sh / Epoa (display)
    shading_loss_fraction: Optional[float] = None   # SHD-05
    poa_global_shaded: Optional[np.ndarray] = None  # SHD-03 Epoa,sh, W/m2
    sample_points_enu: Optional[np.ndarray] = None

    def pv_kwargs(self) -> dict:
        """Keyword arguments for A4's ``pv_hourly_yield`` (shading part only)."""
        if not self.ray_cast:
            return {}
        return {"beam_shading_fraction": self.beam_shading_fraction,
                "diffuse_shading_factor": self.diffuse_shading_factor}

    @property
    def screened_out(self) -> bool:
        """SHD-05 screening: a position losing more than 20 % is not used."""
        return self.shading_loss_fraction is not None and self.shading_loss_fraction > SCREEN_LOSS_LIMIT


@dataclass(frozen=True)
class ShadingResult:
    panels: tuple[PanelShading, ...]
    origin: Origin
    scene_triangles: int
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def placements(self, panels: Sequence[PanelPlacement]) -> list[PanelPlacement]:
        """Copies of the input placements with ``shading_loss_fraction`` filled where known."""
        out = []
        for p, s in zip(panels, self.panels):
            out.append(p if s.shading_loss_fraction is None
                       else p.model_copy(update={"shading_loss_fraction": s.shading_loss_fraction}))
        return out


# ---------------------------------------------------------------- SHD-03, SHD-05 arithmetic

def shaded_poa_components(poa_beam, poa_sky_diffuse, poa_ground, beam_shading_fraction,
                          diffuse_shading_factor, poa_sky_circumsolar=None) -> dict[str, np.ndarray]:
    """SHD-03 without the IAM term (PV-03's transmitted value stays with A4).

    Eb,sh = (1 - f_b) Eb; Ecirc,sh = (1 - f_b) Ecirc; (iso + horizon),sh = S_d (Ed - Ecirc); Eg,sh = Eg.
    Without a circumsolar component the whole sky diffuse takes S_d (SAM15 eq. 7.4).
    """
    eb = np.asarray(poa_beam, float)
    ed = np.asarray(poa_sky_diffuse, float)
    eg = np.asarray(poa_ground, float)
    fb = np.asarray(beam_shading_fraction, float)
    sd = np.asarray(diffuse_shading_factor, float)
    circ = np.zeros_like(ed) if poa_sky_circumsolar is None else np.asarray(poa_sky_circumsolar, float)
    poa = eb + ed + eg
    poa_sh = (1.0 - fb) * (eb + circ) + sd * (ed - circ) + eg
    with np.errstate(divide="ignore", invalid="ignore"):
        factor = np.where(poa > 0.0, 1.0 - poa_sh / np.where(poa > 0.0, poa, 1.0), 0.0)
    return {"poa_global": poa, "poa_global_shaded": poa_sh, "shading_factor": factor}


def annual_shading_loss(hourly_poa_unshaded, hourly_poa_shaded) -> float:
    """SHD-05. 1 - sum(Epoa,sh) / sum(Epoa); 0 when there is no irradiance at all."""
    tot = float(np.sum(hourly_poa_unshaded))
    if tot <= 0.0:
        return 0.0
    return float(1.0 - np.sum(hourly_poa_shaded) / tot)


# ---------------------------------------------------------------- SHD-04 inputs

def _is_tree(label: str) -> bool:
    return "tree" in label.lower()


def obstructions_from_detections(detections: Sequence[VexcelDetection], heights_m: Mapping[str, float],
                                 base_z_m: float = 0.0) -> tuple[list[Obstruction], list[str]]:
    """SHD-04. Tree (and any other labelled) masks to prisms, for labels with a height.

    ``heights_m`` maps a detection label (case-insensitive) to the prism's top height
    above its base; there is no default (SHD-04, physics 01 section 8): a label without
    a height is not cast, and a warning says so. The footprint is ``mask_wkt`` when
    present; otherwise ``bbox_wkt`` shrunk about its centroid to ``mask_area_m2`` (the
    box overstates a crown). Roof fragments (label "roof") are never cast. Overlapping
    (nested) masks of one label are merged first, so a fragment is not counted twice.
    """
    heights = {k.lower(): float(v) for k, v in heights_m.items()}
    warnings: list[str] = []
    by_label: dict[str, list] = {}
    missing: set[str] = set()
    for d in detections:
        lab = d.label.lower()
        if lab == "roof":
            continue
        if lab not in heights:
            if _is_tree(lab):
                missing.add(d.label)
            continue
        g = load_polygon(d.mask_wkt) or load_polygon(d.bbox_wkt)
        if g is None:
            continue
        if not d.mask_wkt and d.mask_area_m2:
            # area in m2 against a lon/lat box: shrink by the metric ratio
            c = g.centroid
            area_m = geometry_to_enu(g, (c.x, c.y)).area
            if area_m > d.mask_area_m2 > 0.0:
                g = scale_about_centroid(g, g.area * d.mask_area_m2 / area_m)
        by_label.setdefault(lab, []).append(g)
    for lab in sorted(missing):
        warnings.append(f"SHD-04: no height for '{lab}' masks; they are not ray cast "
                        "(their roof area is still excluded by ROOF-04)")
    out = []
    for lab in sorted(by_label):
        merged = unary_union(by_label[lab])
        out.append(Obstruction(merged.wkt, heights[lab], base_z_m, lab))
    return out, warnings


# ---------------------------------------------------------------- entry point

def _origin(planes: Sequence[RoofPlane]) -> Optional[Origin]:
    for pl in planes:
        g = load_polygon(pl.polygon_wkt)
        if g is not None:
            c = g.centroid
            return (c.x, c.y)
    return None


def shade_panels(planes: Sequence[RoofPlane], panels: Sequence[PanelPlacement],
                 sun_zenith_deg, sun_azimuth_deg, *,
                 poa_components: Optional[Mapping[str, Mapping[str, np.ndarray]]] = None,
                 detections: Sequence[VexcelDetection] = (),
                 obstruction_heights_m: Mapping[str, float] = {},
                 obstructions: Sequence[Obstruction] = (),
                 scene_triangles_enu: Optional[np.ndarray] = None,
                 eave_height_m: Optional[float] = None,
                 origin: Optional[Origin] = None,
                 n_el: int = 30, n_az: int = 120) -> ShadingResult:
    """Shading per panel and hour (SHD-01..05).

    Parameters
    ----------
    planes, panels : the model's ``RoofPlane`` list and the layout's ``PanelPlacement`` list.
    sun_zenith_deg, sun_azimuth_deg : hourly arrays (degrees; apparent zenith, azimuth
        clockwise from true north), as from SOL-01 at the SOL-07 instant.
    poa_components : per plane id, hourly ``poa_beam``, ``poa_sky_diffuse``, ``poa_ground``
        and optionally ``poa_sky_circumsolar`` (IRR-05, IRR-08, IRR-09; A4's names). Needed
        for the combined factor and ``shading_loss_fraction``; without them only f_b and
        S_d are returned.
    detections, obstruction_heights_m : Vexcel detections (the planes' own ``obstructions``
        are added) and a height per label (SHD-04; no default).
    obstructions : further prisms, e.g. neighbour footprints with an assumed height.
    scene_triangles_enu : exterior mesh (T, 3, 3) in this function's ENU frame (z = 0 at
        ground), e.g. from the aerial splat.
    eave_height_m : height of each plane's lowest edge above ground. Required when prisms
        standing on the ground are cast; otherwise 0.
    origin : (lon, lat) of the ENU frame; default the centroid of the first plane polygon.
    """
    zen = np.atleast_1d(np.asarray(sun_zenith_deg, float))
    azi = np.atleast_1d(np.asarray(sun_azimuth_deg, float))
    if zen.shape != azi.shape:
        raise ValueError("sun zenith and azimuth arrays must have the same shape")
    s = sun_vectors(zen, azi)
    warnings: list[str] = []
    planes_by_id = {p.id: p for p in planes}

    origin = origin or _origin(planes)
    obs = list(obstructions)
    all_dets = list(detections) + [d for p in planes for d in p.obstructions]
    seen, uniq = set(), []
    for d in all_dets:
        key = (d.label, d.bbox_wkt, d.mask_wkt)
        if key not in seen:
            seen.add(key)
            uniq.append(d)
    det_obs, w = obstructions_from_detections(uniq, obstruction_heights_m)
    obs += det_obs
    warnings += w
    if obs and eave_height_m is None:
        raise ValueError("eave_height_m is required when obstructions are ray cast")
    z_eave = 0.0 if eave_height_m is None else float(eave_height_m)

    # Scene
    surfaces: dict[str, PlaneSurface] = {}
    if origin is not None:
        for pl in planes:
            g = load_polygon(pl.polygon_wkt)
            if g is not None:
                surfaces[pl.id] = PlaneSurface(geometry_to_enu(g, origin), pl.tilt_deg.expected,
                                               pl.azimuth_deg, z_eave)
    parts = [surf.triangles() for surf in surfaces.values()]
    for o in obs:
        g = load_polygon(o.polygon_wkt)
        if g is not None and origin is not None:
            parts.append(extrude_polygon_enu(geometry_to_enu(g, origin), o.base_z_m, o.height_m))
    if scene_triangles_enu is not None:
        parts.append(np.asarray(scene_triangles_enu, float))
    scene = merge_triangles(parts)
    external = bool(obs) or (scene_triangles_enu is not None and len(scene_triangles_enu) > 0)

    results = []
    zeros = np.zeros(len(zen))
    for i, pp in enumerate(panels):
        pl = planes_by_id.get(pp.plane_id)
        if pl is None:
            raise ValueError(f"panel {i} refers to unknown plane '{pp.plane_id}'")
        surf = surfaces.get(pl.id)
        cast = surf is not None and (pl.geometry_source == "splat" or external)
        if not cast:
            warnings.append(f"SHD: panel {i} on '{pl.id}' ({pl.geometry_source}) has no geometry to "
                            f"cast against; PV-04 default {DEFAULT_SHADING_LOSS:.0%} kept")
            results.append(PanelShading(pl.id, i, False, zeros.copy(), 1.0, float("nan"),
                                        shading_loss_fraction=DEFAULT_SHADING_LOSS))
            continue
        footprint = load_polygon(pp.polygon_wkt)
        if footprint is None:
            footprint_enu = surf.footprint
            warnings.append(f"SHD-01: panel {i} has no drawn position; sampled over plane '{pl.id}'")
        else:
            footprint_enu = geometry_to_enu(footprint, origin)
        pts = surf.lift(sample_grid(footprint_enu, SAMPLE_GRID_N))
        n = surf.normal
        fb = beam_shading_fractions(pts, n, s, scene)
        centre = surf.lift(np.asarray(footprint_enu.centroid.coords)[0])
        svf, svf_open = sky_view_factors(centre, n, scene, n_el, n_az)
        # S_d as the ratio of the two quadratures on one grid: exactly 1 for an open sky,
        # and the grid's discretisation error cancels (SHD-02 prints SVF / closed form).
        sd = svf / svf_open if svf_open > 0.0 else 1.0
        factor = loss = poa_sh = None
        comps = (poa_components or {}).get(pl.id)
        if comps is not None:
            sh = shaded_poa_components(*(comps[k] for k in POA_KEYS), fb, sd, comps.get(CIRC_KEY))
            factor, poa_sh = sh["shading_factor"], sh["poa_global_shaded"]
            loss = annual_shading_loss(sh["poa_global"], poa_sh)
            if comps.get(CIRC_KEY) is None:
                warnings.append(f"SHD-03: no circumsolar component for '{pl.id}'; all sky diffuse "
                                "shaded with S_d (SAM15 rule)")
        results.append(PanelShading(pl.id, i, True, fb, float(sd), float(svf), factor, loss,
                                    poa_sh, pts))
    if poa_components is None and any(r.ray_cast for r in results):
        warnings.append("SHD-05: no plane-of-array components given; only f_b and S_d returned")
    # one warning per distinct text, in first-seen order
    warnings = list(dict.fromkeys(warnings))
    return ShadingResult(tuple(results), origin if origin is not None else (float("nan"), float("nan")),
                         int(len(scene)), tuple(warnings))

"""Helpers shared by the wall and window measures (A20): surface selection, anchors in the
3D tour, evidence and small range arithmetic. Contract types only; no sibling imports."""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence

from backend.schema import (Anchor, Assumption, BuildingModel, EvidenceRef, PropertyBundle,
                            Ranged, Surface)

# Boundaries through which a wall or window loses heat (physics 02 ENV-03): exterior, and
# a wall to an unconditioned space. Party walls and ground contact are not treated.
LOSS_BOUNDARIES = ("exterior", "adjacent_unconditioned")

# Anchor height when the opening's sill and height are unknown (vision windows, walls):
# about eye level, metres above the floor. A display choice, not physics.
DEFAULT_ANCHOR_Z_M = 1.5
MAX_ANCHORS = 6                       # one pin per treated wall edge, largest first

_HOME_USES = {"single_family", "multifamily_unit"}
_COMPASS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")
EPS = 1e-9


def is_home(bundle: PropertyBundle) -> bool:
    """Home flow (SPEC 6.2): single-family and multifamily units; otherwise the segment."""
    s = bundle.summary
    if s.use_type in _HOME_USES:
        return True
    if s.use_type == "office":
        return False
    return s.segment == "residential"


def compass(azimuth_deg: Optional[float]) -> str:
    if azimuth_deg is None:
        return "horizontal"
    return _COMPASS[int(((azimuth_deg % 360.0) + 22.5) // 45.0) % 8]


def facing_list(surfaces: Iterable[Surface]) -> str:
    """'south and west', ordered by glazed or wall area."""
    area: dict[str, float] = {}
    for s in surfaces:
        k = compass(s.azimuth_deg)
        area[k] = area.get(k, 0.0) + s.area_m2
    names = sorted(area, key=lambda k: -area[k])
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def loss_surfaces(model: BuildingModel, kind: str) -> list[Surface]:
    return [s for s in model.surfaces if s.kind == kind and s.boundary in LOSS_BOUNDARIES]


def assumption(model: BuildingModel, key: str) -> Optional[Assumption]:
    return next((a for a in model.assumptions if a.key == key), None)


def scale(r: Ranged, factor_low: float, factor_exp: float, factor_high: float) -> Ranged:
    """r with each end multiplied by its factor, re-ordered so low <= expected <= high."""
    lo, ex, hi = r.low * factor_low, r.expected * factor_exp, r.high * factor_high
    return Ranged(low=round(min(lo, ex, hi), 6), expected=round(ex, 6),
                  high=round(max(lo, ex, hi), 6), unit=r.unit)


def total_area(surfaces: Iterable[Surface]) -> float:
    return round(sum(s.area_m2 for s in surfaces), 2)


# ---------------------------------------------------------------- anchors

def _edge_index(bundle: PropertyBundle):
    edges, verts = {}, {}
    for f in bundle.matterport.floors:
        for v in f.vertices:
            verts[v.id] = (v.x, v.y)
        for e in f.edges:
            edges[e.id] = e
    return edges, verts


def _point_on_edge(edge, verts, opening=None):
    a, b = (verts.get(i) for i in edge.vertex_ids)
    if a is None or b is None:
        return None
    t = opening.relative_center if opening is not None and opening.relative_center is not None else 0.5
    return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])


def anchors_for(bundle: PropertyBundle, surfaces: Sequence[Surface], what: str) -> list[Anchor]:
    """One Anchor per treated wall edge, largest treated area first: the point on the edge
    (the opening's centre for a measured window), its room, and the nearest panorama."""
    edges, verts = _edge_index(bundle)
    by_edge: dict[str, list[Surface]] = {}
    for s in surfaces:
        by_edge.setdefault(s.source_edge_id or s.id, []).append(s)
    order = sorted(by_edge, key=lambda k: -sum(s.area_m2 for s in by_edge[k]))
    out: list[Anchor] = []
    for edge_id in order[:MAX_ANCHORS]:
        group = by_edge[edge_id]
        biggest = max(group, key=lambda s: s.area_m2)
        edge = edges.get(edge_id)
        room = next((r.id for r in bundle.matterport.rooms if edge_id in r.boundary_edge_ids), None)
        x = y = None
        z = DEFAULT_ANCHOR_Z_M
        if edge is not None:
            opening = next((o for o in edge.openings if o.id == biggest.source_opening_id), None)
            p = _point_on_edge(edge, verts, opening)
            if p is not None:
                x, y = round(p[0], 2), round(p[1], 2)
            if opening is not None and opening.lower_elevation_m is not None and opening.height_m:
                z = round(opening.lower_elevation_m + opening.height_m / 2.0, 2)
        pano = None
        if x is not None and bundle.matterport.panos:
            pano = min(bundle.matterport.panos, key=lambda p: math.hypot(p.x - x, p.y - y)).id
        n = len(group)
        label = f"{compass(biggest.azimuth_deg).capitalize()} {what}" + (f" ({n})" if n > 1 else "")
        out.append(Anchor(room_id=room, pano_id=pano, x=x, y=y, z=z if x is not None else None,
                          label=label))
    return out


# ---------------------------------------------------------------- evidence

def opening_evidence(surfaces: Sequence[Surface]) -> list[EvidenceRef]:
    ids = [s.source_opening_id for s in surfaces if s.source_opening_id]
    if not ids:
        return []
    return [EvidenceRef(kind="matterport_field", ref="floors.edges.openings",
                        note=", ".join(ids) if len(ids) <= 6 else f"{len(ids)} measured window openings")]


def assumption_evidence(model: BuildingModel, keys: Sequence[str]) -> list[EvidenceRef]:
    out: list[EvidenceRef] = []
    for k in keys:
        a = assumption(model, k)
        if a is None:
            continue
        for e in a.evidence:
            if e not in out:
                out.append(e)
    return out


def from_vision(surfaces: Sequence[Surface]) -> bool:
    return any(s.source_opening_id is None for s in surfaces)

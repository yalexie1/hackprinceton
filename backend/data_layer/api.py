"""Public door of the Data lane (workplan 3.1). The only module other lanes import.

D5 stub: every function replays the fixtures in `specs/examples/` behind the final
signatures. D1-D4 replace the bodies with live CoStar, Matterport, Vexcel and cache
code; the signatures stay. Nothing here touches the network.

Two deliberate choices, both from `specs/data-integration.md`:

- **No sid is hard-coded.** Example folders are discovered by scanning
  `specs/examples/` for any directory holding `property_summary.json`, and
  sid -> folder comes from reading those files. `specs/examples/office/` is being
  repointed at the Los Angeles office and an `office_houston/` folder follows, so
  anything keyed on a literal sid would break (noted by @yalexie1 on the board).
- **`search_properties` unions `search_results.json` with every folder's own
  summary**, deduped by sid. That keeps the golden properties findable while that
  file is mid-switch, and answers workplan R4: search works before `D7`, which only
  adds radius ranking on top.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend.schema import (
    PropertyBundle,
    PropertySummary,
    Segment,
    UseType,
    VexcelDetection,
)

_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES = _ROOT / "specs" / "examples"
_CACHE = _ROOT / "data" / "cache"

_EARTH_RADIUS_M = 6_371_000.0


# ---------- fixture discovery ----------

def _folders() -> list[Path]:
    """Every example folder that carries a property summary, sorted for determinism."""
    return sorted(p for p in _EXAMPLES.iterdir() if (p / "property_summary.json").is_file())


def _load(folder: Path, name: str):
    return json.loads((folder / name).read_text())


def _folder_for_sid(sid: str) -> Path:
    for folder in _folders():
        if _load(folder, "property_summary.json")["sid"] == sid:
            return folder
    raise LookupError(f"unknown sid: {sid}")


# ---------- door ----------

def search_properties(
    q: Optional[str] = None,
    segment: Optional[Segment] = None,
    use_type: Optional[UseType] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_m: Optional[float] = None,
    limit: int = 20,
) -> list[PropertySummary]:
    """Stage S1. Matches on name, address and city; `use_type="office"` means CoStar
    property type 5 once `D1` is live. Ordering is deterministic: golden properties
    first, in folder order, then the rest of `search_results.json` as written."""
    rows: list[dict] = []
    seen: set[str] = set()
    for folder in _folders():
        row = _load(folder, "property_summary.json")
        rows.append(row)
        seen.add(row["sid"])
    extra_path = _EXAMPLES / "search_results.json"
    if extra_path.is_file():
        for row in json.loads(extra_path.read_text()):
            if row["sid"] not in seen:
                rows.append(row)
                seen.add(row["sid"])

    out = [PropertySummary.model_validate(r) for r in rows]

    if q:
        needle = q.casefold()
        out = [
            s for s in out
            if needle in s.name.casefold()
            or needle in (s.address or "").casefold()
            or needle in (s.city or "").casefold()
        ]
    if segment is not None:
        out = [s for s in out if s.segment == segment]
    if use_type is not None:
        out = [s for s in out if s.use_type == use_type]
    if lat is not None and lon is not None and radius_m is not None:
        out = [s for s in out if _within(s, lat, lon, radius_m)]
    return out[: max(0, limit)]


def get_property_summary(sid: str) -> PropertySummary:
    """Stage S1, workplan R3. Answers `GET /api/properties/{sid}`."""
    return PropertySummary.model_validate(_load(_folder_for_sid(sid), "property_summary.json"))


def get_property_bundle(sid: str) -> PropertyBundle:
    """Stage S2. All three layers present, or an explicit `FetchRecord` in `provenance`
    saying what is missing and why (SPEC 14). Cached, so a second call is free."""
    return PropertyBundle.model_validate(_load(_folder_for_sid(sid), "property_bundle.json"))


def detect_roof_elements(sid: str, labels: Optional[list[str]] = None) -> list[VexcelDetection]:
    """Vexcel `elements/detect` with SAM 3; the live code is `D8`. Lives in this lane
    because it is a network call and SPEC 14 requires analysis to run without one.

    `specs/data-integration.md` 4.4 measured the label quality: use `"roof"`, not
    `"roof plane"`, which returns nothing, and a detection threshold near 0.3 rather
    than the quickstart's 0.5. Roof obstruction counts should come from the Vexcel
    precomputed `roof-objects` attributes, not from these masks.
    """
    bundle = get_property_bundle(sid)
    found = list(bundle.vexcel.detections) if bundle.vexcel else []
    if labels is not None:
        wanted = {l.casefold() for l in labels}
        found = [d for d in found if d.label.casefold() in wanted]
    return found


def get_asset(path: str) -> bytes:
    """Return cached bytes for a path as stored in a bundle (`face_paths`,
    `ortho_path`, `weather_path`, ...).

    Never returns or stores a URL: signed Matterport and CoStar links expire, so the
    live version re-queries for a fresh link and returns the bytes. Any path outside
    the cache directory is refused.

    The stub has no fetch-on-miss, so a path inside the cache that is not present
    raises `FileNotFoundError` - the server should answer that with 404.
    """
    target = (_ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    cache = _CACHE.resolve()
    if not target.is_relative_to(cache):
        raise ValueError(f"path outside the cache directory: {path}")
    if not target.is_file():
        raise FileNotFoundError(f"not cached: {path}")
    return target.read_bytes()


# ---------- helpers ----------

def _within(summary: PropertySummary, lat: float, lon: float, radius_m: float) -> bool:
    if summary.lat is None or summary.lon is None:
        return False
    from math import asin, cos, radians, sin, sqrt

    dlat = radians(summary.lat - lat)
    dlon = radians(summary.lon - lon)
    h = sin(dlat / 2) ** 2 + cos(radians(lat)) * cos(radians(summary.lat)) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * asin(sqrt(h)) <= radius_m

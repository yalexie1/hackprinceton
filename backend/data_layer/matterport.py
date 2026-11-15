"""Matterport Model API client (package D2).

Every rule here is a verified finding from `specs/data-integration.md` section 3:

- `POST /api/models/graph`, GraphQL, HTTP basic auth with the key as user and the
  token as password. **Production only, and the keys are shared across every team**,
  so this client rate-limits itself well under the documented 10 requests/second.
- **No mutation is ever called.** The schema exposes `patchModelGeoCoordinates`,
  `removeEdgeOpenings` and others against live sponsor data; a test asserts this
  module contains none of them.
- **Null fields are omitted, not sent as null**, so every read tolerates absence.
- **A GraphQL response can carry `errors` *and* usable `data` at the same time.**
  Verified 2026-11-14: asking for the defurnished view on a model that has none
  answers `{"errors": [...path: ["model","view"], code: not.found...],
  "data": {"model": {...fully populated..., "view": null}}}`. Treating any `errors`
  as fatal throws away a complete response, so this client fails only when
  `data.model` is unusable and turns field-scoped errors into `FetchRecord`s.
- **Signed asset URLs expire.** Nothing here returns or stores one. Asset fields
  carry deterministic *cache* paths; whatever downloads the bytes re-queries for a
  fresh link at that moment and never persists it.
- `geocoordinates` gives the georeference directly, including a `rotation`
  quaternion whose z may be either sign, and a `source` of `client`, `processing`
  or `unknown`. `altitude` is **unusable** (0.0 on one model and 29.6 on another in
  the same building), so it is carried through but never relied on.
- Room `classifications` are populated on residential scans and empty on commercial
  ones, and `areaFloor` can contradict `width`x`depth` outright, so `area_m2` is
  trusted over the two.
- MatterPak `availability: unlocked` does **not** mean the files exist: the golden
  house reports unlocked with all three resources `unavailable`.
"""
from __future__ import annotations

import os
import time
from typing import Callable, Optional

from backend.schema import (
    FetchRecord,
    Floor,
    FloorplanAsset,
    GeoReference,
    MatterportData,
    Opening,
    Pano,
    Quaternion,
    Room,
    Vertex,
    WallEdge,
)

from . import cache

ENDPOINT = "https://api.matterport.com/api/models/graph"

#: Documented ceiling is 10 requests/second on keys shared with every other team,
#: so the client holds itself to a quarter of that.
MIN_INTERVAL_S = 0.25

_last_call = 0.0

#: A poster returns the whole GraphQL body, `{"data": ..., "errors": ...}`, because
#: field-scoped errors have to be inspected rather than raised on.
Poster = Callable[[str, dict], dict]


class MatterportAuthMissing(RuntimeError):
    """No usable key set in the environment."""


# ---------- transport ----------

def credentials(key_set: str = "") -> tuple[str, str]:
    """`MATTERPORT_API_KEY`/`_TOKEN`, optionally suffixed `_B` or `_C`.

    Set `_D` is invalid (HTTP 403 `invalid key/secret`) and is never a default.
    """
    suffix = f"_{key_set.upper().lstrip('_')}" if key_set else ""
    key = os.environ.get(f"MATTERPORT_API_KEY{suffix}")
    token = os.environ.get(f"MATTERPORT_API_TOKEN{suffix}")
    if not key or not token:
        raise MatterportAuthMissing(
            f"MATTERPORT_API_KEY{suffix} and MATTERPORT_API_TOKEN{suffix} must be set"
        )
    return key, token


def _throttle() -> None:
    global _last_call
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _default_post(query: str, variables: dict) -> dict:
    import httpx  # imported lazily so offline tests need no transport

    _throttle()
    key, token = credentials(os.environ.get("MATTERPORT_KEY_SET", ""))
    resp = httpx.post(
        ENDPOINT,
        json={"query": query, "variables": variables},
        auth=(key, token),
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


# ---------- the query ----------

MODEL_QUERY = """
query Model($id: ID!) {
  model(id: $id) {
    id
    name
    geocoordinates { latitude longitude altitude source
                     rotation { x y z w } translation { x y z } }
    floors { id label
             vertices { id position { x y } }
             edges { id type thickness vertices { id }
                     openings { id type label width height lowerElevation relativeCenter } } }
    rooms { id floor { id }
            classifications { label confidence }
            boundary { edges { id } }
            dimensions(units: metric) { areaFloor width depth height } }
    panoLocations { id label position { x y z } }
    assets { floorplans(provider: "matterport") { format flags width height resolution
                                                  origin { x y } } }
    bundle(id: "mp:matterpak") { availability }
    view(type: "matterport.model.defurnished") { id }
  }
}
"""


PANO_FACES_QUERY = """
query PanoFaces($id: ID!) {
  model(id: $id) {
    locations { id panos { id skyboxes(resolutions: ["2k"]) { resolution status children } } }
  }
}
"""


def download_face(url: str) -> bytes:
    """One signed face URL to bytes."""
    import httpx  # imported lazily so offline tests need no transport

    resp = httpx.get(url, timeout=60.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def pano_face_urls(sid: str, *, post: Optional[Poster] = None) -> dict[str, list[str]]:
    """Fresh, expiring download URLs of the six 2k cube faces of every panorama, by pano id, in the
    API's order (up, four sides, down). The URLs are signed and short-lived: use them at once and
    never store them. A panorama with no available 2k skybox is left out."""
    body = (post or _default_post)(PANO_FACES_QUERY, {"id": sid})
    if body.get("errors") and not (body.get("data") or {}).get("model"):
        raise LookupError(f"Matterport refused the panorama query: {str(body['errors'])[:200]}")
    out: dict[str, list[str]] = {}
    for loc in ((body.get("data") or {}).get("model") or {}).get("locations") or []:
        for pano in loc.get("panos") or []:
            for sky in pano.get("skyboxes") or []:
                kids = sky.get("children") or []
                if sky.get("status") == "available" and sky.get("resolution") == "2k" and len(kids) == 6:
                    out[pano["id"]] = list(kids)
    return out


# ---------- cache paths (never URLs) ----------

def cache_root(sid: str) -> str:
    return f"data/cache/{sid}"


def pano_face_paths(sid: str, pano_id: str, defurnished: bool = False) -> list[str]:
    """Six cube faces in the API's order: up, four sides, down."""
    mid = "defurnished/panos" if defurnished else "panos"
    return [f"{cache_root(sid)}/{mid}/{pano_id}/face{i}.jpg" for i in range(6)]


def floorplan_path(sid: str, floor_label: str, fmt: str) -> str:
    slug = "".join(c if c.isalnum() else "_" for c in floor_label.lower()).strip("_") or "floor"
    return f"{cache_root(sid)}/floorplans/{slug}.{fmt.lower()}"


# ---------- mapping ----------

def _georeference(raw: Optional[dict]) -> Optional[GeoReference]:
    if not raw or raw.get("latitude") is None or raw.get("longitude") is None:
        return None
    rot = raw.get("rotation") or {}
    if not all(k in rot for k in "xyzw"):
        return None
    tr = raw.get("translation")
    return GeoReference(
        latitude=raw["latitude"],
        longitude=raw["longitude"],
        # Carried through, never relied on: measured 0.0 on one model and 29.6 on
        # another in the same building.
        altitude_m=raw.get("altitude"),
        rotation=Quaternion(**{k: rot[k] for k in "xyzw"}),
        translation=(tr["x"], tr["y"], tr["z"]) if tr else None,
        source=raw.get("source"),
    )


def _openings(raw_edge: dict) -> list[Opening]:
    out = []
    for o in raw_edge.get("openings") or []:
        rc = o.get("relativeCenter")
        out.append(Opening(
            id=o["id"],
            type=o.get("type") or "opening",
            label=o.get("label"),
            width_m=o.get("width"),
            height_m=o.get("height"),
            lower_elevation_m=o.get("lowerElevation"),
            # A fraction of the edge length in [0, 1], not metres. Proven on 41 real
            # openings: every one fits inside its wall as a fraction, 11 of 41 are
            # geometrically impossible read as metres.
            relative_center=min(1.0, max(0.0, rc)) if isinstance(rc, (int, float)) else None,
        ))
    return out


def _floors(raw: list[dict]) -> list[Floor]:
    floors = []
    for f in raw or []:
        edges = []
        for e in f.get("edges") or []:
            vids = [v["id"] for v in (e.get("vertices") or [])]
            if len(vids) < 2:
                continue  # an edge without both ends cannot be placed
            edges.append(WallEdge(
                id=e["id"],
                type=e.get("type") or "wall",
                thickness_m=e.get("thickness"),
                vertex_ids=(vids[0], vids[1]),
                openings=_openings(e),
            ))
        floors.append(Floor(
            id=f["id"],
            label=f.get("label") or f["id"],
            vertices=[
                Vertex(id=v["id"], x=v["position"]["x"], y=v["position"]["y"])
                for v in (f.get("vertices") or []) if v.get("position")
            ],
            edges=edges,
        ))
    return floors


def _rooms(raw: list[dict]) -> list[Room]:
    rooms = []
    for r in raw or []:
        cls = (r.get("classifications") or [])
        dims = r.get("dimensions") or {}
        best = max(cls, key=lambda c: c.get("confidence") or 0.0) if cls else {}
        rooms.append(Room(
            id=r["id"],
            floor_id=(r.get("floor") or {}).get("id") or "",
            # Empty on every commercial model sampled; populated on residential ones.
            label=best.get("label"),
            label_confidence=best.get("confidence"),
            # Trusted over width x depth, which can contradict it outright.
            area_m2=dims.get("areaFloor"),
            width_m=dims.get("width"),
            depth_m=dims.get("depth"),
            height_m=dims.get("height"),
            boundary_edge_ids=[e["id"] for e in ((r.get("boundary") or {}).get("edges") or [])],
        ))
    return rooms


def _panos(sid: str, raw: list[dict], defurnished: bool) -> list[Pano]:
    out = []
    for p in raw or []:
        pos = p.get("position") or {}
        out.append(Pano(
            id=p["id"],
            label=p.get("label"),
            x=pos.get("x", 0.0), y=pos.get("y", 0.0), z=pos.get("z", 0.0),
            face_paths=pano_face_paths(sid, p["id"]),
            defurnished_face_paths=pano_face_paths(sid, p["id"], True) if defurnished else [],
        ))
    return out


def _floorplans(sid: str, raw: list[dict]) -> list[FloorplanAsset]:
    out = []
    for i, fp in enumerate(raw or []):
        fmt = (fp.get("format") or "png").lower()
        origin = fp.get("origin") or {}
        out.append(FloorplanAsset(
            format=fmt,
            flags=list(fp.get("flags") or []),
            path=floorplan_path(sid, f"floor_{i + 1}", fmt),
            resolution_px_per_m=fp.get("resolution"),
            origin_x=origin.get("x"),
            origin_y=origin.get("y"),
        ))
    return out


def get_matterport_data(sid: str, *, post: Optional[Poster] = None) -> MatterportData:
    """One model as `MatterportData`. `post` is injectable so tests run offline."""
    return get_matterport_data_with_notes(sid, post=post)[0]


def _notes(errors: list[dict]) -> list[FetchRecord]:
    """Field-scoped GraphQL errors become provenance, not exceptions.

    A `not.found` on an optional field is a normal outcome - the commonest is
    `["model", "view"]` on a model with no defurnished view - so it is recorded as
    `missing` rather than `error`.
    """
    out = []
    for e in errors or []:
        path = ".".join(str(p) for p in (e.get("path") or [])) or "model"
        code = (e.get("extensions") or {}).get("code") or ""
        out.append(FetchRecord(
            layer="matterport",
            what=path,
            status="missing" if code == "not.found" else "error",
            detail=e.get("message"),
        ))
    return out


#: The query shape that goes into the cache key. The document text itself, hashed:
#: adding a field to `MODEL_QUERY` must not serve a caller the older, narrower
#: response, which is the Vexcel `include=` trap in a different costume.
def _query_shape() -> dict:
    import hashlib

    return {"document": hashlib.sha256(MODEL_QUERY.encode()).hexdigest()[:12]}


def get_matterport_data_with_notes(
    sid: str, *, post: Optional[Poster] = None, refresh: bool = False
) -> tuple[MatterportData, list[FetchRecord]]:
    """As `get_matterport_data`, plus a `FetchRecord` for every field-scoped error.

    Raises `LookupError` only when `data.model` is unusable; a response carrying both
    `errors` and a populated model is a success with notes.

    The response is cached by D4 when the default transport is used, so re-assembling
    a bundle does not re-query a key shared with every other team. **An injected
    `post` bypasses the cache entirely** - a caller supplying the response is in
    control of what comes back, and a stubbed response has no business being left on
    disk for the next caller to find.
    """
    body, from_cache = cache.cached_json(
        "matterport", sid,
        lambda: (post or _default_post)(MODEL_QUERY, {"id": sid}) or {},
        _query_shape(),
        use_cache=post is None,
        refresh=refresh,
    )
    body = body or {}
    model = (body.get("data") or {}).get("model")
    errors = body.get("errors") or []
    if not model:
        detail = f": {errors}" if errors else ""
        raise LookupError(f"no Matterport model: {sid}{detail}")

    defurnished_id = (model.get("view") or {}).get("id")
    bundle = model.get("bundle") or {}
    notes = _notes(errors)
    if post is None:
        notes.append(cache.cache_note("matterport", f"model:{sid}", hit=from_cache))
    return MatterportData(
        georeference=_georeference(model.get("geocoordinates")),
        floors=_floors(model.get("floors")),
        rooms=_rooms(model.get("rooms")),
        panos=_panos(sid, model.get("panoLocations"), bool(defurnished_id)),
        floorplans=_floorplans(sid, (model.get("assets") or {}).get("floorplans")),
        # "unlocked" is not "available": the golden house reports unlocked with all
        # three resources unavailable, so mesh and point cloud stay None until a
        # resource is actually fetched (D12).
        matterpak_available=bundle.get("availability") == "unlocked",
        defurnished_view_id=defurnished_id,
    ), notes

"""SPEC 8 rule 5: the five fallbacks the auditor decides and logs. Pure: it reads a bundle
and returns the fallback events, so the decision is testable without a model."""
from __future__ import annotations

from backend.schema import PropertyBundle, RunEvent


def _has_window_openings(bundle: PropertyBundle) -> bool:
    return any(o.type == "window" for f in bundle.matterport.floors
               for e in f.edges for o in e.openings)


def detect_fallbacks(bundle: PropertyBundle) -> list[RunEvent]:
    mp = bundle.matterport
    found: list[tuple[str, str, str]] = []   # (key, stage, message)
    if not mp.splat_path:
        found.append(("no_splat", "ingest", "No splat: use the Vexcel roof."))
    if not mp.matterpak_available:
        found.append(("matterpak_locked", "ingest", "MatterPak locked: use the wall graph."))
    if bundle.costar is None:
        found.append(("no_costar", "ingest",
                      "No CoStar record: use the Vexcel building type and a wider vintage range."))
    if mp.georeference is None:
        found.append(("no_georeference", "model",
                      "No georeference: register the floor outline to the Vexcel footprint."))
    if not _has_window_openings(bundle):
        found.append(("no_window_openings", "model",
                      "No window openings in the wall graph: use window sizes read by vision."))
    return [RunEvent(type="fallback", stage=stage, message=msg, payload={"fallback": key})
            for key, stage, msg in found]


# The data lane's own account of what it could not get. `missing` and `locked` stay out: a layer
# that does not exist for a property is not a degraded run, and the model is told about it through
# the bundle itself. `fallback` and `error` mean a number in the result rests on a substitute.
_REPORTED = ("fallback", "error")


def provenance_fallbacks(bundle: PropertyBundle) -> list[RunEvent]:
    """Every `FetchRecord` the data lane marked `fallback` or `error`, as a run event.

    The bundle has carried these all along and nothing surfaced them, so a run could quietly rest
    on a state average tariff or three obliques out of four. Pure, like `detect_fallbacks`, so the
    live runtime and the replay path can both use it and agree.
    """
    out = []
    for record in bundle.provenance:
        if record.status not in _REPORTED:
            continue
        detail = f": {record.detail}" if record.detail else ""
        out.append(RunEvent(
            type="fallback", stage="ingest",
            message=f"{record.layer} {record.what} ({record.status}){detail}",
            payload={"fallback": f"provenance:{record.layer}", "layer": record.layer,
                     "what": record.what, "status": record.status, "detail": record.detail}))
    return out


def provenance_warnings(bundle: PropertyBundle) -> list[str]:
    """One line per reported `FetchRecord`, for `RunResult.warnings`."""
    return [event.message for event in provenance_fallbacks(bundle)]

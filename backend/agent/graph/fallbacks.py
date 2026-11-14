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

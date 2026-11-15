"""The adapter must carry BDG2's building into the bundle, and nothing else.

Both of these were real defects found by @vinayak-sinha's independent audit:
the golden example's CoStar block and Vexcel roof rode along into every eval
building, and an unsupported climate_zone fell back silently.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from backend.evals.run_eval import effective_climate_zone, scaled_bundle

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = json.loads((ROOT / "specs/examples/office/property_bundle.json").read_text())
SITE = {"state": "NY", "tz": "US/Eastern", "zone": "6A"}
ROW = SimpleNamespace(building_id="Cockatoo_office_Z", site_id="Cockatoo", sqm=5000.0,
                      yearbuilt=1985, lat=42.46, lng=-76.49,
                      primaryspaceusage="Office", numberoffloors=3)


def test_no_costar_value_from_the_example_survives():
    # The Culver office's leasing record says nothing about a building in Ithaca.
    # `kind` is the one field that legitimately carries over (commercial vs
    # residential); everything else must be ours or empty.
    b = scaled_bundle(GOLDEN, ROW, SITE, "bdg2temp")
    costar = b.get("costar") or {}
    golden = GOLDEN["costar"]
    for key, value in costar.items():
        if key == "kind" or value in (None, {}, []):
            continue
        assert value != golden.get(key), f"{key} leaked from the example"
    assert costar["raw"] == {}
    assert costar["record_id"].startswith("BDG2:")


def test_storeys_come_from_bdg2_not_from_the_example():
    # costar.stories is consumed by build_geometry(building_stories=...), so an
    # inherited 4 made every commercial eval building four storeys tall.
    b = scaled_bundle(GOLDEN, ROW, SITE, "bdg2temp")
    assert (b.get("costar") or {}).get("stories") == 3


def test_a_building_with_no_floor_count_does_not_inherit_the_examples():
    row = SimpleNamespace(**{**ROW.__dict__, "numberoffloors": float("nan")})
    b = scaled_bundle(GOLDEN, row, SITE, "bdg2temp")
    assert (b.get("costar") or {}).get("stories") is None


def test_the_example_vexcel_roof_is_dropped():
    # BDG2 carries no roof geometry, so keeping Culver's roof planes would be
    # inventing evidence; PV is out of scope for this eval anyway.
    b = scaled_bundle(GOLDEN, ROW, SITE, "bdg2temp")
    assert b.get("vexcel") is None


def test_year_built_comes_from_bdg2():
    b = scaled_bundle(GOLDEN, ROW, SITE, "bdg2temp")
    assert (b.get("costar") or {}).get("year_built") == 1985


def test_effective_climate_zone_reports_a_supported_zone_as_stated():
    assert effective_climate_zone("2A") == ("2A", "stated")
    assert effective_climate_zone("3B") == ("3B", "stated")


def test_effective_climate_zone_reports_an_unsupported_zone_as_a_fallback():
    # tables.CLIMATES is ("2A", "3B"); registry blends or defaults anything else.
    # The eval must say so per building rather than implying 6A was honoured.
    for zone in ("3C", "6A", "2B", "4A"):
        effective, source = effective_climate_zone(zone)
        assert source == "unsupported_fallback", zone
        assert effective != zone


def test_the_bundle_records_which_zone_was_actually_in_force():
    b = scaled_bundle(GOLDEN, ROW, SITE, "bdg2temp")
    assert b["climate"]["climate_zone"] == "6A"
    assert b["_eval"]["stated_climate_zone"] == "6A"
    assert b["_eval"]["zone_source"] == "unsupported_fallback"


def test_an_unsupported_zone_is_refused_not_silently_run(monkeypatch):
    # Lead decision (@yalexie1, board 2026-11-15): abstain on zones the DEF tables
    # do not carry, rather than running them on a 3B/2A blend and reporting the
    # number as if the stated zone had been honoured.
    import backend.evals.run_eval as run_eval
    assert run_eval.zone_is_supported("2A") is True
    assert run_eval.zone_is_supported("3B") is True
    for zone in ("3C", "6A", "2B", "4A", None):
        assert run_eval.zone_is_supported(zone) is False, zone

"""Tests for package D1 (the CoStar kit reader).

Two sets. The first builds a **synthetic mini-kit** in `tmp_path`, so every code
path is exercised offline without the real 404 MB mirror. The second runs only
when the real kit is present and asserts the values verified live on
2026-11-14 and recorded in `specs/data-integration.md`.
"""
from __future__ import annotations

import json

import pytest

from backend.data_layer import costar
from backend.schema import CostarData

ENUMS = {
    "PropertyType": {"0": "Unknown", "2": "Industrial", "5": "Office", "11": "Multifamily"},
    "BuildingClass": {"0": "Unknown", "1": "A", "2": "B", "3": "C", "4": "F"},
    "ConstructionEventType": {"1": "GroundBreaking", "2": "ConstructionComplete",
                              "3": "RenovationBegun", "4": "RenovationFinished"},
    "ListingPropertyType": {"0": "None", "1": "Detached", "2": "Townhouse"},
}


@pytest.fixture
def kit(tmp_path, monkeypatch):
    """A miniature kit with the same shape as the real one."""
    (tmp_path / "data").mkdir()
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "enums.json").write_text(json.dumps(ENUMS))

    # dirty city/state casing on purpose, plus an empty-model row that must be skipped
    (tmp_path / "commercial-properties.csv").write_text(
        "PropertyId,MatterportModelId,Address,City,State\n"
        "500,OFFICEMODEL1,1 Tower St,LOS ANGELES,California\n"
        "500,OFFICEMODEL2,1 Tower St,LOS ANGELES,California\n"
        "501,WAREHOUSEMOD,2 Shed Rd,houston,Tx\n"
        "502,,3 NoModel Ave,Houston,TX\n"
    )
    (tmp_path / "residential-listings.csv").write_text(
        "ListingId,ResidentialListingId,MatterportModelId,Address,City,State\n"
        "900,901,HOUSEMODEL1,4 Home Ln,Los Angeles,CA\n"
    )
    (tmp_path / "data" / "commercial-property.jsonl").write_text(
        json.dumps({
            "id": 500, "propertyType": 5, "buildingClass": 1, "constructionStatus": 1,
            "grossBuildingAreaSquareFeet": 10000.0, "rentableBuildingAreaSquareFeet": 9000.0,
            "numStoriesAboveGrade": 17, "isOwnerOccupied": False,
            "constructionEvents": [{"eventType": 1, "year": 1987},
                                   {"eventType": 2, "year": 1989},
                                   {"eventType": 4, "year": 2005}],
        }) + "\n" + json.dumps({
            "id": 501, "propertyType": 2, "buildingClass": 3,
            "grossBuildingAreaSquareFeet": 13320.0,
            "constructionEvents": [{"eventType": 2, "year": 1984}],
        }) + "\n"
    )
    (tmp_path / "data" / "residential-listings.jsonl").write_text(
        json.dumps({
            "id": 900, "property": {
                "yearBuilt": 1920, "sqftMin": 1628, "sqftMax": 1628, "stories": 1,
                "propertyType": 1, "listingPropertyType": 1,
                "mlsPropertyType": "Residential Single-Family, Single Family Residence",
            },
        }) + "\n"
    )
    monkeypatch.setenv("COSTAR_KIT_DIR", str(tmp_path))
    costar.enums.cache_clear()
    costar.rows_by_model.cache_clear()
    yield tmp_path
    costar.enums.cache_clear()
    costar.rows_by_model.cache_clear()


# ---------- synthetic kit ----------

def test_missing_kit_raises_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("COSTAR_KIT_DIR", str(tmp_path / "nope"))
    costar.rows_by_model.cache_clear()
    with pytest.raises(costar.KitMissing) as e:
        costar.rows_by_model()
    assert "git-ignored" in str(e.value)
    costar.rows_by_model.cache_clear()


def test_index_skips_rows_with_no_model_and_normalises(kit):
    idx = costar.index_by_model()
    assert set(idx) == {"OFFICEMODEL1", "OFFICEMODEL2", "WAREHOUSEMOD", "HOUSEMODEL1"}
    assert idx["OFFICEMODEL1"]["city"] == "Los Angeles"      # from LOS ANGELES
    assert idx["OFFICEMODEL1"]["state"] == "CA"              # from California
    assert idx["WAREHOUSEMOD"]["city"] == "Houston"          # from houston
    assert idx["WAREHOUSEMOD"]["state"] == "TX"              # from Tx


def test_several_models_on_one_property(kit):
    assert costar.models_for_property("500") == ["OFFICEMODEL1", "OFFICEMODEL2"]


def test_commercial_mapping(kit):
    d = costar.get_costar_data("OFFICEMODEL1")
    CostarData.model_validate(d.model_dump(mode="json"))
    assert d.kind == "commercial_property" and d.property_id == "500" and d.record_id == "500"
    assert d.property_type == "Office" and d.property_type_code == 5
    assert d.building_class == "A" and d.stories == 17
    # yearBuilt comes from constructionEvents, preferring ConstructionComplete
    assert d.year_built == 1989 and d.year_built_event == "ConstructionComplete"
    assert d.year_renovated == 2005
    # GBA for the envelope, RBA kept separate
    assert d.building_area_m2 == pytest.approx(10000 * costar.SQFT_TO_M2)
    assert d.rentable_area_m2 == pytest.approx(9000 * costar.SQFT_TO_M2)
    assert d.building_area_m2 != d.rentable_area_m2
    assert d.owner_name is None


def test_office_selector_is_property_type_5(kit):
    assert costar.is_office(costar.get_costar_data("OFFICEMODEL1").raw) is True
    warehouse = costar.get_costar_data("WAREHOUSEMOD")
    assert costar.is_office(warehouse.raw) is False
    assert warehouse.property_type == "Industrial" and warehouse.property_type_code == 2


def test_residential_mapping(kit):
    d = costar.get_costar_data("HOUSEMODEL1")
    CostarData.model_validate(d.model_dump(mode="json"))
    assert d.kind == "residential_listing"
    assert d.listing_id == "900" and d.residential_listing_id == "901"
    # residential yearBuilt IS a scalar, unlike commercial
    assert d.year_built == 1920 and d.year_built_event == "yearBuilt"
    assert d.building_area_m2 == pytest.approx(1628 * costar.SQFT_TO_M2)
    # listingPropertyType, not the ambiguous property.propertyType
    assert d.property_type == "Detached" and d.property_type_code == 1


def test_unknown_model_and_dangling_record_raise_lookuperror(kit):
    with pytest.raises(LookupError):
        costar.get_costar_data("NOSUCHMODEL")
    # a CSV row pointing at a record the dataset does not hold
    (kit / "commercial-properties.csv").write_text(
        "PropertyId,MatterportModelId,Address,City,State\n999,DANGLING,x,Houston,TX\n"
    )
    costar.rows_by_model.cache_clear()
    with pytest.raises(LookupError):
        costar.get_costar_data("DANGLING")


def test_multi_parent_commercial_keeps_every_row(kit):
    """A model attached to several PropertyIds must not lose the alternatives."""
    (kit / "commercial-properties.csv").write_text(
        "PropertyId,MatterportModelId,Address,City,State\n"
        "500,SHARED,1 Park Dr,Houston,TX\n"
        "501,SHARED,1 Park Dr,Houston,TX\n"
    )
    costar.rows_by_model.cache_clear()
    assert costar.parents_for_model("SHARED") == ["500", "501"]
    # primary is the first row in CSV order whose record exists
    assert costar.get_costar_data("SHARED").property_id == "500"


def test_commercial_primary_skips_a_dangling_first_row(kit):
    (kit / "commercial-properties.csv").write_text(
        "PropertyId,MatterportModelId,Address,City,State\n"
        "99999,SHARED,1 Park Dr,Houston,TX\n"
        "500,SHARED,1 Park Dr,Houston,TX\n"
    )
    costar.rows_by_model.cache_clear()
    d = costar.get_costar_data("SHARED")
    assert d.property_id == "500" and d.property_type == "Office"


def test_residential_primary_is_the_latest_listing(kit):
    """A home listed more than once resolves to its most recent marketing."""
    (kit / "residential-listings.csv").write_text(
        "ListingId,ResidentialListingId,MatterportModelId,Address,City,State\n"
        "900,901,HOUSEMODEL1,4 Home Ln,Los Angeles,CA\n"
        "902,901,HOUSEMODEL1,4 Home Ln,Los Angeles,CA\n"
    )
    (kit / "data" / "residential-listings.jsonl").write_text(
        json.dumps({"id": 900, "listDate": "2024-01-01T00:00:00+00:00",
                    "property": {"yearBuilt": 1920, "sqftMin": 1628, "sqftMax": 1628,
                                 "listingPropertyType": 1}}) + "\n"
        + json.dumps({"id": 902, "listDate": "2026-06-01T00:00:00+00:00",
                      "property": {"yearBuilt": 1920, "sqftMin": 1700, "sqftMax": 1700,
                                   "listingPropertyType": 1}}) + "\n"
    )
    costar.rows_by_model.cache_clear()
    assert costar.parents_for_model("HOUSEMODEL1") == ["900", "902"]
    d = costar.get_costar_data("HOUSEMODEL1")
    assert d.listing_id == "902"
    assert d.building_area_m2 == pytest.approx(1700 * costar.SQFT_TO_M2)


def test_state_normalisation_rejects_other_states(kit):
    assert costar.normalise_state("NY") is None     # contract allows only CA and TX
    assert costar.normalise_state("  ") is None
    assert costar.normalise_city("") is None


# ---------- the real kit, when it is mirrored ----------

def _have_kit() -> bool:
    try:
        costar.kit_dir()
        return True
    except costar.KitMissing:
        return False


live = pytest.mark.skipif(not _have_kit(), reason="CoStar kit mirror not present (git-ignored)")


@live
def test_live_counts_match_the_spec():
    costar.rows_by_model.cache_clear()
    rows = costar.rows_by_model()
    total = sum(len(v) for v in rows.values())
    # 13,147 commercial rows (51 with no model) + 2,224 residential (1 with no model)
    assert total == 13_147 - 51 + 2_224 - 1
    # a model id is not unique to one parent: 387 rows are second-or-later ones
    assert len(rows) == total - 387
    ambiguous = {s: v for s, v in rows.items() if len({p for p in costar.parents_for_model(s)}) > 1}
    assert len(ambiguous) == 307


@live
@pytest.mark.parametrize(
    "sid,pid,ptype,cls,year,stories",
    [("jfiEvosX974", "246899", "Office", "A", 1989, 17),    # LA golden office
     ("L3266YcPPvd", "234088", "Office", "A", 1974, 16)],   # Houston golden office
)
def test_live_golden_offices(sid, pid, ptype, cls, year, stories):
    costar.rows_by_model.cache_clear()
    d = costar.get_costar_data(sid)
    assert (d.property_id, d.property_type, d.building_class) == (pid, ptype, cls)
    assert d.year_built == year and d.year_built_event == "ConstructionComplete"
    assert d.stories == stories
    assert costar.is_office(d.raw)


@live
def test_live_golden_house():
    costar.rows_by_model.cache_clear()
    d = costar.get_costar_data("zvKHR9DHNjJ")
    assert d.kind == "residential_listing"
    assert (d.listing_id, d.residential_listing_id) == ("235967170", "221139020")
    assert d.year_built == 1920
    assert d.property_type == "Detached"

"""A31 BEN-01 to BEN-03: site EUI against RECS 2020 and CBECS 2018 (physics 02 section 13)."""
import csv
import socket
from pathlib import Path

import pytest

from backend.schema import BaselineResult, BuildingModel, PropertyBundle
from backend.analysis.model.benchmark import benchmark_eui, check_baseline
from backend.analysis.model.benchmark import eui as E

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A31 must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)


def _rows():
    with E.TABLE.open(newline="") as f:
        return list(csv.DictReader(f))


def test_unit_conversion():
    assert E.KWH_M2_TO_KBTU_FT2 == pytest.approx(0.316998, rel=1e-5)


def test_table_rows_are_ordered_percentiles():
    rows = _rows()
    assert len(rows) > 400
    for r in rows:
        assert int(r["n"]) >= 30
        for q in ("total", "electricity") + (("gas",) if r["fuel"] == "gas" else ()):
            vals = [float(r[f"{q}_p{p}"]) for p in E.QUANTILES]
            assert vals == sorted(vals), (r["survey"], r["climate"], r["fuel"], r["size"], q)
            assert vals[0] >= 0


def test_table_reproduces_published_aggregates():
    """BEN-01 validation: the floorspace-weighted means of the microdata against the published tables."""
    idx = {(r["survey"], r["building_type"], r["climate"], r["fuel"], r["size"]): r for r in _rows()}
    sf = float(idx[("RECS2020", "single_family", "*", "*", "*")]["agg_total"])
    assert 41.6 <= sf <= 41.8            # RECS CE1.1: detached 41.8, attached 41.6 kBtu/ft2
    office = float(idx[("CBECS2018", "office", "*", "*", "*")]["agg_total"])
    assert office == pytest.approx(1093e12 / 16662e6 / 1e3, rel=0.02)    # CBECS C3: 1,093 TBtu / 16,662 Msqft
    median = float(idx[("CBECS2018", "office", "*", "*", "*")]["total_p50"])
    assert median == pytest.approx(52.9, rel=0.02)    # ENERGY STAR national median office site EUI


def test_worked_example_golden_house():
    """BEN worked example: 5,200 kWh electricity + 7,200 kWh gas on 82.04 m2 in 3B."""
    r = benchmark_eui(5200.0, 7200.0, 82.04, "single_family", "3B")
    assert r.status == "checked" and r.survey == "RECS2020"
    assert r.cut == {"climate": "3B", "fuel": "gas", "size": "lt1000"} and r.n == 88
    assert r.eui_kwh_m2 == pytest.approx(151.1, abs=0.05)
    assert r.eui_kbtu_ft2 == pytest.approx(47.91, abs=0.01)
    total = r.bands[0]
    assert total.percentiles_kbtu_ft2[25] == pytest.approx(43.884) and total.percentiles_kbtu_ft2[50] == pytest.approx(59.071)
    assert total.percentile == pytest.approx(31.6, abs=0.1) and total.verdict == "typical"
    assert [b.quantity for b in r.bands] == ["total", "electricity", "gas"]
    assert r.warnings == []


def test_out_of_band_high_and_low_warn():
    high = benchmark_eui(5200.0, 30000.0, 82.04, "single_family", "3B")
    assert any("Gas use intensity" in w and "above" in w for w in high.warnings)
    assert any(w.startswith("Site energy use intensity") for w in high.warnings)
    assert {b.quantity: b.verdict for b in high.bands}["gas"] == "very_high"
    low = benchmark_eui(600.0, 300.0, 82.04, "single_family", "3B")
    assert {b.quantity: b.verdict for b in low.bands}["total"] in ("low", "very_low")
    assert any("below" in w for w in low.warnings)


def test_all_electric_building_uses_the_all_electric_cut():
    r = benchmark_eui(9000.0, 0.0, 150.0, "single_family", "2A")
    assert r.fuel == "electric" and r.cut["fuel"] == "electric"
    assert [b.quantity for b in r.bands] == ["total"]


def test_office_size_class_from_building_area_and_fallback_note():
    with_size = benchmark_eui(294391.3, 74448.5, 2312.0, "office", "3B", building_area_m2=10600.9)
    assert with_size.cut == {"climate": "warm", "fuel": "gas", "size": "50k_200k"}
    no_size = benchmark_eui(294391.3, 74448.5, 2312.0, "office", "3B")
    assert no_size.cut == {"climate": "warm", "fuel": "gas", "size": "*"}
    houston = benchmark_eui(141600.0, 9000.0, 898.4, "office", "2A", building_area_m2=15100.5)
    assert houston.cut["climate"] == "*" and "fewer than 50" in houston.cut_note


def test_multifamily_unit_maps_to_apartments():
    r = benchmark_eui(4000.0, 2000.0, 70.0, "multifamily_unit", "3B")
    assert r.status == "checked" and r.building_type == "multifamily"


@pytest.mark.parametrize("kwargs, words", [
    (dict(climate_zone=None), "no climate zone"),
    (dict(building_type="retail"), "no survey benchmark"),
    (dict(floor_area_m2=None), "no conditioned floor area"),
])
def test_missing_inputs_are_not_checked(kwargs, words):
    args = dict(electricity_kwh=5200.0, gas_kwh=7200.0, floor_area_m2=82.04, building_type="single_family",
                climate_zone="3B")
    args.update(kwargs)
    r = benchmark_eui(**args)
    assert r.status == "not_checked" and words in r.reason
    assert len(r.warnings) == 1 and "not benchmarked" in r.warnings[0]


# Where each golden example's baseline_result.json lands (reported in the PR; physics 02 BEN worked examples).
GOLDEN = {
    "house": ({"climate": "3B", "fuel": "gas", "size": "lt1000"}, 151.1, 31.6, 0),
    "office": ({"climate": "warm", "fuel": "gas", "size": "50k_200k"}, 159.5, 29.5, 0),
    "office_houston": ({"climate": "*", "fuel": "gas", "size": "50k_200k"}, 167.6, 36.0, 1),
}


@pytest.mark.parametrize("folder", sorted(GOLDEN))
def test_golden_examples(folder):
    d = EXAMPLES / folder
    bundle = PropertyBundle.model_validate_json((d / "property_bundle.json").read_text())
    baseline = BaselineResult.model_validate_json((d / "baseline_result.json").read_text())
    model = BuildingModel.model_validate_json((d / "building_model.json").read_text())
    area = sum(z.floor_area_m2 for z in model.zones if z.conditioned)
    warnings, r = check_baseline(baseline, area, bundle.summary.use_type, bundle.climate.climate_zone,
                                 building_area_m2=bundle.costar.building_area_m2 if bundle.costar else None)
    cut, eui, rank, n_warn = GOLDEN[folder]
    assert r.status == "checked" and r.cut == cut
    assert r.eui_kwh_m2 == pytest.approx(eui, abs=0.05)
    assert r.bands[0].percentile == pytest.approx(rank, abs=0.1) and r.bands[0].verdict == "typical"
    assert len(warnings) == n_warn and warnings == r.warnings
    if folder == "office_houston":      # gas 3.18 kBtu/ft2 sits near the 8th percentile of gas-using offices
        assert "Gas use intensity" in warnings[0] and "fewer than 50" in warnings[0]

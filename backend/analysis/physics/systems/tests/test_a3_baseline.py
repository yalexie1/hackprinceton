"""A3 acceptance (workplan 4.2): BaselineResult from Systems, Tariff and synthetic hourly loads.

low <= expected <= high on every Ranged; 12 monthly values; end uses sum to the annual expected
total; a Systems without occupants runs on the schedule default."""
import re
import socket
from pathlib import Path

import numpy as np
import pytest

from backend.analysis.physics.systems import (END_USES, HourlyLoads, baseline_result, calendar_from_stamps,
                                              egrid_subregion, gas_emission_factor, grid_emission_factor,
                                              internal_gains_hourly, systems_baseline)
from backend.schema import Assumption, BaselineResult, BuildingModel, PropertyBundle, Ranged

ROOT = Path(__file__).resolve().parents[5]
EX = ROOT / "specs" / "examples"
SITES = {"house": "typical_year_hourly.csv", "office": "typical_year_hourly.csv",
         "office_houston": "typical_year_hourly_houston.csv"}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*a, **k):
        raise RuntimeError("network access in a unit test")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def _weather(name):
    """Weather sample without 29 February (as the A1 reader returns it), hour_end stamps."""
    raw = np.genfromtxt(EX / "weather" / name, delimiter=",", skip_header=1, usecols=(0, 1), dtype=None,
                        encoding="utf-8")
    stamps = np.array([r[0] for r in raw], dtype="datetime64[h]")
    temp = np.array([r[1] for r in raw], dtype=float)
    keep = ~((stamps.astype("datetime64[M]") == np.datetime64("2024-02")) &
             ((stamps.astype("datetime64[D]") - stamps.astype("datetime64[M]")).astype(int) == 28))
    return stamps[keep], temp[keep]


def _fixture(name):
    model = BuildingModel.model_validate_json((EX / name / "building_model.json").read_text())
    bundle = PropertyBundle.model_validate_json((EX / name / "property_bundle.json").read_text())
    return model, bundle


def _synthetic_loads(t, area, heat_w_per_k_m2=2.5, cool_w_per_k_m2=5.0, latent=True):
    heat = np.maximum(17.0 - t, 0.0) * heat_w_per_k_m2 * area
    cool = np.maximum(t - 21.0, 0.0) * cool_w_per_k_m2 * area
    lat = np.where(cool > 0, 0.1 * cool, 0.0) if latent else None
    return HourlyLoads(heating_need_w=heat, cooling_need_w=cool, outdoor_temp_c=t, latent_oa_w=lat)


def _run(name, systems=None, **kw):
    model, bundle = _fixture(name)
    stamps, t = _weather(SITES[name])
    cal = calendar_from_stamps(stamps, "hour_end")
    area = sum(z.floor_area_m2 for z in model.zones)
    loads = kw.pop("loads", None) or _synthetic_loads(t, area)
    tariff = kw.pop("tariff", bundle.tariff)
    res = systems_baseline(systems or model.systems, tariff, loads, floor_area_m2=area,
                           bedrooms=model.bedrooms, calendar=cal,
                           subregion=egrid_subregion(bundle.summary.state, bundle.summary.address[-5:]),
                           assumptions=model.assumptions, **kw)
    return res, model, bundle, loads, cal


def _all_ranged(obj):
    if isinstance(obj, Ranged):
        yield obj
    elif hasattr(type(obj), "model_fields"):
        for f in type(obj).model_fields:
            yield from _all_ranged(getattr(obj, f))


@pytest.mark.parametrize("name", list(SITES))
def test_acceptance_on_each_golden_fixture(name):
    res, model, bundle, loads, cal = _run(name)
    b = res.baseline
    BaselineResult.model_validate(b.model_dump())                    # contract round trip
    for r in _all_ranged(b):
        assert r.low <= r.expected <= r.high
    assert b.annual.electricity_kwh.low < b.annual.electricity_kwh.high
    assert b.annual.cost_usd.low < b.annual.cost_usd.high
    assert len(b.monthly_electricity_kwh) == 12 and len(b.monthly_gas_kwh) == 12
    assert sum(b.monthly_electricity_kwh) == pytest.approx(b.annual.electricity_kwh.expected, rel=1e-9)
    assert sum(b.monthly_gas_kwh) == pytest.approx(b.annual.gas_kwh.expected, rel=1e-9)
    assert set(b.end_use_kwh) == set(END_USES)
    total = b.annual.electricity_kwh.expected + b.annual.gas_kwh.expected
    assert sum(b.end_use_kwh.values()) == pytest.approx(total, rel=1e-9)
    t = bundle.tariff
    cost = (b.annual.electricity_kwh.expected * t.electricity_usd_per_kwh + 12 * t.fixed_usd_per_month
            + b.annual.gas_kwh.expected * (t.gas_usd_per_kwh or 0.0))
    assert b.annual.cost_usd.expected == pytest.approx(cost, rel=1e-9)
    sub = res.subregion
    co2 = b.annual.electricity_kwh.expected * grid_emission_factor(sub) + b.annual.gas_kwh.expected * gas_emission_factor()
    assert b.annual.co2_kg.expected == pytest.approx(co2, rel=1e-9)
    assert b.annual.co2_nonbaseload_kg.expected > b.annual.co2_kg.expected
    assert b.heating_need_kwh == pytest.approx(loads.heating_need_w.sum() / 1000)
    assert b.cooling_need_kwh == pytest.approx(loads.cooling_need_w.sum() / 1000)
    assert b.latent_cooling_kwh > 0 and b.peak_cooling_w > 0 and b.peak_heating_w > 0
    assert res.occupants_source == "systems"


def test_routes_and_subregions_of_the_fixtures():
    house = _run("house")[0]
    office = _run("office")[0]
    hou = _run("office_houston")[0]
    assert (house.cooling_route, house.heating_route, house.subregion) == ("hourly_seer", "furnace", "CAMX")
    assert (office.cooling_route, office.subregion) == ("hourly_seer", "CAMX")
    assert (hou.cooling_route, hou.subregion) == ("ieer", "ERCT")
    assert office.baseline.end_use_kwh["water_heating"] == 0.0
    assert house.baseline.end_use_kwh["water_heating"] > 0 and house.baseline.end_use_kwh["appliances"] > 0


def test_formula_ids_exist_in_the_physics_files():
    text = "".join((ROOT / "specs" / "physics" / f).read_text()
                   for f in ("02-thermal-systems.md", "04-economics-emissions-mv.md"))
    known = set(re.findall(r"### ([A-Z]+-\d+[a-z]?)", text))
    for name in SITES:
        res = _run(name)[0]
        assert res.formula_ids and set(res.formula_ids) <= known


@pytest.mark.parametrize("name", ["office", "office_houston"])
def test_office_without_occupants_runs_on_schedule_default(name):
    model, _ = _fixture(name)
    sys_none = model.systems.model_copy(update={"occupants": None})
    res = _run(name, systems=sys_none)[0]
    area = sum(z.floor_area_m2 for z in model.zones)
    assert res.occupants_source == "schedule_default"
    assert res.occupants == pytest.approx(area / 18.59)
    for r in _all_ranged(res.baseline):
        assert r.low <= r.expected <= r.high
    with_occ = _run(name)[0]
    # head count scales the plug density (LGT-02) only when occupants come from the model
    scale = min(max(model.systems.occupants.expected / area * 18.59, 0.5), 2.0)
    assert with_occ.baseline.end_use_kwh["plug"] == pytest.approx(res.baseline.end_use_kwh["plug"] * scale, rel=1e-9)


def test_home_without_occupants_runs_on_schedule_default():
    model, _ = _fixture("house")
    res = _run("house", systems=model.systems.model_copy(update={"occupants": None}))[0]
    assert res.occupants_source == "schedule_default"
    assert res.occupants == pytest.approx(0.59 * model.bedrooms + 0.87)


def test_internal_gains_for_the_zone_model():
    model, _ = _fixture("office")
    area = sum(z.floor_area_m2 for z in model.zones)
    g = internal_gains_hourly(model.systems, area)
    assert len(g["sensible_w"]) == 8760 and g["occupants"] == 20.0
    g0 = internal_gains_hourly(model.systems.model_copy(update={"occupants": None}), area)
    assert g0["occupants_source"] == "schedule_default" and g0["occupants"] == pytest.approx(area / 18.59)
    assert (g["latent_w"] >= 0).all() and g["sensible_w"].min() > 0       # night lighting and plug base load


def test_price_range_from_the_registry_is_used():
    res, model, bundle, *_ = _run("office_houston")
    rows = [r for r in res.sensitivity if r.key == "tariff.electricity_usd_per_kwh" and r.output == "cost_usd"]
    assert len(rows) == 1
    e = res.baseline.annual.electricity_kwh.expected
    gas_usd = res.baseline.annual.gas_kwh.expected * bundle.tariff.gas_usd_per_kwh   # D15 EIA TX COM
    assert rows[0].y_low_run == pytest.approx(e * 0.086 + gas_usd, rel=1e-9)
    assert rows[0].y_high_run == pytest.approx(e * 0.133 + gas_usd, rel=1e-9)
    assert res.baseline.annual.cost_usd.high >= rows[0].y_high_run - 1e-9


def test_single_input_range_equals_the_direct_runs():
    """With only one ranged input the band is exactly that input's two runs (UNC-02)."""
    model, bundle = _fixture("office_houston")
    s = model.systems
    flat = lambda r: Ranged(low=r.expected, expected=r.expected, high=r.expected, unit=r.unit)  # noqa: E731
    s1 = s.model_copy(update={"lighting_w_per_m2": flat(s.lighting_w_per_m2), "plug_w_per_m2": flat(s.plug_w_per_m2),
                              "occupants": flat(s.occupants), "cooling_rating": flat(s.cooling_rating)})
    res = _run("office_houston", systems=s1)[0]
    e = res.baseline.annual.electricity_kwh
    assert {r.key for r in res.sensitivity} == {"hvac.seasonal_climate", "tariff.electricity_usd_per_kwh"}
    cool = res.baseline.end_use_kwh["cooling"]
    assert e.low == pytest.approx(e.expected - 0.15 * cool, rel=1e-9)
    assert e.high == pytest.approx(e.expected + 0.15 * cool, rel=1e-9)


def test_load_variants_widen_the_range():
    name = "house"
    model, _ = _fixture(name)
    stamps, t = _weather(SITES[name])
    area = sum(z.floor_area_m2 for z in model.zones)
    lo = _synthetic_loads(t, area, 2.0, 4.0)
    hi = _synthetic_loads(t, area, 3.5, 6.5)
    base = _run(name)[0].baseline
    wide = _run(name, load_variants={"envelope": (lo, hi)})[0]
    assert any(r.key == "envelope" for r in wide.sensitivity)
    assert wide.baseline.annual.gas_kwh.high > base.annual.gas_kwh.high
    assert wide.baseline.annual.gas_kwh.expected == pytest.approx(base.annual.gas_kwh.expected)


def test_heat_pump_resistance_and_variable_speed_routes():
    model, _ = _fixture("house")
    s = model.systems
    hp = s.model_copy(update={"hvac_type": "heat_pump", "heating_fuel": "electricity",
                              "heating_rating": Ranged(low=7.7, expected=8.2, high=8.5, unit="HSPF"),
                              "heating_rating_metric": "HSPF", "dhw_fuel": "electricity",
                              "dhw_efficiency": Ranged(low=0.87, expected=0.92, high=0.93, unit="-")})
    r = _run("house", systems=hp)[0]
    assert r.heating_route == "heat_pump_hourly"
    assert r.baseline.annual.gas_kwh.expected == 0.0
    assert r.baseline.end_use_kwh["heating"] > 0
    hp_out = hp.model_copy(update={"heating_rating": Ranged(low=9.0, expected=9.5, high=10.0, unit="HSPF")})
    r2 = _run("house", systems=hp_out)[0]
    assert r2.heating_route == "heat_pump_seasonal" and any("HSPF" in w for w in r2.warnings)
    res = s.model_copy(update={"heating_fuel": "electricity", "hvac_type": "central_ac_furnace",
                               "heating_rating": None, "heating_rating_metric": None,
                               "heating_efficiency": Ranged(low=1, expected=1, high=1, unit="-")})
    r3 = _run("house", systems=res)[0]
    assert r3.heating_route == "resistance"
    assert r3.baseline.end_use_kwh["heating"] == pytest.approx(r3.hourly["heating_load_w"].sum() / 1000)
    var = s.model_copy(update={"compressor_type": "variable", "cooling_rating_metric": "SEER2"})
    r4 = _run("house", systems=var)[0]
    assert r4.cooling_route == "seasonal"
    cool_load = r4.hourly["cooling_load_w"].sum() / 1000
    assert r4.baseline.end_use_kwh["cooling"] == pytest.approx(cool_load / (13.0 / 0.95 * 0.293071), rel=1e-9)


def test_no_hvac_and_central_plant():
    model, _ = _fixture("office")
    none = model.systems.model_copy(update={"hvac_type": "none"})
    r = _run("office", systems=none)[0]
    assert r.baseline.end_use_kwh["heating"] == 0 and r.baseline.end_use_kwh["cooling"] == 0
    plant = model.systems.model_copy(update={"hvac_type": "central_plant"})
    rp = _run("office", systems=plant)[0]
    base = _run("office")[0]
    assert any(k.key == "hvac.central_plant" for k in rp.sensitivity)
    assert (rp.baseline.annual.electricity_kwh.high - rp.baseline.annual.electricity_kwh.low
            > base.baseline.annual.electricity_kwh.high - base.baseline.annual.electricity_kwh.low)


def test_unknown_fuels_assume_gas_even_without_a_gas_price_and_warn():
    # A missing gas price means gas is unknown, not absent (HVAC-00): the fuels must not turn electric.
    model, bundle = _fixture("house")
    s = model.systems.model_copy(update={"heating_fuel": "unknown", "dhw_fuel": "unknown"})
    r = _run("house", systems=s)[0]
    assert r.heating_route == "furnace" and r.baseline.annual.gas_kwh.expected > 0
    no_gas = bundle.tariff.model_copy(update={"gas_usd_per_kwh": None})
    r2 = _run("house", systems=s, tariff=no_gas)[0]
    assert r2.heating_route == "furnace"
    assert r2.baseline.annual.gas_kwh.expected == pytest.approx(r.baseline.annual.gas_kwh.expected)
    assert any("whether gas is at the site is unknown" in w for w in r2.warnings)
    assert any("costed at 0" in w and "understated" in w for w in r2.warnings)
    r3 = _run("house", tariff=no_gas)[0]
    assert any("no gas price" in w for w in r3.warnings)


def test_default_calendar_and_length_checks():
    model, bundle = _fixture("office")
    t = np.full(8760, 25.0)
    loads = HourlyLoads(np.zeros(8760), np.full(8760, 1000.0), t)
    b = baseline_result(model.systems, bundle.tariff, loads, floor_area_m2=383.42)
    assert len(b.monthly_electricity_kwh) == 12
    with pytest.raises(ValueError):
        HourlyLoads(np.zeros(10), np.zeros(9), np.zeros(10))


def test_lowering_a_homes_lighting_density_lowers_its_lighting_energy():
    # LGT_LED on a home applies the LGT-01 lamp-mix factor to lighting_w_per_m2; that must reach the
    # energy (it did not while the scale was taken relative to the model's own expected value)
    model, _ = _fixture("house")
    before = _run("house")[0].baseline.end_use_kwh["lighting"]
    lpd = model.systems.lighting_w_per_m2
    led = Ranged(low=lpd.low * 0.4851, expected=lpd.expected * 0.4851, high=lpd.high * 0.4851, unit=lpd.unit)
    after = _run("house", systems=model.systems.model_copy(update={"lighting_w_per_m2": led}))[0]
    assert after.baseline.end_use_kwh["lighting"] == pytest.approx(before * 0.4851, rel=1e-6)

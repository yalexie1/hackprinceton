"""#439: multi-dwelling buildings (the lodging archetype). The home formulas are per dwelling."""
from __future__ import annotations

import numpy as np
import pytest

from backend.analysis.physics.systems.loads import bedrooms_per_dwelling, default_calendar, end_use_profiles
from backend.schema import Assumption, Ranged

from backend.analysis.physics.systems import calendar_from_stamps, egrid_subregion, systems_baseline

from test_a3_baseline import SITES, _fixture, _synthetic_loads, _weather


def _baseline(extra=()):
    model, bundle = _fixture("house")
    stamps, t = _weather(SITES["house"])
    cal = calendar_from_stamps(stamps, "hour_end")
    area = sum(z.floor_area_m2 for z in model.zones)
    return systems_baseline(model.systems, bundle.tariff, _synthetic_loads(t, area), floor_area_m2=area,
                            bedrooms=model.bedrooms, calendar=cal,
                            subregion=egrid_subregion(bundle.summary.state, bundle.summary.address[-5:]),
                            assumptions=[*model.assumptions, *extra]), model


def _profiles(area, units, bedrooms=3, occupants=None):
    return end_use_profiles(occupancy_schedule="home", floor_area_m2=area, cal=default_calendar(),
                            lpd_w_m2=7.0, ppd_w_m2=5.0, occupants=occupants, bedrooms=bedrooms,
                            dwelling_units=units)


def test_one_dwelling_is_exactly_the_single_home_calculation():
    a = end_use_profiles(occupancy_schedule="home", floor_area_m2=150.0, cal=default_calendar(),
                         lpd_w_m2=7.0, ppd_w_m2=5.0, occupants=None, bedrooms=3)
    b = _profiles(150.0, 1.0)
    for f in ("lighting_kwh", "plug_kwh", "appliances_kwh"):
        np.testing.assert_allclose(getattr(a, f), getattr(b, f))
    assert a.occupants == b.occupants


def test_n_dwellings_are_n_times_one_dwelling_of_the_share():
    one = _profiles(80.0, 1.0, bedrooms=2)
    many = _profiles(80.0 * 40, 40.0, bedrooms=2)
    for f in ("lighting_kwh", "plug_kwh", "appliances_kwh"):
        assert getattr(many, f).sum() == pytest.approx(40 * getattr(one, f).sum(), rel=1e-9)
    assert many.occupants == pytest.approx(40 * one.occupants)


def test_bedrooms_per_dwelling():
    assert bedrooms_per_dwelling(3, 1.0) == 3            # one dwelling: unchanged
    assert bedrooms_per_dwelling(None, 1.0) is None
    assert bedrooms_per_dwelling(80, 40.0) == 2.0        # the scan's count spread over the units
    assert bedrooms_per_dwelling(3, 40.0) == 1.5         # too few labelled: the per-dwelling default


def test_baseline_reads_dwelling_units_and_scales_home_energy():
    base, _ = _baseline()
    units = Ranged(low=20.0, expected=30.0, high=40.0, unit="dwellings")
    extra = Assumption(key="dwelling.units", label="Number of dwellings in the building", value=units,
                       source="vintage_default", confidence=0.2)
    many, _ = _baseline([extra])
    e0 = base.baseline.annual.electricity_kwh
    e1 = many.baseline.annual.electricity_kwh
    assert e1.expected > 3 * e0.expected                  # per-dwelling constants now count 30 times
    assert e1.low < e1.expected < e1.high
    assert any(r.key == "dwelling.units" for r in many.sensitivity)

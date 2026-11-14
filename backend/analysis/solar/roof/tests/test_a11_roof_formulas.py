"""A11 formula tests against the physics 01 worked examples (ROOF-03, ROOF-04, ROOF-06)."""
from __future__ import annotations

import pytest

from backend.analysis.solar.roof import (fire_setbacks, obstruction_allowance_m2, roof_pitch_range,
                                         setback_area_m2, usable_area_parametric)


def _t(r):
    return (r.low, r.expected, r.high)


# ---------- ROOF-03 ----------

def test_pitch_table_printed_triples():
    assert _t(roof_pitch_range("flat", 2207.0)) == (0.0, 1.2, 9.5)
    assert _t(roof_pitch_range("gable", 190.4, "shingle")) == (15.8, 28.4, 41.1)
    assert _t(roof_pitch_range("hip", 190.4)) == (15.8, 28.4, 41.1)
    assert _t(roof_pitch_range("Gable ", 190.4)) == (15.8, 28.4, 41.1)
    assert _t(roof_pitch_range(None, 190.4)) == (0.0, 28.4, 47.4)
    assert _t(roof_pitch_range("mansard", 5000.0)) == (0.0, 28.4, 47.4)


def test_pitch_large_pitched_roof_starts_at_covering_minimum():
    assert _t(roof_pitch_range("gable", 1000.0)) == (1.2, 15.8, 28.4)
    assert _t(roof_pitch_range("hip", 1000.0, "shingle")) == (9.46, 15.8, 28.4)
    assert _t(roof_pitch_range("gable", 1000.0, "tile")) == (11.77, 15.8, 28.4)
    assert roof_pitch_range("gable", 1000.0, "metal").low == pytest.approx(1.19)


def test_pitch_small_threshold_is_5000_sqft():
    assert roof_pitch_range("gable", 464.0).expected == 28.4
    assert roof_pitch_range("gable", 465.0).expected == 15.8


# ---------- ROOF-06 ----------

def test_setback_metric_values_are_inches_times_0_0254():
    sb = fire_setbacks("CA", "R-3", 28.4)
    assert sb.ridge_setback_m == pytest.approx(18 * 0.0254, abs=1e-4)
    assert sb.pathway_width_m == pytest.approx(36 * 0.0254, abs=1e-4)
    assert fire_setbacks("CA", "R-3", 28.4, array_plan_share=0.40).ridge_setback_m == pytest.approx(0.9144, abs=1e-4)
    assert fire_setbacks("CA", "R-3", 28.4, array_plan_share=0.40, sprinklered=True).ridge_setback_m == \
        pytest.approx(0.4572, abs=1e-4)
    small = fire_setbacks("CA", "commercial", 1.2, building_axes_m=(60.0, 30.0))
    large = fire_setbacks("CA", "commercial", 1.2, building_axes_m=(100.0, 80.0))
    assert small.perimeter_m == pytest.approx(1.2192, abs=1e-4)
    assert large.perimeter_m == pytest.approx(1.8288, abs=1e-4)
    assert large.interior_interval_m == pytest.approx(45.72, abs=1e-4)


def test_low_slope_house_is_exempt_and_status_is_never_silently_verified():
    sb = fire_setbacks("CA", "R-3", 9.0)
    assert (sb.ridge_setback_m, sb.pathway_width_m, sb.perimeter_m) == (0.0, 0.0, 0.0)
    assert fire_setbacks("CA", "R-3", 28.4).status == "U"           # R329.6 not opened
    assert fire_setbacks("TX", "commercial", 1.2).status == "P"     # Houston adoption pending
    assert fire_setbacks("CA", "commercial", 1.2).status == "V-repro"
    assert fire_setbacks(None, "R-3", 28.4).status == "U"


# ---------- ROOF-04 ----------

def test_obstruction_allowance_table():
    a = obstruction_allowance_m2({"chimney": 1, "roof-vent": 5})
    assert a.expected == pytest.approx(3.04 + 5 * 0.81)
    assert (a.low, a.high) == pytest.approx((2.0 + 5 * 0.4, 5.0 + 5 * 1.5))
    assert obstruction_allowance_m2({}).expected == 0.0


def test_area_method_golden_house_worked_example():
    sb = fire_setbacks("CA", "R-3", 28.4)
    s = 5.6 / 0.879649          # 5.6 / cos(28.4)
    a_plane = 95.20 / 0.879649
    a_rect = setback_area_m2(a_plane, 17.0, s, sb)
    assert a_rect == pytest.approx(95.05, abs=0.01)
    usable = usable_area_parametric(a_plane, 17.0, s, sb, {"chimney": 1, "roof-vent": 5}, plan_share=0.5)
    assert usable == pytest.approx(91.50, abs=0.01)
    # 36-inch ridge setback redo
    sb36 = fire_setbacks("CA", "R-3", 28.4, array_plan_share=0.388)
    assert setback_area_m2(a_plane, 17.0, s, sb36) == pytest.approx(87.70, abs=0.01)
    assert usable_area_parametric(a_plane, 17.0, s, sb36, {"chimney": 1, "roof-vent": 5}, 0.5) == \
        pytest.approx(84.15, abs=0.01)


def test_commercial_perimeter_worked_example():
    sb = fire_setbacks("CA", "commercial", 0.0, building_axes_m=(60.0, 30.0))
    # 60 x 30 has an axis above 45.72 m, so one interior pathway; without it the
    # printed 57.5616 * 27.5616 = 1586.49 m2 is the perimeter-only result
    assert setback_area_m2(1800.0, 60.0, 30.0, sb.__class__(0.0, 0.0, sb.perimeter_m, None, "", "U")) == \
        pytest.approx(1586.49, abs=0.01)
    assert setback_area_m2(1800.0, 60.0, 30.0, sb) == pytest.approx((57.5616 - 1.2192) * 27.5616, abs=0.01)
    big = fire_setbacks("CA", "commercial", 0.0, building_axes_m=(100.0, 80.0))
    perim_only = big.__class__(0.0, 0.0, big.perimeter_m, None, "", "U")
    assert setback_area_m2(8000.0, 100.0, 80.0, perim_only) == pytest.approx(7355.01, abs=0.01)


def test_usable_never_exceeds_plane_and_never_negative():
    sb = fire_setbacks("CA", "R-3", 28.4)
    assert usable_area_parametric(10.0, 3.0, 2.0, sb, {"ac-unit": 50}, 1.0) == 0.0
    assert usable_area_parametric(10.0, 3.0, 2.0, sb, {}, 1.0, tree_area_m2=-5.0) <= 10.0
    assert usable_area_parametric(108.23, 17.0, 6.3662, sb, {}, 0.5, tree_area_m2=10.0) == \
        pytest.approx(usable_area_parametric(108.23, 17.0, 6.3662, sb, {}, 0.5) - 10.0)

"""PV yield cross-check payload."""
from __future__ import annotations

import pytest

from backend.evals.run_pv import pv_row


def test_records_kwh_per_kw_and_pct_diff():
    row = pv_row(sid="ZSPaQbkGcJJ", annual_kwh=16767.5, system_kw_dc=10.0,
                 pvgis_kwh_per_kw=1676.75, mountingplace="free")
    assert row["kwh_per_kw"] == 1676.75
    assert row["pct_diff"] == 0.0
    assert row["mountingplace"] == "free"


def test_pct_diff_is_signed_against_pvgis():
    # 5% above PVGIS.
    row = pv_row(sid="x", annual_kwh=1760.6, system_kw_dc=1.0,
                 pvgis_kwh_per_kw=1676.75, mountingplace="free")
    assert row["pct_diff"] == pytest.approx(5.0, abs=0.05)


def test_mountingplace_is_required_because_it_moves_pvgis_by_4_to_5_percent():
    # PVGIS free vs building differ by ~4-5% (1754 vs 1677 kWh/kWp at LA), so a row
    # without it is not reproducible. Refuse rather than record an ambiguous number.
    with pytest.raises(ValueError, match="mountingplace"):
        pv_row(sid="x", annual_kwh=1000.0, system_kw_dc=1.0,
               pvgis_kwh_per_kw=1676.75, mountingplace=None)


def test_no_design_is_not_checked_rather_than_zero():
    row = pv_row(sid="x", annual_kwh=None, system_kw_dc=None,
                 pvgis_kwh_per_kw=1676.75, mountingplace="free")
    assert row["status"] == "not_checked"
    assert row["kwh_per_kw"] is None
    assert row["pct_diff"] is None


def test_no_pvgis_reference_is_not_checked():
    row = pv_row(sid="x", annual_kwh=1000.0, system_kw_dc=1.0,
                 pvgis_kwh_per_kw=None, mountingplace="free")
    assert row["status"] == "not_checked"
    assert row["pct_diff"] is None


def test_pv_row_records_which_design_constraint_produced_it():
    # The product sizes PV two ways: standalone (roof/consumption limited, what the
    # PV_ROOF card alone does) and inside a plan (also budget limited, what the demo
    # shows). A cross-check that does not say which one it measured is unreadable.
    row = pv_row(sid="x", annual_kwh=1676.75, system_kw_dc=1.0, pvgis_kwh_per_kw=1676.75,
                 mountingplace="free", constraint="roof_and_consumption")
    assert row["constraint"] == "roof_and_consumption"
    budgeted = pv_row(sid="x", annual_kwh=1676.75, system_kw_dc=1.0, pvgis_kwh_per_kw=1676.75,
                      mountingplace="free", constraint="budget_10000")
    assert budgeted["constraint"] == "budget_10000"


def test_kwh_per_kw_is_scale_invariant_so_both_constraints_are_comparable():
    # PV-10 compares yield per kW, so a budget-limited array and a roof-limited one
    # are directly comparable even though their capacities differ.
    small = pv_row(sid="x", annual_kwh=3353.5, system_kw_dc=2.0, pvgis_kwh_per_kw=1676.75,
                   mountingplace="free", constraint="budget_10000")
    big = pv_row(sid="x", annual_kwh=167675.0, system_kw_dc=100.0, pvgis_kwh_per_kw=1676.75,
                 mountingplace="free", constraint="roof_and_consumption")
    assert small["kwh_per_kw"] == big["kwh_per_kw"] == 1676.75
    assert small["pct_diff"] == big["pct_diff"] == 0.0

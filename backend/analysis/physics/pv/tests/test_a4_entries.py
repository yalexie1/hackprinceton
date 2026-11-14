"""A4: every PV worked example in physics 01 section 3 (and SHD-03, SHD-05 arithmetic).

Printed values are checked to their printed digits; pvlib functions named in
each entry are checked at 1e-6 relative (physics 01 section 7).
"""
import math

import numpy as np
import pytest

pvlib = pytest.importorskip("pvlib")

from backend.analysis.physics.pv import (
    PV09_SCENARIOS, ac_nameplate, annual_energy, array_rating, cell_temperature_sapm,
    degraded_energy, energy_range, incidence_angle_modifier, inverter_ac_power,
    lifetime_energy, losses_with_shading, pv_dc_power, pv_hourly_from_poa,
    pv_hourly_yield, sapm_row, shaded_poa, system_loss_fraction, transmitted_irradiance,
    weather_sigma,
)
from backend.analysis.physics.pv import constants as C
from backend.schema import Ranged

REL = 1e-6

# Running example components (IRR-05, IRR-08, IRR-09), physics 01 section 0.4.
EB, ED, EG = 670.332, 221.881, 4.825
THETA = 15.8675


# ---------------------------------------------------------------- PV-01

# The running example of physics 01 prints IAM(15.8675) = 0.999890, which is the
# value without the absorption factor (K = 0; pvlib gives 0.999758 at the K = 4
# default). Every running-example number downstream of PV-01 (Etr = 896.96, PV-03,
# SHD-03 transmitted 611.88) was computed with that K = 0 value, so those tests
# pass K = 0. The implementation default stays K = 4, as the entry and the PV-06
# ModelChain reference (aoi_model="physical") state.
K0 = {"k_per_m": 0.0}


def test_pv01_iam_printed():
    assert float(incidence_angle_modifier(60.0)) == pytest.approx(0.946003, abs=5e-7)
    assert float(incidence_angle_modifier(15.8675, **K0)) == pytest.approx(0.999890, abs=5e-7)


def test_pv01_iam_without_absorption_printed():
    assert float(incidence_angle_modifier(60.0, k_per_m=0.0)) == pytest.approx(0.947628, abs=5e-7)
    assert float(incidence_angle_modifier(80.0, k_per_m=0.0)) == pytest.approx(0.6357, abs=5e-5)


def test_pv01_iam_matches_pvlib():
    aoi = np.array([0.0, 1e-9, 5.0, 15.8675, 30.0, 45.0, 60.0, 75.0, 80.0, 85.0, 89.9])
    ours = incidence_angle_modifier(aoi)
    ref = pvlib.iam.physical(aoi, n=1.526, K=4.0, L=0.002)
    np.testing.assert_allclose(ours, ref, rtol=REL, atol=1e-12)
    ref0 = pvlib.iam.physical(aoi, n=1.526, K=0.0, L=0.002)
    np.testing.assert_allclose(incidence_angle_modifier(aoi, k_per_m=0.0), ref0, rtol=REL, atol=1e-12)


def test_pv01_iam_behind_plane_is_zero():
    np.testing.assert_array_equal(incidence_angle_modifier([90.0, 120.0, 180.0, np.nan]), 0.0)
    assert float(incidence_angle_modifier(0.0)) == 1.0


def test_pv01_transmitted_running_example():
    assert float(transmitted_irradiance(EB, ED, EG, THETA, **K0)) == pytest.approx(896.96, abs=0.005)


# ---------------------------------------------------------------- PV-02

@pytest.mark.parametrize("row,tc", [
    ("glass_glass_close_roof_mount", 72.364),
    ("glass_polymer_open_rack", 54.648),
    ("glass_polymer_insulated_back", 79.309),
    ("glass_glass_open_rack", 57.478),
])
def test_pv02_cell_temperature(row, tc):
    a, b, dt = sapm_row(row)
    ours = float(cell_temperature_sapm(897.037, 30.0, 2.0, a, b, dt))
    assert ours == pytest.approx(tc, abs=5e-4)
    ref = float(pvlib.temperature.sapm_cell(897.037, 30.0, 2.0, a, b, dt))
    assert ours == pytest.approx(ref, rel=REL)


def test_pv02_rows_match_pvlib_table():
    table = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]
    names = {"glass_glass_open_rack": "open_rack_glass_glass",
             "glass_glass_close_roof_mount": "close_mount_glass_glass",
             "glass_polymer_open_rack": "open_rack_glass_polymer",
             "glass_polymer_insulated_back": "insulated_back_glass_polymer"}
    for ours, theirs in names.items():
        p = table[theirs]
        assert C.SAPM_TEMPERATURE_ROWS[ours] == (p["a"], p["b"], p["deltaT"])


# ---------------------------------------------------------------- PV-03

def test_pv03_dc_power():
    p = float(pv_dc_power(896.963, 72.364, 6000.0, -0.0035))
    assert p == pytest.approx(4489.62, abs=0.005)
    assert p == pytest.approx(float(pvlib.pvsystem.pvwatts_dc(896.963, 72.364, 6000.0, -0.0035)), rel=REL)


def test_pv03_negative_is_zero():
    assert float(pv_dc_power(500.0, 400.0, 1000.0, -0.0035)) == 0.0


# ---------------------------------------------------------------- PV-04

def test_pv04_defaults():
    loss = system_loss_fraction()
    assert 100 * loss == pytest.approx(14.0757, abs=5e-5)
    assert 100 * loss == pytest.approx(float(pvlib.pvsystem.pvwatts_losses()), rel=REL)


def test_pv04_no_shading():
    loss = system_loss_fraction(losses_with_shading(0.0))
    assert 100 * loss == pytest.approx(11.4182, abs=5e-5)
    assert 100 * loss == pytest.approx(float(pvlib.pvsystem.pvwatts_losses(shading=0)), rel=REL)
    assert 4489.62 * (1 - loss) == pytest.approx(3976.99, abs=0.005)


def test_pv04_rejects_bad_percent():
    with pytest.raises(ValueError):
        system_loss_fraction({"soiling": 120})


# ---------------------------------------------------------------- PV-05

@pytest.mark.parametrize("pdc,pac", [(3976.99, 3825.84), (5600.0, 5000.0), (250.0, 214.70)])
def test_pv05_inverter(pdc, pac):
    pac0 = ac_nameplate(6000.0, 1.2)
    assert pac0 == pytest.approx(5000.0)
    ours = float(inverter_ac_power(pdc, pac0))
    assert ours == pytest.approx(pac, abs=0.01)  # printed values are truncated
    ref = float(pvlib.inverter.pvwatts(pdc, pac0 / 0.96, eta_inv_nom=0.96))
    assert ours == pytest.approx(ref, rel=REL)


def test_pv05_zero_and_negative_dc():
    np.testing.assert_array_equal(inverter_ac_power([0.0, -5.0], 5000.0), 0.0)


def test_pv05_pvw5_ratio_check():
    assert ac_nameplate(4000.0, 1.1) == pytest.approx(3636.36, abs=0.01)


# ---------------------------------------------------------------- whole hour, running example

def test_running_example_one_hour_chain():
    """PV-01 to PV-05 chained for the running example hour, 6 kW, shading loss 0."""
    out = pv_hourly_yield([EB], [ED], [EG], [THETA], [30.0], [2.0],
                          losses_percent=losses_with_shading(0.0), iam_kwargs=K0)
    assert out.poa_global_w_m2[0] == pytest.approx(897.038, abs=1e-3)
    assert out.transmitted_w_m2[0] == pytest.approx(896.96, abs=0.005)
    assert out.cell_temp_c[0] == pytest.approx(72.364, abs=5e-4)
    assert 6 * out.dc_net_w_per_kw[0] == pytest.approx(3976.99, abs=0.02)
    # 3825.84 W for 6 kW, one hour -> kWh per kW
    assert 6 * out.ac_kwh_per_kw[0] * 1000 == pytest.approx(3825.84, abs=0.02)


def test_default_losses_keep_three_percent_shading():
    out = pv_hourly_yield([EB], [ED], [EG], [THETA], [30.0], [2.0])
    assert 100 * out.loss_fraction == pytest.approx(14.0757, abs=5e-5)
    assert out.warnings == ()


# ---------------------------------------------------------------- SHD-03 / SHD-05 as applied by A4

def test_shd03_worked_example():
    # Perez components of the running example (IRR-08): circumsolar 153.663, iso 56.380, horizon 11.839
    circ, iso, hor = 153.663, 56.380, 11.839
    sh = shaded_poa(EB, circ + iso + hor, EG, THETA, 3 / 9, 0.84693, poa_sky_circumsolar=circ, **K0)
    assert float(sh["poa_global_shaded"]) == pytest.approx(611.93, abs=0.005)
    assert float(sh["shading_factor"]) == pytest.approx(0.3178, abs=5e-5)
    assert float(sh["transmitted_shaded"]) == pytest.approx(611.88, abs=0.005)
    # SAM rule printed as the alternative
    sam = shaded_poa(EB, circ + iso + hor, EG, THETA, 3 / 9, 0.84693)
    assert float(sam["poa_global_shaded"]) == pytest.approx(639.63, abs=0.005)


def test_shd03_unshaded_equals_irr10():
    sh = shaded_poa(EB, ED, EG, THETA, 0.0, 1.0, poa_sky_circumsolar=100.0)
    assert float(sh["poa_global_shaded"]) == pytest.approx(EB + ED + EG, rel=1e-9)
    assert float(sh["transmitted_shaded"]) == pytest.approx(
        float(transmitted_irradiance(EB, ED, EG, THETA)), rel=1e-9)
    assert float(sh["shading_factor"]) == pytest.approx(0.0, abs=1e-12)


def test_shading_inputs_switch_loss_row_and_scale():
    base = pv_hourly_yield([EB], [ED], [EG], [THETA], [30.0], [2.0],
                           losses_percent=losses_with_shading(0.0))
    zero = pv_hourly_yield([EB], [ED], [EG], [THETA], [30.0], [2.0], shading_factor=[0.0])
    assert zero.ac_kwh_per_kw[0] == pytest.approx(base.ac_kwh_per_kw[0], rel=1e-12)
    assert "SHD-03" in zero.formula_ids and any("PV-04" in w for w in zero.warnings)
    half = pv_hourly_yield([EB], [ED], [EG], [THETA], [30.0], [2.0], shading_factor=[0.5])
    assert half.poa_global_w_m2[0] == pytest.approx(0.5 * (EB + ED + EG), rel=1e-12)
    assert half.ac_kwh_per_kw[0] < base.ac_kwh_per_kw[0]
    pair = pv_hourly_yield([EB], [ED], [EG], [THETA], [30.0], [2.0],
                           beam_shading_fraction=[3 / 9], diffuse_shading_factor=[0.84693],
                           poa_sky_circumsolar=[153.663], iam_kwargs=K0)
    assert pair.poa_global_w_m2[0] == pytest.approx(611.93, abs=0.005)
    with pytest.raises(ValueError):
        pv_hourly_yield([EB], [ED], [EG], [THETA], [30.0], [2.0], shading_factor=[0.1],
                        beam_shading_fraction=[0.1])


def test_shd05_annual_shading_loss_definition():
    assert 1 - 1750.0 / 1900.0 == pytest.approx(0.0789, abs=5e-5)


# ---------------------------------------------------------------- PV-06

def test_pv06_annual_energy_and_monthly():
    hourly = np.full(8760, 0.2)
    month = np.repeat(np.arange(1, 13), 730)
    out = annual_energy(hourly, pdc0_kw=6.0, month=month)
    assert out["yield_kwh_per_kw"] == pytest.approx(1752.0)
    assert out["annual_kwh"] == pytest.approx(6 * 1752.0)
    assert sum(out["monthly_kwh"]) == pytest.approx(out["annual_kwh"])


def test_chain_is_linear_in_nameplate():
    """Per-kW output times the rating equals running the entries at full size."""
    out = pv_hourly_from_poa([897.038, 300.0, 50.0], [896.96, 290.0, 45.0], 30.0, 2.0)
    for i in range(3):
        a, b, dt = sapm_row(C.TEMPERATURE_ROW_EXPECTED)
        tc = cell_temperature_sapm(out.poa_global_w_m2[i], 30.0, 2.0, a, b, dt)
        pdc = pv_dc_power(out.transmitted_w_m2[i], tc, 6000.0) * (1 - system_loss_fraction())
        pac = float(inverter_ac_power(pdc, 5000.0))
        assert 6 * out.ac_kwh_per_kw[i] * 1000 == pytest.approx(pac, rel=1e-12)


# ---------------------------------------------------------------- PV-07, PV-08

def test_pv07_degradation():
    assert degraded_energy(9000.0, 10) == pytest.approx(8603.01, abs=0.005)
    assert degraded_energy(9000.0, 25) == pytest.approx(7979.88, abs=0.005)
    closed = lifetime_energy(9000.0, 25)
    summed = sum(degraded_energy(9000.0, y) for y in range(1, 26))
    assert closed == pytest.approx(212003.56, abs=0.005)
    assert closed == pytest.approx(summed, rel=1e-9)


def test_pv08_array_rating():
    assert array_rating(14, 430.0) == pytest.approx(6.02)
    assert array_rating(15, 430.0) == pytest.approx(6.45)


# ---------------------------------------------------------------- PV-09 (weather step)

def test_pv09_scenarios_follow_entry():
    assert PV09_SCENARIOS["low"] == {"temperature_row": "glass_polymer_insulated_back", "gamma_per_c": -0.0047}
    assert PV09_SCENARIOS["high"]["temperature_row"] == "glass_polymer_open_rack"
    assert PV09_SCENARIOS["expected"]["temperature_row"] == "glass_glass_close_roof_mount"


def test_pv09_confirmed_ridge_with_weather():
    sigma = weather_sigma(161.0, 7017.0)
    assert sigma == pytest.approx(0.02294, abs=5e-6)
    rng, params = energy_range(11242.0, [10881.0, 11156.0], sigma_w=sigma)
    assert isinstance(rng, Ranged) and rng.unit == "kWh"
    assert rng.low == pytest.approx(10561.0, abs=1.0)
    assert rng.expected == 11242.0
    assert rng.high == pytest.approx(11573.0, abs=1.0)
    assert params["L_in"] == 10881.0 and params["H_in"] == 11242.0


def test_pv09_unconfirmed_ridge_without_weather():
    rng, params = energy_range(11242.0, [10881.0, 11156.0, 9638.0, 9275.0, 8778.0])
    assert (rng.low, rng.expected, rng.high) == (8778.0, 11242.0, 11242.0)
    assert params["weather_step_applied"] is False

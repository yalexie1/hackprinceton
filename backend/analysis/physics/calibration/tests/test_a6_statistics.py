"""A6: the M&V formulas against the worked examples of physics 04 (MV-02, MV-03, MV-04, MV-05)."""
import math

import numpy as np
import pytest

from backend.analysis.physics.calibration import (calibration_ok, choose_degree_day, degree_days, fit_change_point,
                                                  fit_degree_day, fit_statistics, fractional_savings_uncertainty,
                                                  guarantee_level, model_acceptable, predict, savings_uncertainty,
                                                  t_value, y_factor_monthly)
from backend.analysis.physics.calibration.changepoint import DAYS_IN_MONTH, monthly_degree_days

# MV-02 worked example
T = [12, 14, 18, 21, 25, 28, 29, 29, 27, 22, 17, 13]
E = [31.0, 29.2, 30.5, 36.3, 48.4, 54.6, 58.6, 56.8, 52.8, 39.1, 30.6, 29.6]


def test_mv02_change_point_worked_example():
    m = fit_change_point(T, E, "3PC")
    assert m.tb_cool == 18.5
    assert m.b0 == pytest.approx(30.161, abs=5e-4)
    assert m.b1 == pytest.approx(2.632, abs=5e-4)
    assert m.sse == pytest.approx(5.827, abs=5e-4)
    assert m.p == 3 and m.n == 12
    assert m.t_stats[0] == pytest.approx(48.8, abs=0.05)
    # closed-form simple regression at the same change point (the spec's second method)
    x = np.maximum(np.array(T, float) - 18.5, 0.0)
    b1 = np.cov(x, E, bias=True)[0, 1] / np.var(x)
    assert b1 == pytest.approx(m.b1, rel=1e-9)


def test_mv03_fit_statistics_worked_example():
    m = fit_change_point(T, E, "3PC")
    s = fit_statistics(E, predict(m, T), p=3)
    assert s.rmse == pytest.approx(0.805, abs=5e-4)
    assert s.cv_rmse == pytest.approx(0.0194, abs=5e-5)
    assert abs(s.nmbe) < 1e-12 and abs(s.ndbe) < 1e-12
    assert s.r2 == pytest.approx(0.9962, abs=5e-5)
    assert model_acceptable(s, "monthly") == (True, [])


def test_mv04_calibration_ok_uses_femp_equations():
    measured = [100.0] * 12
    ok, s = calibration_ok(measured, [104.0] * 12)
    assert ok and s.p == 0 and s.nmbe == pytest.approx(-0.04)          # model above: negative in MV-03's sign
    assert s.ndbe == pytest.approx(s.nmbe)                               # p = 0: identical (MV-03)
    ok, s = calibration_ok(measured, [106.0] * 12)
    assert not ok and model_acceptable(s)[1][0].startswith("bias")
    zigzag = [120.0, 80.0] * 6                                           # no bias, CV(RMSE) 20 %
    ok, s = calibration_ok(measured, zigzag)
    assert not ok and abs(s.nmbe) < 1e-12 and s.cv_rmse == pytest.approx(0.20)
    # FEMP-MV4 eq. 4-2: divide by the number of points, not n - 1
    assert s.rmse == pytest.approx(20.0)
    ok, _ = calibration_ok(measured, [115.0, 85.0] * 6)                  # CV(RMSE) exactly 15 %: passes
    assert ok
    with pytest.raises(ValueError):
        calibration_ok(measured[:11], measured[:11])


def test_mv04_hourly_tolerance():
    s = fit_statistics([100.0] * 24, [108.0] * 24, p=0)
    assert model_acceptable(s, "hourly")[0] and not model_acceptable(s, "monthly")[0]


def test_mv05_worked_example():
    s = fit_statistics(E, predict(fit_change_point(T, E, "3PC"), T), p=3)
    assert t_value(0.68, 9) == pytest.approx(1.0525, abs=1e-4)
    assert t_value(0.90, 9) == pytest.approx(1.8331, abs=1e-4)
    f = 2276.0 / 15236.4
    assert f == pytest.approx(0.1494, abs=5e-5)
    fsu68 = fractional_savings_uncertainty(s.cv_rmse, 12, 12, 3, f, 0.68)
    fsu90 = fractional_savings_uncertainty(s.cv_rmse, 12, 12, 3, f, 0.90)
    assert fsu68 == pytest.approx(0.05373, abs=5e-5)
    assert fsu90 == pytest.approx(0.0936, abs=5e-4)
    assert fsu68 * 2276.0 == pytest.approx(122, abs=1)
    assert guarantee_level(2276.0, fsu90) == pytest.approx(2063, abs=1)
    assert y_factor_monthly(12) == pytest.approx(1.306, abs=5e-4)
    u = savings_uncertainty(s.cv_rmse, 12, 3, 2276.0, 15236.4)
    assert u.acceptable and u.fsu_68 == pytest.approx(fsu68, rel=1e-3) and u.fsu_90 > u.fsu_68
    assert "can be verified" in u.note


def test_mv05_autocorrelation_widens_and_small_savings_fail():
    base = fractional_savings_uncertainty(0.10, 12, 12, 3, 0.2)
    assert fractional_savings_uncertainty(0.10, 12, 12, 3, 0.2, rho=0.5) > base
    u = savings_uncertainty(0.12, 12, 3, 100.0, 10000.0)        # 1 % saving under a 12 % CV(RMSE)
    assert not u.acceptable and "too small to verify" in u.note
    assert math.isinf(fractional_savings_uncertainty(0.1, 12, 12, 3, 0.0))


def _daily_year():
    d = np.arange(365)
    return 18.0 - 8.0 * np.cos(2 * np.pi * (d - 15) / 365.0)          # coldest mid-January


def test_degree_day_fit_recovers_known_parts():
    daily = _daily_year()
    days = np.array(DAYS_IN_MONTH, float)
    gas = 10.0 * days + 3.0 * monthly_degree_days(daily, 16.0, "heating")
    m = fit_degree_day(gas, daily, "3PH")
    assert m.tb_heat == 16.0
    assert m.base_kwh_per_day == pytest.approx(10.0, abs=1e-6)
    assert m.heat_kwh_per_kday == pytest.approx(3.0, abs=1e-6)
    assert choose_degree_day(gas, daily, "gas").kind == "3PH"
    parts = m.annual_parts(daily)
    assert parts["base"] == pytest.approx(3650.0) and parts["heating"] == pytest.approx(3 * degree_days(daily, 16, "heating"))
    elec = 20.0 * days + 2.0 * monthly_degree_days(daily, 20.0, "cooling") + 1.0 * monthly_degree_days(daily, 14.0, "heating")
    chosen = choose_degree_day(elec, daily, "electricity")
    assert chosen.kind == "5P" and chosen.tb_cool == 20.0 and chosen.tb_heat == 14.0
    flat = 15.0 * days
    assert choose_degree_day(flat, daily, "electricity").kind == "1P"

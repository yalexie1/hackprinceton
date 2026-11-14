"""A2 worked examples of specs/physics/02-thermal-systems.md (ENV, ZON, INF, WIN) and the
published ISO 13790 hourly test cases (physics.md section 5; S2 tests/testRCmodel.py).
"""
import math
import socket

import numpy as np
import pytest

from backend.analysis.physics.zone import (
    assembly_u_value, combine_air_flows, distribute_gains, infiltration_flow_sg, iso_combined_u_value,
    leakage_area_from_ach50, monthly_heating_need, office_infiltration_off, office_occupants_default,
    office_outdoor_air, opaque_solar_gain, outdoor_air_latent_load, parallel_path_u_value, rc_step,
    RCParams, shading_factor, slab_f_factor_coefficient, slab_on_grade_coefficient, sol_air_temperature,
    solve_hour, solve_hour_with_economizer, stack_wind_coefficients, steady_state_h_eff,
    surface_coefficients, transmission_coefficients, ventilation_coefficient, window_solar_gain,
    zone_rc_parameters)
from backend.schema import Ranged, Surface

R_IP = 0.176110      # h ft2 F / Btu -> m2 K / W
U_IP = 5.678263      # Btu/(h ft2 F) -> W/(m2 K)
INF = math.inf


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A2 must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def rel(x, y, tol=1e-3):
    return x == pytest.approx(y, rel=tol)


# ---------- ENV ----------

def test_env01_layers_us_films():
    layers_ip = [0.17, 0.08, 4.0, 0.06, 15.0, 0.45, 0.68]
    assert sum(layers_ip) == pytest.approx(20.44)
    u = assembly_u_value([{"r_m2k_w": r * R_IP} for r in layers_ip], include_films=False)
    assert rel(1 / u, 3.5997) and rel(u, 0.2778)
    assert rel(u, U_IP / 20.44, 1e-5)


def test_env01_iso_films():
    u = assembly_u_value([{"thickness_m": 0.1, "conductivity_w_mk": 0.04}], "horizontal")
    assert u == pytest.approx(1 / (0.13 + 2.5 + 0.04))
    assert assembly_u_value([{"r_m2k_w": 1.0}], "up") == pytest.approx(1 / 1.14)


def test_env02_parallel_path_and_iso_combined():
    u_ip = parallel_path_u_value(20.44, 8.91, 0.25)
    assert u_ip == pytest.approx(0.065, abs=0.001)
    assert rel(u_ip, 0.0648)
    assert rel(parallel_path_u_value(20.44 * R_IP, 8.91 * R_IP, 0.25), 0.3677)
    u_iso = iso_combined_u_value(20.44, 8.91, 0.25, r_homogeneous_m2k_w=5.44, r_insulation_m2k_w=15,
                                 r_wood_m2k_w=3.47)
    assert rel(u_iso, 0.0688) and rel(u_iso * U_IP, 0.3906)
    assert u_iso * U_IP / (u_ip * U_IP) == pytest.approx(1.062, abs=0.001)


def _surf(id, kind, area, u, boundary="exterior", **kw):
    return Surface(id=id, zone_id="z", kind=kind, boundary=boundary, area_m2=area, tilt_deg=90.0,
                   u_value=Ranged(low=u, expected=u, high=u, unit="W/m2K"), **kw)


def test_env03_ua_summation_and_boundaries():
    surfs = [_surf("w", "wall", 95, 0.368), _surf("r", "roof", 120, 0.20), _surf("g", "window", 18, 2.8),
             _surf("d", "door", 3.8, 2.0), _surf("f", "floor", 120, 9.9, boundary="ground")]
    h = transmission_coefficients(surfs)
    assert h["h_tr_w_w_k"] == pytest.approx(58.00)
    assert h["h_tr_op_w_k"] == pytest.approx(58.96)
    assert transmission_coefficients(surfs, 74.32)["h_tr_op_w_k"] == pytest.approx(133.28)
    adj = [_surf("a", "wall", 10, 2.0, boundary="adjacent_conditioned"),
           _surf("b", "wall", 10, 2.0, boundary="adjacent_unconditioned")]
    assert transmission_coefficients(adj)["h_tr_op_w_k"] == pytest.approx(10 / (0.5 + 0.3))


def test_env04_slab():
    r = slab_on_grade_coefficient(120, 44, 0.15)
    assert r["u_w_m2k"] == pytest.approx(0.619342, rel=1e-4)
    assert r["h_g_w_k"] == pytest.approx(74.32, rel=1e-4)
    hi = slab_on_grade_coefficient(120, 44, 0.15, ground_conductivity_w_mk=2.0)
    assert hi["u_w_m2k"] == pytest.approx(0.7762, rel=1e-4) and hi["h_g_w_k"] == pytest.approx(93.15, rel=1e-4)
    assert slab_f_factor_coefficient(44) == pytest.approx(55.59, rel=1e-3)
    # branch d_t >= B': a small, heavily insulated slab, against the second formula by hand
    small = slab_on_grade_coefficient(4.0, 8.0, 0.15, r_floor_m2k_w=5.0)
    d_t = 0.15 + 1.5 * (0.17 + 5.0 + 0.04)
    assert d_t >= 1.0
    assert small["u_w_m2k"] == pytest.approx(1.5 / (0.457 * 1.0 + d_t), rel=1e-4)


def test_env05_sol_air_and_iso_route():
    u, a, te, ti, i = 0.30, 150.0, 32.0, 24.0, 800.0
    for alpha, tsa, phi in [(0.85, 57.22, 1494.9), (0.30, 39.62, 702.9)]:
        t = sol_air_temperature(te, i, alpha, sky_form_factor=1.0)
        assert t == pytest.approx(tsa, abs=0.005)
        sol_air_route = u * a * (t - ti)
        iso_route = u * a * (te - ti) + opaque_solar_gain(u, a, i, alpha, 1.0)
        assert sol_air_route == pytest.approx(phi, abs=0.05)
        assert iso_route == pytest.approx(sol_air_route, rel=1e-9)
    d = opaque_solar_gain(u, a, i, 0.85, 1.0) - opaque_solar_gain(u, a, i, 0.30, 1.0)
    assert d == pytest.approx(792.0)


def test_env05_nonlinear_balance_within_8pct():
    from scipy.optimize import brentq
    u, area, te, ti, i, eps, hc = 0.30, 150.0, 32.0, 24.0, 800.0, 0.9, 20.5
    sigma = 5.67e-8
    tsky = te - 11.0 + 273.15
    for alpha, linear, printed in [(0.85, 1494.9, 1394.7), (0.30, 702.9, 665.5)]:
        def f(ts):
            tk = ts + 273.15
            return (alpha * i + eps * sigma * (tsky ** 4 - tk ** 4) + hc * (te - ts)
                    - (ts - ti) / (1 / u - 0.04))
        ts = brentq(f, -50, 150)
        phi = (ts - ti) / (1 / u - 0.04) * area
        assert phi == pytest.approx(printed, rel=0.01)
        assert abs(linear - phi) / phi < 0.08


def test_env06_coefficients():
    assert surface_coefficients("wall")["h_i_w_m2k"] == pytest.approx(7.692, rel=1e-3)
    assert surface_coefficients("wall", "ashrae")["h_i_w_m2k"] == pytest.approx(8.350, rel=1e-3)
    assert surface_coefficients("roof")["h_e_w_m2k"] == pytest.approx(25.0)
    assert surface_coefficients("window", "ashrae")["h_e_w_m2k"] == pytest.approx(33.40, rel=1e-3)
    assert surface_coefficients("floor")["h_i_w_m2k"] == pytest.approx(1 / 0.17)


# ---------- ZON ----------

HOUSE = zone_rc_parameters(150.0, 133.26, 58.0, "medium")


def test_zon01_parameters():
    p = HOUSE
    assert (p.a_m_m2, p.a_tot_m2, p.c_m_j_k) == (375.0, 675.0, 2.475e7)
    assert p.h_tr_is_w_k == pytest.approx(2328.75) and p.h_tr_ms_w_k == pytest.approx(3412.50)
    assert p.h_tr_em_w_k == pytest.approx(138.675, rel=1e-5)
    assert ventilation_coefficient(0.5 * 375 / 3600) == pytest.approx(62.5)
    with pytest.raises(ValueError):
        zone_rc_parameters(10.0, 1e6, 0.0)
    assert zone_rc_parameters(10.0, 0.0, 5.0).h_tr_em_w_k == 0.0


def test_zon02_distribution():
    g = distribute_gains(600, 1500, 375, 675, 58.0)
    assert g["phi_ia_w"] == pytest.approx(300.0)
    assert g["phi_m_w"] == pytest.approx(1000.0)
    assert g["phi_st_w"] == pytest.approx(783.00, abs=0.005)
    assert 2100 - sum(g.values()) == pytest.approx(17.0, abs=0.05)


def _direct_solve(theta_m_prev, te, ia, st, m, hc, hve, p):
    """Three node balances of ZON-03 solved as a linear system (Crank-Nicolson on the mass)."""
    cap = p.c_m_j_k / 3600
    his, hms, hem, hw = p.h_tr_is_w_k, p.h_tr_ms_w_k, p.h_tr_em_w_k, p.h_tr_w_w_k
    # unknowns: air, surface, m_end; theta_m = (m_end + m_prev)/2
    a = np.array([
        [-(hve + his), his, 0.0],
        [his, -(his + hw + hms), hms / 2],
        [0.0, hms, -cap - (hms + hem) / 2],
    ])
    b = np.array([
        -(hve * te + ia + hc),
        -(hw * te + st) - hms * theta_m_prev / 2,
        -cap * theta_m_prev + (hms + hem) * theta_m_prev / 2 - hem * te - m,
    ])
    air, s, m_end = np.linalg.solve(a, b)
    return air, s, m_end


@pytest.mark.parametrize("te,tm,phi_int,phi_sol,hc", [(34, 26, 600, 1500, -2000.0), (5, 19, 600, 0, 1500.0),
                                                      (10, 22, 10, 2000, 0.0)])
def test_zon03_closed_form_equals_linear_solve(te, tm, phi_int, phi_sol, hc):
    p = HOUSE
    g = distribute_gains(phi_int, phi_sol, p.a_m_m2, p.a_tot_m2, p.h_tr_w_w_k)
    r = rc_step(tm, te, te, g["phi_ia_w"], g["phi_st_w"], g["phi_m_w"], hc, 62.5, p)
    air, s, m_end = _direct_solve(tm, te, g["phi_ia_w"], g["phi_st_w"], g["phi_m_w"], hc, 62.5, p)
    assert r.theta_air_c == pytest.approx(air, rel=1e-9)
    assert r.theta_s_c == pytest.approx(s, rel=1e-9)
    assert r.theta_m_end_c == pytest.approx(m_end, rel=1e-9)
    assert r.theta_op_c == pytest.approx(0.3 * air + 0.7 * s)


# S2 test zone: A_f 34.3, room 7 x 4.9 x 3.1 m, H_tr,em = u_walls x opaque wall = 0.2 x 1.69 (as S2
# defines it), H_ve from 2.0 air changes on 106.33 m3 (the spec prints it rounded, 70.887).
S2 = RCParams(floor_area_m2=34.3, a_m_m2=85.75, a_tot_m2=142.38, c_m_j_k=5_659_500.0,
              h_tr_is_w_k=3.45 * 142.38, h_tr_ms_w_k=9.1 * 85.75, h_tr_em_w_k=0.338, h_tr_w_w_k=14.85)
S2_HVE = 1200.0 * 34.3 * 3.1 * 2.0 / 3600.0


@pytest.mark.parametrize("te,tm,phi_int,phi_sol,phi_pub,tm_pub", [
    (10, 22, 10, 2000, 0.0, 22.33),          # no demand
    (25, 24, 10, 4000, -264.75, 25.15),      # cooling
    (10, 20, 10, 2000, 328.09, 20.46),       # heating
    (30, 25, 10, 5000, -411.6, 26.49),       # cooling at capacity
])
def test_zon04_published_iso13790_cases(te, tm, phi_int, phi_sol, phi_pub, tm_pub):
    assert S2_HVE == pytest.approx(70.887, abs=5e-4)
    r = solve_hour(tm, te, phi_int, phi_sol, 20.0, 26.0, 12 * 34.3, 12 * 34.3, S2_HVE, S2)
    assert round(r.phi_hc_w, 2) == pytest.approx(phi_pub, abs=0.01)
    assert round(r.theta_m_c, 2) == pytest.approx(tm_pub, abs=0.01)


def test_zon04_house_hours():
    c = solve_hour(26, 34, 600, 1500, 20, 25, INF, INF, 62.5, HOUSE)
    assert c.phi_hc_w == pytest.approx(-2888.8, abs=0.05)
    assert c.theta_m_end_c == pytest.approx(26.1926, abs=5e-5)
    assert (c.theta_s_c, c.theta_air_c, c.theta_op_c) == pytest.approx((25.870, 25.000, 25.609), abs=5e-4)
    h = solve_hour(19, 5, 600, 0, 20, 25, INF, INF, 62.5, HOUSE)
    assert h.phi_hc_w == pytest.approx(2377.0, abs=0.05)
    assert h.theta_m_end_c == pytest.approx(18.8947, abs=5e-5)
    assert h.theta_s_c == pytest.approx(19.253, abs=5e-4)
    # direct solve with the air held at the setpoint and the power unknown
    g = distribute_gains(600, 0, HOUSE.a_m_m2, HOUSE.a_tot_m2, HOUSE.h_tr_w_w_k)
    lo = rc_step(19, 5, 5, g["phi_ia_w"], g["phi_st_w"], g["phi_m_w"], 0.0, 62.5, HOUSE).theta_air_c
    hi = rc_step(19, 5, 5, g["phi_ia_w"], g["phi_st_w"], g["phi_m_w"], 1000.0, 62.5, HOUSE).theta_air_c
    assert 1000.0 * (20 - lo) / (hi - lo) == pytest.approx(h.phi_hc_w, rel=1e-9)


def test_zon04_off_conventions():
    r = solve_hour(19, 5, 600, 0, -50, 80, INF, INF, 62.5, HOUSE)
    assert r.phi_hc_w == 0.0


def test_zon05_steady_state_identity():
    h_eff = steady_state_h_eff(62.5, HOUSE)
    assert h_eff == pytest.approx(239.2440, rel=1e-6)
    tm = 20.0
    for _ in range(3000):
        r = solve_hour(tm, 5.0, 0.0, 0.0, 20.0, 80.0, INF, INF, 62.5, HOUSE)
        tm = r.theta_m_end_c
    assert r.phi_hc_w == pytest.approx(h_eff * 15.0, rel=1e-6)
    assert r.phi_hc_w == pytest.approx(3588.660, abs=5e-4)


def test_zon06_monthly_worked_example_and_hourly_month():
    m = monthly_heating_need(253.76, 20.0, 10.0, 744, 600.0, 250.0, HOUSE.c_m_j_k)
    assert m["tau_h"] == pytest.approx(27.09, abs=0.005)
    assert m["a"] == pytest.approx(2.806, abs=5e-4)
    assert m["q_ht_kwh"] == pytest.approx(1888.0, abs=0.05)
    assert m["q_gn_kwh"] == pytest.approx(632.4)
    assert m["gamma"] == pytest.approx(0.3350, abs=5e-5)
    assert m["eta"] == pytest.approx(0.9686, abs=5e-5)
    assert m["q_h_nd_kwh"] == pytest.approx(1275.4, abs=0.05)
    # the hourly model on the same month, +/- 6 K daily swing, same mean gains
    hours = np.arange(744 + 336)
    te = 10.0 + 6.0 * np.sin(2 * np.pi * (hours % 24 - 9) / 24)
    tm, total = 20.0, 0.0
    for k, t in enumerate(te):
        r = solve_hour(tm, float(t), 600.0, 250.0, 20.0, 80.0, INF, INF, 62.5, HOUSE)
        tm = r.theta_m_end_c
        if k >= 336:
            total += max(r.phi_hc_w, 0.0) / 1000
    assert abs(total - m["q_h_nd_kwh"]) / total < 0.15
    assert total == pytest.approx(1191.4, rel=0.02)
    assert monthly_heating_need(253.76, 20.0, 25.0, 744, 600, 250, HOUSE.c_m_j_k)["q_h_nd_kwh"] == 0.0


# ---------- INF ----------

def test_inf01():
    q = 0.5 * 375 / 3600
    assert q == pytest.approx(0.05208, abs=5e-6)
    assert ventilation_coefficient(q) == pytest.approx(62.50)


def test_inf02_leakage_area():
    assert leakage_area_from_ach50(7, 375) * 1e4 == pytest.approx(546.9, abs=0.05)
    assert leakage_area_from_ach50(7, 375, 0.60) * 1e4 == pytest.approx(620.5, abs=0.05)
    assert leakage_area_from_ach50(7, 375, 0.70) * 1e4 == pytest.approx(482.0, abs=0.05)


@pytest.mark.parametrize("dt,v,q,ach", [(15, 3.0, 0.03050, 0.293), (8, 4.0, 0.02906, 0.279),
                                        (0, 2.0, 0.01115, 0.107)])
def test_inf03_sherman_grimsrud(dt, v, q, ach):
    a_l = leakage_area_from_ach50(7, 375)
    got = infiltration_flow_sg(a_l, 20 + dt, 20, v, stories=1, shelter_class=4)
    assert got == pytest.approx(q, rel=1e-3)
    assert got * 3600 / 375 == pytest.approx(ach, abs=5e-4)


def test_inf03_stack_coefficient_identity():
    r, x, h, t, g = 0.5, 0.0, 2.5, 295.0, 9.81
    fs = ((1 + r / 2) / 3) * (1 - x ** 2 / (2 - r) ** 2) ** 1.5 * math.sqrt(g * h / t)
    assert fs == pytest.approx(0.1201, abs=5e-5)
    assert (0.1 * fs) ** 2 == pytest.approx(stack_wind_coefficients(1, 4)[0], rel=0.01)
    assert stack_wind_coefficients(5, 3) == (0.000435, 0.000271)


def test_inf04_combination():
    assert combine_air_flows(0.0305, exhaust_m3_s=0.025) == pytest.approx(0.03944, abs=5e-6)
    assert combine_air_flows(0.0305) == pytest.approx(0.0305)
    assert combine_air_flows(0.0305, 0.02, 0.02) == pytest.approx(0.0505)


ENV_AREA = 2 * (4 * math.sqrt(500) * 3) + 500     # 1036.66 m2, the area the worked values use


def test_inf05_office():
    n = office_occupants_default(500)
    assert n == pytest.approx(26.9, abs=0.05)
    q_oa = n * 0.00944
    assert q_oa == pytest.approx(0.2539, abs=5e-5)
    assert ventilation_coefficient(q_oa) == pytest.approx(304.7, abs=0.05)
    assert ENV_AREA == pytest.approx(1036.6, abs=0.1)
    assert 7.5 * (4 / 75) ** 0.65 == pytest.approx(1.1159, abs=5e-5)
    assert office_infiltration_off(ENV_AREA) == pytest.approx(1.1567, abs=5e-4)
    on = office_outdoor_air(n, ENV_AREA, True)
    assert on - q_oa == pytest.approx(0.2892, abs=5e-4)
    assert office_outdoor_air(n, ENV_AREA, False) == pytest.approx(1.1567, abs=5e-4)


@pytest.mark.parametrize("te,without,with_,q_between", [(15.0, -2445.3, 0.0, 0.7695),
                                                        (20.5, -7568.1, 0.0, 2.3450),
                                                        (30.0, -16416.6, -16416.6, None)])
def test_inf06_economizer(te, without, with_, q_between):
    a = 500.0
    wall = 4 * math.sqrt(a) * 3
    p = zone_rc_parameters(a, 0.7 * wall * 0.852 + a * 0.375, 0.3 * wall * 6.93)
    assert p.h_tr_w_w_k == pytest.approx(557.8, abs=0.1) and p.h_tr_em_w_k > 0
    q_min = office_outdoor_air(office_occupants_default(a), ENV_AREA, True)
    assert q_min == pytest.approx(0.5431, abs=5e-5)
    r0 = solve_hour(24.5, te, 12000, 6000, 21, 24, INF, INF, ventilation_coefficient(q_min), p)
    assert r0.phi_hc_w == pytest.approx(without, abs=0.1)
    r = solve_hour_with_economizer(24.5, te, 12000, 6000, 21, 24, INF, INF, p, q_min, 2.5, 21.0)
    assert r["phi_hc_w"] == pytest.approx(with_, abs=0.1)
    if q_between is not None:
        assert q_min < r["flow_m3_s"] < 2.5
        assert r["flow_m3_s"] == pytest.approx(q_between, abs=5e-5)
        assert r["theta_air_c"] == pytest.approx(24.0, abs=0.001)
    else:
        assert r["flow_m3_s"] == q_min and not r["economizer"]


def test_inf07_latent():
    assert outdoor_air_latent_load(0.05, 0.0180, 0.0093) == pytest.approx(1305.0)
    assert outdoor_air_latent_load(0.05, 0.0080) == 0.0
    assert 1200 * 0.05 * 8 == pytest.approx(480.0)


# ---------- WIN ----------

def test_win01_window_gain():
    solar = window_solar_gain(2.0, 0.60, 500.0, 2.8, shading_factor=0.70, sky_form_factor=0.0)
    assert solar == pytest.approx(378.0)
    a_sol = 0.70 * (0.9 * 0.60) * 2.0
    assert a_sol * 500 == pytest.approx(378.0)
    net = window_solar_gain(2.0, 0.60, 500.0, 2.8, shading_factor=0.70)
    assert solar - net == pytest.approx(5.54, abs=0.005)
    assert net == pytest.approx(372.5, abs=0.05)


def test_win02_shading():
    assert shading_factor("light_blinds_closed", shgc=0.60) == pytest.approx(0.498)
    assert shading_factor("medium_shades", shgc=0.60) == pytest.approx(0.836)
    assert shading_factor("light_curtains", shgc=0.60) == pytest.approx(0.794)
    film = 0.70 * shading_factor(exterior_type="solar_film")
    screen = 0.70 * shading_factor(exterior_type="solar_screen")
    assert window_solar_gain(2.0, 0.60, 500.0, 2.8, shading_factor=film, sky_form_factor=0) == pytest.approx(264.6)
    assert window_solar_gain(2.0, 0.60, 500.0, 2.8, shading_factor=screen, sky_form_factor=0) == pytest.approx(113.4)
    assert shading_factor() == 1.0

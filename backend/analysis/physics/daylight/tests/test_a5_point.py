"""A5 point scoring: score_point on the reference room R0 and on the three fixtures."""
import math
import socket
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from backend.schema import (BuildingModel, DeskScore, Floor, Opening, PropertyBundle, Ranged, Room,
                            Surface, Vertex, WallEdge)
from backend.analysis.physics.daylight import (desk_score_fields, occupied_mask_from_stamps,
                                               prepare_room, resolve_assumptions, score_point,
                                               sun_arrays)

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"
NO_OBSTRUCTION = {"site.obstruction_angle_deg": 0.0}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A5 tests must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def synthetic_year(lat=34.0, winter_t=5.0):
    """8760 hour-ending local stamps of 2023 and a simple sun (Cooper declination, solar time =
    clock time). A test input only, not a climate model."""
    stamps = np.datetime64("2023-01-01T01:00") + np.arange(8760).astype("timedelta64[h]")
    hours = np.arange(8760) + 0.5 - 1.0          # hour midpoint, hours since Jan 1 00:00
    doy = hours // 24 + 1
    hour_of_day = hours % 24
    dec = math.radians(23.45) * np.sin(2 * np.pi * (284 + doy) / 365)
    ha = np.radians(15 * (hour_of_day - 12))
    phi = math.radians(lat)
    sin_alt = np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.cos(ha)
    alt = np.degrees(np.arcsin(sin_alt))
    cos_az = (np.sin(dec) - sin_alt * np.sin(phi)) / (np.cos(np.radians(alt)) * np.cos(phi))
    az = np.degrees(np.arccos(np.clip(cos_az, -1, 1)))
    az = np.where(ha > 0, 360 - az, az)
    up = alt > 0
    dni = np.where(up, 900 * np.exp(-0.2 / np.maximum(sin_alt, 0.05)), 0.0)
    dhi = np.where(up, 60 + 80 * np.maximum(sin_alt, 0), 0.0)
    t_out = winter_t + 10 * (1 - np.cos(2 * np.pi * (doy - 15) / 365)) + 4 * np.sin(2 * np.pi * (hour_of_day - 9) / 24)
    return dict(altitude_deg=alt, azimuth_deg=az, dni_w_m2=dni, dhi_w_m2=dhi,
                ghi_w_m2=dni * np.maximum(sin_alt, 0) + dhi, t_out_c=t_out, rh_pct=np.full(8760, 50.0),
                stamps=stamps)


SUN = synthetic_year()


def box_room(width=4.0, depth=6.0, height=2.8, window_az_true=180.0, opening=None):
    """R0 (section 0.6) as contract objects: window wall along y = 0, model +y = north."""
    op = opening or Opening(id="op1", type="window", width_m=2.0, height_m=1.5, lower_elevation_m=0.9,
                            relative_center=0.5)
    fl = Floor(id="f1", label="1", vertices=[Vertex(id="a", x=0, y=0), Vertex(id="b", x=width, y=0),
                                             Vertex(id="c", x=width, y=depth), Vertex(id="d", x=0, y=depth)],
               edges=[WallEdge(id="e1", type="wall", vertex_ids=("a", "b"), openings=[op]),
                      WallEdge(id="e2", type="wall", vertex_ids=("b", "c")),
                      WallEdge(id="e3", type="wall", vertex_ids=("c", "d")),
                      WallEdge(id="e4", type="wall", vertex_ids=("d", "a"))])
    room = Room(id="r0", floor_id="f1", height_m=height, boundary_edge_ids=["e1", "e2", "e3", "e4"],
                polygon=[(0, 0), (width, 0), (width, depth), (0, depth)])
    win = Surface(id="surf_win", zone_id="z", kind="window", boundary="exterior",
                  area_m2=op.width_m * op.height_m, azimuth_deg=window_az_true, tilt_deg=90,
                  u_value=Ranged(low=2.8, expected=2.8, high=2.8, unit="W/m2K"),
                  shgc=Ranged(low=0.6, expected=0.6, high=0.6, unit="-"),
                  source_edge_id="e1", source_opening_id=op.id)
    return room, fl, [win]


def test_r0_daylight_factor_at_p_and_f():
    room, fl, surfaces = box_room()
    p = score_point(room, surfaces, 2.0, 2.0, SUN, 21.0, floor=fl, assumptions=NO_OBSTRUCTION)
    c = p["df_components"]
    assert c["sc"] == pytest.approx(0.019944, rel=1e-3)
    assert c["irc_sky"] == pytest.approx(0.003738, rel=1e-3)
    assert c["irc_ground"] == pytest.approx(0.001620, rel=1e-3)
    assert p["daylight_factor"] == pytest.approx(2.53, abs=0.005)
    f = score_point(room, surfaces, 2.0, 5.0, SUN, 21.0, floor=fl, assumptions=NO_OBSTRUCTION)
    assert f["daylight_factor"] == pytest.approx(0.69, abs=0.01)
    assert p["window_source"] == "measured"
    DeskScore(**desk_score_fields(p))


def test_window_beats_point_six_metres_in():
    """Workplan A5 acceptance: beside the window more daylight than 6 m into the room."""
    room, fl, surfaces = box_room(depth=8.0)
    near = score_point(room, surfaces, 2.0, 0.6, SUN, 21.0, floor=fl)
    deep = score_point(room, surfaces, 2.0, 6.0, SUN, 21.0, floor=fl)
    assert near["daylight_factor"] > deep["daylight_factor"]
    assert near["daylight"] > deep["daylight"]
    assert near["cda_300"] > deep["cda_300"]


def test_low_expected_high_ordering():
    room, fl, surfaces = box_room()
    r = {c: score_point(room, surfaces, 2.0, 2.0, SUN, 21.0, floor=fl, case=c) for c in ("low", "expected", "high")}
    assert r["low"]["daylight_factor"] <= r["expected"]["daylight_factor"] <= r["high"]["daylight_factor"]
    assert r["low"]["daylight"] <= r["expected"]["daylight"] <= r["high"]["daylight"]
    assert resolve_assumptions(None, "low")["site.obstruction_angle_deg"] == 30.0
    # a contract Assumption with a numerically ordered Ranged is flipped for the obstruction angle
    from backend.schema import Assumption
    a = Assumption(key="site.obstruction_angle_deg", label="x", source="user", confidence=1,
                   value=Ranged(low=0, expected=5, high=20, unit="deg"))
    assert resolve_assumptions([a], "low")["site.obstruction_angle_deg"] == 20
    assert resolve_assumptions([a], "high")["site.obstruction_angle_deg"] == 0


def test_glare_view_direction_and_south_window():
    room, fl, surfaces = box_room(window_az_true=180.0)
    r = score_point(room, surfaces, 2.0, 1.0, SUN, 21.0, floor=fl, assumptions=NO_OBSTRUCTION)
    assert r["view_azimuth_deg"] in (pytest.approx(90.0), pytest.approx(270.0))
    assert r["glare_risk_facing_window"] >= r["glare_risk"]
    assert r["direct_sun_hours"] > 0
    assert 0 <= r["glare_risk"] <= 1
    # a north window at 34 N sees almost no direct sun
    room_n, fl_n, surf_n = box_room(window_az_true=0.0)
    rn = score_point(room_n, surf_n, 2.0, 1.0, SUN, 21.0, floor=fl_n, north_offset_deg=180.0,
                     assumptions=NO_OBSTRUCTION)
    assert rn["direct_sun_hours"] < r["direct_sun_hours"]


def test_comfort_near_cold_glass():
    room, fl, surfaces = box_room()
    cold = synthetic_year(winter_t=-15.0)
    near = score_point(room, surfaces, 2.0, 0.6, cold, 21.0, floor=fl)
    far = score_point(room, surfaces, 2.0, 5.0, cold, 21.0, floor=fl)
    assert near["max_dt_pr_k"] > far["max_dt_pr_k"] > 0
    assert 5.0 <= far["comfort_ppd"] <= 100 and 5.0 <= near["comfort_ppd"] <= 100
    # A2-style zone output: theta_air_c and mode arrays
    zone = dict(theta_air_c=np.full(8760, 21.0), mode=np.where(cold["t_out_c"] < 15, "heating", "cooling"))
    z = score_point(room, surfaces, 2.0, 2.0, cold, zone, floor=fl)
    assert 5.0 <= z["comfort_ppd"] <= 100
    sp = score_point(room, surfaces, 2.0, 2.0, cold, dict(setpoint_heat_c=21.0, setpoint_cool_c=24.0), floor=fl)
    assert any("active setpoint" in w for w in sp["warnings"])
    with pytest.raises(ValueError):
        score_point(room, surfaces, 2.0, 2.0, cold, None, floor=fl)


def test_context_reuse_and_errors():
    room, fl, surfaces = box_room()
    ctx = prepare_room(room, surfaces, floor=fl)
    a = score_point(room, surfaces, 1.5, 2.5, SUN, 21.0, context=ctx)
    b = score_point(room, surfaces, 1.5, 2.5, SUN, 21.0, floor=fl)
    for k in ("daylight", "glare_risk", "comfort_ppd", "score", "daylight_factor"):
        assert a[k] == pytest.approx(b[k], rel=1e-12)
    with pytest.raises(ValueError):
        score_point(room, surfaces, 9.0, 2.0, SUN, 21.0, context=ctx)
    other = Room(id="other", floor_id="f1", polygon=room.polygon)
    with pytest.raises(ValueError):
        score_point(other, surfaces, 1.0, 1.0, SUN, 21.0, context=ctx)
    with pytest.raises(ValueError):
        score_point(room, surfaces, 1.0, 1.0, SUN, 21.0)          # no floor
    h = score_point(room, surfaces, 1.5, 2.5, SUN, 21.0, context=ctx, return_hourly=True)["hourly"]
    assert h["e_in_lux"].shape == (8760,) and np.isnan(h["pmv"]).sum() == 8760 - 2600


def test_sun_inputs():
    assert occupied_mask_from_stamps(SUN["stamps"]).sum() == 2600        # 260 weekdays of 2023
    s = sun_arrays(SUN)
    assert s.occupied.sum() == 2600 and s.i0_w_m2.shape == (8760,)
    # attribute names of a climate object (as A1's ClimateHours carries them)
    obj = SimpleNamespace(sun_elevation_deg=SUN["altitude_deg"], sun_azimuth_deg=SUN["azimuth_deg"],
                          dni_w_m2=SUN["dni_w_m2"], dhi_w_m2=SUN["dhi_w_m2"], ghi_w_m2=SUN["ghi_w_m2"],
                          temp_c=SUN["t_out_c"], e0n_w_m2=np.full(8760, 1361.0), stamps=SUN["stamps"],
                          weather=SimpleNamespace(rh_pct=np.full(8760, 50.0)))
    s2 = sun_arrays(obj)
    assert np.all(s2.i0_w_m2 == 1361.0) and s2.occupied.sum() == 2600
    with pytest.raises(ValueError):
        sun_arrays({"altitude_deg": [1.0]})


def test_relative_center_reading_moves_the_window():
    op = Opening(id="op1", type="window", width_m=1.2, height_m=1.2, lower_elevation_m=0.9, relative_center=0.2)
    room, fl, surfaces = box_room(width=5.0, opening=op)
    first = score_point(room, surfaces, 1.0, 1.5, SUN, 21.0, floor=fl)
    second = score_point(room, surfaces, 1.0, 1.5, SUN, 21.0, floor=fl, relative_center_from="second")
    assert first["df_components"]["sc"] > second["df_components"]["sc"]
    assert first["df_components"]["irc_sky"] == pytest.approx(second["df_components"]["irc_sky"])


@pytest.mark.parametrize("folder, source", [("house", {"measured", "vision"}), ("office", {"measured", None}),
                                            ("office_houston", {"vision"})])
def test_fixtures_score_every_room(folder, source):
    b = PropertyBundle.model_validate_json((EXAMPLES / folder / "property_bundle.json").read_text())
    m = BuildingModel.model_validate_json((EXAMPLES / folder / "building_model.json").read_text())
    fl = {f.id: f for f in b.matterport.floors}
    seen = set()
    for room in b.matterport.rooms:
        ctx = prepare_room(room, m.surfaces, floor=fl[room.floor_id], assumptions=m.assumptions)
        cx = sum(p[0] for p in room.polygon) / len(room.polygon)
        cy = sum(p[1] for p in room.polygon) / len(room.polygon)
        r = score_point(room, m.surfaces, cx, cy, SUN, 22.0, context=ctx)
        seen.add(r["window_source"])
        d = DeskScore(**desk_score_fields(r))
        assert 0 <= d.daylight <= 1 and 0 <= d.glare_risk <= 1 and 5 <= d.comfort_ppd <= 100
        assert 0 <= d.score <= 1
        if ctx.windows:
            assert ctx.north_offset_deg == pytest.approx(m.north_offset_deg.expected, abs=0.05)
    assert seen == source


def test_mode_off_clothing_follows_the_outdoor_temperature_rule():
    # CMF-08: when the zone neither heats nor cools, T_out < 15 picks the heating clothing
    room, fl, surfaces = box_room()
    cold = synthetic_year(winter_t=-15.0)
    theta = np.full(8760, 21.0)
    by_rule = np.where(cold["t_out_c"] < 15, "heating", "cooling")
    off = score_point(room, surfaces, 2.0, 2.0, cold, dict(theta_air_c=theta, mode=np.full(8760, "off")), floor=fl)
    ruled = score_point(room, surfaces, 2.0, 2.0, cold, dict(theta_air_c=theta, mode=by_rule), floor=fl)
    assert off["comfort_ppd"] == pytest.approx(ruled["comfort_ppd"])

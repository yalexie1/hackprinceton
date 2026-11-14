"""A15 acceptance: shade_panels on map-coordinate roofs with walls, trees and the fixtures."""
from __future__ import annotations

import json
import math
import socket
from pathlib import Path

import numpy as np
import pytest

from backend.analysis.solar.shading import Obstruction, shade_panels
from backend.analysis.solar.shading.geometry import EARTH_RADIUS_M
from backend.schema import BuildingModel, MeasureResult, PanelPlacement, Ranged, RoofPlane, VexcelDetection

EX = Path(__file__).resolve().parents[5] / "specs" / "examples"
LON0, LAT0 = -118.0, 34.0
EAVE_M = 3.0


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def ll(x: float, y: float) -> tuple[float, float]:
    k = math.pi / 180.0 * EARTH_RADIUS_M
    return LON0 + x / (k * math.cos(math.radians(LAT0))), LAT0 + y / k


def rect_wkt(x0, y0, x1, y1) -> str:
    pts = [ll(x0, y0), ll(x1, y0), ll(x1, y1), ll(x0, y1), ll(x0, y0)]
    return "POLYGON((" + ", ".join(f"{a:.10f} {b:.10f}" for a, b in pts) + "))"


def plane(tilt=20.0, az=180.0, source="splat", obstructions=()) -> RoofPlane:
    return RoofPlane(id="p", polygon_wkt=rect_wkt(-5, -5, 5, 5), area_m2=100.0 / math.cos(math.radians(tilt)),
                     tilt_deg=Ranged(low=tilt, expected=tilt, high=tilt, unit="deg"), azimuth_deg=az,
                     usable_area_m2=80.0, obstructions=list(obstructions), geometry_source=source)


PANEL = PanelPlacement(plane_id="p", polygon_wkt=rect_wkt(-0.5, -0.85, 0.5, 0.85),
                       annual_kwh=0.0, shading_loss_fraction=0.0)
SOUTH_WALL = Obstruction(rect_wkt(-30, -8.2, 30, -8.0), height_m=12.0, label="wall")
# Winter noon at latitude 34 N: zenith 34 + 23.44 = 57.44 deg, sun due south.
WINTER_NOON = ([57.44], [180.0])
POA = {"p": {"poa_beam": np.array([600.0]), "poa_sky_diffuse": np.array([120.0]),
             "poa_sky_circumsolar": np.array([40.0]), "poa_ground": np.array([10.0])}}


def run(obstructions=(), sunpos=WINTER_NOON, poa=POA, **kw):
    pl = kw.pop("roof", None) or plane()
    return shade_panels([pl], [PANEL], *sunpos, poa_components=poa, obstructions=obstructions,
                        eave_height_m=EAVE_M, origin=(LON0, LAT0), n_el=18, n_az=72, **kw)


def test_wall_due_south_shades_at_winter_noon_and_not_without_it():
    with_wall = run([SOUTH_WALL]).panels[0]
    assert with_wall.ray_cast
    assert with_wall.beam_shading_fraction[0] == 1.0
    assert with_wall.diffuse_shading_factor < 1.0
    assert with_wall.shading_loss_fraction > 0.0
    assert with_wall.shading_factor[0] == pytest.approx(with_wall.shading_loss_fraction)
    none = run([]).panels[0]
    assert none.beam_shading_fraction[0] == 0.0
    assert none.diffuse_shading_factor == 1.0
    assert none.shading_loss_fraction == 0.0


def test_no_obstructions_zero_loss_over_a_day():
    zen = [80.0, 65.0, 57.44, 65.0, 80.0, 100.0]
    azi = [125.0, 150.0, 180.0, 210.0, 235.0, 270.0]
    h = len(zen)
    poa = {"p": {"poa_beam": np.full(h, 300.0), "poa_sky_diffuse": np.full(h, 80.0),
                 "poa_ground": np.full(h, 5.0)}}
    r = run([], (zen, azi), poa).panels[0]
    assert np.all(r.beam_shading_fraction == 0.0)
    assert np.all(r.shading_factor == 0.0)
    assert r.shading_loss_fraction == 0.0


def test_tree_east_shades_morning_only():
    # 4 m x 4 m box with a 9 m2 mask, 6 m east of the panel, 10 m tall
    tree = VexcelDetection(label="tree", confidence=0.5, image_id="ortho-1",
                           bbox_wkt=rect_wkt(4, -2, 8, 2), mask_area_m2=9.0)
    zen, azi = [70.0, 70.0, 57.44, 70.0], [95.0, 110.0, 180.0, 265.0]
    r = shade_panels([plane(obstructions=[tree])], [PANEL], zen, azi,
                     obstruction_heights_m={"tree": 10.0}, eave_height_m=EAVE_M,
                     origin=(LON0, LAT0), n_el=18, n_az=72)
    fb = r.panels[0].beam_shading_fraction
    assert fb[0] > 0.0 and fb[1] > 0.0
    assert fb[2] == 0.0 and fb[3] == 0.0
    # a tree without a height is not cast and a warning says so
    r2 = shade_panels([plane(obstructions=[tree])], [PANEL], zen, azi, origin=(LON0, LAT0), n_el=18, n_az=72)
    assert np.all(r2.panels[0].beam_shading_fraction == 0.0)
    assert any("no height for 'tree'" in w for w in r2.warnings)


def test_deterministic():
    a = run([SOUTH_WALL]).panels[0]
    b = run([SOUTH_WALL]).panels[0]
    assert np.array_equal(a.beam_shading_fraction, b.beam_shading_fraction)
    assert a.diffuse_shading_factor == b.diffuse_shading_factor
    assert a.shading_loss_fraction == b.shading_loss_fraction


def test_parametric_plane_keeps_default():
    r = run([], roof=plane(source="vexcel_parametric"))
    p = r.panels[0]
    assert not p.ray_cast and p.shading_loss_fraction == 0.03 and p.pv_kwargs() == {}
    assert any("PV-04 default" in w for w in r.warnings)


def test_obstructions_need_eave_height():
    with pytest.raises(ValueError):
        shade_panels([plane()], [PANEL], *WINTER_NOON, obstructions=[SOUTH_WALL], origin=(LON0, LAT0))


def test_pvlib_day_wall_south():
    """A full winter day at Los Angeles with pvlib sun positions and Perez components."""
    pvlib = pytest.importorskip("pvlib")
    pd = pytest.importorskip("pandas")
    times = pd.date_range("2024-12-21 06:00", "2024-12-21 18:00", freq="1h", tz="Etc/GMT+8")
    sp = pvlib.solarposition.get_solarposition(times, LAT0, LON0)
    cs = pvlib.location.Location(LAT0, LON0).get_clearsky(times, model="haurwitz")
    dni_dhi = pvlib.irradiance.erbs(cs["ghi"], sp["apparent_zenith"], times)
    perez = pvlib.irradiance.perez(20, 180, dni_dhi["dhi"], dni_dhi["dni"],
                                   pvlib.irradiance.get_extra_radiation(times),
                                   sp["apparent_zenith"], sp["azimuth"],
                                   pvlib.atmosphere.get_relative_airmass(sp["apparent_zenith"]),
                                   return_components=True)
    aoi = pvlib.irradiance.aoi(20, 180, sp["apparent_zenith"], sp["azimuth"])
    poa = {"p": {"poa_beam": (dni_dhi["dni"] * np.maximum(np.cos(np.radians(aoi)), 0)).to_numpy(),
                 "poa_sky_diffuse": perez["poa_sky_diffuse"].fillna(0).to_numpy(),
                 "poa_sky_circumsolar": perez["poa_circumsolar"].fillna(0).to_numpy(),
                 "poa_ground": pvlib.irradiance.get_ground_diffuse(20, cs["ghi"]).to_numpy()}}
    sunpos = (sp["apparent_zenith"].to_numpy(), sp["azimuth"].to_numpy())
    shaded = run([SOUTH_WALL], sunpos, poa).panels[0]
    clear = run([], sunpos, poa).panels[0]
    noon = int(np.argmin(sunpos[0]))
    assert shaded.beam_shading_fraction[noon] == 1.0
    assert 0.0 < shaded.shading_loss_fraction <= 1.0
    assert clear.shading_loss_fraction == 0.0


@pytest.mark.parametrize("flavor", ["house", "office", "office_houston"])
def test_fixtures_run(flavor):
    model = BuildingModel.model_validate_json((EX / flavor / "building_model.json").read_text())
    measures = json.loads((EX / flavor / "measures.json").read_text())
    pv = [MeasureResult.model_validate(m) for m in (measures if isinstance(measures, list) else measures["measures"])
          if m.get("solar")][0]
    panels = pv.solar.panels
    zen, azi = np.array([60.0, 40.0, 60.0]), np.array([120.0, 180.0, 240.0])
    poa = {p.id: {"poa_beam": np.full(3, 500.0), "poa_sky_diffuse": np.full(3, 100.0),
                  "poa_sky_circumsolar": np.full(3, 30.0), "poa_ground": np.full(3, 5.0)}
           for p in model.roof_planes}
    r = shade_panels(model.roof_planes, panels, zen, azi, poa_components=poa, n_el=9, n_az=36)
    assert len(r.panels) == len(panels)
    for p in r.panels:
        assert 0.0 <= p.shading_loss_fraction <= 1.0
        assert p.beam_shading_fraction.shape == (3,)
    placed = r.placements(panels)
    assert all(isinstance(p, PanelPlacement) for p in placed)
    if flavor == "house":
        assert all(p.ray_cast for p in r.panels)
        assert any("no height for 'tree'" in w for w in r.warnings)
    else:
        assert not any(p.ray_cast for p in r.panels)

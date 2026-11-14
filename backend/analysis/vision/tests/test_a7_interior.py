"""A7 interior vision (workplan 4.2): a hand-written reply -> assumptions, no network.

Fixture roles (corrected A7 row): the house's wall graph has window openings, so no window size
is written there; the two offices have none, so window count and size come from vision.
"""
import json
import socket
from pathlib import Path

import pytest

from backend.schema import Assumption, PropertyBundle, Ranged
from backend.analysis.vision import (REPLY_SCHEMA, build_prompt, observe_interior, parse_reply,
                                     read_interior, select_panos)

EXAMPLES = Path(__file__).resolve().parents[4] / "specs" / "examples"
SIZE_KEYS = ("window.area_m2", "window.count")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A7 tests must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def bundle(folder):
    return PropertyBundle.model_validate_json((EXAMPLES / folder / "property_bundle.json").read_text())


def fake_bytes(path):
    return b"\xff\xd8 synthetic " + path.encode()       # never sponsor imagery


REPLY = {
    "windows": {"visible": True, "count": 3, "total_area_m2": 8.0, "frame": "metal",
                "panes": "single", "low_e": "no", "shading": "interior_blinds",
                "confidence": 0.7, "note": "aluminium sliders, one reflection"},
    "hvac": {"system_type": "central_ac_furnace", "cues": ["ceiling_diffuser", "thermostat"],
             "thermostat": "programmable", "heating_fuel": "gas", "age_band": "1992_2005",
             "confidence": 0.6, "note": "registers and a wall thermostat"},
    "water_heater": {"visible": True, "type": "storage", "fuel": "gas", "confidence": 0.8,
                     "note": "tank with a flue in a closet"},
    "lighting": {"fixture_type": "fluorescent_t8", "fixture_count": 6, "confidence": 0.75,
                 "note": "2x4 troffers"},
}


class Recorder:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def __call__(self, images, prompt):
        assert images and all(isinstance(b, bytes) for b in images)
        self.calls.append((len(images), prompt))
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def by_key(assumptions):
    return {a.key: a for a in assumptions}


@pytest.mark.parametrize("folder", ["house", "office", "office_houston"])
def test_reply_maps_to_all_four_targets(folder):
    ask = Recorder(REPLY)
    assumptions, flags = observe_interior(bundle(folder), ask, fake_bytes)
    keys = by_key(assumptions)
    assert flags == []
    assert len(ask.calls) == len(bundle(folder).matterport.panos)
    assert all(n == 5 for n, _ in ask.calls)          # up and four sides, no floor face
    for target in ("window.type", "hvac.system_type", "dhw.type", "lighting.fixture_type"):
        assert target in keys, target
    for a in assumptions:
        assert isinstance(a, Assumption) and a.source == "vision"
        assert any(e.kind == "pano" for e in a.evidence), a.key
        assert 0 < a.confidence <= 0.8
    assert keys["window.type"].value == "single_clear_metal"
    assert keys["window.shading"].value == "interior_blinds"
    assert keys["hvac.heating_fuel"].value == "gas"
    assert keys["hvac.thermostat_type"].value == "programmable"
    assert keys["hvac.install_year"].value == Ranged(low=1992, expected=1999, high=2005, unit="year")
    assert keys["dhw.fuel"].value == "gas"


def test_house_has_measured_windows_so_no_window_size():
    keys = by_key(observe_interior(bundle("house"), Recorder(REPLY), fake_bytes)[0])
    assert not any(k in keys for k in SIZE_KEYS)
    assert not any(k.startswith("window.") and k.endswith(".area_m2") for k in keys)
    cross = [e.note for e in keys["window.type"].evidence if e.kind == "default_table"][0]
    assert "cross-check only" in cross
    assert "lighting.lpd" not in keys                # homes use LGT-01, not a density


def test_house_room_fallback_names_the_bedroom_only():
    # opt-in: rooms without window openings in a model that has some (house building_model.json)
    keys = by_key(observe_interior(bundle("house"), Recorder(REPLY), fake_bytes, room_fallback=True)[0])
    rooms = [k for k in keys if k.startswith("window.") and k.endswith(".area_m2")]
    assert rooms == ["window.room_bedroom.area_m2"]
    a = keys["window.room_bedroom.area_m2"]
    assert a.value == Ranged(low=5.6, expected=8.0, high=10.4, unit="m2")
    assert [e.ref for e in a.evidence if e.kind == "pano"] == ["pano_03"]


@pytest.mark.parametrize("folder,rooms_seen", [("office", 6), ("office_houston", 4)])
def test_office_window_count_and_size_from_vision(folder, rooms_seen):
    b = bundle(folder)
    keys = by_key(observe_interior(b, Recorder(REPLY), fake_bytes)[0])
    # 3 windows, 8 m2 per panorama; every fixture panorama is its own view (rooms or > 6 m apart)
    assert keys["window.count"].value.expected == 3 * rooms_seen
    area = keys["window.area_m2"]
    assert area.source == "vision" and area.confidence <= 0.5
    assert area.value.expected == pytest.approx(8.0 * rooms_seen)
    assert area.value.low == pytest.approx(0.7 * area.value.expected)
    assert area.value.high == pytest.approx(1.3 * area.value.expected)
    assert {e.ref for e in area.evidence if e.kind == "pano"} == {p.id for p in b.matterport.panos}
    lpd = keys["lighting.lpd"]
    assert lpd.value == Ranged(low=10.76, expected=19.48, high=19.48, unit="W/m2")


@pytest.mark.parametrize("reply", [
    "", "not json", "I see a window.", "[]", "null", '{"windows": {}}', "{'windows': 1}",
    json.dumps({k: "x" for k in REPLY}),
    json.dumps({k: {"confidence": 2.0, "visible": True} for k in REPLY}),
    json.dumps(REPLY)[:-5],
])
@pytest.mark.parametrize("folder", ["house", "office"])
def test_malformed_reply_gives_nothing_and_no_exception(folder, reply):
    assumptions, flags = observe_interior(bundle(folder), Recorder(reply), fake_bytes)
    assert assumptions == [] and flags == []


def test_model_or_asset_failure_gives_nothing():
    def boom(images, prompt):
        raise RuntimeError("provider down")

    def missing(path):
        raise FileNotFoundError(path)

    assert observe_interior(bundle("office"), boom, fake_bytes) == ([], [])
    ask = Recorder(REPLY)
    assert observe_interior(bundle("office"), ask, missing) == ([], [])
    assert ask.calls == []
    r = read_interior(bundle("office"), None, None)
    assert r.assumptions == [] and "vintage defaults" in r.warnings[0]


def test_code_fence_and_bad_fields_are_tolerated():
    reply = dict(REPLY, windows=dict(REPLY["windows"], frame="unobtainium", panes="double",
                                     low_e="yes"),
                 hvac=dict(REPLY["hvac"], system_type="unknown"),
                 water_heater={"visible": False, "confidence": 0.9})
    text = "```json\n" + json.dumps(reply) + "\n```"
    r = parse_reply("pano_01", text)
    assert r is not None and "frame" not in r.windows.fields
    keys = by_key(observe_interior(bundle("office"), Recorder(text), fake_bytes)[0])
    assert keys["window.type"].value == "double_clear_non_metal"   # frame unknown: non-metal row
    assert "hvac.system_type" not in keys                            # unknown is not written
    assert not any(k.startswith("dhw.") for k in keys)               # no heater seen
    assert "hvac.thermostat_type" in keys


def test_low_e_double_non_metal_and_led_office():
    reply = dict(REPLY, windows=dict(REPLY["windows"], frame="vinyl", panes="double", low_e="yes"),
                 lighting=dict(REPLY["lighting"], fixture_type="led"))
    keys = by_key(observe_interior(bundle("office_houston"), Recorder(reply), fake_bytes)[0])
    assert keys["window.type"].value == "double_lowe_non_metal"
    assert keys["lighting.lpd"].value == Ranged(low=6.5, expected=10.76, high=10.76, unit="W/m2")


def test_max_panos_one_per_room_first_and_prompt_schema():
    b = bundle("office")
    picked = select_panos(b, 2)
    assert len(picked) == 2
    ask = Recorder(REPLY)
    observe_interior(b, ask, fake_bytes, max_panos=2)
    assert len(ask.calls) == 2
    prompt = build_prompt(b.matterport.panos[0], "office")
    for key in REPLY_SCHEMA["required"]:
        assert f'"{key}"' in prompt
    assert "pano_01" in prompt


def test_two_panoramas_close_together_in_one_room_count_once():
    b = bundle("office_houston")                # no openings, so vision counts the windows
    p4 = next(p for p in b.matterport.panos if p.id == "pano_04")
    p4.x, p4.y = 10.0, 3.0                      # 2 m from pano_01, both in room_plate
    keys = by_key(observe_interior(b, Recorder(REPLY), fake_bytes)[0])
    assert keys["window.count"].value.expected == 9
    assert keys["window.area_m2"].value.expected == pytest.approx(24.0)

"""A8 feasibility cues (workplan 4.2): hand-written replies -> flags and vision assumptions.

No network, synthetic image bytes only. The flag keys are checked against the fixtures, never
imported from sibling folders.
"""
import json
import socket
from pathlib import Path

import pytest

from backend.schema import Flag, PropertyBundle, Ranged
from backend.analysis.vision import REPLY_SCHEMA, build_prompt, observe_interior, parse_reply

EXAMPLES = Path(__file__).resolve().parents[4] / "specs" / "examples"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A8 tests must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def bundle(folder):
    return PropertyBundle.model_validate_json((EXAMPLES / folder / "property_bundle.json").read_text())


def fake_bytes(path):
    return b"\x89PNG synthetic " + path.encode()


BASE = {
    "windows": {"visible": False, "confidence": 0.5},
    "hvac": {"confidence": 0.5},
    "water_heater": {"visible": False, "confidence": 0.5},
    "lighting": {"confidence": 0.5},
}
NOTHING = {"outlets": [], "panel_visible": False, "panel_type": "unknown",
           "main_breaker_amps": None, "wall_material": "unknown", "water_heater_space": "unknown",
           "confidence": 0.6, "note": "no outlet or panel in view"}


def reply(**feas):
    return json.dumps(dict(BASE, feasibility=dict(NOTHING, **feas)))


def run(folder, text):
    a, f = observe_interior(bundle(folder), lambda images, prompt: text, fake_bytes)
    return {x.key: x for x in a}, {x.key: x for x in f}


def fixture_flag_keys():
    keys = set()
    for p in EXAMPLES.glob("*/building_model.json"):
        keys |= {f["key"] for f in json.loads(p.read_text())["flags"]}
    return keys


def test_two_prong_gives_likely_upgrade_with_cost():
    a, f = run("house", reply(outlets=["two_prong"], confidence=0.7, note="bedroom outlets"))
    e = f["electrical.service"]
    assert e.status == "likely_upgrade"
    c = e.added_cost_usd
    assert c is not None and c.unit == "USD" and 0 < c.low <= c.expected <= c.high
    assert all(ev.kind == "pano" for ev in e.evidence) and e.evidence
    amps = a["electrical.service_amps"]
    assert amps.source == "vision" and amps.value == Ranged(low=60, expected=100, high=200, unit="A")
    assert amps.confidence == 0.3
    assert a["electrical.outlet_type"].value == "two_prong"


def test_nothing_visible_gives_unknown_without_cost():
    a, f = run("house", reply())
    assert f["electrical.service"].status == "unknown"
    assert f["electrical.service"].added_cost_usd is None
    assert "dhw.space" not in f
    assert a == {}


def test_cue_changes_range_and_confidence_only_and_source_is_vision():
    a2, _ = run("house", reply(outlets=["two_prong"], confidence=0.7))
    a3, f3 = run("house", reply(outlets=["three_prong", "gfci"], confidence=0.7))
    x, y = a2["electrical.service_amps"], a3["electrical.service_amps"]
    assert (x.key, x.label, x.source) == (y.key, y.label, y.source) == (
        "electrical.service_amps", "Main electrical service size", "vision")
    assert x.value != y.value and x.confidence != y.confidence
    assert f3["electrical.service"].status == "unknown"
    assert f3["electrical.service"].added_cost_usd.low == 0
    for folder in ("house", "office", "office_houston"):
        for text in (reply(outlets=["two_prong"], wall_material="plaster"),
                     reply(panel_visible=True, panel_type="breaker_panel", main_breaker_amps=200),
                     reply(panel_visible=True, panel_type="fuse_box")):
            a, _ = run(folder, text)
            assert a and all(v.source == "vision" and v.confidence <= 0.8 for v in a.values())


@pytest.mark.parametrize("feas,status,cost", [
    (dict(panel_visible=True, panel_type="breaker_panel", main_breaker_amps=200), "likely_ok", False),
    (dict(panel_visible=True, panel_type="breaker_panel", main_breaker_amps=60), "likely_upgrade", True),
    (dict(panel_visible=True, panel_type="breaker_panel", main_breaker_amps=125), "unknown", True),
    (dict(panel_visible=True, panel_type="breaker_panel"), "unknown", True),
    (dict(panel_visible=True, panel_type="fuse_box"), "likely_upgrade", True),
    (dict(panel_visible=True, panel_type="switchgear_room"), "likely_ok", False),
    # a legible 200 A panel outranks two-prong outlets
    (dict(panel_visible=True, panel_type="breaker_panel", main_breaker_amps=200,
          outlets=["two_prong"]), "likely_ok", False),
])
def test_main_panel(feas, status, cost):
    a, f = run("house", reply(**feas))
    e = f["electrical.service"]
    assert e.status == status
    assert (e.added_cost_usd is not None) == cost
    if feas.get("main_breaker_amps"):
        v = a["electrical.service_amps"].value
        assert v.low == v.expected == v.high == feas["main_breaker_amps"]


def test_hard_walls_add_routing_cost_and_era_cue():
    a, f = run("house", reply(outlets=["two_prong"]))
    a2, f2 = run("house", reply(outlets=["two_prong"], wall_material="plaster"))
    assert f2["electrical.service"].added_cost_usd.expected > f["electrical.service"].added_cost_usd.expected
    assert f2["electrical.service"].status == "likely_upgrade"
    w = a2["wall.material"]
    assert w.value == "plaster" and w.source == "vision"
    assert "1950" in w.evidence[0].note


@pytest.mark.parametrize("space,status", [("small_closet_conditioned", "blocked"),
                                          ("garage", "likely_ok")])
def test_dhw_space(space, status):
    _, f = run("house", reply(water_heater_space=space))
    assert f["dhw.space"].status == status


def test_keys_are_those_the_fixtures_use():
    _, f = run("house", reply(outlets=["two_prong"], water_heater_space="small_closet_conditioned"))
    assert set(f) <= fixture_flag_keys()
    house = {x["key"]: x for x in json.loads(
        (EXAMPLES / "house" / "building_model.json").read_text())["assumptions"]}
    a, _ = run("house", reply(outlets=["two_prong"]))
    fx = house["electrical.service_amps"]
    assert a["electrical.service_amps"].value == Ranged(**fx["value"])
    assert a["electrical.service_amps"].source == fx["source"]
    for x in f.values():
        Flag.model_validate(x.model_dump())


@pytest.mark.parametrize("text", [
    json.dumps(dict(BASE, feasibility="two prong")),
    json.dumps(dict(BASE, feasibility={"outlets": ["two_prong"]})),            # no confidence
    json.dumps(dict(BASE, feasibility={"outlets": ["two_prong"], "confidence": 3})),
    reply(outlets=["two_prong"])[:-7],
    "two-prong outlets everywhere",
    "",
    None,
])
def test_malformed_feasibility_gives_no_flag_and_no_exception(text):
    a, f = observe_interior(bundle("house"), lambda images, prompt: text, fake_bytes)
    assert f == []
    assert not any(k.startswith(("electrical.", "wall.material")) for k in (x.key for x in a))


def test_bad_fields_dropped_and_reply_without_section_gives_no_flag():
    text = reply(outlets=["two_prong", "four_prong", 3], panel_type="nuclear", main_breaker_amps=-5)
    r = parse_reply("pano_01", text)
    assert r.feasibility.fields["outlets"] == ["two_prong"]
    assert "panel_type" not in r.feasibility.fields and "main_breaker_amps" not in r.feasibility.fields
    _, f = run("house", text)
    assert f["electrical.service"].status == "likely_upgrade"
    assert run("house", json.dumps(BASE))[1] == {}          # registry's own unknown stands


def test_one_call_per_panorama_and_prompt_asks_for_feasibility():
    b = bundle("house")
    calls = []

    def ask(images, prompt):
        assert all(isinstance(x, bytes) for x in images)
        calls.append(prompt)
        return reply(outlets=["two_prong"])
    observe_interior(b, ask, fake_bytes)
    assert len(calls) == len(b.matterport.panos)
    p = build_prompt(b.matterport.panos[0], "home")
    assert '"feasibility"' in p and '"main_breaker_amps"' in p and "two_prong" in p
    assert "feasibility" in REPLY_SCHEMA["properties"] and "feasibility" not in REPLY_SCHEMA["required"]

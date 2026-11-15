"""Issue 392: once vision is on, observe_interior reads the panoramas and never falls back to the example's
invented observations; panoramas are capped and spread across rooms."""
import json
from types import SimpleNamespace

import pytest

from backend import config
from backend.analysis import api
from backend.schema import Pano, PropertyBundle

from .test_wiring import FLAVORS, load  # noqa: F401  (also pulls in the no-network guard)


@pytest.fixture(autouse=True)
def vision_off_after():
    yield
    api.set_vision(None, None)


def _with_panos(bundle, n):
    rooms = bundle.matterport.rooms
    panos = [Pano(id=f"p{i}", x=0, y=0, z=1.5, face_paths=[f"data/cache/x/p{i}/face{k}.jpg" for k in range(6)])
             for i in range(n)]
    return bundle.model_copy(update={"matterport": bundle.matterport.model_copy(update={"panos": panos})}), rooms


@pytest.mark.parametrize("flavor", FLAVORS)
def test_with_vision_on_a_demo_property_never_gets_the_example_observations(flavor):
    bundle, _ = load(flavor)
    example, _ = _example_of(flavor)
    assert example                                         # the fixture does carry invented observations
    api.set_vision(ask_model=lambda *a: "not json", get_bytes=lambda p: b"x")   # the model is useless
    got, flags = api.observe_interior(bundle)
    assert not ({a.key for a in got} & {a.key for a in example if a.source == "vision"})
    assert got == [] or all(a.source == "vision" for a in got)


@pytest.mark.parametrize("flavor", FLAVORS)
def test_a_failing_image_reader_still_gives_no_example_observations(flavor):
    bundle, _ = load(flavor)
    example, _ = _example_of(flavor)

    def boom(path):
        raise FileNotFoundError(path)
    api.set_vision(ask_model=lambda *a: "{}", get_bytes=boom)
    got, _ = api.observe_interior(bundle)
    assert [a.key for a in got] != [a.key for a in example]


def test_without_vision_the_example_is_used_as_before():
    bundle, _ = load("house")
    assert api.observe_interior(bundle)[0]


def test_panoramas_are_capped_and_the_count_is_logged(caplog):
    bundle, _ = load("house")
    big, _ = _with_panos(bundle, 100)
    asked = []
    api.set_vision(ask_model=lambda imgs, prompt: asked.append(1) or "{}", get_bytes=lambda p: b"x")
    with caplog.at_level("INFO", logger="backend.analysis.api"):
        api.observe_interior(big)
    assert len(asked) == config.VISION_MAX_PANOS == 40
    assert "reading 40 of 100 panoramas" in caplog.text


def test_spread_panos_keeps_every_pano_and_interleaves_rooms():
    bundle, _ = load("house")
    big, _ = _with_panos(bundle, 30)
    out = api.spread_panos(big, 40)
    assert sorted(p.id for p in out.matterport.panos) == sorted(p.id for p in big.matterport.panos)


def _example_of(flavor):
    m = json.loads((api._EXAMPLES / flavor / "building_model.json").read_text())
    from backend.schema import Assumption, Flag
    return ([Assumption.model_validate(a) for a in m["assumptions"]],
            [Flag.model_validate(f) for f in m["flags"]])

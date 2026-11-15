"""Retired measures are left out of plans entirely by default, and come back with the switch."""
import json
from pathlib import Path

import pytest

from backend.analysis import api
from backend.analysis.measures.engine import RETIRED_ENV, RETIRED_MEASURES, offered
from backend.schema import PropertyBundle, RunRequest

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"


def _load(flavor):
    bundle = PropertyBundle.model_validate(json.loads((EXAMPLES / flavor / "property_bundle.json").read_text()))
    request = RunRequest.model_validate(json.loads((EXAMPLES / flavor / "run_request.json").read_text()))
    return bundle, request


def test_offered_follows_the_switch(monkeypatch):
    monkeypatch.delenv(RETIRED_ENV, raising=False)
    assert not any(offered(m) for m in RETIRED_MEASURES)
    assert offered("PV_ROOF") and offered("LGT_LED")
    monkeypatch.setenv(RETIRED_ENV, "1")
    assert all(offered(m) for m in RETIRED_MEASURES)


@pytest.mark.parametrize("flavor", ["house", "office"])
def test_plan_never_mentions_a_retired_measure(monkeypatch, flavor):
    monkeypatch.delenv(RETIRED_ENV, raising=False)
    api._EVAL_CACHE.clear()
    bundle, request = _load(flavor)
    plan = api.build_plan(bundle, api.build_building_model(bundle), request)
    mentioned = ({i.measure.measure_id for i in plan.selected} | {s.measure_id for s in plan.skipped}
                 | {m.measure_id for m in plan.financeable})
    assert not mentioned & RETIRED_MEASURES
    assert mentioned, "the plan still considers the measures that are offered"

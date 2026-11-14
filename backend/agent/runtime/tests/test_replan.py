"""G11: adjust and re-run. A lower budget gives a new done event and a RunResult whose plan has the
new budget; an override that is not an assumption of the model is refused."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agent import analysis_stub
from backend.agent.runtime import RunStore, execute_run
from backend.agent.runtime.replan import PatchError, patch_request, replan, validate_patch
from backend.schema import RunRequest, RunResult

EX = Path(__file__).resolve().parents[4] / "specs" / "examples"
DOORS = SimpleNamespace(analysis=analysis_stub)


def finished_run(tmp_path, flavor="house"):
    """A done run on disk, as the runtime leaves it: run files plus result.json."""
    example = json.loads((EX / flavor / "run_result.json").read_text())
    bundle = json.loads((EX / flavor / "property_bundle.json").read_text())
    store = RunStore(tmp_path)
    files = store.files("run_x")
    for name, content in (("bundle.json", bundle), ("model.json", example["building_model"]),
                          ("baseline.json", example["baseline"]), ("measures.json", example["measures"]),
                          ("plan.json", example["plan"]), ("report.md", example["narrative_md"])):
        files.write(name, content)
    result = RunResult.model_validate({**example, "run_id": "run_x"})
    store.save("run_x", result)
    return store, files, result


def test_a_lower_budget_gives_a_new_done_event_and_a_plan_with_that_budget(tmp_path):
    store, files, result = finished_run(tmp_path)
    new, events = replan(result, files, store, DOORS, budget_usd=500.0)
    assert new.status == "done" and new.plan.budget_usd == 500.0 and new.request.budget_usd == 500.0
    assert events[-1].type == "done" and events[0].type == "stage_started"
    assert any(e.type == "tool_call" and e.payload["name"] == "set_budget" for e in events)
    assert any(e.type == "tool_call" and e.payload["name"] == "build_plan" for e in events)
    assert store.load("run_x") == new                                    # saved, and it validates
    assert json.loads(files.path("plan.json").read_text())["budget_usd"] == 500.0
    RunResult.model_validate_json(new.model_dump_json())


def test_an_override_rebuilds_the_model_with_the_user_value(tmp_path):
    store, files, result = finished_run(tmp_path)
    key = "occupancy.count"
    new, events = replan(result, files, store, DOORS, overrides={key: 5.0})
    a = next(a for a in new.building_model.assumptions if a.key == key)
    assert (a.value.low, a.value.expected, a.value.high) == (5.0, 5.0, 5.0) and a.source == "user"
    assert new.request.overrides[key] == 5.0 and result.request.overrides.get(key) != 5.0
    assert [e.payload["args"]["key"] for e in events if e.payload.get("name") == "set_assumption"] == [key]


def test_a_key_that_is_not_an_assumption_is_refused_and_nothing_changes(tmp_path):
    store, files, result = finished_run(tmp_path)
    before = store.load("run_x").model_dump_json()
    with pytest.raises(PatchError) as err:
        replan(result, files, store, DOORS, overrides={"not.an.assumption": 1.0})
    assert err.value.status == 422 and err.value.code == "unknown_assumption"
    assert store.load("run_x").model_dump_json() == before


@pytest.mark.parametrize("patch,status,code", [
    ({"overrides": {"geometry.ceiling_height_m": 3.0}}, 422, "not_editable"),          # measured
    ({"overrides": {"occupancy.count": "many"}}, 422, "invalid_override"),              # wrong kind
    ({"overrides": {"hvac.thermostat_type": 4.0}}, 422, "invalid_override"),
    ({"budget_usd": -5.0}, 422, "invalid_budget"),
    ({}, 422, "empty_patch"),
])
def test_refused_patches(tmp_path, patch, status, code):
    _, _, result = finished_run(tmp_path)
    with pytest.raises(PatchError) as err:
        validate_patch(result, patch.get("budget_usd"), patch.get("overrides"))
    assert (err.value.status, err.value.code) == (status, code)


def test_only_a_finished_run_can_be_adjusted(tmp_path):
    _, _, result = finished_run(tmp_path)
    for status in ("running", "waiting_for_user", "error"):
        with pytest.raises(PatchError) as err:
            validate_patch(result.model_copy(update={"status": status}), 100.0, None)
        assert (err.value.status, err.value.code) == (409, "run_not_done")


def test_the_summary_text_is_kept_and_flagged_when_it_no_longer_matches(tmp_path):
    store, files, result = finished_run(tmp_path)
    new, _ = replan(result, files, store, DOORS, budget_usd=500.0)
    assert new.narrative_md == result.narrative_md
    assert any(w.startswith("re-run:") and "not regenerated" in w for w in new.warnings)
    again, _ = replan(new, files, store, DOORS, budget_usd=400.0)
    assert sum(w.startswith("re-run:") for w in again.warnings) == 1       # not stacked


def test_patch_request_merges_overrides_and_keeps_the_rest():
    request = RunRequest.model_validate_json((EX / "house" / "run_request.json").read_text())
    new = patch_request(request, 99.0, {"occupancy.count": 7.0})
    assert new.budget_usd == 99.0 and new.overrides["occupancy.count"] == 7.0 and new.sid == request.sid
    assert patch_request(request, None, None) == request


def test_the_rerun_is_deterministic(tmp_path):
    store, files, result = finished_run(tmp_path)
    a, ea = replan(result, files, store, DOORS, budget_usd=500.0)
    store2, files2, result2 = finished_run(tmp_path / "again")
    b, eb = replan(result2, files2, store2, DOORS, budget_usd=500.0)
    assert a.model_dump_json() == b.model_dump_json() and [e.model_dump() for e in ea] == [e.model_dump() for e in eb]

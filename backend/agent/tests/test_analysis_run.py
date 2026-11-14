"""Real analysis (mode = "analysis"): the audit without the agent. Offline: the example bundle through the data
door, the real analysis door where the plan matters, and no model anywhere."""
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agent import api, live
from backend.agent.narrative import analysis_report, check_narrative
from backend.agent.tools import Doors
from backend.schema import PropertyBundle, RunRequest, RunResult

EX = Path(__file__).resolve().parents[3] / "specs" / "examples"


def request(flavor="house", **update):
    base = RunRequest.model_validate_json((EX / flavor / "run_request.json").read_text())
    return base.model_copy(update={"mode": "analysis", **update})


def real_doors():
    from backend.analysis import api as analysis
    from backend.data_layer import api as data
    from backend.legal import api as legal
    return Doors(data=data, analysis=analysis, legal=legal)


@pytest.fixture
def analysis_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAYER_LIVE", "0")              # the example bundle through the data door: no network
    monkeypatch.setattr(live, "_load_env", lambda: None)
    monkeypatch.setattr(live, "SETTINGS", live.LiveSettings(doors=real_doors(), runs_dir=tmp_path))
    return tmp_path


def finish(run_id, timeout=120):
    run = live._RUNS[run_id]
    end = time.time() + timeout
    while not run.closed and time.time() < end:
        time.sleep(0.1)
    run._thread.join(timeout=10)
    assert run.closed, "the run did not finish"
    return run


def test_a_real_analysis_run_reaches_done_with_a_plan_and_says_how(analysis_mode):
    run_id = api.start_run(request())
    assert run_id.startswith("run_") and not run_id.startswith("run_demo")
    run = finish(run_id)
    result = api.get_run(run_id)
    assert result.status == "done" and result.plan is not None and result.baseline is not None
    assert result.served_by == "analysis" and result.data_source == "example"      # offline data here, and it says so
    events = run.events
    assert events[-1].type == "done" and not any(e.type == "question" for e in events)
    assert {"stage_started", "stage_done", "tool_call", "partial_result"} <= {e.type for e in events}
    tools = [e.payload["name"] for e in events if e.type == "tool_call"]
    assert tools[0] == "get_property_bundle" and "build_plan" in tools and "run_baseline" in tools
    assert run.usage == {} and not (live.demo_dir() / result.property.sid).exists()   # no model, and not recorded


def test_the_report_is_a_template_of_the_runs_own_figures_and_passes_the_check(analysis_mode):
    run_id = api.start_run(request())
    finish(run_id)
    result = api.get_run(run_id)
    bundle = PropertyBundle.model_validate(live._RUNS[run_id].files.read_json("bundle.json"))
    assert result.narrative_md.startswith("## Audit summary (real analysis)")
    assert check_narrative(result.narrative_md, result, bundle, result.building_model) == []
    for needle in ("operations first, then load reduction, then equipment", "solar last",
                   "uncalibrated estimate", "example property data"):
        assert needle in result.narrative_md, needle
    for w in result.warnings:                                  # every warning is carried
        assert w in result.narrative_md, w


def test_the_same_property_at_two_budgets_gives_two_different_plans(analysis_mode):
    small, big = api.start_run(request(budget_usd=10_000.0)), api.start_run(request(budget_usd=60_000.0))
    finish(small), finish(big)
    plans = {api.get_run(i).request.budget_usd: api.get_run(i).plan for i in (small, big)}
    chosen = {b: [i.measure.measure_id for i in p.selected] for b, p in plans.items()}
    assert chosen[10_000.0] != chosen[60_000.0], chosen
    assert "PV_ROOF" in chosen[60_000.0] and "PV_ROOF" not in chosen[10_000.0]
    assert plans[60_000.0].total_upfront_usd.expected > plans[10_000.0].total_upfront_usd.expected
    assert api.get_run(big).narrative_md != api.get_run(small).narrative_md


def test_a_run_can_be_adjusted_after_it_finishes_like_any_other(analysis_mode):
    run_id = api.start_run(request(budget_usd=10_000.0))
    finish(run_id)
    api.update_run(run_id, budget_usd=60_000.0)
    assert "PV_ROOF" in [i.measure.measure_id for i in api.get_run(run_id).plan.selected]
    assert api.get_run(run_id).served_by == "analysis"


def test_a_failing_step_ends_the_run_in_error_and_says_which(analysis_mode, monkeypatch):
    doors = real_doors()
    monkeypatch.setattr(doors.analysis, "run_baseline", lambda *a, **k: (_ for _ in ()).throw(ValueError("no weather")),
                        raising=True)
    monkeypatch.setattr(live, "SETTINGS", live.LiveSettings(doors=doors, runs_dir=analysis_mode))
    run_id = api.start_run(request())
    run = finish(run_id)
    result = api.get_run(run_id)
    assert result.status == "error" and run.events[-1].type == "error"
    assert any("run_baseline failed" in w and "no weather" in w for w in result.warnings)


def test_asking_for_real_analysis_without_its_keys_is_a_loud_503_not_a_fallback(monkeypatch, tmp_path):
    for key in live.LIVE_DATA_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("DATA_LAYER_LIVE", raising=False)
    monkeypatch.setattr(live, "_load_env", lambda: None)
    monkeypatch.setattr(live, "SETTINGS", None)
    from backend.server import app
    r = TestClient(app).post("/api/runs", json=request().model_dump(mode="json"))
    assert r.status_code == 503 and r.json()["error"]["code"] == "live_data_unavailable"
    assert "MATTERPORT_API_KEY" in r.json()["error"]["message"]


def test_no_key_value_reaches_the_files_events_or_result_of_a_real_analysis_run(analysis_mode, monkeypatch):
    secrets = {"EIA_API_KEY": "sentinel-eia-1a2b", "MATTERPORT_API_KEY": "sentinel-mp-3c4d",
               "MATTERPORT_API_TOKEN": "sentinel-mt-5e6f", "VEXCEL_API_KEY": "sentinel-vx-7a8b"}
    for k, v in secrets.items():
        monkeypatch.setenv(k, v)
    run_id = api.start_run(request())
    run = finish(run_id)
    text = json.dumps([e.model_dump(mode="json") for e in run.events]) + api.get_run(run_id).model_dump_json()
    assert not [v for v in secrets.values() if v in text]
    leaked = [str(p) for p in Path(analysis_mode).rglob("*") if p.is_file()
              and any(v.encode() in p.read_bytes() for v in secrets.values())]
    assert not leaked, leaked


def test_the_report_template_alone_passes_the_check_for_every_example(analysis_mode):
    for flavor in ("house", "office", "office_houston"):
        result = RunResult.model_validate_json((EX / flavor / "run_result.json").read_text())
        bundle = PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())
        report = analysis_report(result)
        assert check_narrative(report, result, bundle, result.building_model) == [], flavor

import asyncio
import json
from pathlib import Path

import pytest

from backend.agent import api
from backend.schema import DocumentDraft, DocumentRequest, RunEvent, RunRequest, RunResult

EX = Path(__file__).resolve().parents[3] / "specs" / "examples"


@pytest.mark.parametrize("flavor", ["house", "office"])
def test_start_stream_get(flavor):
    req = RunRequest.model_validate_json((EX / flavor / "run_request.json").read_text())
    run_id = api.start_run(req)

    async def collect():
        return [e async for e in api.stream_events(run_id)]

    events = asyncio.run(collect())
    expected = json.loads((EX / flavor / "run_events.json").read_text())
    assert [e.model_dump(mode="json") for e in events] == [RunEvent.model_validate(e).model_dump(mode="json") for e in expected]
    assert events[-1].type == "done"
    result = api.get_run(run_id)
    RunResult.model_validate(result.model_dump(mode="json"))
    assert result.run_id == run_id and result.request.sid == req.sid


def test_unknown_run_raises():
    with pytest.raises(KeyError):
        api.get_run("nope")


def test_answer_update_and_documents():
    req = RunRequest.model_validate_json((EX / "house" / "run_request.json").read_text())
    run_id = api.start_run(req)
    api.answer(run_id, "q1", "yes")
    api.update_run(run_id, budget_usd=1234.0, overrides={"occupancy.count": 5.0})
    assert api.get_run(run_id).request.budget_usd == 1234.0
    dreq = DocumentRequest.model_validate_json((EX / "house" / "document_request.json").read_text())
    dreq.run_id = run_id
    draft = api.draft_document(dreq)
    DocumentDraft.model_validate(draft.model_dump(mode="json"))
    assert api.get_document(run_id, draft.doc_id) == draft
    with pytest.raises(KeyError):
        api.get_document(run_id, "missing")


# ---------- a recorded run answers the request that was made (#362) ----------

#: The example files, under the names a recording uses. Building the recording here rather than
#: reading the developer's (`conftest` points AGENT_DEMO_DIR at an empty temp dir on purpose)
#: keeps these tests the same on every machine - which is the whole point, since the bug they
#: cover only shows up for a property that *has* a recording.
_AS_RECORDED = {"property_bundle.json": "bundle.json", "building_model.json": "model.json",
                "baseline_result.json": "baseline.json", "measures.json": "measures.json",
                "plan.json": "plan.json"}


def recorded_house(flavor: str = "house") -> RunRequest:
    """Write a recording of the house example into the demo dir, and return its own request."""
    from backend.agent.live import demo_dir

    example = EX / flavor
    result = json.loads((example / "run_result.json").read_text())
    folder = demo_dir() / result["property"]["sid"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "result.json").write_text(json.dumps(result))
    (folder / "events.json").write_text((example / "run_events.json").read_text())
    for src, dst in _AS_RECORDED.items():
        (folder / dst).write_text((example / src).read_text())
    (folder / "report.md").write_text(result.get("narrative_md") or "# Recorded run\n")
    return RunRequest.model_validate(result["request"])


def test_a_recorded_run_reports_the_budget_that_was_asked_for():
    """Vignesha's bug. `start_run` overwrote only `run_id`, so a recorded run returned the
    recording's own request: asking for $10,000,000 was answered with the $15,000 the recording
    was made with, and from the outside that is indistinguishable from a broken input field."""
    saved = recorded_house()
    request = saved.model_copy(update={"budget_usd": 10_000_000.0})
    result = api.get_run(api.start_run(request))
    assert result.request.budget_usd == 10_000_000.0


def test_a_bigger_budget_on_a_recorded_run_really_buys_more():
    """Carrying the request is not enough on its own - a result saying $10,000,000 above a plan
    built for $15,000 is a worse lie than the one it replaces. The plan is rebuilt for real."""
    saved = recorded_house()
    small = api.get_run(api.start_run(saved))
    large = api.get_run(api.start_run(saved.model_copy(update={"budget_usd": 10_000_000.0})))

    chosen = lambda r: [i.measure.measure_id for i in (r.plan.selected if r.plan else [])]
    assert len(chosen(large)) > len(chosen(small)), (chosen(small), chosen(large))
    assert set(chosen(small)) <= set(chosen(large)), "the cheaper plan's measures should survive"


def test_a_request_the_recording_cannot_answer_is_declared():
    """Role and desks change which measures apply at all, so they cannot be re-planned. Saying
    nothing would let the demo show an owner's plan under the word "tenant"."""
    saved = recorded_house()
    other = "tenant" if saved.role != "tenant" else "landlord"
    result = api.get_run(api.start_run(saved.model_copy(update={"role": other})))

    assert result.request.role == other
    said = [w for w in result.warnings if "does not answer part of what was asked" in w]
    assert len(said) == 1 and f"role {other!r}" in said[0]
    assert "real analysis" in said[0], "the warning says what to do instead"


def test_a_request_identical_to_the_recording_is_not_warned_about():
    """The warning is about a difference. A caller who asked for exactly what was recorded has
    nothing to be told, and a spurious warning there would train a reader to ignore them."""
    result = api.get_run(api.start_run(recorded_house()))
    assert not [w for w in result.warnings if "does not answer part of what was asked" in w]

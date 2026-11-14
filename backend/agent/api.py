"""Run door of the agent lane (workplan 3.5). Imported only by backend/server.py.

Two modes, chosen per run by the env var AGENT_MODE (read at `start_run`, default replay):
- replay: every function replays the fixtures in specs/examples/ behind the final
  signatures (the G0 behaviour; any example folder with a run_result.json is recognised).
- live: `start_run` drives the deep agent through the run runtime (backend/agent/live.py);
  `answer` resumes a paused run with Command(resume={"value": v}).
A run belongs to the mode it started in; the other functions find it in either registry.

Confirmed against the installed deepagents 0.7.38 (G0, 2026-11-14):
- create_deep_agent(model, tools, *, system_prompt, middleware, subagents, skills,
  memory, permissions, backend, interrupt_on, response_format, state_schema,
  context_schema, checkpointer, store, debug, name, cache). SPEC 8 names match:
  subagents, interrupt_on and checkpointer are keyword arguments.
- SPEC 8 [U] note 1 (subagents cannot delegate further): not tested here, it needs a model.
- SPEC 8 [U] note 2 (TodoListMiddleware may need adding explicitly): a source search of
  the installed package finds the middleware imported only in a model-profile module, so
  the real agent passes it through `middleware=[TodoListMiddleware()]`.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import os
import sys
from typing import AsyncIterator

from backend.agent.fixtures import flavor_for_sid as _flavor_for_sid, load as _load
from backend.agent.runtime.replan import patch_request, replan_events, validate_patch
from backend.schema import DocumentDraft, DocumentRequest, RunEvent, RunRequest, RunResult

_counter = itertools.count(1)
_runs: dict[str, dict] = {}


def mode() -> str:
    value = os.environ.get("AGENT_MODE", "replay").strip().lower() or "replay"
    if value not in ("replay", "live"):
        raise ValueError(f"AGENT_MODE must be replay or live, not {value!r}")
    return value


def _live(run_id: str):
    """The LiveRun for run_id, or None when the run is a replay run."""
    live = sys.modules.get("backend.agent.live")      # not imported: no live run can exist
    return live._RUNS.get(run_id) if live else None


def _get(run_id: str) -> dict:
    try:
        return _runs[run_id]
    except KeyError:
        raise KeyError(f"unknown run_id: {run_id}") from None


def start_run(request: RunRequest) -> str:
    if request.mode == "analysis":           # real analysis: live data and the analysis door, no agent, whatever AGENT_MODE says
        from backend.agent import analysis_run
        return analysis_run.start_run(request)
    if mode() == "live":
        from backend.agent import live
        return live.start_run(request)
    recorded = _recorded(request.sid)
    if recorded is not None:                 # a live run that was kept for the demo
        run_id = f"run_demo_{next(_counter)}"
        result, events, bundle = recorded
        asked_for = RunRequest.model_validate(result["request"])
        result["run_id"] = run_id
        result["served_by"] = "replay"           # the recording keeps the data_source it was made with
        # **The caller's request, not the recording's.** Overwriting only `run_id` meant every
        # property with a recording reported the budget, role and desks the recording was made
        # with, so a user who asked for $10,000,000 was told $15,000 and had no way to tell the
        # difference from a UI bug. The request a result carries has to be the one that was made.
        result["request"] = request.model_dump(mode="json")
        _runs[run_id] = {"flavor": None, "bundle": bundle, "folder": _recording_folder(request.sid),
                         "result": RunResult.model_validate(result),
                         "events": [RunEvent.model_validate(e) for e in events], "answers": {}, "docs": {}}
        _honour_request(_runs[run_id], request, asked_for)
        return run_id
    flavor = _flavor_for_sid(request.sid)
    run_id = f"run_{flavor}_{next(_counter)}"
    result = _load(flavor, "run_result.json")
    result["run_id"] = run_id
    result["request"] = request.model_dump(mode="json")
    result["data_source"], result["served_by"] = "example", "replay"
    _runs[run_id] = {
        "flavor": flavor,
        "result": RunResult.model_validate(result),
        "events": [RunEvent.model_validate(e) for e in _load(flavor, "run_events.json")],
        "answers": {},
        "docs": {},
    }
    return run_id


def _honour_request(run: dict, wanted: RunRequest, recorded: RunRequest) -> None:
    """Make a recorded run's plan answer the request it now claims, or say that it cannot.

    Carrying the caller's request is necessary but not sufficient: a result that says
    "$10,000,000" above a plan built for $15,000 is a worse lie than the one it replaces. A
    different budget is re-planned for real through the same path `update` uses (#356), which
    leaves the recording on disk untouched.

    Role and desks cannot be re-planned - they change which measures apply at all - so they are
    reported as not honoured rather than quietly ignored. Silence there would let the demo show a
    tenant's plan under the word "landlord".
    """
    changed = []
    if wanted.role != recorded.role:
        changed.append(f"role {wanted.role!r} (the recording was made as {recorded.role!r})")
    if wanted.desks_requested != recorded.desks_requested:
        changed.append(f"desks {wanted.desks_requested} (the recording used {recorded.desks_requested})")

    if wanted.budget_usd != recorded.budget_usd:
        try:
            new, events = _replan_recorded(run, wanted.budget_usd, wanted.overrides or None)
        except LookupError as exc:
            changed.append(f"budget {wanted.budget_usd:,.0f} USD (the recorded plan was built for "
                           f"{recorded.budget_usd:,.0f}; it could not be rebuilt: {exc})")
        else:
            run["result"] = new
            run["events"] = [*run["events"], *events]

    if not changed:
        return
    result = run["result"]
    run["result"] = result.model_copy(update={"warnings": [
        *result.warnings,
        "This saved run does not answer part of what was asked: "
        + "; ".join(changed)
        + ". Use real analysis for a plan built to your own inputs.",
    ]})


def _recording_folder(sid: str):
    from backend.agent.live import demo_dir
    return demo_dir() / sid


RECORDED_REPLAN_WARNING = ("re-run: the plan was rebuilt for the new budget or assumptions; the report describes "
                           "the recorded run")
_RUN_FILES = ("bundle.json", "model.json", "baseline.json", "measures.json", "plan.json", "report.md")


def _replan_recorded(run: dict, budget_usd, overrides):
    """A recorded run keeps its bundle, model and baseline, so a new budget re-plans for real: the analysis door
    builds the plan again (no model call), exactly as a finished live run is adjusted. Raises LookupError when the
    recording is incomplete or the analysis door is unavailable, and the caller falls back to the replayed shape."""
    import shutil
    import tempfile
    from pathlib import Path
    from backend.agent.live import default_doors
    from backend.agent.runtime.replan import replan
    from backend.agent.runtime.runtime import RunStore
    folder = run.get("folder")
    result = run["result"]
    if folder is None or not all((Path(folder) / n).is_file() for n in _RUN_FILES):
        raise LookupError("the recording does not keep every run file")
    doors = default_doors()
    if doors.degraded:
        raise LookupError(doors.degraded)
    tmp = Path(tempfile.mkdtemp(prefix="replan-"))
    try:
        store = RunStore(tmp)
        files = store.files(result.run_id)
        for name in _RUN_FILES:
            shutil.copy(Path(folder) / name, files.root / name)
        new, events = replan(result, files, store, doors, budget_usd, overrides)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    warnings = [w for w in new.warnings if not w.startswith("re-run:")]
    stale = [w for w in new.warnings if w.startswith("re-run:")]
    new = new.model_copy(update={"served_by": "replay", "data_source": result.data_source,
                                 "warnings": [*warnings, RECORDED_REPLAN_WARNING, *stale]})
    return new, events


def _recorded(sid: str):
    """(result, events, bundle) of a successful live run kept for this sid, or None. Replay serves it
    in place of the example, so the demo shows a real run without calling a model."""
    from backend.agent.live import demo_dir
    folder = demo_dir() / sid
    try:
        return (json.loads((folder / "result.json").read_text()),
                json.loads((folder / "events.json").read_text()),
                json.loads((folder / "bundle.json").read_text()))
    except (OSError, ValueError):
        return None


async def stream_events(run_id: str) -> AsyncIterator[RunEvent]:
    run = _live(run_id)
    if run is not None:
        async for event in run.stream():
            yield event
        return
    for event in _get(run_id)["events"]:
        yield event
        await asyncio.sleep(0)


def get_run(run_id: str) -> RunResult:
    run = _live(run_id)
    if run is not None:
        return run.result()
    return _get(run_id)["result"]


def answer(run_id: str, question_id: str, value: float | str | bool | None) -> None:
    run = _live(run_id)
    if run is not None:
        run.answer(question_id, value)
        return
    _get(run_id)["answers"][question_id] = value


def update_run(run_id: str, budget_usd: float | None = None,
               overrides: dict[str, float | str | bool] | None = None) -> None:
    """Adjust and re-run (G11). Raises PatchError for a patch that cannot be applied. A live run
    re-runs the analysis for real; a replay run only replays the shape: the request and the plan's
    budget change and the re-run events are added, the plan itself is the example's."""
    live_run = _live(run_id)
    if live_run is not None:
        live_run.update(budget_usd, overrides)
        return
    run = _get(run_id)
    result = run["result"]
    validate_patch(result, budget_usd, overrides)
    if run.get("flavor") is None:
        try:
            run["result"], more = _replan_recorded(run, budget_usd, overrides)
            run["events"] = [*run["events"], *more]
            return
        except LookupError:
            pass                      # an incomplete recording: the replayed shape below
    request = patch_request(result.request, budget_usd, overrides)
    plan = result.plan.model_copy(update={"budget_usd": request.budget_usd}) if result.plan else None
    run["result"] = result.model_copy(update={"request": request, "plan": plan})
    run["events"] = [*run["events"], *replan_events(
        result.request, request, f"{len(plan.selected) if plan else 0} measures within ${request.budget_usd:,.0f} (replayed)")]


def draft_document(request: DocumentRequest) -> DocumentDraft:
    live_run = _live(request.run_id)
    if live_run is not None:
        return live_run.draft(request)
    run = _get(request.run_id)
    # A recorded run and an example run are drafted the same way, offline, with the legal door: the real
    # template and the real checks, never a fixture draft relabelled with the request's type.
    from backend.legal import api as legal
    from backend.schema import PropertyBundle
    raw = run["bundle"] if run["flavor"] is None else _load(run["flavor"], "property_bundle.json")
    draft = legal.fill_template(request, run["result"], PropertyBundle.model_validate(raw))
    if not draft.statutory_checks:
        # `engine.fill_template` always returns an empty checklist: running the predicates is the
        # caller's job (`LiveRun.draft` does it too), and the checklist is what SPEC 15 step 7 shows.
        draft = draft.model_copy(update={"statutory_checks": legal.check_document(draft)})
    run["docs"][draft.doc_id] = draft
    return draft


def get_roof(run_id: str):
    """The roof view of a run (agent/roof): its bundle and result, drawn on the aerial image."""
    from backend.agent.roof import roof_view
    from backend.data_layer import api as data
    from backend.schema import PropertyBundle
    live_run = _live(run_id)
    if live_run is not None:
        raw = live_run.files.read_json("bundle.json")
    else:
        run = _get(run_id)
        raw = run["bundle"] if run.get("flavor") is None else _load(run["flavor"], "property_bundle.json")
    if raw is None:
        raise KeyError(f"run {run_id} has no property bundle yet")
    return roof_view(PropertyBundle.model_validate(raw), get_run(run_id), data.get_asset)


def get_document(run_id: str, doc_id: str) -> DocumentDraft:
    live_run = _live(run_id)
    if live_run is not None:
        try:
            return live_run.docs[doc_id]
        except KeyError:
            raise KeyError(f"unknown doc_id: {doc_id}") from None
    try:
        return _get(run_id)["docs"][doc_id]
    except KeyError:
        raise KeyError(f"unknown doc_id: {doc_id}") from None

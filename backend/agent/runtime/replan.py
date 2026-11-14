"""Adjust and re-run (G11; SPEC 4 step 6): a new budget or new assumption values, then the plan
again. Deterministic: no model call. The audit's findings (bundle, panorama observations, flags) are
kept; the building model is rebuilt with the overrides, the baseline and the plan are recomputed
by the analysis door, the run files and the saved RunResult are updated, and the events of the
re-run are returned for the stream.
"""
from __future__ import annotations

from typing import Any, Optional, Union

from backend.agent.narrative import check_narrative
from backend.agent.runtime.runtime import RunFiles, RunStore, build_result
from backend.schema import (Assumption, BuildingModel, MeasureResult, PropertyBundle, Ranged, RunEvent,
                            RunRequest, RunResult)

Value = Union[float, str, bool]


class PatchError(Exception):
    """A change the run cannot take. `code` is the error-envelope code, `status` the HTTP status."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def validate_patch(result: RunResult, budget_usd: Optional[float],
                   overrides: Optional[dict[str, Value]]) -> None:
    """Refuse a patch that cannot be applied: a run that is not done, a negative budget, an override
    key that is not an assumption of the run's model (or is not user-editable) or a value of the
    wrong kind. Nothing is changed."""
    if result.status != "done":
        raise PatchError(409, "run_not_done", f"run {result.run_id} is {result.status}; adjust a finished run")
    if budget_usd is not None and budget_usd < 0:
        raise PatchError(422, "invalid_budget", "budget_usd must not be negative")
    if budget_usd is None and not overrides:
        raise PatchError(422, "empty_patch", "give a new budget_usd or overrides")
    known = {a.key: a for a in (result.building_model.assumptions if result.building_model else [])}
    for key, value in (overrides or {}).items():
        a = known.get(key)
        if a is None:
            raise PatchError(422, "unknown_assumption", f"{key!r} is not an assumption of this run's model")
        if not a.user_editable:
            raise PatchError(422, "not_editable", f"{key!r} cannot be edited: it is measured")
        numeric = isinstance(a.value, Ranged)
        if numeric != (isinstance(value, (int, float)) and not isinstance(value, bool)):
            raise PatchError(422, "invalid_override", f"{key!r} takes {'a number' if numeric else 'a text or yes/no value'}")


def patch_request(request: RunRequest, budget_usd: Optional[float],
                  overrides: Optional[dict[str, Value]]) -> RunRequest:
    update: dict[str, Any] = {}
    if budget_usd is not None:
        update["budget_usd"] = budget_usd
    if overrides:
        update["overrides"] = {**request.overrides, **overrides}
    return request.model_copy(update=update)


def replan_events(old: RunRequest, new: RunRequest, summary: str) -> list[RunEvent]:
    """The events of a re-run, in the vocabulary of a full run."""
    changed = sorted(k for k, v in new.overrides.items() if old.overrides.get(k) != v)
    events = [RunEvent(type="stage_started", stage="S4", message="Applying your change")]
    for key in changed:
        events.append(RunEvent(type="tool_call", stage="S4", message="set_assumption",
                               payload={"name": "set_assumption", "args": {"key": key, "value": new.overrides[key]}}))
    if new.budget_usd != old.budget_usd:
        events.append(RunEvent(type="tool_call", stage="S4", message="set_budget",
                               payload={"name": "set_budget", "args": {"budget_usd": new.budget_usd}}))
    events += [RunEvent(type="stage_done", stage="S4", message="Building model ready"),
               RunEvent(type="stage_started", stage="S7", message="Building the plan"),
               RunEvent(type="tool_call", stage="S7", message="build_plan",
                        payload={"name": "build_plan", "args": {"budget_usd": new.budget_usd}}),
               RunEvent(type="partial_result", stage="S7", message=summary),
               RunEvent(type="stage_done", stage="S7", message="Plan ready"),
               RunEvent(type="done", message="Re-run complete")]
    return events


def replan(result: RunResult, files: RunFiles, store: RunStore, doors,
           budget_usd: Optional[float] = None,
           overrides: Optional[dict[str, Value]] = None) -> tuple[RunResult, list[RunEvent]]:
    """Re-run the analysis for a finished run with a new budget and/or overrides. `doors.analysis`
    is the analysis door. The new RunResult is saved; the events are for the stream."""
    validate_patch(result, budget_usd, overrides)
    request = patch_request(result.request, budget_usd, overrides)
    bundle = PropertyBundle.model_validate(files.read_json("bundle.json"))
    old_model = result.building_model
    observed = [a for a in (old_model.assumptions if old_model else []) if a.source == "vision"]
    flags = list(old_model.flags) if old_model else []
    analysis = doors.analysis
    model: BuildingModel = analysis.build_building_model(bundle, observed, flags, request.overrides)
    baseline = analysis.run_baseline(bundle, model, request.bills)
    plan = analysis.build_plan(bundle, model, request)
    measures: list[MeasureResult] = [i.measure for i in plan.selected] + list(plan.financeable)
    files.write("model.json", model.model_dump_json(indent=2))
    files.write("baseline.json", baseline.model_dump_json(indent=2))
    files.write("measures.json", [m.model_dump(mode="json") for m in measures])
    files.write("plan.json", plan.model_dump_json(indent=2))

    updated = build_result(result.run_id, request, files, "done", result.questions, [])
    narrative = result.narrative_md
    warnings = [w for w in result.warnings if not w.startswith("re-run:")]
    if narrative:
        stale = check_narrative(narrative, updated.model_copy(update={"narrative_md": ""}), bundle, model)
        if stale:
            warnings.append(f"re-run: the summary text was written for the earlier plan and was not "
                            f"regenerated; {len(stale)} of its numbers no longer match")
    updated = updated.model_copy(update={"narrative_md": narrative, "warnings": warnings})
    store.save(result.run_id, updated)
    summary = (f"{len(plan.selected)} measures within ${request.budget_usd:,.0f}; "
               f"{len(plan.financeable)} more financeable")
    return updated, replan_events(result.request, request, summary)

"""Run door of the agent lane (workplan 3.5). Imported only by backend/server.py.

G0 stub: every function replays the fixtures in specs/examples/ behind the final
signatures. Real code replaces the bodies later; the signatures stay.

Confirmed against the installed deepagents 0.7.38 (G0, 2026-11-14):
- create_deep_agent(model, tools, *, system_prompt, middleware, subagents, skills,
  memory, permissions, backend, interrupt_on, response_format, state_schema,
  context_schema, checkpointer, store, debug, name, cache). SPEC 8 names match:
  subagents, interrupt_on and checkpointer are keyword arguments.
- SPEC 8 [U] note 1 (subagents cannot delegate further): not tested here, it needs a model.
- SPEC 8 [U] note 2 (TodoListMiddleware may need adding explicitly): a source search of
  the installed package finds the middleware imported only in a model-profile module, so
  the real agent should pass it through `middleware=[TodoListMiddleware()]`.
"""
from __future__ import annotations

import asyncio
import itertools
import json
from pathlib import Path
from typing import AsyncIterator

from backend.schema import DocumentDraft, DocumentRequest, RunEvent, RunRequest, RunResult

_EXAMPLES = Path(__file__).resolve().parents[2] / "specs" / "examples"
_FLAVORS = ("house", "office")
_counter = itertools.count(1)
_runs: dict[str, dict] = {}


def _load(flavor: str, name: str) -> dict | list:
    return json.loads((_EXAMPLES / flavor / name).read_text())


def _flavor_for_sid(sid: str) -> str:
    for flavor in _FLAVORS:
        if _load(flavor, "run_result.json")["property"]["sid"] == sid:
            return flavor
    return "house"


def _get(run_id: str) -> dict:
    try:
        return _runs[run_id]
    except KeyError:
        raise KeyError(f"unknown run_id: {run_id}") from None


def start_run(request: RunRequest) -> str:
    flavor = _flavor_for_sid(request.sid)
    run_id = f"run_{flavor}_{next(_counter)}"
    result = _load(flavor, "run_result.json")
    result["run_id"] = run_id
    result["request"] = request.model_dump(mode="json")
    _runs[run_id] = {
        "flavor": flavor,
        "result": RunResult.model_validate(result),
        "events": [RunEvent.model_validate(e) for e in _load(flavor, "run_events.json")],
        "answers": {},
        "docs": {},
    }
    return run_id


async def stream_events(run_id: str) -> AsyncIterator[RunEvent]:
    for event in _get(run_id)["events"]:
        yield event
        await asyncio.sleep(0)


def get_run(run_id: str) -> RunResult:
    return _get(run_id)["result"]


def answer(run_id: str, question_id: str, value: float | str | bool | None) -> None:
    _get(run_id)["answers"][question_id] = value


def update_run(run_id: str, budget_usd: float | None = None,
               overrides: dict[str, float | str | bool] | None = None) -> None:
    run = _get(run_id)
    request = run["result"].request
    if budget_usd is not None:
        request.budget_usd = budget_usd
    if overrides:
        request.overrides = {**request.overrides, **overrides}


def draft_document(request: DocumentRequest) -> DocumentDraft:
    run = _get(request.run_id)
    draft = DocumentDraft.model_validate(_load(run["flavor"], "document_draft.json"))
    draft.doc_type = request.doc_type
    draft.state = request.state
    draft.doc_id = f"doc_{request.run_id}_{len(run['docs']) + 1}"
    run["docs"][draft.doc_id] = draft
    return draft


def get_document(run_id: str, doc_id: str) -> DocumentDraft:
    try:
        return _get(run_id)["docs"][doc_id]
    except KeyError:
        raise KeyError(f"unknown doc_id: {doc_id}") from None

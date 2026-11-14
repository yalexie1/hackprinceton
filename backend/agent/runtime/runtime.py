"""Run runtime (G5): run lifecycle, agent stream -> RunEvent, run files, saved RunResult.

The agent is passed in: an async callable `agent(request, files) -> AsyncIterator[chunk]`.
A chunk is either a RunEvent, or a dict the mapper below understands. The agent writes the
six run files of SPEC 8 rule 6 through `files`; the runtime builds RunResult from them.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, Optional

from backend.schema import (BaselineResult, BuildingModel, MeasureResult, Plan,
                            PropertyBundle, Question, RunEvent, RunRequest, RunResult)

RUN_FILES = ("bundle.json", "model.json", "baseline.json", "measures.json", "plan.json",
             "report.md")
DEFAULT_RUNS_DIR = Path(__file__).resolve().parents[3] / "data" / "runs"


class RunFiles:
    """The agent's /run/ directory for one run, stored at data/runs/{run_id}/."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        if name not in RUN_FILES and name != "result.json":
            raise ValueError(f"not a run file: {name}")
        return self.root / name

    def write(self, name: str, content: str | bytes | dict | list) -> Path:
        p = self.path(name)
        if isinstance(content, (dict, list)):
            content = json.dumps(content, indent=2, sort_keys=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(content) if isinstance(content, str) else tmp.write_bytes(content)
        tmp.replace(p)   # atomic: an interrupted write never leaves a half file
        return p

    def read_json(self, name: str):
        p = self.path(name)
        return json.loads(p.read_text()) if p.exists() else None

    def missing(self) -> list[str]:
        return [n for n in RUN_FILES if not (self.root / n).exists()]


Agent = Callable[[RunRequest, RunFiles], AsyncIterator]


def map_chunk(chunk) -> list[RunEvent]:
    """Map one item of the agent stream to RunEvents. Unknown chunks map to nothing."""
    if isinstance(chunk, RunEvent):
        return [chunk]
    if not isinstance(chunk, dict):
        return []
    if "todos" in chunk:                       # write_todos update
        todos = [{"content": str(t.get("content", "")), "status": t.get("status", "pending")}
                 for t in chunk["todos"] if isinstance(t, dict)]
        done = sum(t["status"] == "completed" for t in todos)
        current = next((t["content"] for t in todos if t["status"] == "in_progress"), None)
        message = f"{done} of {len(todos)} done" + (f": {current}" if current else "")
        return [RunEvent(type="todo", message=message,
                         payload={"todos": todos, "total": len(todos), "done": done, "current": current})]
    if "tool_call" in chunk:
        tc = chunk["tool_call"]
        return [RunEvent(type="tool_call", stage=chunk.get("stage"), message=tc.get("name", ""),
                         payload={"name": tc.get("name"), "args": tc.get("args", {})})]
    if "fallback" in chunk:
        return [RunEvent(type="fallback", stage=chunk.get("stage"), message=str(chunk["fallback"]),
                         payload=chunk.get("payload", {}))]
    if "question" in chunk:
        # kind "question" is an ask_user question about an assumption; kind "approval" is the counsel's
        # gate before a document is drafted (payload.approval holds the proposal). Both are answered
        # the same way: POST the choice value for payload.question.id.
        payload = {"question": chunk["question"], "kind": chunk.get("kind", "question")}
        if chunk.get("approval") is not None:
            payload["approval"] = chunk["approval"]
        return [RunEvent(type="question", stage=chunk.get("stage"),
                         message=chunk["question"].get("prompt", ""), payload=payload)]
    for key, kind in (("stage_started", "stage_started"), ("stage_done", "stage_done")):
        if key in chunk:
            return [RunEvent(type=kind, stage=chunk[key], message=chunk.get("message", ""))]
    if "type" in chunk:
        return [RunEvent.model_validate(chunk)]
    return []


def build_result(run_id: str, request: RunRequest, files: RunFiles, status: str,
                 questions: Optional[list[Question]] = None,
                 warnings: Optional[list[str]] = None) -> RunResult:
    bundle = files.read_json("bundle.json")
    if bundle is None:
        raise ValueError("bundle.json is missing, so there is no property for the result")
    summary = PropertyBundle.model_validate(bundle).summary
    model = files.read_json("model.json")
    baseline = files.read_json("baseline.json")
    measures = files.read_json("measures.json") or []
    plan = files.read_json("plan.json")
    report = files.path("report.md")
    return RunResult(
        run_id=run_id, status=status, request=request, property=summary,
        building_model=BuildingModel.model_validate(model) if model else None,
        baseline=BaselineResult.model_validate(baseline) if baseline else None,
        measures=[MeasureResult.model_validate(m) for m in measures],
        plan=Plan.model_validate(plan) if plan else None,
        questions=questions or [],
        narrative_md=report.read_text() if report.exists() else "",
        warnings=warnings or [])


class RunStore:
    def __init__(self, runs_dir: Path = DEFAULT_RUNS_DIR):
        self.runs_dir = Path(runs_dir)

    def files(self, run_id: str) -> RunFiles:
        return RunFiles(self.runs_dir / run_id)

    def new_run_id(self) -> str:
        return f"run_{uuid.uuid4().hex[:12]}"

    def save(self, run_id: str, result: RunResult) -> None:
        self.files(run_id).write("result.json", result.model_dump_json(indent=2))

    def load(self, run_id: str) -> RunResult:
        p = self.files(run_id).root / "result.json"
        if not p.exists():
            raise KeyError(f"unknown run_id: {run_id}")
        return RunResult.model_validate_json(p.read_text())


async def execute_run(request: RunRequest, agent: Agent, store: RunStore,
                      run_id: Optional[str] = None) -> AsyncIterator[RunEvent]:
    """Run the agent to completion, yielding RunEvents. The last event is `done` or `error`.
    The saved RunResult has status done, waiting_for_user or error."""
    run_id = run_id or store.new_run_id()
    files = store.files(run_id)
    questions: list[Question] = []
    warnings: list[str] = []
    status, last = "done", None
    try:
        async for chunk in agent(request, files):
            for event in map_chunk(chunk):
                if event.type == "question":
                    questions.append(Question.model_validate(event.payload["question"]))
                elif event.type == "done":
                    last = event
                    continue
                elif event.type == "error":
                    warnings.append(event.message)
                yield event
        if questions and last is None:      # stream ended on a question with no `done`
            status = "waiting_for_user"
        if status == "done":
            missing = files.missing()
            if missing:
                warnings.append("run files missing: " + ", ".join(missing))
        store.save(run_id, build_result(run_id, request, files, status, questions, warnings))
        if status != "waiting_for_user":     # a paused run stays open until answered
            yield last or RunEvent(type="done", message=status)
    except Exception as exc:    # an agent exception becomes an error event and status error
        msg = f"{type(exc).__name__}: {exc}"
        warnings.append(msg)
        try:
            store.save(run_id, build_result(run_id, request, files, "error", questions, warnings))
        except Exception:
            pass
        yield RunEvent(type="error", message=msg)

"""Live run door: the deep agent driven by the run runtime (workplan 3.5, AGENT_MODE=live).

One `LiveRun` per run. It owns a thread with its own event loop, so the sync `start_run`
returns at once and any number of `stream_events` readers replay `events` from the start.
`execute_run` (runtime) turns the agent stream into RunEvents and saves the RunResult; a
question or an approval pauses the graph with a langgraph interrupt, and `answer` resumes
it with `Command(resume={"value": v})` (also when v is None: a bare resume=None breaks
langgraph).
"""
from __future__ import annotations

import asyncio
import copy
import functools
import hashlib
import json
import os
import queue
import shutil
import time
import threading
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from backend.agent.ask import AskSession, make_ask_user
from backend.agent.graph import build_auditor, detect_fallbacks, provenance_fallbacks, provenance_warnings
from backend.agent.narrative import check_narrative, remove_unsupported
from backend.agent.runtime.replan import PatchError, replan
from backend.agent.runtime.runtime import DEFAULT_RUNS_DIR, RunStore, build_result, execute_run
from backend.agent.tools import Doors, ToolContext, build_reader_tools, build_tools
from backend.schema import (BuildingModel, Choice, DocumentDraft, DocumentRequest, PropertyBundle, Question,
                            RunEvent, RunRequest, RunResult)

STAGE_OF = {
    "search_properties": "S1", "get_property_bundle": "S2", "get_asset": "S2",
    "observe_interior": "S3", "detect_roof_elements": "S3",
    "build_building_model": "S4", "set_assumption": "S4", "calibrate_model": "S5", "run_baseline": "S5",
    "evaluate_measure": "S6", "design_pv": "S6", "score_desk_positions": "S6",
    "price_measure": "S7", "lookup_incentives": "S7", "build_plan": "S7",
    "cpace_scenario": "S7", "sensitivity": "S7",
    "list_templates": "S9", "fill_template": "S9", "check_document": "S9",
}
STAGE_TITLE = {
    "S1": "Locating the property", "S2": "Fetching the property data",
    "S3": "Reading panoramas and the roof", "S4": "Building the model",
    "S5": "Simulating the baseline", "S6": "Evaluating measures", "S7": "Building the plan",
    "S8": "Writing the summary", "S9": "Drafting documents",
}
# Tools never memoized: fill_template drafts a document and records it, every call counts.
NO_MEMO = frozenset({"fill_template"})
# Files a tool result can depend on; measures.json is folded in per measure, not whole.
STATE_FILES = ("bundle.json", "model.json", "baseline.json")
# Tools whose result also depends on the saved row of their measure (evaluate_measure does
# not: it ignores measures.json, so re-running it never overwrites a priced row).
MEASURE_STATE = frozenset({"price_measure", "cpace_scenario"})
REPORT_KEYS = ("/report.md", "/run/report.md", "report.md")


@dataclass
class LiveSettings:
    """Test seam: scripted models, fake doors, a temp runs directory."""
    model: Any = None
    subagent_model: Any = None
    doors: Optional[Doors] = None
    runs_dir: Optional[Path] = None


SETTINGS: Optional[LiveSettings] = None


class LiveDataUnavailable(RuntimeError):
    """A live run was asked for live data but the keys the data layer needs are not in the environment."""


#: What the data layer needs to assemble a live bundle (names only; values are never printed or stored).
LIVE_DATA_KEYS = ("MATTERPORT_API_KEY", "MATTERPORT_API_TOKEN", "VEXCEL_API_KEY", "EIA_API_KEY")


def require_live_data_keys(env=None) -> None:
    """Fail loudly, before any model call, when live data is switched on and a key is missing. The data layer
    would otherwise hand back an error per tool or the example bundle, and the run would look like a live one."""
    env = os.environ if env is None else env
    if env.get("DATA_LAYER_LIVE") != "1":
        return
    missing = [k for k in LIVE_DATA_KEYS if not env.get(k)]
    if missing:
        raise LiveDataUnavailable("live data is on (DATA_LAYER_LIVE=1) but these keys are not set: "
                                  + ", ".join(missing) + ". Set them, or run with DATA_LAYER_LIVE=0 for the example data.")


_ENV_KEYS = ("ANTHROPIC_API_KEY", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_TRACING",
             "LANGSMITH_ENDPOINT", "LANGSMITH_WORKSPACE_ID",
             # the data layer reads these from the environment (it does not read .env itself)
             "EIA_API_KEY", "MATTERPORT_API_KEY", "MATTERPORT_API_TOKEN", "MATTERPORT_SDK_KEY", "VEXCEL_API_KEY")
DEFAULT_PROJECT = "energy-consultant"


def demo_dir() -> Path:
    """Where successful live runs are kept for demo replay (AGENT_DEMO_DIR overrides)."""
    return Path(os.environ.get("AGENT_DEMO_DIR") or DEFAULT_RUNS_DIR / "_demo")


def _load_env() -> None:
    """Pick the keys this module needs up from the repo's (git-ignored) .env when they are not
    exported. Values are never printed or logged."""
    env = DEFAULT_RUNS_DIR.parents[1] / ".env"
    if not env.is_file():
        return
    for line in env.read_text().splitlines():
        key, _, value = line.partition("=")
        if key in _ENV_KEYS and not os.environ.get(key):
            os.environ[key] = value.strip().strip("'\"")


def configure_tracing(env=None) -> bool:
    """LangSmith tracing for live runs. On when a LANGSMITH_API_KEY is present and tracing has not
    been switched off; with no key it is forced off, so a missing or empty key never makes the
    run fail or log errors. Returns whether traces will be sent."""
    env = os.environ if env is None else env
    flag = (env.get("LANGSMITH_TRACING") or "true").strip().lower()
    on = bool(env.get("LANGSMITH_API_KEY")) and flag not in ("false", "0", "no", "off")
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
        env[name] = "true" if on else "false"
    if on and not env.get("LANGSMITH_PROJECT"):
        env["LANGSMITH_PROJECT"] = DEFAULT_PROJECT
    try:                                    # langsmith caches its environment lookups
        from langsmith import utils
        utils.get_env_var.cache_clear()
        if hasattr(utils.tracing_is_enabled, "cache_clear"):
            utils.tracing_is_enabled.cache_clear()
    except Exception:
        pass
    return on


def default_doors() -> Doors:
    from backend.data_layer import api as data
    from backend.legal import api as legal
    degraded = None
    try:
        from backend.analysis import api as analysis
    except ImportError as exc:
        # The analysis door **is** on main, so an ImportError here means a broken
        # environment - a missing numpy or shapely - not a missing lane. Falling back is
        # still better than refusing to run, but it replaces every analysis figure with
        # the example's, so it is recorded and surfaces as a run warning rather than
        # leaving someone to wonder why the numbers look like the fixtures.
        from backend.agent import analysis_stub as analysis
        degraded = (f"the analysis door could not be imported ({exc}), so this run "
                    f"replays the example's analysis instead of computing it")
    return Doors(data=data, analysis=analysis, legal=legal, degraded=degraded)


class FeedingSession(AskSession):
    """AskSession whose queue is filled from the `sensitivity` tool result."""

    def feed(self, questions: list[Question]) -> None:
        self._queue = list(questions)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content
                   if isinstance(b, dict) and b.get("type") == "text") if isinstance(content, list) else ""


def _approval_question(proposal: dict) -> Question:
    kind = proposal.get("doc_type", "document")
    return Question(
        id=f"approve_{kind}", assumption_key="document.approval",
        prompt=(f"Draft the {kind} ({proposal.get('state')}) for "
                f"{', '.join(proposal.get('measure_ids', [])) or 'no measures'}? Party names, "
                "licence number and addresses stay blank unless you supply them."),
        choices=[Choice(label="Approve", value=True), Choice(label="Decline", value=False)],
        impact_note="Nothing is drafted until you approve.")


def enable_real_vision(doors: Doors) -> bool:
    """Real panorama reading (A7) for live and real-analysis runs only: replay and re-plans never call it, and a
    property then never falls back to the example's invented observations. AGENT_VISION=0 turns it off; no
    ANTHROPIC_API_KEY means no vision (vintage defaults)."""
    if doors.degraded or os.environ.get("AGENT_VISION", "1") == "0":
        return False
    from backend.agent.vision_client import enable_vision
    return enable_vision(doors.analysis, doors.data)


class LiveRun:
    def __init__(self, run_id: str, request: RunRequest, settings: LiveSettings):
        self.run_id, self.request = run_id, request
        self.store = RunStore(settings.runs_dir or DEFAULT_RUNS_DIR)
        self.files = self.store.files(run_id)
        self.doors = settings.doors or default_doors()
        if settings.doors is None:
            enable_real_vision(self.doors)
        self.events: list[RunEvent] = []
        self.docs: dict[str, DocumentDraft] = {}
        self.active = True               # a segment is executing (the saved result is stale)
        self.closed = False              # terminal: done or error, no more events
        self.pending: Optional[tuple[str, Question]] = None    # (kind, question) while paused
        self.session = FeedingSession([])
        self.usage: dict = {}
        self._inbox: "queue.Queue[Any]" = queue.Queue()
        # Tools share the run files (read-modify-write of measures.json, model.json), and
        # the model may issue parallel tool calls: one tool at a time per run.
        self._tool_lock = threading.RLock()
        self._update_lock = threading.Lock()
        # A degraded door is a property of the environment, not of the run, so it is
        # seeded here rather than waiting for an `error` event that never comes.
        self._warnings: list[str] = [self.doors.degraded] if self.doors.degraded else []
        self._memo: dict[str, Any] = {}      # (tool, args, run state) -> result
        self.memo_hits = 0
        self._stage: Optional[str] = None
        self._last_text = ""
        self._q: Optional[asyncio.Queue] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._build_agent(settings)
        self._thread = threading.Thread(target=self._thread_main, daemon=True,
                                        name=f"run-{run_id}")

    # ---- construction ----

    def _build_agent(self, settings: LiveSettings) -> None:
        from langchain_core.callbacks import UsageMetadataCallbackHandler
        from langgraph.checkpoint.memory import InMemorySaver

        ctx = ToolContext(request=self.request, files=self.files, doors=self.doors,
                          run=lambda: build_result(self.run_id, self.request, self.files, "done"),
                          asset_dir=self.files.root / "assets")
        raw = {**build_tools(ctx), **build_reader_tools(ctx)}
        tools = self.tools = {name: self._instrument(name, fn) for name, fn in raw.items()}
        ask_user = make_ask_user(self.session, lambda k, v: tools["set_assumption"](k, v))
        self.usage_handler = UsageMetadataCallbackHandler()
        self.tracing = os.environ.get("LANGSMITH_TRACING") == "true" and bool(os.environ.get("LANGSMITH_API_KEY"))
        self.trace_id = uuid.uuid4()          # the root trace of the first segment (a resumed segment is its own trace)
        self._first_segment = True
        self.config = {"configurable": {"thread_id": self.run_id}, "recursion_limit": 200,
                       "callbacks": [self.usage_handler], "run_name": "energy-audit",
                       "tags": ["energy-audit", f"sid:{self.request.sid}"],
                       "metadata": {"audit_run": self.run_id, "sid": self.request.sid, "role": self.request.role,
                                    "budget_usd": self.request.budget_usd}}
        orchestrator = settings.model or os.environ.get("AGENT_ORCHESTRATOR_MODEL") or None
        subagent = settings.subagent_model or os.environ.get("AGENT_SUBAGENT_MODEL") or None
        self.graph = build_auditor(tools, model=orchestrator, subagent_model=subagent,
                                   checkpointer=InMemorySaver(), ask_user=ask_user,
                                   with_counsel=True)

    def _emit(self, chunk: dict) -> None:
        """Called from tool threads: hand a chunk to the running event loop."""
        if self._loop is not None and self._q is not None:
            self._loop.call_soon_threadsafe(self._q.put_nowait, ("event", chunk))

    def _stage_chunks(self, tool: str) -> list[dict]:
        stage = STAGE_OF.get(tool)
        if stage is None or stage == self._stage:
            return []
        out = []
        if self._stage:
            out.append({"stage_done": self._stage, "message": STAGE_TITLE[self._stage]})
        out.append({"stage_started": stage, "message": STAGE_TITLE[stage]})
        self._stage = stage
        return out

    def _memo_key(self, name: str, a: tuple, k: dict) -> str:
        """Tool, arguments and the run state the result depends on (bundle, model, baseline,
        and for a measure tool that measure's saved row). A state change misses the cache."""
        h = hashlib.sha256(json.dumps([name, list(a), k], sort_keys=True, default=str).encode())
        for f in STATE_FILES:
            p = self.files.root / f
            h.update(p.read_bytes() if p.exists() else b"-")
        measure_id = k.get("measure_id") or (a[0] if a else None)
        if name in MEASURE_STATE and measure_id:
            row = next((r for r in (self.files.read_json("measures.json") or [])
                        if r.get("measure_id") == measure_id), None)
            h.update(json.dumps(row, sort_keys=True).encode())
        return h.hexdigest()

    def _instrument(self, name: str, fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*a, **k):
            with self._tool_lock:
                key = None if name in NO_MEMO else self._memo_key(name, a, k)
                if key is not None and key in self._memo:     # identical call, same state
                    self.memo_hits += 1
                    return copy.deepcopy(self._memo[key])
                for chunk in self._stage_chunks(name):
                    self._emit(chunk)
                self._emit({"tool_call": {"name": name, "args": k or list(a)},
                            "stage": STAGE_OF.get(name)})
                out = fn(*a, **k)
                if key is not None and not (isinstance(out, dict) and "error" in out):
                    # stored under the state before and after, so the same call repeated
                    # once the run files have moved on (a saved row, a new model) still hits
                    self._memo[key] = self._memo[self._memo_key(name, a, k)] = copy.deepcopy(out)
            if isinstance(out, dict) and "error" in out:
                # a failing tool is a recoverable error of the run, not something only the model sees
                self._emit({"type": "error", "stage": STAGE_OF.get(name), "message": str(out["error"])[:300]})
            if name == "get_property_bundle" and isinstance(out, dict) and "error" not in out:
                bundle = self.files.read_json("bundle.json")
                if bundle:
                    parsed = PropertyBundle.model_validate(bundle)
                    for ev in [*detect_fallbacks(parsed), *provenance_fallbacks(parsed)]:
                        self._emit(ev)
                    for line in provenance_warnings(parsed):      # and into RunResult.warnings
                        if line not in self._warnings:
                            self._warnings.append(line)
            if name == "build_building_model" and isinstance(out, dict) and "error" not in out:
                # what the geometry had to assume (for example: no wall graph in the scan, so the walls come from
                # the footprint) belongs to the user as a fallback of the run, not only to the model
                for flag in out.get("flags") or []:
                    if str(flag.get("key", "")).startswith("geometry.note."):
                        note = str(flag.get("message", ""))
                        self._emit(RunEvent(type="fallback", stage=STAGE_OF.get(name), message=note,
                                            payload={"fallback": "geometry:note"}))
                        if note and note not in self._warnings:
                            self._warnings.append(note)
            if name == "run_baseline" and isinstance(out, dict) and "error" not in out:
                # The analysis door substitutes the example weather year when the site's own
                # cached file is absent, which moves every energy figure. It is a fallback of
                # the run like any other, so it is said once, here, where it is decided.
                bundle = self.files.read_json("bundle.json")
                notes = self._climate_notes(bundle) if bundle else []
                for note in notes:
                    self._emit(RunEvent(type="fallback", stage=STAGE_OF.get(name), message=note,
                                        payload={"fallback": "weather:example_year"}))
                    if note not in self._warnings:
                        self._warnings.append(note)
            if name == "sensitivity" and isinstance(out, list):
                self.session.feed([Question.model_validate(q) for q in out])
            return out
        return wrapper

    def _climate_notes(self, bundle: dict) -> list[str]:
        """What the analysis door had to substitute for the site's weather. Never raises: a door
        that does not offer this (the stub, or an older one) simply has nothing to report, and a
        missing warning must not be the thing that fails a run."""
        reader = getattr(self.doors.analysis, "climate_notes", None)
        if reader is None:
            return []
        try:
            return list(reader(PropertyBundle.model_validate(bundle)))
        except Exception:
            return []

    # ---- the agent stream, as the runtime wants it ----

    def _prompt(self) -> str:
        r = self.request
        return (f"Audit the property with sid {r.sid}. Budget: ${r.budget_usd:,.0f}. Role: {r.role}. "
                f"Desks requested: {r.desks_requested}. Overrides already given by the user: "
                f"{json.dumps(r.overrides)}. Utility bills: {'given (12 monthly values)' if r.bills else 'not given'}. "
                "Follow the order in your instructions: scout, surveyor, "
                "physicist, financier, then the questions if sensitivity returned any, then report.md. "
                "Finish only when build_plan has returned a plan and report.md is written.")

    def _segment_config(self) -> dict:
        config = dict(self.config)
        if self._first_segment and self.tracing:
            config["run_id"] = self.trace_id
        self._first_segment = False
        return config

    def trace_url(self) -> Optional[str]:
        """Link to this run's first trace in LangSmith, or None (tracing off, not yet ingested, or
        any failure). Private: it is never put in an event, a result or a log."""
        if not self.tracing:
            return None
        try:
            from langchain_core.tracers.langchain import wait_for_all_tracers
            from langsmith import Client
            wait_for_all_tracers()
            client = Client()
            for _ in range(3):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")      # read_run is being renamed; the old name works
                        return client.read_run(self.trace_id).url
                except Exception:
                    time.sleep(2)
        except Exception:
            pass
        return None

    def _agent(self, graph_input: Any):
        async def agent(request, files) -> AsyncIterator:
            q: asyncio.Queue = asyncio.Queue()
            self._q, self._loop = q, asyncio.get_running_loop()

            async def produce():
                try:
                    async for chunk in self.graph.astream(graph_input, self._segment_config(),
                                                          stream_mode="updates"):
                        q.put_nowait(("chunk", chunk))
                    q.put_nowait(("end", None))
                except BaseException as exc:      # reported through the runtime as an error
                    q.put_nowait(("exc", exc))

            task = asyncio.create_task(produce())
            self.pending, interrupted = None, False
            while True:
                kind, item = await q.get()
                if kind == "event":
                    yield item
                elif kind == "chunk":
                    for out in self._map_update(item):
                        interrupted = interrupted or "question" in out
                        yield out
                elif kind == "exc":
                    raise item
                else:
                    break
            await task
            self._q = None
            if interrupted:
                return
            async for out in self._finish():
                yield out

        return agent

    def _map_update(self, update: dict) -> list[dict]:
        out: list[dict] = []
        for node, body in update.items():
            if node == "__interrupt__":
                payload = body[0].value if body else {}
                extra: dict = {}
                if "question" in payload:
                    q = Question.model_validate(payload["question"])
                    self.pending = ("question", q)
                elif "approval" in payload:
                    q = _approval_question(payload["approval"])
                    self.pending = ("approval", q)
                    extra = {"kind": "approval", "approval": payload["approval"]}
                else:
                    continue
                out.append({"question": q.model_dump(mode="json"), "stage": self._stage, **extra})
            elif isinstance(body, dict):
                if body.get("todos"):
                    out.append({"todos": body["todos"]})
                msgs = body.get("messages")
                msgs = msgs if isinstance(msgs, list) else []
                for m in msgs:
                    if getattr(m, "type", "") == "ai" and not getattr(m, "tool_calls", None):
                        text = _text(m.content)
                        if text.strip():
                            self._last_text = text
        return out

    def _build_plan_now(self) -> None:
        bundle = PropertyBundle.model_validate(self.files.read_json("bundle.json"))
        model = BuildingModel.model_validate(self.files.read_json("model.json"))
        plan = self.doors.analysis.build_plan(bundle, model, self.request)
        self.files.write("plan.json", plan.model_dump_json(indent=2))
        self.files.write("measures.json", [m.model_dump(mode="json")
                                           for m in [i.measure for i in plan.selected] + list(plan.financeable)])

    async def _plan_if_missing(self) -> AsyncIterator:
        """The plan is the point of a run. If the agent finished without building it (it chose not to,
        or every pricing call failed), the runtime builds it from the model the agent made, as
        SPEC 8 rule 5 allows for a decision the agent skipped, and says so."""
        if self.files.read_json("plan.json") is not None:
            return
        if self.files.read_json("bundle.json") is None or self.files.read_json("model.json") is None:
            yield {"type": "error", "stage": "S7",
                   "message": "the run ended without a building model, so no plan could be built"}
            return
        try:
            await asyncio.get_running_loop().run_in_executor(None, self._build_plan_now)
        except Exception as exc:
            yield {"type": "error", "stage": "S7", "message": f"the runtime could not build the plan: {type(exc).__name__}: {exc}"[:300]}
            return
        yield {"fallback": "The agent did not build the plan; the runtime built it from the building model.",
               "stage": "S7", "payload": {"fallback": "plan_built_by_runtime"}}

    async def _report_text(self) -> str:
        state = await self.graph.aget_state(self.config)
        vfiles = (state.values or {}).get("files") or {}
        for key in REPORT_KEYS:
            if key in vfiles:
                data = vfiles[key]
                content = data.get("content") if isinstance(data, dict) else data
                return "\n".join(content) if isinstance(content, list) else str(content or "")
        return self._last_text

    async def _ask_for_a_corrected_report(self, problems: list[str]) -> None:
        """One more turn for the auditor: the numbers no tool returned, and the instruction to rewrite."""
        message = ("report.md states numbers that no tool returned: " + "; ".join(problems[:8]) + ". Rewrite "
                   "report.md now, using only numbers copied exactly from tool results and removing any figure "
                   "you worked out yourself. You may call read_run_file and check_report; call no other tool.")
        async for chunk in self.graph.astream({"messages": [("user", message)]}, self._segment_config(),
                                              stream_mode="updates"):
            self._map_update(chunk)

    def _check(self, report: str) -> list[str]:
        result = build_result(self.run_id, self.request, self.files, "done")
        bundle = PropertyBundle.model_validate(self.files.read_json("bundle.json"))
        return check_narrative(report, result, bundle, result.building_model)

    async def _finish(self) -> AsyncIterator:
        async for out in self._plan_if_missing():
            yield out
        if self._stage:
            yield {"stage_done": self._stage, "message": STAGE_TITLE[self._stage]}
        yield {"stage_started": "S8", "message": STAGE_TITLE["S8"]}
        report = await self._report_text()
        if report:
            self.files.write("report.md", report)
            try:
                problems = self._check(report)
                if problems:        # SPEC 8 rule 1: the text may not state a number the tools did not return
                    yield {"fallback": f"The summary stated {len(problems)} number(s) no tool returned; the "
                                       "auditor was asked to correct it.", "stage": "S8",
                           "payload": {"fallback": "narrative_repair", "problems": problems[:8]}}
                    try:
                        await self._ask_for_a_corrected_report(problems)
                        report = await self._report_text() or report
                        self.files.write("report.md", report)
                        problems = self._check(report)
                    except Exception as exc:
                        yield {"type": "error", "stage": "S8", "message": f"narrative repair failed: {type(exc).__name__}: {exc}"[:300]}
                if problems:        # still wrong: drop the lines that state them, and say so
                    result = build_result(self.run_id, self.request, self.files, "done")
                    bundle = PropertyBundle.model_validate(self.files.read_json("bundle.json"))
                    report, dropped = remove_unsupported(report, result, bundle, result.building_model)
                    self.files.write("report.md", report)
                    yield {"type": "error", "stage": "S8",
                           "message": f"check_narrative: removed {len(dropped)} line(s) that stated numbers no result holds"}
            except ValueError:
                pass
        yield {"stage_done": "S8", "message": "Summary written"}

    # ---- threading ----

    def start(self) -> None:
        if self.tracing:
            # The key may be able to write traces but not read them back (then trace_url() is None),
            # so the ids that find the trace are kept with the run. Private: data/runs is git-ignored.
            (self.files.root / "trace.json").write_text(json.dumps({
                "trace_id": str(self.trace_id), "project": os.environ.get("LANGSMITH_PROJECT"),
                "run_id": self.run_id, "metadata_to_search": {"audit_run": self.run_id, "sid": self.request.sid}}, indent=2))
        self._thread.start()

    def _publish(self, event: RunEvent) -> None:
        self.events.append(event)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._main())
            self._record()
        except BaseException as exc:
            self._publish(RunEvent(type="error", message=f"{type(exc).__name__}: {exc}"))
        finally:
            self.active, self.closed = False, True

    async def _main(self) -> None:
        graph_input: Any = {"messages": [("user", self._prompt())]}
        loop = asyncio.get_running_loop()
        while True:
            self.active = True
            deferred: list[RunEvent] = []
            last: Optional[RunEvent] = None
            async for ev in execute_run(self.request, self._agent(graph_input), self.store,
                                        self.run_id):
                # A question is held back, and so is the final event, until the result is
                # saved and `active` is off, so GET /runs/{id} always agrees with the stream.
                if ev.type == "error" and ev.message not in self._warnings:
                    self._warnings.append(ev.message)          # kept across a pause and a resume
                if ev.type == "question":
                    deferred.append(ev)
                    continue
                if last is not None:
                    self.events.append(last)
                last = ev
            self._keep_asked_questions()
            # **Snapshot before the question becomes visible.** Whether this segment
            # paused is a fact about the segment; `self.pending` is also "a question is
            # open", and `answer()` clears it. Reading it *after* publishing the question
            # let a client that answered immediately make this branch say "no question
            # was asked": the run returned, closed with `question` as its last event, and
            # left the answer unconsumed in `_inbox`. `_write_usage` puts a disk write
            # inside that window, which is why it only showed up under multi-lane I/O.
            paused = self.pending is not None
            self.active = False
            if last is not None:
                self.events.append(last)
            self.events.extend(deferred)
            self._write_usage()
            if not paused:
                return
            graph_input = await loop.run_in_executor(None, self._inbox.get)
            self.active = True

    def _keep_asked_questions(self) -> None:
        """A resumed segment sees no question event and none of the earlier errors, so its saved
        result would drop the questions the user answered and the warnings of the first segment;
        keep both."""
        try:
            saved = self.store.load(self.run_id)
        except KeyError:
            return
        known = {q.id for q in saved.questions}
        missing = [q for q in self.session.asked if q.id not in known]
        warnings = list(dict.fromkeys([*self._warnings, *saved.warnings]))
        if missing or warnings != saved.warnings:
            self.store.save(self.run_id, saved.model_copy(update={
                "questions": [*saved.questions, *missing], "warnings": warnings}))

    def _record(self) -> None:
        """A run that finished with a plan is kept for demo replay: its events and its files, under
        data/runs/_demo/{sid}/ (git-ignored: they are derived from sponsor data). The replay mode of the
        run door serves it. Never raises."""
        try:
            result = self.store.load(self.run_id)
            if result.status != "done" or result.plan is None:
                return
            (self.files.root / "events.json").write_text(json.dumps(
                [e.model_dump(mode="json") for e in self.events], indent=1))
            target = demo_dir() / self.request.sid
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(self.files.root, target, ignore=shutil.ignore_patterns("assets", "*.tmp"))
        except Exception:
            pass

    def _write_usage(self) -> None:
        self.usage = dict(self.usage_handler.usage_metadata)
        (self.files.root / "usage.json").write_text(json.dumps(self.usage, indent=2))

    # ---- the door ----

    def answer(self, question_id: str, value) -> None:
        from langgraph.types import Command
        if self.closed:                     # nothing reads the inbox of a finished run: say so, do not queue
            raise LookupError(f"run {self.run_id} is closed; it cannot take an answer")
        if self.pending is None or self.pending[1].id != question_id:
            raise LookupError(f"no open question {question_id}")
        kind, _ = self.pending
        if kind == "approval":              # the counsel gate wants {"approved": bool}
            value = {"approved": value is True}
        self.pending = None
        self.active = True
        self._inbox.put(Command(resume={"value": value}))

    def update(self, budget_usd: Optional[float], overrides: Optional[dict]) -> None:
        """G11: a new budget and/or assumption values on a finished run; the plan is re-run by the
        analysis door (no model call) and the events of the re-run join the stream."""
        with self._update_lock:
            if self.active or not self.closed:
                raise PatchError(409, "run_not_done", f"run {self.run_id} is still running; adjust a finished run")
            result = self.store.load(self.run_id)
            new, events = replan(result, self.files, self.store, self.doors, budget_usd, overrides)
            self.request = new.request
            self.events.extend(events)

    def result(self) -> RunResult:
        if not self.active:
            try:
                return self.store.load(self.run_id)
            except KeyError:
                pass
        status = "error" if self.closed else "running"     # closed with nothing saved = failed
        try:
            return build_result(self.run_id, self.request, self.files, status)
        except ValueError:                   # nothing ingested yet
            from backend.data_layer import api as data
            return RunResult(run_id=self.run_id, status=status, request=self.request,
                             property=data.get_property_summary(self.request.sid))

    async def stream(self) -> AsyncIterator[RunEvent]:
        i = 0
        while True:
            while i < len(self.events):
                yield self.events[i]
                i += 1
            if self.closed and i >= len(self.events):
                return
            await asyncio.sleep(0.05)

    def draft(self, request: DocumentRequest) -> DocumentDraft:
        result = self.store.load(self.run_id)
        bundle = PropertyBundle.model_validate(self.files.read_json("bundle.json"))
        draft = self.doors.legal.fill_template(request, result, bundle)
        if not draft.statutory_checks:
            draft = draft.model_copy(update={"statutory_checks": self.doors.legal.check_document(draft)})
        self.docs[draft.doc_id] = draft
        return draft


_RUNS: dict[str, LiveRun] = {}


def use_live_data(settings: "LiveSettings") -> None:
    """A real live run (the real doors) uses live data. Without the flag the data layer hands back the example
    bundle and says so only in a provenance record, so a "live" recording would be of the fixtures. With the
    flag on and a key missing the run is refused here, before any model call. Fake doors (tests) are left alone."""
    if settings.doors is None:
        os.environ.setdefault("DATA_LAYER_LIVE", "1")
        require_live_data_keys()


def start_run(request: RunRequest) -> str:
    _load_env()
    configure_tracing()
    settings = SETTINGS or LiveSettings()
    use_live_data(settings)
    store = RunStore(settings.runs_dir or DEFAULT_RUNS_DIR)
    run = LiveRun(store.new_run_id(), request, settings)
    _RUNS[run.run_id] = run
    run.start()
    return run.run_id


def get(run_id: str) -> LiveRun:
    try:
        return _RUNS[run_id]
    except KeyError:
        raise KeyError(f"unknown run_id: {run_id}") from None

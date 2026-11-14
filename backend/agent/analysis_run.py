"""Real analysis (RunRequest.mode = "analysis"): the audit without the agent.

Live data is assembled, then the analysis door runs on the request's own budget, role, desks and bills, in the
fixed order of the agent's tools: bundle, interior, roof, model, (calibration), baseline, plan. The run files, the
events (stages, fallbacks, partial results) and the saved RunResult are the same as a live agent run's, so the UI
and the document routes work unchanged. The report is a template filled with the run's own figures
(`narrative.analysis_report`). No model is called. About ten seconds cold.

It is a LiveRun in everything but the graph: the tool wrappers, the events, the replan after a PATCH and the
documents are inherited. It is never recorded for demo replay (that would overwrite a real agent recording).
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from backend.agent import live
from backend.agent.live import LiveRun, LiveSettings
from backend.agent.narrative import analysis_report, check_narrative, remove_unsupported
from backend.agent.runtime.runtime import RunStore, build_result
from backend.agent.tools import ToolContext, build_tools
from backend.schema import PropertyBundle, RunEvent, RunRequest


class AnalysisFailed(RuntimeError):
    """A step of the fixed pipeline failed; the run says which and why, and ends in error."""


class AnalysisRun(LiveRun):
    def _build_agent(self, settings: LiveSettings) -> None:
        ctx = ToolContext(request=self.request, files=self.files, doors=self.doors,
                          run=lambda: build_result(self.run_id, self.request, self.files, "done"),
                          asset_dir=self.files.root / "assets")
        self.tools = {name: self._instrument(name, fn) for name, fn in build_tools(ctx).items()}
        self.tracing = False
        self.graph = None

    def _write_usage(self) -> None:           # no model, no usage
        pass

    def _record(self) -> None:                # a real-analysis run must never replace an agent recording
        pass

    def answer(self, question_id: str, value) -> None:
        raise LookupError("a real-analysis run asks no questions; change an assumption with a PATCH instead")

    # ---- the pipeline ----

    def _step(self, name: str, *args):
        out = self.tools[name](*args)
        if isinstance(out, dict) and "error" in out:
            raise AnalysisFailed(f"{name} failed: {out['error']}")
        return out

    def _pipeline(self) -> None:
        r = self.request
        self._step("get_property_bundle", r.sid)
        try:
            self._step("detect_roof_elements", ["roof"])
        except AnalysisFailed:
            pass                              # optional: the error event already tells the user
        self._step("observe_interior")
        self._step("build_building_model")
        if r.bills is not None:
            self._step("calibrate_model")
        self._step("run_baseline")
        plan = self._step("build_plan")
        measures = [i["measure"] for i in plan["selected"]] + list(plan["financeable"])
        self.files.write("measures.json", measures)

    def _agent(self, graph_input):
        async def agent(request, files) -> AsyncIterator:
            q: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_running_loop()
            self._q, self._loop = q, loop

            def work():
                try:
                    self._pipeline()
                    loop.call_soon_threadsafe(q.put_nowait, ("end", None))
                except BaseException as exc:
                    loop.call_soon_threadsafe(q.put_nowait, ("exc", exc))

            task = loop.run_in_executor(None, work)
            while True:
                kind, item = await q.get()
                if kind == "event":
                    yield item
                elif kind == "exc":
                    await asyncio.shield(task)
                    raise item
                else:
                    break
            await task
            self._q = None
            if self._stage:
                yield {"stage_done": self._stage, "message": live.STAGE_TITLE[self._stage]}
            yield {"stage_started": "S8", "message": live.STAGE_TITLE["S8"]}
            result = build_result(self.run_id, self.request, self.files, "done")
            yield {"type": "partial_result", "stage": "S7", "message": (
                f"{len(result.plan.selected)} measures within ${self.request.budget_usd:,.0f}; "
                f"{len(result.plan.financeable)} more financeable") if result.plan else "no plan"}
            result = result.model_copy(update={"warnings": list(dict.fromkeys(self._warnings))})
            report = analysis_report(result)
            bundle = PropertyBundle.model_validate(self.files.read_json("bundle.json"))
            problems = check_narrative(report, result, bundle, result.building_model)
            if problems:                      # a template should never state what the result does not hold
                report, dropped = remove_unsupported(report, result, bundle, result.building_model)
                yield {"type": "error", "stage": "S8",
                       "message": f"check_narrative: removed {len(dropped)} line(s) of the report"}
            self.files.write("report.md", report)
            yield {"stage_done": "S8", "message": "Summary written"}

        return agent


def start_run(request: RunRequest) -> str:
    live._load_env()
    settings = live.SETTINGS or LiveSettings()
    live.use_live_data(settings)
    store = RunStore(settings.runs_dir or live.DEFAULT_RUNS_DIR)
    run = AnalysisRun(store.new_run_id(), request, settings)
    live._RUNS[run.run_id] = run
    run.start()
    return run.run_id

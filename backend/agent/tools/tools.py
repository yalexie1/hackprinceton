"""Agent tools (G1): the 19 wrappers of workplan 3.4.

A wrapper takes only the small arguments the model supplies, reads large objects from the
run files, calls one door function, writes the result back to the run files and returns
JSON-able data. It does no arithmetic. A door that raises becomes {"error": message}.

Doors are passed in (`Doors`) so tests use fakes; `default_doors()` imports the real
`api.py` of each lane lazily. Run files are passed in as a `files` object with
`read_json(name)` and `write(name, content)` (the runtime's `RunFiles` fits).
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from backend.schema import (BaselineResult, BuildingModel, DocumentDraft, DocumentRequest,
                            MeasureResult, PropertyBundle, RunRequest, RunResult)

TOOL_NAMES = (
    "search_properties", "get_property_bundle", "get_asset", "observe_interior",
    "detect_roof_elements", "build_building_model", "set_assumption", "run_baseline",
    "evaluate_measure", "design_pv", "score_desk_positions", "price_measure",
    "lookup_incentives", "build_plan", "cpace_scenario", "sensitivity", "list_templates",
    "fill_template", "check_document",
)  # the 19 wrapper tools; ask_user (a pause, no door call) belongs to package G2


@dataclass
class Doors:
    data: Any       # module/object with the functions of workplan 3.1
    analysis: Any   # 3.2
    legal: Any      # 3.3


def default_doors() -> Doors:
    from backend.analysis import api as analysis
    from backend.data_layer import api as data
    from backend.legal import api as legal
    return Doors(data=data, analysis=analysis, legal=legal)


@dataclass
class ToolContext:
    request: RunRequest
    files: Any                                   # read_json(name) / write(name, content)
    doors: Doors
    run: Callable[[], RunResult]                 # current RunResult, for fill_template
    asset_dir: Optional[Any] = None              # where get_asset saves bytes
    drafts: dict[str, DocumentDraft] = field(default_factory=dict)
    observed: tuple[list, list] = field(default_factory=lambda: ([], []))


def _json(x):
    if hasattr(x, "model_dump"):
        return x.model_dump(mode="json")
    if isinstance(x, (list, tuple)):
        return [_json(i) for i in x]
    return x


def _safe(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as exc:     # a failing door never crashes the agent
            return {"error": f"{fn.__name__} failed: {type(exc).__name__}: {exc}"}
    return wrapper


def build_tools(ctx: ToolContext) -> dict[str, Callable]:
    d, files = ctx.doors, ctx.files

    def bundle() -> PropertyBundle:
        return PropertyBundle.model_validate(files.read_json("bundle.json"))

    def model() -> BuildingModel:
        return BuildingModel.model_validate(files.read_json("model.json"))

    def measures() -> list[dict]:
        return files.read_json("measures.json") or []

    def upsert_measure(m: MeasureResult) -> None:
        rows = [r for r in measures() if r["measure_id"] != m.measure_id]
        rows.append(m.model_dump(mode="json"))
        files.write("measures.json", rows)

    def find_measure(measure_id: str) -> MeasureResult:
        for r in measures():
            if r["measure_id"] == measure_id:
                return MeasureResult.model_validate(r)
        raise LookupError(f"measure {measure_id} has not been evaluated")

    tools: dict[str, Callable] = {}

    def tool(fn):
        tools[fn.__name__] = _safe(fn)
        return fn

    @tool
    def search_properties(q=None, segment=None, use_type=None, lat=None, lon=None,
                          radius_m=None, limit=20):
        return _json(d.data.search_properties(q, segment, use_type, lat, lon, radius_m, limit))

    @tool
    def get_property_bundle(sid: str):
        b = d.data.get_property_bundle(sid)
        files.write("bundle.json", b.model_dump_json(indent=2))
        return {"summary": _json(b.summary), "provenance": _json(b.provenance)}

    @tool
    def get_asset(path: str):
        data = d.data.get_asset(path)
        name = path.replace("/", "_")
        out = ctx.asset_dir / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return {"path": str(out), "bytes": len(data)}

    @tool
    def observe_interior():
        assumptions, flags = d.analysis.observe_interior(bundle())
        ctx.observed = (list(assumptions), list(flags))
        return {"assumptions": _json(assumptions), "flags": _json(flags)}

    @tool
    def detect_roof_elements(labels=None):
        b = bundle()
        found = d.data.detect_roof_elements(b.summary.sid, labels)
        if b.vexcel is not None:
            b.vexcel.detections = list(found)
            files.write("bundle.json", b.model_dump_json(indent=2))
        return _json(found)

    @tool
    def build_building_model():
        m = d.analysis.build_building_model(bundle(), ctx.observed[0], ctx.observed[1],
                                            ctx.request.overrides)
        files.write("model.json", m.model_dump_json(indent=2))
        return _json(m)

    @tool
    def set_assumption(key: str, value):
        m = d.analysis.set_assumption(model(), key, value)
        files.write("model.json", m.model_dump_json(indent=2))
        return _json(m)

    @tool
    def run_baseline():
        r = d.analysis.run_baseline(bundle(), model(), ctx.request.bills)
        files.write("baseline.json", r.model_dump_json(indent=2))
        return _json(r)

    @tool
    def evaluate_measure(measure_id: str):
        m = d.analysis.evaluate_measure(bundle(), model(), measure_id, ctx.request.role,
                                        ctx.request.desks_requested)
        upsert_measure(m)
        return _json(m)

    @tool
    def design_pv(budget_usd: Optional[float] = None):
        baseline = BaselineResult.model_validate(files.read_json("baseline.json"))
        return _json(d.analysis.design_pv(bundle(), model(), baseline, budget_usd))

    @tool
    def score_desk_positions(desks_requested: Optional[int] = None):
        return _json(d.analysis.score_desk_positions(bundle(), model(), desks_requested))

    @tool
    def price_measure(measure_id: str):
        m = d.analysis.price_measure(bundle(), find_measure(measure_id))
        upsert_measure(m)
        return _json(m)

    @tool
    def lookup_incentives(measure_id: str):
        return _json(d.analysis.lookup_incentives(measure_id, bundle().summary))

    @tool
    def build_plan(budget_usd: Optional[float] = None):
        request = ctx.request if budget_usd is None else ctx.request.model_copy(
            update={"budget_usd": budget_usd})
        p = d.analysis.build_plan(bundle(), model(), request)
        files.write("plan.json", p.model_dump_json(indent=2))
        return _json(p)

    @tool
    def cpace_scenario(measure_id: str):
        return _json(d.analysis.cpace_scenario(bundle(), find_measure(measure_id)))

    @tool
    def sensitivity():
        return _json(d.analysis.sensitivity(bundle(), model(), ctx.request))

    @tool
    def list_templates(state: Optional[Literal["CA", "TX"]] = None):
        return _json(d.legal.list_templates(state, bundle().summary.segment))

    @tool
    def fill_template(doc_type: str, state: str, measure_ids: list, fields: Optional[dict] = None):
        # Approval before drafting (SPEC 8 rule 4) is enforced by the graph (G6), not here.
        req = DocumentRequest(run_id=ctx.run().run_id, doc_type=doc_type, state=state,
                              measure_ids=measure_ids, fields=fields or {})
        draft = d.legal.fill_template(req, ctx.run(), bundle())
        ctx.drafts[draft.doc_id] = draft
        return _json(draft)

    @tool
    def check_document(doc_id: str):
        return _json(d.legal.check_document(ctx.drafts[doc_id]))

    return tools

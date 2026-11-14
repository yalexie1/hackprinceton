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

from backend.schema import (BaselineResult, BuildingModel, DocType, DocumentDraft, DocumentRequest,
                            MeasureId, MeasureResult, PropertyBundle, RunRequest, RunResult, Segment,
                            UseType)

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
    #: Why a door is not the real one, when it is not. `live.default_doors()` falls back
    #: to `analysis_stub` if `backend.analysis.api` cannot be imported, and that swap
    #: used to be silent: a missing numpy or shapely on the demo machine would replay
    #: fixtures for the whole analysis lane with nothing in the run saying so, leaving
    #: someone to debug the numbers. Set here, reported as a run warning.
    degraded: Optional[str] = None


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

    def need(name: str, produced_by: str):
        """A run file the tool reads: a clear message, naming the tool that makes it, when it is not there yet."""
        content = files.read_json(name)
        if content is None:
            raise LookupError(f"{name} does not exist yet: call {produced_by} first")
        return content

    def bundle() -> PropertyBundle:
        return PropertyBundle.model_validate(need("bundle.json", "get_property_bundle"))

    def model() -> BuildingModel:
        return BuildingModel.model_validate(need("model.json", "build_building_model"))

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
        raise LookupError(f"measure {measure_id} has not been evaluated: call evaluate_measure({measure_id!r}) first")

    tools: dict[str, Callable] = {}

    def tool(fn):
        tools[fn.__name__] = _safe(fn)
        return fn

    @tool
    def search_properties(q: Optional[str] = None, segment: Optional[Segment] = None,
                          use_type: Optional[UseType] = None, lat: Optional[float] = None,
                          lon: Optional[float] = None, radius_m: Optional[float] = None, limit: int = 20):
        """Search the property index. Not needed when the sid is already given in the task."""
        return _json(d.data.search_properties(q, segment, use_type, lat, lon, radius_m, limit))

    @tool
    def get_property_bundle(sid: str):
        """Fetch and save the property's data (Matterport scan, Vexcel roof, CoStar record, weather,
        tariff). Call it once, first, with the sid from the task. Returns the summary and what was
        missing or substituted."""
        b = d.data.get_property_bundle(sid)
        files.write("bundle.json", b.model_dump_json(indent=2))
        return {"summary": _json(b.summary), "provenance": _json(b.provenance)}

    @tool
    def get_asset(path: str):
        """Save one cached image. `path` is a file path read from the bundle (a face, ortho or oblique
        path), never a property id. Optional: the analysis does not need the images saved."""
        data = d.data.get_asset(path)
        name = path.replace("/", "_")
        out = ctx.asset_dir / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return {"path": str(out), "bytes": len(data)}

    @tool
    def observe_interior():
        """Read the interior observations (glazing, HVAC, water heater, lighting, panel). Call once,
        after get_property_bundle and before build_building_model."""
        assumptions, flags = d.analysis.observe_interior(bundle())
        ctx.observed = (list(assumptions), list(flags))
        return {"assumptions": _json(assumptions), "flags": _json(flags)}

    @tool
    def detect_roof_elements(labels: Optional[list[str]] = None):
        """Roof detections from the aerial imagery; use the label "roof". Optional, once."""
        b = bundle()
        found = d.data.detect_roof_elements(b.summary.sid, labels)
        if b.vexcel is not None:
            b.vexcel.detections = list(found)
            files.write("bundle.json", b.model_dump_json(indent=2))
        return _json(found)

    @tool
    def build_building_model():
        """Build the building model (zones, walls, windows, systems, roof planes, assumptions) from the
        bundle and the interior observations. Call once, after observe_interior. Nothing that needs the
        model works before this."""
        m = d.analysis.build_building_model(bundle(), ctx.observed[0], ctx.observed[1],
                                            ctx.request.overrides)
        files.write("model.json", m.model_dump_json(indent=2))
        return _json(m)

    @tool
    def set_assumption(key: str, value: float | str | bool):
        """Set one assumption of the model to a value the user gave. `key` must be one of the keys in the
        model returned by build_building_model, and `value` of the kind that assumption has (a number for
        a range, text or true/false otherwise). Only after build_building_model, and only for a user's answer."""
        m = d.analysis.set_assumption(model(), key, value)
        files.write("model.json", m.model_dump_json(indent=2))
        return _json(m)

    @tool
    def run_baseline():
        """Simulate the building as it is (energy, cost and CO2 per year, with a range). Call once, after
        build_building_model."""
        r = d.analysis.run_baseline(bundle(), model(), ctx.request.bills)
        files.write("baseline.json", r.model_dump_json(indent=2))
        return _json(r)

    @tool
    def evaluate_measure(measure_id: MeasureId):
        """Evaluate one measure against the current building: its annual saving, with a range, or why it
        does not apply. Call once per measure of this property type, after run_baseline; do not repeat
        a measure and do not use ids outside the allowed values."""
        m = d.analysis.evaluate_measure(bundle(), model(), measure_id, ctx.request.role,
                                        ctx.request.desks_requested)
        upsert_measure(m)
        return _json(m)

    @tool
    def design_pv(budget_usd: Optional[float] = None):
        """Lay out rooftop panels on the roof planes, stopping at the roof, the budget or the annual
        consumption. Optional: evaluate_measure("PV_ROOF") already designs the array."""
        baseline = BaselineResult.model_validate(files.read_json("baseline.json"))
        return _json(d.analysis.design_pv(bundle(), model(), baseline, budget_usd))

    @tool
    def score_desk_positions(desks_requested: Optional[int] = None):
        """Score desk positions for daylight, glare and comfort. Optional: evaluate_measure("LAYOUT")
        already places the desks."""
        return _json(d.analysis.score_desk_positions(bundle(), model(), desks_requested))

    @tool
    def price_measure(measure_id: MeasureId):
        """Price a measure that evaluate_measure found applicable: installed cost with its source,
        incentives, net upfront cash, payback, NPV. Once per applicable measure, after evaluate_measure."""
        m = d.analysis.price_measure(bundle(), find_measure(measure_id))
        upsert_measure(m)
        return _json(m)

    @tool
    def lookup_incentives(measure_id: MeasureId):
        """The incentives that can apply to a measure at this property, with status and citation.
        Optional: price_measure already carries them."""
        return _json(d.analysis.lookup_incentives(measure_id, bundle().summary))

    @tool
    def build_plan(budget_usd: Optional[float] = None):
        """Choose the measures that fit the budget (highest annual saving first) and return the plan:
        selected, financeable, skipped with reasons, totals. REQUIRED: every run ends with a plan. Call it
        after sensitivity, and again once if the user's answers changed an assumption."""
        request = ctx.request if budget_usd is None else ctx.request.model_copy(
            update={"budget_usd": budget_usd})
        p = d.analysis.build_plan(bundle(), model(), request)
        files.write("plan.json", p.model_dump_json(indent=2))
        return _json(p)

    @tool
    def cpace_scenario(measure_id: MeasureId):
        """The C-PACE financing scenario of a priced measure. Commercial properties only; a home is
        never eligible."""
        return _json(d.analysis.cpace_scenario(bundle(), find_measure(measure_id)))

    @tool
    def sensitivity():
        """Find the assumptions whose uncertainty changes the plan (SPEC 5.3). Returns the questions to
        ask the user, at most three, or none. Call once, after pricing and before build_plan."""
        return _json(d.analysis.sensitivity(bundle(), model(), ctx.request))

    @tool
    def list_templates(state: Optional[Literal["CA", "TX"]] = None):
        """The document types available for a state."""
        return _json(d.legal.list_templates(state, bundle().summary.segment))

    @tool
    def fill_template(doc_type: DocType, state: Literal["CA", "TX"], measure_ids: list[MeasureId],
                      fields: Optional[dict] = None):
        """Draft a document for the measures given. Leaves party names, licence numbers and addresses
        blank unless supplied. The user approves the parties and measures before this runs."""
        # Approval before drafting (SPEC 8 rule 4) is enforced by the graph (G6), not here.
        req = DocumentRequest(run_id=ctx.run().run_id, doc_type=doc_type, state=state,
                              measure_ids=measure_ids, fields=fields or {})
        draft = d.legal.fill_template(req, ctx.run(), bundle())
        ctx.drafts[draft.doc_id] = draft
        return _json(draft)

    @tool
    def check_document(doc_id: str):
        """Run the statutory checks on a draft made by fill_template, by its doc_id."""
        return _json(d.legal.check_document(ctx.drafts[doc_id]))

    return tools


READABLE = ("plan.json", "measures.json", "baseline.json", "bundle.json")


def build_reader_tools(ctx: ToolContext) -> dict[str, Callable]:
    """The auditor's and the reviewer's read-only tools (not among the 19 wrappers): the numbers a
    report may state are the ones in the run files, and `check_report` tests a draft against them."""
    from backend.agent.narrative import check_narrative
    files = ctx.files

    def read_run_file(name: Literal["plan.json", "measures.json", "baseline.json", "bundle.json"]):
        """Read one run file: /run/plan.json, /run/measures.json, /run/baseline.json or /run/bundle.json
        (its summary only). Every number in report.md must be copied, digit for digit, from these."""
        name = name.rsplit("/", 1)[-1]
        if name not in READABLE:
            return {"error": f"read_run_file: {name} is not readable; use one of {', '.join(READABLE)}"}
        content = files.read_json(name)
        if content is None:
            return {"error": f"/run/{name} does not exist yet"}
        if name == "bundle.json":
            return {"summary": content.get("summary")}
        return content

    def check_report(report_md: str):
        """Check a draft of report.md: lists each number that no tool result holds (an empty list means the
        draft is clean). Run it on the draft before you finish, and fix every line it lists."""
        result = ctx.run()
        bundle = files.read_json("bundle.json")
        bundle = PropertyBundle.model_validate(bundle) if bundle else None
        return {"problems": check_narrative(report_md, result, bundle, result.building_model)}

    return {"read_run_file": _safe(read_run_file), "check_report": _safe(check_report)}

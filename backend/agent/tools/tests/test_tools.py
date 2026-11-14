import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agent.tools import TOOL_NAMES, Doors, ToolContext, build_tools
from backend.agent.tools import tools as tools_module
from backend.schema import (Assumption, BaselineResult, BuildingModel, DocumentDraft, Flag,
                            MeasureResult, Plan, PropertyBundle, Question, RunRequest,
                            RunResult)

EX = Path(__file__).resolve().parents[4] / "specs" / "examples" / "house"


def J(name):
    return json.loads((EX / name).read_text())


class Files:
    def __init__(self):
        self.d = {}

    def read_json(self, n):
        return self.d.get(n)

    def write(self, n, c):
        self.d[n] = json.loads(c) if isinstance(c, str) else c


RUN = RunResult.model_validate(J("run_result.json"))
BUNDLE = PropertyBundle.model_validate(J("property_bundle.json"))
MODEL = BuildingModel.model_validate(J("building_model.json"))
BASE = RUN.baseline
MEAS = RUN.measures[0]
DRAFT = DocumentDraft.model_validate(J("document_draft.json"))


def fake_doors():
    data = SimpleNamespace(
        search_properties=lambda *a: [BUNDLE.summary],
        get_property_bundle=lambda sid: BUNDLE,
        get_asset=lambda path: b"img",
        detect_roof_elements=lambda sid, labels=None: [])
    analysis = SimpleNamespace(
        observe_interior=lambda b: ([], []),
        build_building_model=lambda b, o, f, ov: MODEL,
        set_assumption=lambda m, k, v: MODEL,
        run_baseline=lambda b, m, bills: BASE,
        evaluate_measure=lambda b, m, mid, role, desks: MEAS,
        design_pv=lambda b, m, base, budget: MEAS.solar or {"x": 1},
        score_desk_positions=lambda b, m, n: [],
        price_measure=lambda b, m: m,
        lookup_incentives=lambda mid, s: [],
        build_plan=lambda b, m, r: RUN.plan,
        cpace_scenario=lambda b, m: [],
        sensitivity=lambda b, m, r: RUN.questions)
    legal = SimpleNamespace(list_templates=lambda state, seg: ["retrofit_contract_residential"],
                            fill_template=lambda req, run, bundle: DRAFT,
                            check_document=lambda draft: draft.statutory_checks)
    return Doors(data, analysis, legal)


def make(tmp_path, doors=None):
    files = Files()
    ctx = ToolContext(request=RUN.request, files=files, doors=doors or fake_doors(),
                      run=lambda: RUN, asset_dir=tmp_path)
    return build_tools(ctx), files


def test_all_19_named_tools_exist(tmp_path):
    tools, _ = make(tmp_path)
    assert len(TOOL_NAMES) == 19 and set(tools) == set(TOOL_NAMES)


def test_pipeline_returns_valid_json_and_writes_files(tmp_path):
    t, files = make(tmp_path)
    out = t["get_property_bundle"](BUNDLE.summary.sid)
    assert set(out) == {"summary", "provenance"} and "bundle.json" in files.d
    t["search_properties"]()
    assert t["get_asset"]("a/b.jpg")["bytes"] == 3
    t["observe_interior"]()
    t["detect_roof_elements"](["roof"])
    BuildingModel.model_validate(t["build_building_model"]())
    BuildingModel.model_validate(t["set_assumption"]("k", 1.0))
    BaselineResult.model_validate(t["run_baseline"]())
    MeasureResult.model_validate(t["evaluate_measure"](MEAS.measure_id))
    MeasureResult.model_validate(t["price_measure"](MEAS.measure_id))
    assert [m["measure_id"] for m in files.d["measures.json"]] == [MEAS.measure_id]
    t["design_pv"](1000.0); t["score_desk_positions"](); t["lookup_incentives"](MEAS.measure_id)
    Plan.model_validate(t["build_plan"](5000.0)); t["cpace_scenario"](MEAS.measure_id)
    [Question.model_validate(q) for q in t["sensitivity"]()]
    assert "retrofit_contract_residential" in t["list_templates"]("CA")
    draft = t["fill_template"]("retrofit_contract_residential", "CA", [MEAS.measure_id])
    DocumentDraft.model_validate(draft)
    assert t["check_document"](draft["doc_id"])
    for name in ("model.json", "baseline.json", "plan.json"):
        assert name in files.d


def test_door_exception_becomes_error_message(tmp_path):
    doors = fake_doors()
    def boom(*a, **k):
        raise LookupError("unknown sid")
    doors.data.get_property_bundle = boom
    t, _ = make(tmp_path, doors)
    out = t["get_property_bundle"]("zzz")
    assert "error" in out and "unknown sid" in out["error"]
    assert "error" in t["run_baseline"]()      # no bundle.json yet: also a message, not a crash


def test_no_arithmetic_in_wrappers():
    tree = ast.parse(inspect.getsource(tools_module))
    # `/` joins paths and `|` is a type union; every other operator would be arithmetic
    ops = [n for n in ast.walk(tree)
           if isinstance(n, ast.AugAssign)
           or (isinstance(n, ast.BinOp) and not isinstance(n.op, (ast.Div, ast.BitOr)))]
    assert ops == []


# ---- the tool schemas the model sees ----

def _schema(name, tools=None):
    from backend.agent.graph.graph import as_langchain_tool
    tools = tools or make(Path("."))[0]
    return as_langchain_tool(name, tools[name]).args_schema.model_json_schema()


def _enum(prop):
    """The allowed values of a property, whether the schema nests them in anyOf or not."""
    if "enum" in prop:
        return set(prop["enum"])
    for part in prop.get("anyOf", []) + prop.get("allOf", []):
        if "enum" in part:
            return set(part["enum"])
    return None


def test_measure_tools_list_the_allowed_measure_ids():
    from typing import get_args
    from backend.schema import MeasureId
    allowed = set(get_args(MeasureId))
    for name in ("evaluate_measure", "price_measure", "lookup_incentives", "cpace_scenario"):
        assert _enum(_schema(name)["properties"]["measure_id"]) == allowed, name


def test_document_and_search_tools_list_their_allowed_values():
    from typing import get_args
    from backend.schema import DocType, Segment, UseType
    fill = _schema("fill_template")["properties"]
    assert _enum(fill["doc_type"]) == set(get_args(DocType)) and _enum(fill["state"]) == {"CA", "TX"}
    assert _enum(fill["measure_ids"]["items"]) is not None
    search = _schema("search_properties")["properties"]
    assert _enum(search["segment"]) == set(get_args(Segment)) and _enum(search["use_type"]) == set(get_args(UseType))
    assert _enum(_schema("list_templates")["properties"]["state"]) == {"CA", "TX"}


def test_every_tool_describes_itself_and_the_order_it_belongs_in():
    from backend.agent.graph.graph import as_langchain_tool
    tools, _ = make(Path("."))
    for name, fn in tools.items():
        doc = as_langchain_tool(name, fn).description
        assert len(doc) > 40 and doc != name.replace("_", " "), name
    assert "REQUIRED" in as_langchain_tool("build_plan", tools["build_plan"]).description
    assert "never a property id" in as_langchain_tool("get_asset", tools["get_asset"]).description


def test_a_tool_called_too_early_says_which_tool_to_call_first(tmp_path):
    tools, files = make(tmp_path)
    for name, args, first in (("build_building_model", (), "get_property_bundle"),
                              ("run_baseline", (), "get_property_bundle")):
        out = tools[name](*args)
        assert "error" in out and f"call {first} first" in out["error"], name
    tools["get_property_bundle"]("zvKHR9DHNjJ")
    out = tools["set_assumption"]("occupancy.count", 4.0)
    assert "error" in out and "call build_building_model first" in out["error"]
    out = tools["price_measure"]("LGT_LED")
    assert "error" in out and "call evaluate_measure('LGT_LED') first" in out["error"]


def test_reader_tools_return_run_files_and_check_a_draft(tmp_path):
    from backend.agent.tools import build_reader_tools
    t, files = make(tmp_path)
    ctx = ToolContext(request=RUN.request, files=files, doors=fake_doors(), run=lambda: RUN, asset_dir=tmp_path)
    r = build_reader_tools(ctx)
    assert set(r) == {"read_run_file", "check_report"}
    assert "does not exist" in r["read_run_file"]("plan.json")["error"]
    t["get_property_bundle"](BUNDLE.summary.sid); t["build_building_model"](); t["run_baseline"](); t["build_plan"](5000.0)
    assert r["read_run_file"]("/run/plan.json") == r["read_run_file"]("plan.json") and "error" not in r["read_run_file"]("plan.json")
    assert set(r["read_run_file"]("bundle.json")) == {"summary"}
    assert "not readable" in r["read_run_file"]("model.json")["error"]
    clean = r["check_report"]("The property has no figures here.")
    assert clean == {"problems": []}
    assert r["check_report"]("It saves $987,654,321 a year.")["problems"]

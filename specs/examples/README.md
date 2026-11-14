# Example payloads for the shared contract

One house and one office, written as JSON for every type in the contract (`specs/SPEC.md` section 9, `SCHEMA_VERSION` 0.2.0). Lanes build and test against these files until the real doors are live.

**These files are hand-made examples, not analysis output and not a capture of sponsor data.** No API response and no CoStar kit record is copied here. A short list of values is real (section 2): identifiers, the georeference, and a few Vexcel attribute values that `specs/data-integration.md` already records. Every other number, name, polygon and sentence is ILLUSTRATIVE: it was invented to be internally consistent, and it says nothing about the real buildings. Do not quote an energy, cost, savings, tenant or market figure from these files as a finding.

## 1. Files

`house/` is the golden house, Matterport model `zvKHR9DHNjJ`. `office/` is the golden office, model `HjEyXryhRLk`.

| File (in `house/` and in `office/`) | Contract type | Produced by | Where it appears in the API (SPEC section 10) |
|---|---|---|---|
| `property_summary.json` | `PropertySummary` | S1 Locate, Data | `GET /api/properties/{sid}` |
| `property_bundle.json` | `PropertyBundle` | S2 Ingest, Data | not served; `get_property_bundle(sid)`, agent file `/run/bundle.json` |
| `building_model.json` | `BuildingModel` | S4 Model, Analysis | inside `RunResult.building_model` |
| `baseline_result.json` | `BaselineResult` | S5 Baseline, Analysis | inside `RunResult.baseline` |
| `measures.json` | `MeasureResult[]` | S6 Measures, Analysis | inside `RunResult.measures`; each measure evaluated against the baseline |
| `plan.json` | `Plan` | S7 Plan, Analysis | inside `RunResult.plan`; each selected measure evaluated against the state when it was picked |
| `run_request.json` | `RunRequest` | Frontend | body of `POST /api/runs` |
| `run_result.json` | `RunResult` | Agent and server | `GET /api/runs/{run_id}`; embeds the six files above unchanged |
| `run_events.json` | `RunEvent[]` | Agent and server | `GET /api/runs/{run_id}/events`, one array element per server-sent event |
| `document_request.json` | `DocumentRequest` | Frontend | body of `POST /api/runs/{run_id}/documents` |
| `document_draft.json` | `DocumentDraft` | S9 Draft, Agent | returned by the two `documents` routes |
| `plan_tenant.json`, `run_request_tenant.json` | `Plan`, `RunRequest` | as above | the same property run with `role: "tenant"`, to show measures skipped for the role |

`search_results.json` (top level) is a `PropertySummary[]`, the response of `GET /api/properties/search`. It holds the two golden properties, the two other models of the golden office property (real model ids, same `costar_property_id`), and four invented entries whose `sid` starts with `EXAMPLE`.

File names here follow the brief this folder was written from. `specs/workplan.md` section 2.3 proposes other names for the same content. Until one naming is chosen, the mapping is:

| workplan alias | workplan file name | File here |
|---|---|---|
| `bundle` | `property_bundle.house.json`, `property_bundle.office.json` | `house/property_bundle.json`, `office/property_bundle.json` |
| `model` | `building_model.*.json` | `*/building_model.json` |
| `run` | `run_result.*.json` | `*/run_result.json` |
| `docreq`, `draft` | `document_request.*.json`, `document_draft.*.json` | `*/document_request.json`, `*/document_draft.json` |
| `search` | `property_search.json` | `search_results.json` |
| `events` | `run_events.house.jsonl` (one event per line) | `*/run_events.json` (one JSON array) |
| `ask`, `weather` | `building_model.ask_wide.json`, `building_model.ask_narrow.json`, `weather.sample.csv` | not written yet |

## 2. Which values are real

Real means: stated in the brief for this folder or verified live by the Data lane in `specs/data-integration.md` on 2026-11-14. Everything not in these two tables is illustrative.

### House, `zvKHR9DHNjJ`

| Value | Where | Source |
|---|---|---|
| Model id, address 5836 La Mirada Ave, Los Angeles, CA 90038, residential, has a splat and a defurnished view | `PropertySummary` | brief; data-integration 2.6 |
| 1 floor, 19 rooms, 39 panoramas | `PropertySummary` counts | brief. The example carries only 4 rooms and 3 panoramas |
| `ListingId` 235967170, `ResidentialListingId` 221139020; `record_id` equals the `ListingId` | `PropertySummary`, `CostarData` | data-integration 2.4, 2.6 |
| Label, area, width, depth and height of the four rooms (Living Room 28.87 m2, Dining Room 22.71, Kitchen 13.28, Bedroom 17.18 with no height) | `MatterportData.rooms` | brief |
| Wall thickness values 0.16 m and 0.28 m | `WallEdge.thickness_m` | brief. Which wall has which thickness is invented |
| Georeference: latitude 34.093491666999995, longitude -118.3171, altitude 120.2, rotation quaternion (0, 0, 0.7289895896353398, 0.6845247827531877), source `processing` | `MatterportData.georeference` | data-integration 3.2. `translation` was not recorded and is null |
| Opening type `doorway` occurs on this model | `Opening.type` | data-integration 3.3. Sizes and positions are invented |
| Vexcel parcel attributes: `structure.count` 2, `parcel-source` Bins, `parcel-tree-cover.percent` 30, `hardscapes.area` 128 | `VexcelData.attributes` | data-integration 4.2 |
| Vexcel primary structure: footprint 190.39 m2, ground elevation 100.584, gable, shingle, condition 5.0, roof tree cover 4, 2 AC units, 1 chimney, 5 roof vents, 0 skylights, no solar, `building-type.class` null, roof elevation 100.220123 and height 0.363877 (implausible, carried as returned) | `VexcelStructure.attributes`, `footprint_area_m2` | data-integration 4.2, 4.3 |

### Office, `HjEyXryhRLk`

| Value | Where | Source |
|---|---|---|
| Model id, name "Suite A - 2,000SF", CoStar `PropertyId` 354635, address 9050 Emnora Ln, Houston, TX, no splat; `record_id` equals the `PropertyId` | `PropertySummary`, `CostarData` | brief; data-integration 2.6, 3.2 |
| The property has two more models, `B9b1hGuh61v` and `cpBz4ivmcTN` | `search_results.json` | data-integration 2.6. Their names and counts are invented |
| Georeference: latitude 29.816116896197208, longitude -95.51538273549774, altitude 25.039, rotation z 0.6964351 and w 0.7176198, source `processing` | `MatterportData.georeference` | data-integration 3.2, 4.5. z and w are the seven digits recorded there; x = y = 0 is assumed; `translation` is null |
| Vexcel: 1 structure, footprint 1,215.91 m2, ground elevation 26.5176, gable, metal, roof tree cover 1, 0 AC units, 0 skylights, no solar, `building-type.class` commercial, roof elevation 30.456892, height 3.939292 | `VexcelData`, `VexcelStructure.attributes` | data-integration 4.3, 4.5 |

Real as vocabulary, in both examples: the opening types `divider`, `doorway`, `opening`, `window`; the edge types `wall` and `invisible`; the georeference sources `client`, `processing`, `unknown`; CoStar `propertyType` 5 = Office and the construction event name `ConstructionComplete`; the Vexcel attribute keys used; the SAM 3 label `roof` and image ids of the form `ortho-1`, `oriented-1`. That the golden office itself has `propertyType` 5 is not verified.

### Illustrative, stated plainly

- **All energy, cost, savings, payback, NPV, SIR, IRR, CO2 and value-uplift numbers**, the tariffs, the emission factors, the incentives (their names say so) and the economic rates.
- **All CoStar normalised values**: year built, building class, areas, stories. **All tenants and the market data** in the office (`occupancy`, `market`): the names carry "(illustrative)". `CostarData.raw` holds only a `_note`: no kit record and no kit field name is copied into this folder.
- **The wall graphs**: vertex positions, which rooms touch, every opening's size and position, the invisible edge. House rooms are drawn as rectangles from the real width and depth, so a polygon's area differs a little from the real `area_m2`. The office suite (15.0 m by 12.4 m, five rooms, 2.74 m ceilings) is invented apart from its 2,000 sq ft size.
- **The house has no window openings on purpose.** It shows the fallback of SPEC section 5.1 (window sizes from vision, source `vision`, wider range). Whether the real model has window openings is not known. The office shows the measured path: eight openings of type `window`, and the window surfaces of its building model are computed from them.
- **Panorama positions, the office's pano and room counts, floor plans, all cache paths.** No file behind any path exists.
- **Roof geometry**: every WKT polygon (parcel, footprint, roof planes, panels, detections) is a rectangle invented in the model frame and rotated to the map with the real georeference. Only the footprint area is real. Tilt ranges, usable areas and the ridge direction are invented.
- **SAM 3 detections**: invented, but shaped like the live behaviour on the house (roof fragments rather than planes, confidence 0.31 to 0.70, a pixel box and a mask PNG path). `mask_wkt` is null where the map polygon "has not been derived yet".
- **Documents**: the draft text is a sketch. Requirement ids and citations are copied from `specs/legal/california.md` section 2 and `specs/legal/texas.md` section 6; each `satisfied` value is illustrative. Placeholder names are examples until the legal spec's placeholder table is final.
- **Shared string keys**: assumption keys, flag keys, `end_use_kwh` keys, `occupancy_schedule` keys, `hvac_type` and `dhw_type` values, `formula_ids` (physics section ids such as `ENV`, `PV`, `DAY`) and the value-uplift method `VAL` are this folder's guesses. The physics spec decides the real lists (workplan open item O10).

## 3. Conventions these examples assume

The contract leaves these open. The examples had to pick one reading; treat each as a proposal until its owner confirms it.

1. **North.** `BuildingModel.north_offset_deg` is taken as the rotation about z carried by the georeference quaternion, `2 * atan2(z, w)` in degrees: 93.60 for the house, 88.28 for the office (`data-integration.md` rounds these to 93.7 and 88.3). The quaternion is read as rotating the model frame into east-north-up, so a model-frame direction at angle `a` (counter-clockwise from model +x) has compass azimuth `(90 - a - north_offset_deg) mod 360`. With this reading model +x points about north on both golden models, and `north_offset_deg` is the clockwise angle from model +y to true north. Every `Surface.azimuth_deg`, `RoofPlane.azimuth_deg` and WKT polygon here follows it. The sign has not been checked against imagery.
2. **`Opening.relative_center`** is written as a fraction from 0 to 1 along the edge, measured from the first id in `vertex_ids`. The Model API's own convention is not recorded yet.
3. **Map polygons** are WKT, longitude first, in degrees.
4. **`VexcelDetection.pixel_bbox`** is `[x, y, width, height]` in image pixels.
5. **Vexcel attribute counts** are JSON numbers and validate as floats (`2.0`), because the attribute value type has no integer member.
6. **`RunEvent.stage`** is one of `S1` to `S9` (SPEC section 6.1) or null. `RunEvent.payload` shapes used here:

   | `type` | `payload` |
   |---|---|
   | `stage_started` | empty |
   | `stage_done` | empty, or `{sid}`, or `{artifact}` with the agent file written |
   | `todo` | `{todos: [{content, status}]}` |
   | `tool_call` | `{agent, tool, args}` |
   | `fallback` | `{layer, from, to}` |
   | `question` | `{question: Question}` |
   | `partial_result` | `{kind: "baseline", artifact, annual_cost_usd: Ranged}` or `{kind: "finding", measure_id, anchor: Anchor}` |
   | `error` | `{code, message, recoverable}` |
   | `done` | `{run_id, status}` |

7. **Money rules** (SPEC sections 6.5 and 6.6): net upfront cash is installed cost minus point-of-sale rebates whose status is `verified`; unverified and expired incentives are listed and not subtracted. Simple payback is net upfront divided by annual savings. A C-PACE scenario finances the expected net upfront cost over a term no longer than the useful life. Value uplift is annual savings divided by the comparable-sales capitalisation rate (a placeholder formula; the physics value module is not written).

## 4. What each example shows

**House** (`role: owner_occupier`, budget $14,000). Three selected measures in the order of the budget algorithm: `PV_ROOF` (with a `SolarDesign` of seven panels and the warning "may exceed budget", because the electrical service flag is `unknown`), `ENV_ATTIC`, `LGT_LED`. `HVAC_HP` saves more than the LED retrofit but does not fit, so it is skipped as `over_budget` and listed as financeable, evaluated against the final state. Skipped: `DHW_HPWH` (`feasibility`, a `blocked` flag), `ROOF_COOL` (`no_savings` once the attic is insulated), `CTRL_TSTAT` (`already_done`). `HVAC_RTU` is not applicable (office-only). One question, on the electrical service size. No CoStar market data, so `value_uplift` is null. The tenant variant selects only `LGT_LED` and skips the owner-only measures with reason `role`. Document: `retrofit_contract_residential`, California.

**Office** (`role: landlord`, budget $3,500). `LAYOUT` first (zero cost, with a `LayoutResult` of eight scored desk positions, four recommended), then `LGT_LED` and `PLUG_MGMT`. `HVAC_RTU` does not fit and is financeable with a C-PACE `FinancingScenario`. Vexcel reports no rooftop AC unit on this building, so the unit replacement rests on interior evidence only and carries the flag `hvac.unit_location` with status `unknown`; `HVAC_ECON` is blocked for the same reason. `LGT_CTRL` is `already_done`, `WIN_FILM` has `no_savings` after the desk layout. The bundle exercises the v0.2 fields: `window`, `doorway` and `opening` openings on wall edges, the georeference, CoStar occupancy with three tenancies (one ended), market data, and a `ValueUplift` on the plan. `Systems.occupants` comes from the suite's tenant. Document: `cpace_package`, Texas.

Both examples have assumptions from all six sources, a not-applicable measure with its reason, and every `RunEvent` type. Each folder shows all five skip reasons across its two plans.

## 5. Re-run the validation

The script below takes the contract block from the current `specs/SPEC.md`, validates every JSON file in this folder against its type, and checks consistency:

- no file carries a field the contract does not have, and no value is changed by validation;
- every `Ranged` has low <= expected <= high; every `schema_version` equals the contract's;
- wall graph: vertex, edge, floor and opening ids resolve, every room boundary is a closed loop, openings fit their edge;
- every `room_id`, `zone_id`, `plane_id`, `pano_id`, `parent_surface_id`, evidence panorama and roof obstruction that is referenced exists;
- CoStar join ids match the summary; the georeference matches the summary coordinates; `north_offset_deg` matches the quaternion;
- baseline: twelve monthly values that sum to the annual figure; end uses sum to electricity plus gas;
- measures: payback, net upfront cost, C-PACE term and amount, solar panel totals, recommended desk count;
- plans: each pick fits the remaining budget, cumulative cost never exceeds the budget, zero-cost measures come first, the "may exceed budget" warning matches the cost range, totals equal the sum of the items, `baseline_after` equals the baseline minus the selected savings, every `measure_id` is in `measures.json`, the value uplift matches the cap rate;
- `run_result.json` embeds the other files unchanged; questions point at existing assumptions; events cover every type; the question event carries a valid `Question`;
- documents: run id, measures, state, and the list of unfilled placeholders match the text.

Run it from the repository root. It needs Python 3.9 or later and `pydantic>=2`, reads only, and writes nothing.

```sh
python3 -m venv /tmp/contract-venv && /tmp/contract-venv/bin/pip install -q "pydantic>=2"
awk '/^````python$/{f=1;next} /^````$/{f=0} f' specs/examples/README.md > /tmp/validate_examples.py
/tmp/contract-venv/bin/python /tmp/validate_examples.py .
```

The last line of a passing run is `PASSED: <n> checks, 0 failures`; the exit status is 0. After any change to the contract block or to a file here, run it again.

````python
#!/usr/bin/env python3
"""Validate specs/examples/ against the contract block in specs/SPEC.md.

Usage:  python validate_examples.py [REPO_ROOT] [--examples DIR]

Needs Python 3.9+ and pydantic>=2. Reads only; writes nothing. The contract is taken
from specs/SPEC.md section 9 (between the contract:start and contract:end markers) at
run time, so the examples are always checked against the current contract.
Exit status 0 = every file validates and every consistency check passes.
"""
import json
import math
import pathlib
import re
import sys
import types

from pydantic import TypeAdapter

args = [a for a in sys.argv[1:] if not a.startswith("--")]
ROOT = pathlib.Path(args[0] if args else ".").resolve()
EX = ROOT / "specs" / "examples"
if "--examples" in sys.argv:
    EX = pathlib.Path(sys.argv[sys.argv.index("--examples") + 1]).resolve()
    args = [a for a in args if pathlib.Path(a).resolve() != EX]
    ROOT = pathlib.Path(args[0] if args else ".").resolve()

# ---------------------------------------------------------------- contract
spec_text = (ROOT / "specs" / "SPEC.md").read_text(encoding="utf-8")
block = re.search(r"<!-- contract:start -->\s*```python\n(.*?)\n```\s*<!-- contract:end -->",
                  spec_text, re.S)
if not block:
    sys.exit("contract block not found in specs/SPEC.md")
C = types.ModuleType("contract_schema")
sys.modules["contract_schema"] = C
exec(compile(block.group(1), "SPEC.md#contract", "exec"), C.__dict__)

PER_PROPERTY = {
    "property_summary.json": C.PropertySummary,
    "property_bundle.json": C.PropertyBundle,
    "building_model.json": C.BuildingModel,
    "baseline_result.json": C.BaselineResult,
    "measures.json": list[C.MeasureResult],
    "plan.json": C.Plan,
    "run_request.json": C.RunRequest,
    "run_result.json": C.RunResult,
    "run_events.json": list[C.RunEvent],
    "document_request.json": C.DocumentRequest,
    "document_draft.json": C.DocumentDraft,
}
OPTIONAL = {"plan_tenant.json": C.Plan, "run_request_tenant.json": C.RunRequest}
TOP = {"search_results.json": list[C.PropertySummary]}
FOLDERS = ("house", "office")

errors, checks = [], 0


def check(cond, where, msg):
    global checks
    checks += 1
    if not cond:
        errors.append(f"{where}: {msg}")
    return cond


def close(a, b, tol=0.011):
    return abs(a - b) <= tol


def type_name(tp):
    return getattr(tp, "__name__", None) if not getattr(tp, "__args__", None) else \
        f"list[{tp.__args__[0].__name__}]"


def lost(raw, dumped, path=""):
    """Paths present in the JSON file that the contract type dropped or changed."""
    if isinstance(raw, dict) and isinstance(dumped, dict):
        out = []
        for k, v in raw.items():
            out += [f"{path}/{k} (unknown field)"] if k not in dumped else \
                lost(v, dumped[k], f"{path}/{k}")
        return out
    if isinstance(raw, list) and isinstance(dumped, list) and len(raw) == len(dumped):
        return [x for i, (a, b) in enumerate(zip(raw, dumped)) for x in lost(a, b, f"{path}/{i}")]
    if isinstance(raw, bool) or isinstance(dumped, bool) or raw is None or dumped is None:
        return [] if raw is dumped else [f"{path} (value changed: {raw!r} -> {dumped!r})"]
    if isinstance(raw, (int, float)) and isinstance(dumped, (int, float)):
        return [] if math.isclose(raw, dumped) else [f"{path} (value changed)"]
    return [] if raw == dumped else [f"{path} (value changed: {raw!r} -> {dumped!r})"]


def walk(node, path=""):
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}/{i}")


def load(rel, tp):
    """Validate one file against its type; return the raw JSON (or None)."""
    path = EX / rel
    if not check(path.is_file(), rel, "file is missing"):
        return None
    text = path.read_text(encoding="utf-8")
    raw = json.loads(text)
    adapter = TypeAdapter(tp)
    try:
        obj = adapter.validate_json(text)
    except Exception as exc:                                  # pydantic.ValidationError
        check(False, rel, f"does not validate as {type_name(tp)}: {exc}")
        return None
    dropped = lost(raw, adapter.dump_python(obj, mode="json"))
    check(not dropped, rel, f"fields the contract does not carry: {dropped[:5]}")
    n = 0
    for p, node in walk(raw):
        if isinstance(node, dict) and {"low", "expected", "high"} <= node.keys():
            n += 1
            check(node["low"] <= node["expected"] <= node["high"], rel,
                  f"{p}: Ranged is not low <= expected <= high: {node}")
        if isinstance(node, dict) and "schema_version" in node:
            check(node["schema_version"] == C.SCHEMA_VERSION, rel, f"{p}: schema_version")
    print(f"ok    {rel:38s} {type_name(tp):22s} {n:4d} Ranged")
    return raw


def rsum(items, get, key):
    return sum(get(i)[key] for i in items)


def check_finance(w, m):
    f, s = m["finance"], m["savings"]
    rebate = sum(i["amount_usd"]["expected"] for i in f["incentives"]
                 if i["kind"] == "upfront_rebate" and i["status"] == "verified")
    check(close(f["net_upfront_usd"]["expected"], f["installed_cost_usd"]["expected"] - rebate),
          w, "net upfront != installed cost minus verified point-of-sale rebates")
    check(f["annual_savings_usd"] == s["cost_usd"], w, "finance savings != savings.cost_usd")
    pb = f["simple_payback_years"]
    if pb is not None and f["annual_savings_usd"]["expected"] > 0:
        check(close(pb["expected"],
                    f["net_upfront_usd"]["expected"] / f["annual_savings_usd"]["expected"]),
              w, "simple payback != net upfront / annual savings")
    kinds = [sc["kind"] for sc in f["financing"]]
    check("cash" in kinds, w, "no cash financing scenario")
    for sc in f["financing"]:
        if sc["kind"] == "cpace" and sc["eligible"]:
            check(sc["term_years"] <= f["useful_life_years"], w, "C-PACE term > useful life")
            check(close(sc["financed_usd"], f["net_upfront_usd"]["expected"]), w,
                  "C-PACE financed amount != net upfront")


def check_plan(w, plan, request, baseline, measure_ids, applicable_ids, market):
    budget = plan["budget_usd"]
    check(budget == request["budget_usd"], w, "plan budget != request budget")
    cum, seen_cost = 0.0, False
    for n, item in enumerate(plan["selected"], 1):
        m = item["measure"]
        net, sav = m["finance"]["net_upfront_usd"], m["finance"]["annual_savings_usd"]
        left = budget - cum
        iw = f"{w} rank {n} {m['measure_id']}"
        check(item["rank"] == n, iw, "ranks are not 1..n in order")
        check(net["expected"] <= left + 0.005, iw, "does not fit the remaining budget")
        check(sav["expected"] > 0, iw, "no positive savings")
        check((net["high"] > left + 0.005) == ("may exceed budget" in m["warnings"]), iw,
              "'may exceed budget' warning does not match net_upfront_usd.high")
        check(not (seen_cost and net["expected"] == 0), iw, "zero-cost measure not first")
        seen_cost = seen_cost or net["expected"] > 0
        cum += net["expected"]
        check(close(item["cumulative_upfront_usd"], cum), iw, "cumulative cost is wrong")
        check(item["cumulative_upfront_usd"] <= budget + 0.005, iw, "cumulative cost > budget")
        check(close(item["remaining_budget_usd"], budget - cum), iw, "remaining budget is wrong")
        check_finance(iw, m)
    sel = [i["measure"] for i in plan["selected"]]
    for key, get in (("total_upfront_usd", lambda m: m["finance"]["net_upfront_usd"]),
                     ("total_annual_savings_usd", lambda m: m["finance"]["annual_savings_usd"]),
                     ("total_co2_kg", lambda m: m["savings"]["co2_kg"])):
        for k in ("low", "expected", "high"):
            check(close(plan[key][k], rsum(sel, get, k), 0.02), w, f"{key}.{k} != sum of items")
    for key in ("electricity_kwh", "gas_kwh", "cost_usd", "co2_kg"):
        want = baseline["annual"][key]["expected"] - rsum(sel, lambda m: m["savings"][key],
                                                          "expected")
        check(close(plan["baseline_after"][key]["expected"], want, 0.02), w,
              f"baseline_after.{key} != baseline minus selected savings")
    for m in plan["financeable"]:
        fw = f"{w} financeable {m['measure_id']}"
        check(m["finance"]["net_upfront_usd"]["expected"] > budget - cum, fw, "would fit budget")
        check(m["finance"]["annual_savings_usd"]["expected"] > 0, fw, "no positive savings")
        check_finance(fw, m)
    ids_sel = [m["measure_id"] for m in sel]
    ids_fin = [m["measure_id"] for m in plan["financeable"]]
    ids_skip = [s["measure_id"] for s in plan["skipped"]]
    for mid in ids_sel + ids_fin + ids_skip:
        check(mid in measure_ids, w, f"{mid} is not in measures.json")
    check(len(set(ids_sel)) == len(ids_sel) and not set(ids_sel) & set(ids_fin + ids_skip), w,
          "a selected measure is also financeable or skipped, or is selected twice")
    check(applicable_ids <= set(ids_sel + ids_fin + ids_skip), w,
          f"applicable measures missing from the plan: {applicable_ids - set(ids_sel + ids_fin + ids_skip)}")
    vu = plan["value_uplift"]
    check((vu is None) == (market is None), w, "value_uplift present iff CoStar market data")
    if vu and market:
        s, cap = plan["total_annual_savings_usd"], vu["cap_rate"]
        check(cap == market["cap_rate"] and vu["comp_count"] == market["comp_count"], w,
              "value_uplift cap rate or comp count != CostarData.market")
        for k, kc in (("low", "high"), ("expected", "expected"), ("high", "low")):
            check(close(vu["value_usd"][k], s[k] / cap[kc], 0.02), w,
                  f"value_uplift.value_usd.{k} != annual savings / cap rate")
    return set(ids_sel), set(ids_fin), {s["reason"] for s in plan["skipped"]}


def check_property(folder):
    d = {name: load(f"{folder}/{name}", tp) for name, tp in PER_PROPERTY.items()}
    for name, tp in OPTIONAL.items():
        d[name] = load(f"{folder}/{name}", tp) if (EX / folder / name).is_file() else None
    extra = {p.name for p in (EX / folder).glob("*.json")} - set(PER_PROPERTY) - set(OPTIONAL)
    check(not extra, folder, f"JSON files with no contract type assigned: {sorted(extra)}")
    if any(d[name] is None for name in PER_PROPERTY):
        return None
    summary, bundle, model = d["property_summary.json"], d["property_bundle.json"], \
        d["building_model.json"]
    baseline, measures, result = d["baseline_result.json"], d["measures.json"], \
        d["run_result.json"]
    sid, mp, w = summary["sid"], bundle["matterport"], f"{folder}/property_bundle.json"

    # ---- bundle: wall graph, rooms, panoramas, join keys
    check(bundle["summary"] == summary, w, "summary differs from property_summary.json")
    edge_ids, floor_ids = set(), set()
    for fl in mp["floors"]:
        floor_ids.add(fl["id"])
        vert = {v["id"]: (v["x"], v["y"]) for v in fl["vertices"]}
        check(len(vert) == len(fl["vertices"]), w, "duplicate vertex id")
        for e in fl["edges"]:
            check(e["id"] not in edge_ids, w, f"duplicate edge id {e['id']}")
            edge_ids.add(e["id"])
            ok = check(all(v in vert for v in e["vertex_ids"]), w, f"edge {e['id']}: vertex id")
            length = math.dist(*(vert[v] for v in e["vertex_ids"])) if ok else 0.0
            op_ids = [o["id"] for o in e["openings"]]
            check(len(set(op_ids)) == len(op_ids), w, f"edge {e['id']}: duplicate opening id")
            check(sum(o["width_m"] or 0 for o in e["openings"]) <= length + 1e-6, w,
                  f"edge {e['id']}: openings wider than the edge")
    edges = {e["id"]: e for fl in mp["floors"] for e in fl["edges"]}
    for r in mp["rooms"]:
        check(r["floor_id"] in floor_ids, w, f"room {r['id']}: floor_id")
        if check(all(e in edges for e in r["boundary_edge_ids"]), w, f"room {r['id']}: edge id"):
            degree = {}
            for e in r["boundary_edge_ids"]:
                for v in edges[e]["vertex_ids"]:
                    degree[v] = degree.get(v, 0) + 1
            check(degree and all(n == 2 for n in degree.values()), w,
                  f"room {r['id']}: boundary edges do not form a closed loop")
    room_ids, pano_ids = {r["id"] for r in mp["rooms"]}, {p["id"] for p in mp["panos"]}
    check(len(room_ids) == len(mp["rooms"]) and len(pano_ids) == len(mp["panos"]), w,
          "duplicate room or pano id")
    geo, cs = mp["georeference"], bundle["costar"]
    if geo:
        check(close(geo["latitude"], summary["lat"], 1e-4)
              and close(geo["longitude"], summary["lon"], 1e-4), w,
              "georeference and summary coordinates differ")
        q = geo["rotation"]
        check(close(sum(q[k] ** 2 for k in "xyzw"), 1.0, 1e-5), w, "quaternion is not unit")
    if cs:
        check(cs["matterport_model_id"] == sid, w, "costar.matterport_model_id != sid")
        check((cs["property_id"], cs["listing_id"], cs["residential_listing_id"])
              == (summary["costar_property_id"], summary["costar_listing_id"],
                  summary["costar_residential_listing_id"]), w, "CoStar ids != summary ids")
    for p, node in walk(bundle):
        if isinstance(node, str) and node.startswith("data/"):
            check(node.startswith(f"data/cache/{sid}/"), w, f"{p}: asset path outside the cache")

    # ---- building model
    w = f"{folder}/building_model.json"
    check(model["sid"] == sid, w, "sid")
    zones = {z["id"]: z for z in model["zones"]}
    for z in model["zones"]:
        check(set(z["room_ids"]) <= room_ids, w, f"zone {z['id']}: unknown room_id")
        area = sum(r["area_m2"] or 0 for r in mp["rooms"] if r["id"] in z["room_ids"])
        check(close(z["floor_area_m2"], area), w, f"zone {z['id']}: area != sum of its rooms")
    surf = {s["id"]: s for s in model["surfaces"]}
    check(len(surf) == len(model["surfaces"]), w, "duplicate surface id")
    for s in model["surfaces"]:
        check(s["zone_id"] in zones, w, f"surface {s['id']}: unknown zone_id")
        parent = s["parent_surface_id"]
        check(parent is None or (parent in surf and surf[parent]["kind"] == "wall"), w,
              f"surface {s['id']}: parent_surface_id is not a wall surface")
        check((s["shgc"] is not None) == (s["kind"] == "window"), w, f"{s['id']}: shgc")
    plane_ids = {p["id"] for p in model["roof_planes"]}
    detections = bundle["vexcel"]["detections"] if bundle["vexcel"] else []
    for pl in model["roof_planes"]:
        check(all(o in detections for o in pl["obstructions"]), w,
              f"roof plane {pl['id']}: obstruction is not one of the bundle's detections")
        check(pl["usable_area_m2"] <= pl["area_m2"], w, f"roof plane {pl['id']}: usable > area")
    keys = [a["key"] for a in model["assumptions"]]
    check(len(set(keys)) == len(keys), w, "duplicate assumption key")
    sources = {a["source"] for a in model["assumptions"]}
    check(sources == set(C.Source.__args__), w, f"assumption sources present: {sorted(sources)}")
    if geo and model["north_source"] == "georeference":
        angle = 2 * math.degrees(math.atan2(geo["rotation"]["z"], geo["rotation"]["w"]))
        check(close(model["north_offset_deg"]["expected"], angle, 0.01), w,
              "north_offset_deg != rotation about z of the georeference quaternion")

    # ---- baseline
    w = f"{folder}/baseline_result.json"
    a = baseline["annual"]
    for key, total in (("monthly_electricity_kwh", a["electricity_kwh"]["expected"]),
                       ("monthly_gas_kwh", a["gas_kwh"]["expected"])):
        check(len(baseline[key]) == 12 and close(sum(baseline[key]), total, 0.5), w,
              f"{key}: not 12 values summing to the annual figure")
    check(close(sum(baseline["end_use_kwh"].values()),
                a["electricity_kwh"]["expected"] + a["gas_kwh"]["expected"], 0.5), w,
          "end uses do not sum to electricity + gas")

    # ---- measures
    w = f"{folder}/measures.json"
    mids = [m["measure_id"] for m in measures]
    check(len(set(mids)) == len(mids), w, "duplicate measure_id")
    check(any(not m["applicable"] for m in measures), w, "no not-applicable measure")
    for m in measures:
        mw = f"{w} {m['measure_id']}"
        if m["applicable"]:
            if check(m["savings"] and m["finance"], mw, "applicable but no savings or finance"):
                check_finance(mw, m)
            check(m["formula_ids"], mw, "no formula_ids")
        else:
            check(m["not_applicable_reason"], mw, "not applicable but no reason")
        if m["solar"]:
            so = m["solar"]
            check(all(p["plane_id"] in plane_ids for p in so["panels"]), mw, "unknown plane_id")
            check(so["panel_count"] == len(so["panels"]), mw, "panel_count != len(panels)")
            check(close(so["annual_kwh"]["expected"], sum(p["annual_kwh"] for p in so["panels"]),
                        0.5), mw, "annual_kwh != sum of panels")
        if m["layout"]:
            la = m["layout"]
            check(all(c["room_id"] in room_ids for c in la["candidates"]), mw, "desk room_id")
            check(sum(c["recommended"] for c in la["candidates"]) == la["desks_requested"], mw,
                  "recommended desks != desks_requested")
        check((m["measure_id"] != "PV_ROOF" or not m["applicable"]) or m["solar"], mw, "no solar")
        check((m["measure_id"] != "LAYOUT" or not m["applicable"]) or m["layout"], mw, "no layout")

    # ---- references that can sit anywhere: anchors, evidence, flags
    statuses = set()
    for name, raw in d.items():
        for p, node in walk(raw):
            if not isinstance(node, dict):
                continue
            fw = f"{folder}/{name}{p}"
            if node.get("kind") == "pano" and "ref" in node:
                check(node["ref"] in pano_ids, fw, f"evidence pano {node['ref']} does not exist")
            if "label" in node and "pano_id" in node and "room_id" in node:        # Anchor
                check(node["pano_id"] in pano_ids | {None}, fw, "anchor pano_id")
                check(node["room_id"] in room_ids | {None}, fw, "anchor room_id")
            if "status" in node and "message" in node and "key" in node:           # Flag
                statuses.add(node["status"])
    check("unknown" in statuses, folder, "no Flag with status 'unknown'")

    # ---- plans
    applicable = {m["measure_id"] for m in measures if m["applicable"]}
    market = cs["market"] if cs else None
    sel, fin, reasons = check_plan(f"{folder}/plan.json", d["plan.json"], d["run_request.json"],
                                   baseline, set(mids), applicable, market)
    if d["plan_tenant.json"] and d["run_request_tenant.json"]:
        check(d["run_request_tenant.json"]["role"] == "tenant", folder, "tenant request role")
        reasons |= check_plan(f"{folder}/plan_tenant.json", d["plan_tenant.json"],
                              d["run_request_tenant.json"], baseline, set(mids), applicable,
                              market)[2]
    all_reasons = set(C.SkippedItem.model_fields["reason"].annotation.__args__)
    check(reasons == all_reasons, folder, f"skip reasons not shown: {all_reasons - reasons}")

    # ---- run result and events
    w = f"{folder}/run_result.json"
    for key, name in (("request", "run_request.json"), ("property", "property_summary.json"),
                      ("building_model", "building_model.json"),
                      ("baseline", "baseline_result.json"), ("measures", "measures.json"),
                      ("plan", "plan.json")):
        check(result[key] == d[name], w, f"{key} differs from {name}")
    check(d["run_request.json"]["sid"] == sid, w, "request sid")
    for q in result["questions"]:
        check(q["assumption_key"] in keys, w, f"question {q['id']}: unknown assumption_key")
        check(any(c["value"] is None for c in q["choices"]), w, "no \"I don't know\" choice")
    w = f"{folder}/run_events.json"
    events = d["run_events.json"]
    all_types = set(C.RunEvent.model_fields["type"].annotation.__args__)
    check({e["type"] for e in events} == all_types, w,
          f"event types not shown: {all_types - {e['type'] for e in events}}")
    check(events[-1]["type"] == "done", w, "last event is not 'done'")
    stages = {f"S{i}" for i in range(1, 10)} | {None}
    check(all(e["stage"] in stages for e in events), w, "stage is not S1..S9 or null")
    for e in events:
        if e["type"] == "question":
            try:
                C.Question.model_validate(e["payload"]["question"])
                check(e["payload"]["question"] in result["questions"], w,
                      "question event differs from RunResult.questions")
            except Exception as exc:
                check(False, w, f"question payload is not a Question: {exc}")

    # ---- documents
    w = f"{folder}/document_draft.json"
    req, draft = d["document_request.json"], d["document_draft.json"]
    check(req["run_id"] == result["run_id"], w, "document_request.run_id != run_result.run_id")
    check(set(req["measure_ids"]) <= sel | fin, w, "document covers a measure outside the plan")
    check((draft["doc_type"], draft["state"]) == (req["doc_type"], req["state"]), w,
          "doc_type or state differs from the request")
    check(req["state"] == summary["state"], w, "document state != property state")
    blanks = set(re.findall(r"\{\{([a-z_]+)\}\}", draft["markdown"]))
    check(blanks == set(draft["unfilled_placeholders"]), w,
          "unfilled_placeholders != {{placeholders}} left in the markdown")
    check(draft["statutory_checks"] and draft["disclaimer"], w, "no checks or no disclaimer")
    return summary


goldens = [check_property(f) for f in FOLDERS]
search = load("search_results.json", TOP["search_results.json"])
if search is not None:
    w = "search_results.json"
    sids = [s["sid"] for s in search]
    check(len(set(sids)) == len(sids), w, "duplicate sid")
    for g in goldens:
        check(g is None or g in search, w, "a golden property_summary.json is not in the list")
    for field, want in (("segment", {"residential", "commercial"}), ("state", {"CA", "TX"}),
                        ("city", {"Los Angeles", "Houston"})):
        check({s[field] for s in search} == want, w, f"{field} values are not {sorted(want)}")
    check({"office", "single_family"} <= {s["use_type"] for s in search}, w, "use types")
extra = {p.name for p in EX.glob("*.json")} - set(TOP)
check(not extra, "specs/examples", f"JSON files with no contract type assigned: {sorted(extra)}")

print(f"\ncontract {C.SCHEMA_VERSION} from {ROOT / 'specs' / 'SPEC.md'}")
print(f"examples {EX}")
if errors:
    print(f"\nFAILED: {len(errors)} of {checks} checks")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print(f"\nPASSED: {checks} checks, 0 failures")
````

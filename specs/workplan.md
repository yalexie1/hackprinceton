# Workplan: who builds what, and how parallel work stays apart

Status: draft v0.2, 2026-11-14. Owner: @yalexie1. Change by agreement on the board.

v0.2 brings this file in line with `specs/SPEC.md` v0.2 (contract 0.2.0) and with the Data lane's own work packages in `specs/data-integration.md` section 6. That section is the authority for the Data lane; section 4.1 of this file restates it.

Event: HackPrinceton, November 13 to 15, 2026. The submission deadline is not confirmed. Every time in this file is written as `T-N h`: N hours before the deadline `T`.

## 1. How to use this file

Find your lane in 1.1, read the rules in section 2 once, then take one work package from section 4 and build only that. Your coding agent gets the kickoff prompt in 5.4 with one package ID filled in; the package row tells it which folder it may write, what goes in, what comes out, and the test that proves it is done. Product behaviour is defined in `specs/SPEC.md`; this file only divides the work and never adds a feature.

Naming used below:

- "SPEC 6.1" means section 6.1 of `specs/SPEC.md`.
- "Physics spec" means `specs/physics.md`, the index, and the four files it indexes: `specs/physics/01-solar-pv.md`, `02-thermal-systems.md`, `03-daylight-comfort.md` and `04-economics-emissions-mv.md`. "Physics 02" means the second of them.
- "Legal spec" means three files. `specs/legal.md` is the document framework: the document templates, the clause library and the placeholder table; @Sri-SriPod owns it. `specs/legal/california.md` and `specs/legal/texas.md` are the statutory requirements it cites; @yalexie1 owns them. Where SPEC says `physics.md` or `legal.md`, it means the files named in these two lines (open item O13).
- "Data spec" means `specs/data-integration.md`, which the Data lane owns. "Data spec 6.1" is its section 6.1.
- A dagger (†) after a tier means SPEC 13 does not state a tier for that item and this file inferred one (open item O5).

### 1.1 Lanes

One writer per path. Paths marked *proposed* are proposals to confirm on the board. Paths already agreed on the board but not yet written into the owner table of `AGENTS.md` are listed in open item O19.

| Lane | Series | Owner | Folders | Reference spec |
|---|---|---|---|---|
| Data | `D` | @vigjay | `backend/data_layer/`, `data/fixtures/`, `data/cache/`, `specs/data-integration.md`, and *proposed* `.claude/agents/data-*.md`, `.claude/commands/data-*.md` | data spec |
| Analysis | `A` | @yalexie1 | `backend/analysis/` (split into `physics/`, `vision/`, `solar/`, `measures/`, `finance/`, and *proposed* `model/`, `layout/`), `backend/config.py` | physics spec |
| Agent and server | `G` | @Sri-SriPod | `backend/agent/`, `backend/server.py`, `data/runs/` | SPEC 8 and 10 |
| Legal drafting | `L` | @Sri-SriPod | `backend/legal/`, `specs/legal.md` | legal spec |
| Frontend, demo, submission | `F` | @vinayak-sinha | `frontend/` | SPEC 11 and 15 |
| Contract and specs | `C` | @yalexie1 | `backend/schema.py`, `specs/` except the Data lane's spec file and the legal framework file (so including `specs/legal/` and `specs/examples/`), root files (2.5) | `specs/SPEC.md` |

`AGENTS.md` does not name the team lead. Wherever this file says "the lead", it means the person the team names on the board (open item O16).

Three paths are agreed on the board and not yet in `AGENTS.md` (open item O19): the data spec is @vigjay's (recorded at the top of that file); `backend/legal/` and `specs/legal.md` are @Sri-SriPod's (accepted and handed over on 2026-11-14; SPEC's companion table records the second). The owner table in `AGENTS.md` still lists all of `specs/` under @yalexie1, has no row for `backend/legal/`, and says nothing about `.claude/`.

## 2. Rules that keep parallel work from colliding

Each rule is written so an agent can follow it literally.

### 2.1 Contract first

**Rule.** The only types that cross a lane boundary are the ones in SPEC 9, which become `backend/schema.py`. Nobody but the contract owner edits `backend/schema.py` or SPEC 9 and 10. Before the freeze (checkpoint 1) the contract can change in any way by agreement. After the freeze, changes are additive only: a new optional field with a default, a new type, or a new literal value. Code that reads contract data must ignore fields and literal values it does not know.

**Example.** Your measure needs to report a refrigerant type. Do not add a field to `MeasureResult`. Put it in `MeasureResult.params` (a free `dict`) now, and request a contract change if another lane must read it.

**What counts as a contract change.** Any edit to one of these:

| Item | Where it lives |
|---|---|
| A type, field, default or literal value (`MeasureId`, `DocType`, `RunEvent.type`, ...) | SPEC 9, `backend/schema.py` |
| An endpoint path, method, body or return value | SPEC 10 |
| A door function name or signature, or an agent tool name | section 3 of this file |
| An environment variable name, or a constant name in `backend/config.py` | SPEC 12 |
| A fixture file name or the shape of a fixture | `specs/examples/` (2.3) |
| A shared key vocabulary once published: assumption keys, flag keys, end-use keys, schedule keys, placeholder names, opening type values | physics spec, legal spec, data spec |

Not a contract change: anything inside your own subfolder, private helper functions, prompts, tests, your lane's dependencies file.

**Steps to request a contract change.**

1. Keep working. Carry the value in an existing free field (`params`, `payload`, `attributes`, `raw`, `fields`) or keep it private to your subfolder. Never edit `backend/schema.py` yourself.
2. Post `CONTRACT-CHANGE:` on the board (format in 6.1) with: the exact diff, whether it is additive, the lanes it affects, and why.
3. Each affected owner replies `ACK` or objects. This is the one case where an acknowledgement reply is required.
4. Additive change: the contract owner may merge after every affected owner has acknowledged, or after 30 minutes with no objection. Breaking change: allowed only before the freeze and only with an `ACK` from all four owners.
5. The contract owner (or their agent) edits SPEC 9 and `backend/schema.py`, bumps `SCHEMA_VERSION` (third digit for additive, second digit for breaking), updates the affected fixtures, runs the examples validator (2.3), merges, and posts `CONTRACT-CHANGE: landed <version>`.
6. You rebase on `main` and switch to the new field.

### 2.2 One public door per lane

**Rule.** A lane exposes exactly one module to other lanes: `backend/data_layer/api.py`, `backend/analysis/api.py`, `backend/legal/api.py`. The server's door is its REST routes (SPEC 10). The frontend has no door; it only calls the server. A door function takes and returns contract types and plain values, never a lane-private class.

**Import rule.** A Python file may import only:

1. the standard library and third-party packages listed in its lane's dependencies file,
2. `backend/schema.py`,
3. `backend/config.py` (constants only; it is treated as part of the contract, see O7),
4. files in its own subfolder,
5. and, only inside `backend/agent/`, `backend/server.py` and the three `api.py` files: another lane's `api.py`.

Nothing imports from another lane's internals, and no subfolder imports from a sibling subfolder (2.6).

**Example.** The agent's `run_baseline` tool does `from backend.analysis import api` and calls `api.run_baseline(...)`. It does not do `from backend.analysis.physics.zone import loads`.

### 2.3 Fixtures before integration

**Rule.** Every package is built and tested against the example payloads in `specs/examples/`, not against another lane's running code. Each lane's door starts life as a stub that returns those fixtures (packages `D5`, `A0`, `G0`, `L0`), so every consumer can call it from the first hour. Real code later replaces the stub behind the same signature. A test in your package may read fixtures and call your own code; it may not need another lane to be running or a network connection, unless it is marked `live`.

**Example.** The Plan screen is built from `house/run_result.json` with the server off. The plan algorithm is tested with a fake "evaluate" function that returns measures from the same file.

Fixture files. They are in the repository under `specs/examples/` (package `C2`): `README.md`, `search_results.json`, and the folders `house/` and `office/`, which hold the same thirteen files each. The alias is how the tables in section 4 refer to them; `alias#/field` means one field of that file, and `.house` or `.office` picks one of the pair.

| Alias | File in `specs/examples/` | Content |
|---|---|---|
| `bundle` | `house/property_bundle.json`, `office/property_bundle.json` | `PropertyBundle`. Both have a `georeference`. The office has eight openings of type `window`, and `costar.occupancy` and `costar.market`. The house has doorways only, on purpose, to show the vision fallback for windows |
| `model` | `house/building_model.json`, `office/building_model.json` | `BuildingModel` with `north_source` and `systems.occupants` |
| `run` | `house/run_result.json`, `office/run_result.json` | `RunResult` with `request`, `property`, `building_model`, `baseline`, `measures`, `plan`, `questions`, `narrative_md` filled; the office plan has a `value_uplift`, the house plan has none |
| `docreq` | `house/document_request.json`, `office/document_request.json` | `DocumentRequest` |
| `draft` | `house/document_draft.json`, `office/document_draft.json` | `DocumentDraft` |
| `search` | `search_results.json` | `PropertySummary[]`, the search response |
| `events` | `house/run_events.json`, `office/run_events.json` | one JSON array of `RunEvent` for a full run, with every event type at least once |
| `ask` | not written yet. Proposed: `ask/building_model_wide.json`, `ask/building_model_narrow.json` | two `BuildingModel` files, one built so the ask rule fires and one so it stays silent (SPEC 14). Work of `A27`, the first package that needs them |
| `weather` | not written yet. Proposed: `weather/typical_year_hourly.csv` | one typical year of hourly weather. Work of `A1`, the first package that needs it. It is the reference format until the Data lane writes one into data spec section 5 (O9) |

The two folders also hold each part of a run as its own file (`property_summary.json`, `baseline_result.json`, `measures.json`, `plan.json`, `run_request.json`), identical to the matching field of `run`, and a tenant variant (`plan_tenant.json`, `run_request_tenant.json`) that shows measures skipped for the role.

**The examples validator.** There is no validator file in the repository. The validator's text is in section 5 of `specs/examples/README.md`; the three commands given there extract it and run it from a scratch virtualenv, from the repository root. It reads only. Wherever this file says "the examples validator", it means that.

**What the examples contain.** They are hand-made. They carry a few real identifying facts about the two golden properties (the model ids, the CoStar ids, the georeference, a handful of Vexcel attribute values), all of which the data spec already publishes; README section 2 lists them. Every other value is invented and is illustrative. What must never be committed, here or anywhere else in the repository: sponsor records, kit files, API responses, imagery.

Two sets of fixtures exist, and they are different things:

- `specs/examples/` (the table above): shaped as contract types, illustrative. Every lane's tests read these.
- `data/fixtures/` (Data lane, data spec 6.4): payloads of the two golden properties in `costar/`, `matterport/` and `vexcel/`, each written by the Data package that owns that source, in the shape of its output type. Other lanes use them to run on real values without keys. What may be committed there is open item O8.

### 2.4 Fixtures and doors are announced, not discovered

**Rule.** When a fixture, a stub door or a real door lands on `main`, its author posts `FIXTURE-READY:` or `INTERFACE-LIVE:` (6.1). Consumers switch only after that post.

**Example.** The agent lane keeps using the stub `build_plan` until it reads `INTERFACE-LIVE: real analysis.api.build_plan`.

### 2.5 No shared files

**Rule.** No file is written by two lanes, and inside a lane no file is written by two agents at the same time.

- **Dependencies.** Each lane declares its own, in one file that only the lane owner (or the agent holding the lane's scaffold package: `D5`, `A0`, `G0`, `L0`, `F0`) edits. An agent that needs a new package says so in its PR description; it does not edit the file.

  | Lane | Dependencies file |
  |---|---|
  | Data | `backend/data_layer/requirements.txt` |
  | Analysis | `backend/analysis/requirements.txt` |
  | Agent and server | `backend/agent/requirements.txt` (also covers `backend/server.py`) |
  | Legal drafting | `backend/legal/requirements.txt` |
  | Frontend | `frontend/package.json` and its lock file |
  | Contract | root `requirements.txt`: `pydantic` plus one `-r` line per lane file |

  A lane does not pin a package at a version that conflicts with another lane's file. If two lanes need different versions, post `BLOCKED:` to both owners.
- **Root files.** `README.md`, `.gitignore`, `.env.example`, root `requirements.txt`, `backend/__init__.py` and `.github/CODEOWNERS` belong to the contract owner (@yalexie1). `AGENTS.md`, `CLAUDE.md`, `tools/`, `.claude/`, `.github/ISSUE_TEMPLATE/` and `docs/` are the board template: nobody edits them during the build, and the owner table in `AGENTS.md` changes only after board agreement. One exception: the Data lane keeps its sub-agent definitions and launch commands in `.claude/agents/data-*.md` and `.claude/commands/data-*.md` and owns those files (O19). `.env` is personal and never committed.
- **Tests.** Tests live inside the package's own subfolder (`<subfolder>/tests/`), so test files never collide. There is no shared `tests/` folder and no shared `conftest.py` above a subfolder. The Data lane has one file per package, not one folder; where its tests live is that lane's decision (4.1.2, R11).
- **Package markers.** Each subfolder owns its own `__init__.py`. `backend/<lane>/__init__.py` belongs to the lane's scaffold package.

**Example.** Your physics package needs `numpy`. You write "needs numpy" in the PR; the analysis owner adds the line to `backend/analysis/requirements.txt`.

### 2.6 Sub-lanes: one writer per subfolder, wiring only in the door

**Rule.** Every package is bound to one subfolder (two when the table says so). At any moment a subfolder has one writer: the agent holding the open package for it. Packages that share a subfolder run one after the other in ID order; the subfolder is free again when the earlier package's PR is merged. Packages in different subfolders can always run at the same time.

A subfolder never imports a sibling subfolder. If your code needs a sibling's result, your function takes it as an argument: either a contract-typed value, or a function whose arguments and return value are contract types and plain numbers or arrays. Only the lane's door (`api.py`, written by the lane's scaffold and wiring packages) imports the subfolders and connects them. In your tests you pass a fake.

**Example.** `measures/engine/` needs a simulation. It does not import `physics/`. Its function is `evaluate(bundle, model, measure_id, role, simulate)`, where `simulate(bundle, model) -> BaselineResult`. The test passes a fake `simulate`; `backend/analysis/api.py` passes the real one.

**Data lane.** The Data lane is organised as one file per package under `backend/data_layer/`, each with a fixture folder under `data/fixtures/` (data spec 6.1). There, "subfolder" in this rule reads as "the package's file and its fixture folder". How that lane's own files import one another (for example the source clients using `cache.py`) is decided inside the lane. The one-writer rule and the door rule apply unchanged.

### 2.7 Board protocol

**Rule.** Use the five post types in section 6 on top of the board rules in `AGENTS.md`. One post, one topic, the type word first after your name tag.

**Example.** `[Yale's Claude] INTERFACE-LIVE: stub backend/analysis/api.py, all 12 functions return fixtures.`

### 2.8 Git

**Rule.** Follow `AGENTS.md` section 3. In addition: one GitHub issue per package, titled `<ID> <title>`; one branch per issue, named `<issue#>-<slug>`; each agent works in its own git worktree, never in a checkout another agent is using; stage files by path, only inside the package's bound subfolder. `Closes #N` closes the issue only when the PR merges into `main`; for a PR into any other branch the author closes the issue by hand after the merge. `main` is the trunk: the `spec-draft` branch the spec was first written on was merged into `main` on 2026-11-14 and is retired.

**Example.** Package `A2`, issue 23: `git worktree add ../hp-23 -b 23-a2-zone-loads origin/main`, then work only in `backend/analysis/physics/zone/`.

## 3. Public interface of each lane

Tool names come from SPEC 8 and stage inputs and outputs from SPEC 6.1; the types are from SPEC 9. SPEC does not give argument lists, so the signatures below are this file's proposal and become binding at the schema freeze (O2). Changing one afterwards is a contract change.

Common behaviour of every door function: an unknown `sid` or `run_id` raises `LookupError`; a missing or locked data layer is never an exception, it is a `FetchRecord`; nothing is printed; results are deterministic for the same inputs.

### 3.1 `backend/data_layer/api.py` (owner @vigjay)

The Data lane defines its door in `.claude/agents/data-api.md` (package `D5`) as three functions. This file needs two more, shown last. They are requests until the Data lane agrees (4.1.2, R3).

```python
# Defined by the Data lane
def search_properties(q: str | None = None, segment: Segment | None = None,
                      use_type: UseType | None = None, lat: float | None = None,
                      lon: float | None = None, radius_m: float | None = None,
                      limit: int = 20) -> list[PropertySummary]: ...          # S1
    # runs on the CoStar kit's two starter lists; use_type "office" means CoStar property type 5

def get_property_bundle(sid: str) -> PropertyBundle: ...                      # S2, cached

def get_asset(path: str) -> bytes: ...
    # path as stored in a bundle (face_paths, ortho_path, ...). Returns the cached bytes,
    # fetching them again through a fresh signed link if they are missing. Never returns or
    # stores a URL. Refuses any path outside the cache directory.

# Requested by this file (R3)
def get_property_summary(sid: str) -> PropertySummary: ...                    # S1

def detect_roof_elements(sid: str, labels: list[str] | None = None) -> list[VexcelDetection]: ...
    # Vexcel elements/detect with SAM 3 (the code is the Data lane's D8). Also stored, so a
    # later get_property_bundle(sid) returns the same list in vexcel.detections.
```

This is the only lane that talks to Matterport, Vexcel, the CoStar kit, weather and tariff sources. `detect_roof_elements` is placed here, not in analysis, because it is a network call and SPEC 14 requires every analysis function to run with no network. Until R3 is settled, `GET /api/properties/{sid}` is answered from the `summary` of `get_property_bundle(sid)`, and the `detect_roof_elements` tool wraps a stub.

### 3.2 `backend/analysis/api.py` (owner @yalexie1)

All functions are pure: no network (the one exception is the vision model call inside `observe_interior`), no file writes outside the cache directory, same output for the same input. Image bytes are read with `data_layer.api.get_asset`, called from `api.py` only and handed to the subfolder that needs them.

```python
# S3 See
def observe_interior(bundle: PropertyBundle) -> tuple[list[Assumption], list[Flag]]: ...

# S4 Model
def build_building_model(bundle: PropertyBundle, observed: list[Assumption] = [],
                         flags: list[Flag] = [],
                         overrides: dict[str, float | str | bool] = {}) -> BuildingModel: ...
    # true north from bundle.matterport.georeference, cross-checked against the Vexcel
    # footprint (north_source says which was used); window and door surfaces from the
    # measured openings, from vision only where the wall graph has no window openings;
    # systems.occupants from bundle.costar.occupancy when the bundle has it
def set_assumption(model: BuildingModel, key: str, value: float | str | bool,
                   source: Source = "user") -> BuildingModel: ...
    # a float collapses the range to that value; returns a new model, the input is not changed

# S5 Baseline
def run_baseline(bundle: PropertyBundle, model: BuildingModel,
                 bills: UtilityBills | None = None) -> BaselineResult: ...

# S6 Measures
def evaluate_measure(bundle: PropertyBundle, model: BuildingModel, measure_id: MeasureId,
                     role: Role, desks_requested: int | None = None) -> MeasureResult: ...
    # savings filled, finance empty; model may already have earlier measures applied
def design_pv(bundle: PropertyBundle, model: BuildingModel, baseline: BaselineResult,
              budget_usd: float | None = None) -> SolarDesign: ...
def score_desk_positions(bundle: PropertyBundle, model: BuildingModel,
                         desks_requested: int | None = None) -> LayoutResult: ...

# S7 Plan
def price_measure(bundle: PropertyBundle, measure: MeasureResult) -> MeasureResult: ...
    # returns the same measure with finance filled
def lookup_incentives(measure_id: MeasureId, summary: PropertySummary) -> list[Incentive]: ...
def build_plan(bundle: PropertyBundle, model: BuildingModel, request: RunRequest) -> Plan: ...
    # SPEC 6.5; evaluates and prices measures itself after every pick. Fills value_uplift
    # when bundle.costar.market has comparables (SPEC 6.6), else leaves it empty
def cpace_scenario(bundle: PropertyBundle, measure: MeasureResult) -> FinancingScenario: ...
def sensitivity(bundle: PropertyBundle, model: BuildingModel,
                request: RunRequest) -> list[Question]: ...
    # SPEC 5.3 steps 1 to 3. Largest swing first. Empty list means: do not ask.
```

### 3.3 `backend/legal/api.py` (owner @Sri-SriPod)

```python
def list_templates(state: Literal["CA", "TX"] | None = None,
                   segment: Segment | None = None) -> list[DocType]: ...
    # cpace_package is listed only for segment "commercial"; whether a property is eligible
    # is decided by cpace_scenario (SPEC 6.6)
def fill_template(request: DocumentRequest, run: RunResult,
                  bundle: PropertyBundle | None = None) -> DocumentDraft: ...
    # never invents a party, licence number or legal description: leaves a visible blank
def check_document(draft: DocumentDraft) -> list[StatutoryCheck]: ...
```

### 3.4 Agent tools (`backend/agent/tools/`, owner @Sri-SriPod)

A tool takes only the small arguments shown. Large objects are read from and written to the run files of SPEC 8 rule 6 by the tool wrapper, so the model never copies a bundle through its context. A wrapper calls door functions and does no arithmetic.

| Tool | Agent | Arguments from the model | Door call | Result |
|---|---|---|---|---|
| `search_properties` | `scout` | `q`, `segment`, `use_type`, `lat`, `lon`, `radius_m`, `limit` | `data_layer.api.search_properties` | `PropertySummary[]` |
| `get_property_bundle` | `scout` | `sid` | `data_layer.api.get_property_bundle` | `PropertyBundle` to `/run/bundle.json`; returns `summary` and `provenance` |
| `get_asset` | `scout` | `path` | `data_layer.api.get_asset` | bytes; the wrapper saves them in the run's file system and returns that path |
| `observe_interior` | `surveyor` | none | `analysis.api.observe_interior` | `Assumption[]`, `Flag[]` |
| `detect_roof_elements` | `surveyor` | `labels` | `data_layer.api.detect_roof_elements` (requested, R3) | `VexcelDetection[]`, merged into `/run/bundle.json` |
| `build_building_model` | `surveyor` | none | `analysis.api.build_building_model` | `BuildingModel` to `/run/model.json` |
| `set_assumption` | `surveyor` | `key`, `value` | `analysis.api.set_assumption` | `BuildingModel` to `/run/model.json` |
| `run_baseline` | `physicist` | none | `analysis.api.run_baseline` | `BaselineResult` to `/run/baseline.json` |
| `evaluate_measure` | `physicist` | `measure_id` | `analysis.api.evaluate_measure` | `MeasureResult` to `/run/measures.json` |
| `design_pv` | `physicist` | `budget_usd` | `analysis.api.design_pv` | `SolarDesign` |
| `score_desk_positions` | `physicist` | `desks_requested` | `analysis.api.score_desk_positions` | `LayoutResult` |
| `price_measure` | `financier` | `measure_id` | `analysis.api.price_measure` | `MeasureResult` with `finance`, to `/run/measures.json` |
| `lookup_incentives` | `financier` | `measure_id` | `analysis.api.lookup_incentives` | `Incentive[]` |
| `build_plan` | `financier` | `budget_usd` | `analysis.api.build_plan` | `Plan` to `/run/plan.json` |
| `cpace_scenario` | `financier` | `measure_id` | `analysis.api.cpace_scenario` | `FinancingScenario` |
| `sensitivity` | `financier` | none | `analysis.api.sensitivity` | `Question[]` |
| `list_templates` | `counsel` | `state` | `legal.api.list_templates` | `DocType[]` |
| `fill_template` | `counsel` | `doc_type`, `state`, `measure_ids`, `fields` | `legal.api.fill_template` | `DocumentDraft`; runs only after user approval (SPEC 8 rule 4) |
| `check_document` | `counsel` | `doc_id` | `legal.api.check_document` | `StatutoryCheck[]` |
| `ask_user` | `auditor` | one `Question` | none; pauses the run | the chosen `Choice.value` |

The `auditor` also has the built-in `task`, file system and todo tools of `deepagents`. `check_narrative` is a step inside the agent lane, not a model tool: `check_narrative(narrative_md: str, result: RunResult) -> list[str]`, where an empty list means every number in the text matches a structured result.

### 3.5 Server

The server's interface is SPEC 10; it is not repeated here. `backend/server.py` is a thin translation from HTTP to the run door below, which is private to the agent and server lane and may change without a contract change:

```python
# backend/agent/api.py: imported only by backend/server.py
def start_run(request: RunRequest) -> str: ...                      # run_id
def stream_events(run_id: str) -> AsyncIterator[RunEvent]: ...
def get_run(run_id: str) -> RunResult: ...
def answer(run_id: str, question_id: str, value: float | str | bool | None) -> None: ...
def update_run(run_id: str, budget_usd: float | None = None,
               overrides: dict[str, float | str | bool] | None = None) -> None: ...
def draft_document(request: DocumentRequest) -> DocumentDraft: ...
def get_document(run_id: str, doc_id: str) -> DocumentDraft: ...
```

## 4. Work packages

How to read the tables:

- **Tier** is from SPEC 13. Work P0 first. Do not start a P1 package while a P0 package in your lane is unassigned.
- **Bound to** is the only place the package may write. Where two packages name the same path, the note "after X" gives the order (2.6). In the Data lane the bound path is one file and its fixture folder.
- **In** and **Out** name contract types. Plain values (numbers, strings, arrays, a function passed in) are written in words.
- **Fixture** uses the aliases of 2.3.
- **Acceptance test** runs inside the lane with no other lane running and no network. A line starting `live:` is an extra check that needs the keys in `.env`; it is run by hand, not in the default test run.
- **Depends on** lists what must exist before the package can start: contract types (so `C1`) and fixtures (so `C2`; for `ask` and `weather`, the package that 2.3 names). It never names another package's code. A package that needs another package's result takes it as an argument and fakes it in tests (2.6).
- Each package is sized for two to four hours of one person with one agent.

### 4.1 Data lane (`D`), @vigjay

**Authority.** The Data lane's packages are defined by its owner in the data spec, section 6: ids, tiers, scope, owned paths, sub-agents, how many agents may run at once, board post types, and the cache and fixture layout. Each package's acceptance test is in its agent definition, `.claude/agents/data-*.md`. The table below restates those packages in this file's columns so the other lanes can see what arrives and when. If the two files disagree, the data spec is right and this file is corrected. An earlier draft of this file numbered the Data packages differently; those numbers are withdrawn.

Reference: data spec sections 1 to 5 (keys, the CoStar kit, the Model API, Vexcel, external data). Keys and rate limits: data spec section 1 and SPEC 12.

How this table differs from the other lanes' tables:

- A Data package is bound to one file, not one folder, plus its fixture folder under `data/fixtures/` (data spec 6.1 and 6.4).
- ID, package name (the words before the colon), tier, bound path and output type come from data spec 6.1. The words after the colon and the In, Fixture and Depends on columns are this file's reading of the data spec.
- The acceptance test of `D1` to `D5` is a summary of the agent definition, which is the binding text. `D6` to `D10` have no test of their own there, so theirs is this file's proposal and starts with "Proposed" (R11).
- Data packages are started with `/data-wp <ID>` and reported with `/data-status`, not with the prompt of 5.4.

| ID | Package | Tier | Bound to | In | Out | Fixture | Acceptance test | Depends on |
|---|---|---|---|---|---|---|---|---|
| D1 | CoStar kit reader: S2 Ingest, CoStar layer. Reads the local mirror of the kit; finds a model's record through the two starter lists, joining on the Matterport model id; fills the join keys (`CostarData.matterport_model_id`, `CostarData.property_id`, `CostarData.listing_id`, `CostarData.residential_listing_id`) and the normalised fields (`CostarData.year_built` with `CostarData.year_built_event`, `CostarData.building_area_m2`, `CostarData.property_type_code`, `CostarData.building_class`); normalises city and state | P0 | `backend/data_layer/costar.py`, `data/fixtures/costar/` | `sid` | `CostarData` | `bundle#/costar` for the shape; its own payloads in `data/fixtures/costar/` | Agent definition `data-costar`: both golden properties resolve, the office by its property id and the house by its listing id; property type 5 selects offices; the year comes from the construction events and the event used is recorded; envelope area is the gross building area; city and state are normalised; the kit is never downloaded again and no dataset file is loaded whole; the fixture replays with the network off | `CostarData`; fx `bundle` |
| D2 | Matterport client: S2 Ingest, Matterport layer. Model API queries only, never a mutation: the georeference (`MatterportData.georeference`), floors and the wall graph with the openings of every edge (`WallEdge.openings`), rooms with dimensions, panoramas with six cached cube faces, floor plans, the defurnished view, MatterPak availability | P0 | `backend/data_layer/matterport.py`, `data/fixtures/matterport/` | `sid` | `MatterportData`, `GeoReference`, `Quaternion`, `Floor`, `Vertex`, `WallEdge`, `Opening`, `Room`, `Pano`, `FloorplanAsset` | `bundle#/matterport` for the shape; its own payloads in `data/fixtures/matterport/` | Agent definition `data-matterport`: rooms, dimensions, the wall graph with openings, panoramas, the defurnished view and floor plans return for both golden models; the georeference has the quaternion and its source, and the golden house reproduces the verified rotation; no URL is stored in cache or fixture; an absent field is handled as absent; the client stays well under 10 requests per second; the code contains no mutation; fixtures replay with the network off | `MatterportData`, `GeoReference`, `Quaternion`, `Floor`, `Vertex`, `WallEdge`, `Opening`, `Room`, `Pano`, `FloorplanAsset`; fx `bundle` |
| D3 | Vexcel client: S2 Ingest, Vexcel layer. `property/extract` at the model's georeferenced point: parcel, structures and which one is primary, footprint, roof attributes including the roof-object counts and the solar attribute. Roof height comes from one combined precomputed and calculated extract, is sanity-checked, and is returned with a confidence flag, never as a bare fact (data spec 4.3) | P0 | `backend/data_layer/vexcel.py`, `data/fixtures/vexcel/` | latitude and longitude from the `GeoReference` | `VexcelData`, `VexcelStructure` | `bundle#/vexcel` for the shape; its own payloads in `data/fixtures/vexcel/` | Agent definition `data-vexcel`: the precomputed extract parses into typed fields for both golden lots; the house lot and the office lot reproduce the verified roof shape, roof material and footprint area; the primary structure is chosen on a lot with two structures; height comes from one combined call, cached per property, and is sanity-checked; a 404 gives a `FetchRecord`, not an exception; a 429 is retried with backoff; WKT is longitude first; fixtures replay with the network off | `VexcelData`, `VexcelStructure`, `GeoReference`, `FetchRecord`; fx `bundle` |
| D4 | Cache + fetch records: the cache under `data/cache/`, keyed by source, identifier and query shape; atomic writes; no signed URL stored; one `FetchRecord` per fetch, with each normal "missing" outcome of data spec 6.4 distinct | P0 | `backend/data_layer/cache.py` | a payload with its source, identifier and query shape | `FetchRecord` | `bundle#/provenance` | Agent definition `data-cache`: a second identical call is served with the network blocked; each normal missing outcome gives a distinct, readable `FetchRecord`; no URL is in any cache entry; two queries that differ only in their include parameters do not share a key; an interrupted write never reads as a hit; a field that is absent and a field that is null stay distinguishable | `FetchRecord`; fx `bundle` |
| D5 | The one public door: S1 Locate and S2 Ingest. The door functions of 3.1. They first return fixture data, and `INTERFACE-LIVE:` is posted then; later they are backed by the source clients and the cache: search on the kit's starter lists, bundle assembly with one `FetchRecord` per layer, asset bytes | P0 | `backend/data_layer/api.py` | search parameters; `sid`; an asset path | `PropertySummary`, `PropertyBundle` | `bundle`, `search`; the payloads in `data/fixtures/` | Agent definition `data-api`: both golden properties return a valid `PropertyBundle` with each layer present or explained by a `FetchRecord`; a second call is served from cache with the network blocked; `search_properties` finds both golden properties by address and offices by property type 5; the office with several models reports which model the bundle used and the alternatives; `get_asset` returns bytes and never a URL; the bundle states whether it is a unit or a building; the whole path runs from `data/fixtures/` with the network off; `api.py` imports only `backend/schema.py` and the lane's own modules | `PropertySummary`, `PropertyBundle`, `MatterportData`, `VexcelData`, `CostarData`, `ClimateSite`, `Tariff`, `FetchRecord`, `Segment`, `UseType`; fx `bundle`, `search` |
| D6 | Golden fixtures: the payloads of the two golden properties (data spec 2.6). Each source agent writes them in its own fixture folder, never in the parent folder; same writers as the three source packages, after them | P0 | `data/fixtures/costar/`, `data/fixtures/matterport/`, `data/fixtures/vexcel/` | the two golden properties | golden payloads shaped as `CostarData`, `MatterportData` and `VexcelData` | `bundle` for the shape | Proposed: every file in the three fixture folders validates against its contract type; the door runs its whole path from them with the network off; a `FIXTURE-READY:` post names the files; what is committed follows O8 | `CostarData`, `MatterportData`, `VexcelData`, `PropertyBundle`; fx `bundle` |
| D7 | Index + office selection: S1 Locate over every model. The property index from the kit's lists and records; offices chosen by CoStar property type 5, not by segment (SPEC 3.2) | P1 | `backend/data_layer/index.py` | search parameters | `PropertySummary` | `search` | Proposed: every result validates as `PropertySummary`; a search for `use_type` office returns only records whose `CostarData.property_type_code` is 5; the spelling variants of city and state fold to one value; a radius search returns only rows inside the radius; `limit` is respected | `PropertySummary`, `Segment`, `UseType`, `CostarData`; fx `search` |
| D8 | Imagery + SAM 3: ortho and oblique image bytes, and `elements/detect` with SAM 3 on them, label `roof` at a detection threshold near 0.3 (SPEC 6.3 step 3). Each detection keeps its confidence, its map-coordinate bounding polygon and its pixel mask, cached at `VexcelDetection.mask_png_path` | P1 | `backend/data_layer/imagery.py` | latitude and longitude; labels | `VexcelDetection`; the `VexcelData` fields `ortho_path`, `oblique_paths` and `detections` | `bundle#/vexcel` | Proposed: a hand-written detect reply parses into `VexcelDetection` items with `bbox_wkt`, `pixel_bbox` and a cached mask at `mask_png_path`; a 429 is retried with backoff; no image URL is stored. live: the label `roof` on the golden house returns at least one detection | `VexcelData`, `VexcelDetection`, `FetchRecord`; fx `bundle` |
| D9 | External data: for a site, the typical-year hourly weather file, time zone and climate zone; electricity, gas and export prices; and the sources and citations for the emission factors and measure costs that the physics spec tabulates (data spec 5: the hourly source is the Open-Meteo archive and the Los Angeles tariff comes from the NREL rate database; Houston has no tariff source yet) | P1 | `backend/data_layer/external.py` | latitude, longitude, state | `ClimateSite`, `Tariff` | `bundle#/climate`, `bundle#/tariff`, `weather` | Proposed: the file at `ClimateSite.weather_path` has 8,760 rows in the format of `weather`; `Tariff.source` and `Tariff.retrieved` are set. live: one Los Angeles and one Houston point | `ClimateSite`, `Tariff`, `FetchRecord`; fx `bundle`, `weather` |
| D10 | The five unused datasets: tenancies and tenant companies into `CostarData.occupancy`; sale comparables and asking rents into `CostarData.market`, the inputs to value uplift | P2 | `backend/data_layer/costar_extra.py` | a CoStar property id | `OccupancyData`, `Tenancy`, `MarketData` | `bundle.office#/costar` | Proposed: synthetic tenancy and company rows give a valid `OccupancyData`; synthetic sale comparables give a valid `MarketData` whose `comp_count` is the number of comparables used; a property with no such records gives neither, not an exception | `CostarData`, `OccupancyData`, `Tenancy`, `MarketData`, `Ranged`; fx `bundle` |

Tasks of the lane owner, listed in data spec 6.1 with no tier and no sub-agent:

| ID | Task | Bound to | Out |
|---|---|---|---|
| D0 | Board reply, the verified mirror of the CoStar kit, the gaps in `.env` | none | the kit mirror under `data/cache/costar/` (data spec 2.1) |
| D11 | The data spec | `specs/data-integration.md` | the file |

Order inside the lane (data spec 6.1): `D0`, then `D1`, `D2` and `D3` in parallel, then `D5`, then `D6`. `D4` can start as a stub written from the contract. `D7` to `D10` start only after the walking skeleton (checkpoint 2).

Status on 2026-11-14, as the Data lane reports it: `D8`, `D9` and `D11` are done, and `D1` to `D7` and `D10` remain as implementation. The data spec bears out the research: 4.4 has the live imagery and SAM 3 results and 5 has the checked external sources. But data spec 6.1 has no status column and still lists `imagery.py` under `D8` and `external.py` under `D9`, and neither file is written. This file keeps both rows as data spec 6.1 has them until the Data lane says which package writes the two files (R2, R7).

#### 4.1.1 What the other lanes read, and when it arrives

Contract 0.2.0 fields that a package in another lane reads, with the Data package that fills them. A reader in a higher tier than its source runs on the fixtures of 2.3 until the source lands.

| Contract field | Filled by | Tier there | Read by |
|---|---|---|---|
| `MatterportData.georeference` | `D2` | P0 | `A9` for true north |
| `WallEdge.openings` | `D2` | P0 | `A9` for window and door surfaces, `A23` for door positions, `A7` to decide whether vision must size windows |
| the join keys and normalised fields of `CostarData`; `PropertySummary.costar_property_id`, `PropertySummary.costar_listing_id`, `PropertySummary.costar_residential_listing_id` | `D1`, `D5` | P0 | `A10` |
| `VexcelData.structures` (footprint, roof shape, roof-object counts, solar attribute) | `D3` | P0 | `A9`, `A11` |
| `PropertyBundle.climate`, `PropertyBundle.tariff` | `D9` | P1 | `A1`, `A3`, `A4`, `A19`, `A25`, all P0 (R2) |
| `VexcelData.detections` (with `VexcelDetection.mask_png_path`), `VexcelData.ortho_path`, `VexcelData.oblique_paths` | `D8` | P1 | `A12`, `A15`, `F9` |
| `CostarData.occupancy` | `D10` | P2 | `A10`, then `A2` and `A3` through `Systems.occupants` (R9) |
| `CostarData.market` | `D10` | P2 | `A30` for `Plan.value_uplift`, shown by `F6` (R9) |
| `MatterportData.splat_path`, `MatterportData.drone_photo_paths`, `MatterportData.mesh_path`, `MatterportData.point_cloud_path` | not stated (R8) | | `A13` |

#### 4.1.2 Requests to the Data lane

Things this plan needs from the Data lane that data spec 6.1 does not cover or leaves open. They are for @vigjay to answer; @yalexie1 raises them on the board. None of them is a package this file assigns.

| # | Request |
|---|---|
| R1 | **Fixtures and the licence.** Data spec 6.4 lists `data/fixtures/` as committed. SPEC 3.6 and 14 and the hard rules of the Data agent definitions say sponsor data is never committed, and the repository is public. State what a committed golden fixture may contain (O8). |
| R2 | **Weather and tariff at P0.** `PropertyBundle.climate` and `PropertyBundle.tariff` are required fields, and the P0 packages `A1`, `A3`, `A4`, `A19` and `A25` read them. `D9` is P1, and the Data lane reports it done: data spec 5 names the sources. But `external.py` is not written and is in no package the lane lists as remaining, Houston has no tariff source (data spec 5.2), and the weather file has no stated format. Needed by checkpoint 3 for the two golden sites: a `ClimateSite` with a real typical-year file, a `Tariff`, and a statement of who writes `external.py`. Until a format is written into data spec section 5, the weather sample of 2.3 is the reference (O9, O20). |
| R3 | **Two more door functions.** The data-api agent definition allows three. This file needs `get_property_summary(sid)` for the SPEC 10 route `GET /api/properties/{sid}`, and `detect_roof_elements(sid, labels)` for the SPEC 8 tool of that name, whose code would sit in `D8`. Agree to them or name the alternative (O2). |
| R4 | **Search before `D7`.** The acceptance test of `D5` has `search_properties` find both golden properties by address and offices by property type; the index is `D7`, which is P1. State what a search returns before `D7` lands. The Find screen (`F1`) and step 1 of the demo depend on it. |
| R5 | **The office `sid` and the house's splat.** The golden office is one CoStar property with three models. Data spec 3.2 and 4.5 use `HjEyXryhRLk`; confirm that it is the office `sid` the team uses. Confirm that the golden house has an aerial splat, as SPEC 13 P0 says (O18). |
| R6 | **Window openings and rotation.** SPEC 3.3 now records window openings on the golden house, and that an opening's position along its wall is a fraction from 0 to 1. Still open for the Data lane: whether the golden office has window openings, which end of the edge the fraction is measured from, and the sense of the georeference rotation (model frame to east, north, up, or the reverse). `A9` builds window surfaces and true north from them. |
| R7 | **The code of `D8`.** Data spec 4.4 holds the live imagery and SAM 3 findings, and the Data lane reports `D8` done. `imagery.py` is not written and is in no package the lane lists as remaining, yet the door's roof detection (R3), `VexcelData.detections`, `VexcelData.ortho_path` and `VexcelData.oblique_paths` come from it, and `A12`, `A15` and `F9` read them. State who writes it and when. |
| R8 | **Deep assets.** Data spec 6.1 does not say which package fills `MatterportData.mesh_path`, `MatterportData.point_cloud_path`, `MatterportData.splat_path` and `MatterportData.drone_photo_paths`. The splat and drone photos come from the track site, which data spec 3.4 has not re-verified. `A13` needs them. |
| R9 | **Occupancy and market data arrive at P2.** `D10` fills `CostarData.occupancy` and `CostarData.market`. SPEC 5.1 and 6.6 use them for office occupancy and value uplift, and SPEC 13 gives neither a tier (O5). Until `D10` lands their readers run on fixtures. If the team wants either in the demo, the lead decides whether `D10`, or the part of it for the golden office, moves up. Also: data spec 6.1 names the second output `value_uplift`; under contract 0.2.0 the Data lane supplies `MarketData` and Analysis computes `ValueUplift` (`A30`). Confirm. |
| R10 | **P2 items of SPEC 13 with no Data package.** "Any property on demand" (a valid bundle for any indexed `sid`, bulk fetching spread over the key sets) and the data side of portfolio screening (the Vexcel attribute filters of data spec 4.3). State whether they are inside `D5` and `D7` or need a package (O12). |
| R11 | **Acceptance checks and test files.** Data spec 6.1 has no acceptance column. For `D1` to `D5` this file summarises the agent definitions; for `D6` to `D10` the checks above are proposals. Confirm or replace them, and state where each package's tests live, so that two agents never write the same test file. |
| R12 | **Emission factors and measure costs.** `D9` lists emissions as an output and data spec 5 adds measure cost data. Data spec 5.2 says the emission factor values have not been opened and cost data is not started, and 5.3 that every CO2 figure is blocked until then. The contract has no type for either. This file reads them as sources and citations for the emission and cost tables of the physics spec (physics 04), not as door outputs. Confirm, and say who opens the emission factor file. |

### 4.2 Analysis lane (`A`), @yalexie1

Reference: physics spec. Every physics function has a unit test against its worked example there, and every `MeasureResult` lists its `formula_ids` (SPEC 14). All tests run with no network.

| ID | Package | Tier | Bound to | In | Out | Fixture | Acceptance test | Depends on |
|---|---|---|---|---|---|---|---|---|
| A0 | Lane scaffold: the twelve door functions of 3.2 as stubs that return fixtures; `backend/config.py` constants (SPEC 12); dependencies file | P0 | `backend/analysis/api.py`, `backend/config.py` | as 3.2 | as 3.2 | `bundle`, `model`, `run` | `pytest backend/analysis/tests -q`: every door function returns fixture data that validates; no network call is made | `PropertyBundle`, `BuildingModel`, `BaselineResult`, `MeasureResult`, `SolarDesign`, `LayoutResult`, `Plan`, `FinancingScenario`, `Incentive`, `Question`, `RunRequest`; fx `bundle`, `model`, `run` |
| A1 | Climate inputs for S5 and solar: weather file reader, solar position, irradiance split (needed only when the weather file has no direct and diffuse columns, data spec 5.3) and transposition onto a tilted plane (physics 01: SOL, IRR). Also writes the weather sample of 2.3 | P0 | `backend/analysis/physics/climate/`, `specs/examples/weather/` | `ClimateSite`; tilt and azimuth | hourly arrays: sun azimuth and elevation, irradiance on the plane, outdoor temperature | `bundle#/climate`, `weather` | `pytest backend/analysis/physics/climate -q`: each formula reproduces its worked example; the reader returns 8,760 hours from `weather` | `ClimateSite`; fx `bundle`, `weather` |
| A2 | S5 Baseline, zone loads: envelope conduction, ground contact, infiltration and ventilation (ventilation follows `Systems.occupants` when it is set), window solar gain, sol-air roof, hourly zone model (physics 02: ENV, ZON, INF, WIN) | P0 | `backend/analysis/physics/zone/` | `BuildingModel`; hourly arrays passed in (temperature, irradiance per surface, internal gains) | hourly heating and cooling load per `Zone`; peak heating and cooling in W | `model` | `pytest backend/analysis/physics/zone -q`: worked examples reproduce; doubling every `u_value` raises the annual heating load; a zone with `conditioned=false` has zero load | `BuildingModel`, `Zone`, `Surface`, `Systems`, `Ranged`; fx `model` |
| A3 | S5 Baseline, systems and totals: HVAC, water heating, lighting and plug loads with their heat gains (occupant-driven loads use `Systems.occupants` when it is set, else the schedule default), cost from the tariff, emissions, low, expected and high (physics 02: HVAC, DHW, LGT; physics 04) | P0 | `backend/analysis/physics/systems/` | `Systems`, `Tariff`; hourly loads passed in | `BaselineResult`, `EnergyUse` | `model`, `run#/baseline` | `pytest backend/analysis/physics/systems -q`: worked examples reproduce; `low <= expected <= high` on every `Ranged`; 12 monthly values; end uses sum to the annual expected total; a `Systems` without `occupants` runs on the schedule default | `Systems`, `Tariff`, `BaselineResult`, `EnergyUse`, `Ranged`; fx `model`, `run` |
| A4 | PV production: cell temperature, DC and AC output, losses (physics 01: PV) | P0 | `backend/analysis/physics/pv/` | hourly plane irradiance and temperature, shading factor, as arrays | hourly kWh per kW DC | `weather` | `pytest backend/analysis/physics/pv -q`: the worked example reproduces; annual yield on `weather` is within the tolerance the physics spec states against its reference implementation | `Ranged`; fx `weather` |
| A5 | Daylight, glare and thermal comfort at a point (physics 03: DAY, GLR, CMF, LCT) | P1 | `backend/analysis/physics/daylight/` | `Room`, `Surface`; window positions from `Opening`; sun arrays; a point x, y | the `DeskScore` fields `daylight`, `glare_risk`, `comfort_ppd` | `model`, `bundle#/matterport` | `pytest backend/analysis/physics/daylight -q`: worked examples reproduce; a point beside a window has higher daylight than a point 6 m into the room | `Room`, `Surface`, `WallEdge`, `Opening`, `DeskScore`; fx `model`, `bundle` |
| A6 | Bill calibration (physics 04, measurement and verification) | P2 | `backend/analysis/physics/calibration/` | `BaselineResult`, `UtilityBills` | `BaselineResult` with `calibrated_to_bills=true` | `run#/baseline` | `pytest backend/analysis/physics/calibration -q`: calibrated monthly electricity matches the twelve bill values within the tolerance the physics spec states | `BaselineResult`, `UtilityBills`; fx `run` |
| A7 | S3 See, interior: read panoramas for glazing cues (frame, single or double pane, shading), HVAC, water heater and lighting (SPEC 5.2). Window count and size are read only as a cross-check on the measured openings, or as the fallback for a model whose wall graph has no window openings. The live call waits for the answer on sending sponsor imagery to an external model (SPEC 16); until then the lane runs on vintage defaults | P0† | `backend/analysis/vision/` | `PropertyBundle`; a function that returns an asset's bytes, passed in | `Assumption` with `source="vision"`, `EvidenceRef` with `kind="pano"` | `bundle` | `pytest backend/analysis/vision -q`: a hand-written model reply maps to assumptions for all four targets, each with at least one panorama as evidence and a confidence; on the office fixture, whose wall graph has window openings, no window-size assumption is written; on the house fixture, which has none, window count and size come back with `source="vision"`; a malformed reply yields no assumption and no exception; the test makes no network call | `PropertyBundle`, `Pano`, `Room`, `WallEdge`, `Opening`, `Assumption`, `EvidenceRef`; fx `bundle` |
| A8 | S3 See, feasibility cues: wall material, outlet type, main panel; electrical flag with added cost (SPEC 5.2, 6.3 step 7). After A7 | P1 | `backend/analysis/vision/` | `PropertyBundle` | `Assumption`, `Flag` | `bundle` | `pytest backend/analysis/vision -q`: a two-prong reply gives `likely_upgrade` with an `added_cost_usd` range; nothing visible gives `unknown`; a cue changes range and confidence only and never writes a `source` other than `vision` | `PropertyBundle`, `Assumption`, `Flag`, `EvidenceRef`; fx `bundle` |
| A9 | S4 Model, geometry: rooms and wall graph to zones and surfaces; exterior or adjacent boundary per wall; window and door surfaces from the measured openings in `WallEdge.openings` (area from width and height, azimuth from the edge and the north offset), and from vision sizes only where a model has no window openings; true north from `MatterportData.georeference`, with the match of the floor outline to the Vexcel footprint as the cross-check and as the fallback, and `BuildingModel.north_source` recording which was used (SPEC 6.3 step 2, SPEC 16) | P0 | `backend/analysis/model/geometry/` | `MatterportData`, `VexcelData`, `Assumption` | `Zone`, `Surface` with `Surface.source_edge_id` and, for a window or door built from an opening, `Surface.source_opening_id`; `north_offset_deg` as a `Ranged`; the `north_source` value | `bundle`, `model` | `pytest backend/analysis/model/geometry -q`: on the house fixture, zone floor areas sum to the room areas within 1%; every surface names an existing zone; on the office fixture each opening of type `window` becomes one window surface with area equal to width times height, its wall as `parent_surface_id` and its opening as `source_opening_id`; on the house fixture, which has no window openings, window surfaces come from the vision assumptions and have no `source_opening_id`; with a georeference the result is `north_source="georeference"`; when the georeference and the footprint disagree, or the georeference is absent, it is `footprint_registration` with a wider `north_offset_deg`; with no footprint either it is `assumed` | `MatterportData`, `GeoReference`, `Quaternion`, `Floor`, `WallEdge`, `Opening`, `Room`, `VexcelData`, `VexcelStructure`, `Zone`, `Surface`, `Ranged`, `Assumption`; fx `bundle`, `model` |
| A10 | S4 Model, assumption registry: vintage defaults by era, climate zone and building type; merge by source strength (SPEC 5.1); `Systems` from assumptions; year built from `CostarData.year_built` with `CostarData.year_built_event` as evidence, and envelope area from `CostarData.building_area_m2`, never the rentable area; for an office with CoStar tenancies, `Systems.occupants` and the occupancy-driven assumptions from `CostarData.occupancy` with source `costar`, otherwise vintage defaults; the model's feasibility flags, each `unknown` until a cue sets it (SPEC 5.2); `set_assumption` and overrides (physics 02: DEF) | P0 | `backend/analysis/model/registry/` | `PropertyBundle`, `Assumption`; overrides as a plain map | `Assumption`, `Systems`, `Flag` | `bundle`, `model#/assumptions` | `pytest backend/analysis/model/registry -q`: for one key, `user` replaces `vision` replaces `vintage_default`; a bundle with no CoStar record gets a wider vintage range; the office fixture with tenancies gives `Systems.occupants` and an assumption with `source="costar"`; the same bundle without `costar.occupancy` gives no `occupants` and the vintage default; with no cue the electrical and structural flags are `unknown`; a number override collapses the range and sets `source="user"` | `PropertyBundle`, `CostarData`, `OccupancyData`, `Tenancy`, `ClimateSite`, `Assumption`, `Source`, `Systems`, `Flag`, `Ranged`; fx `bundle`, `model` |
| A11 | Roof planes, parametric, the P0 path (SPEC 6.3 step 2, sources 2 and 3, and step 4): flat, gable or hip from the footprint and the roof shape class; tilt is the pitch range looked up by shape, azimuth comes from the footprint's ridge direction; Vexcel's calculated roof height is not used for pitch. Usable area is the plane area minus an allowance per obstruction counted in Vexcel's precomputed roof-object attributes minus setbacks, and the counts are kept in `RoofPlane.obstruction_counts`; existing solar is read from the precomputed solar attribute (SPEC 6.3 step 3; physics 01: ROOF) | P0 | `backend/analysis/solar/roof/` | `VexcelData`; north offset in degrees | `RoofPlane` with `geometry_source` `vexcel_parametric` or `assumed` | `bundle#/vexcel`, `model#/roof_planes` | `pytest backend/analysis/solar/roof -q`: plane areas match footprint area divided by the cosine of the tilt within 2%; a missing shape class gives `assumed` with the widest tilt range; `usable_area_m2 <= area_m2`; a higher obstruction count gives a lower `usable_area_m2`; a solar attribute of true is reported so `PV_ROOF` can be skipped as already done; a roof height in the attributes changes no tilt | `VexcelData`, `VexcelStructure`, `RoofPlane`, `Ranged`; fx `bundle`, `model` |
| A12 | Roof extent from SAM 3 (SPEC 6.3 step 3): turn the pixel masks of the `roof` detections into map polygons (`VexcelDetection.mask_wkt`), which give roof area and tree overhang, and refine the usable area with them. SAM 3 returns fragments, not planes, so plane geometry and obstruction counts stay as the parametric path left them. After A11 | P1 | `backend/analysis/solar/roof/` | `VexcelDetection`, `RoofPlane`; mask bytes passed in | `RoofPlane` with a refined `usable_area_m2`; `VexcelDetection` items with `mask_wkt` | `bundle#/vexcel`, `model#/roof_planes` | `pytest backend/analysis/solar/roof -q`: a synthetic mask with a known pixel box and bounding polygon becomes a map polygon of the expected area within 5%; a tree mask over a plane lowers `usable_area_m2` by at least the overlap; fragments never raise `usable_area_m2` above the parametric value; with no detections the planes come back unchanged | `VexcelDetection`, `RoofPlane`; fx `bundle`, `model` |
| A13 | Roof planes from the aerial splat and drone photos (SPEC 6.3 step 2, source 1). The splat is in its own local frame, so the planes are registered to the Vexcel footprint | P1† | `backend/analysis/solar/splat/` | `MatterportData`, `VexcelData`; the splat's bytes passed in | `RoofPlane` with `geometry_source="splat"` | `bundle#/matterport`, `bundle#/vexcel` | `pytest backend/analysis/solar/splat -q`: a synthetic point set for a 30 degree gable returns two planes with tilt within 3 degrees and azimuths 180 degrees apart; rotating the point set leaves the registered azimuths unchanged | `MatterportData`, `VexcelData`, `VexcelStructure`, `RoofPlane`; fx `bundle` |
| A14 | Panel layout (SPEC 6.3 step 6): fill planes in order of yield per panel; stop at roof area, budget or annual consumption (physics 01: LAY) | P0 | `backend/analysis/solar/layout/` | `RoofPlane`, two `Flag` values; budget and annual consumption as numbers; a yield function passed in | `SolarDesign`, `PanelPlacement` | `model#/roof_planes`, `run#/measures` | `pytest backend/analysis/solar/layout -q`: one test case per stop condition; every panel polygon lies inside its plane's usable area; `panel_count` equals the number of `panels` | `RoofPlane`, `SolarDesign`, `PanelPlacement`, `Flag`; fx `model`, `run` |
| A15 | Shading by ray casting, hour by hour, against exterior geometry and tree masks (SPEC 6.3 step 4; physics 01: SHD) | P1 | `backend/analysis/solar/shading/` | `RoofPlane`, `VexcelDetection`, `PanelPlacement`; sun arrays passed in | a shading factor per panel and hour; `shading_loss_fraction` | `model#/roof_planes` | `pytest backend/analysis/solar/shading -q`: a wall due south of a panel gives a loss above zero at winter noon and zero when the wall is removed | `RoofPlane`, `VexcelDetection`, `PanelPlacement`; fx `model` |
| A16 | S6 Measures, engine: applicability by role, flow and feasibility flags (SPEC 6.2); evaluate = apply the measure to the current state, simulate before and after, report the difference | P0 | `backend/analysis/measures/engine/` | `PropertyBundle`, `BuildingModel`, `MeasureId`, `Role`; a simulate function passed in | `MeasureResult` with `savings` | `model`, `run#/measures` | `pytest backend/analysis/measures/engine -q` with a fake simulate: a `tenant` asking for `ENV_ATTIC` gets `applicable=false` with a reason; every result lists `formula_ids`; the same measure evaluated on a state that already has another measure applied gives a different saving | `PropertyBundle`, `BuildingModel`, `MeasureId`, `Role`, `MeasureResult`, `EnergyUse`, `BaselineResult`; fx `model`, `run` |
| A17 | S6 Measures `ENV_ATTIC`, `ENV_AIRSEAL`, `ROOF_COOL`: applicability, the change each makes to the model, anchors, evidence, formula ids | P0 | `backend/analysis/measures/envelope/` | `BuildingModel` | changed `BuildingModel`; `MeasureResult` (`params`, `anchors` as `Anchor` items, `evidence`, `formula_ids`) | `model` | `pytest backend/analysis/measures/envelope -q`: each measure changes only the fields it names; an attic already at the target insulation returns the already-done reason; the input model is not mutated | `BuildingModel`, `Surface`, `Systems`, `Assumption`, `MeasureResult`, `Anchor`, `EvidenceRef`; fx `model` |
| A18 | S6 Measures `HVAC_HP`, `HVAC_RTU`, `LGT_LED`: same content as A17 | P0 | `backend/analysis/measures/systems/` | `BuildingModel` | changed `BuildingModel`; `MeasureResult` | `model` | `pytest backend/analysis/measures/systems -q`: `HVAC_HP` applies to the house fixture and not the office, `HVAC_RTU` the reverse; `LGT_LED` lowers `lighting_w_per_m2`; the input model is not mutated | `BuildingModel`, `Systems`, `Assumption`, `MeasureResult`, `Anchor`, `EvidenceRef`; fx `model` |
| A19 | S6 Measure `PV_ROOF`: savings from a `SolarDesign`, with self-consumption and the export price; skip when a flag blocks it | P0 | `backend/analysis/measures/pv/` | `SolarDesign`, `BaselineResult`, `Tariff` | `MeasureResult` with `solar` | `run#/measures` | `pytest backend/analysis/measures/pv -q`: production above consumption is valued at `export_usd_per_kwh`; with no export price (Texas, SPEC 6.6) the export value is a range whose low end is zero; a structural `Flag` of `blocked` gives `applicable=false` with the reason | `SolarDesign`, `BaselineResult`, `Tariff`, `MeasureResult`, `Flag`, `EnergyUse`; fx `run` |
| A20 | S6 Measures `ENV_WALL`, `WIN_REPLACE`, `WIN_FILM`, `WIN_SHADE`: same content as A17 | P1 | `backend/analysis/measures/walls_windows/` | `BuildingModel` | changed `BuildingModel`; `MeasureResult` | `model` | `pytest backend/analysis/measures/walls_windows -q`: `ENV_WALL` is offered to the house fixture only; the window measures change `u_value` or `shgc` of window surfaces only; the input model is not mutated | `BuildingModel`, `Surface`, `Assumption`, `MeasureResult`, `Anchor`, `EvidenceRef`; fx `model` |
| A21 | S6 Measures `HVAC_ECON`, `HVAC_DUCT`, `DHW_HPWH`: same content as A17 | P1 | `backend/analysis/measures/hvac_dhw/` | `BuildingModel` | changed `BuildingModel`; `MeasureResult` | `model` | `pytest backend/analysis/measures/hvac_dhw -q`: `HVAC_ECON` is offered to the office fixture only, `HVAC_DUCT` and `DHW_HPWH` to the house only; the input model is not mutated | `BuildingModel`, `Systems`, `Assumption`, `MeasureResult`, `Anchor`, `EvidenceRef`; fx `model` |
| A22 | S6 Measures `LGT_CTRL`, `PLUG_MGMT`, `CTRL_TSTAT`: same content as A17 | P1 | `backend/analysis/measures/controls/` | `BuildingModel` | changed `BuildingModel`; `MeasureResult` | `model` | `pytest backend/analysis/measures/controls -q`: `LGT_CTRL` and `PLUG_MGMT` are offered to the office fixture only, `CTRL_TSTAT` to both; a `tenant` may do all three; the input model is not mutated | `BuildingModel`, `Systems`, `Assumption`, `MeasureResult`, `Anchor`, `EvidenceRef`; fx `model` |
| A23 | Desk placement and the `LAYOUT` measure (SPEC 6.4): candidate grid clear of the door openings in `WallEdge.openings`, scoring, top N with minimum spacing, lighting energy displaced at zero cost | P1 | `backend/analysis/layout/` | `MatterportData`, `BuildingModel`; desks requested as a number; a point-scoring function passed in | `LayoutResult`, `DeskScore`, `MeasureResult` | `bundle#/matterport`, `run.office#/measures` | `pytest backend/analysis/layout -q`: candidates sit on a 0.5 m grid at least 0.6 m from walls; the number recommended equals the number requested; recommended desks keep the minimum spacing | `MatterportData`, `Room`, `Floor`, `WallEdge`, `Opening`, `BuildingModel`, `LayoutResult`, `DeskScore`, `MeasureResult`; fx `bundle`, `run` |
| A24 | S7 Plan, costs and incentives: installed cost table with sources, maintenance change, useful life, incentive registry with status and citation, net upfront cash (SPEC 6.6; physics 04) | P0 | `backend/analysis/finance/costs/` | `MeasureResult`, `PropertySummary` | `Incentive`; the `FinancialBreakdown` fields `installed_cost_usd`, `cost_source`, `useful_life_years`, `annual_om_change_usd`, `net_upfront_usd` | `run#/measures` | `pytest backend/analysis/finance/costs -q`: every `MeasureId` has a cost entry with a named source; net upfront subtracts `upfront_rebate` incentives only; federal incentives carry `unverified` and are left out of every total | `MeasureResult`, `MeasureId`, `PropertySummary`, `Incentive`, `FinancialBreakdown`, `Ranged`; fx `run` |
| A25 | S7 Plan, life-cycle economics: simple and discounted payback, NPV, SIR, IRR, the cash scenario (physics 04) | P0 | `backend/analysis/finance/economics/` | `EnergyUse`, `Tariff`, `Incentive`; cost fields as `Ranged` | `FinancialBreakdown`, `FinancingScenario` with `kind="cash"` | `run#/measures` | `pytest backend/analysis/finance/economics -q`: worked examples reproduce; discount rate, escalation rates and analysis period come from `backend/config.py` and are echoed in the result; zero savings gives no payback value, not a division error | `EnergyUse`, `Tariff`, `Incentive`, `FinancialBreakdown`, `FinancingScenario`, `Ranged`; fx `run` |
| A26 | S7 Plan, budget algorithm of SPEC 6.5. A `ValueUplift` computed elsewhere is taken as an optional argument and placed on `Plan.value_uplift` unchanged | P0 | `backend/analysis/finance/plan/` | `MeasureId`, `Role`; budget as a number; an evaluate-and-price function passed in; an optional `ValueUplift` | `Plan`, `PlanItem`, `SkippedItem` | `run#/plan` | `pytest backend/analysis/finance/plan -q` with a fake evaluate function: when the top measure is over budget the next one is taken; an expected cost that fits with a high cost that does not adds the warning "may exceed budget"; every measure not selected is in `financeable` or in `skipped` with a reason; a `ValueUplift` passed in appears on the plan and changes no total and no order; the same inputs give an identical `Plan` twice | `MeasureId`, `Role`, `MeasureResult`, `Plan`, `PlanItem`, `SkippedItem`, `ValueUplift`, `EnergyUse`, `Ranged`; fx `run` |
| A27 | Sensitivity for the ask rule (SPEC 5.3 steps 1 to 3). Also writes the wide and narrow fixture pair of 2.3 | P0 | `backend/analysis/finance/sensitivity/`, `specs/examples/ask/` | `BuildingModel`; a plan function passed in; `ASK_WIDTH` | `Question`, `Choice` | `ask` | `pytest backend/analysis/finance/sensitivity -q`: the wide fixture returns at least one `Question`, first the assumption with the largest swing; the narrow fixture returns none; every question has an "I don't know" choice with no value | `BuildingModel`, `Assumption`, `Plan`, `Question`, `Choice`; fx `ask` |
| A28 | C-PACE scenario (SPEC 6.6) | P1 | `backend/analysis/finance/cpace/` | `MeasureResult`, `PropertySummary` | `FinancingScenario` with `kind="cpace"` | `run.office#/measures` | `pytest backend/analysis/finance/cpace -q`: a house, or any residential property under five units, gives `eligible=false`; the term is never longer than the useful life; the program's own savings test (in Texas the program SIR) is reported in `FinancingScenario.program_sir`, apart from `FinancialBreakdown.sir`, and a value below 1 gives `eligible=false`; `notes` carry the lien and lender-consent statements; the annual payment matches the worked example | `MeasureResult`, `PropertySummary`, `FinancingScenario`, `FinancialBreakdown`; fx `run` |
| A29 | Lane wiring: replace each A0 stub with the real modules, passing results and functions between subfolders; reproducibility on the fixtures. After A0, same writer | P0 | `backend/analysis/api.py` | as 3.2 | as 3.2: `BuildingModel`, `BaselineResult`, `MeasureResult`, `SolarDesign`, `LayoutResult`, `Plan`, `FinancingScenario`, `Incentive`, `Question` | `bundle`, `model`, `run` | `pytest backend/analysis/tests -q`: every door function runs on the fixtures with no network; `build_plan` on each fixture gives byte-identical JSON on two runs; every `MeasureResult` returned has `formula_ids`; `Plan.value_uplift` is filled only when the bundle has market data and the value module is merged, and is empty otherwise | `PropertyBundle`, `BuildingModel`, `BaselineResult`, `MeasureResult`, `SolarDesign`, `LayoutResult`, `Plan`, `ValueUplift`, `FinancingScenario`, `Incentive`, `Question`, `RunRequest`; fx `bundle`, `model`, `run` |
| A30 | Value uplift (SPEC 6.6): the estimated change in property value from the plan's annual savings, capitalised at the rate from comparable sales in `CostarData.market`; low, expected and high, with the number of comparables; reported beside the plan totals, never added to savings and never used in the ranking (physics 04: VAL). Live data arrives with the Data lane's `D10` | P2† | `backend/analysis/finance/value/` | `MarketData`; the plan's total annual savings as a `Ranged` | `ValueUplift` | `bundle.office#/costar`, `run.office#/plan` | `pytest backend/analysis/finance/value -q`: the worked example reproduces; no market data, no capitalisation rate or a `comp_count` of zero gives no `ValueUplift`, not a guess; `low <= expected <= high`; `method` names the physics entry used; `comp_count` is echoed | `MarketData`, `ValueUplift`, `Ranged`; fx `bundle`, `run` |

### 4.3 Agent and server lane (`G`), @Sri-SriPod

Reference: SPEC 8 (agents, tools, rules, build notes) and SPEC 10 (routes). Tests use the stub doors, so no model key and no other lane is needed. A line starting `live:` needs `ANTHROPIC_API_KEY`.

| ID | Package | Tier | Bound to | In | Out | Fixture | Acceptance test | Depends on |
|---|---|---|---|---|---|---|---|---|
| G0 | Lane scaffold: the run door of 3.5 as stubs that replay fixtures; dependencies file; confirm the installed `deepagents` signature and the two [U] notes of SPEC 8 | P0 | `backend/agent/api.py` | `RunRequest`, `DocumentRequest` | `RunEvent`, `RunResult`, `DocumentDraft` | `run`, `events`, `draft` | `pytest backend/agent/tests -q`: `start_run` then `stream_events` replays `events` and ends with `done`; `get_run` returns a valid `RunResult` | `RunRequest`, `RunEvent`, `RunResult`, `DocumentRequest`, `DocumentDraft`; fx `run`, `events`, `draft` |
| G1 | Tools: wrappers of 3.4 for `search_properties`, `get_property_bundle`, `get_asset`, `observe_interior`, `detect_roof_elements`, `build_building_model`, `set_assumption`, `run_baseline`, `evaluate_measure`, `design_pv`, `score_desk_positions`, `price_measure`, `lookup_incentives`, `build_plan`, `cpace_scenario`, `sensitivity`, `list_templates`, `fill_template`, `check_document`; results written to the run files | P0 | `backend/agent/tools/` | as 3.4 | as 3.4 | `bundle`, `model`, `run`, `draft` | `pytest backend/agent/tools -q` against the stub doors: each of the 19 tools is callable by its SPEC 8 name and returns schema-valid JSON; a door that raises becomes a tool error message, not a crash; no wrapper contains arithmetic on result values | `PropertyBundle`, `BuildingModel`, `BaselineResult`, `MeasureResult`, `Plan`, `Question`, `DocumentDraft`, `StatutoryCheck`, `DocType`; fx `bundle`, `model`, `run`, `draft` |
| G2 | Deep agent: `auditor` orchestrator with `scout`, `surveyor`, `physicist` and `financier`; model ids from `backend/config.py`; visible todo list; fallbacks decided and logged (SPEC 8 rules 2 and 5) | P0 | `backend/agent/graph/` | `RunRequest`; tools passed in | agent messages, todo items, tool calls | `run`, `events` | `pytest backend/agent/graph -q` with fake tools and a scripted model: each subagent is given only the tools SPEC 8 lists for it; the todo list changes during the run; a bundle with no splat, and one with no `georeference`, each produce a logged fallback (SPEC 8 rule 5 lists five). live: one run on the house fixture produces a bundle, model, baseline, measures and plan in that order | `RunRequest`, `PropertyBundle`, `BuildingModel`, `BaselineResult`, `MeasureResult`, `Plan`, `MeasureId`; fx `run`, `events` |
| G3 | Ask rule: `ask_user` tool, pause and resume, stop after `ASK_MAX`, "I don't know" keeps the range (SPEC 5.3 step 4, SPEC 8 rule 3) | P0 | `backend/agent/ask/` | `Question`; the answer value | a `question` `RunEvent`; the run resumed | `run.house#/questions`, `events` | `pytest backend/agent/ask -q`: given the question of the house fixture the run pauses with status `waiting_for_user` and exactly one question; resuming with a value leads to a `set_assumption` call; resuming with no value changes no assumption; given an empty list the run never pauses; never more than `ASK_MAX` questions | `Question`, `Choice`, `RunEvent`, `RunResult`; fx `run`, `events` |
| G4 | S8 Explain: narrative with tags, and the `check_narrative` step (SPEC 8 rule 1) | P0 | `backend/agent/narrative/` | `RunResult` | `narrative_md` text; a list of mismatches | `run` | `pytest backend/agent/narrative -q`: the fixture narrative passes; changing one number in the text fails; a number that appears in no structured result fails | `RunResult`, `Plan`, `MeasureResult`, `BaselineResult`, `Ranged`; fx `run` |
| G5 | Run runtime: run lifecycle, agent stream mapped to `RunEvent`, the six run files of SPEC 8 rule 6, `RunResult` saved under `data/runs/{run_id}/` | P0 | `backend/agent/runtime/`, `data/runs/` | `RunRequest`; an agent passed in | `RunEvent`, `RunResult` | `events`, `run` | `pytest backend/agent/runtime -q` with a fake agent: the emitted event types match those in `events`; the six run files exist after `done`; the saved `RunResult` reloads and validates; an agent exception becomes an `error` event and status `error` | `RunRequest`, `RunEvent`, `RunResult`; fx `events`, `run` |
| G6 | `counsel` subagent and approval before drafting (S9 Draft, SPEC 8 rule 4). After G2 | P0 | `backend/agent/graph/` | `DocumentRequest`, `RunResult` | `DocumentDraft` | `docreq`, `draft` | `pytest backend/agent/graph -q` with the stub legal door: `fill_template` does not run until the parties and the measure list are approved; a rejected approval produces no draft; the returned draft lists `unfilled_placeholders` and `statutory_checks` | `DocumentRequest`, `DocumentDraft`, `StatutoryCheck`, `DocType`, `RunResult`; fx `docreq`, `draft`, `run` |
| G7 | Server skeleton: all eleven routes of SPEC 10 answering from fixtures; the error envelope | P0 | `backend/server.py`, `backend/agent/server/` | as SPEC 10 | as SPEC 10 | `search`, `run`, `events`, `docreq`, `draft` | `pytest backend/agent/server -q`: every route returns its fixture and the body validates; an unknown `run_id` gives 404 with `{error: {code, message}}`; `GET /api/health` returns `SCHEMA_VERSION` | `PropertySummary`, `RunRequest`, `RunEvent`, `RunResult`, `DocumentRequest`, `DocumentDraft`; fx `search`, `run`, `events`, `docreq`, `draft` |
| G8 | Routes on the data door: `GET /api/health`, `GET /api/properties/search`, `GET /api/properties/{sid}` (answered from the bundle's `summary` until R3 gives a summary function), `GET /api/assets/{path}`. After G7 | P0 | `backend/server.py`, `backend/agent/server/` | query parameters | `PropertySummary`; image bytes | `search`, `bundle` | `pytest backend/agent/server -q` against the stub data door: all seven search parameters reach `search_properties`; an asset path outside the cache is refused with 404; an unknown `sid` gives 404 | `PropertySummary`, `Segment`, `UseType`; fx `search`, `bundle` |
| G9 | Routes on the run door: `POST /api/runs`, `GET /api/runs/{run_id}/events`, `GET /api/runs/{run_id}`, `POST /api/runs/{run_id}/answers`. After G8 | P0 | `backend/server.py`, `backend/agent/server/` | `RunRequest`; `{question_id, value}` | `{run_id}`; a stream of `RunEvent`; `RunResult`; `{ok}` | `run`, `events` | `pytest backend/agent/server -q` against the stub run door: the event stream ends with `done`; an answer posted to a waiting run reaches `answer`; an invalid `RunRequest` gives 422 in the error envelope | `RunRequest`, `RunEvent`, `RunResult`, `Question`; fx `run`, `events` |
| G10 | Routes for documents: `POST /api/runs/{run_id}/documents`, `GET /api/runs/{run_id}/documents/{doc_id}`. After G9 | P0 | `backend/server.py`, `backend/agent/server/` | `DocumentRequest` | `DocumentDraft` | `docreq`, `draft` | `pytest backend/agent/server -q`: a posted `DocumentRequest` returns a `DocumentDraft`; the same draft is returned by its `doc_id`; a request for a run that is not `done` is refused | `DocumentRequest`, `DocumentDraft`; fx `docreq`, `draft` |
| G11 | Adjust and re-run (SPEC 4 step 6): `PATCH /api/runs/{run_id}` with a new budget or overrides, then new events. After G5 and G10 | P1† | `backend/server.py`, `backend/agent/runtime/` | `{budget_usd?, overrides?}` | `{ok}`; new `RunEvent` items; an updated `RunResult` | `run`, `events` | `pytest backend/agent/server backend/agent/runtime -q`: a lower budget produces a new `done` event and a `RunResult` whose `plan.budget_usd` is the new value; an override key that is not an assumption key is refused | `RunRequest`, `RunEvent`, `RunResult`, `Assumption`; fx `run`, `events` |
| G12 | Any property on demand: the run completes for any indexed `sid`, using the fallbacks of SPEC 8 rule 5. After G6 | P2 | `backend/agent/graph/` | `RunRequest` | `RunResult`, `RunEvent` | `bundle`, `run` | `pytest backend/agent/graph -q` with a stub bundle that has no `vexcel`, no `costar`, no `georeference` and no window openings: the run reaches `done`; each gap appears as a `fallback` event and in `RunResult.warnings` | `RunRequest`, `PropertyBundle`, `FetchRecord`, `RunEvent`, `RunResult`; fx `bundle`, `run` |
| G13 | Portfolio screening: run many properties and rank them by retrofit return. Starts only after O12 is settled | P2 | `backend/agent/portfolio/` | `PropertySummary`, `RunRequest` | `RunResult` items in rank order | `search`, `run` | `pytest backend/agent/portfolio -q` with a stub run door: three fixture runs come back ordered by the return measure O12 settles; a failed run is listed with its error, not dropped | `PropertySummary`, `RunRequest`, `RunResult`, `Plan`; fx `search`, `run` |

### 4.4 Legal drafting lane (`L`), @Sri-SriPod

Reference: legal spec. `specs/legal.md` has the templates, the clause library and the placeholder table (package `L9`, this lane); the state files have the required terms with citations (package `C6`). Templates use `{{snake_case}}` placeholders. Every draft carries the notice that it is a draft for attorney review and not legal advice.

| ID | Package | Tier | Bound to | In | Out | Fixture | Acceptance test | Depends on |
|---|---|---|---|---|---|---|---|---|
| L0 | Lane scaffold: the three door functions of 3.3 as stubs that return fixtures; dependencies file | P0 | `backend/legal/api.py` | `DocumentRequest`, `RunResult` | `DocType`, `DocumentDraft`, `StatutoryCheck` | `docreq`, `draft`, `run` | `pytest backend/legal/tests -q`: the three door functions return fixture data that validates | `DocumentRequest`, `RunResult`, `DocType`, `DocumentDraft`, `StatutoryCheck`; fx `docreq`, `draft`, `run` |
| L1 | S9 Draft, engine: template loading, placeholder resolver bound to contract fields by the legal spec's placeholder table, visible blanks, the notice, `list_templates` and `fill_template` | P0 | `backend/legal/engine/` | `DocumentRequest`, `RunResult`, `PropertyBundle`; template text passed in | `DocumentDraft`, `DocType` | `docreq`, `run`, `draft` | `pytest backend/legal/engine -q` with a three-line test template: a bound placeholder is filled from `RunResult`; an unbound one stays a visible blank and is listed in `unfilled_placeholders`; a value in `DocumentRequest.fields` wins over a derived one; no party name is produced that was not supplied; the notice is always present | `DocumentRequest`, `RunResult`, `PropertyBundle`, `Plan`, `MeasureResult`, `DocumentDraft`, `DocType`; fx `docreq`, `run`, `draft` |
| L2 | S9 Draft, template: California residential retrofit contract (`retrofit_contract_residential`, state `CA`) | P0 | `backend/legal/templates/ca/` | none | one template file | `docreq.house`, `draft.house` | `pytest backend/legal/templates/ca -q`: every placeholder in the template is in the legal spec's placeholder table; every required term in the California residential section of the legal spec has a clause carrying its id; no clause text is copied from a published form | `DocType`, `DocumentRequest`, `DocumentDraft`; fx `docreq`, `draft` |
| L3 | S9 Draft, statutory checks: `check_document` rules for the California residential retrofit contract | P0 | `backend/legal/checks/` | `DocumentDraft` | `StatutoryCheck` | `draft.house` | `pytest backend/legal/checks -q`: the fixture draft satisfies every rule; removing the cancellation clause from its markdown turns that check to `satisfied=false`; every check has a `citation` and, in `StatutoryCheck.requirement_id`, the id of the requirement in the state file | `DocumentDraft`, `StatutoryCheck`, `DocType`; fx `draft` |
| L4 | Templates, California: `retrofit_contract_commercial`, `solar_installation_agreement`, `bid_package_rfp`, `energy_savings_guarantee`. After L2 | P1 | `backend/legal/templates/ca/` | none | four template files | `docreq`, `draft` | `pytest backend/legal/templates/ca -q`: the L2 checks hold for each new template | `DocType`, `DocumentRequest`, `DocumentDraft`; fx `docreq`, `draft` |
| L5 | Templates, Texas: `retrofit_contract_residential`, `retrofit_contract_commercial`, `solar_installation_agreement`, `bid_package_rfp`, `energy_savings_guarantee` | P1 | `backend/legal/templates/tx/` | none | five template files | `docreq.office`, `draft.office` | `pytest backend/legal/templates/tx -q`: the L2 checks hold for each template against the Texas sections of the legal spec | `DocType`, `DocumentRequest`, `DocumentDraft`; fx `docreq`, `draft` |
| L6 | Templates: `cpace_package` for California and Texas, only for properties eligible under SPEC 6.6, tied to the SIR result | P1 | `backend/legal/templates/cpace/` | none | two template files | `docreq.office`, `draft.office`, `run.office#/plan` | `pytest backend/legal/templates/cpace -q`: the L2 checks hold; the plan's SIR placeholder is bound to `FinancialBreakdown.sir`, and the program's own savings test of SPEC 6.6 is a separate placeholder; the template metadata limits it to eligible properties | `DocType`, `DocumentRequest`, `DocumentDraft`, `FinancialBreakdown`, `FinancingScenario`; fx `docreq`, `draft`, `run` |
| L7 | Statutory checks for every P1 document in both states. After L3 | P1 | `backend/legal/checks/` | `DocumentDraft` | `StatutoryCheck` | `draft` | `pytest backend/legal/checks -q`: each `DocType` and state pair has at least one rule; every rule cites a section the legal spec lists as verified; a rule for a term the legal spec lists as unverified is reported with a `note`, not as satisfied | `DocumentDraft`, `StatutoryCheck`, `DocType`; fx `draft` |
| L8 | Document export to Word. Starts only after O12 is settled | P2 | `backend/legal/export/` | `DocumentDraft` | a `.docx` file | `draft` | `pytest backend/legal/export -q`: the exported file contains every heading of the markdown; blanks stay visible; the notice is on the first page | `DocumentDraft`; fx `draft` |
| L9 | Legal framework document: the structure of the documents, the clause library, and the placeholder table that binds every placeholder to a contract field. It cites the requirement ids of the two state files. A draft with the first document, the California residential retrofit contract, exists; that part is what L1 and L2 start from, and the other documents are added before L4 to L6 start | P0 | `specs/legal.md` | SPEC 9; the two state files | the file | none | Every placeholder is bound to a field of SPEC 9 or marked user-supplied; every clause that answers a statutory requirement carries that requirement's id from the state files; every `DocType` value has a document structure | `DocType`, `DocumentRequest`, `DocumentDraft`, `RunResult` |

### 4.5 Frontend, demo and submission lane (`F`), @vinayak-sinha

Reference: SPEC 11 (screens), SPEC 4 (flow), SPEC 15 (demo). The stack is the frontend owner's choice, so the folder names under `frontend/src/` are a proposal the owner may rename; the binding rule (one writer per screen folder) stays. `F0` defines the test command; below it is written `npm test`. "Mock mode" means the app reads `specs/examples/` and the server is off. Rules for every screen: every figure shows its range (expected with low to high); every number comes from the API; no calculation beyond unit display.

Precondition for this lane: `F0` is merged before any other `F` package starts. After that, `frontend/src/shared/` is read-only for screen agents and is changed only by the frontend owner.

| ID | Package | Tier | Bound to | In | Out | Fixture | Acceptance test | Depends on |
|---|---|---|---|---|---|---|---|---|
| F0 | Scaffold: stack, app shell and navigation between the eight screens with no page reload, typed API client for SPEC 10 with mock mode, event-stream client, shared range and unit display | P0 | `frontend/package.json`, `frontend/src/shared/` | every response type of SPEC 10 | none | `search`, `run`, `events`, `docreq`, `draft`, `bundle`, `model` | `npm test -- shared`: in mock mode every fixture loads with no console error; the range component shows expected with low to high; a `schema_version` from `GET /api/health` that differs from the client's shows a warning | `PropertySummary`, `RunRequest`, `RunEvent`, `RunResult`, `DocumentRequest`, `DocumentDraft`, `Ranged`; fx `search`, `run`, `events`, `docreq`, `draft`, `bundle`, `model` |
| F1 | Find screen: search box and result cards with segment, use type, city and the layers available | P0† | `frontend/src/find/` | `PropertySummary` | the chosen `sid` | `search` | `npm test -- find`: in mock mode the cards of `search` render with segment, use type, city and layer badges from the `PropertySummary` fields; choosing a card yields its `sid` | `PropertySummary`, `Segment`, `UseType`; fx `search` |
| F2 | Find screen: map of the two cities with result markers | P1† | `frontend/src/find_map/` | `PropertySummary` | the chosen `sid` | `search` | `npm test -- find_map`: every result with `lat` and `lon` gets a marker; a result without coordinates is skipped, not an error | `PropertySummary`; fx `search` |
| F3 | Set up screen: budget, role, optional twelve months of bills | P0† | `frontend/src/setup/` | `PropertySummary` | `RunRequest`, with `UtilityBills` when bills are entered | `run#/request` | `npm test -- setup`: the form output validates as a `RunRequest` (budget not negative, one of the three roles, bills either absent or twelve values) | `PropertySummary`, `RunRequest`, `Role`, `UtilityBills`; fx `run` |
| F4 | Audit screen: the agent's todo list and event stream beside the tour; question cards | P0 | `frontend/src/audit/` | `RunEvent`, `Question` | an answer `{question_id, value}` | `events` | `npm test -- audit`: replaying `events` shows the todo list changing, a fallback line, and one question card with its choices and "I don't know"; choosing one emits the body of `POST /api/runs/{run_id}/answers`; an unknown event type is ignored | `RunEvent`, `Question`, `Choice`; fx `events` |
| F5 | 3D tour: Matterport Showcase embed, a pin at each selected measure's `Anchor`, camera jump to the evidence panorama when a measure is clicked | P0 | `frontend/src/tour/` | `Anchor`, `EvidenceRef`; the `sid` | none | `run#/plan` | `npm test -- tour` with the SDK faked: each selected measure of the house fixture that has an anchor produces one pin call; clicking a measure produces a camera move to its evidence panorama. By hand with `MATTERPORT_SDK_KEY`: pins appear in the real tour, and the result of the sweep-id against pano-id check ([P] in SPEC 11) is posted on the board | `Anchor`, `EvidenceRef`, `MeasureResult`, `Plan`, `PropertySummary`; fx `run` |
| F6 | Plan screen: ranked measures inside the budget, financeable list, skipped list with reasons, totals, and beside the totals the value uplift when `Plan.value_uplift` is present (its range and number of comparables, kept apart from savings; SPEC 6.6); each measure expands to its financial breakdown, financing scenarios, ranges and evidence | P0 | `frontend/src/plan/` | `Plan`, `MeasureResult`, `FinancialBreakdown`, `ValueUplift` | the clicked measure id | `run#/plan` | `npm test -- plan`: both fixtures render in mock mode; every item of SPEC 6.6 appears in the expanded breakdown; every figure shows a range; each skipped item shows its reason; the office fixture shows the value uplift with its range and `comp_count`, the house fixture shows none, and it is part of no total; the component computes nothing | `Plan`, `PlanItem`, `SkippedItem`, `MeasureResult`, `FinancialBreakdown`, `FinancingScenario`, `Incentive`, `ValueUplift`, `Ranged`; fx `run` |
| F7 | Assumptions screen, read only: every assumption with source, range and evidence | P0† | `frontend/src/assumptions/` | `Assumption` | none | `model#/assumptions` | `npm test -- assumptions`: every assumption of both fixtures is listed with its source and range; text and yes-or-no values render without a range | `Assumption`, `EvidenceRef`, `Source`, `Ranged`; fx `model` |
| F8 | Adjust (SPEC 4 step 6): edit control on an assumption and on the budget, then re-run | P1† | `frontend/src/adjust/` | `Assumption`; the current budget | the body of `PATCH /api/runs/{run_id}` | `model`, `run` | `npm test -- adjust`: an edit emits a body whose `overrides` key is the assumption's `key`; an assumption with `user_editable=false` has no control; after the change the screen follows the new events | `Assumption`, `RunRequest`, `RunEvent`; fx `model`, `run` |
| F9 | Roof screen: Vexcel ortho with SAM 3 masks, roof planes and the panel layout. Needs O3 settled to go live | P1 | `frontend/src/roof/` | `SolarDesign`, `RoofPlane`, `VexcelData` | none | `bundle#/vexcel`, `model#/roof_planes`, `run#/measures` | `npm test -- roof`: in mock mode every panel polygon is drawn inside its plane over the ortho; with no detections the screen shows planes and panels only | `SolarDesign`, `PanelPlacement`, `RoofPlane`, `VexcelData`, `VexcelDetection`; fx `bundle`, `model`, `run` |
| F10 | Layout screen: floor plan with the desk score heat map and recommended positions. Needs O3 settled to go live | P1 | `frontend/src/layout/` | `LayoutResult`, `MatterportData` | none | `run.office#/measures`, `bundle.office#/matterport` | `npm test -- layout`: every candidate is drawn at its position coloured by `score`; recommended desks are marked; a floor plan without `origin_x` falls back to the wall graph | `LayoutResult`, `DeskScore`, `MatterportData`, `FloorplanAsset`, `Floor`, `Room`; fx `run`, `bundle` |
| F11 | Documents screen: pick the type, confirm the parties, preview with blanks highlighted and the statutory checklist, export | P0 | `frontend/src/documents/` | `RunResult`, `DocumentDraft` | `DocumentRequest` | `docreq`, `draft` | `npm test -- documents`: confirming the parties emits a valid `DocumentRequest`; every entry of `unfilled_placeholders` is highlighted in the preview; an unsatisfied check is marked; the notice is visible; export downloads the markdown | `RunResult`, `DocumentRequest`, `DocumentDraft`, `StatutoryCheck`, `DocType`, `MeasureId`; fx `docreq`, `draft` |
| F12 | Demo and submission: rehearse SPEC 15, record it, write and file the submission; confirm the submission deadline | P0 | `frontend/demo/` | `RunResult` for both golden properties | the recording and the submission text | `run` | By hand: the deadline is posted on the board; the steps of SPEC 15 whose features shipped run twice in a row from a cold start with no manual fix; steps whose features did not ship are removed from the script, not faked | `RunResult`; fx `run` |
| F13 | Word download on the Documents screen. After F11; starts only after O12 is settled | P2 | `frontend/src/documents/` | `DocumentDraft` | a file download | `draft` | `npm test -- documents`: the control appears only when the server offers the export; the download is the file the server returns | `DocumentDraft`; fx `draft` |

### 4.6 Contract and specs lane (`C`), @yalexie1

These are documents and the schema, not application features. All are P0 because every other package starts from them.

| ID | Package | Tier | Bound to | In | Out | Fixture | Acceptance test | Depends on |
|---|---|---|---|---|---|---|---|---|
| C1 | `backend/schema.py`: the code block between `contract:start` and `contract:end` in SPEC 9, unchanged | P0 | `backend/schema.py` | SPEC 9 | an importable module | none | `python -c "import backend.schema as s; print(s.SCHEMA_VERSION)"` prints the version in SPEC 9; every model builds a JSON schema; the file is identical to the SPEC block | none |
| C2 | Fixtures: the example payloads of 2.3 for the golden house and the golden office on contract 0.2.0, the README that says which values are real and which are illustrative, and the validator inside it. They exist; the package stays open to keep them valid: after every contract change the validator is run again and the files are updated | P0 | `specs/examples/README.md`, `specs/examples/search_results.json`, `specs/examples/house/`, `specs/examples/office/` | every contract type | the files of 2.3 | all | The examples validator (2.3) exits 0: every file validates against its type and its consistency checks pass. Every value the README does not list as real is illustrative. No sponsor record, kit file, API response or imagery is in the folder | every type in SPEC 9 |
| C3 | Settle the open contract items of 4.6.1 and the requests of 4.1.2 on the board, write the answers into SPEC, announce the freeze | P0 | `specs/SPEC.md`, `specs/workplan.md` | the board replies | SPEC with no open item that changes a type, route or signature | none | Each item O1 to O22 has an answer recorded in SPEC or in this file; each request R1 to R12 has a reply; `CONTRACT-CHANGE: frozen <version>` is posted | none |
| C4 | Root files: the `.gitignore` entry for `data/runs/` (`data/fixtures/` follows O8), `.env.example`, root `requirements.txt`, `backend/__init__.py`, `.github/CODEOWNERS` from 8.2 | P0 | `.gitignore`, `.env.example`, `requirements.txt`, `backend/__init__.py`, `.github/CODEOWNERS`, `README.md` | 1.1 and 8.2 | the root files | none | `git check-ignore data/runs/x data/cache/x .env` lists all three; `pip install -r requirements.txt` succeeds in a clean environment | none |
| C5 | Physics spec complete: every formula with sources and a worked example, default tables, key vocabularies, the value module SPEC 6.6 refers to, and the index file | P0 | `specs/physics.md`, `specs/physics/` | primary sources | the index and the four physics files | none | Every entry has a worked example recomputed by a script that was run; the unverified list and the verification log are filled; the index lists every section | none |
| C6 | Legal requirements complete: the required terms with citations for both states, each with an id that the legal framework and the statutory checks cite | P0 | `specs/legal/` | official code text | the two state files | none | Every requirement has an id and a citation that was re-opened; the unverified list is filled | none |

Two spec files are not in this lane. `specs/data-integration.md` is the Data lane owner's task `D11` (4.1); an earlier draft of this file listed it here under the id C7, which is withdrawn. `specs/legal.md` is the Legal lane's package `L9` (4.4).

#### 4.6.1 Open contract items for `C3`

Found while writing this plan. Each has a default that applies if the board has not decided by checkpoint 1.

| # | Item | Default |
|---|---|---|
| O1 | SPEC 6.1 says S3 outputs "observations with evidence", but SPEC 9 has no type for them | S3 returns `Assumption[]` and `Flag[]` (3.2); no new type |
| O2 | SPEC 8 names the tools but gives no arguments or results. `sensitivity`, `get_asset`, `set_assumption` and `detect_roof_elements` have no stage in SPEC 6.1. `detect_roof_elements` is a Vexcel network call listed under an analysis-side agent, while SPEC 14 requires analysis functions to run with no network. The Data lane's door has three functions (`.claude/agents/data-api.md`); this file needs two more | Signatures of section 3; `detect_roof_elements` and `get_property_summary` are data-lane door functions once the Data lane agrees (R3) |
| O3 | SPEC 11 gives `VexcelData` and `MatterportData` as data for the Roof and Layout screens, but no route in SPEC 10 returns a `PropertyBundle` and `RunResult` does not carry one | Add one additive route that returns the run's `PropertyBundle`; until it exists `F9` and `F10` work in mock mode only |
| O4 | `RunEvent.payload` is an untyped `dict` and `RunEvent.stage` has no list of values, so server and frontend can drift | The shapes in the `events` fixture are binding; `stage` uses the ids `S1` to `S9` of SPEC 6.1 |
| O5 | SPEC 13 gives no tier for: S3 panorama reading other than electrical feasibility; splat roof fitting; the Find, Set up, Audit, Assumptions and Documents screens; the map; the Adjust step and `PATCH`; and the two v0.2 additions, office occupancy from CoStar tenancies (SPEC 5.1) and value uplift (SPEC 6.6) | The tiers marked † in section 4. Value uplift is P2† (`A30`) because its data arrives with the Data lane's `D10`, which is P2 there. Occupancy has no package of its own: the P0 packages `A10`, `A2` and `A3` use it when the bundle has it (R9) |
| O6 | SPEC 13 says "one document (California retrofit contract)" but `DocType` has a residential and a commercial retrofit contract; SPEC 1 and 13 say five documents and `DocType` has six values | P0 is `retrofit_contract_residential`, state `CA`, drafted for the golden house; "five documents" counts the retrofit contract once |
| O7 | SPEC 7 allows imports of `backend/schema.py` and other lanes' `api.py` only, but SPEC 8 and 12 have the agent lane read model ids and `ASK_MAX` from `backend/config.py` | `backend/config.py` holds constants only and is treated as part of the contract (2.2) |
| O8 | Data spec 6.4 lists `data/fixtures/` as committed golden-property payloads. SPEC 3.6 and 14 and the hard rules of the Data agent definitions say sponsor data is never committed, and the repository is public. Runs under `data/runs/` are also derived from sponsor data and are not git-ignored yet | `C4` adds `data/runs/` to `.gitignore`. The rule of 2.3 holds for `data/fixtures/` as for every folder: no sponsor record, kit file, API response or imagery is committed. A golden payload that is a reader's output from such data stays out of git until @vigjay states on the board what the licence allows (R1); until then each teammate regenerates it with their own keys |
| O9 | `ClimateSite.weather_path` points to a file whose format is not defined anywhere yet; data spec 5 names the sources but no file format | The weather sample of 2.3, once `A1` has written it, is the reference format until data spec section 5 defines one (R2) |
| O10 | Assumption keys, flag keys, `end_use_kwh` keys and `occupancy_schedule` keys are strings shared by three lanes with no list in SPEC | The physics spec lists them; after the freeze a new key is an additive contract change |
| O11 | SPEC 6.5: the pseudocode orders the whole pool by annual savings, while the rule below it says zero-cost measures are always evaluated first | Zero-cost measures with positive savings are applied first, in order of savings; then the loop runs as written |
| O12 | The P2 items portfolio screening and Word export have no type, route or screen in SPEC 9 to 11, and "retrofit return" has no stated measure. The data spec has no package for the data side of portfolio screening (R10) | `G13`, `L8` and `F13` do not start until a contract change defines them |
| O13 | SPEC names `physics.md` and `legal.md`. The physics text is in four files under `specs/physics/` and the statutory text in two files under `specs/legal/`. Of the two files SPEC's names point to, the legal framework `specs/legal.md` exists as a draft with its first document, and the physics index `specs/physics.md` is not written yet | `C5` writes the physics index and `L9` completes the legal framework; SPEC keeps its names |
| O14 | SPEC 13 P0 says "`HVAC_HP` or `HVAC_RTU`"; SPEC 6.2 offers the first to homes only and the second to offices only, and P0 needs one house and one office | Both are P0 (`A18`) |
| O15 | SPEC 15 demo steps 4 to 6 use the roof view with panel layout, the budget re-rank, the desk layout and the C-PACE view, which are P1 or have no tier | `F12` cuts the script to what shipped (checkpoint 4) |
| O16 | `AGENTS.md` does not name the team lead and its mention list still has placeholders | The team names the lead on the board; the lead fills in `AGENTS.md` |
| O17 | SPEC 16 gives the risk "georeference missing or wrong on a model" to "Data + Analysis" | Data delivers the field as returned (`D2`). Analysis owns the conversion to `BuildingModel.north_offset_deg`, the cross-check against the footprint and the fallback (`A9`) |
| O18 | Data spec 2.6 names the golden properties: the house is Matterport model `zvKHR9DHNjJ` in Los Angeles; the office is CoStar property 354635 in Houston, which has three models. Not yet stated: which of the three is the office `sid`, and whether the house has an aerial splat, as SPEC 13 P0 says | The Data lane confirms both (R5). Until then the office `sid` in fixtures is `HjEyXryhRLk`, the model the data spec uses for the office's georeference and lot |
| O19 | `AGENTS.md` lists all of `specs/` under @yalexie1 and has no row for `backend/legal/`. Agreed on the board since: the data spec is @vigjay's; `backend/legal/` and `specs/legal.md` are @Sri-SriPod's. The Data lane also added `.claude/agents/data-*.md` and `.claude/commands/data-*.md`; who owns `.claude/agents/` is open (data spec 7), and 2.5 treats the rest of `.claude/` as the untouched board template | 1.1 and 8.2 of this file. The `data-*` files under `.claude/` are the Data lane's; hooks and `settings.json` stay untouched. The lead updates the owner table in `AGENTS.md` |
| O20 | `PropertyBundle.climate` and `PropertyBundle.tariff` are required fields and P0 analysis packages read them. The Data lane delivers external data in `D9`, which is P1 and which it reports as done on the strength of its source checks (data spec 5); `external.py` is not written, and Houston has no tariff source | For the two golden sites both are delivered by checkpoint 3 (R2). Until then the `bundle` fixtures stand in, and office dollar savings in Houston are illustrative |
| O21 | The Data agent definitions expect things contract 0.2.0 does not have: more fetch outcomes than the five values of `FetchRecord.status`; which model a bundle used when one property has several, and the alternatives; the unit-or-building distinction of SPEC 3.5; a confidence flag on the roof height; typed Vexcel fields where `VexcelStructure.attributes` is a flat map | Each is carried in `FetchRecord.what`, `FetchRecord.detail` or `VexcelStructure.attributes` until the Data lane posts a `CONTRACT-CHANGE:` and it lands |
| O22 | Vexcel counts no rooftop AC unit on the golden office (data spec 4.5, SPEC 16), but `HVAC_RTU` is the P0 office HVAC measure (O14) | The fallback of SPEC 16: the HVAC type comes from interior vision (`A7`, through the registry of `A10`) and the measure that matches it is evaluated. The team decides on the board whether to pick another golden office instead |

## 5. Sub-lanes: running several agents per person

### 5.1 The principle

Two packages can run at the same time if their **Bound to** paths differ. Packages that share a path run in ID order. So each person's lane splits into the sub-lanes below; give each sub-lane to one agent, or give one agent several sub-lanes in turn. Start every lane with its scaffold package (`A0`, `G0`, `L0`, `F0`; in the Data lane the door package `D5`, which first returns fixture data): it creates the door stubs that the other packages and the other lanes assume.

### 5.2 Sub-lanes per person

P1 and P2 packages are in brackets: start them only when the P0 packages of the lane are assigned.

**@vigjay, data.** At most three agents making live calls at the same time, one per working key set (data spec 6.2; the limit is the rate limit of the shared keys). The sub-lanes are the Data lane's own sub-agents (data spec 6.1, `.claude/agents/data-*.md`). Start one with `/data-wp <ID>`.

| Sub-lane | Paths | Packages, in order |
|---|---|---|
| `data-costar` | `backend/data_layer/costar.py`, `data/fixtures/costar/`, `backend/data_layer/index.py`, `backend/data_layer/external.py`, `backend/data_layer/costar_extra.py` | D1, [D7], [D9], [D10] |
| `data-matterport` | `backend/data_layer/matterport.py`, `data/fixtures/matterport/` | D2 |
| `data-vexcel` | `backend/data_layer/vexcel.py`, `data/fixtures/vexcel/`, `backend/data_layer/imagery.py` | D3, [D8] |
| `data-cache` | `backend/data_layer/cache.py` | D4 |
| `data-api` | `backend/data_layer/api.py` | D5 |
| the three source agents, each in its own fixture folder | the three fixture folders above | D6 |
| lane owner | `specs/data-integration.md` | D0, D11 |

Order: `D0`, then `D1`, `D2` and `D3` in parallel, then `D5`, then `D6`; `D4` can start as a stub; `D7` to `D10` only after the walking skeleton.

**@yalexie1, analysis and contract.** Up to eight agents. This lane has the most P0 packages (19) and sits on the critical path of checkpoint 3; if it falls behind, the lead decides whether another person's idle agents take analysis sub-lanes (a `HANDOFF-REQUEST:` is still needed).

| Sub-lane | Paths | Packages, in order |
|---|---|---|
| contract | `backend/schema.py`, `specs/` (not the data spec, not `specs/legal.md`), root files | C1, C2, C4, C3, with C5 and C6 alongside |
| door | `backend/analysis/api.py`, `backend/config.py` | A0, A29 |
| climate and PV | `backend/analysis/physics/climate/`, `specs/examples/weather/`, `physics/pv/`, `physics/daylight/` | A1, A4, [A5] |
| zone | `backend/analysis/physics/zone/` | A2 |
| systems | `backend/analysis/physics/systems/`, `physics/calibration/` | A3, [A6] |
| model and vision | `backend/analysis/model/geometry/`, `model/registry/`, `vision/` | A9, A10, A7, [A8] |
| solar | `backend/analysis/solar/roof/`, `solar/layout/`, `solar/splat/`, `solar/shading/` | A11, A14, [A12], [A13], [A15] |
| measures | `backend/analysis/measures/engine/`, `envelope/`, `systems/`, `pv/`, `walls_windows/`, `hvac_dhw/`, `controls/`, `backend/analysis/layout/` | A16, A17, A18, A19, [A20], [A21], [A22], [A23] |
| finance | `backend/analysis/finance/costs/`, `economics/`, `plan/`, `sensitivity/`, `specs/examples/ask/`, `cpace/`, `value/` | A24, A25, A26, A27, [A28], [A30] |

Every package inside a sub-lane except the door has its own folder, so a sub-lane can itself be split further: for example `A9`, `A10` and `A7` can go to three agents.

**@Sri-SriPod, agent, server and legal.** Up to six agents.

| Sub-lane | Paths | Packages, in order |
|---|---|---|
| run door and runtime | `backend/agent/api.py`, `backend/agent/runtime/`, `data/runs/` | G0, G5 |
| tools | `backend/agent/tools/` | G1 |
| graph | `backend/agent/graph/`, `backend/agent/portfolio/` | G2, G6, [G12], [G13] |
| ask and narrative | `backend/agent/ask/`, `backend/agent/narrative/` | G3, G4 |
| server | `backend/server.py`, `backend/agent/server/` | G7, G8, G9, G10, [G11] |
| legal | `specs/legal.md`, `backend/legal/api.py`, `engine/`, `templates/`, `checks/`, `export/` | L9, L0, L1, L2, L3, [L4], [L5], [L6], [L7], [L8] |

`G11` also writes `backend/agent/runtime/`; it starts only after `G5` is merged. Inside legal, `engine/`, `templates/ca/`, `templates/tx/`, `templates/cpace/` and `checks/` are separate folders, so `L1`, `L2` and `L3` can go to three agents. `L9` is a document: it can be written while `L0` is built, and `L1` and `L2` start from it.

**@vinayak-sinha, frontend.** Up to five agents, after `F0` is merged.

| Sub-lane | Paths | Packages, in order |
|---|---|---|
| shell | `frontend/package.json`, `frontend/src/shared/`, `frontend/demo/` | F0, F12 |
| find and set up | `frontend/src/find/`, `setup/`, `find_map/` | F1, F3, [F2] |
| audit and tour | `frontend/src/audit/`, `tour/` | F4, F5 |
| plan and assumptions | `frontend/src/plan/`, `assumptions/`, `adjust/` | F6, F7, [F8] |
| documents and views | `frontend/src/documents/`, `roof/`, `layout/` | F11, [F9], [F10], [F13] |

### 5.3 Branches and worktrees

One issue per package, one branch per issue, one worktree per agent (2.8). Examples:

```bash
# issue 23 is "A2 Zone loads"
git fetch origin
git worktree add ../hp-23 -b 23-a2-zone-loads origin/main

# issue 31 is "G7 Server skeleton"
git worktree add ../hp-31 -b 31-g7-server-skeleton origin/main
```

### 5.4 Kickoff prompt template

Paste this to start an agent on one package. Fill in the four values in angle brackets. Data lane packages are started with `/data-wp <ID>` instead, which carries the same boundaries (data spec 6.2).

```text
You are building work package <ID> for the HackPrinceton energy consultant project.
Your GitHub issue is #<issue number>. Your branch is <issue number>-<slug>, in its own worktree.

Read these first, fully, in this order:
1. AGENTS.md (team rules and the board tool).
2. specs/SPEC.md section 9 (the shared contract). It is frozen: do not change it.
3. specs/workplan.md section 2 (rules) and the row for <ID> in section 4.
4. The reference spec named at the top of your lane's table, only the parts your row cites.

Then build exactly what the row says:
- Write only inside the "Bound to" path: <bound path>. Do not create or edit any file
  outside it. Not backend/schema.py, not any api.py you do not own, not a requirements
  file, not a root file, not specs/ (unless your row binds a path there).
- Import only: the standard library, packages already in your lane's dependencies file,
  backend/schema.py, backend/config.py, and files in your own folder. Never import a
  sibling folder or another lane's internals. If you need another package's result, take
  it as a function argument and pass a fake in your tests.
- Inputs and outputs are the contract types in the row. Test against the fixtures the row
  names, in specs/examples/. Tests go in <bound path>tests/ and must pass with no network
  and no other lane running.
- Done means the acceptance test in the row passes and section 8.1 of specs/workplan.md
  holds.

If you need a new dependency, a contract change, or a file outside your path: stop that
part, say so in your report, and post on the board with tools/board using the post types
in specs/workplan.md section 6. Do not work around it by editing someone else's file.

Start every board post with [<your human's name>'s <agent name>]. Run tools/board unread
before you start and before each commit. Stage files by path; never git add -A. Do not
force-push. When finished, open a PR with "Closes #<issue number>" and report: files
written, the test command and its result, and anything you could not finish.
```

## 6. Board protocol

These post types sit on top of the board rules in `AGENTS.md` section 1. The type word comes right after the name tag. Mention people by GitHub login.

The Data lane lists the same five types in data spec 6.3. This section is the definition for every lane, because it also says who must respond and by when. Two habits from the data spec are taken over here for everyone: post `INTERFACE-LIVE:` as soon as the signatures return fixture data, and name the contract type in a `BLOCKED:` post.

### 6.1 Post types

| Type | Post it when | Who must respond |
|---|---|---|
| `CONTRACT-CHANGE:` | you need a change to anything listed in 2.1, or the contract owner has landed or frozen one | Every affected owner replies `ACK` or objects, within 30 minutes. The contract owner (@yalexie1) makes the edit and posts when it lands. |
| `FIXTURE-READY:` | a fixture in `specs/examples/` or a golden payload in `data/fixtures/` is on `main` or ready to regenerate | Nobody replies. Consumers switch to it. Reply only if it fails your tests, with `BLOCKED:`. |
| `INTERFACE-LIVE:` | a door function is on `main`, as a stub or as the real thing; say which. Post the stub as soon as its signature returns fixture data, before live fetches work | Nobody replies. Consumers re-run their tests against it and post `BLOCKED:` if they fail. |
| `BLOCKED:` | you cannot continue a package because of something another lane owns; name the contract type or the file | The mentioned owner, or their agent, within 15 minutes: a fix, a time, or a workaround. With no reply after 30 minutes, the lead decides. |
| `HANDOFF-REQUEST:` | you need to edit a file in someone else's path | The file's owner or the lead says yes or no. You do not touch the file until one of them says yes. |

### 6.2 Examples

```text
[Sri's Codex] CONTRACT-CHANGE: request, additive. Add `approval_needed` to the literal
RunEvent.type so the Documents screen can show the approval card. Affects @vinayak-sinha
(frontend) and me. Until it lands I send type "question" with payload.kind = "approval".
@yalexie1 @vinayak-sinha please ACK.

[Yale's Claude] CONTRACT-CHANGE: landed 0.2.1. RunEvent.type gains "approval_needed".
schema.py, SPEC 9 and house/run_events.json updated; the examples validator passes.
Rebase on main.

[Yale's Claude] FIXTURE-READY: specs/examples/ on main. All files of workplan 2.3 for
house and office; the examples validator passes on schema 0.2.0. @all build against these.

[Vignesha's Claude] FIXTURE-READY: data/fixtures/matterport/ for both golden models
(house zvKHR9DHNjJ, office <sid>), shaped as MatterportData, with georeference and
openings. Replays with the network off.

[Vignesha's Claude] INTERFACE-LIVE: stub data_layer.api on main (D5). The three door
functions return fixture data for both golden properties. Live fetches are not wired
yet; roof detections come with D8, which is P1.

[Vinayak's Claude] BLOCKED: F5 tour pins. Anchor.pano_id values in
house/run_result.json do not match any sweep id the Showcase SDK reports for that model.
@vigjay are Model API pano ids and SDK sweep ids the same thing? I continue with room
anchors meanwhile.

[Sri's Codex] HANDOFF-REQUEST: @yalexie1 backend/config.py. I need the constant
CHECKPOINT_DIR next to ASK_MAX. One line, no other change. May I add it, or will you?
```

## 7. Integration checkpoints

`T` is the submission deadline. The frontend owner confirms it (SPEC 16) and posts it; from then on the lead posts each checkpoint as a clock time. The offsets below assume about 32 hours of build time remain when the deadline is confirmed. With less, the lead scales the four offsets by the same factor and posts the new times.

A missed checkpoint is not moved. The cut in the last column happens, the lead posts it, and work continues.

| # | Checkpoint | When | What must be true | Who checks | If missed |
|---|---|---|---|---|---|
| 1 | Schema freeze | T-30 h | `C1` and `C2` merged: `backend/schema.py` imports and the examples validator (2.3) passes. `C4` merged. Every open item O1 to O22 has an answer or takes its default, and every request R1 to R12 has a reply or a date for one. The five door stubs are merged (`D5` returning fixture data, `A0`, `G0`, `L0`, `F0`) and each has posted `INTERFACE-LIVE: stub`. The golden office `sid` is confirmed (R5). | @yalexie1 runs the validator and posts `CONTRACT-CHANGE: frozen <version>` | No P2 package is started for the rest of the event. Open items take the defaults of 4.6.1 with no further discussion. The freeze is declared on whatever loads. |
| 2 | Walking skeleton on fixtures | T-22 h | With every door still a stub: `POST /api/runs` for the house fixture streams events to `done`, `GET /api/runs/{run_id}` returns a valid `RunResult`, a document request returns a draft (`G7`, `G0`). The frontend, pointed at that server, goes Find, Set up, Audit, Plan, Documents with no page reload (`F0` and at least a first pass of `F1`, `F3`, `F4`, `F6`, `F11`). | @Sri-SriPod runs the server check; @vinayak-sinha confirms from the browser; both post | P2 is dropped entirely. No P1 package starts until the skeleton is green. Each owner puts one agent on whatever part of the skeleton is missing. |
| 3 | Live data on the two golden properties | T-12 h | SPEC 14 holds for the P0 scope. Data: `get_property_bundle` real for both `sid` values, each layer present or explained by a `FetchRecord`, second call from cache (`D1` to `D6`), with a real weather file and a tariff for both sites (R2). Analysis: real door functions, plan reproduces exactly on re-run (`A29`). Agent: a run on each golden property completes with no manual step and its narrative passes `check_narrative`; the ask rule fires on the wide fixture and not on the narrow one (`G1` to `G6`, `G9`). Frontend: the run is driven from Find to Documents against the live server, pins appear in the tour (`F5`), one California retrofit contract is drafted (`L1` to `L3`, `G10`, `F11`). | @vigjay checks the bundles, @yalexie1 the plan, @Sri-SriPod the run; @vinayak-sinha drives it once in the browser and posts the result | Every P1 package not yet merged is cut; its PR is closed or parked. If one golden property still fails, that flow is shown from its payloads in `data/fixtures/` and the other runs live; the submission says which. The lead decides any further reduction inside P0. |
| 4 | Feature freeze, then demo rehearsal | freeze at T-5 h, rehearsal at T-3 h, submission filed by T-1 h | At the freeze: `main` is green (every merged package's acceptance test passes) and the SPEC 14 criteria hold. After the freeze only fixes for bugs that break the demo are merged, each approved by the lead. At the rehearsal: `F12` passes, meaning the shipped steps of SPEC 15 run twice in a row from a cold start. | @vinayak-sinha runs the rehearsal and posts; each owner confirms their lane's tests on `main` | Anything not merged is cut, whatever its tier. The demo runs from the last green commit. Demo steps whose features did not ship are removed from the script; any P0 item that did not ship is stated in the submission. |

## 8. Definition of done and code owners

### 8.1 A package is done when all of these hold

1. The acceptance test in its row passes, run from the repo root, with no network and no other lane running. Any `live:` or "by hand" line in the row has been run once and its result is in the PR.
2. Every file in the PR is inside the package's **Bound to** path. `git diff --name-only origin/main` shows nothing else.
3. It imports only what 2.2 allows. No import of a sibling subfolder or of another lane's internals.
4. Inputs and outputs are the contract types in the row, and an output written to JSON validates against `backend/schema.py`.
5. Results are deterministic: the same input gives the same output twice.
6. Physical quantities are SI and money is USD (SPEC 7). No number is invented: an unknown is a `Ranged` with a source, a blank, or a `FetchRecord`.
7. For analysis packages: each formula used is named in `formula_ids` and tested against its worked example. For legal packages: every draft has the notice and lists its blanks.
8. No secret is in the diff, and no sponsor record, kit file, API response or imagery (2.3). `git status` shows nothing under `data/cache/` or `data/runs/`; what may be committed under `data/fixtures/` follows O8.
9. Any new dependency is named in the PR description, not added to a file the package does not own.
10. The PR says `Closes #N`, is rebased on fresh `main`, and is merged by its author (`AGENTS.md` section 3). If it merged into a branch other than `main`, the author has closed the issue by hand (2.8).
11. If the package brings a door function or a fixture to `main`, `INTERFACE-LIVE:` or `FIXTURE-READY:` is posted.

### 8.2 Proposed `CODEOWNERS`

Not created by this plan. Package `C4` adds it as `.github/CODEOWNERS` once the team confirms the paths still marked proposed in 1.1. It mirrors the table in 1.1. In this file format the last matching line wins, so the default comes first.

```text
# Default: root files and anything not listed below (contract owner)
*                         @yalexie1

# Data lane
/backend/data_layer/      @vigjay
/data/fixtures/           @vigjay
/data/cache/              @vigjay

# Analysis lane
/backend/analysis/        @yalexie1
/backend/config.py        @yalexie1

# Agent and server lane
/backend/agent/           @Sri-SriPod
/backend/server.py        @Sri-SriPod
/data/runs/               @Sri-SriPod

# Legal drafting lane
/backend/legal/           @Sri-SriPod

# Frontend, demo, submission
/frontend/                @vinayak-sinha

# Contract and specs
/backend/schema.py        @yalexie1
/specs/                   @yalexie1

# Single files inside folders owned above. They come last so that they win.
/specs/data-integration.md      @vigjay
/specs/legal.md                 @Sri-SriPod
/.claude/agents/data-*.md       @vigjay
/.claude/commands/data-*.md     @vigjay
```

`data/cache/` is git-ignored, and `data/runs/` will be after `C4`, so their lines only record ownership. What is tracked under `data/fixtures/` follows O8.

## 9. Self-check

Performed on 2026-11-14 on this file as it stands, by a script kept outside the repository. The script reads only. It parses, in this file, the tables of sections 1.1, 2.3, 3.4, 4, 4.1.2, 4.6.1, 5.2, 9.1 and 9.2 and the code blocks of 3.1 to 3.3 and 8.2; in `specs/SPEC.md`, the tables of sections 6.1, 6.2, 8, 10, 11 and 13 and the contract block of section 9, which it executes under Pydantic 2; and the package table of data spec 6.1. Tables 9.1 and 9.2 are inputs to the check as well as part of its record: the script verifies them against SPEC and against section 4.

### 9.1 P0 items of SPEC 13 and the packages that cover them

The items are the P0 row of SPEC 13, split at its semicolons.

| P0 item of SPEC 13 | Packages |
|---|---|
| two golden properties (one house with a splat, one office; ids in `data-integration.md` section 2.6) end to end on live data | `D1`, `D2`, `D3`, `D5`, `D6`, `G2`, `G5`, `G9`, `F12` |
| all three layers in the bundle | `D1`, `D2`, `D3`, `D4`, `D5` |
| building model with assumption registry | `A9`, `A10` |
| hourly baseline | `A1`, `A2`, `A3` |
| measures `ENV_ATTIC`, `ENV_AIRSEAL`, `LGT_LED`, `HVAC_HP` or `HVAC_RTU`, `ROOF_COOL`, `PV_ROOF` on a parametric roof | `A16`, `A17`, `A18`, `A19`, `A4`, `A11`, `A14` |
| budget plan with full financial breakdown | `A24`, `A25`, `A26` |
| deep agent with subagents and the ask rule | `G1`, `G2`, `G3`, `A27` |
| plan screen and 3D tour with pins | `F6`, `F5` |
| one document (California retrofit contract) | `L9`, `L1`, `L2`, `L3`, `C6`, `G6`, `G10`, `F11` |

### 9.2 Contract types that no package outputs

| Type no package outputs | Why |
|---|---|
| `Source`, `Segment`, `UseType`, `MeasureId`, `Role` | fixed lists of values, defined by the contract itself (`C1`); packages use them and none produces them |

### 9.3 Results

The output of the last run, unedited. 17 of 18 checks pass; check 18 fails with five findings, explained below the output.

Inputs: `specs/SPEC.md` sha256 13d44a007475, `specs/data-integration.md` sha256 99bed0b37afe.

| # | Check | Items | Result |
|---|---|---|---|
| 1 | Contract block of SPEC 9 loads under Pydantic 2 and every model builds a JSON schema (SCHEMA_VERSION 0.2.0: 55 models, 6 literal aliases) | 61 | pass |
| 2 | Package ids are unique | 87 | pass |
| 3 | Every work package has all nine columns filled, a valid id and tier, and sits in its own lane's table (85 packages; the 2 owner tasks have their four columns filled) | 87 | pass |
| 4 | No path is owned by two owners: no path is listed under two lanes in 1.1, and every package's bound path resolves, by the most specific path of 1.1, to its own lane's owner (18 lane paths, 111 bound paths, 92 distinct) | 111 | pass |
| 5 | The proposed CODEOWNERS block of 8.2 (17 rules, last match wins) gives every lane path, bound path and root file the same owner as 1.1 | 116 | pass |
| 6 | Inside a lane, a path bound by more than one package is never bound across lanes, and every later package states its order with 'after' (13 shared paths); no bound path lies inside another package's bound folder | 92 | pass |
| 7 | Every dependency is a type that exists in the contract block of SPEC 9 or a fixture alias of 2.3, and no 'Depends on' cell names a package | 520 | pass |
| 8 | Every type named in an In or Out cell exists in the contract, and every fixture named is an alias of 2.3 | 344 | pass |
| 9 | Every `Type.field` reference names a real field of the contract; each of the 7 new types and 10 new fields of contract 0.2.0, and 5 of the fields added to it since, is used in sections 1 to 8; no retired name remains there (the old listing-id join key, the model index file, schema versions 0.1.x) | 110 | pass |
| 10 | Every contract type is named in the Out cell of at least one package (56 types) or is listed in 9.2 as a type no package outputs (5 types) | 61 | pass |
| 11 | Every P0 item of SPEC 13 (9 items, split at semicolons) has a row in 9.1 with at least one package, all of them P0; each of the 7 measures the P0 row names is in a P0 package | 9 | pass |
| 12 | Every MeasureId (18, equal to the rows of SPEC 6.2) is named in the Package cell of an analysis package | 18 | pass |
| 13 | Every stage of SPEC 6.1 (9), agent (6) and tool (20) of SPEC 8, route of SPEC 10 (11) and screen of SPEC 11 (8) is named in a package; every tool is in 3.4 and its door call is defined in 3.1 to 3.3 | 54 | pass |
| 14 | Every package and owner task is in exactly one sub-lane of 5.2; P1 and P2 packages are in brackets there and P0 packages are not | 87 | pass |
| 15 | The Data lane table of 4.1 agrees with the table of data spec 6.1: same ids, tiers, package names, owned paths and sub-agents, and every contract type the data spec gives as output is in Out | 12 | pass |
| 16 | Open items are O1 to O22 and requests R1 to R12, numbered without gaps; every O, R and package id referenced in the text exists; 7 counts stated in prose match the tables | 41 | pass |
| 17 | Every fixture file that 2.3 describes as existing is on disk under specs/examples/, the two it describes as not written yet are absent, and the README has the validator section | 31 | pass |
| 18 | No package depends on a type whose only producers are in a lower tier than itself | 385 | FAIL (5) |

Packages per lane and tier:

| Lane | P0 | P1 | P2 | Total |
|---|---|---|---|---|
| `D` Data | 6 | 3 | 1 | 10 |
| `A` Analysis | 19 | 10 | 2 | 31 |
| `G` Agent and server | 11 | 1 | 2 | 14 |
| `L` Legal drafting | 5 | 4 | 1 | 10 |
| `F` Frontend, demo, submission | 9 | 4 | 1 | 14 |
| `C` Contract and specs | 6 | 0 | 0 | 6 |
| All | 56 | 22 | 7 | 85 |

Tiers inferred by this file (†): 9 packages: A7, A13, A30, G11, F1, F2, F3, F7, F8. Owner tasks outside the tiers: D0, D11.

Note: Single paths carved out of a folder with another owner, each listed explicitly in 1.1: specs/data-integration.md (@vigjay) inside specs/ (@yalexie1); specs/legal.md (@Sri-SriPod) inside specs/ (@yalexie1).

Failures:

- Check 18: `ClimateSite` (required field of PropertyBundle): output only by D9 (P1), depended on by higher-tier D5, A1, A10
- Check 18: `OccupancyData` (optional or list field): output only by D10 (P2), depended on by higher-tier A10
- Check 18: `Tariff` (required field of PropertyBundle): output only by D9 (P1), depended on by higher-tier D5, A3, A19, A25
- Check 18: `Tenancy` (optional or list field): output only by D10 (P2), depended on by higher-tier A10
- Check 18: `ValueUplift` (optional or list field): output only by A30 (P2†), depended on by higher-tier A26, A29, F6

**What still fails, and why.** The five findings of check 18 are of two kinds.

- `ClimateSite` and `Tariff` are required fields of `PropertyBundle`, and P0 packages read them, but the only package that outputs them is the Data lane's `D9`, which is P1. This file cannot change another lane's tier. It is request R2 and open item O20. Until it is settled, checkpoint 3 cannot be met for the baseline.
- `OccupancyData`, `Tenancy` and `ValueUplift` are optional fields. The P0 packages that name them (`A10`, `A26`, `A29`, `F6`) work without them, and each of their acceptance tests covers the empty case. Their sources are P2 (`D10`, `A30`) by the decisions recorded in O5 and R9. They stay listed so the lead sees them when deciding whether `D10` moves up.

**How far the check can be trusted.** The script was also run on twelve copies of this file, each broken in one way: a duplicate id, a dependency on a package, an unknown type, a path under another owner, a wrong field name, an empty cell, a dropped measure, a wrong line in the CODEOWNERS block, a P0 package moved to P1, a Data tier that differs from the data spec, a dropped route, and the retired join key. It reported every one.

**What the check does not cover.** It does not judge whether an acceptance test is adequate or whether a package fits in two to four hours. It does not run the examples validator. It compares the Data lane with the table of data spec 6.1 only, not with the agent definitions that the acceptance summaries of `D1` to `D5` are taken from. It reads `specs/SPEC.md` and the data spec as they were at the time of the run (the hashes are in the first line of the output); both files were still changing on 2026-11-14, so the check must be run again after the next change to either.

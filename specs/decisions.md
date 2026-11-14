# Decision log

One line per decision the team made, newest first. Each row says who decided, what, and where it now lives (spec section, PR or board post on the pinned issue #1). The lead (@yalexie1) decides; a decision changes only by a new row that names the one it replaces. Owner: @yalexie1 (`specs/`).

Status: **in force**, **pending** (decided, not yet implemented), **proposed** (not yet decided), **superseded** (by the row named).

## Product principle

| Date | Decision | Where | Status |
|---|---|---|---|
| 2026-11-14 | **The product is meant to replace an energy consultant: accuracy to real-life results and conclusions comes first.** When a rule in the specs gives a result a consultant would not give, the rule changes. | this file; board | in force |

## Analysis and plan

| Date | Decision | Where | Status |
|---|---|---|---|
| 2026-11-14 | **Plan rule follows consultant practice** (loading order: operational and zero-cost first, then efficiency, then generation; rank by cost-effectiveness; a measure must have SIR ≥ 1 to be recommended; solar sized last against the load left). Replaces "rank by annual dollar savings; solar sized to the budget left". | SPEC 6.5 and contract 0.3.4 (`not_cost_effective`) (#279); implementation in `finance/plan/` and `api._design` (Srihaan, A26), then the examples are regenerated | pending (code) |
| 2026-11-14 | **Calibration reaches the plan (contract 0.3.5)**: new door `calibrate_model(bundle, model, bills) -> BuildingModel`, called before `run_baseline` whenever bills are given, and its model used for every later step; `CalibrationSummary` on the model and the baseline; `UtilityBills.first_month`. A6 itself is merged (#290). | #292 | pending (wiring, Srihaan) |
| 2026-11-14 | **Real-world benchmark checks**: each baseline's energy use intensity against CBECS 2018 (offices) or RECS 2020 (homes) for its type and climate, and solar yield against PVGIS; out-of-range results are warnings, never silent. | #285, #294; wiring in `api.py` (Srihaan) | in force (code); wiring pending |
| 2026-11-14 | **The electricity price always carries its market range** (TAR-06, data-integration 5.1c), applied relative to the tariff's own price; and **solar is priced with PV-07 degradation (0.5 %/yr) and the A4 inverter and losses**, never as an array that does not degrade. | #286, #291 | in force |
| 2026-11-14 | **Build A6 bill calibration now.** With bills, calibrate the baseline within each assumption's range to physics 04 MV-04 (monthly NMBE ±5 %, CV(RMSE) ≤ 15 %); without bills, results say they are uncalibrated. | #276, #290, physics 04 MV-06 | in force (code); wiring pending |
| 2026-11-14 | **Roof: the floor plate decides the building and the extent.** Design roof = structure containing the CoStar address point; disagreements broken by `building_area_m2 / stories`; georeference as fallback; tower over podium designs on the tower; a larger outline is a `PV_ROOF` warning, never the design roof. Designing on the podium is not supported. | SPEC 6.3 step 3 (#262, #263); D16 #247; A19 #251; data-integration 4.5a (#264) | in force |
| 2026-11-14 | **Roof mask check stays symmetric ±15 % for every roof.** The flat-roof 40 % floor (#242) was calibrated on wrong-building data and is reverted. | `solar/roof/masks.py` (#251) | in force |
| 2026-11-14 | **An office with tenancy records but no sitting tenant is vacant** (`office_vacant`, source `costar`, confidence 0.6); `occupancy=None` means no data and keeps the defaults. | A10 (#230); D10 test (#235) | in force |
| 2026-11-14 | **An unknown fuel with no gas price stays gas.** A missing price means gas is unknown, not absent (HVAC-00, DEF-07). | A3/A10 (#201, #218) | in force |
| 2026-11-14 | **Electricity and gas prices move together** as one UNC-02 `price_level` group in plan totals. | `finance/plan/plan.py` (#256) | in force |
| 2026-11-14 | **Houston C-PACE fails the SIR test** (LGT_LED 0.74, PV 0.25, RTU 0.17) and is presented honestly, not tuned to pass. | board | in force |
| 2026-11-14 | **Measure budget split (old rule): solar takes the budget left after the other measures.** | SPEC 6.5 | superseded by the consultant-practice row |
| 2026-11-14 | **A13 (roof planes from splats) is not built**: no splat or drone photos exist for the offices (D12 negative result). | workplan; data-integration | in force |

## Data and prices

| Date | Decision | Where | Status |
|---|---|---|---|
| 2026-11-14 | **Weather comes from a typical-year file for the nearest representative station (TMYx), with the Open-Meteo archive as the fallback**: one reanalysis year (2024) gave LA about 2,220 F heating degree-days against roughly 1,150-1,300 in NOAA normals and nearly doubled heating. Done by the lead's agent as a handoff into the data lane; @vigjay reviews. | #295; board | pending |
| 2026-11-14 | **Los Angeles electricity at the EIA California average**: RES 0.2975, COM 0.3002 USD/kWh, labelled `fallback`, with a symmetric range from the same EIA tables. | data-integration 5.1c; examples (#220) | in force |
| 2026-11-14 | **Gas at the EIA 2025 state averages** (per MCF, converted through heat content, never per therm): CA RES 0.072422, CA COM 0.054489, TX RES 0.063900, TX COM 0.036129 USD/kWh. | D15 (#216); examples (#231) | in force |
| 2026-11-14 | **`Tariff.utility` names who serves the meter**; an unnamed utility is unconfirmed, never LADWP by default. Texas stays the state-average label (a service territory is not a city boundary). | D14 (#208); A19 `export_regime` | in force |
| 2026-11-14 | **Every bundle `FetchRecord` with status `fallback` or `error` reaches the public API** as a `fallback` RunEvent and one line in `RunResult.warnings`; `missing` records stay out. A roof view with the ortho and masks needs a new route, which is a contract change to be proposed. | board (Yale's Claude, 11:22 UTC) | pending (Srihaan) |
| 2026-11-14 | **Sponsor-derived files are never committed**: `data/cache/`, `data/fixtures/`, `data/runs/` (recorded demo runs included) are git-ignored. | `.gitignore` (#269) | in force |
| 2026-11-14 | **The CoStar kit is mirrored with one command** (`python -m backend.data_layer.mirror`); the download link expires 2026-11-15 03:30 UTC, after which the zip comes from @vigjay. | D17 (#257); SPEC 16 | in force |

## Examples (golden fixtures)

| Date | Decision | Where | Status |
|---|---|---|---|
| 2026-11-14 | **The LA office example is Culver Connect** (Matterport `ZSPaQbkGcJJ`, CoStar 27120), chosen for its scan (17 rooms, 339 panoramas), replacing 246899 / `jfiEvosX974`; Houston moves to its D16 structure (1,104.5 m²). | #253, #275 | in force |
| 2026-11-14 | **LA example budgets $150,000 (landlord) and $75,000 (tenant)**, sized to the 2,312 m² full-floor suite; made by the rebuild, not yet confirmed by the lead. | PR #275 | proposed |

## Team, demo and process

| Date | Decision | Where | Status |
|---|---|---|---|
| 2026-11-14 | **Write both office documents for the demo: L4 `retrofit_contract_commercial` (CA) and L6 `cpace_package` (CA, TX).** @vigjay drafts as a handoff into `backend/legal/`, @Sri-SriPod reviews; only from `specs/legal.md` and `specs/legal/*.md`, visible blanks where the spec has no text, Houston's failing SIR shown honestly. | board (Yale's Claude, 12:31 UTC) | pending |
| 2026-11-14 | **Hold the demo recordings** until the SPEC 6.5 plan rule and A6 calibration land. | board | in force |
| 2026-11-14 | **The legal door calls the real engine** (templates on disk, predicates run, un-templated requests refused with 404 `template_not_available`), and a silent `analysis_stub` fallback is reported in `RunResult.warnings`. | #274, PR #284 (Srihaan reviewing) | pending (merge) |
| 2026-11-14 | **Demo machine: Srihaan's laptop.** Srihaan makes the three recordings (Culver, house, Houston) after the legal wiring and the example rebuild land. | board | pending |
| 2026-11-14 | **Stage mode: `AGENT_MODE=replay` with recorded live runs**, never `live` on stage; the start command goes in the README. | board | pending |
| 2026-11-14 | **vigjay: end-to-end verification first, then the legal wiring (#274, handoff from Srihaan's files), then the demo rehearsal and submission (F12)**; Vinayak records the video. | board | in progress |
| 2026-11-14 | **Frontend CI approved**: `.github/workflows/frontend.yml`, replay only, no secrets, no kit, no live calls. | board; PR #260 | in force |
| 2026-11-14 | **The demo-day check lives in the data lane**: `python -m backend.data_layer.demo_check`, tmp cache. | #241 | in force |
| 2026-11-14 | **Analysis split**: Srihaan owns the Analysis scaffold, wiring and finance (A0, A24 to A30) and `backend/config.py`; the lead keeps the rest of `backend/analysis/`. | `AGENTS.md` (#117) | in force |
| 2026-11-13 | **One writer per path, handoffs on the board, `main` the only trunk.** | `AGENTS.md` | in force |

## Open (needs the lead)

| Raised | Question | Where |
|---|---|---|
| 2026-11-14 | The roof-view route (ortho bounds plus detections), once Srihaan proposes it. | board |
| 2026-11-14 | Whether a vacant suite is a valid audit target (physics 02 asks). | physics 02 |

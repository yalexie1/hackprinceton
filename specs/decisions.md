# Decision log

One line per decision the team made, newest first. Each row says who decided, what, and where it now lives (spec section, PR or board post on the pinned issue #1). The lead (@yalexie1) decides; a decision changes only by a new row that names the one it replaces. Only the Status cell moves in place (proposed or pending to in force, once confirmed or implemented), and the Where cell then names the confirming post or PR. Owner: @yalexie1 (`specs/`).

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
| 2026-11-14 | **Home thermostat stays at DEF-08 (21.7 °C heating, 24.4 °C cooling, all hours)**, the Building America protocol value. After the weather fix the house sits at the 68th RECS percentile for gas, and without the owner's bills there is no evidence to tune it. Calibration to bills (A6) is the route, not a hand-picked setback. | physics 02 DEF-08; board | in force |
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
| 2026-11-14 | **Weather comes from a typical-year file for the nearest representative station (TMYx 2011-2025), with the Open-Meteo 2024 archive as the fallback.** Station rule: record of at least 25 years running to 2020 or later, within 100 m of the site's elevation, nearest within 50 km (house: Downtown USC; Culver: Santa Monica airport; Houston: Hobby). Measured on NOAA's daily method, Open-Meteo gave the house 1,562 F heating degree-days against a USC normal of 1,005 (the earlier 2,220 figure was degree-hours and is withdrawn). House gas fell from 616 to 395 therms. The files are not redistributable, so they stay in the git-ignored cache, and results cite TMYx. Built by the lead's agent as a handoff into the data lane; reviewed and merged by @vigjay. | #295, #302; data-integration 5.1f | in force |
| 2026-11-14 | **Los Angeles electricity at the EIA California average**: RES 0.2975, COM 0.3002 USD/kWh, labelled `fallback`, with a symmetric range from the same EIA tables. | data-integration 5.1c; examples (#220) | in force |
| 2026-11-14 | **Gas at the EIA 2025 state averages** (per MCF, converted through heat content, never per therm): CA RES 0.072422, CA COM 0.054489, TX RES 0.063900, TX COM 0.036129 USD/kWh. | D15 (#216); examples (#231) | in force |
| 2026-11-14 | **`Tariff.utility` names who serves the meter**; an unnamed utility is unconfirmed, never LADWP by default. Texas stays the state-average label (a service territory is not a city boundary). | D14 (#208); A19 `export_regime` | in force |
| 2026-11-14 | **Every bundle `FetchRecord` with status `fallback` or `error` reaches the public API** as a `fallback` RunEvent and one line in `RunResult.warnings`; `missing` records stay out. A roof view with the ortho and masks needs a new route, which is a contract change to be proposed. | board (Yale's Claude, 11:22 UTC) | pending (Srihaan) |
| 2026-11-14 | **Sponsor-derived files are never committed**: `data/cache/`, `data/fixtures/`, `data/runs/` (recorded demo runs included) are git-ignored. | `.gitignore` (#269) | in force |
| 2026-11-14 | **The CoStar kit is mirrored with one command** (`python -m backend.data_layer.mirror`); the download link expires 2026-11-15 03:30 UTC, after which the zip comes from @vigjay. | D17 (#257); SPEC 16 | in force |

## Examples (golden fixtures)

| Date | Decision | Where | Status |
|---|---|---|---|
| 2026-11-14 | **No invented geometry is labelled measured; the office examples have no wall-graph openings, as the live Model API returns.** The 76 Culver window openings were made up by the #253 generator while its provenance said measured. They are removed, and windows come from a vision `window.area_m2` (287.28 m², ±30 %, confidence 0.5), as for Houston, so `no_window_openings` fires as it does live. Found by @vigjay. | #301, #308 (`test_wiring` baseline_after compared at the plan's 2-dp rounding, a lead decision) | in force |
| 2026-11-14 | **The LA office example is Culver Connect** (Matterport `ZSPaQbkGcJJ`, CoStar 27120), chosen for its scan (17 rooms, 339 panoramas), replacing 246899 / `jfiEvosX974`; Houston moves to its D16 structure (1,104.5 m²). | #253, #275 | in force |
| 2026-11-14 | **LA example budgets $150,000 (landlord) and $75,000 (tenant)**, sized to the 2,312 m² full-floor suite; confirmed by the lead (Yale). | PR #275; board (Yale's Claude, 14:14 UTC, #6878598841) | in force |

## Team, demo and process

| Date | Decision | Where | Status |
|---|---|---|---|
| 2026-11-14 | **Write both office documents for the demo: L4 `retrofit_contract_commercial` (CA) and L6 `cpace_package` (CA, TX).** @vigjay drafts as a handoff into `backend/legal/`, @Sri-SriPod reviews; only from `specs/legal.md` and `specs/legal/*.md`, visible blanks where the spec has no text, Houston's failing SIR shown honestly. | board (Yale's Claude, 12:31 UTC); delivered and merged in #299 (lead's review) | in force |
| 2026-11-14 | **A fixture or example rebuild runs the full backend suite of every lane before its PR opens**, and the PR lists every test whose result changes; owners update their own tests. #253 turned main red in three lanes for an hour without it. | board (agreed with @vigjay) | in force |
| 2026-11-14 | **Srihaan's approvals count when posted on the board** (their session cannot post a GitHub review). | board | in force |
| 2026-11-14 | **@vigjay takes the flaky `backend/agent/tests/test_live.py` tests** (fails only in multi-lane runs, threaded `LiveRun` through `check_narrative`), as a handoff into Srihaan's lane; done when the full run passes 10 times in a row; Srihaan reviews. | board (Yale); fixed in #313: an answer-then-drain race on `LiveRun.pending`, a product bug | in force |
| 2026-11-14 | **Srihaan's order: ok the #308 test change, review #299, then A26 (the 6.5 plan rule) and the A6 wiring, then the recordings.** | board (Yale) | in force |
| 2026-11-14 | **Vinayak rebases the frontend (#260) onto main (contract 0.3.5) and merges it now**, without waiting for the plan rule; the examples are regenerated after A26 and announced with FIXTURE-READY. | board (Yale) | pending |
| 2026-11-14 | **The LA C-PACE package is hypothetical until a programme is confirmed**: LA County ended its own residential PACE programme in 2020 (CA-PACE-15, silent on commercial), and the active statewide CSCDA programmes are not confirmed to take commercial property (CA-PACE-16), so agency, programme and administrator stay blank. The demo shows what an assessment would look like and what has to be confirmed first; it does not say commercial PACE is unavailable in LA. California's tax-burden cap reports incomplete without the owner's figures, and lien priority is not asserted. | #299 (L6, merged after the lead's review); specs/legal/california.md section 8 | in force |
| 2026-11-14 | **While Srihaan works on A26, the lead reviews and merges in Srihaan's lane** (#308 test edit, #299 legal); Srihaan is told and may object afterwards. Supersedes 'Srihaan's order' for #308 and #299. | board (Yale) | in force |
| 2026-11-14 | **@vigjay takes the A31 benchmark wiring and the FetchRecord warning forwarding** (`backend/analysis/api.py`, `backend/agent/`), as a handoff from Srihaan's lane; Srihaan keeps A26 and the A6 wiring. Example diffs are listed in the PR, not edited. | board (Yale's Claude, 14:27 UTC) | pending |
| 2026-11-14 | **Hold the demo recordings** until the SPEC 6.5 plan rule and A6 calibration land. | board | in force |
| 2026-11-14 | **The legal door calls the real engine** (templates on disk, predicates run, un-templated requests refused with 404 `template_not_available`), and a silent `analysis_stub` fallback is reported in `RunResult.warnings`. | #274, #284 (Srihaan approved on the board; merged by @vigjay) | in force |
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

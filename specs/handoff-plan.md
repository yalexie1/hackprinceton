# Plan: write the project spec (spec only, no code)

## Context

The team (4 people, HackPrinceton Fall 2026, Nov 13–15) wants an AI energy consultant: the user picks a scanned building and a budget, the system audits it with physics models, ranks retrofits by money saved within the budget, and then drafts the legal paperwork to carry the plan out. Tracks: Sustainability (main), LangChain, CoStar, Amazon (nice to have).

The repo is the "agent board" template. It has no code and no `specs/` folder yet; `AGENTS.md` already assigns folders to four owners. The spec must fit that ownership table. This plan is the outline for your final confirmation. Nothing is written until you approve.

## Decisions you made

| Topic | Decision |
|---|---|
| Building types | Homes and offices, both fully specified |
| Physics | Deterministic, unit-tested Python exposed as tools; the LangChain deepagent plans and calls them, never does the math |
| Missing thermal data | Infer from CoStar year built + climate zone + vision on panoramas; report low/expected/high; ask the user to correct an assumption **only when the range is too wide** |
| Budget | Hard upfront cash cap for the ranked plan; over-cap measures go to a second "financeable" list (C-PACE for offices); every recommendation spells out all financial aspects |
| Legal documents | Retrofit construction contract, solar installation agreement, contractor bid package (RFP), energy savings guarantee, C-PACE package (commercial only) |
| LLM | Anthropic API directly, via LangChain |
| CoStar fields | You add keys to `.env`; I inspect the real kit and API responses before writing so field names are verified |
| Data breadth | Use all four key types (CoStar data kit, Matterport Model API, Matterport Showcase SDK, Vexcel API) and pull every distinct data type each one offers, for houses and offices equally |
| Solar pipeline | Exterior property mesh + geolocation + weather APIs for viability; SAM 3 segments the roof from top-down imagery to place panels; an indoor vision model reads wall material and outlet type/age from the panoramas as installation-feasibility signals |

**My reading of "4 different API keys":** the four key types in the CoStar announcement, not four copies of one key. If you meant one key set per teammate (for parallel harvesting), say so and I'll add a rate-limit-sharing plan.

## Facts found that shape the spec

- **No scan upload.** Hackathon keys reach 14,944 existing Matterport models in Houston and Los Angeles only (1,930 residential, 13,014 commercial). "Input the scan" becomes "search an address / pick a model". Vexcel keys also cover only those two cities.
- **What a scan gives:** room polygons, classifications, area/width/depth/height, wall graph with wall thickness, panoramas (furnished and defurnished), floor plan image + DXF. Mesh and point cloud (MatterPak) are unlocked for the 232 splat models and "being unlocked" for the rest.
- **What it does not give:** U-values, insulation, window type, HVAC equipment, or a guaranteed north-aligned frame. These are inferred (vision, CoStar vintage, footprint registration against Vexcel).
- **Joins:** `models_index.csv` carries lat/lon, segment, Homes listing id (residential) or CoStar property id (commercial). The quickstart says the CoStar join is untested on their side.
- **Track rules (second-hand, I will re-verify on the official pages):** CoStar scores 30% data use, 30% agentic depth, 25% usefulness, 15% demo, and wants at least two data layers; LangChain requires a `deepagents` agent; Amazon wants practical AI that reasons, plans, acts, adapts.
- **Amazon caveat:** with Anthropic direct there is no AWS usage, so that entry rests on usefulness alone.

## Deliverables (all in `specs/`, owned by @yalexie1)

1. `specs/SPEC.md` — master spec
   - Product flow: property search + budget → ingest → building model → baseline simulation → measure evaluation → budget-ranked plan → financial report → legal drafting
   - Home flow and office flow side by side (office adds lighting power density, rooftop units, daylight controls, desk placement by daylight/glare/thermal comfort)
   - Architecture mapped to the owner table: `backend/data_layer/`, `backend/analysis/`, `backend/agent/`, `backend/server.py`, `frontend/`, `backend/schema.py`
   - Shared contract: the data models every owner codes against (property record, building model with per-assumption uncertainty, measure result, plan, financial breakdown, document request), plus API endpoints and env var names
   - Deepagent design: orchestrator with planning, subagents (data, building model/vision, audit, finance, legal), tool list, and the human-in-the-loop rule that triggers a question only when an assumption's range changes the ranking or exceeds a set width
   - Budget algorithm exactly as you described: rank by annual dollar savings, skip what exceeds the cap, take the next; re-simulate after each pick because measures interact; then the financeable list
   - Financial breakdown per recommendation: installed cost range and its source, incentives actually in force in 2026, net cost, annual savings range, simple and discounted payback, NPV, SIR, IRR, lifetime, maintenance, rate-escalation assumption, CO2; cash view vs C-PACE view (term, rate, annual assessment, net cash flow, lien and lender-consent implications)
   - Frontend: Matterport Showcase SDK embed with measures pinned in the 3D tour, Vexcel roof view with panel layout, report, document drafting screen
   - Track mapping, P0/P1/P2 scope tiers for the weekend, per-owner acceptance criteria, demo script, risks

2. `specs/data-integration.md` — CoStar, Matterport, Vexcel
   - Full inventory of what each of the four keys returns, and which analysis step consumes it, so no available data type goes unused:
     - CoStar kit: every file and column (residential listings, commercial property records), joined by Homes listing id / CoStar property id
     - Matterport Model API: model basics, AI summary, property classification, floors, rooms, dimensions, wall graph, panoramas (furnished + defurnished), floor plans + DXF, MatterPak mesh and point cloud, aerial splat and drone photos with GPS
     - Matterport Showcase SDK: in-tour tags, measurements, camera control for the frontend
     - Vexcel: orthophoto, obliques, parcels, roof attributes, object detection, embedding search, elevation data if the key allows it
   - Harvest plan: a metadata index over all 14,944 models (cheap queries), and deep assets (panoramas, mesh, splat) for a curated set balanced 50/50 between houses and offices, since full deep data is hundreds of MB per model
   - Every query/endpoint used, verified field names, the join path, caching and fixtures, signed-URL expiry handling, fallbacks when MatterPak is locked or a CoStar field is missing
   - External data: geocoding, TMY and live weather APIs, utility tariffs, emission factors, measure cost data, each with its source

   **Solar pipeline (spans `data-integration.md`, `physics.md`, and the analysis section of `SPEC.md`):**
   1. Locate: CoStar parcel/property record + Matterport lat/lon + Vexcel parcel → georeferenced lot
   2. Exterior mesh: built from the best available source in order (Vexcel elevation/obliques, aerial splat + drone photos, fallback to footprint + assumed pitch), registered to true north
   3. Roof understanding: SAM 3 on the Vexcel orthophoto with concept prompts (roof planes, vents, chimneys, skylights, HVAC units, trees) → usable roof polygons with setbacks
   4. Per-plane tilt and azimuth from the mesh; hour-by-hour shading by ray casting the mesh against sun positions
   5. Weather: typical-year irradiance and temperature from a weather API → verified PV production model → kWh, dollars, CO2
   6. Panel layout optimisation: place modules on the highest-yield unshaded planes until budget or roof area runs out
   7. Indoor feasibility check: a vision model on the Matterport panoramas reports wall material and outlet type (two-prong ungrounded, three-prong, GFCI), and looks for the main electrical panel; these become flags such as "likely needs service upgrade" with added cost, each with a confidence level
   - Stated honestly in the spec: outlet type and wall material are proxies for wiring age and construction era, not proof. The deciding items for installation are service panel capacity and roof structure, so the model reports "likely / unlikely / unknown", and "unknown" triggers the ask-the-user rule rather than a guess
   - SAM 3 hosting (local GPU vs hosted API) and whether sponsor imagery may leave the machine are flagged for the team to settle

3. `specs/physics.md` — the model library
   - One entry per formula: equation, symbols and units, validity range, primary citation (paper DOI or standard clause), a second independent source, a worked numeric example
   - Modules: solar position; irradiance decomposition and transposition; PV production and cell temperature; envelope conduction and U-values; hourly zone thermal model; infiltration; window solar gain; daylight and glare; thermal comfort; HVAC and water-heating efficiency; lighting and plug loads with HVAC interaction; life-cycle economics; emissions; measurement and verification
   - Candidate sources to verify, not yet trusted: NREL SPA (Reda & Andreas 2004), Erbs 1982, Perez 1990, PVWatts v5 (Dobos 2014), ISO 13790 / ISO 52016-1, ISO 6946, Sherman & Grimsrud 1980, ASHRAE Handbook of Fundamentals, ISO 7730, NIST Handbook 135, EPA eGRID, ASHRAE Guideline 14, IPMVP, ASHRAE Standard 140 for validation
   - Build-time validation plan: tests against reference implementations (pvlib, PVWatts) and published test cases

4. `specs/legal.md` — document framework
   - Five document templates with clause libraries in standard contract language, each variable bound to a field from the analysis output
   - State-specific required terms for California and Texas, each cited to the statute section (home improvement contract rules, solar disclosures, lien and homestead notices, PACE statutes) and checked against the official code sites
   - C-PACE limited to commercial properties, tied to the SIR result from the physics/finance model
   - "Draft for attorney review, not legal advice" notice on every generated document

5. `specs/workplan.md` — four-person, multi-agent work framework

   **Lanes** (existing `AGENTS.md` table, extended; new folders marked *new* are proposals to confirm on the board):

   | Lane | Owner | Folders (one writer per path) | Reference spec |
   |---|---|---|---|
   | Data | @vigjay | `backend/data_layer/`, `data/fixtures/`, `data/cache/` | `data-integration.md` |
   | Analysis | @yalexie1 | `backend/analysis/` split into `physics/`, `vision/`, `solar/`, `measures/`, `finance/`; `backend/config.py` | `physics.md` |
   | Agent + server + legal | @Sri-SriPod | `backend/agent/`, `backend/server.py`, `backend/legal/` *new*, `data/runs/` | `legal.md` |
   | Frontend + demo | @vinayak-sinha | `frontend/` | frontend section of `SPEC.md` |
   | Contract | @yalexie1 | `backend/schema.py`, `specs/`, `specs/examples/` *new* | `SPEC.md` |

   **Rules that keep parallel work from colliding:**
   - **Contract first.** `backend/schema.py` is frozen at v0 before anyone builds. Lanes talk to each other only through its types. After the freeze, changes are additive only and go through a `CONTRACT-CHANGE:` board post acknowledged by every affected owner.
   - **One public door per lane.** Each lane exposes a single interface module (data → `data_layer/api.py`, analysis → `analysis/api.py`, server → its REST routes). No lane imports another lane's internals.
   - **Fixtures before integration.** The spec ships hand-written example payloads in `specs/examples/` for one house and one office, for every contract type and API response. Each lane builds and tests against those from hour one, so nobody waits on anybody. The data lane later replaces them with real captures in `data/fixtures/` in the same shape.
   - **No shared files.** Dependencies are declared per lane (one requirements file per lane folder), root files (`README`, `.gitignore`, `.env.example`) belong to the contract owner, and a `CODEOWNERS` file mirrors the table so a PR touching someone else's path is visible at review.
   - **Sub-lanes for each person's own agents.** Every lane is cut into work packages bound to a subfolder (for example analysis: physics / vision + SAM 3 / solar / measures + finance), so one person can run several agents at once, one writer per subfolder, each on its own `<issue#>-<slug>` branch or worktree.
   - **Work packages.** Each has an ID (D1…, A1…, G1…, F1…), tier (P0/P1/P2), input types, output types, the fixture it tests against, an acceptance test runnable inside its own lane, and a dependency list that may name contract types only, never another package's code. One GitHub issue per package.
   - **Board protocol.** Short standard post types on top of the existing board rules: `CONTRACT-CHANGE:`, `FIXTURE-READY:`, `INTERFACE-LIVE:`, `BLOCKED:`, `HANDOFF-REQUEST:`.
   - **Integration checkpoints.** (1) schema freeze, (2) walking skeleton end to end on fixtures, (3) live data on the two demo properties, (4) feature freeze and demo rehearsal. Times set relative to the submission deadline.

## Double-check protocol (physics and legal)

- **Pass 1:** each formula or statutory requirement is written from the opened primary source, not from memory.
- **Pass 2:** separate re-verification after drafting: re-open the source, re-check the equation term by term, run a dimensional check, recompute the worked example with a script, and confirm against the second source.
- Anything I cannot open in primary form is listed as **unverified, do not implement**, never silently included.
- A verification log table at the end of `physics.md` and `legal.md` records source, date checked, and result.

## Order of work after approval

1. Add `.env`, `mp_out/`, `data/cache/`, `CLAUDE.local.md`, `.claude/settings.local.json` to `.gitignore` (only non-spec edit; `.gitignore` currently ignores just `.board/`, so keys would be committable).
2. You add to `.env`: `MATTERPORT_API_KEY`, `MATTERPORT_API_TOKEN`, `VEXCEL_API_KEY`, `COSTAR_ZIP_PASSWORD`, and `COSTAR_KIT_URL` or `COSTAR_KIT_ZIP`. I start physics and legal research meanwhile.
3. Read-only data checks across all four keys: key check, one residential and one commercial model, every Vexcel product the key answers for on the same lot, CoStar kit file list and all CSV headers via range requests (no full 160 MB download). Also confirm SAM 3 availability and how it can be run. Downloads go to the scratchpad, not the repo.
4. Write the five spec files plus `specs/examples/`, run the double-check pass.
5. Post one short note on the team board that the spec and shared contract landed, including the proposed ownership additions (`backend/legal/`, `specs/examples/`) for the team to confirm (AGENTS.md rule 3.6). I will not edit `AGENTS.md` itself or commit/push unless you ask.

## Verification

- Every formula in `physics.md` has two sources and a worked example whose numbers reproduce from a script run.
- Every statutory citation in `legal.md` resolves to the official code text.
- Every field name in `data-integration.md` and the shared contract appears in a real response captured in step 3.
- Each owner's section in `SPEC.md` ends with acceptance criteria that can be checked without reading another owner's section.
- Every work package in `workplan.md` lists only contract types as dependencies, and no path appears under two owners.
- Every example payload in `specs/examples/` validates against the contract types defined in `SPEC.md`.

## Open items I will resolve or flag in the spec

- Whether sponsor imagery may be sent to an external LLM or segmentation provider (needs `/ask-costar`; affects the vision and SAM 3 steps).
- Which Vexcel products the hackathon key actually unlocks (elevation data decides how good the exterior mesh is).
- Model orientation to true north (planned: register the floor outline to the Vexcel footprint).
- Federal and utility incentive status for 2026 (to be verified, not assumed).
- Official track rules on Devpost.

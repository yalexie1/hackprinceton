# Leto

An energy consultant for a scanned building. Pick a property and a budget. Leto reads the building from the inside (a Matterport scan), from above (Vexcel aerial imagery) and from its market record (CoStar). It simulates a year of energy use with physics models and checks every retrofit that applies. It then returns a plan, ranked by money saved, that fits the budget. From the plan you can draft the documents needed to carry it out.

Built at HackPrinceton 2026 for the CoStar track.

## What it does

- **Two flows, homes and offices.** For homes: insulation, air sealing, windows, cool roof, heat pump, water heater, lighting and rooftop solar. For offices: lighting power and controls, rooftop units, economizer, plug loads, rooftop solar and daylight-aware desk placement.
- **Facts kept apart from estimates.** Room geometry comes from the scan. Window, lighting and equipment types are read from the scan's panoramas by a vision model. Anything a photo cannot confirm, such as hidden insulation, is labelled as an assumption you can correct. Every input names its source.
- **Ranges, not single numbers.** Savings and costs come with a low-to-high range built from the uncertain inputs.
- **Calibration to your bills.** Given a year of utility bills, the model fits itself to them before ranking upgrades (ASHRAE Guideline 14 tolerances).
- **Solar last, sized to what is left.** Panels are placed greedily by yield on the roof planes, and the system is sized after the other upgrades have cut demand.
- **Money the way a consultant counts it.** Net present value, savings-to-investment ratio and payback, with incentives. C-PACE financing is offered for offices where eligible. An upgrade that does not pay for itself is never recommended.
- **Document drafts.** A California residential retrofit contract, drafted from the plan, with every statutory check listed and every missing detail left visibly blank. It is a draft for attorney review, not legal advice.
- **Solar map.** Estimated rooftop-solar payback for a typical home, by zip code, across Los Angeles County and Harris County (Houston), from public data.

## How accurate is it

The app's **Accuracy & evidence** page shows every study, with its limits beside it. The headline results:

| What we measured | Result | Against |
|---|---|---|
| Error with a year of utility bills | **4.1%** median (18.1% before calibration) | Calibrated on 2016 bills, scored on 2017, 44 metered buildings (Building Data Genome 2) |
| Los Angeles offices, from our own scans, no bills | **14.8%** median energy-use-intensity error (a typical-office benchmark: 16.5%) | City of Los Angeles EBEWE benchmarking data, 49 offices |
| Solar output | **76 of 76** roofs within 10%, median +2% | PVGIS, the European Commission's solar model (model against model) |

What these do not show: calibration to bills succeeds for 44 of 283 buildings today, savings from individual upgrades have not yet been checked against measured results, and without bills the model is about as accurate as a typical-building benchmark on total energy. Details are in `backend/evals/FINDINGS.md`.

## Repository

| Path | What it holds |
|---|---|
| `backend/data_layer/` | CoStar, Matterport, Vexcel, weather, tariffs and the cache; builds one `PropertyBundle` per property |
| `backend/analysis/` | Geometry, vision, the building energy model, measures, solar layout, finance |
| `backend/agent/` | The agent, the API server's run logic, recorded runs, the EBEWE eval |
| `backend/legal/` | Document templates and statutory checks |
| `backend/evals/` | Metered-building, calibration, PV and cost evaluations |
| `backend/roi_map/` | The Solar map data |
| `frontend/` | The React app (see `frontend/README.md`) |
| `specs/` | The product spec (`SPEC.md`), physics formulas with sources (`physics/`), legal requirements by state (`legal/`) and example payloads |

`backend/schema.py` is the shared contract, generated from the code block in `specs/SPEC.md` section 9.

## Running it

Install the backend once, in a virtual environment, from the repo root. Each lane has its own requirements file, and the server and the tests need all four:

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r backend/data_layer/requirements.txt -r backend/analysis/requirements.txt \
                -r backend/agent/requirements.txt -r backend/legal/requirements.txt

Then start the server from the same shell:

    AGENT_MODE=replay uvicorn backend.server:app --port 8000

And the frontend:

    cd frontend && npm ci && npm run dev

Open http://localhost:5173, **never 127.0.0.1**: the Matterport SDK key is allowlisted for `localhost` only, and on 127.0.0.1 the tour cannot load its evidence markers.

### Stage and live modes

Stage mode is replay: it serves the saved real runs instantly and never calls a model.

- `AGENT_MODE=replay` is the default; never set `live` on stage.
- Recordings are in `data/runs/_demo/<sid>/` (git-ignored, per machine). A property with no recording falls back to the example in `specs/examples/`. Override the folder with `AGENT_DEMO_DIR`.
- Make a recording with a live run (`AGENT_MODE=live`, needs `ANTHROPIC_API_KEY`, `EIA_API_KEY` and the mirrored CoStar kit). It is saved only when the run reaches `done` with a plan.
- Before the demo: `python -m backend.data_layer.mirror --check` and `python -m backend.data_layer.demo_check --golden` (the three golden properties, about 2 min). Bare `demo_check` checks all 50 warm properties and takes about an hour.
- After pulling, run `npm install` in `frontend/` (the Solar map needs `leaflet`), and restart the API with the keys loaded.
- `demo_check` and every live run need the sponsor and EIA keys **in the process environment** (`set -a; source .env; set +a` in that shell). Without them they stop with an auth error such as `MatterportAuthMissing`; they never fall back silently. Check that the run header says **live property data** before trusting a recording.

Sponsor data (CoStar, Matterport, Vexcel) is never committed; `data/fixtures/` and `data/cache/` are git-ignored.

## Team

- Yale ([@yalexie1](https://github.com/yalexie1)): lead, analysis and physics
- Vignesha ([@vigjay](https://github.com/vigjay)): data layer and evaluations
- Srihaan ([@Sri-SriPod](https://github.com/Sri-SriPod)): agent, API, finance and legal
- Vinayak ([@vinayak-sinha](https://github.com/vinayak-sinha)): frontend and demo

## How we worked

Each of us ran coding agents in parallel. They coordinated on one pinned GitHub issue, the board (#1), through `tools/board`. Agents post when they finish or need something, tag teammates by GitHub login, and keep `tools/board wait` running so a tag wakes them up. Ownership of every folder is in `AGENTS.md`, which every agent reads.

| Command | What it does |
|---|---|
| `tools/board post "[Sam's Claude] ..."` | Posts to the board. Every post starts with whose agent it is. |
| `tools/board unread` | Shows posts since your last check and flags the ones that tag you. |
| `tools/board wait` | Blocks until someone else posts, then prints it. |
| `tools/board read -n 20` | Shows the last 20 posts. |
| `tools/board whoami` | Prints your GitHub login so you can check `gh` is set up. |

The board tooling needs `bash`, `git` and the [GitHub CLI](https://cli.github.com) logged in with `gh auth login`.

# Leto frontend

Vinayak's frontend and demo lane, built against `specs/SPEC.md` section 9, schema **0.3.8**. “Leto” is the product name. React 19, TypeScript, Vite; no backend changes.

## Run

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173 with the team's FastAPI server running on port 8000. The app connects automatically and checks the schema before loading properties. It only displays audits based on actual property records. Example-input or unverified results are rejected before their replay events can display sample savings.

Private data is not included in a clone. Ask Srihaan for saved audits and Vignesha for the actual property cache through a direct laptop-to-laptop transfer. Install the cache with `python -m backend.data_layer.demo_transfer install /path/to/leto-demo-cache.tgz`; place owner-provided recordings in `data/runs/_demo/` using the owner's recording layout. Keep these files and `.env` out of Git. Run `python -m backend.data_layer.demo_transfer check` to inspect cache readiness. If no real audit is installed, the app explains that instead of substituting example numbers.

## Readable interface

App-owned text uses a 16px minimum, 18px body copy and dark shared text colors. Plan categories use green for included upgrades, amber for options needing more budget and slate for other findings, with labels and icons so color is not the only cue. Category tabs support arrow keys, Home and End. Finance details include plain-language definitions; long reports use safe Markdown paragraphs/lists, and source notes remain available in full. Narrow layouts stack cards and keep form labels, property names and export buttons visible.

## Interactive architecture

The welcome screen has a furnished Three.js house with exterior, cutaway, and exploded views. Drag to orbit, scroll/pinch to zoom, or use the labeled buttons for rotation, zoom, reset, and room focus. Selecting a room reveals its floor before moving the camera. The setup and demo audit screens include a smaller interactive explorer. Property-card previews render once, without animation or nested controls.

The welcome house is an interactive educational guide with no sample financial results. The setup screen uses the selected property's actual imagery. After a real audit, the energy explorer can show upgrade costs, savings and caveats tied to that result. Selected marginal results take precedence over standalone estimates; only selected upgrades contribute to totals. All positions on the concept model remain illustrative.
Geometry, material textures, furniture and lighting are generated locally. These are **illustrative concept models**, not scans or measurements of the selected properties. Live Matterport tours and evidence pins continue to use the real property SDK. No energy estimates are calculated by the 3D scene.

The renderer loads lazily when visible, pauses rendering offscreen/in background tabs, respects reduced motion for camera/view transitions, and disposes GPU resources when unmounted. If WebGL is unavailable, a fallback keeps the rest of the app usable.

## Demo walkthrough

Follow [the judge walkthrough](JUDGE_WALKTHROUGH.md). Use each saved audit's recorded budget and role, which are preselected on setup. Confirm **Based on this property's records · Saved property audit** before presenting a result. Costs remain estimates; contractor quotes, bill calibration and legal details still require confirmation.

## Live integration

Under **How would you like to build your plan?**, **Use the saved property audit** uses the server's configured mode (normally replay for the demo). **Calculate a new plan** sends `mode: "analysis"` with the budget, role, desks and optional bills. New analysis needs the actual property cache or live data credentials. Timing varies by property and cache state.

The development server proxies `/api` to `http://127.0.0.1:8000`. The server controls `AGENT_MODE=replay|live`. Starting a saved audit does not recalculate it; review the returned warnings after changing its budget. Source labels distinguish a saved property audit from a new calculation. API failures and example-only results never fall back to browser fixtures.

Optional configuration goes in the **repository root `.env`** (Vite's envDir is the repo root):

```dotenv
# Used server-side by the Vite development proxy; not exposed to the browser.
FRONTEND_API_PROXY=http://127.0.0.1:8000
# Optional direct browser API base. Omit to use same-origin /api.
VITE_API_BASE_URL=
# The existing domain-scoped Showcase browser key; restart Vite after changing.
MATTERPORT_SDK_KEY=
```

Only `MATTERPORT_SDK_KEY` is deliberately exposed from the sponsor variables. Matterport API credentials, the Vexcel key, CoStar credentials, and the Anthropic key belong to the backend and are never copied to frontend source. Vite also exposes any variable intentionally named `VITE_*`; do not give private credentials that prefix.

Production builds use same-origin `/api` unless `VITE_API_BASE_URL` is set at build time. The deployment must route `/api` to FastAPI and serve SPA requests from `dist/index.html`. Vite's development proxy is not a production server.

### Backend expectations

- Search, start/resume runs, questions, budget/assumption updates, and document routes follow SPEC section 10. Types consumed by the UI live in `src/lib/types.ts`.
- Run headers distinguish `data_source` (live/example/unknown property inputs) from `served_by` (live/replay/unknown delivery). A recording of live property data says “Live property data · Saved replay”; absent provenance is unknown and never implies live data. Connecting to the API alone does not establish either value.
- The SSE endpoint emits JSON `RunEvent` data, either default or named events. Comments, CRLF, fragmented UTF-8, multiline data, and multiple events per chunk are supported. The server replays history from the beginning: the frontend retains a per-run cursor and skips consumed events on reconnect. An active run pauses on a new question, done, or non-recoverable error. If the authoritative run is already complete, it drains the finite history to its end so earlier questions/done events do not hide appended G11 re-plan events. Recoverable errors stay in the stream. It fetches the final run and reconnects after an answer/update. Transport failures expose a reconnect button for the same run. Unknown future event types are ignored.
- Questions may be embedded directly in `event.payload` or under `event.payload.question`; the subsequent `RunResult.questions` is authoritative.
- Structured todo events show their backend statuses only at that point in the stream. Once later activity arrives, their checklists collapse as historical snapshots; they do not remain frozen as current progress. Approval questions show document/state/scope context and preserve boolean answers.
- Budget and assumption changes are sent to the backend. The UI never recomputes energy or financial results. All displayed estimate ranges come from the returned payloads.
- Public data-quality warnings arrive through `RunResult.warnings`, `BaselineResult.warnings`, fallback/error events, and measure warnings. Fallback detail uses the backend's `fallback`, `layer`, `status`, `what` and `detail` fields. Long warnings expand in full. A `re-run:` warning identifies the earlier narrative as outdated.
- Live role selection supports owner-occupier, landlord, and tenant. Optional utility history requires twelve non-negative monthly values, in kWh (gas as kWh thermal), with an optional first billing month. Office runs accept a requested desk count. Calibration shows per-fuel before/after bias and fit error, failed tolerances and warnings; an absent summary is explicitly uncalibrated.
- Plans follow the backend's operations/load-reduction/equipment/solar order and distinguish `not_cost_effective` from budget exclusions. No browser economics or sizing replaces the selected marginal results.
- `GET /api/runs/{id}/roof` supplies georeferenced planes, panels and detections. Missing/null ortho metadata or failed imagery leaves the supplied geometry visible. Parcel-bound overlays are labelled approximate; detection boxes are not treated as masks or summed footprint area. Workspace defaults to recommended positions and offers a precise position picker.
- `GET /api/templates` always receives both state and property segment. Documents offers only returned types; `template_not_available` is an availability notice. Parties use the legal engine's `owner_names`/`contractor_name` fields. Connected drafts also accept eight optional verified fields for owner/contractor addresses, licence number, phone/cancellation email, agreed dates and contractor bid price. Missing values remain visible; estimates never fill the quoted price. Both supported blank formats are highlighted. C-PACE scope retains selected marginal sizing and clearly labels additional financing-review measures. Template availability is not eligibility.
- Narratives and documents render safe Markdown headings, tables and emphasis without executing HTML or loading external images; internal template comments are hidden, missing terms are highlighted, and the exported source is preserved. Parties and selected measures require explicit approval before drafting.

### Matterport

The tour embeds the real `sid` in live mode. A valid domain-allowlisted `MATTERPORT_SDK_KEY` enables session-only evidence pins and camera control. Coordinates are converted from Model API `(x,y,z)` to Showcase `(x,z,-y)`. A panorama ID is matched to a published sweep `sid` or `uuid` before `Sweep.moveTo`; it is never assumed to match. Otherwise the SDK can navigate to the session tag, or the UI reports the unavailable location.

Verified integration references:

- [Embed quickstart and current bootstrap module](https://matterport.github.io/developer-docs/embed-sdk/quickstart/)
- [Coordinate systems and API/SDK conversion](https://developers.matterport.com/overview/concepts/)
- [Mattertag add and session-only persistence](https://matterport.github.io/developer-docs/reference/mattertag/)

SDK behavior on sponsor models remains unverified until configured browser SDK credentials and real run payloads are available.

### Shared contract gaps to resolve with the owners

1. The public roof route supplies aerial bounds and detections. A real workspace floorplan background still needs a public floorplan route; candidate positions use the supplied layout geometry.
2. Window/roof anchors and SDK sweep identity need validation on the two real golden properties.
3. Shared run results and event sequences are discovered under `specs/examples/*/` (currently `house`, `office`, and `office_houston`), without editing or copying the spec files. Additional frontend-owned stress fixtures live in `frontend/fixtures/`, outside the default property picker. Both sources validate against the current Pydantic contract. Shared examples have one saved budget each; arbitrary budget and role changes require the live backend.
4. The financial breakdown and legal checklist depend on the analysis/legal owners. This frontend supplies no production pricing, physics, incentive rules, or statutory contract language.

## Actual property thumbnails

Property cards read the cached-only property preview endpoint. An optional private
Vexcel photo manifest can override the crop and direction through the existing
asset API, while keeping the canonical photos as fallbacks. Missing photos fall back to a
clearly labeled overhead image. Browsing never fetches sponsor imagery or starts
an analysis. A thumbnail is geographic context, not the capture used for roof
measurements; those may have different dates.

Prepare photos from a verified scan location from the repository root:

```bash
uv run --with-requirements frontend/scripts/integration-requirements.txt --with python-dotenv \
  python frontend/scripts/cache_property_photos.py MODEL_ID LATITUDE LONGITUDE --prefer west
```

The helper reads `VEXCEL_API_KEY` from the private `.env`, uses the data lane's
existing clients, and writes only ignored `data/cache/` files. Use the repository's
default cache for both this command and the backend (unset `DATA_LAYER_CACHE_DIR`).
`--context-m 45` requests a wider real geographic image when a narrow parcel clips
the building; it does not change any property boundary or analysis geometry.
The prepared manifest preserves that crop and preferred direction. The house uses
a wider west view; Culver a north view; Houston a west view.

## Checks

```bash
npm test
npm run build
# Uses an isolated ephemeral environment; requires uv.
uv run --with 'pydantic>=2,<3' python scripts/check_contract.py
# Starts and cleans up an isolated real FastAPI replay server, with no API keys.
uv run --with-requirements scripts/integration-requirements.txt python scripts/check_integration.py
```

`npm test` also renders the shared examples through the actual screen components to check optional fields, empty states, document gating, and separation of property value from energy savings. It covers SSE framing and termination, backend error handling, answer value preservation, fixture budget/totals, WKT parsing, and verified sweep matching. `check_contract.py` extracts the team's actual Pydantic block without editing it and validates every saved run, plus the shared property bundles, building models, documents, and event streams. When `backend/schema.py` exists, it checks that the actual backend schema agrees with the spec and validates against both. `scripts/make_fixtures.py` regenerates invented examples; it is not an analysis engine.

`check_integration.py` runs five checks twice through the actual TypeScript client and FastAPI app: first example replay, then synthetic recordings made from the shared examples in a temporary directory. It covers health/schema, search, results/SSE, budget/assumption updates, replay after PATCH, errors, roof metadata, segment-filtered templates and every offered document type for every shared property. Both paths verify typed parties, the real C-PACE body, visible blanks/statutory checks, unavailable-template errors and wrong-segment rejection. Synthetic recordings are test inputs, not claimed live analyses, and never replace a user's demo archive. Replay does not pause for answers, so waiting/resume behavior also has transport regression tests; sponsor-backed live/model verification belongs to the team end-to-end run.

The approved `.github/workflows/frontend.yml` runs unit/screen tests, contract validation, replay integration and production build on PRs to main and changes on main/frontend affecting `frontend/`, `backend/` or `specs/`. It uses pinned action commits, Node 22.14.0 and Python 3.12.10, and requires no secrets or kit mirror. CI will flag schema/fixture drift as teammates land changes.

## Files

- `src/App.tsx`: navigation, audit state, live stream lifecycle, setup, and questions.
- `src/components/`: property discovery, plan/financial detail, tour, geometry, assumptions, and document review.
- `src/lib/api.ts`: typed API adapter and incremental SSE reader.
- `fixtures/`: frontend-owned illustrative house and office runs for three budgets, alongside directly imported shared golden examples.
- `scripts/`: sandbox fixture generation and Pydantic contract verification.

Keep work under `frontend/`. Do not copy sponsor data or `.env` values into fixtures, screenshots, commits, or documentation.

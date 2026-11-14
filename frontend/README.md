# Evergreen frontend

Vinayak's frontend and demo lane, built against `specs/SPEC.md` section 9, schema **0.3.6**. “Evergreen” is a provisional UI name. React 19, TypeScript, Vite; no backend changes.

## Run

```bash
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The app starts in **Demo** with the shared golden house and two office examples from `specs/examples/`, followed by two frontend-owned UI sandboxes with three budget scenarios each. All energy and financial results are clearly marked as illustrative. No API keys, backend, or sponsor assets are needed for this mode.

## Interactive architecture

The welcome screen has a furnished Three.js house with exterior, cutaway, and exploded views. Drag to orbit, scroll/pinch to zoom, or use the labeled buttons for rotation, zoom, reset, and room focus. Selecting a room reveals its floor before moving the camera. The setup and demo audit screens include a smaller interactive explorer. Property-card previews render once, without animation or nested controls.

The welcome house uses the shared house example's energy plan. Hover over highlighted systems or their anchored badges to inspect the proposed change, annual dollar/electricity/gas savings, avoided CO2, upfront cost, payback and caveats. Click/tap a badge or finding to keep its details open; Escape or the close button dismisses them. **Your plan** shows selected upgrades; **All findings** also explains additional and unavailable measures. Only the selected plan supplies the total savings. The demo audit explorer uses that run's results, including budget changes; selected marginal results take precedence over standalone estimates. Raycasting and projected badges follow the model as it rotates and its floors separate. All locations remain conceptual.

Geometry, material textures, furniture and lighting are generated locally. These are **illustrative concept models**, not scans or measurements of the selected properties. Live Matterport tours and evidence pins continue to use the real property SDK. No energy estimates are calculated by the 3D scene.

The renderer loads lazily when visible, pauses rendering offscreen/in background tabs, respects reduced motion for camera/view transitions, and disposes GPU resources when unmounted. If WebGL is unavailable, a fallback keeps the rest of the app usable.

## Demo walkthrough

1. Select **5836 La Mirada Ave**, use its saved budget and role, and start the demo audit. This is the team's shared golden house example.
2. Watch the shared event sequence, including a recoverable tool failure and an electrical-panel question. Choose an answer to resume the saved scenario. Demo answers do not recompute estimates.
3. Open the plan. Expand solar to see cost ranges, payback, NPV, life, incentives, and evidence. Review the explicit high-cost budget warning.
4. Open **Solar & roof** and **Assumptions**. A property without desk candidates shows an empty state rather than invented layout data.
5. In **Documents**, enter illustrative party names, select measures, approve drafting, and export the Markdown preview. Missing terms remain highlighted. Demo documents are unverified interface previews.
6. Return to Properties and run the office marked **Shared contract example** at its saved budget and role. Inspect workspace candidates, financing eligibility and its stated reasons, and the separate property-value estimate. Shared example identity and budgets follow the team's imported files.
7. For the budget-change demo, use the **Silver Lake house** or **Westside workspace** UI sandbox and switch between **$5,000**, **$15,000**, and **$30,000**. These are saved snapshots, not a browser physics calculation.

## Live integration

The development server proxies `/api` to `http://127.0.0.1:8000`. Start the team's FastAPI server, then choose **Connect API**. The app verifies `/api/health` and schema version before switching; it never silently substitutes demo estimates after an API failure. The server controls `AGENT_MODE=replay|live`; connecting does not itself turn on live analysis. Replay returns saved examples, including their original measure selection, even when PATCH changes the request budget.

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
- The SSE endpoint emits JSON `RunEvent` data, either default or named events. Comments, CRLF, fragmented UTF-8, multiline data, and multiple events per chunk are supported. The server replays history from the beginning: the frontend retains a per-run cursor and skips consumed events on reconnect. An active run pauses on a new question, done, or non-recoverable error. If the authoritative run is already complete, it drains the finite history to its end so earlier questions/done events do not hide appended G11 re-plan events. Recoverable errors stay in the stream. It fetches the final run and reconnects after an answer/update. Transport failures expose a reconnect button for the same run. Unknown future event types are ignored.
- Questions may be embedded directly in `event.payload` or under `event.payload.question`; the subsequent `RunResult.questions` is authoritative.
- Structured todo events show backend progress. Approval questions show document/state/scope context and preserve boolean answers.
- Budget and assumption changes are sent to the backend. The UI never recomputes energy or financial results. All displayed estimate ranges come from the returned payloads.
- Public data-quality warnings arrive through `RunResult.warnings`, `BaselineResult.warnings`, fallback/error events, and measure warnings. Fallback detail uses the backend's `fallback`, `layer`, `status`, `what` and `detail` fields. Long warnings expand in full. A `re-run:` warning identifies the earlier narrative as outdated.
- Live role selection supports owner-occupier, landlord, and tenant. Optional utility history requires twelve non-negative monthly values, in kWh (gas as kWh thermal), with an optional first billing month. Office runs accept a requested desk count. Calibration shows per-fuel before/after bias and fit error, failed tolerances and warnings; an absent summary is explicitly uncalibrated.
- Plans follow the backend's operations/load-reduction/equipment/solar order and distinguish `not_cost_effective` from budget exclusions. No browser economics or sizing replaces the selected marginal results.
- `GET /api/runs/{id}/roof` supplies georeferenced planes, panels and detections. Missing/null ortho metadata or failed imagery leaves the supplied geometry visible. Parcel-bound overlays are labelled approximate; detection boxes are not treated as masks or summed footprint area. Workspace defaults to recommended positions and offers a precise position picker.
- `GET /api/templates` always receives both state and property segment. Documents offers only returned types; `template_not_available` is an availability notice. C-PACE scope retains selected marginal sizing and clearly labels additional financing-review measures. Template availability is not eligibility.
- Narrative and document text render as text, not executable HTML. Parties and selected measures require explicit approval before drafting.

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
3. Shared run results and event sequences are discovered under `specs/examples/*/` (currently `house`, `office`, and `office_houston`), without editing or copying the spec files. Additional frontend-owned sandboxes live in `frontend/fixtures/`. Both sources validate against the current Pydantic contract. Shared examples have one saved budget each; arbitrary budget and role changes require the live backend.
4. The financial breakdown and legal checklist depend on the analysis/legal owners. This frontend supplies no production pricing, physics, incentive rules, or statutory contract language.

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

`check_integration.py` runs five checks twice through the actual TypeScript client and FastAPI app: first example replay, then synthetic recordings made from the shared examples in a temporary directory. It covers health/schema, search, results/SSE, budget/assumption updates, replay after PATCH, errors, roof metadata, segment-filtered templates and documents for every shared property. The recorded path exercises the real legal engine, visible blanks/statutory checks and unavailable-template errors. Synthetic recordings are test inputs, not claimed live analyses, and never replace a user's demo archive. Replay does not pause for answers, so waiting/resume behavior also has transport regression tests; sponsor-backed live/model verification belongs to the team end-to-end run.

The approved `.github/workflows/frontend.yml` runs unit/screen tests, contract validation, replay integration and production build on PRs to main and changes on main/frontend affecting `frontend/`, `backend/` or `specs/`. It uses pinned action commits, Node 22.14.0 and Python 3.12.10, and requires no secrets or kit mirror. CI will flag schema/fixture drift as teammates land changes.

## Files

- `src/App.tsx`: navigation, audit state, live stream lifecycle, setup, and questions.
- `src/components/`: property discovery, plan/financial detail, tour, geometry, assumptions, and document review.
- `src/lib/api.ts`: typed API adapter and incremental SSE reader.
- `fixtures/`: frontend-owned illustrative house and office runs for three budgets, alongside directly imported shared golden examples.
- `scripts/`: sandbox fixture generation and Pydantic contract verification.

Keep work under `frontend/`. Do not copy sponsor data or `.env` values into fixtures, screenshots, commits, or documentation.

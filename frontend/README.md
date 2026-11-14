# Evergreen frontend

Vinayak's frontend and demo lane, built against `specs/SPEC.md` section 9, schema **0.1.0**. “Evergreen” is a provisional UI name. React 19, TypeScript, Vite; no backend changes.

## Run

```bash
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The app starts in **Demo** with clearly labeled, invented fixtures for a Los Angeles house and Houston office. No API keys, backend, or sponsor assets are needed for this mode. The illustrations are SVGs created for this UI.

## Demo walkthrough

1. Select **Silver Lake house**, choose **$15,000**, and start the demo audit.
2. Watch the activity stream pause for an insulation question. Choose either answer to resume the saved scenario. Answers do not alter the fixture's estimates.
3. Open the plan. Expand solar to see cost ranges, payback, NPV, life, incentives, and evidence.
4. Change the cash budget to **$5,000**; the saved selection changes to the affordable upgrades. Demo budgets are preset snapshots, not a browser physics calculation.
5. Open **Solar & roof**, **Workspace**, and **Assumptions**. Select desk positions to compare scores.
6. In **Documents**, enter illustrative party names, select the measures, approve drafting, and export the marked-up Markdown preview. Missing terms stay highlighted. Demo documents are explicitly unverified previews.
7. Return to Properties and run **Westside workspace**. Expand a priced measure for the illustrative C-PACE scenario and eligibility notes.

## Live integration

The development server proxies `/api` to `http://127.0.0.1:8000`. Start the team's FastAPI server, then choose **Live data**. The app verifies `/api/health` and schema version before switching; it never silently substitutes demo estimates after an API failure.

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
- The SSE endpoint emits JSON `RunEvent` data, either default or named events. Comments, CRLF, fragmented UTF-8, multiline data, and multiple events per chunk are supported. A `question`, `done`, or `error` ends the frontend listener; it fetches the final run and reconnects after an answer/update. Transport failures expose a reconnect button for the same run.
- Questions may be embedded directly in `event.payload` or under `event.payload.question`; the subsequent `RunResult.questions` is authoritative.
- Budget and assumption changes are sent to the backend. The UI never recomputes energy or financial results. All displayed estimate ranges come from the returned payloads.
- Live role selection supports owner-occupier, landlord, and tenant. Optional utility history requires twelve non-negative monthly values, in kWh (gas as kWh thermal).
- Narrative and document text render as text, not executable HTML. Parties and selected measures require explicit approval before drafting.

### Matterport

The tour embeds the real `sid` in live mode. A valid domain-allowlisted `MATTERPORT_SDK_KEY` enables session-only evidence pins and camera control. Coordinates are converted from Model API `(x,y,z)` to Showcase `(x,z,-y)`. A panorama ID is matched to a published sweep `sid` or `uuid` before `Sweep.moveTo`; it is never assumed to match. Otherwise the SDK can navigate to the session tag, or the UI reports the unavailable location.

Verified integration references:

- [Embed quickstart and current bootstrap module](https://matterport.github.io/developer-docs/embed-sdk/quickstart/)
- [Coordinate systems and API/SDK conversion](https://developers.matterport.com/overview/concepts/)
- [Mattertag add and session-only persistence](https://matterport.github.io/developer-docs/reference/mattertag/)

SDK behavior on the sponsor models remains unverified until the local `.env` and real run payloads are available. `gh` is not authenticated in this environment; the connected GitHub integration can read the board.

### Shared contract gaps to resolve with the owners

1. The public API returns `PropertySummary` and `RunResult`, but currently exposes no `PropertyBundle`/floorplan/orthophoto endpoint. Roof and workspace screens therefore draw supplied geometry and candidate positions. Aerial image overlays and a real floorplan background need a bundle route (plus georeferenced image bounds for alignment).
2. Window/roof anchors and SDK sweep identity need validation on the two real golden properties.
3. The master spec references `specs/examples/`, but those files were not present in the fetched draft. Temporary frontend-owned fixtures live in `frontend/fixtures/` so they do not collide with Yale's active spec work. They validate against the exact Pydantic contract. Import the shared runs with `npm run sync:fixtures` when they land.
4. The financial breakdown and legal checklist depend on the analysis/legal owners. This frontend supplies no production pricing, physics, incentive rules, or statutory contract language.

## Checks

```bash
npm test
npm run build
# Uses an isolated ephemeral environment; requires uv.
uv run --with 'pydantic>=2,<3' python scripts/check_contract.py
```

`npm test` covers SSE framing and termination, backend error handling, answer value preservation, fixture budget/totals, WKT parsing, and verified sweep matching. `check_contract.py` extracts the team's actual Pydantic block without editing it and validates every saved run. `scripts/make_fixtures.py` regenerates invented examples; it is not an analysis engine.

## Files

- `src/App.tsx`: navigation, audit state, live stream lifecycle, setup, and questions.
- `src/components/`: property discovery, plan/financial detail, tour, geometry, assumptions, and document review.
- `src/lib/api.ts`: typed API adapter and incremental SSE reader.
- `fixtures/`: illustrative complete house and office runs for three budgets.
- `scripts/`: fixture generation, shared-example import, and Pydantic contract verification.

Keep work under `frontend/`. Do not copy sponsor data or `.env` values into fixtures, screenshots, commits, or documentation.

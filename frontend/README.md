# Evergreen frontend

Vinayak's frontend and demo lane, built against `specs/SPEC.md` section 9, schema **0.2.0**. “Evergreen” is a provisional UI name. React 19, TypeScript, Vite; no backend changes.

## Run

```bash
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The app starts in **Demo** with the shared golden house and office examples from `specs/examples/`, followed by two frontend-owned UI sandboxes with three budget scenarios each. All energy and financial results are clearly marked as illustrative. No API keys, backend, or sponsor assets are needed for this mode. The illustrations are SVGs created for this UI.

## Demo walkthrough

1. Select **5836 La Mirada Ave**, use its saved **$14,000** scenario, and start the demo audit. This is the team's shared golden house example.
2. Watch the shared event sequence, including a recoverable tool failure and an electrical-panel question. Choose an answer to resume the saved scenario. Demo answers do not recompute estimates.
3. Open the plan. Expand solar to see cost ranges, payback, NPV, life, incentives, and evidence. Review the explicit high-cost budget warning.
4. Open **Solar & roof** and **Assumptions**. A property without desk candidates shows an empty state rather than invented layout data.
5. In **Documents**, enter illustrative party names, select measures, approve drafting, and export the Markdown preview. Missing terms remain highlighted. Demo documents are unverified interface previews.
6. Return to Properties and run **Suite A - 2,000SF** at its saved **$3,500** landlord scenario. Inspect workspace candidates, the financeable rooftop unit's C-PACE scenario, and the separate property-value estimate.
7. For the budget-change demo, use the **Silver Lake house** or **Westside workspace** UI sandbox and switch between **$5,000**, **$15,000**, and **$30,000**. These are saved snapshots, not a browser physics calculation.

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
- The SSE endpoint emits JSON `RunEvent` data, either default or named events. Comments, CRLF, fragmented UTF-8, multiline data, and multiple events per chunk are supported. A `question`, `done`, or non-recoverable `error` ends the frontend listener; recoverable errors stay in the event stream. It fetches the final run and reconnects after an answer/update. Transport failures expose a reconnect button for the same run. Unknown future event types are ignored.
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
3. The shared `specs/examples/house` and `office` run results and event sequences are imported directly, without editing or copying the spec files. Additional frontend-owned sandboxes live in `frontend/fixtures/`. Both sources validate against the current Pydantic contract. Shared examples have one saved budget each; arbitrary budget and role changes require the live backend.
4. The financial breakdown and legal checklist depend on the analysis/legal owners. This frontend supplies no production pricing, physics, incentive rules, or statutory contract language.

## Checks

```bash
npm test
npm run build
# Uses an isolated ephemeral environment; requires uv.
uv run --with 'pydantic>=2,<3' python scripts/check_contract.py
```

`npm test` also renders the shared examples through the actual screen components to check optional fields, empty states, document gating, and separation of property value from energy savings. It covers SSE framing and termination, backend error handling, answer value preservation, fixture budget/totals, WKT parsing, and verified sweep matching. `check_contract.py` extracts the team's actual Pydantic block without editing it and validates every saved run, plus the shared property bundles, building models, documents, and event streams. When `backend/schema.py` exists, it checks that the actual backend schema agrees with the spec and validates against both. `scripts/make_fixtures.py` regenerates invented examples; it is not an analysis engine.

## Files

- `src/App.tsx`: navigation, audit state, live stream lifecycle, setup, and questions.
- `src/components/`: property discovery, plan/financial detail, tour, geometry, assumptions, and document review.
- `src/lib/api.ts`: typed API adapter and incremental SSE reader.
- `fixtures/`: frontend-owned illustrative house and office runs for three budgets, alongside directly imported shared golden examples.
- `scripts/`: sandbox fixture generation and Pydantic contract verification.

Keep work under `frontend/`. Do not copy sponsor data or `.env` values into fixtures, screenshots, commits, or documentation.

# Handoff: continue the spec on another computer

Written 2026-11-13 about 11:10 PM ET. The first computer's Claude account hit its usage limit mid-task. This file carries everything needed to finish the spec from a different computer and account. Delete it once the spec is complete.

**Superseded in part, 2026-11-14.** The Data lane has since verified the sponsor data live. Where this file and `specs/data-integration.md` disagree, that file is right. Known stale statements here: the CoStar kit is 49 MB with JSONL datasets and no `commercial-property/` folder; the CoStar join is direct on `MatterportModelId`, not through `models_index.csv`; the Model API does return the rotation to north (`Model.geocoordinates`) and wall openings (`Edge.openings`).

## 1. Resume in five steps

1. Get the branch:

   ```bash
   git fetch origin && git checkout spec-draft
   ```

2. Check board access for the account on this computer (it must be a collaborator on the repo):

   ```bash
   gh auth status && tools/board whoami
   ```

3. Get `.env` onto this computer. It is **not** in git and must never be: this repo is public. Either copy the `.env` file from the first computer directly (AirDrop, USB, password manager), or run `/costar-keys` in the track Discord again and fill in a copy of `.env.example`. See "Keys" below.
4. Open Claude Code in the repo and paste the prompt in section 2.
5. When all files in section 3 are done, post on the board and delete this file.

### Keys

- The team has four key sets, one per teammate. In `.env` the unsuffixed names are the default set (A); the others use the suffixes `_B`, `_C`, `_D`.
- Checked 2026-11-13 with one read-only request each: sets A, B and C work for both Matterport (14,944 models visible) and Vexcel. Set D was transcribed from a screenshot and is rejected (HTTP 403); its owner needs to re-copy it as text.
- The CoStar kit is one zip of about 52 MB, the same for everyone. Its download link is signed and expires about 24 hours after issue: the links in `.env` stop working around 10:30 PM ET on 2026-11-14. Download the zip once and set `COSTAR_KIT_ZIP`. A fresh link comes from `/costar-keys`.
- `ANTHROPIC_API_KEY` has not been provided yet.
- To add to `data-integration.md`: a plan for spreading bulk harvesting across the key sets, since each set has its own rate limit (one key set per harvest worker; interactive runs always use the default set).

## 2. Prompt to paste

```text
Read specs/HANDOFF.md, specs/handoff-plan.md and specs/SPEC.md, then finish the spec.
This is spec writing only: no application code. Work through the "Remaining work"
list in HANDOFF.md in order. Follow the double-check protocol in handoff-plan.md for
physics and legal: write from opened primary sources, re-verify after drafting, and
list anything you could not confirm as unverified instead of including it silently.
Keys are in .env; do the [P] data checks before writing data-integration.md.
Touch only files under specs/. Do not commit or push unless I ask.
```

## 3. State of the work

| File | State |
|---|---|
| `.gitignore` | done: ignores `.env`, local agent config, `mp_out/`, `data/cache/` |
| `specs/SPEC.md` | drafted, complete first version including the shared contract. The contract code block has **not** been run through Pydantic yet |
| `specs/handoff-plan.md` | the plan the team lead approved; the source of truth for scope and decisions |
| `specs/data-integration.md` | not started. Raw findings are in section 5 below |
| `specs/workplan.md` | not started. Its outline is in `handoff-plan.md`, deliverable 5 |
| `specs/examples/` | not started |
| `specs/physics.md` | not started. A side session read sources for solar position, irradiance, PV and infiltration, then hit the usage limit; its notes did not reach the repo. Start from the brief in section 6 |
| `specs/legal.md` | not started. A side session finished a first read of California and Texas statutes; the California findings are in section 7. Texas findings did not reach the repo |
| Board post | not sent |

Nothing is committed to `main`. `AGENTS.md` has an older uncommitted local change on the first computer that is unrelated to this work and is not on this branch.

## 4. Remaining work, in order

1. **Data checks with keys** (read-only, downloads outside the repo):
   - Matterport key check; one residential model (`zvKHR9DHNjJ`) and one office suite (for example `HjEyXryhRLk`, "Suite A - 2,000SF", Houston, CoStar property id 354635).
   - GraphQL introspection: is there any field giving the model's orientation to north, and what `edges.type` values exist besides `wall` (doors, windows, openings)?
   - Vexcel on both lots: `property/extract` with `include=precomputed` (save the full attribute key list), then `include=calculated` once for roof height; `oriented/collections`; `elements/detect` with `"model": "sam3"` and roof labels.
   - CoStar kit: list the zip, read `index.md`, the header of `residential-listings.csv`, and one `commercial-property/*<id>*.json`. Find the fields for property type, year built, building class, area, stories. Use HTTP range requests; the kit is 160 MB.
   - Showcase SDK: how to add a tag and move the camera, and whether SDK sweep ids equal Model API pano ids.
2. Write `specs/data-integration.md` per `handoff-plan.md` deliverable 2. Replace each `[P]` in `SPEC.md` that the checks resolved, and fill the normalised fields in `CostarData`.
3. Write `specs/workplan.md` per deliverable 5: lanes, rules, work packages (D, A, G, F series with tier, input and output types, fixture, acceptance test), sub-lanes per person, board post types, checkpoints, a proposed `CODEOWNERS`.
4. Write `specs/examples/` for one house and one office: `property_bundle`, `building_model`, `run_result`, `document_request`, `document_draft`. Mark invented numbers as illustrative. Extract the block between `<!-- contract:start -->` and `<!-- contract:end -->` in `SPEC.md`, load it with Pydantic v2, and validate every example against it. Fix the contract if it fails to import.
5. Write `specs/physics.md` using the brief in section 6.
6. Write `specs/legal.md` using the brief in section 7. Bind each placeholder to a contract type from `SPEC.md` section 9.
7. Double-check pass on physics and legal, then re-read `SPEC.md` for anything the other files changed (uncertainty method, setbacks, economic defaults, incentive status).
8. Post one short board note that the spec and shared contract landed, including the proposed ownership additions (`backend/legal/` to @Sri-SriPod, `specs/examples/` to @yalexie1) for the team to confirm. Do not edit `AGENTS.md`.

## 5. Research already done (for `data-integration.md`)

Sponsor documents, all public, re-download as needed (hackathon-only licence, never commit them):

| What | URL |
|---|---|
| Track site config (brief, judging criteria, resource links) | `https://beta-app.matterport.com/2026-princeton-hackathon/assets/config.json` |
| Matterport data reference (every query with a real response) | `https://static.matterport.com/hackathon/26.15.35-main-35-g24e0220/assets/quickstart/reference.html` |
| Same folder: `matterport_quickstart.py`, `models_index.csv`, `AGENTS.md`, `basemap.json` | replace `reference.html` in the URL above |
| Vexcel tutorial PDF and script | `https://beta-app.matterport.com/2026-princeton-hackathon/api/assets/doc/Vexcel_API_Hackathon_Tutorial.pdf` and `.../vexcel_quickstart.py` (follow redirects) |
| Model API reference | `https://static.matterport.com/api-doc/2026.06.68-main-g3a4e710/reference/graphdoc/model/index.html` |
| Showcase SDK docs | `https://matterport.github.io/developer-docs/overview/` |

The build id in the static URL may change; it is the version in the track site's `main.js` script URL.

**Matterport** (from the sponsor's reference page and agent notes, 2026-11-13):

- `POST https://api.matterport.com/api/models/graph`, GraphQL, HTTP basic auth with key as user and token as password. Production only. Keep well under 10 requests per second; keys are shared.
- Null fields are omitted, not sent as null. Signed asset links expire; re-query instead of caching URLs.
- Rooms: `rooms { id floor { id } classifications { label confidence } boundary { edges { id } } dimensions(units: metric) { areaFloor width depth height } }`. Some rooms lack width, depth or height.
- Walls: `floors { id label vertices { id position { x y } } edges { id type thickness vertices { id } } }`, metres, same frame as panoramas, z up.
- Panoramas: `panoLocations { id label position { x y z } skybox(resolution: "2k") { status children } }`, six cube faces in the order up, four sides, down; `4k` also works.
- Defurnished: `view(type: "matterport.model.defurnished") { id }`, then query `model(id: <view id>)`; pano ids match. 6,979 models have one.
- Floor plans: `assets { floorplans(provider: "matterport") { format flags url width height resolution origin { x y } } }`, plus a DXF.
- MatterPak: `bundle(id: "mp:matterpak") { availability }` and `assets { resources(format: "matterpak") { status filename url } }`. Zip with `cloud.xyz` and an OBJ mesh. Unlocked for the 232 splat models, being unlocked for the rest.
- Splats and drone photos come from the track site, not the Model API: `GET <site>/api/models/<sid>` lists files; `GET <site>/resources/<sid>/<file>` redirects to a one-hour signed link. Splat frame is local, z up, **not north-aligned**; drone photo GPS and gimbal angles are in the JPEG XMP block (first 48 KB).
- No geographic search in the API; use `models_index.csv`. Mattertags were empty on models the sponsor checked.

**`models_index.csv` profile** (computed 2026-11-13): 14,944 rows; 13,014 commercial and 1,930 residential; Houston about 7,700 and Los Angeles about 5,600, the rest blank city; splats on 211 residential and 21 commercial; `costar_property_id` on 6,191 commercial rows; `homes_listing_id` on 1,920 residential rows; defurnished on 1,824 residential and 5,155 commercial; 13,121 are single-floor. `internal_id` prefixes: numeric 6,172, `Apartments-` about 3,070, `Homes-` about 1,940, `Loopnet-` about 210, `Tenx-` 88, blank about 2,700. The `state` column is dirty (`TX`, `Texas`, `Tx`, `CA`, `Ca`, `California`, blanks) and needs normalising. Most "commercial" rows are apartment units.

**CoStar kit** (from the quickstart code, untested by the sponsor): one password-protected zip, about 160 MB, containing `index.md`, `residential-listings.csv`, and `commercial-property/` with one JSON per property whose file name contains the CoStar property id. Residential models join on `homes_listing_id`; commercial models on `costar_property_id`.

**Vexcel** (from the tutorial, base `https://api.vexcelgroup.com/v2`, header `X-API-KEY`, Houston and Los Angeles only):

- WKT is longitude first. Always send `srid=4326`. Layers: pass `urban,urban-r,wide-area,urban-g`; obliques exist only in `urban`.
- `GET /property/extract`: parcel polygon plus 80+ attributes as flat dotted keys, and a `structures` list. Seen keys: `metadata.collection`, `structure.count`, `parcel-tree-cover.percent`, `pool.detected`, `building-type.class`, `footprint.area`, `roof-characteristics.material.class`, `roof-characteristics.shape.value`, `roof-characteristics.condition`, `roof-defects.*`, `roof-objects.chimney.count`, `primary-structure`. `include=precomputed` returns everything stored; `include=calculated` adds roof height and elevation but is slow; `include=footprint-wkt` exists. Filters such as `roof-solar=true` and `roof-material=metal` work. 404 means no parcel at that point.
- `POST /ortho/extract` and `POST /oriented/extract` return image bytes; 1,024-tile cap per extract. `GET /oriented/collections` says which oblique directions exist. `GET /oriented/query` lists raw images with camera positions.
- `POST /elements/detect`: open-vocabulary detection that **runs SAM 3 server-side** (`"model": "sam3"`, `detection-threshold`), on ortho and oblique images, returning map-coordinate boxes and pixel masks. This is how the roof segmentation is done: no GPU, and imagery stays inside the sponsor's API. Specific labels work better than vague ones; several seconds per request.
- `POST /embedding/extract`: semantic search over pre-computed tile embeddings (text, location, image or vector query).
- 429 means too fast: exponential backoff.

**Agent framework** (LangChain docs read 2026-11-13, plus field notes): see `SPEC.md` section 8 build notes.

## 6. Brief for `specs/physics.md`

Modules: solar position; irradiance decomposition and transposition; PV production, cell temperature, losses, and shading by ray casting; envelope conduction and U-values including ground contact; a simple hourly zone thermal model; infiltration and ventilation; window solar gain; daylight and glare for scoring desk positions; thermal comfort; HVAC and water-heating efficiency; lighting and plug loads with HVAC interaction; life-cycle economics (NPV, SIR, IRR, payback, escalation); emissions for the Los Angeles and Houston grid regions and for gas; measurement and verification; uncertainty propagation from input ranges to the low/expected/high result. Also needed by `SPEC.md`: vintage default tables for envelope and systems by era and climate zone, roof pitch ranges by roof shape, fire-code setbacks for panels, and economic defaults.

Entry format: equation; symbols with SI units; validity range; primary citation (paper DOI or standard clause); a second independent source; a worked numeric example recomputed by a script that was actually run; the tool-function name it maps to.

Candidate sources, to verify and not to trust from memory: NREL SPA (Reda and Andreas 2004), Erbs 1982, Perez 1990, PVWatts v5 (Dobos 2014), ISO 13790 and ISO 52016-1, ISO 6946, ISO 13370, Sherman and Grimsrud 1980, ASHRAE Handbook of Fundamentals, ISO 7730, NIST Handbook 135, EPA eGRID, ASHRAE Guideline 14, IPMVP, ASHRAE Standard 140. Use pvlib and PVWatts as reference implementations for the test plan.

End with an "Unverified, do not implement" list and a verification log table.

## 7. Brief for `specs/legal.md`, and California findings so far

Five documents for California and Texas: retrofit construction contract (residential and commercial versions), solar installation agreement, contractor bid package, energy savings guarantee addendum, C-PACE package (commercial only, tied to the SIR). For each: purpose, section structure, clause library in original contract language (no copied form text), state-required terms with citations, state differences. Use `{{snake_case}}` placeholders and end with a placeholder table, an "Unverified, needs attorney check" list, and a verification log. Every draft carries a "draft for attorney review, not legal advice" notice; the drafting agent leaves a visible blank rather than inventing a party, licence number or legal description.

The California official site (`leginfo.legislature.ca.gov`) blocks `curl` with a JavaScript challenge; read it through a browser tool. The Texas site (`statutes.capitol.texas.gov`) works with `curl`.

**First-pass findings from the side session, read from official text on 2026-11-13. They have had no second verification pass: re-open each section before relying on it.**

Home improvement contracts, Business and Professions Code:
- §7159 (last amended effective 2026-01-01): heading "Home Improvement" in at least 10-point bold; statement that the owner is entitled to a fully signed copy before work starts; down payment may not exceed $1,000 or 10% of the contract price, whichever is less, stated in 12-point bold; progress payment notice in 12-point bold that it is against the law to collect for work not yet completed or materials not yet delivered; mechanics lien warning with statutory wording; change orders in writing and signed before the work they cover; unconditional lien release owed on partial payment; cancellation right of three business days, five for senior citizens, seven for certain disaster repairs.
- §7159.5: the down payment cap restated, with criminal penalties; contractors who furnish qualifying bonds are exempt from the cap and schedule rules.
- §7159.6: a change order is unenforceable unless it states scope, price change, and effect on payments or completion date.
- §7151: "home improvement" expressly includes solar energy systems on residential property, so a residential solar agreement must also meet home improvement contract law.
- §7030(b) and §7030.5: Contractors State License Board notice in at least 12-point type; licence number on all contracts and bids.
- §7159.2: no security interest in real property for contracts of $5,000 or less, other than a mechanics lien.
- §7163: a contract conditioned on third-party financing is unenforceable unless the lender agrees, the buyer accepts, and the buyer does not rescind within the federal rescission period.
- §7048: licensing chapter does not apply under $1,000 where no permit is needed.
- §7031: an unlicensed contractor cannot sue for payment and the owner can recover what was paid.
- §7191: an arbitration clause in a contract for residential property of four units or fewer must be titled "ARBITRATION OF DISPUTES" and sit immediately before the signature line with the statutory warning.
- §7159.1: door-to-door contracts secured by a lien on the home need an 18-point bold warning.
- §7125 (workers' compensation certificate): could **not** be retrieved; unverified.

Solar, Business and Professions Code §7169: a disclosure document developed with the Public Utilities Commission must be given before sale, financing or lease, on the front page in 16-point bold, covering total cost, complaint contacts and cancellation rights; it must be in the language of the sales presentation; for PACE-financed solar the PACE financing disclosure satisfies it for the financing contract only.

Cancellation, Civil Code §§1689.5 to 1689.7 and 1689.13 (amended effective 2026-01-01): three business days, five for seniors; a "Three-Day Right to Cancel" statement in at least 12-point bold next to the signature line; emergency waiver only by a separate dated statement in the buyer's own words.

Payment and liens, Civil Code:
- §8811 (new, effective 2026-01-01): retention on private works is capped at 5% of each progress payment and 5% of the contract price, with exceptions.
- §8800: owner pays the direct contractor within 30 days of a payment notice; may withhold up to 150% of a disputed amount; 2% per month penalty.
- §8812 and §8818: retention due within 45 days of completion; 2% per month penalty.
- §8204: preliminary notice within 20 days of first furnishing work.
- §2782 and §2782.05: indemnity for a party's own sole negligence or wilful misconduct is void; limits on subcontractor-to-general indemnity.
- Business and Professions Code §7108.5: prime contractor pays subcontractors within 7 days of receiving a progress payment.

Texas sections the side session fetched but whose findings did not reach the repo, as a reading list only: Property Code chapters 27, 28, 41, 53, 162; Business and Commerce Code chapters 59, 113, 115, 272, 601; Occupations Code chapters 1302, 1305, 1805, 1806; Local Government Code chapter 399 (the PACE Act); Utilities Code chapter 39; Insurance Code chapter 151; Texas Constitution article XVI; the Texas PACE Authority's program guide, technical standards and owner FAQ; the state licensing agency's pages on residential solar retailers.

Federal incentives, from secondary sources only, unverified: residential credits under sections 25C and 25D ended for 2025; section 179D ends for construction beginning after June 30, 2026; section 48E is cut off for solar that begins construction after July 4, 2026 unless placed in service by the end of 2027.

# Data integration

Status: v0.1, 2026-11-14. Owner: @vigjay (Data lane). Companion to `specs/SPEC.md`.

Scope confirmed on the board (`#6871828669`): the Data lane and this file are mine. `specs/physics.md`, `specs/legal.md`, `specs/workplan.md`, `specs/examples/` and the contract block in `SPEC.md` are @yalexie1's.

Verification tags, as in `SPEC.md`: **[V]** verified against a primary source on the date given, **[P]** pending a live check, **[U]** second-hand, do not build on it.

> **Where this file disagrees with `SPEC.md` §3, §9 or §16, this file is the verified one.** Those sections were written from the sponsor's quickstart code, which the sponsor had not tested. The five corrections are listed in §7 and have been raised on the board for the contract freeze.

---

## 1. Keys

Four key sets live in a git-ignored `.env`: the unlabelled set plus `_B`, `_C`, `_D`. [V] 2026-11-14

| Set | Matterport | Vexcel | CoStar kit URL |
|---|---|---|---|
| (unlabelled) | 200 OK | 200 OK | 206 OK |
| `_B` | 200 OK | 200 OK | 206 OK |
| `_C` | 200 OK | 200 OK | 206 OK |
| `_D` | **403 `invalid key/secret`** | absent | absent |

- Set `_D` is the screenshot-copied set the board flagged. It is both **invalid and incomplete** — never assign it. It needs re-sharing as text.
- `ANTHROPIC_API_KEY` is **missing from `.env`** entirely, though `SPEC.md` §12 requires it for the Agent lane and Analysis vision. [V]
- Variable names: `MATTERPORT_API_KEY`, `MATTERPORT_API_TOKEN`, `MATTERPORT_SDK_KEY`, `VEXCEL_API_KEY`, `COSTAR_KIT_URL`, `COSTAR_ZIP_PASSWORD` (shared across sets), `ANTHROPIC_API_KEY`.
- **One key set per concurrent agent, three agents maximum.** The keys are shared across the whole hackathon. Matterport must stay well under 10 req/s; Vexcel returns 429 and needs exponential backoff.
- No key value ever goes in a commit, a log, a fixture, a cache entry, or chat.

---

## 2. CoStar data kit

### 2.1 The file

- `51,700,855` bytes (~49 MB). [V] **`SPEC.md`'s "about 160 MB" is wrong.**
- `COSTAR_KIT_URL` is a **presigned S3 link** (`mp-app-qa.s3.amazonaws.com`, `X-Amz-Expires=86400`), signed `20261114T033003Z`, 24-hour window → **expires 2026-11-15 03:30 UTC (2026-11-14 22:30 EST)**. [V]
- `Accept-Ranges: bytes` works. `HEAD` returns 403 (the signature is GET-only). First four bytes `PK\x03\x04`. [V]
- Password-protected with `COSTAR_ZIP_PASSWORD`; 42 of 47 entries encrypted; Python stdlib `zipfile` decrypts it (ZipCrypto, not AES). [V]
- **Mirrored and verified 2026-11-14**: `data/cache/costar/kit.zip` (sha256 `7d55212dfe0174af6772495d8f31a690304f33328053e0477bc0edbbf290dba6`, 47 entries, 42 encrypted), extracted to `data/cache/costar/kit/` (404 MB). Both git-ignored. **Read the mirror; never re-download.** Once the URL expires the mirror is the lane's single hardest dependency — if it is missing after that, the sponsor must re-share the kit.
- To read from a URL without downloading 49 MB: hand a seekable HTTP-range file object to `zipfile.ZipFile`. It reads only the central directory plus the member requested — the full entry listing and `index.md` cost **5.7 KB and 49 KB** respectively. [V]

### 2.2 Layout

**There is no `commercial-property/` folder of per-property JSON files.** [V] `SPEC.md` and `HANDOFF.md` both describe one; the kit does not have one.

| Path | What it is |
|---|---|
| `index.md` | the kit's own documentation — read first |
| `commercial-properties.csv` | starter list: `PropertyId,MatterportModelId,Address,City,State` |
| `residential-listings.csv` | starter list: `ListingId,ResidentialListingId,MatterportModelId,Address,City,State` |
| `data/*.jsonl` | 8 datasets, one record per line |
| `schemas/` | JSON Schema per dataset, `openapi.yaml` (665 KB), `enums.json` (118 KB) |
| `models/` | one field-reference page per dataset: every field, its meaning, allowed values |
| `concepts/` | 12 domain pages: glossary, metrics and formulas, property types, apartments, leasing, tenants, sale comps, residential sales, geography, valuation, hotels and land, data quality |
| `tools/expand_records.py` | writes records out as pretty JSON for browsing |

**`models/` and `schemas/` are authoritative for field names — read them before writing a field access.** Their existence closes the "CoStar kit columns unknown until opened" risk in `SPEC.md` §16 outright. [V]

### 2.3 Datasets

| Dataset | File | Records | Size | Key | Used by |
|---|---|---|---|---|---|
| Commercial property | `data/commercial-property.jsonl` | 3,339 | **193 MB** | `id` = `PropertyId` | D1 — vintage, type, area, class |
| Commercial listing summary | `data/commercial-listing-summary.jsonl` | 1,022 | 14 MB | `id` | D10 |
| Location occupancy | `data/location-occupancy.jsonl` | 74,093 | 69 MB | `id` | **D10 — occupancy schedules** |
| Company detail | `data/company-detail.jsonl` | 49,575 | 42 MB | `id` | **D10 — employee counts → plug loads** |
| Commercial sale comp | `data/commercial-sale-comp.jsonl` | 6,120 | 23 MB | `id` | **D10 — value uplift** |
| Apartment listing | `data/apartment-listing.jsonl` | 1,747 | 6 MB | `id` | D10 — asking rents |
| Residential listings | `data/residential-listings.jsonl` | 2,120 | 45 MB | `id` = `ListingId` | D1 — home flow |
| Residential listing features | `data/residential-listing-features.jsonl` | 1,899 | 28 MB | `id` | D10 |

`commercial-property.jsonl` is 193 MB — **stream it line by line and index what you need; never load it whole.**

### 2.4 The join — direct, no `models_index.csv` hop

[V] 2026-11-14

- `commercial-properties.csv`: **13,147 rows, 3,339 unique `PropertyId`.** One row per (property, model) — a property scanned several times has several rows. 51 properties have an empty `MatterportModelId`.
- `residential-listings.csv`: **2,224 rows, 2,120 MLS listings, 1,867 homes.** `ResidentialListingId` groups the listings of one sale or rental.
- `PropertyId` → `id` in `data/commercial-property.jsonl`. `ListingId` → `id` in `data/residential-listings.jsonl`.
- City split: Houston 7,154, Los Angeles 5,970, `LOS ANGELES` 14, `houston` 9. **Normalise city and state** — the index's `state` column is dirty the same way (`TX`/`Texas`/`Tx`, `CA`/`Ca`/`California`, blanks).

**Do not use the `homes_listing_id` / `costar_property_id` path via `models_index.csv` that `SPEC.md` §9 describes.** It is the join the sponsor marked untested, and the kit ships a direct `MatterportModelId` join with better coverage.

Model ids also appear inside the records as `videoKey` on attachments and media; an item is a Matterport model when `videoExternalReferenceType` (or `externalReferenceType` on residential media) is **36** (MatterportScan) or **234** (MatterportStreamingKey). Join on the key and the model id together.

> `index.md` states: *"How to connect to the Matterport models is provided in a separate zip file."* **We may be missing a second zip.** Raised on the board. [V] quote, [P] whether a second zip exists.

### 2.5 Field rules that are easy to get wrong

[V] from `models/commercial-property.md` and `schemas/enums.json`

- **`yearBuilt` is not a scalar.** Years live in `constructionEvents[]` keyed by `ConstructionEventType`: 1 GroundBreaking, **2 ConstructionComplete**, 3 RenovationBegun, 4 RenovationFinished, 5 CommonAreaRenovated, 6 Demolished, 7 Converted, 17 Redeveloped. `year` can be approximate, `month` is often empty, and a property can carry several events. Prefer `ConstructionComplete` and record which event was used — vintage drives every envelope and systems default in `physics.md`.
- **Two area fields.** `grossBuildingAreaSquareFeet` (GBA, to the outside of exterior walls) → **use for the envelope**. `rentableBuildingAreaSquareFeet` (RBA, inside the walls, excluding vertical shafts) → leasing and vacancy only. Do not mix them.
- **`propertyType` integer enum**: 0 Unknown, 1 Hospitality, 2 Industrial, 3 Land, **5 Office**, 6 GeneralRetail, 7 Flex, 8 SportsAndEntertainment, 9 MixedUse, 10 Specialty, 11 Multifamily, 13 Healthcare, 14 PropertyTypeUnknown, 15 Residential, 16 Homes. **The office flow selects `propertyType == 5`**, not the index's "commercial" segment — most commercial models are apartment units (`SPEC.md` §3.2 is right about the problem, and this is the fix).
- `propertySubtype` refines the type; pick `propertyType` first and expect other subtype blocks to be null.
- **`buildingClass` integer enum**: 0 Unknown, 1 A, 2 B, 3 C, 4 F. Market-relative and subjective — not a national rating. `buildingRating` is the national one.
- **`constructionStatus`**: 0 Unknown, **1 Existing**, 2 Demolished, 3 Proposed, 4 UnderConstruction, 5 UnderRenovation, 11 UnderRedevelopment, 12 Redeveloped. Filter to Existing for standing inventory.
- Geography joins on ids (`cityId`, `countyId`, `stateId`, `researchMarketId`, `primarySubmarketId`), never on names.
- 4 residential listings have an empty address (hidden from the public); 228 are not public on Homes.com — `permissionLevels.homes` tells them apart.
- Photos: every published attachment with a file location carries `attachmentUri` at size `/112/` (up to 1880×900). Swap the segment for `/113/` (1400×720) or `/116/` (2048×2048). 140,677 attachments on 3,337 properties. A vision input nobody has claimed yet.

### 2.6 Golden properties

[V] both confirmed present in the kit, 2026-11-14

- **Office**: `PropertyId 354635` = 9050 Emnora Ln, Houston, TX. Three models: `B9b1hGuh61v`, `HjEyXryhRLk`, `cpBz4ivmcTN`.
- **House**: Matterport `zvKHR9DHNjJ` = 5836 La Mirada Avenue, Los Angeles, CA. Residential — correctly absent from `commercial-properties.csv`. Its row: `ListingId 235967170`, `ResidentialListingId 221139020`. [V]

---

## 3. Matterport Model API

### 3.1 Transport

- `POST https://api.matterport.com/api/models/graph`, GraphQL, HTTP basic auth: key as user, token as password. [V]
- Production only. Well under 10 req/s; keys are shared. [V]
- Null fields are **omitted, not sent as null** — code for absent keys. [V]
- Signed asset URLs expire. **Re-query for a fresh URL; never cache a URL.** Cache bytes instead. [V]
- 266 types in the schema; introspection works. [V]

### 3.2 `geocoordinates` — this answers the spec's top risk

`Model.geocoordinates` is a `GeoCoordinate`: `latitude`, `longitude`, `altitude`, **`rotation: Quaternion{x,y,z,w}`**, `translation: Point`, `modelLocationOf`, `geoLocationOf`, **`source: GeoCoordinateSource`**. [V]

Live on the golden house: `latitude 34.093491666999995`, `longitude -118.3171`, `rotation {x:0, y:0, z:0.7289895896353398, w:0.6845247827531877}` → a rotation about Z of **≈93.7°** (`2·acos(w)`). [V]

`SPEC.md` §16 lists "model frame may not be north-aligned" as the top risk, with registering the floor outline against the Vexcel footprint as the fallback and a wide `north_offset_deg` plus an ask-the-user prompt as the degraded path. **One field supersedes all of that.** Carry the full quaternion plus `translation`, `altitude` and `source`; `source` is the confidence signal. Footprint registration becomes a cross-check, not the primary method.

`Mutation.patchModelGeoCoordinates` / `resetModelGeoCoordinates` / `updateModelAddress` / `addEdgeOpenings` / `patchEdgeOpening` / `removeEdgeOpenings` all exist. **This lane never calls a mutation** — the keys are shared and point at production sponsor data. [V]

### 3.3 `openings` — window and door geometry is measured

`Edge`: `id`, `type: EdgeType`, `thickness`, `centerLineBias`, `layer`, `vertices`, **`openings: Opening`**. [V]

`Opening`: `id`, `type: OpeningType`, `label`, `width`, `height`, `lowerElevation`, `relativeCenter`, `metadata`, `layer`. [V] Verified live — real edges carry openings of `type: "doorway"`.

`SPEC.md` §3.3 says the scan "does not give ... window type". **Wrong for geometry**: per-opening width, height and sill elevation are measured, so **window area and orientation are derivable** and belong in the building model as data. Glazing *performance* (U-value, SHGC) is still inferred — keep that distinction crisp, because §5.1's assumption registry currently treats the whole window as an assumption.

Working query: `floors { id label edges { id type thickness openings { id type width height lowerElevation relativeCenter } } }`

### 3.4 Everything else

[V] from the sponsor reference and live queries, except as marked

- Rooms: `rooms { id floor { id } classifications { label confidence } boundary { edges { id } } dimensions(units: metric) { areaFloor width depth height } }`. Some rooms lack width, depth or height.
- `Dimensions` is richer than the spec uses: `area`, `areaIndoor`, **`areaIndoorWithWalls`**, `depth`, `depthData`, `height`, `lowerElevation`, `units`, `width`, `widthData`. `areaIndoorWithWalls` vs `areaIndoor` is a free envelope-vs-conditioned-area signal.
- Walls: `floors { id label vertices { id position { x y } } edges { ... } }`, metres, z up, same frame as panoramas.
- Panoramas: `panoLocations { id label position { x y z } skybox(resolution: "2k") { status children } }` — six cube faces, order up, four sides, down. `4k` also works.
- Defurnished: `view(type: "matterport.model.defurnished") { id }`, then query `model(id: <view id>)`; pano ids match. 6,979 models have one.
- Floor plans: `assets { floorplans(provider: "matterport") { format flags url width height resolution origin { x y } } }`, plus a DXF.
- MatterPak: `bundle(id: "mp:matterpak") { availability }`, then `assets { resources(format: "matterpak") { status filename url } }`. Zip with `cloud.xyz` and an OBJ mesh. Unlocked for the 232 splat models, "being unlocked" for the rest — treat **locked as a normal outcome**, not an error.
- Splats and drone photos come from the track site, not the Model API: `GET <site>/api/models/<sid>` lists files, `GET <site>/resources/<sid>/<file>` redirects to a one-hour signed link. Splat frame is local, z up, **not north-aligned**; drone GPS and gimbal angles are in the JPEG XMP block (first 48 KB). [U] not re-verified
- **No geographic search in the API.** Property search comes from the CoStar kit CSVs (§2.4). [V]
- Mattertags were empty on the models the sponsor checked. [U]

---

## 4. Vexcel

### 4.1 Transport

- Base `https://api.vexcelgroup.com/v2`, header `X-API-KEY`. [V]
- **WKT is longitude first.** Always send `srid=4326`. [V]
- Layers `urban`, `urban-r`, `wide-area`, `urban-g`; obliques only in `urban`. Houston and Los Angeles only. [V]
- `404` = no parcel at that point, a **normal outcome**. `429` = too fast, exponential backoff. [V]
- `GET /oriented/collections` verified 200; returns a FeatureCollection of collections with `product-type` (e.g. `us-ca-glendale-2025`, `nadir`). Use it to learn which obliques exist before asking for imagery. [V]

### 4.2 `GET /property/extract?include=precomputed`

`HTTP 200`, ~70 KB **GeoJSON FeatureCollection** (`{type, features}`) — not a flat dict. The "flat dotted keys" the spec describes live *inside* `features[0].properties`. 174 leaf paths on the golden lot, 129 relevant. [V]

Parcel level (`features[0].properties`): `structure.count`, `parcel-source` (`Bins`), `parcel-tree-cover.percent` (30.0), `pool.*`, `hardscapes.area` (128.0), `deck.area`, `enclosure.area`, `request-information.inside-parcel`.

Per structure (`features[0].properties.structures[i]`):

| Key | Golden house value | Use |
|---|---|---|
| `primary-structure` | `True` | **the golden lot has 2 structures — this picks the building** |
| `footprint.wkt` / `footprint.area` | polygon / `190.39` m² | footprint, envelope area, north registration cross-check |
| `ground-elevation.value` | `100.584` | terrain |
| `roof-characteristics.shape.value` | `gable` | roof pitch range → PV tilt |
| `roof-characteristics.material.class` | `shingle` | cool-roof measure, roof condition |
| `roof-characteristics.condition` / `.precise-value` | `5.0` / `4.53` | re-roof timing, PV feasibility |
| `roof-characteristics.tree-cover.percent` | `4.0` | shading |
| `roof-characteristics.centroid.wkt` | point | panel layout origin |
| `roof-objects.ac-unit.count` | `2` | existing HVAC, roof obstruction |
| `roof-objects.chimney.count` | `1` | roof obstruction |
| `roof-objects.roof-vent.count` | `5` | roof obstruction |
| `roof-objects.skylight.count` | `0` | daylight, obstruction |
| `roof-objects.solar.value` | `False` | existing PV |
| `roof-objects.solar-panel-photovoltaic.{count,area}` | `None` | existing PV area |
| `roof-defects.*` | all `detected: False` | roof condition before PV |
| `defensible-space.zone1-4-{building,tree}` | 0/25/39/33, 29/28/17/14 | **cheap shading proxy before any ray casting** |
| `building-type.class` | **`None`** | do not depend on it for the home flow |

### 4.3 Roof height needs `include=calculated`

Under `include=precomputed`, **all of these are `None`**: `maximum-roof-height`, `eave-height`, `entrance-elevation`, `number-of-stories-below-eave`, `volume-below-eave`, `structure-score`, `condition.attic-habitable`. [V]

So `include=calculated` is required for roof height and elevation, and it is slow. Treat it as a **per-property one-off, cached hard** — never a hot path. `include=footprint-wkt` also exists. Query filters such as `roof-solar=true` and `roof-material=metal` work, which is how P2 portfolio screening would run. [V] filters from the tutorial, [P] not yet exercised

### 4.4 Imagery and detection — D8, not yet verified

`POST /ortho/extract` and `POST /oriented/extract` return image bytes, 1,024-tile cap per extract. `GET /oriented/query` lists raw images with camera positions. `POST /elements/detect` runs **SAM 3 server-side** (`"model": "sam3"`, `detection-threshold`) on ortho and oblique images, returning map-coordinate boxes and pixel masks — so roof segmentation needs no GPU and sponsor imagery never leaves the API. Specific labels beat vague ones; several seconds per request. `POST /embedding/extract` does semantic search over pre-computed tile embeddings. [V] from the tutorial; [P] none of these exercised live yet — that is D8.

### 4.5 Golden lots

- House: `POINT(-118.3171 34.093491667)` — taken from the Matterport model's own `geocoordinates`, which is the authoritative source for a model's location. [V]
- Office: 9050 Emnora Ln, Houston (`PropertyId 354635`). Get coordinates from `geocoordinates` on `HjEyXryhRLk`, **not** by geocoding the address string. [P]

---

## 5. External data — D9, not started

Geocoding, TMY and live weather, utility tariffs, emission factors and measure cost data are all **[P] not started**. Each needs a source and a citation usable by `physics.md`. Emission factors are needed for the Los Angeles and Houston grid regions and for gas. Owner: D9.

---

## 6. Data-lane workflow

### 6.1 Work packages

One writer per path. Dependencies name **contract types only**, never another package's code.

| ID | Tier | Package | Subagent | Owns | Output |
|---|---|---|---|---|---|
| D0 | — | board reply, kit mirror, `.env` gaps | — (lane owner) | — | — |
| D1 | P0 | CoStar kit reader | `data-costar` | `backend/data_layer/costar.py`, `data/fixtures/costar/` | `CostarData` |
| D2 | P0 | Matterport client | `data-matterport` | `backend/data_layer/matterport.py`, `data/fixtures/matterport/` | `MatterportData` |
| D3 | P0 | Vexcel client | `data-vexcel` | `backend/data_layer/vexcel.py`, `data/fixtures/vexcel/` | `VexcelData` |
| D4 | P0 | Cache + fetch records | `data-cache` | `backend/data_layer/cache.py` | `FetchRecord` |
| D5 | P0 | The one public door | `data-api` | `backend/data_layer/api.py` | `PropertyBundle`, `PropertySummary` |
| D6 | P0 | Golden fixtures | source agents | `data/fixtures/` | — |
| D7 | P1 | Index + office selection | `data-costar` | `backend/data_layer/index.py` | `PropertySummary[]` |
| D8 | P1 | Imagery + SAM 3 | `data-vexcel` | `backend/data_layer/imagery.py` | roof masks, ortho/oblique |
| D9 | P1 | External data | `data-costar` | `backend/data_layer/external.py` | weather, tariffs, emissions |
| D10 | P2 | The five unused datasets | `data-costar` | `backend/data_layer/costar_extra.py` | `occupancy`, `value_uplift` |
| D11 | — | this file | lane owner | `specs/data-integration.md` | — |

**Critical path:** D0 (kit mirror) → D1 / D2 / D3 in parallel → D5 → D6. D4 can be stubbed from the contract and hardened later. D7–D10 come strictly after the walking skeleton.

### 6.2 Running agents in parallel

- **Three source agents at most**, one per working key set (unlabelled, `_B`, `_C`). Set `_D` is invalid. This cap is a rate-limit constraint, not a style preference — the keys are shared across every team.
- Each agent on its own `<issue#>-<slug>` branch from fresh `main` (AGENTS.md §3.2), or a git worktree when two need the same dependency tree.
- Launch with `/data-wp <ID>`; check lane state with `/data-status`. Subagent definitions live in `.claude/agents/data-*.md` and carry the verified facts for their source inline, so an agent starts from evidence rather than from the stale spec.
- **Fixtures ship with the package**, not after it. D5 and the other three lanes must never wait on live keys.
- `backend/schema.py` belongs to @yalexie1. This lane imports it and never edits it.

### 6.3 Board post types

On top of the AGENTS.md rules: `CONTRACT-CHANGE:` (a contract type is wrong or missing — address @yalexie1), `FIXTURE-READY:`, `INTERFACE-LIVE:` (post as soon as signatures return fixture data, before live fetches work — three lanes are waiting), `BLOCKED:` (name the contract type), `HANDOFF-REQUEST:` (to touch a path you do not own).

### 6.4 Cache and fixture layout

```
data/cache/           git-ignored — the CoStar kit mirror, fetched bytes, Vexcel calculated results
data/fixtures/        committed — golden-property payloads other lanes build against
  costar/  matterport/  vexcel/
mp_out/               git-ignored
```

Cache keys include source, identifier **and query shape** (Vexcel's `include=` and `layer`, Matterport's field selection, CoStar's dataset and record id). **No signed URL is ever persisted.** Writes are atomic so an interrupted run cannot leave a half-written entry that later reads as a hit.

Every fetch returns a `FetchRecord` alongside its payload. Outcomes that must each be distinct and are all **normal**: Vexcel 404 (no parcel) and 429 (rate limited), MatterPak locked, no splat, no defurnished view, rooms missing dimensions, a CoStar property with an empty `MatterportModelId` (51 commercial, 1 residential), a hidden residential address (4) or a non-public listing (228), `building-type.class` absent.

---

## 7. Corrections raised for the contract freeze

Sent to @yalexie1 on the board. Each is verified above.

1. **Kit structure and size** (§2.1, §2.2) — 49 MB; 8 JSONL datasets plus `schemas/`, `models/`, `concepts/`; no `commercial-property/` folder. `schemas/` closes the §16 "columns unknown" risk.
2. **Join keys** (§2.4) — `CostarData` should carry `PropertyId` / `ListingId` / `ResidentialListingId` / `MatterportModelId` from the kit's own CSVs, not `homes_listing_id` / `costar_property_id` via `models_index.csv`.
3. **North alignment is solved** (§3.2) — `MatterportData` should carry the `geocoordinates` quaternion plus `translation`, `altitude` and `source`, not a wide `north_offset_deg` with an ask-the-user fallback. Retires the top risk in §16.
4. **Window geometry is measured** (§3.3) — `Opening{type,width,height,lowerElevation,relativeCenter}` belongs in the contract. §3.3 and the §5.1 assumption registry both need correcting: geometry is data, performance is still inferred.
5. **Five unused datasets** (§2.3) — `occupancy` and `value_uplift` proposed as additive fields. Employee counts and tenancy periods drive office plug loads, lighting schedules and occupancy-driven HVAC; sale comps and asking rents give retrofit value uplift, the "switch it on Monday" axis.

Also open: whether a **second zip** exists for the Matterport connection (§2.4), who owns `.claude/agents/`, and the two `.env` gaps (§1).

---

## 8. Verification log

| What | Method | Date | Result |
|---|---|---|---|
| 4 key sets, charset and uniqueness | local audit, no values printed | 2026-11-14 | all distinct, no damage; `_D` incomplete |
| Matterport auth × 4 sets | live `model(id:)` query | 2026-11-14 | A/B/C 200; `_D` 403 |
| Vexcel auth × 3 sets | live `/oriented/collections` | 2026-11-14 | all 200 |
| CoStar URL × 3 sets | range GET | 2026-11-14 | all 206, `application/zip`, `PK\x03\x04` |
| Kit size and expiry | `Content-Range`, `X-Amz-*` | 2026-11-14 | 51,700,855 B; expires 2026-11-15 03:30 UTC |
| Zip password | decrypted a member over range reads | 2026-11-14 | works; 42/47 encrypted |
| Kit layout and `index.md` | range-read zip | 2026-11-14 | 47 entries; no `commercial-property/` |
| Join CSVs and counts | parsed both CSVs | 2026-11-14 | 13,147/3,339 and 2,224/2,120/1,867 |
| Enums | `schemas/enums.json` | 2026-11-14 | Office=5; BuildingClass 1–4 |
| Field rules | `models/commercial-property.md` | 2026-11-14 | `constructionEvents[]`, GBA vs RBA |
| Golden properties present | CSV lookup | 2026-11-14 | 354635 (3 models); house residential |
| Matterport schema | GraphQL introspection | 2026-11-14 | 266 types; `geocoordinates.rotation`; `Edge.openings` |
| Georeference live | live query, golden house | 2026-11-14 | quaternion z=0.72899 w=0.68452 → ≈93.7° |
| Openings live | live query, golden house | 2026-11-14 | `type: "doorway"` on real edges |
| Vexcel precomputed | live `property/extract`, golden lot | 2026-11-14 | 174 leaf paths; gable/shingle; heights `None` |
| Vexcel `include=calculated` | — | — | **[P] not run** |
| `elements/detect` SAM 3 | — | — | **[P] not run (D8)** |
| Office lot in Vexcel | — | — | **[P] not run** |
| External data sources | — | — | **[P] not started (D9)** |

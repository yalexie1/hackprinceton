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
- Variable names: `MATTERPORT_API_KEY`, `MATTERPORT_API_TOKEN`, `MATTERPORT_SDK_KEY`, `VEXCEL_API_KEY`, `COSTAR_KIT_URL`, `COSTAR_ZIP_PASSWORD` (shared across sets), `ANTHROPIC_API_KEY`, `EIA_API_KEY`.
- `ANTHROPIC_API_KEY` and `EIA_API_KEY` are both present and verified against their APIs as of 2026-11-14. **`.env.example` needs an `EIA_API_KEY=` line** — that is a root file @yalexie1 owns.
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
| Commercial sale comp | `data/commercial-sale-comp.jsonl` | 6,120 | 23 MB | `id` | **D10 — `MarketData` for value uplift** |
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

- **Office**: `PropertyId 246899` = 11400 Olympic Blvd, Los Angeles, CA 90064 — chosen 2026-11-14 to replace `354635`, which is an Industrial_Warehouse (§3.3). `propertyType` **5 = Office**, `buildingClass` **1 = A**, `constructionStatus` Existing, `constructionEvents` `[(ConstructionComplete, 1989)]`, GBA = RBA **259,923 sq ft**, `grossTypicalFloorSquareFeet` 14,137, **`numStoriesAboveGrade` 17**, `propertyOffice` populated, 9 Matterport models. Market 20, submarket 1435.
  **Office `sid` = `jfiEvosX974`** ("Executive Tower - Suite 140 - 4,410 SF") — richest of the nine: 8 rooms, 36 panoramas, 1 floor. Others: `2cLAWCVj1tA` (Suite 1530, 6 rooms), `vNxGNVDgVs9` (Suite 400, 5 rooms), `YbKz5PKbzwp` (Brentwood Executive Plaza, 5), `BkjvwqdchVY` (Suite 1100, 2 rooms but **93 panoramas** — the open-plan alternative for desk placement), `C7sMGY7UZfL`, `5xViZEoqi5n`, `bZ8jxbUviCF`, `iAw7TsDLoof`. **None of the nine has a defurnished view.**
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

**`GeoCoordinateSource` = `client` | `processing` | `unknown`.** [V] Both golden models report **`processing`** — the georeference was derived during processing, not set by a client. So `source` distinguishes a derived georeference from a human-set one; neither golden model is human-set, which is the honest confidence floor for the north angle. [V] 2026-11-14

Verified georeferences: [V] 2026-11-14

| Model | lat | lon | altitude | rotation (z, w) | angle about Z | source |
|---|---|---|---|---|---|---|
| House `zvKHR9DHNjJ` | 34.093491667 | -118.3171 | 120.200 | 0.7289896, 0.6845248 | **≈93.7°** | `processing` |
| Office `jfiEvosX974` "Executive Tower - Suite 140" | 34.036533908 | -118.443118175 | **0.0** | −0.3548537, 0.9349218 | **≈41.6°** | `processing` |

The office reports **`altitude` 0.0** against the house's 120.2, so altitude is not reliably populated and must not be used as terrain elevation — take that from Vexcel `ground-elevation`. The office quaternion also has a **negative** z, so its rotation runs the other way from the house's; whatever convention the contract fixes has to handle both signs.

`Mutation.patchModelGeoCoordinates` / `resetModelGeoCoordinates` / `updateModelAddress` / `addEdgeOpenings` / `patchEdgeOpening` / `removeEdgeOpenings` all exist. **This lane never calls a mutation** — the keys are shared and point at production sponsor data. [V]

### 3.3 `openings` — window and door geometry is measured

`Edge`: `id`, `type: EdgeType`, `thickness`, `centerLineBias`, `layer`, `vertices`, **`openings: Opening`**. [V]

`Opening`: `id`, `type: OpeningType`, `label`, `width`, `height`, `lowerElevation`, `relativeCenter`, `metadata`, `layer`. [V] Verified live — real edges carry openings of `type: "doorway"`.

`SPEC.md` §3.3 says the scan "does not give ... window type". **Wrong for geometry**: per-opening width, height and sill elevation are measured, so **window area and orientation are derivable** and belong in the building model as data. Glazing *performance* (U-value, SHGC) is still inferred — keep that distinction crisp, because §5.1's assumption registry currently treats the whole window as an assumption.

**No office model has window openings.** [V] 2026-11-14. The first office examined (`HjEyXryhRLk`, the Industrial_Warehouse since replaced) returned 5 openings, every one a `doorway`. The chosen golden office is worse: **all nine models of `246899` return no openings at all.** The wider sample below shows this is systemic, so window surfaces cannot come from the scan for the office flow — and office daylight, glare and desk placement (`SPEC.md` §6.4) all depend on them. Raised for the analysis lane.

**Two findings that change the office flow.** [V] 2026-11-14

**1. The golden office is not an office.** `PropertyId 354635` (9050 Emnora Ln, "Exchange Emnora", Houston 77080) reads from the kit as `propertyType` **2 = Industrial**, `propertySubtype` **52 = Industrial_Warehouse**, `buildingClass` **3 = C**, with `propertyIndustrial` populated and `propertyOffice` null. GBA = RBA = 13,320 sq ft, `numStoriesAboveGrade` present, `constructionEvents` = `[(2, 1984)]` so year built 1984. **It would never be returned by the office selector**, which filters `propertyType == 5` (§2.5). This also explains the two anomalies already recorded: a warehouse plausibly has no rooftop AC unit (§4.5) and no windows.

There is no shortage of real offices: **289 properties are `propertyType` 5 and 274 of them carry at least one Matterport model** — 183 Houston, 90 Los Angeles. For context the kit is dominated by apartments: of 3,339 properties, 2,765 are Multifamily, 289 Office, 122 Industrial, 65 GeneralRetail, 55 Hospitality, 31 Flex. Strong candidates by model count, all `constructionStatus` Existing:

| PropertyId | Address | Models | GBA | Stories | Class | Built |
|---|---|---|---|---|---|---|
| 234088 | 2100 West Loop, Houston 77027 | 9 | 162,540 | 16 | A | 1974 |
| 246899 | 11400 Olympic Blvd, Los Angeles 90064 | 9 | 259,923 | 17 | A | 1989 |
| 246836 | 10940 Wilshire Blvd, Los Angeles 90024 | 8 | 223,797 | 24 | A | 1988 |
| 23551 | 7457 Harwin Dr, Houston 77036 | 10 | 105,717 | 3 | B | 1983 |

**2. Re-picking the office does not get you windows.** Sampled one model from each of 12 distinct `propertyType == 5` properties against 12 residential models:

| Sample | Models with ≥1 opening | Opening types seen |
|---|---|---|
| Office (12 properties) | **2 / 12** | `doorway` 17, `opening` 16 — **no `window` at all** |
| Office 246899, **all 9 of its models** | **0 / 9** | none at all — not even a doorway |
| Residential (12 listings) | **12 / 12** | `doorway` 154, `opening` 35, **`window` 34**, `divider` 5 |

That is **21 office models sampled with no windows between them**, including all nine models of the chosen golden office. The openings graph is populated on residential scans and essentially absent on commercial ones. This is systemic, not a property-selection artefact: **office window surfaces can never come from the scan**, whichever office is chosen.

Consequence for the analysis lane: `A9` builds window surfaces and true north from openings, and that path is **home-flow only**. The office flow needs windows from another source — Vexcel obliques or facade imagery, or footprint plus storey count plus a window-to-wall ratio from the vintage tables, or the panorama vision model — and whichever is chosen must carry its uncertainty as an `Assumption`. Office daylight, glare and desk placement (`SPEC.md` §6.4) all sit downstream of that choice.

One more, for EMI-01: the current office ZIP is **77080**, prefix 770, which falls in the Houston set `specs/physics/04-economics-emissions-mv.md` flags as ambiguous (of 415 ZIPs with prefixes 770 and 772–775, 325 are ERCT only, 35 are SRMV only, 55 split). Whichever office is finally chosen, its eGRID subregion must be resolved from the delivery utility rather than assumed — CenterPoint territory is ERCT.

**The enum values settle it.** [V] 2026-11-14

- **`OpeningType` = `divider` | `doorway` | `opening` | `window`.** `window` is an explicit, first-class value — windows are *typed*, not merely "an opening we guess about".
- **`EdgeType` = `invisible` | `wall`.** Only two values.

That answers the open question in `HANDOFF.md` §4.1 ("what `edges.type` values exist besides `wall` — doors, windows, openings?"): **none.** Doors and windows are not edge types at all; they live in `Edge.openings` with their own `OpeningType`. Anything looking for windows on `edge.type` will find nothing. Also `Units = imperial | metric`, so always pass `units: metric` explicitly.

Working query: `floors { id label edges { id type thickness openings { id type width height lowerElevation relativeCenter } } }`

### 3.4 Everything else

[V] from the sponsor reference and live queries, except as marked

- Rooms: `rooms { id floor { id } classifications { label confidence } boundary { edges { id } } dimensions(units: metric) { areaFloor width depth height } }`. Some rooms lack width, depth or height.
- **Office room classifications are empty.** All 8 rooms of the golden office return `classifications: []` — no label at all — where the golden house returns Living Room, Dining Room, Kitchen and Bedroom. Room-type-driven zoning is therefore **home-flow only**, the same split as openings. [V] 2026-11-14
- **`areaFloor` can contradict `width` × `depth`.** The office's largest room reports `areaFloor` 157.82 m² with `width` 1.46 and `depth` 1.34, so those are meaningless for a non-rectangular space. Trust `areaFloor`; treat `width`/`depth` as present-but-unreliable, not merely sometimes-absent. One of the eight rooms has `depth: null`. Measured room heights run 2.90–3.21 m. [V] 2026-11-14
- `Dimensions` is richer than the spec uses: `area`, `areaIndoor`, **`areaIndoorWithWalls`**, `depth`, `depthData`, `height`, `lowerElevation`, `units`, `width`, `widthData`. `areaIndoorWithWalls` vs `areaIndoor` is a free envelope-vs-conditioned-area signal.
- Walls: `floors { id label vertices { id position { x y } } edges { ... } }`, metres, z up, same frame as panoramas.
- Panoramas: `panoLocations { id label position { x y z } skybox(resolution: "2k") { status children } }` — six cube faces, order up, four sides, down. `4k` also works.
- Defurnished: `view(type: "matterport.model.defurnished") { id }`, then query `model(id: <view id>)`; pano ids match. 6,979 models have one.
- Floor plans: `assets { floorplans(provider: "matterport") { format flags url width height resolution origin { x y } } }`, plus a DXF.
- MatterPak: `bundle(id: "mp:matterpak") { availability }`, then `assets { resources(format: "matterpak") { status filename url } }`. Zip with `cloud.xyz` and an OBJ mesh. Unlocked for the 232 splat models, "being unlocked" for the rest — treat **locked as a normal outcome**, not an error.
- **MatterPak on the golden house: `bundle(id:"mp:matterpak").availability` is `unlocked`, but all three resources report `status: "unavailable"`** (`mp_matterpak_...zip`, `mp_obj_...zip`, `mp_obj-low-res_...zip`). So `mesh_path` and `point_cloud_path` **cannot be filled today** — unlocked is not the same as available, and anything depending on the mesh must treat it as absent. [V] 2026-11-14
- **Splat and drone photos exist for both golden properties, and they are very large.** [V] 2026-11-14, from the track site:

| Model | `outsideView` | `splatBytes` | `totalBytes` | drone images |
|---|---|---|---|---|
| House `zvKHR9DHNjJ` | `true` | 553,269,021 (553 MB) | **15,567,074,993 (15.6 GB)** | `DJI_20260915...*_D.JPG` |
| Office `HjEyXryhRLk` (the **replaced** warehouse) | **`false`** | 394,940,609 (395 MB) | 4,131,262,549 (4.1 GB) | `DJI_20261105...*_V.JPG` |
| **Office `246899` — all nine models** | — | — | — | **none: every model 404s on the track site** |

  The replaced warehouse's record carried `propertyId: "354635"`, which **independently confirmed the CoStar join** from a second source. The 15.6 GB house total is a hard constraint on D12 — fetch selectively, never the whole folder.

  **The chosen golden office has no exterior assets at all.** All nine models of `246899` return HTTP 404 from `GET <site>/api/models/<sid>`, so no splat and no drone photos. That is consistent with the index profile: only 21 of 13,014 commercial models have a splat, so almost any office will lack one. Consequences: **`D12` is home-flow only**, and `A13`, which reads `mesh_path` / `splat_path` / `drone_photo_paths`, has no office input. It matters less than it sounds — the office roof is **flat** (§4.5), so PV needs no mesh-derived pitch, and the Vexcel ortho plus footprint is sufficient. [V] 2026-11-14
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

### 4.3 Roof height: use `include=precomputed,calculated`, and distrust the value

Under `include=precomputed`, **all of these are `None`**: `maximum-roof-height`, `eave-height`, `entrance-elevation`, `number-of-stories-below-eave`, `volume-below-eave`, `structure-score`, `condition.attic-habitable`. [V]

**`include=calculated` alone is not "precomputed plus heights".** It returns a *disjoint* two-key set per structure — `roof-characteristics.elevation` and `roof-characteristics.height` — plus four parcel keys, and nothing else. It carries **no `primary-structure` flag and no structure id**, so on a multi-structure parcel its results cannot be joined back to the precomputed structures at all. It is also **fast (~0.5 s), not slow** as the tutorial implies. [V] 2026-11-14

**The fix: `include=precomputed,calculated` in one call.** Verified — 71,347 bytes, 92 keys on the primary structure, carrying `primary-structure`, `footprint.area`, `ground-elevation.value` **and** `roof-characteristics.{elevation,height}` together. Use this; never two separate calls. [V] 2026-11-14

**`roof-characteristics.height` = ground elevation − roof elevation** — note the sign: it is **negative for a building that rises above grade**. [V] 2026-11-14, from consistent `include=precomputed,calculated` calls:

| Lot | ground | roof | reported height | ground − roof |
|---|---|---|---|---|
| House (190.4 m², shingle gable) | 100.584 | 100.220123 | **+0.363877** | +0.363877 ✓ |
| Office 246899 (2,207.4 m², flat membrane, **17 storeys**) | 54.5592 | 70.056587 | **−15.497387** | −15.497387 ✓ |

> **Correction to an earlier version of this section.** It gave the formula as *roof − ground*, derived from the old office lot where `ground` came from an `include=precomputed` call and `roof` from a separate `include=calculated` call. By this section's own rule those two responses cannot be paired, so that match was spurious. Both lots measured with a single combined call fit **ground − roof**.

**The magnitude is wrong too.** The tower reports 15.5 m against 17 storeys — about 54 m at the 2.90–3.21 m floor-to-floor heights measured in its own scan. Its detected footprint of 2,207 m² is ~1.7× the CoStar typical floor plate (14,137 sq ft = 1,313 m²), so Vexcel is almost certainly outlining a low podium or garage rather than the tower. The house value also **changed between calls** (0.4254 standalone vs 0.3639 combined), so it is not even stable.

**Conclusion: do not use `roof-characteristics.height` for building height.** Take storey count from CoStar `numStoriesAboveGrade` and multiply by a floor-to-floor height, or use the scan's own room heights. Keep the Vexcel figure only as a weak cross-check, with its sign stated explicitly.

Consequence for the solar pipeline: **per-plane tilt cannot come from Vexcel height.** It must come from `roof-characteristics.shape.value` (`gable` on both golden lots) mapped through the roof-pitch-by-shape table in `physics.md` — which is exactly the fallback `SPEC.md` §16 describes. Treat the mesh-derived tilt path as P1 at best.

`include=footprint-wkt` also exists. Query filters such as `roof-solar=true` and `roof-material=metal` work, which is how P2 portfolio screening would run. [V] filters from the tutorial, [P] not yet exercised

### 4.4 Imagery and SAM 3 detection — verified, and it changes the solar pipeline

[V] 2026-11-14, run live on the golden house parcel. The request contract is **not** what §6.3 of `SPEC.md` assumes; the shape below comes from the sponsor's own `vexcel_quickstart.py`.

`POST /elements/detect` takes an **area plus a list of extract requests**, not image ids:

```json
{"wkt": "<parcel POLYGON>", "srid": 4326, "buffer-meter": 0,
 "images": [
   {"endpoint": "ortho/extract",
    "request": {"layer": "...", "srid": 4326, "wkt": "<parcel>", "crop": "bounding_box"}},
   {"endpoint": "oriented/extract",
    "request": {"layer": "urban", "srid": 4326, "wkt": "<parcel>",
                "product-type": "oblique-north", "rotation": "natural", "crop": "bbox"}}],
 "model-input": {
   "elements": [{"label": "roof", "model": "sam3", "detection-threshold": 0.3}],
   "include": ["bbox", "confidence", "pixel-mask", "pixel-bbox"]}}
```

Gotchas, each verified: [V]

- Each `images[]` entry needs its own **`endpoint`** key. Passing image-name strings fails with `Parameter 'endpoint' is mandatory for this service`, and that message is misleading — the missing key is *inside* `images[]`, not at the top level. `endpoint` is also not accepted as a query parameter.
- **`pixel-bbox` is required whenever `pixel-mask` is requested.**
- `buffer-meter: 0` restricts detection to the parcel itself, excluding neighbours.
- The parcel geometry from `property/extract` can be a **`MultiPolygon`** — the golden house is. Take the largest ring; a bare `POINT` makes `elements/detect` return 404.
- Oblique directions must come from `oriented/collections` with `product-type=oblique` and `include=product-type,collection,last-capture-date`, filtered to the **newest** `last-capture-date`. All four directions exist on the golden house (newest collection `2025-12-10T21:03:34`).
- Response: `images[]` echoes each request with an `image-id` (`ortho-1`, `oriented-1`) and `metadata`. **The label is on `features[i].properties.label`, not on the detection** — each detection carries only `imageId`, `bbox` (a map-coordinate POLYGON), `pixel-bbox` (`[x, y, w, h]`), `pixel-mask` (base64 PNG, white where the object is, cropped to the box) and `confidence`.

**Label quality on roofs — the measured result:** [V] golden house, ortho, threshold 0.3

| Label | detections | confidences |
|---|---|---|
| `roof` | **13** | 0.309 – 0.695 |
| `roof surface` | 2 | 0.474, 0.358 |
| **`roof plane`** | **0** | — |
| `roof facet` | 0 | — |
| `chimney` | **0** | — (precomputed says `chimney.count` = **1**) |
| `skylight` | 2 | 0.368, 0.373 (precomputed says `skylight.count` = **0**) |
| `solar panel` | 0 | — (consistent with `solar.value` False) |
| `tree` | 12 | — |
| `roof vent` | 1 | — (precomputed says `roof-vent.count` = 5) |

Four conclusions the analysis lane needs:

1. **`"roof plane"` — the exact label `SPEC.md` §6.3 specifies — returns nothing.** Use `"roof"`. `"roof facet"` also returns nothing.
2. **Threshold 0.5 (the quickstart default) is too high for roofs.** Real confidences run 0.31–0.70, so 0.5 discards most detections. Use ~0.3 and carry the confidence through.
3. **For roof *obstructions*, the precomputed `roof-objects` counts beat SAM 3.** SAM 3 missed the chimney that precomputed reports, invented 2 skylights that precomputed says do not exist, and found 1 of 5 roof vents. `SPEC.md` §16 lists "SAM 3 label quality on roofs" as a risk with precomputed roof attributes as the fallback — **the risk is real and the fallback should be the primary.**
4. **13 `roof` detections on one small house means SAM 3 returns roof fragments, not clean planes.** Per-plane tilt and azimuth from these masks is not a short path; combined with the unusable roof height (§4.3), the honest P0 position is roof pitch from `shape.value` plus the `physics.md` pitch table, with SAM 3 masks used for *usable-area* estimation rather than plane geometry.

`POST /ortho/extract` and `POST /oriented/extract` return image bytes, 1,024-tile cap per extract. `POST /embedding/extract` does semantic search over pre-computed tile embeddings. [V] from the tutorial, [P] not exercised

### 4.5 Golden lots

- **House**: `POINT(-118.3171 34.093491667)`, from the model's own `geocoordinates`. 2 structures. [V] `primary-structure` True, `footprint.area` 190.39 m², `ground-elevation` 100.584, roof `gable`/`shingle`, `condition.precise-value` 4.53, `tree-cover` 4.0, `ac-unit.count` 2, `chimney.count` 1, `roof-vent.count` 5, `skylight.count` 0, `solar.value` False, `building-type.class` **null**.
- **Office**: `POINT(-118.44311817454468 34.036533907520074)` = 11400 Olympic Blvd, LA 90064 (`PropertyId 246899`), from `geocoordinates` on `jfiEvosX974`. [V] 2026-11-14 — 1 structure, `primary-structure` True, `footprint.area` **2,207.43 m²**, `ground-elevation` 54.5592, roof **`flat`** / **`membrane`**, `condition.precise-value` 3.17, roof `tree-cover` 0.0, parcel `tree-cover` 5.0, `ac-unit.count` **0**, `skylight.count` 0, `solar.value` False, `building-type.class` **null**.

**Good news for office solar: the roof is flat.** A flat membrane roof removes the pitch problem entirely — tilt becomes a racking design choice rather than a value inferred from `shape.value`. So the §4.3 height failure and the §4.4 SAM 3 plane-fragmentation problem both stop blocking office PV. The house still needs pitch from `shape.value` plus the `physics.md` table.

Two cautions carried over:

- **`ac-unit.count` is 0 here too**, on a 17-storey Class A office built 1989. A tower of that vintage certainly has rooftop plant, so this is a **detection limit, not an absence** — the same lesson as §4.4, where SAM 3 missed a chimney that Vexcel's own attributes reported. `HVAC_RTU` and `HVAC_ECON` need evidence from elsewhere.
- **`building-type.class` is null again.** It returned `"commercial"` on the old industrial lot and null on both the house and this office, so it is unreliable on both flows and must never be required.

## 5. External data — D9

Checked live 2026-11-14. **Two of the sources `SPEC.md` and `handoff-plan.md` name are unreachable from this environment**, so the recommended set differs from the plan.

### 5.1 What is verified reachable

| Need | Source | Key? | Status |
|---|---|---|---|
| Hourly irradiance (GHI, DNI, DHI), temperature, RH, wind | **Open-Meteo archive API** (`archive-api.open-meteo.com/v1/archive`) | none | [V] 200; units in `hourly_units`; timezone-aware; returns site `elevation` |
| Annual PV yield + inter-annual uncertainty | **PVGIS v5_3 `PVcalc`** (EC Joint Research Centre) | none | [V] 200 on both golden lots |
| PV reference implementation for unit tests | **pvlib 0.16.1** (local wheel) | n/a | [V] downloads |
| Utility tariff, Los Angeles | **NREL URDB** via `api.openei.org/utility_rates` | free NREL key (`DEMO_KEY` works for probing) | [V] returns LADWP, `eiaid` 11208 |
| State average retail price (tariff fallback) | **EIA API v2** `electricity/retail-sales` | free EIA key, `EIA_API_KEY` | [V] 200 for TX and CA, commercial and residential |

Verified PVGIS output, 4 kWp, 14 % loss, tilt 20°, azimuth south:

| Lot | `E_y` kWh/yr | `SD_y` | `H(i)_y` kWh/m² | radiation db |
|---|---|---|---|---|
| House (LA) | 7,016.92 | ±161.45 | — | PVGIS-ERA5, 2005–2023 |
| House (LA), tilt 0 | 5,977.53 | ±123.27 | 2,042.5 | PVGIS-ERA5 |
| Office (Houston), tilt 0 | 4,944.09 | ±191.78 | 1,684.72 | PVGIS-ERA5 |

**`SD_y` is the inter-annual standard deviation across 19 years.** That is a ready-made uncertainty band for the low/expected/high requirement in `SPEC.md` §5 — the solar figure gets a defensible spread without inventing one.

**Open-Meteo returns DNI and DHI already separated from GHI.** So for the hourly path the irradiance *decomposition* step (Erbs 1982) in the `physics.md` brief is **optional** — only the transposition to plane-of-array (Perez 1990) is strictly needed. Worth knowing before that module gets written.

### 5.1a Weather file format and time convention (workplan R2)

`ClimateSite.weather_path` points at a typical-year hourly CSV in the cache. Format, written by `external.py`:

| Column | Unit | Open-Meteo field |
|---|---|---|
| `time_local` | ISO 8601 local, no offset (the site's `timezone` is on `ClimateSite`) | `hourly.time` |
| `temp_c` | °C | `temperature_2m` |
| `rh_pct` | % | `relative_humidity_2m` |
| `ghi_w_m2` | W/m² | `shortwave_radiation` |
| `dni_w_m2` | W/m² | `direct_normal_irradiance` |
| `dhi_w_m2` | W/m² | `diffuse_radiation` |
| `wind_m_s` | m/s (Open-Meteo returns km/h — convert) | `wind_speed_10m` |

**`weather_time_convention` = `hour_end`.** [V] 2026-11-14, verified two independent ways on the golden house:

1. **Full-hour means, not instantaneous samples.** The 24 hourly `shortwave_radiation` values for 2024-06-21 sum to 8,312 W/m²·h = **29.923 MJ/m²**, against the daily `shortwave_radiation_sum` of **29.92 MJ/m²** — ratio **1.0001**. If the values were instantaneous samples the sum would not reconcile with the daily total.
2. **The stamp labels the hour that *ends* at that time.** Sunrise was 04:42. GHI reads 0.0 at the 04:00 stamp, **2.0** at 05:00, 85.0 at 06:00. Under an hour-*start* reading, the 05:00 stamp would cover 05:00–06:00 with the sun already 18–78 minutes up and would have to read roughly 60+, not 2.0. Under hour-end it covers 04:00–05:00, which contains only the 18 minutes after sunrise at 0–3° elevation — which is exactly what 2.0 looks like.

So an hour stamped `05:00` is the mean over `04:00`–`05:00`. **Anything that treats it as the following hour shifts every solar calculation by one hour.**

### 5.1b Both golden properties are now in Los Angeles

Choosing `246899` over the Houston warehouse puts **both** golden properties in Los Angeles. Four consequences: [V] 2026-11-14

1. **Both use the real LADWP tariff** from URDB (`eiaid` 11208), so the EIA state-average fallback is **off the demo path**. It stays implemented and documented — any Houston property still needs it, and 183 of the 274 office candidates are in Houston.
2. **Both are eGRID subregion CAMX.** ZIP 90064 has prefix 900, inside the range EMI-01 confirmed for all 533 LA-area ZIPs (900–918). So `EF_avg` = **0.19504 kg CO₂e/kWh** for both, and the ERCT-versus-SRMV ambiguity that affected Houston ZIP 77080 **disappears**.
3. **The 3.35× Texas/California price gap leaves the demo.** The weaker-Houston-economics warning below no longer applies to either golden property, though it stays true for any Houston run.
4. **Texas now has no demo vehicle.** `specs/legal/texas.md`, the Texas documents 2–6 and the Texas PACE Act route in `SPEC.md` §6.6 have no golden property to run against, while California does. That is a real cost of this choice: either accept that Texas is specified but not demonstrated, or add a Houston office as a third property. Flagged, not decided — candidates are in §3.3.

### 5.2 What is blocked, and the caveats

- **`developer.nrel.gov` and `nsrdb.nrel.gov` both fail DNS resolution from this environment** (`curl: (6) Could not resolve host`). So **PVWatts v8 and NSRDB PSM3 are unusable here**, although `api.openei.org` — also NREL-operated — resolves fine. `handoff-plan.md` names PVWatts as a reference implementation for the test plan; use **pvlib locally** instead, with PVGIS as an independent cross-check. [V]
- **PVGIS offers only `PVGIS-ERA5` for the United States.** `PVGIS-NSRDB` is not a valid value in v5_3, and `PVGIS-SARAH3` answers "location out of the spatial coverage" for Los Angeles. ERA5 is a ~30 km reanalysis, materially coarser than satellite-derived NSRDB, so treat PVGIS as a **sanity band and annual cross-check, not the primary hourly source**. Open-Meteo is the hourly source. [V]
- **URDB has no tariff at the Houston office coordinates at all** — 0 items for `sector=Commercial`, `sector=Residential`, and with no sector filter. That is consistent with ERCOT's deregulated retail market, where there is no single regulated utility tariff to look up. [V]
- **Resolved via EIA, as a documented fallback.** `EIA_API_KEY` is now in `.env` and verified. `GET https://api.eia.gov/v2/electricity/retail-sales/data/` with `frequency=monthly`, `data[0]=price`, `facets[stateid][]`, `facets[sectorid][]` returns the state monthly average retail price in **cents per kWh**: [V] 2026-11-14, latest period 2026-08

  | State | Sector | Period | Price |
  |---|---|---|---|
  | TX | Commercial | 2026-08 | **8.96 ¢/kWh** |
  | TX | Residential | 2026-08 | 15.91 ¢/kWh |
  | CA | Commercial | 2026-08 | 30.02 ¢/kWh |
  | CA | Residential | 2026-08 | 29.75 ¢/kWh |

  **This is a state monthly average, not the building's actual retail contract.** In deregulated ERCOT the real price varies widely by retail plan, so the office `Tariff` must carry `source` naming EIA with the state, sector and period, and a `FetchRecord{layer: "tariff", status: "fallback"}` beside it. It is defensible and traceable; it is not a lookup of that building's tariff. The LA home flow still uses the real LADWP rate from URDB.

  **One consequence worth stating before anyone is surprised by it.** Texas commercial power is **8.96 ¢/kWh against California commercial at 30.02 — a factor of 3.35**. Since every retrofit's dollar saving is energy saved times price, the Houston office will show markedly worse payback, NPV and SIR than the Los Angeles house for identical physics. That is a real result, not a bug, and it is exactly the sort of thing the C-PACE route in `SPEC.md` §6.6 exists to address. The demo script should not treat a weak office result as a failure.
- **Emission factors: eGRID2023 is the current edition** (the EPA page also still references eGRID2022). The relevant subregions are **CAMX** for Los Angeles and **ERCT** for Houston. **The factor values have not been opened**, and per the double-check protocol they are therefore **unverified — do not hardcode them from memory.** The data file must be read before any CO₂ figure is computed. [P]
- **Measure cost data** is not started. [P]

### 5.3 Consequences for other lanes

1. The analysis lane should write the PV module against **pvlib**, not PVWatts-over-HTTP, and validate against PVGIS annual totals.
2. The irradiance decomposition module is **optional**, not required, if Open-Meteo is the hourly source.
3. **Every CO₂ figure is blocked** until eGRID2023 is actually opened. Until then the plan should report energy and dollars, and mark CO₂ unavailable rather than estimated.
4. **Office-flow dollar savings are unblocked**, using the EIA state-average fallback with an explicit `fallback` FetchRecord. But expect weak office economics: Texas commercial power is 3.35x cheaper than California's, so identical physics yields far worse payback in Houston.

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
| D6 | P0 | Golden fixtures | each source agent, in its own subdirectory | `data/fixtures/costar/`, `/matterport/`, `/vexcel/` — **never the parent** | — |
| D7 | P1 | Index + office selection | `data-costar` | `backend/data_layer/index.py` | `PropertySummary[]` |
| D8 | P1 | Imagery + SAM 3 | `data-vexcel` | `backend/data_layer/imagery.py` | roof masks, ortho/oblique |
| D9 | P1 | External data | `data-costar` | `backend/data_layer/external.py` | weather, tariffs, emissions |
| D10 | P2 | The five unused datasets | `data-costar` | `backend/data_layer/costar_extra.py` | `OccupancyData`, `MarketData` |
| D12 | P1 | Splat + drone photos (track site) | `data-matterport` | `backend/data_layer/tracksite.py` | `splat_path`, `drone_photo_paths` |
| D13 | P2 | Portfolio screening by Vexcel filters | `data-vexcel` | `backend/data_layer/screening.py` | `PropertySummary[]` |
| D11 | — | this file | lane owner | `specs/data-integration.md` | — |

**Critical path:** D0 (kit mirror) → D1 / D2 / D3 in parallel → D5 → D6. D4 can be stubbed from the contract and hardened later. D7–D10 come strictly after the walking skeleton.

### 6.2 Running agents in parallel

- **Three source agents at most**, one per working key set (unlabelled, `_B`, `_C`). Set `_D` is invalid. This cap is a rate-limit constraint, not a style preference — the keys are shared across every team.
- Each agent on its own `<issue#>-<slug>` branch, or a git worktree when two need the same dependency tree.
- **Branch from fresh `main` and open PRs against `main`** (AGENTS.md §3.2). `spec-draft` is **retired** as of PR #19 — do not commit to it or target it. `Closes #N` works again now that `main` is the merge target, so issues auto-close.
- **Tests** live in `backend/data_layer/tests/test_<package>.py`, one file per package, so two agents never write the same test file (workplan R11).
- **`backend/schema.py` exists** as of PR #28 (`SCHEMA_VERSION` 0.2.0), with `backend/__init__.py` alongside it so `import backend.schema` works. `SPEC.md` §9 remains the source and **only @yalexie1 edits the module** — this lane imports it and never writes it. Independently verified 2026-11-14: the module is the §9 block, imports clean under pydantic 2.14.3, defines 56 models, and all 27 payloads in `specs/examples/` validate against it (99 `model_validate` calls, 0 failures). Note three example files are **arrays** — `measures.json` is `MeasureResult[]`, `run_events.json` is `RunEvent[]`, `search_results.json` is `PropertySummary[]` — so a validator assuming one object per file reports false failures.
- Launch with `/data-wp <ID>`; check lane state with `/data-status`. Subagent definitions live in `.claude/agents/data-*.md` and carry the verified facts for their source inline, so an agent starts from evidence rather than from the stale spec.
- **Fixtures ship with the package**, not after it. D5 and the other three lanes must never wait on live keys.

### 6.3 Board post types

On top of the AGENTS.md rules: `CONTRACT-CHANGE:` (a contract type is wrong or missing — address @yalexie1), `FIXTURE-READY:`, `INTERFACE-LIVE:` (post as soon as signatures return fixture data, before live fetches work — three lanes are waiting), `BLOCKED:` (name the contract type), `HANDOFF-REQUEST:` (to touch a path you do not own).

### 6.4 Cache and fixture layout

```
data/cache/           git-ignored — the CoStar kit mirror, fetched bytes, Vexcel calculated results
data/fixtures/        git-ignored — REAL captures replayed offline, never committed
  costar/  matterport/  vexcel/
specs/examples/       committed — the shared fixture set every lane builds against
mp_out/               git-ignored
```

**What may be committed (workplan R1).** An earlier version of this section called `data/fixtures/` "committed", which contradicts `SPEC.md` §3.6 and §14 and the hard rules in the Data agent definitions: sponsor data is hackathon-licensed and this repository is **public**. The rule is:

- **`specs/examples/` is the single committed fixture set.** Its README states that no API response and no CoStar kit record is copied into it; a short list of identifiers and verified scalars is real and everything else is illustrative. Lanes build and test against it.
- **`data/fixtures/` holds real captures and is git-ignored.** It exists so the lane can replay live responses offline without a network, which is what the acceptance tests need. It is never pushed.
- A committed file may contain: synthetic payloads shaped like the real ones, identifiers (model ids, `PropertyId`, `ListingId`), and the small set of verified scalars already published in this document. It may **never** contain a raw Matterport GraphQL response, a Vexcel GeoJSON response, a CoStar kit record, or any image or mask bytes.

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
| Golden properties present | CSV lookup | 2026-11-14 | house residential; office now `246899` (9 models) |
| Office exterior assets | track site, all 9 models | 2026-11-14 | **all 404 — no splat, no drone photos** |
| Matterport schema | GraphQL introspection | 2026-11-14 | 266 types; `geocoordinates.rotation`; `Edge.openings` |
| Georeference live | live query, golden house | 2026-11-14 | quaternion z=0.72899 w=0.68452 → ≈93.7° |
| Openings live | live query, golden house | 2026-11-14 | `type: "doorway"` on real edges |
| Vexcel precomputed | live `property/extract`, golden lot | 2026-11-14 | 174 leaf paths; gable/shingle; heights `None` |
| Vexcel `include=calculated` | live, both lots | 2026-11-14 | disjoint 2-key set, no `primary-structure`; fast not slow |
| Vexcel `include=precomputed,calculated` | live, house lot | 2026-11-14 | **works** — 92 keys, both sets, join problem solved |
| `roof-characteristics.height` semantics | arithmetic on both lots | 2026-11-14 | = roof − ground elevation; office 3.94 m plausible, house 0.36 m implausible and unstable |
| `elements/detect` SAM 3 | live, golden house, ortho + oblique | 2026-11-14 | **works**; `roof` 13 hits @0.3, but `roof plane` 0, chimney missed, skylight false-positive |
| `elements/detect` request shape | sponsor `vexcel_quickstart.py` + live | 2026-11-14 | `images[]` entries need own `endpoint`; `pixel-bbox` required with `pixel-mask` |
| Office lot in Vexcel | live `property/extract` | 2026-11-14 | 1 structure; gable/metal; `building-type.class`=`commercial`; `ac-unit.count`=0 |
| Office georeference | live query | 2026-11-14 | lat 29.8161169, lon -95.5153827, rotation ≈88.3°, source `processing` |
| Matterport enums | GraphQL introspection | 2026-11-14 | `OpeningType` includes `window`; `EdgeType` only `invisible`/`wall` |
| Open-Meteo archive | live, golden house | 2026-11-14 | 200; GHI/DNI/DHI + temp/RH/wind, units documented |
| PVGIS v5_3 `PVcalc` | live, both golden lots | 2026-11-14 | 200; `E_y`, `SD_y`, `H(i)_y`; ERA5 only for the US |
| NREL PVWatts / NSRDB | DNS | 2026-11-14 | **unreachable here** — `Could not resolve host` |
| NREL URDB (LA) | live | 2026-11-14 | LADWP, `eiaid` 11208 |
| NREL URDB (Houston) | live, 3 sector variants | 2026-11-14 | **0 rates** — ERCOT deregulated; open blocker |
| pvlib | wheel download | 2026-11-14 | 0.16.1 available locally |
| EPA eGRID factors | page only | 2026-11-14 | eGRID2023 current; **values not opened, unverified** |
| EIA API v2 retail price | live, TX + CA, both sectors | 2026-11-14 | 200; TX com 8.96, TX res 15.91, CA com 30.02, CA res 29.75 ¢/kWh (2026-08) |
| Measure cost data | — | — | **[P] not started, no owner** |
| Contract v0.2 extract + examples | independent check, pydantic 2.14.3 | 2026-11-14 | 538 lines, imports clean, 56 models, 27/27 examples valid (99 checks, 0 fail) |
| Open-Meteo time convention | hourly-vs-daily reconciliation + sunrise boundary | 2026-11-14 | **`hour_end`** — ratio 1.0001; 05:00 stamp = 04:00–05:00 mean |
| Golden office openings | live query | 2026-11-14 | **5 openings, all `doorway` — no windows** |
| Golden house MatterPak | live query | 2026-11-14 | `unlocked` but all 3 resources `unavailable` |
| Splat / drone, both lots | track site | 2026-11-14 | house 15.6 GB total, office 4.1 GB; office `outsideView` false |
| CoStar join, second source | track site `propertyId` | 2026-11-14 | `HjEyXryhRLk` -> `354635`, matches the kit CSV |
| Old golden office 354635 | kit record | 2026-11-14 | **Industrial_Warehouse, class C, 1984 — not an office** |
| New golden office 246899 | kit record + all 9 models profiled | 2026-11-14 | type 5 Office, class A, 1989, 259,923 sq ft, 17 storeys; `sid` `jfiEvosX974` |
| New office georeference | live query | 2026-11-14 | 34.0365339, −118.4431182, rot ≈41.6° (**negative z**), **altitude 0.0** |
| New office Vexcel lot | live combined call | 2026-11-14 | 1 structure, 2,207.4 m², **flat/membrane**, condition 3.17, ac-unit 0 |
| `roof-characteristics.height` sign | arithmetic across 2 combined calls | 2026-11-14 | **= ground − roof**; earlier "roof − ground" came from mismatched calls, corrected |
| Office room classifications | live query | 2026-11-14 | **all 8 rooms return `classifications: []`** |
| Office openings, all 9 models | live query | 2026-11-14 | **0/9 have any opening**; 21 office models sampled, 0 windows |
| Office inventory in the kit | streamed all 3,339 records + CSV join | 2026-11-14 | 289 type-5 offices, **274 with models** (183 HOU, 90 LA) |
| Openings: office vs residential | 12 + 12 live models | 2026-11-14 | office 2/12 any opening, **0 windows**; residential 12/12, 34 windows |
| Edge-fraction origin, rotation sense | — | — | **[P] open — footprint registration cross-check** |

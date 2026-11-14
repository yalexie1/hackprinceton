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

**A `MatterportModelId` is not unique to one parent.** [V] 2026-11-14, measured while building D1. Of the 15,319 rows that carry a model id, **387 are second-or-later rows for a model already seen**, so **307 model ids have more than one parent**:

| Case | Models | What it is |
|---|---|---|
| Commercial, several `PropertyId`s | **55** | multi-building complexes — one scan at 2121 Brittmoore Rd is attached to **13** property records, and 6 more models have 4 each |
| Residential, several `ListingId`s under **one** `ResidentialListingId` | **202** | one sale marketed through several MLSs |
| Residential, several `ResidentialListingId`s | **50** | separate sales or rentals of the same home over time |

`CostarData` carries a single `property_id` / `listing_id`, so the reader picks a primary by a documented deterministic rule — commercial: the first CSV row whose record exists; residential: the latest `listDate`, being the most recent marketing of that home — and exposes the alternatives through `parents_for_model(sid)` so nothing is silently dropped. **Keying a dict by model id and keeping the last row loses 387 rows without any error**, which is how this was found. Neither golden office is affected: `jfiEvosX974` → `246899` and `L3266YcPPvd` → `234088`, one parent each.

**Do not use the `homes_listing_id` / `costar_property_id` path via `models_index.csv` that `SPEC.md` §9 describes.** It is the join the sponsor marked untested, and the kit ships a direct `MatterportModelId` join with better coverage.

Model ids also appear inside the records as `videoKey` on attachments and media; an item is a Matterport model when `videoExternalReferenceType` (or `externalReferenceType` on residential media) is **36** (MatterportScan) or **234** (MatterportStreamingKey). Join on the key and the model id together.

> `index.md` states: *"How to connect to the Matterport models is provided in a separate zip file."* **We may be missing a second zip.** Raised on the board. [V] quote, [P] whether a second zip exists.

### 2.4a The index over the whole kit — D7

[V] 2026-11-14, built and measured on the mirror.

`search_properties` answered from `specs/examples/` alone until D7: three golden
properties plus the nine rows in `search_results.json`. That was the stated pre-D7
answer to workplan R4. `backend/data_layer/index.py` now backs it with the kit.

**One pass, not 14,932 lookups.** `get_costar_data` streams the 193 MB
`commercial-property.jsonl` and stops at the first match — right for one property,
hopeless for all of them. The index reads each dataset exactly once (3,339 + 2,120
records, **1.1 s together**) and keeps only the dozen fields a `PropertySummary`
needs. Built once to `data/cache/costar/index/summaries.jsonl` (4.4 MB, git-ignored
like the rest of the mirror), invalidated by the size and mtime of the four source
files. Cold load **0.06 s**; a filtered search **0.006 s**.

| Measured | Value |
|---|---|
| Scanned models indexed | **14,932** — every row `rows_by_model` keeps |
| Distinct properties behind them | **5,098** (commercial 12,994 → 3,247; residential 1,938 → 1,851) |
| With coordinates | **14,929** of 14,932 |
| Office **properties** | **264** with a scan, out of 289 office records — 25 offices in the kit were never scanned |
| Office **models** | 669 |
| Largest single group | **32 unit scans** of one apartment complex |

**A search result is a property, not a scan.** This was the one finding that changed
the design. Indexing per model is correct — `PropertySummary.sid` *is* a Matterport
model — but a search for offices in Houston then returns "333 Northbelt" five times
and a radius search near the LA tower returns "Eighth & Grand" five times: the same
building, once per scan. The door collapses the kit to one row per property
(`index.property_key`: `PropertyId`, else `ResidentialListingId`, else the sid),
after filtering and before ranking so the representative does not change with the
query point. `all_scans=True` returns every model, and `api.scans_for_property(sid)`
lists the siblings of one result — which is also the D5 criterion that an office with
several models reports the alternatives.

The **fixtures are not collapsed**, deliberately. `search_results.json` carries three
suites of the LA tower on purpose, and one of them — `BkjvwqdchVY`, 2 rooms and **93
panoramas** — is the open-plan scan the desk-placement demo wants. Collapsing a
curated set of nine to tidy a list that is already short would throw that away.

**`use_type` comes from the property record, never from which CSV the row was in.**
2,765 of the 3,339 commercial properties are Multifamily and only 289 are Office, so
`segment="commercial"` and `use_type="office"` are very different questions. One
table, `index.use_type_for(kind, code)`, keyed by CoStar's enum **code**: `api.py`
had a second table keyed by enum *name* that had to agree with it, and two tables
that must agree eventually do not. Mapping notes:

- `Multifamily` (11) → `multifamily_unit`: a Matterport scan of a multifamily
  property is a scan of one unit, and the contract has no "multifamily building".
- `Flex`, `Industrial`, `Hospitality`, `Healthcare`, `Land`, `Specialty` → `other`,
  not `unknown` — we know what they are, we just have no template for them.
- `Townhouse` (2) → `single_family`: one dwelling with party walls, and the party
  wall is a surface adjacency, not a different use type.
- `listingPropertyType` looks like a flag set (its values are powers of two) but all
  2,120 records carry a single flag. A composite value would be **new data** and is
  reported as `unknown` rather than guessed at by picking a bit.

**Scan statistics are not in the kit.** `pano_count`, `room_count`, `floor_count`,
`has_splat` and `has_defurnished` come from Matterport, and filling them for 14,932
models means 14,932 GraphQL calls against a key shared with every other team. They
keep their contract defaults in the index and get real values when the bundle is
fetched. **A caller must not read a zero from search as "this scan has no
panoramas".** The golden properties keep their fixture summaries, which do carry the
real counts, and a kit row for a property a fixture already represents is dropped —
otherwise the LA office appears twice, once with its 36 panoramas and once as a
sibling scan with zeros.

**A CSV row whose parent record the kit does not ship stays findable.** Its address is
still real data, so it is indexed with `use_type: "unknown"` rather than dropped.

The index is also what `get_property_summary` falls back to, so **any** of the 14,932
models has a summary, not only the golden five, and live bundle assembly now names
buildings properly: `jfiEvosX974` is "Executive Tower", not "11400 Olympic Blvd".

**No kit mirror, no change.** The mirror is 49 MB of licensed sponsor data and is
never committed, so a teammate's checkout has none; `index.summaries()` is empty
there and search behaves exactly as it did before D7. Verified by running the lane
suite both ways: 115 passed / 15 skipped with the mirror, 100 passed / 30 skipped
without, no failures either way.

### 2.5 Field rules that are easy to get wrong

[V] from `models/commercial-property.md` and `schemas/enums.json`

- **Residential records differ from commercial ones in two ways.** `property.yearBuilt` **is** a plain scalar there (1920 on the golden house), unlike commercial; and residential area is a **range**, `property.sqftMin`/`sqftMax` (1628/1628 on the golden house), not a single field. [V] 2026-11-14
- **`property.propertyType` on a residential record is ambiguous — do not use it.** On the golden house it is `1`, which under `PropertyResidentialType` means `ApartmentCommunity`, contradicting the record's own `mlsPropertyType` of "Residential Single-Family, Single Family Residence". `listingPropertyType` is also `1`, which under `ListingPropertyType` means `Detached` and agrees. Use `listingPropertyType` with the `ListingPropertyType` enum. [V] 2026-11-14
- **No owner name exists on a property record.** `commercial-property` carries only `isOwnerOccupied` and `apartmentOwnershipType`; `compOwners` is on sale comps (D10). `CostarData.owner_name` stays null. [V] 2026-11-14
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
- **Houston office** (third golden property, added 2026-11-14 so the Texas path keeps a demo vehicle): `PropertyId 234088` = 2100 West Loop, Houston TX 77027. `propertyType` **5 = Office**, `buildingClass` **A**, Existing, built **1974**, GBA **162,540 sq ft**, typical floor 10,159, **16 storeys**, `propertyOffice` populated, 9 models.
  **Houston office `sid` = `L3266YcPPvd`** ("2100 West Loop S Fwy - Full Floor Suite 500") — 6 rooms totalling 814.5 m², of which one open plate is **761.9 m²**, plus **88 panoramas**; room heights 2.57–2.75 m. Chosen over `rEpuTTQ1zEv` (Suite 200, 7 rooms, 465.8 m², 48 panoramas) because a full open floor plate suits desk placement and gives the richest tour. None of the nine has a defurnished view.
  **It passes the City of Houston test, and CoStar cannot answer that question.** Texas PACE lists the city, not Harris County outside it. Resolved against the **US Census Bureau geocoder** (`geocoding.geo.census.gov/geocoder/geographies/coordinates`, `layers=Incorporated Places`): `234088` and `23551` return **"Houston city"**; `240022` (3934 FM-1960, 77068) returns **no place — unincorporated**, so it would fail PACE. **All three carry CoStar `cityId` 5316 "Houston", including the unincorporated one**, so that field is the mailing city and must never be used for PACE eligibility. [V] 2026-11-14
  **eGRID: ERCT.** ZIP 77027 inside the city limits means CenterPoint Energy Houston Electric is the TDU, which EMI-01 maps to **ERCT**, `EF_avg` 0.33413 kg CO₂e/kWh. Confirm from a bill if one becomes available. `23551` (7457 Harwin Dr, 77036, class B, 1983, 10 models) is the backup.

  **Office `sid` = `jfiEvosX974`** ("Executive Tower - Suite 140 - 4,410 SF") — richest of the nine: 8 rooms, 36 panoramas, 1 floor. Others: `2cLAWCVj1tA` (Suite 1530, 6 rooms), `vNxGNVDgVs9` (Suite 400, 5 rooms), `YbKz5PKbzwp` (Brentwood Executive Plaza, 5), `BkjvwqdchVY` (Suite 1100, 2 rooms but **93 panoramas** — the open-plan alternative for desk placement), `C7sMGY7UZfL`, `5xViZEoqi5n`, `bZ8jxbUviCF`, `iAw7TsDLoof`. **None of the nine has a defurnished view.**
- **House**: Matterport `zvKHR9DHNjJ` = 5836 La Mirada Avenue, Los Angeles, CA. Residential — correctly absent from `commercial-properties.csv`. Its row: `ListingId 235967170`, `ResidentialListingId 221139020`. [V]

---

## 3. Matterport Model API

### 3.1 Transport

- `POST https://api.matterport.com/api/models/graph`, GraphQL, HTTP basic auth: key as user, token as password. [V]
- Production only. Well under 10 req/s; keys are shared. [V]
- Null fields are **omitted, not sent as null** — code for absent keys. [V]
- **A response can carry `errors` and usable `data` at the same time, and treating any `errors` as fatal throws away a complete answer.** [V] 2026-11-14, found while building D2. Asking for `view(type: "matterport.model.defurnished")` on a model that has none returns:

  ```json
  {"errors": [{"path": ["model","view"], "extensions": {"code": "not.found", "httpCode": 404}}],
   "data":   {"model": {"id": "...", "rooms": [ ...8 rooms... ], "view": null}}}
  ```

  The model is **fully populated**; only the optional field failed. So a client must fail only when `data.model` is unusable, and turn field-scoped errors into provenance. D2 records a `not.found` as `FetchRecord{layer: "matterport", status: "missing"}` — a normal outcome, since only 6,979 models have a defurnished view — and anything else as `status: "error"`.
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

| Houston office `L3266YcPPvd` "Full Floor Suite 500" | 29.746027599 | −95.457545726 | **0.0** | −0.6983887, 0.7157187 | **≈88.6°** | `processing` |

**`altitude` is unusable.** It reads 0.0 on `L3266YcPPvd` but **29.6 on `rEpuTTQ1zEv`, another model in the same building** — so it is inconsistently populated even within one property. The LA office reports **`altitude` 0.0** against the house's 120.2, so altitude is not reliably populated and must not be used as terrain elevation — take that from Vexcel `ground-elevation`. The office quaternion also has a **negative** z, so its rotation runs the other way from the house's; whatever convention the contract fixes has to handle both signs.

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

Adding all nine models of the Houston office `234088`, also zero openings, that is **30 office models sampled with no windows between them**, including every model of both golden offices. The openings graph is populated on residential scans and essentially absent on commercial ones. This is systemic, not a property-selection artefact: **office window surfaces can never come from the scan**, whichever office is chosen.

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
- **The `layer` set changes which collection is selected, and so changes every attribute.** [V] 2026-11-14, found while building D3. The same point on the LA office:

  | `layer` | collection | structures | primary footprint | height |
  |---|---|---|---|---|
  | `urban` | `us-ca-losangeles-2023` | **1** | 2,207.43 m² | −15.338 |
  | `urban,urban-r,wide-area,urban-g` | `us-ca-losangeles_rf08-2023` | **2** | 2,473.94 m² | −14.223 |

  Structure count, footprint, roof elevation and height all move, so the tutorial's advice to pass every layer silently changes the parcel decomposition. **D3 pins `layer=urban`** — both cities are urban and obliques exist only there — and carries the collection on `VexcelData.collection` so any result can be traced to the flight it came from.
- **`403` means outside the licensed coverage, as distinct from `404` meaning no parcel inside it.** A point at 0°,0° answers 403. Both are normal outcomes and are reported as `FetchRecord`s. [V] 2026-11-14
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

**`|roof-characteristics.height|` = `|roof elevation − ground elevation|`, and the sign is unreliable.** [V] 2026-11-14, three lots each measured with a single `include=precomputed,calculated` call:

| Lot | ground | roof | reported height | signed fit |
|---|---|---|---|---|
| House (190.4 m², gable, 1 storey) | 100.584 | 100.220123 | **+0.363877** | ground − roof |
| LA office 246899 (2,207.4 m², flat, **17 storeys**) | 54.5592 | 70.056587 | **−15.497387** | ground − roof |
| Houston office 234088 (4,320.2 m², flat, **16 storeys**) | 19.5072 | 35.216709 | **+15.709509** | **roof − ground** |

The absolute value matches `|roof − ground|` on all three; the sign comes out +, −, + with no apparent pattern. **Take `abs()` and never rely on the sign.**

> **This section has now been corrected twice.** The first version said *roof − ground*, inferred from a `precomputed`-only response paired with a `calculated`-only one, which this section's own rule forbids. The second said *ground − roof*, which fitted the house and the LA office but is contradicted by the Houston office above. Three samples were needed before the real behaviour was visible — one sample can confirm a wrong formula.

**The magnitude is wrong on both towers, and now the cause is clear.** They report 15.5 m and 15.7 m against roughly 47 m and 44 m expected at their own measured room heights. Their detected footprints are **1.7× and 4.6×** the CoStar typical floor plate (1,313 m² and 944 m²), so Vexcel is outlining a low podium or garage on both. **So `footprint.area` and `height` describe the podium, not the tower** — which also bounds how `footprint.area` may be used for rooftop PV area on a tower. The house value additionally **changed between calls** (0.4254 standalone vs 0.3639 combined), and the LA office returned **−15.497 then −15.338 for identical parameters**, so the calculated elevation and height are **not reproducible**. Never assert equality on them and never derive a dimension from them.

**Catching the podium case needs the storey count.** An absolute floor alone (reject under ~2.5 m) catches the house's 0.36 m but not a tower's 15.5 m, which looks like an ordinary low building. D3's `plausible_building_height(attrs, stories=...)` compares the rise against `stories × 2.2 m`, so the caller passes CoStar `numStoriesAboveGrade`; both golden towers then fail it as they should.

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

### 4.4a What D8 built, and the three numbers that decide how to use it

`backend/data_layer/imagery.py`, 2026-11-14. [V] all measured live on the golden
house parcel. Section 4.4 said SAM 3's label quality is poor; this says what it *is*
good for, and the answer is narrower and more useful than expected.

**The pixel-to-map transform exists and is exact.** 4.4 left `images[].metadata` as
`[P]`. It carries `geometry` (the image footprint, an axis-aligned polygon), `width`,
`height`, `srid`, `collection` and the capture dates, so pixels map linearly onto the
footprint. The direction was **not** assumed: the response gives both `pixel-bbox` and
a map-coordinate `bbox` for every detection, so the transform can be checked against
the service's own answer. Over all 13 detections and both corners:

| Assumption | mean corner error | worst |
|---|---|---|
| **row 0 = north** | **0.024 m** | 0.124 m |
| row 0 = south | 17.1 m | 34.8 m |

Sub-pixel one way, a third of the parcel the other. North-up it is.

**Do not use `min-gsd` or `max-gsd` for scale.** They bracket the truth without
matching it — reported 0.05623 and 0.07821 m/px where the footprint and pixel
dimensions imply 0.06182 by 0.06140. Using `min-gsd` under-states ground area by
about **17 %**. The footprint and the pixel dimensions are the scale.

**`pixel-bbox` can start outside the image.** The first detection on the golden house
has `x = -1`, so coordinates are clamped before being transformed.

**`features` is one feature per detection.** 4.4's "13 detections" was 13 *features*,
each with `properties.label` and a `properties.detections` list of length one.

#### Roof area is the thing SAM 3 is actually good for

With the transform in hand, each mask's ground area is its white-pixel count times
the per-pixel area. The result is a genuine capability and three traps:

| | m² | vs the 190.4 m² precomputed footprint |
|---|---|---|
| **Largest single mask** (conf 0.484) | **180.9** | **−5 %** |
| Sum of all 13 masks | 485.8 | **+155 %** |
| Highest-confidence mask (0.695) | 38.8 | a different building |

1. **Never sum.** The masks are *nested*, not adjacent: 8 of the other 12 detections
   are **100 %** inside the largest one's box and 3 more are 81–97 % inside. Summing
   over-states by 2.6×.
2. **Never rank by confidence.** The most confident detection sits **0 %** inside the
   largest one. This parcel has two structures (4.2), and 0.695 is the secondary —
   ranking by confidence hands back the garage.
3. **Never use the bounding box.** Mask fill ran **43–93 %** of its own box, so box
   area over-states a fragment by up to a factor of two.

So `imagery.roof_area_m2()` returns the **largest single mask**, and the
`FetchRecord` names which detection it came from and its confidence. Agreeing with an
independently-sourced footprint to 5 % is what makes this usable at all; the three
obvious alternatives are wrong by 17 %, 155 % and 2×.

#### `mask_wkt` is left unset, deliberately

The contract describes it as "map polygon derived from the pixel mask". The two honest
options were a convex hull and the exact rectilinear outline, and **a hull is the
dangerous one**: it is a valid single-ring polygon that a consumer would reasonably
take the area of, and for a concave roof fragment that area is wrong by an amount
nothing in the payload reveals. `bbox_wkt` already gives location and
`roof_area_m2` gives true area, so a hull would add no capability and one silent trap.
`mask_area_m2` is proposed to @yalexie1 as an additive contract field; until then the
number comes from `imagery.detect_with_areas()`.

#### Consequences for other lanes

- **Obstruction counts stay on the precomputed `roof-objects` attributes.** SAM 3
  missed a chimney they report, invented two skylights they say do not exist, and
  found one of five roof vents. `SPEC.md` 16 lists this as a risk with precomputed as
  the fallback — the fallback is the primary.
- **Roof *geometry* stays with A11's parametric planes.** 13 fragments on one small
  house is not plane segmentation.
- **Roof *area* is now measured rather than inferred**, to 5 % on the one case where
  an independent number exists to check against.
- `Pillow` joins the data lane's dependencies, to decode the base64 PNG masks.

### 4.5 Golden lots

- **House**: `POINT(-118.3171 34.093491667)`, from the model's own `geocoordinates`. 2 structures. [V] `primary-structure` True, `footprint.area` 190.39 m², `ground-elevation` 100.584, roof `gable`/`shingle`, `condition.precise-value` 4.53, `tree-cover` 4.0, `ac-unit.count` 2, `chimney.count` 1, `roof-vent.count` 5, `skylight.count` 0, `solar.value` False, `building-type.class` **null**.
- **Office**: `POINT(-118.44311817454468 34.036533907520074)` = 11400 Olympic Blvd, LA 90064 (`PropertyId 246899`), from `geocoordinates` on `jfiEvosX974`. [V] 2026-11-14 — 1 structure, `primary-structure` True, `footprint.area` **2,207.43 m²**, `ground-elevation` 54.5592, roof **`flat`** / **`membrane`**, `condition.precise-value` 3.17, roof `tree-cover` 0.0, parcel `tree-cover` 5.0, `ac-unit.count` **0**, `skylight.count` 0, `solar.value` False, `building-type.class` **null**.

- **Houston office**: `POINT(-95.45754572577202 29.74602759879178)` = 2100 West Loop, Houston 77027 (`PropertyId 234088`), from `geocoordinates` on `L3266YcPPvd`. [V] 2026-11-14 — 1 structure, `footprint.area` **4,320.15 m²**, `ground-elevation` 19.5072, roof **`flat`** / **`membrane`**, `condition.precise-value` **2.88** (more degraded than the LA office's 3.17, so a stronger retrofit case), parcel `tree-cover` 6.0, `skylight.count` 0, `solar.value` False, **`building-type.class` `"commercial"`** — populated here where it is null on the house and the LA office, confirming it is usable only as an optional cross-check.

**`HVAC_RTU` becomes demonstrable on the Houston office.** Vexcel reports **`ac-unit.count` = 2** on this building, against 0 on both the LA office and the house. `physics.md` has `HVAC_RTU` and `HVAC_ECON` returning not-applicable until a rooftop unit is confirmed; this property confirms one, so the two measures have a demo vehicle.

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
| Retail electricity price, **all three golden properties** | **EIA API v2** `electricity/retail-sales`, state average | free EIA key, `EIA_API_KEY` | [V] 200 for TX and CA, commercial and residential |
| Utility tariff, Los Angeles | ~~**NREL URDB**~~ — **off the path**, see 5.1c | free NREL key (`DEMO_KEY` works for probing) | [V] returns LADWP, `eiaid` 11208, but unused |

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
| `wind_m_s` | m/s (Open-Meteo returns km/h — convert, ×1000/3600) | `wind_speed_10m` |

**What D9 writes is one real calendar year, not a TMY.** Building a true typical meteorological year needs multi-year statistics that are out of scope here, so `weather_source` names the exact year fetched and the inter-annual spread comes from PVGIS `SD_y` rather than being invented. A year short of 8,760 rows is reported as `FetchRecord{layer:"weather", status:"fallback"}` rather than passing silently.

**`weather_time_convention` = `hour_end`.** [V] 2026-11-14, verified two independent ways on the golden house:

1. **Full-hour means, not instantaneous samples.** The 24 hourly `shortwave_radiation` values for 2024-06-21 sum to 8,312 W/m²·h = **29.923 MJ/m²**, against the daily `shortwave_radiation_sum` of **29.92 MJ/m²** — ratio **1.0001**. If the values were instantaneous samples the sum would not reconcile with the daily total.
2. **The stamp labels the hour that *ends* at that time.** Sunrise was 04:42. GHI reads 0.0 at the 04:00 stamp, **2.0** at 05:00, 85.0 at 06:00. Under an hour-*start* reading, the 05:00 stamp would cover 05:00–06:00 with the sun already 18–78 minutes up and would have to read roughly 60+, not 2.0. Under hour-end it covers 04:00–05:00, which contains only the 18 minutes after sunrise at 0–3° elevation — which is exactly what 2.0 looks like.

So an hour stamped `05:00` is the mean over `04:00`–`05:00`. **Anything that treats it as the following hour shifts every solar calculation by one hour.**

### 5.1b Both golden properties are now in Los Angeles

Choosing `246899` over the Houston warehouse puts **both** golden properties in Los Angeles. Four consequences: [V] 2026-11-14

1. ~~**Both use the real LADWP tariff** from URDB (`eiaid` 11208), so the EIA state-average fallback is **off the demo path**.~~ **Superseded 2026-11-14 by the lead** (board #6873683873): all three golden properties take the EIA state average. See 5.1c.
2. **Both are eGRID subregion CAMX.** ZIP 90064 has prefix 900, inside the range EMI-01 confirmed for all 533 LA-area ZIPs (900–918). So `EF_avg` = **0.19504 kg CO₂e/kWh** for both, and the ERCT-versus-SRMV ambiguity that affected Houston ZIP 77080 **disappears**.
3. **The 3.35× Texas/California price gap leaves the demo.** The weaker-Houston-economics warning below no longer applies to either golden property, though it stays true for any Houston run.
**Resolved 2026-11-14:** a third golden property, the Houston office `234088` / `L3266YcPPvd`, was added so the Texas path keeps a demo vehicle. The demo now shows both states — the California price and CAMX on the LA house and LA office, and the Texas price, ERCT 0.33413, the Texas documents and the Texas C-PACE route on the Houston office. The EIA state-average fallback is therefore **back on the demo path** for that property, and the 3.35× price gap becomes a visible, honest contrast between the two offices rather than a hidden surprise. Items 1–3 above still describe the two Los Angeles properties.

4. **~~Texas now has no demo vehicle.~~** `specs/legal/texas.md`, the Texas documents 2–6 and the Texas PACE Act route in `SPEC.md` §6.6 have no golden property to run against, while California does. That is a real cost of this choice: either accept that Texas is specified but not demonstrated, or add a Houston office as a third property. Flagged, not decided — candidates are in §3.3.

### 5.1c One price source for all three properties — the lead's decision

**Decided 2026-11-14 by @yalexie1 (lead), board #6873683873.** Every golden property
takes its electricity price from the **EIA state average**, not from a looked-up
utility schedule:

| Property | State | Sector | Price | `FetchRecord` |
|---|---|---|---|---|
| LA house `zvKHR9DHNjJ` | CA | RES | **0.2975** USD/kWh | `tariff / fallback` |
| LA office `jfiEvosX974` | CA | COM | **0.3002** USD/kWh | `tariff / fallback` |
| Houston office `L3266YcPPvd` | TX | COM | **0.0896** USD/kWh | `tariff / fallback` |

`Tariff.source` names EIA with the state, sector and period, and the `fallback`
record sits beside it, so no reader mistakes a state average for the building's
retail contract. **LADWP is unchanged as the utility** for net metering, the LADWP
rebates and eGRID CAMX — the decision is about where the *price* comes from.

**URDB stays off the path. My call, and the reasons:** [V] 2026-11-14

1. **It cannot serve all three properties.** URDB returns 0 rates at the Houston
   office for every sector filter, because ERCOT is deregulated and there is no
   single regulated schedule to look up. So the EIA path has to exist regardless,
   and one sourcing path for three properties beats two.
2. **The contract carries a single marginal price.**
   `Tariff.electricity_usd_per_kwh` is one number, so a URDB time-of-use schedule
   has to be flattened to an average anyway. That flattening is itself an
   assumption, and it is less traceable than "EIA, CA, COM, 2026-08".
3. It remains implemented-adjacent and documented here, so it is a half-hour of work
   if the finance lane later wants a real LADWP schedule and the contract grows a
   place to put one.

**`Tariff.utility` is a separate, open question.** [P] It currently reads
`CA state average (RES)`, not `LADWP`, and the easy fix is unsafe: resolving the
utility from the CoStar `City` field would repeat the mistake the PACE work already
caught, where `cityId` 5316 "Houston" included a property that is **not** in the
incorporated city. LADWP serves the city of Los Angeles while surrounding
unincorporated county is SCE territory, so the same trap applies. Doing it properly
means the Census incorporated-place lookup that answered the PACE question — which
is cheap, but whether `utility` must literally read `LADWP` depends on how the
analysis and legal lanes key the rebates off it. Raised with the lead; not guessed
at here.

**`Tariff.export_regime` is now set**, which it was not before: `net_metering` for
California and `none` for Texas. This is the contract's own rule — the field's
comment reads "None where no export price is mandated (Texas)" — and ERCOT mandates
no export compensation, so leaving it unset was losing data the schema asked for.

### 5.1d D14: which place, and therefore which utility

`backend/data_layer/places.py`, 2026-11-14. [V] This closes the `Tariff.utility`
question 5.1c left open, and answers a second one nobody had assigned to a package.

**CoStar's `City` is a mailing city, and the error rate is not small.** Measured
against the US Census Bureau geocoder's `Incorporated Places` layer:

| CoStar `City` | sample | actually |
|---|---|---|
| `"Houston"`, TX | 16 | **9 Houston city, 6 unincorporated, 1 Nassau Bay city** |
| `"Los Angeles"`, CA | 14 | **14 Los Angeles city** |

So the field is reliable for Los Angeles and wrong **7 times in 16** for Houston. This
is a **sample, not a census** — enough to justify the lookup, not a figure to quote as
the kit's true error rate. It confirms at scale what §2.4 caught on one property.

**Two consumers, both of which were getting a wrong answer rather than no answer:**

1. **C-PACE.** A28's `cpace_scenario(..., in_pace_region=...)` sets `eligible = False`
   for Texas unless it is `True`, and nothing supplied it, so the Houston golden
   office — the only property that demonstrates the Texas route — reported ineligible.
2. **`Tariff.utility`.** `incentives.py` inferred it from the CoStar city field, with
   8 `LADWP` and 4 `CenterPoint` registry entries keyed on the result.

One keyless Census call answers both: `Incorporated Places` and `Counties` come back
together. Verified live — a point off land returns no place rather than an error, and
Burbank, Glendale and Pasadena return their own names, which is what lets the module
decline to guess for the Los Angeles County cities that run their own utilities
(`california.md:1001`).

**The rule is the lead's, from the board.** City of Los Angeles → `LADWP`; elsewhere
in LA County → `SCE`, status `fallback`, flagged as needing confirmation; a city with
its own utility → **neither**; California outside LA County → not guessed, since the
state has about forty publicly owned utilities; **outside California → unchanged**.
The price always stays on the EIA fallback: `Tariff.source` carries the price
provenance and `utility` names who serves the meter.

**Texas gets no utility from this.** CenterPoint is the Houston wires utility but its
delivery area is not the city limit, so an incorporation test is the wrong instrument
— it says nothing about a property in unincorporated Harris County that CenterPoint
does serve. The field keeps its honest label there.

**`None` is not `False`.** A failed lookup returns `None` from both
`in_pace_region` and `utility_for`. A28 treats anything other than `True` as not
eligible, which is the right default — but "we could not check" must never be reported
to a user as "your property is not in a PACE region". The records distinguish them.

#### What this did and did not fix

Verified live on the Houston office: the region blocker is **cleared for all seven
priced measures**. Eligibility does not follow, and it is worth being precise about
why, because it is not a data gap:

1. `config.CPACE_RATE` and `CPACE_TERM_YEARS` are deliberately `None` — a rate is a
   market quote, so no payment is computed.
2. Supplying an illustrative 7 % over 20 years, every measure then fails Texas's
   `SIR >= 1` rule (ECO-12b): LGT_LED 0.74, PV_ROOF 0.25, HVAC_RTU 0.17.

That second result is the 3.35x price gap of 5.2 showing up exactly where this
document predicted it would. **Houston C-PACE may simply not pencil at 8.96 ¢/kWh**,
which is a real finding for the demo script rather than a bug to fix.

Also closed: the live-versus-fixture mismatch. `specs/examples/README.md:593` checks
`"LADWP" in tariff["utility"]`, which passed on the fixtures and would have failed on
live data. All three golden properties now pass it **live**.

### 5.1e D15: the gas price, and the unit that would have been wrong by 10x

`physics/04:1060` assigned this to the data lane as open — *"Houston gas price
default: no source opened; [P] Data lane (the gas utility's tariff or EIA state gas
prices)"*. [V] 2026-11-14.

**Why it mattered.** `Tariff.gas_usd_per_kwh` was never set, so on every live bundle
it was `None`, and three places in the analysis lane branch on that:

| Reader | With the price missing |
|---|---|
| `registry.py:182` | **Fixed by @yalexie1 in #201** — a missing price is now "unknown", and the home keeps its gas-furnace default at a lower confidence. D15 raises that confidence from 0.25 to 0.4 |
| `physics/systems/baseline.py:149` | assumes **electric** heating |
| `physics/systems/baseline.py:216` | assumes an **electric** water heater |
| `physics/systems/baseline.py:252` | prices gas energy at **0.00 USD/kWh** |

So A3's baseline still reads a 1920s Los Angeles house as all-electric. Supplying the
number removes the question.

**The unit trap, which is the real finding.** EIA prices gas in **dollars per thousand
cubic feet**, not per therm. Applying TAR-04's `usd_per_therm / 29.3071` to a `$/MCF`
figure overstates the price by a factor of about **10.37**, and nothing downstream
would error — it would just quietly make gas look as expensive as electricity. A
volume becomes energy through the heat content of gas delivered to consumers, about
1,037 Btu/cf, hence **1.037 MMBtu per MCF** and 303.915 kWh per MCF.

That factor carries about **±0.5 %** (heat content runs roughly 1,030–1,040 Btu/cf),
which is far inside the uncertainty already present in using a state average rather
than the building's own tariff. The reader can reconstruct the number: `Tariff.source`
carries the raw `$/MCF` figure, the period and the conversion factor.

`_eia_gas_usd_per_kwh` **refuses any series whose units are not per-MCF** rather than
converting it. The same lesson as D9: there, an offline fixture used a float where the
API sends a string, and the suite stayed green against a shape that cannot occur.

**Measured prices** (EIA annual, 2025; **annual** not monthly, because gas swings hard
with the heating season in a way the electricity price does not):

| | $/MCF | USD/therm | USD/kWh |
|---|---|---|---|
| CA residential | 22.01 | 2.1225 | **0.072422** |
| CA commercial | 16.56 | 1.5969 | **0.054489** |
| TX residential | 19.42 | 1.8727 | **0.063900** |
| TX commercial | 10.98 | 1.0588 | **0.036129** |

California dearer than Texas and commercial below residential, the same shape as the
electricity prices — a weak but real sanity check.

**Why the four values are committed.** The live route is slow and erratic: measured
1 s, 14 s, 41 s and 66 s on the four combinations, with 504s in between, and the
heat-content series 504'd outright. Waiting on it took a cold bundle from 2.5 s to
**44–76 s**, which is not a demo path. These are public EIA figures, not sponsor data,
and they change once a year, so the table is committed with its series ids and a test
that notices if it drifts. `EIA_GAS_REFRESH=1` still fetches live first, so the table
can be refreshed rather than rotting. Either route is labelled `fallback` — it is a
state average either way — and the record says which one answered.

After the table, a cold live bundle is **0.4–0.6 s** with the gas price present.

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

  **EIA returns numeric fields as JSON strings** — `"price": "8.96"` — so an `isinstance(v, (int, float))` guard silently rejects every real response. A hand-written fixture using a float will not catch it: that is exactly what happened here, and only the live test found it. [V] 2026-11-14

  **This is a state monthly average, not the building's actual retail contract.** In deregulated ERCOT the real price varies widely by retail plan, so the office `Tariff` must carry `source` naming EIA with the state, sector and period, and a `FetchRecord{layer: "tariff", status: "fallback"}` beside it. It is defensible and traceable; it is not a lookup of that building's tariff. As of the lead's decision below, **every** golden property is sourced this way, not just the Houston one.

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
| D4 | P0 | Cache + fetch records — **done**, see 6.5 | `data-cache` | `backend/data_layer/cache.py` | `FetchRecord` |
| D5 | P0 | The one public door | `data-api` | `backend/data_layer/api.py` | `PropertyBundle`, `PropertySummary` |
| D6 | P0 | Golden fixtures | each source agent, in its own subdirectory | `data/fixtures/costar/`, `/matterport/`, `/vexcel/` — **never the parent** | — |
| D7 | P1 | Index + office selection — **done**, see 2.4a | `data-costar` | `backend/data_layer/index.py` | `PropertySummary[]` |
| D8 | P1 | Imagery + SAM 3 — **done**, see 4.4a | `data-vexcel` | `backend/data_layer/imagery.py` | roof masks, ortho/oblique, roof area |
| D9 | P1 | External data | `data-costar` | `backend/data_layer/external.py` | weather, tariffs, emissions |
| D10 | P2 | The five unused datasets | `data-costar` | `backend/data_layer/costar_extra.py` | `OccupancyData`, `MarketData` |
| D12 | P1 | Splat + drone photos (track site) | `data-matterport` | `backend/data_layer/tracksite.py` | `splat_path`, `drone_photo_paths` |
| D13 | P2 | Portfolio screening by Vexcel filters | `data-vexcel` | `backend/data_layer/screening.py` | `PropertySummary[]` |
| D14 | P1 | Incorporated place, utility and PACE region — **done**, see 5.1d | `data-costar` | `backend/data_layer/places.py` | `Tariff.utility`, `in_pace_region` |
| D15 | P1 | Gas price on the tariff — **done**, see 5.1e | `data-costar` | `backend/data_layer/external.py` | `Tariff.gas_usd_per_kwh` |
| D11 | — | this file | lane owner | `specs/data-integration.md` | — |

**Critical path:** D0 (kit mirror) → D1 / D2 / D3 in parallel → D5 → D6. D4 can be stubbed from the contract and hardened later. D7–D10 come strictly after the walking skeleton.

### 6.2 Running agents in parallel

- **Three source agents at most**, one per working key set (unlabelled, `_B`, `_C`). Set `_D` is invalid. This cap is a rate-limit constraint, not a style preference — the keys are shared across every team.
- Each agent on its own `<issue#>-<slug>` branch, or a git worktree when two need the same dependency tree.
- **Branch from fresh `main` and open PRs against `main`** (AGENTS.md §3.2). `spec-draft` is **retired** as of PR #19 — do not commit to it or target it. `Closes #N` works again now that `main` is the merge target, so issues auto-close.
- **Tests** live in `backend/data_layer/tests/test_<package>.py`, one file per package, so two agents never write the same test file (workplan R11).
- **Live bundle assembly is opt-in: `live=True` or `DATA_LAYER_LIVE=1`.** Six modules import `data_layer/api.py`, including `backend/server.py` and the agent tools, and the server lane's checkpoint asserts `pytest backend -q` makes no network call. So the ordinary call path replays `specs/examples/` and records a `fallback` `FetchRecord` saying so; no caller can mistake a fixture for live data.
- **The bundle cache belongs to the live path only.** If the offline path read it, a machine where someone had once assembled live data would silently test against that instead of the fixtures, and the suite would behave differently from one checkout to the next. A regression test asserts a cached live bundle cannot leak into the offline path. On the live path the cache is what satisfies SPEC §14's "a second call is served from cache": measured 2.46 s to assemble against 0.0006 s from cache.
- **`climate` and `tariff` are required, so a missing one raises `IncompleteBundle` carrying the provenance** rather than substituting the fixture's numbers for live ones — that would fabricate data while looking successful.
- **Network tests are opt-in: set `RUN_LIVE_NETWORK=1`.** A plain `pytest backend -q` must stay offline for every lane, because the server lane's checkpoint asserts the whole suite makes no network call. Gating a live test on "a key happens to be present" quietly breaks that the moment someone fills in `.env`, so every network-touching test in this lane requires the flag as well as its key. The D1 kit tests are the exception and gate on the mirror being on disk, since reading a local file is not a network call.
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

### 6.5 What D4 actually does, and the one invariant that bit

`backend/data_layer/cache.py`, built 2026-11-14. [V]

**Measured.** With every source payload cached, a full live re-assembly of a bundle
drops from **2.9 s to 0.39 s** and makes no call to a sponsor API; the bundle cache
on top of that serves in **0.002–0.046 s**. The point is not the milliseconds, it is
that the keys are shared with every other team at the hackathon, so a demo that
re-assembles three times should query Matterport once.

**An injected transport bypasses the cache, read and write.** D5 shipped the opposite
once: its bundle cache was consulted *before* the live-or-offline decision, so on a
machine where someone had run a live assembly the tests silently ran against cached
data instead of the fixtures — and passed. A caller supplying the response is in
control of what comes back, and a stubbed response has no business being left on disk
for the next caller. Checked by running the whole lane suite with the cache empty and
with it fully populated from live runs: **150 passed / 15 skipped both ways.**

**A 429 is never cached.** It describes the service's last few seconds, not the
parcel, so a cached one would poison that point for every later run. A 404 *is*
cached: "Vexcel has never flown this parcel" is a stable fact about coverage.

**The URL invariant caught a real leak in my own code.** The rule above says no
signed URL is ever persisted, and the first version of the bundle cache broke it:
`CostarData.raw` is "the record as found in the kit" per the contract, and the golden
house's record carries **54 URL-valued fields** — `imagescdn.homes.com` image URIs
with query strings, agent profile images, brokerage websites. Three ways to fix it,
and only one is right:

- *Scrub `raw` in place on write* — then a cache hit disagrees with a fresh assembly.
  That is the worst option: silent, invisible, and exactly the class of bug the D5
  cache-ordering mistake belonged to.
- *Scrub `raw` at assembly* — then the field no longer is what the contract says it
  is, and the contract is not mine to redefine.
- **Strip `raw` from the cache entry and rebuild it on read.** Safe precisely because
  it is *local* data: the kit mirror is on disk, so `raw` comes back in about 0.04 s
  and the field stays truthful on both paths. Verified: `hit == miss` on all three
  golden properties, `raw` rebuilt in each.

If a URL ever survives the strip — a new field somewhere starts carrying one — the
write is **refused** rather than persisting or mangling it. The caller still gets its
bundle, with a `FetchRecord` saying it was not cached and why. A loud failure on an
unexpected shape is what a cache with a documented invariant owes its reader.

**Unreadable entries are deleted on read.** A pre-D4 bundle entry cannot be parsed by
this code, so it was dead weight that went on leaking those 54 URLs indefinitely. The
reader removes it; it is git-ignored and regenerable. A test asserts no entry anywhere
in the real cache carries a URL, so this cannot quietly regress.

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
| Houston office 234088 | kit record + 9 models profiled | 2026-11-14 | type 5 Office, class A, 1974, 162,540 sq ft, 16 storeys; `sid` `L3266YcPPvd` |
| City of Houston test | US Census geocoder, Incorporated Places | 2026-11-14 | 234088 and 23551 **"Houston city"**; 240022 **unincorporated** |
| CoStar `cityId` vs incorporation | 3 candidates | 2026-11-14 | **all `cityId` 5316 Houston incl. the unincorporated one — unusable for PACE** |
| Houston office Vexcel lot | live combined call | 2026-11-14 | flat/membrane, condition 2.88, **`ac-unit.count` 2**, `building-type.class` commercial |
| `roof-characteristics.height` rule | 3 lots, combined calls | 2026-11-14 | **`abs()` only** — magnitude = \|roof−ground\|, sign +/−/+ with no pattern |
| Tower footprint vs floor plate | 2 towers | 2026-11-14 | 1.7x and 4.6x the CoStar plate — Vexcel outlines the **podium**, not the tower |
| `altitude` within one building | 2 models of 234088 | 2026-11-14 | 0.0 and 29.6 — **inconsistent, unusable** |
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
| Kit index built (D7) | one pass over both datasets | 2026-11-14 | 14,932 models → **5,098 properties**; 264 office properties; 14,929 with coordinates; build 1.1 s, load 0.06 s |
| Search collapses repeated scans | `use_type=office, q=houston` | 2026-11-14 | before: "333 Northbelt" **5x**; after: once per property |
| Lane suite with and without the mirror | `pytest backend/data_layer -q` | 2026-11-14 | 115/15 skipped with, 100/30 skipped without — **no failures either way** |
| Search makes no network call | `socket.socket.connect` patched to raise | 2026-11-14 | first call 0.069 s, second 0.006 s, no connection attempted |
| Live bundle after D7 | all three golden, `refresh=True` | 2026-11-14 | 2.2–2.9 s; names now `Executive Tower`, `5836 La Mirada Avenue`, `2100 West Loop South` |
| Source payload cache (D4) | all three golden, two passes | 2026-11-14 | full re-assembly **2.9 s → 0.39 s**, zero sponsor-API calls on the second pass |
| Bundle cache round trip (D4) | all three golden | 2026-11-14 | 0.002–0.046 s; `raw` rebuilt from the kit; **hit == miss** on name, tariff and `raw` |
| No URL in any cache entry | regex over the whole cache tree | 2026-11-14 | clean — after fixing the bundle entry, which carried **54** URL-valued fields from `costar.raw` |
| Suite with an empty vs a fully populated cache | `pytest backend/data_layer -q` | 2026-11-14 | **150 passed / 15 skipped both ways** |
| `elements/detect` metadata (D8) | live, golden house | 2026-11-14 | `geometry` + `width`/`height` give the transform; `features` is one per detection |
| Pixel-to-map direction | all 13 detections, both corners, vs the service's own `bbox` | 2026-11-14 | **row 0 = north**: 0.024 m mean error against 17.1 m for south-up |
| gsd versus footprint scale | same response | 2026-11-14 | reported 0.05623/0.07821 vs implied 0.06182/0.06140 — **`min-gsd` is 17 % low** |
| Mask ground areas | 13 masks, pixel counts | 2026-11-14 | largest **180.9 m²** vs 190.4 m² precomputed (**−5 %**); sum 485.8 (**+155 %**) |
| Mask nesting | pixel-box containment, 12 pairs | 2026-11-14 | 8 **100 %** contained in the largest, 3 at 81–97 %, 3 disjoint — never sum |
| Highest-confidence detection | same response | 2026-11-14 | 0.695 is 38.8 m² and **0 % inside** the largest — the secondary structure |
| CoStar `City` vs incorporation, Houston (D14) | Census geocoder, 16 sampled | 2026-11-14 | **9 Houston city, 6 unincorporated, 1 Nassau Bay** — 7 of 16 wrong |
| CoStar `City` vs incorporation, Los Angeles | Census geocoder, 14 sampled | 2026-11-14 | **14/14 Los Angeles city** — reliable there |
| Census edge cases | Burbank, Glendale, Pasadena, Santa Monica, off-land | 2026-11-14 | municipal-utility cities return their own names; the Pacific returns no place, not an error |
| Golden properties placed | live, all three | 2026-11-14 | both LA → `Los Angeles city` → **LADWP**; Houston → `Houston city` → **`in_pace_region` True** |
| A28 region blocker cleared | live, all 7 priced Houston measures | 2026-11-14 | blocker gone for every one; eligibility then fails **SIR ≥ 1** (0.74, 0.25, 0.17) |
| Golden tariff check on live data | `README.md:593` rule | 2026-11-14 | **passes live** for all three, where it previously only passed on fixtures |
| EIA gas route discovered (D15) | `facet/process`, `facet/duoarea` | 2026-11-14 | `PRS` residential, `PCS` commercial; `SCA`/`STX`; **units `$/MCF`, not per therm** |
| Gas prices, all four | live, EIA annual 2025 | 2026-11-14 | CA 22.01/16.56, TX 19.42/10.98 $/MCF → 0.0724/0.0545/0.0639/0.0361 USD/kWh |
| Gas route latency | same four calls | 2026-11-14 | **1 s, 14 s, 41 s, 66 s** plus 504s; heat-content series 504'd — hence the committed table |
| Cold live bundle after D15 | all three golden | 2026-11-14 | **0.4–0.6 s** with gas present (44–76 s if the live gas route is waited on) |
| NREL URDB (LA) | live | 2026-11-14 | LADWP, `eiaid` 11208 |
| NREL URDB (Houston) | live, 3 sector variants | 2026-11-14 | **0 rates** — ERCOT deregulated; resolved by the lead's EIA decision, 5.1c |
| pvlib | wheel download | 2026-11-14 | 0.16.1 available locally |
| EPA eGRID factors | page only | 2026-11-14 | eGRID2023 current; **values not opened, unverified** |
| EIA API v2 retail price | live, TX + CA, both sectors | 2026-11-14 | 200; TX com 8.96, TX res 15.91, CA com 30.02, CA res 29.75 ¢/kWh (2026-08) |
| Measure cost data | — | — | **[P] not started, no owner** |
| Model-id uniqueness | both CSVs, full scan | 2026-11-14 | **307 ids have >1 parent** (55 commercial, 252 residential); 387 extra rows |
| GraphQL partial errors | live, office model | 2026-11-14 | `errors` **and** populated `data` together; absent `view` is a field-scoped `not.found` |
| Vexcel `layer` affects the answer | live, LA office, 2 layer sets | 2026-11-14 | different collection, **1 vs 2 structures**, different footprint and height |
| Vexcel calculated values reproducible? | live, repeated calls | 2026-11-14 | **no** — −15.497 then −15.338 on identical parameters |
| Vexcel 403 vs 404 | live, 0°,0° | 2026-11-14 | **403 = outside coverage**, 404 = no parcel inside it |
| Open-Meteo hour-end, re-checked | live, as an opt-in test | 2026-11-14 | hourly sum reconciles with the daily total, ratio 1.0001 |
| EIA numeric fields | live | 2026-11-14 | **`price` is a JSON string** (`"8.96"`), not a number — parse it |
| Live bundle, all 3 golden properties | `api.get_property_bundle(live=True)` | 2026-11-14 | all assemble in ~2.5-2.9 s and validate; 2nd call from cache in 0.6 ms |
| Residential field shapes | kit record + models/ | 2026-11-14 | `yearBuilt` scalar, area is `sqftMin`/`sqftMax` range, `propertyType` ambiguous |
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

# Example payloads for the shared contract

One house and two offices, written as JSON for every type in the contract (`specs/SPEC.md` section 9, `SCHEMA_VERSION` 0.3.3). Lanes build and test against these files until the real doors are live.

**These files are hand-made examples, not analysis output and not a capture of sponsor data.** No API response and no CoStar kit record is copied here. Three kinds of value appear, and section 2 separates them:

1. a short list of **real facts** about the three golden properties (identifiers, CoStar building facts, georeferences, a few Vexcel and PVGIS values that `specs/data-integration.md` or the Data lane already records);
2. **published figures** taken as they stand from the physics and legal specs (emission factors, unit costs, discount rate, default tables, incentive rules);
3. everything else, which is **ILLUSTRATIVE**: invented to be internally consistent, and saying nothing about the real buildings.

Every energy quantity (kWh used, kWh saved) is in the third group, so every dollar, payback, NPV, CO2 and value-uplift figure computed from them is illustrative too, even where the price, cost or factor behind it is a published one. Do not quote any of them as a finding.

## 1. Files

`house/` is the golden house, Matterport model `zvKHR9DHNjJ`. `office/` is the golden office in Los Angeles, model `jfiEvosX974` (CoStar `PropertyId` 246899). `office_houston/` is the third golden property, the Houston office, model `L3266YcPPvd` (`PropertyId` 234088). Each folder holds the same thirteen files.

| File (in each folder) | Contract type | Produced by | Where it appears in the API (SPEC section 10) |
|---|---|---|---|
| `property_summary.json` | `PropertySummary` | S1 Locate, Data | `GET /api/properties/{sid}` |
| `property_bundle.json` | `PropertyBundle` | S2 Ingest, Data | not served; `get_property_bundle(sid)`, agent file `/run/bundle.json` |
| `building_model.json` | `BuildingModel` | S4 Model, Analysis | inside `RunResult.building_model` |
| `baseline_result.json` | `BaselineResult` | S5 Baseline, Analysis | inside `RunResult.baseline` |
| `measures.json` | `MeasureResult[]` | S6 Measures, Analysis | inside `RunResult.measures`; each measure evaluated against the baseline |
| `plan.json` | `Plan` | S7 Plan, Analysis | inside `RunResult.plan`; selected and financeable measures evaluated against the state when they were picked |
| `run_request.json` | `RunRequest` | Frontend | body of `POST /api/runs` |
| `run_result.json` | `RunResult` | Agent and server | `GET /api/runs/{run_id}`; embeds the six files above unchanged |
| `run_events.json` | `RunEvent[]` | Agent and server | `GET /api/runs/{run_id}/events`, one array element per server-sent event |
| `document_request.json` | `DocumentRequest` | Frontend | body of `POST /api/runs/{run_id}/documents` |
| `document_draft.json` | `DocumentDraft` | S9 Draft, Agent | returned by the two `documents` routes |
| `plan_tenant.json`, `run_request_tenant.json` | `Plan`, `RunRequest` | as above | the same property run with `role: "tenant"`, to show measures skipped for the role |

`search_results.json` (top level) is a `PropertySummary[]`, the response of `GET /api/properties/search`. It holds the three golden properties, two other models of the Los Angeles office property (real model ids, same `costar_property_id`), and four invented entries whose `sid` starts with `EXAMPLE`. The Houston property has nine models, but the ids of the other eight are not recorded on main, so none is listed.

## 2. Which values are real, which are published, which are illustrative

### 2.1 Real facts about the three properties

Real means: verified live by the Data lane (`specs/data-integration.md`, 2026-11-14, or the Data lane's brief for this folder on the same date).

**House, `zvKHR9DHNjJ`**

| Value | Where | Source |
|---|---|---|
| Model id, address 5836 La Mirada Ave, Los Angeles, CA 90038, residential, has a splat and a defurnished view | `PropertySummary` | brief; data-integration 2.6 |
| 1 floor, 19 rooms, 39 panoramas | `PropertySummary` counts | brief. The example carries only 4 rooms and 3 panoramas |
| `ListingId` 235967170, `ResidentialListingId` 221139020; `record_id` equals the `ListingId` | `PropertySummary`, `CostarData` | data-integration 2.4, 2.6 |
| Label, area, width, depth and height of the four rooms (Living Room 28.87 m2, Dining Room 22.71, Kitchen 13.28, Bedroom 17.18 with no height) | `MatterportData.rooms` | brief |
| Wall thickness values 0.16 m and 0.28 m | `WallEdge.thickness_m` | brief. Which wall has which thickness is invented |
| Georeference: latitude 34.093491666999995, longitude -118.3171, altitude 120.2, rotation quaternion (0, 0, 0.7289895896353398, 0.6845247827531877), source `processing` | `MatterportData.georeference` | data-integration 3.2. `translation` was not recorded and is null |
| The model has measured openings of type `window` and `doorway`; window sills 0.63 to 1.11 m, widths 0.51 to 2.69 m, heights 0.91 to 1.49 m | `WallEdge.openings` | Data lane. Each window here is invented inside those ranges; which edge it sits on is invented |
| The MatterPak is unlocked but its resources are unavailable | `mesh_path`, `point_cloud_path` null; a `FetchRecord` with status `missing` | Data lane |
| Vexcel parcel: `structure.count` 2, `parcel-source` Bins, `parcel-tree-cover.percent` 30, `hardscapes.area` 128 | `VexcelData.attributes` | data-integration 4.2 |
| Vexcel primary structure: footprint 190.39 m2, ground elevation 100.584, gable, shingle, condition 5.0, roof tree cover 4, 2 AC units, 1 chimney, 5 roof vents, 0 skylights, no solar, `building-type.class` null, roof elevation 100.220123 and height 0.363877 (implausible, carried as returned) | `VexcelStructure.attributes`, `footprint_area_m2`, `RoofPlane.obstruction_counts` | data-integration 4.2, 4.3 |
| PVGIS for this lot, 4 kWp, 14 % loss, tilt 20, south: 7,016.92 kWh a year, standard deviation 161.45 kWh | `ClimateSite.pvgis_annual_kwh_per_kw` 1754.23, `pvgis_sd_fraction` 0.02301 | data-integration 5.1 |
| The electric utility is LADWP (the address is in the City of Los Angeles by the Census incorporated place); hourly weather comes from Open-Meteo with each value the mean over the hour ending at the stamp | `Tariff.utility`, `ClimateSite.weather_source`, `weather_time_convention` | data-integration 5.1; Data lane |

**Office, Los Angeles, `jfiEvosX974`**

| Value | Where | Source |
|---|---|---|
| Model id, name "Executive Tower - Suite 140 - 4,410 SF", CoStar `PropertyId` 246899, address 11400 Olympic Blvd, Los Angeles, CA 90064; 8 rooms, 36 panoramas, 1 floor; no splat, no drone photos, no defurnished view; `record_id` equals the `PropertyId` | `PropertySummary`, `CostarData`, `MatterportData` | data-integration 2.6, 3.4 |
| CoStar: `propertyType` 5 Office, class A, Existing, built 1989 (construction-complete event), gross building area = rentable area = 259,923 sq ft (24,147.6 m2), 17 storeys above grade | `CostarData` normalised fields | data-integration 2.6 |
| The property has eight other models; `BkjvwqdchVY` (Suite 1100, 2 rooms, 93 panoramas, open plan) and `2cLAWCVj1tA` (Suite 1530, 6 rooms) are listed | `search_results.json` | data-integration 2.6. "Executive Tower -" in their names and the 24 panoramas of `2cLAWCVj1tA` are invented |
| No openings at all on any of the property's models: no windows and no doors from the scan | `WallEdge.openings` empty; windows from vision | data-integration 3.3 |
| All eight rooms have empty classifications (no room label) | `Room.label` null | data-integration 3.4 |
| The largest room's `areaFloor` 157.82 m2 against width 1.46 m and depth 1.34 m; one room has no depth; room heights 2.90 to 3.21 m | `room_01`, `room_08`, `Room.height_m` | data-integration 3.4. Which room has no depth, and the other rooms' areas and heights inside that range, are invented |
| Georeference: latitude 34.036533907520074, longitude -118.44311817454468, altitude 0.0 (not terrain), rotation z -0.3548537 and w 0.9349218, source `processing` | `MatterportData.georeference` | data-integration 3.2. z and w are the seven digits recorded there (negative z: the opposite sense to the house); x = y = 0 is assumed; `translation` is null |
| MatterPak resources not available | `FetchRecord` with status `missing` | Data lane |
| Vexcel: 1 structure, footprint 2,207.43 m2 (probably a podium, about 1.7 times the CoStar floor plate), ground elevation 54.5592, flat, membrane, condition 3.17, roof tree cover 0, parcel tree cover 5, 0 AC units (a detection limit), 0 skylights, no solar, `building-type.class` null, roof elevation 70.056587 and height -15.497387 (ground minus roof; unusable for building height) | `VexcelData`, `VexcelStructure.attributes`, `RoofPlane.obstruction_counts` | data-integration 4.3, 4.5 |
| Electric utility LADWP (City of Los Angeles by the Census incorporated place), net energy metering, eGRID subregion CAMX | `Tariff.utility`, `Tariff.export_regime`, every `co2_kg` | data-integration 5.1, 5.1b, 5.1d; physics 04 TAR-03, EMI-01 |

**Office, Houston, `L3266YcPPvd`**

| Value | Where | Source |
|---|---|---|
| Model id, name "2100 West Loop S Fwy - Full Floor Suite 500", CoStar `PropertyId` 234088, address 2100 West Loop S, Houston, TX 77027; 88 panoramas; nine models for the property; no splat, no drone photos, no defurnished view | `PropertySummary`, `CostarData` | Data lane; data-integration 3.3 (candidate table) |
| CoStar: `propertyType` 5 Office, class A, Existing, built 1974, gross building area 162,540 sq ft (15,100.5 m2), 16 storeys | `CostarData` normalised fields | Data lane |
| A 761.9 m2 open plate plus five side rooms; no room labels | `room_plate` area; `Room.label` null | Data lane. The side rooms' sizes are invented |
| No openings on any of the nine models | `WallEdge.openings` empty; windows from vision | Data lane |
| `altitude` is unusable | `GeoReference.altitude_m` null | Data lane |
| The address is inside the City of Houston (Census incorporated place "Houston city"), so inside the Texas PACE region. CoStar `cityId` is only the mailing city and is **not** used for PACE eligibility | C-PACE notes, `TX-PACE-04` check | Data lane; legal texas 6.4 |
| Vexcel: flat membrane roof, condition 2.88, 2 AC units; the footprint outlines a podium or garage (1.7 to 4.6 times the CoStar floor plate); `roof-characteristics.height` unusable | `VexcelStructure.attributes`, `systems.hvac_type` `rooftop_unit` | Data lane |
| CenterPoint is the wires company; no regulated retail tariff and no mandated export price; eGRID ERCT | `Tariff`, a `FetchRecord` with layer `tariff`, status `fallback`, every `co2_kg` | physics 04 TAR-03, TAR-06, EMI-01 |

Real as vocabulary, in every example: the opening types `divider`, `doorway`, `opening`, `window`; the edge types `wall` and `invisible`; the georeference sources; CoStar `propertyType` 5 = Office and the construction event name `ConstructionComplete`; the Vexcel attribute keys used; the SAM 3 label `roof` and image ids of the form `ortho-1`, `oriented-1`.

### 2.2 Published figures, used as the specs give them

These are not facts about the buildings. They are the defaults and rules of the spec files, applied to illustrative quantities. The entry id is where to check each one.

| Figure | Value in the examples | Spec entry |
|---|---|---|
| Grid emission factors, kg CO2e per kWh | CAMX 0.19504 (non-baseload 0.43599) for the house and the Los Angeles office, ERCT 0.33413 (0.56586) for the Houston office | physics 04 EMI-01 |
| Gas emission factor | 0.18123 kg CO2e per kWh | physics 04 EMI-02 |
| Los Angeles electricity price | EIA California state average for August 2026: 0.2975 USD per kWh residential (house), 0.3002 commercial (LA office); `Tariff.source` names EIA, state, sector and period, with a `tariff` `FetchRecord` of status `fallback` beside it. The utility stays LADWP (City of Los Angeles by the Census incorporated place), so net metering, the LADWP rebates and CAMX are unchanged. The range is in section 2.3 | data-integration 5.1c, 5.1d |
| Gas price | EIA 2025 state average delivered gas price (D15), converted from USD per thousand cubic feet at 1.037 MMBtu per MCF (303.915 kWh per MCF): house California residential 22.01 USD/MCF = 0.072422 USD per kWh, LA office California commercial 16.56 = 0.054489, Houston office Texas commercial 10.98 = 0.036129. Never divided by 29.3071 (that is the per-therm conversion). `Tariff.source` carries the data layer's label (raw USD/MCF, EIA series, period, conversion factor), and a `tariff` `FetchRecord` `eia/natural-gas-price` of status `fallback` sits beside it, exactly as `backend/data_layer/external.get_tariff` writes it. No range: see section 2.3 | data-integration 5.1e; `backend/data_layer/external.py` `GAS_DEFAULTS` |
| Houston electricity price, commercial | 0.086 / 0.090 / 0.133 USD per kWh, source `published_default`, fixed charge 0 (EIA Texas commercial average 8.96 cents for August 2026 lands on the expected 0.090) | physics 04 TAR-06 |
| Export | Los Angeles (LADWP): net metering, kWh netted at the energy price, no separate export price. Houston: regime `none`, no export price, only the self-consumed share is valued | physics 04 TAR-03 |
| Real discount rate, sensitivity rate | 0.03, and NPV at 0.07 in `npv_sensitivity_usd` | physics 04 ECO-05 |
| Real energy price escalation | Los Angeles residential (house), Los Angeles commercial (LA office) and Houston commercial rows of the table, by analysis period | physics 04 ECO-06 |
| NPV, SIR, AIRR, IRR, simple and discounted payback, level payment, program SIR | formulas as written | physics 04 ECO-07 to ECO-12b |
| Unit costs | attic 20.75 / 27.14 / 40.93 USD per m2; air sealing 4.83 / 7.67 / 17.05 USD per m2; cool roof 13.52 / 20.27 / 27.03 USD per m2; heat pump 2,668 / 4,472 / 5,805 USD per ton; rooftop unit 2,090 / 2,297 / 2,713 USD per ton; economizer and controls 4,274 / 6,044 / 7,088 USD per unit; office LED 214 / 390 / 517 USD per luminaire; home LED 4.80 / 9.08 / 13.62 USD per lamp; thermostat 234 / 312 / 467 USD; solar 2.68 / 4.20 / 5.20 (home) and 2.60 / 3.35 / 4.10 (office, under 100 kW) USD per W; solar O&M 35.01 USD per kW a year | physics 04 COST-01 |
| No verified cost | `WIN_FILM`, `WIN_SHADE`, `PLUG_MGMT`: savings but no finance block, skipped as `no_cost_data` | physics 04 COST-01, SPEC 6.5 |
| Useful lives | solar 25, attic 25, rooftop unit 21, cool roof 20, heat pump 15, office LED 15, air sealing 15, economizer 15, home LED 10, thermostat 10, layout 5 | physics 04 COST-02 |
| Incentives | 25D expired (home solar); LADWP heat pump rebate 1,050 USD per ton, attic rebate 0.50 USD per sq ft, cool roof up to 0.60 USD per sq ft (house); LADWP CLIP 0.20 USD per kWh for office LED fixtures and BOSS up to 0.65 USD per kWh for envelope work, both `needs_confirmation` (pre-approval; CLIP needs an account over 200 kW); CenterPoint commercial programme with no verified amount; 48E at 30 percent for business-owned solar with three conditions; all utility rebates paid after installation | physics 04 INC-02, INC-13, INC-17, INC-10, INC-18, INC-19, INC-32, INC-05 |
| Value uplift | office plans: low 0, expected half capitalisation at the highest cap rate, high full capitalisation at the lowest; home solar: up to 4.00 USD per W, expected capped at net cost | physics 04 VAL-01, VAL-03 |
| Solar defaults | 430 W module of 1.722 by 1.134 m, DC/AC ratio 1.2, losses 14.08 percent (11.42 where shading is ray-cast), degradation 0.005 a year, weather band 1.2816 times the PVGIS deviation | physics 01 PV-04, PV-05, PV-07, PV-08, PV-09 |
| Roof | flat roofs (both offices): pitch 0 / 1.2 / 9.5 degrees, modules on racks at 15 degrees facing south at a ground coverage ratio of 0.70; 4 ft (1.2192 m) commercial perimeter, plus one interior pathway on the LA roof whose long side exceeds 45.72 m; 9 m2 per counted AC unit. House: setbacks 0.9144 and 0.4572 m, obstruction allowances per counted object | physics 01 ROOF-03 to ROOF-06, LAY-02 |
| Envelope and systems | house: as DEF-01 to DEF-08 (wall U 0.625 / 2.021 / 2.021, attic 0.182 / 0.403 / 1.703, single clear windows, ACH50 6 / 15 / 30, SEER 10 / 13 / 14, AFUE 0.64 / 0.78 / 0.80). LA office (3B-CA, 1980 to 2004): wall 1.249 / 1.249 / 5.678 (steel frame, the mass-wall "no requirement" value as the high), window 6.93 with SHGC 0.44, SEER 11.06 minus 10 plus 15 percent. Houston office (2A, before 1980): wall 1.306 / 1.306 / 1.931, window 6.93 with SHGC 0.54, EER 9.63 minus 10 plus 15 percent. Both offices: heating 0.80, leakage 2.0 / 7.5 / 7.5 L/s.m2 at 75 Pa, 0.00944 m3/s of outdoor air per person, lighting 10.76 / 19.48 / 19.48 and plug 8.61 / 10.76 / 10.76 W/m2, setpoints 21 and 24 C with 15.6 and 26.7 C unoccupied; window-to-wall default 0.20 / 0.30 / 0.40 named as the fallback behind vision | physics 02 DEF-01 to DEF-11, INF-05, ENV-04, HVAC-00 |
| Daylight | visible transmittance 0.40 / 0.68 / 0.80; target 300 lux, setpoint 500 lux; 2,600 occupied hours; score weights 0.4 / 0.3 / 0.3 with the 0.20 glare and 25 percent PPD limits; manual switching share 0 / 0.5 / 1.0 | physics 03 sections 0.3, 0.4, LCT-02, LCT-03 |
| Legal checks | requirement ids and citations; the CSLB notice in the LA office contract is the verbatim text of CA-COM-03 | `specs/legal/california.md` sections 2, 3 and 7; `specs/legal/texas.md` section 6 |

### 2.3 Illustrative, stated plainly

- **Every energy quantity**: the baseline end uses, monthly values, peaks, heating and cooling needs, and the kWh each measure saves. So are all the figures computed from them.
- **Prices with no published default**: the house's fixed charge. `Tariff.source` says so. Demand charges are not modelled.
- **No range on the gas price**: data-integration 5.1e gives the state average and only a plus or minus 0.5 percent heat-content uncertainty on the conversion, so the examples carry no `tariff.gas_usd_per_kwh` assumption and the gas price is a point value (as it was before D15). Gas is in the UNC-02 `price_level` group with electricity, so a future gas range would add linearly to the electricity price deviation in plan totals.
- **The width of the Los Angeles electricity price range**: data-integration 5.1c gives the expected price but no range, so the examples take a symmetric one whose half-width is the gap between the August 2026 month and the year-to-date average in the same EIA tables (the California check values of physics 04 TAR-06): residential 0.2692 / 0.2975 / 0.3258 (half-width 0.0283 against 32.58 cents), commercial 0.2696 / 0.3002 / 0.3308 (0.0306 against 26.96 cents) USD per kWh. The range covers both EIA figures and is the registry assumption `tariff.electricity_usd_per_kwh`.
- **PVGIS for the two offices**: no PVGIS run is recorded for either lot, so 1,690 (LA) and 1,330 (Houston) kWh per kW at a 15-degree rack, and their deviations, are invented. The house's PVGIS figure is real.
- **The Houston georeference**: its rotation is not recorded on main, so the quaternion (a 30-degree turn, north offset 330.00) and the coordinates (approximate for the address) are invented.
- **CoStar tenants and market data** (`occupancy`, `market`): the names carry "(illustrative)". `CostarData.raw` holds only a `_note`. The CoStar building facts in section 2.1 are real.
- **The wall graphs**: vertex positions, which rooms touch, the invisible edge, wall thicknesses. The LA suite is a 28.0 m by 14.0 m corner suite on floor 1 with two exterior walls (south-west and south-east under the real rotation); the Houston suite is a 36 m by 27 m full floor (floor 5) with the core on the north side. House rooms are rectangles from the real width and depth.
- **Windows read by vision**: every office window surface (one per exterior edge; 64.2 m2 and a window-to-wall ratio of 0.51 in Los Angeles, 123.5 m2 and 0.40 in Houston) and the house bedroom's one. Their sizes are invented.
- **Roof surfaces of the suites**: neither office suite has a roof surface (each sits under conditioned floors); the LA suite has a ground floor slab and the Houston floor slab is not modelled (conditioned floor below). Which floor each suite is on is read from the suite number, not verified.
- **Panorama positions and labels, floor plans, all cache paths.** No file behind any path exists.
- **Roof geometry**: every WKT polygon is a rectangle invented in the model frame and rotated to the map with the georeference. The LA plane is the real Vexcel footprint area; the Houston plane is the tower roof derived from gross building area / 16 storeys (943.8 m2), because the Vexcel footprint is a podium. The house planes "fitted from the splat", ridge directions and panel positions are invented.
- **Solar yield**: the per-panel shading values, the self-consumption fractions and the rack and weather factors of the range are invented.
- **Desk scores**: every daylight, glare, comfort, daylight-factor, sun-hour and asymmetry value. Only the score formula is the spec's.
- **SAM 3 detections**: invented, shaped as the Data lane delivers them (data-integration 4.4a): roof masks are nested fragments (most of the smaller ones sit wholly inside the largest one's box, a few 80 to 90 percent), `mask_wkt` is null and `mask_area_m2` is filled, each mask fills 43 to 93 percent of its box, the largest single roof mask is within 5 percent of the footprint (181.2 against 190.39 m2 on the house, 2,122.9 against 2,207.43 in Los Angeles, 2,296.4 against 2,400 in Houston), and the most confident detection is something else: the house's second structure, a plant enclosure on the LA roof, the Houston tower roof above the podium footprint. Boxes are axis-aligned map rectangles, as the service returns them; pixel boxes follow from an invented image origin and ground sample distance. No mask image exists.
- **HVAC sizes and counts**: the Houston rooftop units' 30 tons together, luminaire counts (48 and 112), thermostat counts.
- **Values with no default table**: partition U-values, the home lighting and plug densities, `infiltration_ach`, the duct location, `bedrooms`, the plus or minus 1 degree on `north_offset_deg`, the C-PACE rate and term (6.5 percent, up to 20 years), the capacity and efficiency of the proposed heat pump, the LA office's market value used in the 5 percent test (comparable sale price times gross building area).
- **Escalation for a 5-year period** (`LAYOUT`): the ECO-06 table has no 5-year column, so the 10-year column is used.
- **Documents**: the draft text is a sketch. Each `satisfied` value is illustrative. The Houston tenant's lease clause on alterations is invented.
- **Shared string keys**: assumption keys follow the lists suggested in physics 02 section 12, physics 03 section 0.4 and physics 04 TAR-06 where one exists; the rest, and the flag keys, are this folder's guesses (workplan open item O10).

## 3. Conventions these examples assume

Where the contract or a spec leaves a choice open, the examples take one reading. Treat each as a proposal until its owner confirms it.

1. **North.** `north_offset_deg` is `atan2(R[0][1], R[1][1]) mod 360` of the georeference quaternion (physics 01 ROOF-02): 266.40 for the house, 41.57 for the LA office (negative z), 330.00 for the Houston office (illustrative quaternion), each carried with plus or minus 1 degree. A surface's azimuth is `atan2(n_x, n_y) + north_offset_deg` for its outward normal in the model frame. Which way the quaternion rotates is still to be confirmed by the Data lane; if it is the inverse, the offsets become 93.60, 318.43 and 30.00 and every azimuth here changes.
2. **`Opening.relative_center`** is measured from the first id in `vertex_ids`. The Data lane has not confirmed the end.
3. **Surfaces follow the wall graph.** One wall `Surface` per exterior or demising edge (`source_edge_id`), one window per `window` opening and one door per `doorway` on such an edge (`source_opening_id`). A window read by vision has `source_opening_id` null and sits on the edge named in `source_edge_id`; the offices have one such surface per exterior edge, standing for all the windows seen on it.
4. **`RoofPlane.obstruction_counts`** repeats the whole roof's Vexcel counts on every plane, because the counts have no positions. Do not add them across planes.
5. **Flat roofs.** ROOF-05 gives a flat plane no azimuth, but `RoofPlane.azimuth_deg` is required, so it carries the rack azimuth (180) and `params.rack_tilt_deg` carries the rack tilt. `eave_length_m` and `slope_length_m` are null.
6. **`end_use_kwh`** has the six keys `heating`, `cooling`, `water_heating`, `lighting`, `plug`, `appliances`. Fan energy is inside heating and cooling, as physics 02 has it. Office hot water is not modelled (physics 02 DHW-02), so both office baselines carry `water_heating` 0 and the run a warning.
7. **Solar in `EnergyUse`.** `savings.electricity_kwh` and `co2_kg` use the whole generation. `savings.cost_usd` uses only what earns the retail price: the netted kWh under net metering, the self-consumed share where there is no export price. A tower-roof array feeds the building's own service; the suite's baseline is only the floor for the netting. `co2_nonbaseload_kg` is filled on measure savings only.
8. **Ranges** (physics 04 UNC-02, simplified). A measure's saving in dollars combines two independent groups in quadrature: the measure's own effect and the price level. A plan's expected totals are sums. Its cost range is the sum of the items' ranges (one correlation group, `cost_level`); its savings range combines each measure's own effect in quadrature and adds the price-level part of every item linearly (one group, `price_level`); its CO2 range combines the measures in quadrature. `baseline_after` combines the baseline's range and the selected savings in quadrature. NPV combines savings, cost and a plus or minus 1 point escalation band.
9. **Incentives** (SPEC 6.6, physics 04 ECO-13). Only `upfront_rebate` reduces `net_upfront_usd`. A verified rebate paid after installation, or a tax credit, enters NPV one year later and nothing else. An incentive whose `eligibility` is `needs_confirmation` has the amount range 0 / 0 / rule amount. `unverified` and `expired` entries are listed and carry zero.
10. **Money formulas.** Simple payback is net upfront divided by (annual savings minus the change in operation and maintenance). The cash scenario's first-year net cash flow is that same difference; the C-PACE one subtracts the level payment. `program_sir` is undiscounted savings over the term divided by all payments. In Texas, `eligible` is false when it is below 1 (program rule TX-PACE-30). California has no statutory SIR test, so there the ratio is a screen; a Los Angeles scenario is `eligible: false` because no programme taking commercial applications is confirmed (SPEC 6.6), and its notes give the 5 percent tax-plus-assessment test (Streets and Highways Code 5898.15) and say lender consent is programme practice.
11. **Who can do what in a tower suite.** Rooftop solar, rooftop units, economizers and the roof are the building owner's; a tenant plan skips them with reason `role`. Air sealing of the exterior wall needs the owner's consent (SPEC 6.2 "tenant with consent"). A measure that is not applicable to the building type, or not part of the suite's envelope (`ROOF_COOL` under 16 floors), is left out of `skipped`.
12. **Rooftop units.** `HVAC_RTU` and `HVAC_ECON` are evaluated only where a packaged unit is confirmed. Houston: Vexcel counts 2 AC units, so both are evaluated and priced, as owner measures, with a flag that which floors the units serve is not shown. Los Angeles: Vexcel counts none, which on a tower is a detection limit, so both are not applicable, `hvac_type` is `unknown` with a flag, and both are listed in `skipped` with reason `feasibility`.
13. **`RunEvent.stage`** is one of `S1` to `S9` or null. `RunEvent.payload` shapes used here:

   | `type` | `payload` |
   |---|---|
   | `stage_started` | empty |
   | `stage_done` | empty, or `{sid}`, or `{artifact}` with the agent file written |
   | `todo` | `{todos: [{content, status}]}` |
   | `tool_call` | `{agent, tool, args}` |
   | `fallback` | `{layer, from, to}` |
   | `question` | `{question: Question}` |
   | `partial_result` | `{kind: "baseline", artifact, annual_cost_usd: Ranged}` or `{kind: "finding", measure_id, anchor: Anchor}` |
   | `error` | `{code, message, recoverable}` |
   | `done` | `{run_id, status}` |

## 4. What each example shows

**House** (`role: owner_occupier`, budget $10,000). Measured windows: seven `window` openings with a window `Surface` each, plus one bedroom window read by vision, the single labelled case of the fallback. Selected: `PV_ROOF` (five modules on the splat-fitted south plane, sized by the budget, shading by ray casting, net metering, the warning "may exceed budget", a `value_uplift` on the measure) and `LGT_LED`. `ENV_ATTIC` saves more than the LED lamps but does not fit; `HVAC_HP` does not fit either, so both are skipped as `over_budget` and listed as financeable. `ROOF_COOL` is an upper bound on a vented attic that loses money at the EIA prices (minus 0.98 USD a year: 60 kWh of cooling saved at 0.2975 against 260 kWh of gas added at 0.072422), so it is skipped as `no_savings`; it had just broken even at the illustrative gas price of 0.065 and been financeable (#210). Skipped: `DHW_HPWH` (`feasibility`, a `blocked` flag), `CTRL_TSTAT` (`already_done`), `WIN_SHADE` (`no_cost_data`). `HVAC_DUCT` and `HVAC_RTU` are not applicable. No federal tax credit; the LADWP rebates are `rebate_after_install`, one confirmed and two `needs_confirmation`. Two-prong outlets and no visible panel give the flag `electrical.service` = `likely_upgrade` with an added cost of 2,250 / 3,000 / 4,500 USD (A8, `backend/analysis/vision/feasibility.py`); `PV_ROOF` and `HVAC_HP` carry it with a warning, and the cost stays outside the installed cost, as the measure code does. One question, on the electrical service size. The tenant variant selects only `LGT_LED` and skips the owner-only measures with reason `role`. Document: `retrofit_contract_residential`, California.

**Office, Los Angeles** (`role: landlord`, budget $25,000). Suite 140 of a 17-storey Class A tower. No openings: `window_source` is `vision`, the window surfaces have no opening behind them, and the layout carries the warning. Selected, in order: `LAYOUT` (zero cost, eight scored desk positions along the south-west glazing, four recommended; no daylight control, so the saving runs from zero), `LGT_LED` (48 troffers, $18,720; the LADWP CLIP rebate listed at zero until confirmed) and `PV_ROOF` sized to the $6,280 left: 4 modules, 1.72 kW on racks on the flat roof, net metered at LADWP, 48E as `needs_confirmation`, with "may exceed budget". `ENV_AIRSEAL` does not fit and is financeable; its C-PACE scenario is hypothetical and not eligible (no Los Angeles programme confirmed), and its notes carry the 5 percent test, which cannot be completed without the tax bill. `HVAC_RTU` and `HVAC_ECON` are not evaluated (`feasibility`): `hvac_type` is `unknown` with a flag, and the run's question asks about it. `CTRL_TSTAT` has `no_savings`, `WIN_SHADE` is `already_done`, `WIN_FILM` and `PLUG_MGMT` are `no_cost_data`, `ROOF_COOL` is not applicable (no roof over the suite). The tenant variant (budget $20,000) selects `LAYOUT` and `LGT_LED`, lists air sealing as financeable with the owner's consent, and skips solar and the rooftop measures for `role`. Document: `retrofit_contract_commercial`, California, for the LED retrofit, the work the owner can sign for now; a C-PACE package would be mostly blanks (no confirmed programme, and the assessment contract is the public agency's own form, CA-PACE-05), and even under C-PACE the installation contract is this section 3 contract (CA-PACE-06).

**Office, Houston** (`role: landlord`, budget $50,000). Full-floor Suite 500 of a 16-storey Class A tower. No openings: windows from vision on all four sides. Two rooftop AC units confirmed by Vexcel, so `hvac_type` is `rooftop_unit` and `HVAC_RTU` (30 tons, $68,910) and `HVAC_ECON` ($12,088) are evaluated and priced. Selected: `LAYOUT`, `LGT_LED` (112 troffers, $43,680, "may exceed budget") and `PV_ROOF` with the $6,320 left (4 modules on the tower roof, self-consumption only, no export value). Financeable: `HVAC_RTU`, `HVAC_ECON`, `ENV_AIRSEAL`, each with a Texas C-PACE scenario whose program SIR is far below 1 (0.16, 0.19, 0.14), so none is eligible although the property is in the City of Houston PACE region. Skipped: those three `over_budget`, `CTRL_TSTAT` `no_savings`, `WIN_SHADE` `already_done`, `WIN_FILM` and `PLUG_MGMT` `no_cost_data`. The tenant variant (budget $45,000) selects `LAYOUT` and `LGT_LED`, skips solar and both rooftop measures for `role`, and skips air sealing for `feasibility` (a `blocked` lease-consent flag). The electricity price is the TAR-06 `published_default` with a `fallback` record. Document: `cpace_package`, Texas, for the two rooftop measures, with the failing program test shown and `TX-PACE-04` satisfied from the Census place, not the CoStar mailing city.

Things worth knowing before the demo, all following from the rules as written. Ranking is by annual savings alone and rooftop solar is sized to whatever budget is left, so both office plans end with a 1.72 kW array on a tower roof. With the published Texas price and unit costs no Houston measure reaches a program SIR of 1. In Los Angeles the LED retrofit and solar would pass a program SIR screen (2.55 and 1.55 at the EIA price) but no programme exists to apply it.

Every example has assumptions from all seven sources, a not-applicable measure with its reason, and every `RunEvent` type. Across the three folders every skip reason and every flag status appears (the house no longer shows `unknown`; the LA office shows it, and `no_savings` appears in all three).

## 5. Re-run the validation

The script below takes the contract block from the current `specs/SPEC.md`, validates every JSON file in this folder against its type, and checks consistency:

- no file carries a field the contract does not have, and no value is changed by validation; every `Ranged` is ordered; every `schema_version` equals the contract's;
- wall graph: ids resolve, every room boundary is a closed loop and `Room.polygon` follows it, openings fit their edge and do not overlap;
- surfaces: `source_edge_id` and `source_opening_id` resolve, a window's area equals its opening, each azimuth is perpendicular to its edge under `north_offset_deg`, windows without an opening have a vision assumption; `north_offset_deg` matches the quaternion;
- every `room_id`, `zone_id`, `plane_id`, `pano_id`, `parent_surface_id`, evidence panorama and roof obstruction that is referenced exists;
- tariff: Texas has no export price and a `fallback` record; LADWP is net metering with no export price; the house and the LA office are LADWP in CAMX, priced at the EIA California average of data-integration 5.1c with a `tariff` `fallback` record; all three carry the D15 gas price (data-integration 5.1e: the EIA 2025 state average for their state and sector, converted per thousand cubic feet), with the data layer's label in `Tariff.source` and an `eia/natural-gas-price` `fallback` record; the Houston office uses the TAR-06 commercial default in the CenterPoint area, in ERCT, with the TAR-06 price range as its assumption; `weather_time_convention` is `hour_end`;
- baseline: twelve monthly values that sum to the annual figure; end uses sum to electricity plus gas and use only the six allowed keys; cost equals energy times the tariff;
- emissions: every `co2_kg`, and explicitly the baseline's, equals its kWh times the eGRID factor of the property's subregion and the gas factor of physics 04;
- measures: no finance block on a measure with no verified cost; only verified upfront rebates in `net_upfront_usd`; no federal tax benefit on a home; 48E only on commercial solar, unconfirmed, with conditions; analysis period, payback, AIRR, level payment and program SIR follow physics 04; C-PACE eligibility follows the state: in Texas a program SIR of at least 1 and notes on lender consent (399.010) and the PACE region, in California a hypothetical, ineligible scenario whose notes carry the 5 percent test and do not call lender consent statutory; `HVAC_RTU` and `HVAC_ECON` only with a confirmed rooftop unit, and evaluated and priced on an office whose Vexcel AC-unit count is above 0; `HVAC_DUCT` never; `HVAC_HP` with its three ratings; solar defaults filled, 3 percent shading on a parametric roof, home solar uplift by VAL-03;
- desk layout: metrics in range, score by LCT-03, `window_source` matches the bundle, a saving from zero where there is no daylight control;
- plans: each pick fits the remaining budget, zero-cost measures come first, the "may exceed budget" warning matches the cost range, expected totals equal the sum of the items and ranges stay inside the sums, `baseline_after` equals the baseline minus the selected savings, no unpriced measure is selected, `no_cost_data` carries its fixed detail, the plan value uplift follows VAL-01 and exists only for the offices; a tenant plan skips every applicable owner-only measure with reason `role`;
- SAM 3 detections as D8 delivers them: `mask_wkt` null, `mask_area_m2` filled, the largest ortho roof mask within about 5 percent of the primary footprint;
- across the three goldens, every `Flag` status and every skip reason appears;
- `run_result.json` embeds the other files unchanged; questions point at existing assumptions; events cover every type; the question event carries a valid `Question`;
- documents: run id, measures, state, and the list of unfilled placeholders match the text; every `requirement_id` exists in `specs/legal/california.md` or `specs/legal/texas.md` for the document's state; residential and commercial document types match the property.

Run it from the repository root. It needs Python 3.9 or later and `pydantic>=2`, reads only, and writes nothing.

```sh
python3 -m venv /tmp/contract-venv && /tmp/contract-venv/bin/pip install -q "pydantic>=2"
awk '/^````python$/{f=1;next} /^````$/{f=0} f' specs/examples/README.md > /tmp/validate_examples.py
/tmp/contract-venv/bin/python /tmp/validate_examples.py .
```

The last line of a passing run is `PASSED: <n> checks, 0 failures`; the exit status is 0. After any change to the contract block or to a file here, run it again.

````python
#!/usr/bin/env python3
"""Validate specs/examples/ against the contract block in specs/SPEC.md.

Usage:  python validate_examples.py [REPO_ROOT] [--examples DIR]

Needs Python 3.9+ and pydantic>=2. Reads only; writes nothing. The contract is taken
from specs/SPEC.md section 9 (between the contract:start and contract:end markers) at
run time, so the examples are always checked against the current contract.
Exit status 0 = every file validates and every consistency check passes.
"""
import json
import math
import pathlib
import re
import sys
import types

from pydantic import TypeAdapter

args = [a for a in sys.argv[1:] if not a.startswith("--")]
ROOT = pathlib.Path(args[0] if args else ".").resolve()
EX = ROOT / "specs" / "examples"
if "--examples" in sys.argv:
    EX = pathlib.Path(sys.argv[sys.argv.index("--examples") + 1]).resolve()
    args = [a for a in args if pathlib.Path(a).resolve() != EX]
    ROOT = pathlib.Path(args[0] if args else ".").resolve()

# ---------------------------------------------------------------- contract
spec_text = (ROOT / "specs" / "SPEC.md").read_text(encoding="utf-8")
block = re.search(r"<!-- contract:start -->\s*```python\n(.*?)\n```\s*<!-- contract:end -->",
                  spec_text, re.S)
if not block:
    sys.exit("contract block not found in specs/SPEC.md")
C = types.ModuleType("contract_schema")
sys.modules["contract_schema"] = C
exec(compile(block.group(1), "SPEC.md#contract", "exec"), C.__dict__)

PER_PROPERTY = {
    "property_summary.json": C.PropertySummary,
    "property_bundle.json": C.PropertyBundle,
    "building_model.json": C.BuildingModel,
    "baseline_result.json": C.BaselineResult,
    "measures.json": list[C.MeasureResult],
    "plan.json": C.Plan,
    "run_request.json": C.RunRequest,
    "run_result.json": C.RunResult,
    "run_events.json": list[C.RunEvent],
    "document_request.json": C.DocumentRequest,
    "document_draft.json": C.DocumentDraft,
}
OPTIONAL = {"plan_tenant.json": C.Plan, "run_request_tenant.json": C.RunRequest}
# Figures the examples must agree with (specs/physics/04-economics-emissions-mv.md, 02, 03).
EF_GRID = {"CA": (0.19504, 0.43599), "TX": (0.33413, 0.56586)}   # EMI-01: average, non-baseload
EGRID = {"CA": "CAMX", "TX": "ERCT"}                              # EMI-01 subregion by golden city
TX_COMMERCIAL_PRICE = (0.086, 0.090, 0.133)                       # TAR-06 commercial default
# data-integration 5.1c: Los Angeles electricity at the EIA California average (RES, COM), a fallback
CA_EIA_PRICE = {"house": 0.2975, "office": 0.3002}
# data-integration 5.1e (D15): gas at the EIA 2025 state average delivered price, read in USD per
# thousand cubic feet and converted at 1.037 MMBtu/MCF (never the per-therm 29.3071), a fallback
EIA_GAS = {"house": ("CA", "RES", 22.01, "N3010CA3"), "office": ("CA", "COM", 16.56, "N3020CA3"),
           "office_houston": ("TX", "COM", 10.98, "N3020TX3")}
KWH_PER_MCF = 1.037 * 293.071070172                               # 303.915 kWh (HHV) per MCF
# What each golden folder's tariff must be (data-integration.md 5.1b; physics 04 TAR-03, TAR-06)
GOLDEN_TARIFF = {"house": "LADWP", "office": "LADWP", "office_houston": "TX_DEFAULT"}
OWNER_ONLY = {"PV_ROOF", "HVAC_RTU", "HVAC_ECON", "ENV_ATTIC", "HVAC_HP", "ROOF_COOL",
              "DHW_HPWH", "WIN_REPLACE", "ENV_WALL", "HVAC_DUCT"}   # SPEC 6.2 "owner" only
EF_GAS = 0.18123                                                  # EMI-02
NO_COST = {"WIN_FILM", "WIN_SHADE", "PLUG_MGMT"}                  # COST-01: no verified cost
NO_QUOTE = "no verified cost; needs a quote"                      # SPEC 6.5
END_USES = {"heating", "cooling", "water_heating", "lighting", "plug", "appliances"}
DISCOUNT_RATE = 0.03                                              # ECO-05 default
TOP = {"search_results.json": list[C.PropertySummary]}
FOLDERS = ("house", "office", "office_houston")
LEGAL = {st: (ROOT / "specs" / "legal" / f"{name}.md").read_text(encoding="utf-8")
         for st, name in (("CA", "california"), ("TX", "texas"))}

errors, checks = [], 0
FLAG_STATUSES, SKIP_REASONS = set(), set()           # gathered over all goldens


def check(cond, where, msg):
    global checks
    checks += 1
    if not cond:
        errors.append(f"{where}: {msg}")
    return cond


def close(a, b, tol=0.011):
    return abs(a - b) <= tol


def type_name(tp):
    return getattr(tp, "__name__", None) if not getattr(tp, "__args__", None) else \
        f"list[{tp.__args__[0].__name__}]"


def lost(raw, dumped, path=""):
    """Paths present in the JSON file that the contract type dropped or changed."""
    if isinstance(raw, dict) and isinstance(dumped, dict):
        out = []
        for k, v in raw.items():
            out += [f"{path}/{k} (unknown field)"] if k not in dumped else \
                lost(v, dumped[k], f"{path}/{k}")
        return out
    if isinstance(raw, list) and isinstance(dumped, list) and len(raw) == len(dumped):
        return [x for i, (a, b) in enumerate(zip(raw, dumped)) for x in lost(a, b, f"{path}/{i}")]
    if isinstance(raw, bool) or isinstance(dumped, bool) or raw is None or dumped is None:
        return [] if raw is dumped else [f"{path} (value changed: {raw!r} -> {dumped!r})"]
    if isinstance(raw, (int, float)) and isinstance(dumped, (int, float)):
        return [] if math.isclose(raw, dumped) else [f"{path} (value changed)"]
    return [] if raw == dumped else [f"{path} (value changed: {raw!r} -> {dumped!r})"]


def walk(node, path=""):
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}/{i}")


def load(rel, tp):
    """Validate one file against its type; return the raw JSON (or None)."""
    path = EX / rel
    if not check(path.is_file(), rel, "file is missing"):
        return None
    text = path.read_text(encoding="utf-8")
    raw = json.loads(text)
    adapter = TypeAdapter(tp)
    try:
        obj = adapter.validate_json(text)
    except Exception as exc:                                  # pydantic.ValidationError
        check(False, rel, f"does not validate as {type_name(tp)}: {exc}")
        return None
    dropped = lost(raw, adapter.dump_python(obj, mode="json"))
    check(not dropped, rel, f"fields the contract does not carry: {dropped[:5]}")
    n = 0
    for p, node in walk(raw):
        if isinstance(node, dict) and {"low", "expected", "high"} <= node.keys():
            n += 1
            check(node["low"] <= node["expected"] <= node["high"], rel,
                  f"{p}: Ranged is not low <= expected <= high: {node}")
        if isinstance(node, dict) and "schema_version" in node:
            check(node["schema_version"] == C.SCHEMA_VERSION, rel, f"{p}: schema_version")
    print(f"ok    {rel:38s} {type_name(tp):22s} {n:4d} Ranged")
    return raw


def rsum(items, get, key):
    return sum(get(i)[key] for i in items)


def check_finance(w, m, summary):
    """physics 04 ECO, INC and SPEC 6.6 rules on one priced measure."""
    f, s = m["finance"], m["savings"]
    home = summary["segment"] == "residential"
    for i in f["incentives"]:
        iw = f"{w} incentive '{i['name'][:40]}'"
        check(not (home and i["kind"] in ("tax_credit", "tax_deduction")
                   and i["status"] == "verified"), iw, "a home carries no federal tax benefit")
        if "48E" in i["name"]:
            check(not home and i["eligibility"] == "needs_confirmation" and i["conditions"], iw,
                  "48E is for business-owned solar, needs_confirmation, with its conditions")
        check(i["eligibility"] != "needs_confirmation" or i["amount_usd"]["expected"] == 0, iw,
              "an unconfirmed incentive must have expected amount 0")
    rebate = sum(i["amount_usd"]["expected"] for i in f["incentives"]
                 if i["kind"] == "upfront_rebate" and i["status"] == "verified"
                 and i["eligibility"] != "not_eligible")
    for k in ("low", "expected", "high"):
        check(close(f["net_upfront_usd"][k], f["installed_cost_usd"][k] - rebate), w,
              f"net_upfront_usd.{k} != installed cost minus verified upfront rebates only")
    check(f["annual_savings_usd"] == s["cost_usd"], w, "finance savings != savings.cost_usd")
    net, sav, om = f["net_upfront_usd"]["expected"], f["annual_savings_usd"]["expected"], \
        f["annual_om_change_usd"]
    n, d = f["analysis_period_years"], f["discount_rate"]
    check(n == min(f["useful_life_years"], 40), w, "analysis period != min(useful life, 40)")
    check(d == DISCOUNT_RATE, w, "discount rate is not the ECO-05 real default")
    pb = f["simple_payback_years"]
    if pb is not None and sav - om > 0:
        check(close(pb["expected"], net / (sav - om)), w,
              "simple payback != net upfront / (annual savings - O&M change)")
    if f["sir"] is not None and f["sir"] > 0:
        check(f["airr"] is not None
              and close(f["airr"], (1 + d) * f["sir"] ** (1 / n) - 1, 2e-3), w,
              "airr != (1 + d) * SIR^(1/N) - 1")
    kinds = [sc["kind"] for sc in f["financing"]]
    check("cash" in kinds, w, "no cash financing scenario")
    for sc in f["financing"]:
        ncf = sc["net_cashflow_year1_usd"]["expected"]
        if sc["kind"] == "cash":
            check(close(ncf, sav - om), w, "cash first-year net cash flow != savings - O&M")
            continue
        check(not (home and sc["eligible"]), w, "C-PACE cannot be eligible on a home")
        notes = " ".join(sc["notes"])
        if sc["financed_usd"] <= 0:
            pass
        elif summary["state"] == "CA":     # SPEC 6.6, specs/legal/california.md sections 7.3-7.6
            check(not sc["eligible"] and "Hypothetical" in notes, w,
                  "a Los Angeles C-PACE scenario is hypothetical and not eligible until a "
                  "programme is confirmed")
            check("5 percent" in notes and "5898.15" in notes, w,
                  "California C-PACE notes must report the 5 percent tax-plus-assessment test")
            check("statutory precondition" not in notes, w,
                  "California lender consent is programme practice, not a statutory condition")
        else:                              # specs/legal/texas.md section 6
            check("399.010" in notes and "PACE region" in notes, w,
                  "Texas C-PACE notes must state lender consent (399.010) and the PACE region")
        if sc["financed_usd"] > 0:
            i, t = sc["rate"], sc["term_years"]
            pay = sc["financed_usd"] * i * (1 + i) ** t / ((1 + i) ** t - 1)
            check(t <= f["useful_life_years"], w, "C-PACE term > useful life")
            check(close(sc["financed_usd"], net), w, "C-PACE financed amount != net upfront")
            check(close(sc["annual_payment_usd"], pay), w, "C-PACE payment != level payment")
            check(close(ncf, sav - om - pay, 0.02), w, "C-PACE net cash flow != S - O&M - A")
            check(sc["program_sir"] is not None
                  and close(sc["program_sir"], t * (sav - om) / (t * pay + net - sc["financed_usd"]),
                            2e-3), w, "program_sir != savings over the term / total cost")
            check(summary["state"] != "TX" or not sc["eligible"] or sc["program_sir"] >= 1.0,
                  w, "Texas C-PACE marked eligible with a program SIR below 1 (ECO-12b)")
        else:
            check(not sc["eligible"], w, "C-PACE eligible with nothing financed")


def check_plan(w, plan, request, baseline, measures, summary, market):
    measure_ids = {m["measure_id"] for m in measures}
    applicable_ids = {m["measure_id"] for m in measures if m["applicable"]}
    budget = plan["budget_usd"]
    check(budget == request["budget_usd"], w, "plan budget != request budget")
    cum, seen_cost = 0.0, False
    for n, item in enumerate(plan["selected"], 1):
        m = item["measure"]
        net, sav = m["finance"]["net_upfront_usd"], m["finance"]["annual_savings_usd"]
        left = budget - cum
        iw = f"{w} rank {n} {m['measure_id']}"
        check(item["rank"] == n, iw, "ranks are not 1..n in order")
        check(net["expected"] <= left + 0.005, iw, "does not fit the remaining budget")
        check(sav["expected"] > 0, iw, "no positive savings")
        check((net["high"] > left + 0.005) == ("may exceed budget" in m["warnings"]), iw,
              "'may exceed budget' warning does not match net_upfront_usd.high")
        check(not (seen_cost and net["expected"] == 0), iw, "zero-cost measure not first")
        seen_cost = seen_cost or net["expected"] > 0
        cum += net["expected"]
        check(close(item["cumulative_upfront_usd"], cum), iw, "cumulative cost is wrong")
        check(item["cumulative_upfront_usd"] <= budget + 0.005, iw, "cumulative cost > budget")
        check(close(item["remaining_budget_usd"], budget - cum), iw, "remaining budget is wrong")
        check_finance(iw, m, summary)
    sel = [i["measure"] for i in plan["selected"]]
    # Expected totals are sums. Costs are one correlation group, so their low and high are
    # sums too; savings and CO2 combine in quadrature (physics 04 UNC-02), so their low and
    # high lie between the expected total and the plain sum.
    for key, get in (("total_upfront_usd", lambda m: m["finance"]["net_upfront_usd"]),
                     ("total_annual_savings_usd", lambda m: m["finance"]["annual_savings_usd"]),
                     ("total_co2_kg", lambda m: m["savings"]["co2_kg"])):
        t = plan[key]
        check(close(t["expected"], rsum(sel, get, "expected"), 0.02), w,
              f"{key}.expected != sum of items")
        if key == "total_upfront_usd":
            check(close(t["low"], rsum(sel, get, "low"), 0.02)
                  and close(t["high"], rsum(sel, get, "high"), 0.02), w,
                  f"{key} low or high != sum of items")
        else:
            check(rsum(sel, get, "low") - 0.02 <= t["low"] and t["high"] <= rsum(sel, get, "high")
                  + 0.02, w, f"{key} range is wider than the sum of the items' ranges")
    for key in ("electricity_kwh", "gas_kwh", "cost_usd", "co2_kg"):
        want = baseline["annual"][key]["expected"] - rsum(sel, lambda m: m["savings"][key],
                                                          "expected")
        check(close(plan["baseline_after"][key]["expected"], want, 0.02), w,
              f"baseline_after.{key} != baseline minus selected savings")
    for m in plan["financeable"]:
        fw = f"{w} financeable {m['measure_id']}"
        check(m["finance"]["net_upfront_usd"]["expected"] > budget - cum, fw, "would fit budget")
        check(m["finance"]["annual_savings_usd"]["expected"] > 0, fw, "no positive savings")
        check_finance(fw, m, summary)
    ids_sel = [m["measure_id"] for m in sel]
    ids_fin = [m["measure_id"] for m in plan["financeable"]]
    ids_skip = [s["measure_id"] for s in plan["skipped"]]
    for mid in ids_sel + ids_fin + ids_skip:
        check(mid in measure_ids, w, f"{mid} is not in measures.json")
    check(len(set(ids_sel)) == len(ids_sel) and not set(ids_sel) & set(ids_fin + ids_skip), w,
          "a selected measure is also financeable or skipped, or is selected twice")
    check(applicable_ids <= set(ids_sel + ids_fin + ids_skip), w,
          f"applicable measures missing from the plan: {applicable_ids - set(ids_sel + ids_fin + ids_skip)}")
    # SPEC 6.5 and physics 04 COST-01: a measure with no verified cost is never priced
    check(not NO_COST & set(ids_sel + ids_fin), w, "a measure with no verified cost is in the plan")
    if request["role"] == "tenant":        # SPEC 6.2: owner-only measures are skipped for role
        for mid in OWNER_ONLY & applicable_ids:
            check({"measure_id": mid, "reason": "role"}.items()
                  <= next((s for s in plan["skipped"] if s["measure_id"] == mid), {}).items(),
                  w, f"{mid} is owner-only and must be skipped for a tenant with reason role")
    for sk in plan["skipped"]:
        if sk["reason"] == "no_cost_data":
            check(sk["measure_id"] in NO_COST and NO_QUOTE in sk["detail"], w,
                  f"{sk['measure_id']}: no_cost_data needs the detail '{NO_QUOTE}'")
        elif sk["measure_id"] in NO_COST & applicable_ids:
            check(sk["reason"] == "role", w, f"{sk['measure_id']} must be skipped as no_cost_data")
    # physics 04 VAL: a home has no plan-level uplift; an office has one by VAL-01 (phi = 1)
    vu = plan["value_uplift"]
    home = summary["segment"] == "residential"
    check((vu is not None) == (market is not None and not home), w,
          "plan value_uplift must exist for a commercial property with market data only")
    if vu and market:
        s, cap = plan["total_annual_savings_usd"], vu["cap_rate"]
        om = sum(m["finance"]["annual_om_change_usd"] for m in sel)
        check(cap == market["cap_rate"] and vu["comp_count"] == market["comp_count"], w,
              "value_uplift cap rate or comp count != CostarData.market")
        check(vu["comp_count"] >= 10, w, "VAL-01 needs at least 10 comparable sales")
        check(vu["value_usd"]["low"] == 0, w, "VAL-01: low must be 0")
        check(close(vu["value_usd"]["expected"], 0.5 * (s["expected"] - om) / cap["high"], 0.02),
              w, "VAL-01: expected != 0.5 * net saving / highest cap rate")
        check(close(vu["value_usd"]["high"], (s["high"] - om) / cap["low"], 0.02), w,
              "VAL-01: high != net saving (high) / lowest cap rate")
    return set(ids_sel), set(ids_fin), {s["reason"] for s in plan["skipped"]}


def check_property(folder):
    d = {name: load(f"{folder}/{name}", tp) for name, tp in PER_PROPERTY.items()}
    for name, tp in OPTIONAL.items():
        d[name] = load(f"{folder}/{name}", tp) if (EX / folder / name).is_file() else None
    extra = {p.name for p in (EX / folder).glob("*.json")} - set(PER_PROPERTY) - set(OPTIONAL)
    check(not extra, folder, f"JSON files with no contract type assigned: {sorted(extra)}")
    if any(d[name] is None for name in PER_PROPERTY):
        return None
    summary, bundle, model = d["property_summary.json"], d["property_bundle.json"], \
        d["building_model.json"]
    baseline, measures, result = d["baseline_result.json"], d["measures.json"], \
        d["run_result.json"]
    sid, mp, w = summary["sid"], bundle["matterport"], f"{folder}/property_bundle.json"

    # ---- bundle: wall graph, rooms, panoramas, join keys
    check(bundle["summary"] == summary, w, "summary differs from property_summary.json")
    edge_ids, floor_ids = set(), set()
    for fl in mp["floors"]:
        floor_ids.add(fl["id"])
        vert = {v["id"]: (v["x"], v["y"]) for v in fl["vertices"]}
        check(len(vert) == len(fl["vertices"]), w, "duplicate vertex id")
        for e in fl["edges"]:
            check(e["id"] not in edge_ids, w, f"duplicate edge id {e['id']}")
            edge_ids.add(e["id"])
            ok = check(all(v in vert for v in e["vertex_ids"]), w, f"edge {e['id']}: vertex id")
            length = math.dist(*(vert[v] for v in e["vertex_ids"])) if ok else 0.0
            op_ids = [o["id"] for o in e["openings"]]
            check(len(set(op_ids)) == len(op_ids), w, f"edge {e['id']}: duplicate opening id")
            spans = sorted((o["relative_center"] - o["width_m"] / 2 / length,
                            o["relative_center"] + o["width_m"] / 2 / length)
                           for o in e["openings"]) if ok and length else []
            check(all(-1e-9 <= a and b <= 1 + 1e-9 for a, b in spans)
                  and all(spans[k][1] <= spans[k + 1][0] + 1e-9 for k in range(len(spans) - 1)),
                  w, f"edge {e['id']}: openings overlap or run past the edge")
            check(e["type"] in ("wall", "invisible"), w, f"edge {e['id']}: EdgeType")
            check(all(o["type"] in ("divider", "doorway", "opening", "window")
                      for o in e["openings"]), w, f"edge {e['id']}: OpeningType")
    edges = {e["id"]: e for fl in mp["floors"] for e in fl["edges"]}
    xy = {v["id"]: (v["x"], v["y"]) for fl in mp["floors"] for v in fl["vertices"]}
    openings = {o["id"]: (e["id"], o) for e in edges.values() for o in e["openings"]}
    for r in mp["rooms"]:
        check(r["floor_id"] in floor_ids, w, f"room {r['id']}: floor_id")
        if check(all(e in edges for e in r["boundary_edge_ids"]), w, f"room {r['id']}: edge id"):
            degree = {}
            for e in r["boundary_edge_ids"]:
                for v in edges[e]["vertex_ids"]:
                    degree[v] = degree.get(v, 0) + 1
            check(degree and all(n == 2 for n in degree.values()), w,
                  f"room {r['id']}: boundary edges do not form a closed loop")
            # Room.polygon: the same loop, in order, in the model frame
            sides = {frozenset(xy[v] for v in edges[e]["vertex_ids"])
                     for e in r["boundary_edge_ids"]}
            pts = [tuple(pt) for pt in r["polygon"]]
            check(len(pts) == len(sides)
                  and {frozenset((pts[k], pts[(k + 1) % len(pts)])) for k in range(len(pts))}
                  == sides, w, f"room {r['id']}: polygon does not follow its boundary edges")
    room_ids, pano_ids = {r["id"] for r in mp["rooms"]}, {p["id"] for p in mp["panos"]}
    check(len(room_ids) == len(mp["rooms"]) and len(pano_ids) == len(mp["panos"]), w,
          "duplicate room or pano id")
    geo, cs = mp["georeference"], bundle["costar"]
    if geo:
        check(close(geo["latitude"], summary["lat"], 1e-4)
              and close(geo["longitude"], summary["lon"], 1e-4), w,
              "georeference and summary coordinates differ")
        q = geo["rotation"]
        check(close(sum(q[k] ** 2 for k in "xyzw"), 1.0, 1e-5), w, "quaternion is not unit")
    if cs:
        check(cs["matterport_model_id"] == sid, w, "costar.matterport_model_id != sid")
        check((cs["property_id"], cs["listing_id"], cs["residential_listing_id"])
              == (summary["costar_property_id"], summary["costar_listing_id"],
                  summary["costar_residential_listing_id"]), w, "CoStar ids != summary ids")
    for p, node in walk(bundle):
        if isinstance(node, str) and node.startswith("data/"):
            check(node.startswith(f"data/cache/{sid}/"), w, f"{p}: asset path outside the cache")
    tariff, state = bundle["tariff"], summary["state"]
    ef_avg, ef_nb = EF_GRID[state]
    # physics 04 TAR-03 and TAR-06: Texas has no mandated export price and no utility tariff
    if state == "TX":
        check(tariff["export_regime"] == "none" and tariff["export_usd_per_kwh"] is None, w,
              "Texas tariff must have export_regime 'none' and no export price")
        check(any(f["layer"] == "tariff" and f["status"] == "fallback"
                  for f in bundle["provenance"]), w, "no tariff FetchRecord with status fallback")
    if "LADWP" in tariff["utility"]:       # TAR-03: LADWP Service Rider NEM, kWh netted
        check(state == "CA" and tariff["export_regime"] == "net_metering"
              and tariff["export_usd_per_kwh"] is None, w,
              "LADWP is net metering with no separate export price")
    want = GOLDEN_TARIFF.get(folder)
    if want == "LADWP":                    # both Los Angeles goldens: LADWP, net metering, CAMX
        check("LADWP" in tariff["utility"] and tariff["export_regime"] == "net_metering"
              and state == "CA" and EGRID[state] == "CAMX", w,
              "this golden's tariff must be LADWP with net metering, in eGRID CAMX")
    elif want == "TX_DEFAULT":             # Houston golden: TAR-06 commercial default, ERCT
        check(state == "TX" and EGRID[state] == "ERCT" and "CenterPoint" in tariff["utility"]
              and close(tariff["electricity_usd_per_kwh"], TX_COMMERCIAL_PRICE[1], 1e-9)
              and tariff["fixed_usd_per_month"] == 0, w,
              "the Houston golden uses the TAR-06 commercial default (0.090 USD/kWh, no fixed "
              "charge) in the CenterPoint area, eGRID ERCT")
    if folder in CA_EIA_PRICE:             # 5.1c: the price is the EIA state average, a fallback
        check(close(tariff["electricity_usd_per_kwh"], CA_EIA_PRICE[folder], 1e-9)
              and "EIA" in tariff["source"]
              and any(f["layer"] == "tariff" and f["status"] == "fallback"
                      for f in bundle["provenance"]), w,
              "a Los Angeles golden is priced at the EIA California average with a tariff fallback "
              "record (data-integration 5.1c)")
    if folder in EIA_GAS:                  # 5.1e: gas at the EIA state average, labelled as D15 does
        st, sec, mcf, series = EIA_GAS[folder]
        gas_label = (f"EIA state average delivered gas price, {st} {sec}, 2025 ({mcf} $/MCF, EIA {series}, "
                     f"table at 1.037 MMBtu/MCF, +/-0.5% on the heat content)")
        check(state == st and tariff["gas_usd_per_kwh"] == round(mcf / KWH_PER_MCF, 6)
              and gas_label in tariff["source"]
              and {"layer": "tariff", "what": "eia/natural-gas-price", "status": "fallback",
                   "detail": gas_label} in bundle["provenance"], w,
              f"this golden's gas is the EIA {st} {sec} 2025 average, {round(mcf / KWH_PER_MCF, 6)} USD/kWh, "
              "with the D15 label in Tariff.source and an eia/natural-gas-price fallback record "
              "(data-integration 5.1e)")
    # data-integration 4.4a: SAM 3 masks as D8 delivers them
    vex = bundle["vexcel"] or {}
    for i, dt in enumerate(vex.get("detections", [])):
        check(dt.get("mask_wkt") is None and (dt.get("mask_area_m2") or 0) > 0, w,
              f"detection {i}: mask_wkt is left unset and mask_area_m2 is filled (D8)")
    roofs = [dt["mask_area_m2"] for dt in vex.get("detections", [])
             if dt["label"] == "roof" and dt["image_id"].startswith("ortho") and dt.get("mask_area_m2")]
    fp = next((st["footprint_area_m2"] for st in vex.get("structures", []) if st["primary"]), None)
    if roofs and fp:
        check(abs(max(roofs) / fp - 1) <= 0.06, w,
              "the largest single roof mask is not within about 5 percent of the footprint (D8)")
    check(bundle["climate"]["weather_time_convention"] == "hour_end", w,
          "weather_time_convention must be hour_end (Open-Meteo)")
    check(mp["mesh_path"] is None or mp["matterpak_available"], w, "mesh without a MatterPak")
    check(summary["has_splat"] == (mp["splat_path"] is not None), w, "has_splat != splat_path")

    # ---- building model
    w = f"{folder}/building_model.json"
    check(model["sid"] == sid, w, "sid")
    zones = {z["id"]: z for z in model["zones"]}
    for z in model["zones"]:
        check(set(z["room_ids"]) <= room_ids, w, f"zone {z['id']}: unknown room_id")
        area = sum(r["area_m2"] or 0 for r in mp["rooms"] if r["id"] in z["room_ids"])
        check(close(z["floor_area_m2"], area), w, f"zone {z['id']}: area != sum of its rooms")
    surf = {s["id"]: s for s in model["surfaces"]}
    check(len(surf) == len(model["surfaces"]), w, "duplicate surface id")
    psi, vision_windows = model["north_offset_deg"]["expected"], []
    for s in model["surfaces"]:
        check(s["zone_id"] in zones, w, f"surface {s['id']}: unknown zone_id")
        parent = s["parent_surface_id"]
        check(parent is None or (parent in surf and surf[parent]["kind"] == "wall"), w,
              f"surface {s['id']}: parent_surface_id is not a wall surface")
        check((s["shgc"] is not None) == (s["kind"] == "window"), w, f"{s['id']}: shgc")
        sw = f"surface {s['id']}"
        e_id, o_id = s["source_edge_id"], s["source_opening_id"]
        if s["kind"] in ("wall", "window", "door"):
            if check(e_id in edges, w, f"{sw}: source_edge_id is not a wall edge"):
                # the surface faces along the edge's normal, turned by north_offset_deg
                (x0, y0), (x1, y1) = (xy[v] for v in edges[e_id]["vertex_ids"])
                along = math.degrees(math.atan2(x1 - x0, y1 - y0)) + psi
                check(close(abs((s["azimuth_deg"] - along) % 180 - 90), 0, 0.2), w,
                      f"{sw}: azimuth is not perpendicular to its edge")
        if o_id is not None:
            if check(o_id in openings and openings[o_id][0] == e_id, w,
                     f"{sw}: source_opening_id is not an opening of its edge"):
                o = openings[o_id][1]
                check(o["type"] == {"window": "window", "door": "doorway"}.get(s["kind"]), w,
                      f"{sw}: kind does not match the opening type")
                check(close(s["area_m2"], o["width_m"] * o["height_m"]), w,
                      f"{sw}: area != opening width x height")
        elif s["kind"] == "window":
            vision_windows.append(s["id"])
        if s["kind"] == "floor" and s["boundary"] == "ground":
            check(s["exposed_perimeter_m"], w, f"{sw}: ground floor without exposed perimeter")
    measured = [o for _e, o in openings.values() if o["type"] == "window"]
    check(len([s for s in model["surfaces"] if s["kind"] == "window" and s["source_opening_id"]])
          == len(measured), w, "not every measured window opening has a window surface")
    check(not vision_windows or any(a["source"] == "vision" and a["key"].startswith("window.")
                                    for a in model["assumptions"]), w,
          "windows without an opening need a vision assumption on window area")
    sy = model["systems"]
    check(sy["occupancy_schedule"] in ("home", "office", "office_vacant"), w,
          "occupancy_schedule key")
    plane_ids = {p["id"] for p in model["roof_planes"]}
    detections = bundle["vexcel"]["detections"] if bundle["vexcel"] else []
    for pl in model["roof_planes"]:
        check(all(o in detections for o in pl["obstructions"]), w,
              f"roof plane {pl['id']}: obstruction is not one of the bundle's detections")
        check(pl["usable_area_m2"] <= pl["area_m2"], w, f"roof plane {pl['id']}: usable > area")
        if pl["eave_length_m"] and pl["slope_length_m"]:
            check(close(pl["area_m2"], pl["eave_length_m"] * pl["slope_length_m"], 0.5), w,
                  f"roof plane {pl['id']}: area != eave length x slope length")
        if pl["geometry_source"] == "vexcel_parametric":
            check(not pl["ridge_confirmed"], w,
                  f"roof plane {pl['id']}: a parametric ridge is assumed, not confirmed")
    keys = [a["key"] for a in model["assumptions"]]
    check(len(set(keys)) == len(keys), w, "duplicate assumption key")
    sources = {a["source"] for a in model["assumptions"]}
    check(sources == set(C.Source.__args__), w, f"assumption sources present: {sorted(sources)}")
    if geo and model["north_source"] == "georeference":
        q = geo["rotation"]                            # physics 01 ROOF-02
        r01, r11 = 2 * (q["x"] * q["y"] - q["w"] * q["z"]), 1 - 2 * (q["x"] ** 2 + q["z"] ** 2)
        check(close(psi, math.degrees(math.atan2(r01, r11)) % 360, 0.01), w,
              "north_offset_deg != atan2(R[0][1], R[1][1]) of the georeference quaternion")

    # ---- baseline
    w = f"{folder}/baseline_result.json"
    a = baseline["annual"]
    for key, total in (("monthly_electricity_kwh", a["electricity_kwh"]["expected"]),
                       ("monthly_gas_kwh", a["gas_kwh"]["expected"])):
        check(len(baseline[key]) == 12 and close(sum(baseline[key]), total, 0.5), w,
              f"{key}: not 12 values summing to the annual figure")
    check(close(sum(baseline["end_use_kwh"].values()),
                a["electricity_kwh"]["expected"] + a["gas_kwh"]["expected"], 0.5), w,
          "end uses do not sum to electricity + gas")
    check(set(baseline["end_use_kwh"]) <= END_USES, w,
          f"end_use_kwh keys outside the allowed set: {set(baseline['end_use_kwh']) - END_USES}")
    check(close(a["co2_kg"]["expected"], a["electricity_kwh"]["expected"] * ef_avg
                + a["gas_kwh"]["expected"] * EF_GAS, 0.05), w,
          f"baseline co2_kg does not use the {EGRID[state]} factor {ef_avg}")
    if GOLDEN_TARIFF.get(folder) == "TX_DEFAULT":
        pa = next((x["value"] for x in model["assumptions"]
                   if x["key"] == "tariff.electricity_usd_per_kwh"), None)
        check(isinstance(pa, dict) and (pa["low"], pa["expected"], pa["high"])
              == TX_COMMERCIAL_PRICE, w, "price assumption is not the TAR-06 commercial range")
    p_e, p_g = tariff["electricity_usd_per_kwh"], tariff["gas_usd_per_kwh"] or 0.0
    check(close(a["cost_usd"]["expected"], a["electricity_kwh"]["expected"] * p_e
                + a["gas_kwh"]["expected"] * p_g + 12 * tariff["fixed_usd_per_month"], 0.05), w,
          "baseline cost != energy x tariff prices + fixed charges")

    # ---- measures
    w = f"{folder}/measures.json"
    mids = [m["measure_id"] for m in measures]
    check(len(set(mids)) == len(mids), w, "duplicate measure_id")
    check(any(not m["applicable"] for m in measures), w, "no not-applicable measure")
    planes = {p["id"]: p for p in model["roof_planes"]}
    has_windows = bool(measured)
    # SPEC 6.2 and physics 02 HVAC-00: a Vexcel-counted rooftop unit on an office confirms a
    # packaged unit, so HVAC_RTU and HVAC_ECON are evaluated and priced there
    prim = next((st for st in (bundle["vexcel"] or {}).get("structures", []) if st["primary"]),
                None)
    ac_count = (prim or {}).get("attributes", {}).get("roof-objects.ac-unit.count") or 0
    if summary["use_type"] == "office" and ac_count > 0:
        for mid in ("HVAC_RTU", "HVAC_ECON"):
            m = next((x for x in measures if x["measure_id"] == mid), None)
            check(m is not None and m["applicable"] and m["finance"] is not None
                  and sy["hvac_type"] == "rooftop_unit", w,
                  f"{mid} must be evaluated and priced: Vexcel counts {ac_count:g} AC units")
    for m in measures:
        mid = m["measure_id"]
        mw = f"{w} {mid}"
        if m["applicable"]:
            check(m["savings"] is not None, mw, "applicable but no savings")
            check(m["formula_ids"], mw, "no formula_ids")
            if mid in NO_COST:                     # SPEC 6.5, physics 04 COST-01
                check(m["finance"] is None, mw, "a measure with no verified cost has a finance block")
            elif check(m["finance"] is not None, mw, "applicable but no finance"):
                check_finance(mw, m, summary)
            if mid != "PV_ROOF" and m["savings"]:  # solar is valued by its netted or self-used share
                sv = m["savings"]
                check(close(sv["cost_usd"]["expected"], sv["electricity_kwh"]["expected"] * p_e
                            + sv["gas_kwh"]["expected"] * p_g, 0.05), mw,
                      "savings.cost_usd != kWh saved x tariff prices")
        else:
            check(m["not_applicable_reason"], mw, "not applicable but no reason")
        # physics 02 limits on the measure table (SPEC 6.2)
        check(not (mid in ("HVAC_RTU", "HVAC_ECON") and m["applicable"]
                   and sy["hvac_type"] != "rooftop_unit"), mw,
              "evaluated without a confirmed packaged rooftop unit")
        check(not (mid == "HVAC_DUCT" and m["applicable"]), mw, "HVAC_DUCT cannot be evaluated")
        check(not (mid == "HVAC_HP" and m["applicable"])
              or {"seer2", "hspf2", "cop_47f"} <= set(m["params"]), mw,
              "HVAC_HP needs seer2, hspf2 and cop_47f in params")
        if m["solar"]:
            so = m["solar"]
            check(all(p["plane_id"] in plane_ids for p in so["panels"]), mw, "unknown plane_id")
            check(so["panel_count"] == len(so["panels"]), mw, "panel_count != len(panels)")
            check(close(so["annual_kwh"]["expected"], sum(p["annual_kwh"] for p in so["panels"]),
                        0.5), mw, "annual_kwh != sum of panels")
            check(None not in (so["module_w"], so["dc_ac_ratio"], so["inverter_kw_ac"],
                               so["losses_percent"], so["degradation_rate"]), mw,
                  "SolarDesign PV defaults are not filled")
            check(close(so["system_kw_dc"], so["panel_count"] * (so["module_w"] or 0) / 1000), mw,
                  "system_kw_dc != panel_count x module_w")
            for pn in so["panels"]:                # physics 01 section 4: no ray casting there
                if pn["plane_id"] in planes and \
                        planes[pn["plane_id"]]["geometry_source"] != "splat":
                    check(pn["shading_loss_fraction"] == 0.03, mw,
                          "shading on a parametric roof must be the 3 percent default")
            vu = m["value_uplift"]                 # physics 04 VAL-03
            if summary["segment"] == "residential" and m["finance"]:
                high = 4.00 * so["system_kw_dc"] * 1000
                check(vu is not None and vu["value_usd"]["low"] == 0
                      and close(vu["value_usd"]["high"], high)
                      and close(vu["value_usd"]["expected"],
                                min(high, m["finance"]["net_upfront_usd"]["expected"])), mw,
                      "home solar value uplift does not follow VAL-03")
        check(m["value_uplift"] is None
              or (mid == "PV_ROOF" and summary["segment"] == "residential"), mw,
              "value_uplift on a measure is for home rooftop solar only")
        if m["layout"]:
            la = m["layout"]
            check(all(c["room_id"] in room_ids for c in la["candidates"]), mw, "desk room_id")
            check(sum(c["recommended"] for c in la["candidates"]) == la["desks_requested"], mw,
                  "recommended desks != desks_requested")
            wts = la["score_weights"]
            for c in la["candidates"]:             # physics 03 section 8 and LCT-03
                check(0 <= c["daylight"] <= 1 and 0 <= c["glare_risk"] <= 1
                      and 5 <= c["comfort_ppd"] <= 100 and 0 <= c["score"] <= 1, mw,
                      "desk metric outside its range")
                want = (wts["daylight"] * c["daylight"]
                        + wts["glare"] * (1 - min(1, c["glare_risk"] / 0.20))
                        + wts["comfort"] * (1 - min(1, max(0, c["comfort_ppd"] - 5) / 20)))
                check(close(c["score"], want, 0.002), mw, "desk score != LCT-03")
                check(not (c["recommended"] and (c["max_dt_pr_k"] or 0) >= 10), mw,
                      "a desk with radiant asymmetry of 10 K or more is recommended")
            check(la["window_source"] == ("measured" if has_windows else "vision"), mw,
                  "window_source does not match the bundle's openings")
            check(la["lighting_kwh_saved"] == m["savings"]["electricity_kwh"], mw,
                  "lighting_kwh_saved != savings.electricity_kwh")
            if la["control_type"] == "none":       # SPEC 6.4 step 4
                check(la["lighting_kwh_saved"]["low"] == 0, mw,
                      "without daylight control the saving must be a range starting at zero")
        check((mid != "PV_ROOF" or not m["applicable"]) or m["solar"], mw, "no solar")
        check((mid != "LAYOUT" or not m["applicable"]) or m["layout"], mw, "no layout")

    # ---- emissions: every co2_kg follows its kWh (physics 04 EMI-01, EMI-02)
    for name, raw in d.items():
        for p, node in walk(raw):
            if isinstance(node, dict) and {"electricity_kwh", "gas_kwh", "co2_kg"} <= node.keys():
                e_kwh, g_kwh = node["electricity_kwh"]["expected"], node["gas_kwh"]["expected"]
                check(close(node["co2_kg"]["expected"], e_kwh * ef_avg + g_kwh * EF_GAS, 0.05),
                      f"{folder}/{name}{p}", "co2_kg != kWh x eGRID and gas factors")
                nb = node.get("co2_nonbaseload_kg")
                check(nb is None or close(nb["expected"], e_kwh * ef_nb + g_kwh * EF_GAS, 0.05),
                      f"{folder}/{name}{p}", "co2_nonbaseload_kg != kWh x non-baseload factor")

    # ---- references that can sit anywhere: anchors, evidence, flags
    statuses = set()
    for name, raw in d.items():
        for p, node in walk(raw):
            if not isinstance(node, dict):
                continue
            fw = f"{folder}/{name}{p}"
            if node.get("kind") == "pano" and "ref" in node:
                check(node["ref"] in pano_ids, fw, f"evidence pano {node['ref']} does not exist")
            if "label" in node and "pano_id" in node and "room_id" in node:        # Anchor
                check(node["pano_id"] in pano_ids | {None}, fw, "anchor pano_id")
                check(node["room_id"] in room_ids | {None}, fw, "anchor room_id")
            if "status" in node and "message" in node and "key" in node:           # Flag
                statuses.add(node["status"])
    FLAG_STATUSES.update(statuses)

    # ---- plans
    market = cs["market"] if cs else None
    sel, fin, reasons = check_plan(f"{folder}/plan.json", d["plan.json"], d["run_request.json"],
                                   baseline, measures, summary, market)
    if d["plan_tenant.json"] and d["run_request_tenant.json"]:
        check(d["run_request_tenant.json"]["role"] == "tenant", folder, "tenant request role")
        reasons |= check_plan(f"{folder}/plan_tenant.json", d["plan_tenant.json"],
                              d["run_request_tenant.json"], baseline, measures, summary,
                              market)[2]
    SKIP_REASONS.update(reasons)

    # ---- run result and events
    w = f"{folder}/run_result.json"
    for key, name in (("request", "run_request.json"), ("property", "property_summary.json"),
                      ("building_model", "building_model.json"),
                      ("baseline", "baseline_result.json"), ("measures", "measures.json"),
                      ("plan", "plan.json")):
        check(result[key] == d[name], w, f"{key} differs from {name}")
    check(d["run_request.json"]["sid"] == sid, w, "request sid")
    for q in result["questions"]:
        check(q["assumption_key"] in keys, w, f"question {q['id']}: unknown assumption_key")
        check(any(c["value"] is None for c in q["choices"]), w, "no \"I don't know\" choice")
    w = f"{folder}/run_events.json"
    events = d["run_events.json"]
    all_types = set(C.RunEvent.model_fields["type"].annotation.__args__)
    check({e["type"] for e in events} == all_types, w,
          f"event types not shown: {all_types - {e['type'] for e in events}}")
    check(events[-1]["type"] == "done", w, "last event is not 'done'")
    stages = {f"S{i}" for i in range(1, 10)} | {None}
    check(all(e["stage"] in stages for e in events), w, "stage is not S1..S9 or null")
    for e in events:
        if e["type"] == "question":
            try:
                C.Question.model_validate(e["payload"]["question"])
                check(e["payload"]["question"] in result["questions"], w,
                      "question event differs from RunResult.questions")
            except Exception as exc:
                check(False, w, f"question payload is not a Question: {exc}")

    # ---- documents
    w = f"{folder}/document_draft.json"
    req, draft = d["document_request.json"], d["document_draft.json"]
    check(req["run_id"] == result["run_id"], w, "document_request.run_id != run_result.run_id")
    check(set(req["measure_ids"]) <= sel | fin, w, "document covers a measure outside the plan")
    check((draft["doc_type"], draft["state"]) == (req["doc_type"], req["state"]), w,
          "doc_type or state differs from the request")
    check(req["state"] == summary["state"], w, "document state != property state")
    blanks = set(re.findall(r"\{\{([a-z_]+)\}\}", draft["markdown"]))
    check(blanks == set(draft["unfilled_placeholders"]), w,
          "unfilled_placeholders != {{placeholders}} left in the markdown")
    check(draft["statutory_checks"] and draft["disclaimer"], w, "no checks or no disclaimer")
    for sc in draft["statutory_checks"]:   # ids must exist in the state's legal spec
        rid = sc["requirement_id"]
        check(rid is None or (rid.startswith(req["state"] + "-")
                              and re.search(rf"\b{re.escape(rid)}\b", LEGAL[req["state"]])),
              w, f"requirement_id {rid} is not in specs/legal for {req['state']}")
    check(draft["doc_type"] != "retrofit_contract_residential"
          or summary["segment"] == "residential", w, "residential contract on a commercial property")
    check(draft["doc_type"] not in ("cpace_package", "retrofit_contract_commercial")
          or summary["segment"] == "commercial", w, "commercial document on a home")
    return summary


goldens = [check_property(f) for f in FOLDERS]
all_statuses = set(C.Flag.model_fields["status"].annotation.__args__)
check(FLAG_STATUSES == all_statuses, "goldens",
      f"Flag statuses not shown: {all_statuses - FLAG_STATUSES}")
all_reasons = set(C.SkippedItem.model_fields["reason"].annotation.__args__)
check(SKIP_REASONS == all_reasons, "goldens", f"skip reasons not shown: {all_reasons - SKIP_REASONS}")
search = load("search_results.json", TOP["search_results.json"])
if search is not None:
    w = "search_results.json"
    sids = [s["sid"] for s in search]
    check(len(set(sids)) == len(sids), w, "duplicate sid")
    for g in goldens:
        check(g is None or g in search, w, "a golden property_summary.json is not in the list")
    for field, want in (("segment", {"residential", "commercial"}), ("state", {"CA", "TX"}),
                        ("city", {"Los Angeles", "Houston"})):
        check({s[field] for s in search} == want, w, f"{field} values are not {sorted(want)}")
    check({"office", "single_family"} <= {s["use_type"] for s in search}, w, "use types")
extra = {p.name for p in EX.glob("*.json")} - set(TOP)
check(not extra, "specs/examples", f"JSON files with no contract type assigned: {sorted(extra)}")

print(f"\ncontract {C.SCHEMA_VERSION} from {ROOT / 'specs' / 'SPEC.md'}")
print(f"examples {EX}")
if errors:
    print(f"\nFAILED: {len(errors)} of {checks} checks")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print(f"\nPASSED: {checks} checks, 0 failures")
````

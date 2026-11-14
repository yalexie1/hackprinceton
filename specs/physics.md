# Physics spec: index

Status: draft, 2026-11-14. Owner: @yalexie1 (Analysis lane). This file is the entry point to the physics library. The formulas are in the four files under `specs/physics/`; this file says what is where, which conventions all four share, how they hand values to each other, and what is not yet sourced.

## 1. How to use it

- Every formula is an **entry** with an id such as `IRR-07`. An entry gives the equation, symbols and units, validity range, the source it was read from, a second independent check, and a worked numeric example.
- Every tool result lists the ids it used in `MeasureResult.formula_ids`.
- Every physics function gets a unit test that reproduces its entry's worked example (SPEC 14, Analysis). Each file has a build-time test plan that names the tests.
- Each file ends with a list headed "Unverified". **Nothing on those lists is to be implemented as fact.** A value from them is carried as an assumption with a range, or the measure that needs it returns not applicable.

## 2. The four files

| File | Modules (id prefix, range) | Test plan | Unverified list | Verification log |
|---|---|---|---|---|
| `specs/physics/01-solar-pv.md` | `SOL-01` to `-07` solar position; `IRR-01` to `-10` irradiance; `PV-01` to `-09` PV production; `SHD-01` to `-05` shading; `ROOF-01` to `-06` roof geometry inputs; `LAY-01` to `-03` panel layout | section 7 | section 8 | section 9 |
| `specs/physics/02-thermal-systems.md` | `ENV-01` to `-06` envelope; `ZON-00` to `-06` hourly zone model; `INF-01` to `-07` infiltration and ventilation; `WIN-01`, `-02` window solar gain; `HVAC-00` to `-08`; `DHW-01` to `-03` hot water; `LGT-01` to `-03` lighting and plug loads; `DEF-01` to `-11` default tables | section 9 | section 10 | section 11 |
| `specs/physics/03-daylight-comfort.md` | `DAY-01` to `-10` daylight; `GLR-01` to `-05` glare; `CMF-01` to `-08` thermal comfort; `LCT-01` to `-03` lighting credit and desk score | section 5 | section 6 | section 7 |
| `specs/physics/04-economics-emissions-mv.md` | `ECO-01` to `-13` and `ECO-12b` life-cycle economics; `TAR-01` to `-06` energy cost; `EMI-01` to `-03` emissions; `INC-01` to `-07`, `-10` to `-23`, `-30` to `-34`, `-40` incentives; `COST-00` to `-02` cost and useful life; `MV-01` to `-05` measurement and verification; `UNC-01` to `-03` uncertainty; `VAL-01` to `-03` value uplift | none; each entry's worked example is the test | section 9 | section 10 |

Which measure uses which modules is in SPEC 6.2.

## 3. Conventions shared by all four files

These are fixed. A file that disagrees with this table is wrong.

| Topic | Convention | Where it is defined |
|---|---|---|
| Units | SI inside the backend: m, m², W, kWh, K or °C, kg. Money in USD | SPEC 7 |
| Azimuth | degrees clockwise from true north, 0 = north, 90 = east | SPEC 9, `Surface.azimuth_deg` |
| Tilt | 0 = horizontal facing up, 90 = vertical | SPEC 9, `Surface.tilt_deg` |
| Model frame to true north | `north_offset_deg` is the azimuth of the model frame's +y axis, clockwise from true north. `azimuth_true = azimuth_in_model + north_offset_deg`, with `azimuth_in_model` measured clockwise from model +y | SPEC 9; `ROOF-02`; physics 03 section 0.2 |
| Hourly weather stamps | a value stamped at an hour is the mean over the hour **ending** at that stamp (`hour_end`). Verified on Open-Meteo by the Data lane on 2026-11-14. Sun position for an hourly value is taken at the middle of that hour. This closes the open risk named in physics 01 | `ClimateSite.weather_time_convention`; data spec 5 |
| Weather year | one real calendar year (2024, Open-Meteo), not a typical meteorological year (TMY). A leap-year file has 8,784 hours; the reader drops 29 February and returns 8,760 with a warning. A single real year carries that year's anomalies, so the PV-09 year-to-year range (from PVGIS) is what covers weather variability | data spec 5.1a; A1 reader; `specs/examples/weather/` |
| Irradiance inputs | the weather source supplies GHI, DNI and DHI separately, so transposition (`IRR`, Perez) is the required path and decomposition from GHI alone is the fallback | physics 01 section 2 |
| Gas | carried as kWh of higher heating value. 1 therm = 29.3071 kWh | `TAR-05` |
| Emissions | kg CO2-equivalent, first year, eGRID total-output rate for electricity and the EPA combustion factor for gas. The non-baseload figure is an optional "up to" number | `EMI-01`, `EMI-02` |
| Money over time | discount and escalation rates are real, not nominal. Costs are at the base date | `ECO-01`, `ECO-05`, `COST-00` |
| Ranges | every result is low, expected, high. Expected is the run at expected inputs; low and high are approximate 10th and 90th percentiles, built from one-at-a-time runs combined in quadrature | `UNC-01`, `UNC-02` |
| Openings | a window is a `WallEdge.openings` entry of type `window`. `relative_center` is a fraction of the edge length from 0 to 1. Measured openings are the primary source; windows read by vision are the fallback, with a wider range | SPEC 3.3, 5.1 |

## 4. What each file hands to the others

| From | To | What | Entry |
|---|---|---|---|
| 01 | 02 | sun position and irradiance on a tilted plane, for window and roof solar gain | `SOL-01`, `SOL-05`, `SOL-07`, `IRR-04`, `IRR-10`; used by `WIN-01`, `ENV-05` |
| 01 | 03 | hourly sun position, DNI, DHI, GHI and extraterrestrial irradiance, for indoor illuminance and glare | `SOL`, `IRR`; used by `DAY-07`, `DAY-08`, `GLR-04` |
| 02 | 03 | hourly zone air temperature, heating or cooling mode, and the inside surface coefficient, for comfort near glazing | `ZON-04` outputs, cached at `BaselineResult.hourly_path`; `ENV-06`; used by `CMF-03` to `CMF-07` |
| 02 | 01 | annual consumption, one of the three stops on the PV layout | `BaselineResult`; used by `LAY-03` |
| 03 | 02 | lighting energy displaced by daylight, which also changes heating and cooling | `LCT-02`; interaction in `LGT-03` |
| 01, 02, 03 | 04 | annual kWh by fuel, turned into dollars, CO2 and the financial figures | `TAR`, `EMI`, `ECO` |
| 04 | all | how a range is built, and the sensitivity ranking the ask rule uses (SPEC 5.3) | `UNC-01` to `UNC-03` |

The inside surface coefficient is 7.69 W/m²K (ISO 6946 surface resistance 0.13 m²K/W), with a range to 8.35 (`ENV-06`). Physics 03's worked example used 8.0 before `ENV-06` existed; 8.0 lies inside the range, and the implementation takes the value from `ENV-06`.

## 5. Reference implementations for the unit tests

| File | Reference | What it reproduces |
|---|---|---|
| 01 | pvlib 0.16.x, run locally | solar position against NREL SPA, transposition, the full 8,760-hour chain against `ModelChain` |
| 01 | PVGIS (ERA5 database for US sites) | an annual sanity band only, and the year-to-year weather variability. Not an hourly source |
| 02 | the published test cases of the open ISO 13790 hourly implementation used as a check | four hourly zone cases, reproduced to the published digits |
| 03 | the ISO 7730 PMV table rows and `pythermalcomfort`; the ASHRAE 55 SolarCal table rows | PMV and PPD; solar gain on the occupant |
| 04 | the printed worked values in NIST Handbook 135 | discount factors, SIR, AIRR, payback |

No NREL web service is a dependency: `developer.nrel.gov` and `nsrdb.nrel.gov` do not resolve from the team's environment.

The scripts that recomputed the worked examples while the spec was written are not in the repo. The analysis lane's unit tests are written from the test plans and the worked examples, and are the lasting check.

## 6. How far it is verified

Each entry was written from a source that was opened, then checked a second time: the equation re-read term by term, units checked, and the worked example recomputed by a script and compared with a second, independent calculation or a published value. Where the primary paper or standard is paywalled, the entry was read in open reproductions that agree with each other, and says so.

What that does not cover:

- **Paywalled standards were not opened.** ISO 13790, 6946, 13370, 7730, 52016-1, EN 17037, ASHRAE 55, 62.1, 90.1 and 140, ASHRAE Guideline 14 and IPMVP. The entries rest on named open reproductions.
- **Worked examples test the arithmetic, not the building.** The solar examples use a synthetic clear-sky year. None of the examples is a prediction for a real property.
- **Some choices are this project's own**, with one source or none, and are labelled in their entries: how the circumsolar part of diffuse light is shaded (`SHD-03`), the geometric shortcut for glare (`GLR-01`, `GLR-04`, `GLR-05`), the glass temperature derivation (`CMF-04`), the desk score (`LCT-03`), and the Houston commercial high price (`TAR-06`).

## 7. Not sourced, and what follows for each measure

| Gap | Effect |
|---|---|
| No verified installed cost for `WIN_FILM`, `WIN_SHADE`, `PLUG_MGMT` (`COST-01`) | skipped with reason `no_cost_data` unless the user enters a quote |
| Distribution efficiency of leaky ducts (physics 02 section 10) | `HVAC_DUCT` returns not applicable; the baseline uses an upper-bound figure |
| How much a vented attic attenuates roof solar gain | `ROOF_COOL` on such a home is an upper bound with a warning; low-slope roofs are fully supported |
| No packaged rooftop unit confirmed on a building | `HVAC_RTU` and `HVAC_ECON` return not applicable (`HVAC-00`) |
| One parameter each for `LGT_LED` in offices, `LGT_CTRL`, `PLUG_MGMT`, `ENV_AIRSEAL`, `CTRL_TSTAT` | carried as an assumption with a wide range; the result is marked as resting on it |
| Lighting saved by moving a desk where there is no daylight control (`LCT-02`) | shown as a range starting at zero; the midpoint has no source |
| Roof pitch by roof shape rests on one lidar study; gable and hip share a range (`ROOF-03`) | tilt is a range, and with the unconfirmed ridge direction it is the main spread in the solar yield |
| Most useful lives (`COST-02`) | flagged placeholders; five are sourced |
| Rent uplift (`VAL-02`) | a stub; value uplift has no rent component |
| Installed cost of an electrical service upgrade, the `added_cost_usd` on an `electrical.service` flag of `likely_upgrade` | an estimate carried as a range, 2,250 / 3,000 / 4,500 USD (the COST-00 range rule around 3,000), with the flag's message saying it is not sourced. When the signal is only grounded outlets, 0 / 1,500 / 4,500 |
| Hours of a home thermostat setback (`DEF-08`) | nights 22:00 to 06:00 and weekdays 08:00 to 18:00, this project's judgment; only used when a home has a setback, so baselines are unaffected |
| Fire-code roof setbacks: the residential code section for the house and Houston's local adoption | setback values flagged unverified (physics 01 section 8) |

## 8. Open items that cross files

| Item | Who | Affects |
|---|---|---|
| Which way the Matterport georeference quaternion rotates. Evidence so far (A9, 2026-11-14): on all three golden properties the footprint's edge directions support the `ROOF-02` reading; the other reading misses by 7.2° (house), 6.9° (LA office) and 30° (Houston office). This holds only if the example footprint polygons are real, and the check works modulo 90°, so a confirmation on live Vexcel footprints is still wanted | Data lane | the sign of `north_offset_deg`, so every azimuth in 01, 02 and 03 |
| Which vertex `Opening.relative_center` is measured from | Data lane | point daylight, glare and comfort in 03: the other reading mirrors each off-centre window along its wall |
| Office scans have no window openings (decided: windows from vision, then the `DEF-03` window-to-wall default); no rooftop unit is counted on the golden offices' roofs | Analysis lane | desk placement in 03; `HVAC_RTU` and `HVAC_ECON` in 02 |
| Ridge direction on a parametric roof is assumed until an oblique image confirms it | Analysis lane | about a fifth of annual solar energy on the golden house (`PV-09`) |
| The Texas PACE program SIR formula rests on the legal spec's reading of the program guide; how escalation and fees enter was not confirmed (`ECO-12b`) | Analysis lane, with the legal spec | the C-PACE eligibility flag |
| Contract gaps found while building A1, A9 and A11, not yet proposed as a `CONTRACT-CHANGE`: `ClimateSite` has no elevation (SOL-01 pressure; the code defaults to 0 m, a negligible effect); `Source` has no value for an assumed north offset (A9 uses `published_default` with confidence 0); `RoofPlane` has no existing-solar field (A11 returns it beside the planes) | Analysis lane | none at present; each is handled in code |

## 9. Formula index for the "How it works" page

Every formula entry in the four files, with a link to it. It is for the app's "How it works" page and source drawer: a figure's `MeasureResult.formula_ids` (or a warning that names an id) resolves here to the entry that holds the equation, its symbols and units, its source and a worked example. **Render or link the entry; do not paraphrase its numbers.** "Shown in the app" marks the 53 ids that appear in `formula_ids` of the three examples on 2026-11-14.

Where the sources are listed: `01-solar-pv.md` section 0.5, `03-daylight-comfort.md` section 0.7 and `02-thermal-systems.md` section 13.1 (the survey benchmarks; the other entries of 02 name their sources in the entry, as `Primary:` and `Second source:`). `04-economics-emissions-mv.md` gives the source inside each entry. The data lane's sources (sponsor APIs, EIA, weather, PVGIS, survey tables) are in `specs/data-integration.md` section 9.

Verification tags are defined in `01-solar-pv.md` section 0.3: **V** read in the primary source (or a named open reproduction) with the worked example computed twice; **V-repro** read in two independent reproductions that agree, the primary not opened; **P** pending; **U** unverified. **J** marks a judgment of the file, with its reason (`02-thermal-systems.md` section 13). "see entry" means the heading carries no tag, and the entry states its status in its text.

Generated from the `###` headings of the four files on 2026-11-14; links follow GitHub's heading anchors.

| Id | What it computes | Verification | Where | Shown in the app |
|---|---|---|---|---|
| `SOL-01` | Solar position, NREL SPA | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#sol-01-solar-position-nrel-spa-v) |  |
| `SOL-02` | Equation of time, Spencer series | V-repro | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#sol-02-equation-of-time-spencer-series-v-repro) |  |
| `SOL-03` | Declination, Spencer series | V-repro | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#sol-03-declination-spencer-series-v-repro) |  |
| `SOL-04` | True solar time and hour angle | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#sol-04-true-solar-time-and-hour-angle-v) |  |
| `SOL-05` | Zenith and azimuth from latitude, declination and hour angle | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#sol-05-zenith-and-azimuth-from-latitude-declination-and-hour-angle-v) |  |
| `SOL-06` | Sun unit vector | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#sol-06-sun-unit-vector-v) |  |
| `SOL-07` | Which instant an hourly weather value stands for | V rule, P data | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#sol-07-which-instant-an-hourly-weather-value-stands-for-v-rule-p-data) |  |
| `IRR-01` | Extraterrestrial normal irradiance | V-repro | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#irr-01-extraterrestrial-normal-irradiance-v-repro) |  |
| `IRR-02` | Clearness index and Erbs decomposition of GHI | V-repro | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#irr-02-clearness-index-and-erbs-decomposition-of-ghi-v-repro) |  |
| `IRR-03` | Relative air mass, Kasten | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#irr-03-relative-air-mass-kasten-v) |  |
| `IRR-04` | Angle of incidence on a tilted plane | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#irr-04-angle-of-incidence-on-a-tilted-plane-v) |  |
| `IRR-05` | Beam irradiance on the plane | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#irr-05-beam-irradiance-on-the-plane-v) |  |
| `IRR-06` | Isotropic sky diffuse | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#irr-06-isotropic-sky-diffuse-v) |  |
| `IRR-07` | Hay and Davies sky diffuse | V-repro | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#irr-07-hay-and-davies-sky-diffuse-v-repro) |  |
| `IRR-08` | Perez 1990 sky diffuse, production model | V-repro | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#irr-08-perez-1990-sky-diffuse-production-model-v-repro) |  |
| `IRR-09` | Ground-reflected irradiance | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#irr-09-ground-reflected-irradiance-v) |  |
| `IRR-10` | Plane-of-array total | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#irr-10-plane-of-array-total-v) |  |
| `PV-01` | Incidence angle modifier and transmitted irradiance | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#pv-01-incidence-angle-modifier-and-transmitted-irradiance-v) | yes |
| `PV-02` | Cell temperature, Sandia model | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#pv-02-cell-temperature-sandia-model-v) | yes |
| `PV-03` | Array DC power | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#pv-03-array-dc-power-v) | yes |
| `PV-04` | System losses | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#pv-04-system-losses-v) | yes |
| `PV-05` | Inverter and DC/AC ratio | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#pv-05-inverter-and-dcac-ratio-v) | yes |
| `PV-06` | Annual energy | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#pv-06-annual-energy-v) | yes |
| `PV-07` | Degradation over the analysis period | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#pv-07-degradation-over-the-analysis-period-v) |  |
| `PV-08` | Array rating from the module count | V arithmetic, U defaults | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#pv-08-array-rating-from-the-module-count-v-arithmetic-u-defaults) |  |
| `PV-09` | Range of the annual energy | V method | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#pv-09-range-of-the-annual-energy-v-method) | yes |
| `PV-10` | Cross-check of the yield against PVGIS | V method, J tolerance | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#pv-10-cross-check-of-the-yield-against-pvgis-v-method-j-tolerance) |  |
| `SHD-01` | Beam shading by ray casting | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#shd-01-beam-shading-by-ray-casting-v) |  |
| `SHD-02` | Sky view factor and diffuse shading factor | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#shd-02-sky-view-factor-and-diffuse-shading-factor-v) |  |
| `SHD-03` | Shaded plane-of-array irradiance for one hour | V arithmetic, design rule | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#shd-03-shaded-plane-of-array-irradiance-for-one-hour-v-arithmetic-design-rule) |  |
| `SHD-04` | Trees and neighbours as shading geometry | U inputs | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#shd-04-trees-and-neighbours-as-shading-geometry-u-inputs) |  |
| `SHD-05` | Annual shading loss of a panel | V definition | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#shd-05-annual-shading-loss-of-a-panel-v-definition) |  |
| `ROOF-01` | Tilt and azimuth from a plane normal | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#roof-01-tilt-and-azimuth-from-a-plane-normal-v) |  |
| `ROOF-02` | Model frame to true north | V mathematics, P convention | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#roof-02-model-frame-to-true-north-v-mathematics-p-convention) |  |
| `ROOF-03` | Roof pitch range by roof shape class | V for the sourced values, U where marked | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#roof-03-roof-pitch-range-by-roof-shape-class-v-for-the-sourced-values-u-where-marked) |  |
| `ROOF-04` | Usable roof area | V geometry, U allowances | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#roof-04-usable-roof-area-v-geometry-u-allowances) | yes |
| `ROOF-05` | Parametric roof planes and ridge direction | V geometry, U ridge assumption | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#roof-05-parametric-roof-planes-and-ridge-direction-v-geometry-u-ridge-assumption) |  |
| `ROOF-06` | Fire-code access pathways and setbacks | V for the model-code text, U or P where marked | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#roof-06-fire-code-access-pathways-and-setbacks-v-for-the-model-code-text-u-or-p-where-marked) |  |
| `LAY-01` | Packing rectangular modules into the usable area | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#lay-01-packing-rectangular-modules-into-the-usable-area-v) |  |
| `LAY-02` | Row spacing on flat roofs | V | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#lay-02-row-spacing-on-flat-roofs-v) |  |
| `LAY-03` | Which planes to fill, in what order, and when to stop | V rule | [`physics/01-solar-pv.md`](physics/01-solar-pv.md#lay-03-which-planes-to-fill-in-what-order-and-when-to-stop-v-rule) | yes |
| `ENV-01` | Assembly U-value from layers | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#env-01-assembly-u-value-from-layers) | yes |
| `ENV-02` | Framing correction (parallel path) | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#env-02-framing-correction-parallel-path) |  |
| `ENV-03` | Transmission heat transfer coefficient (UA summation) | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#env-03-transmission-heat-transfer-coefficient-ua-summation) | yes |
| `ENV-04` | Slab-on-grade floor | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#env-04-slab-on-grade-floor) |  |
| `ENV-05` | Sol-air temperature and roof solar absorptance | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#env-05-sol-air-temperature-and-roof-solar-absorptance) | yes |
| `ENV-06` | Surface heat transfer coefficients `h_i` and `h_e` | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#env-06-surface-heat-transfer-coefficients-h_i-and-h_e) |  |
| `ZON-00` | Choice of method | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#zon-00-choice-of-method) |  |
| `ZON-01` | Model parameters | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#zon-01-model-parameters) | yes |
| `ZON-02` | Distribution of gains to the nodes | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#zon-02-distribution-of-gains-to-the-nodes) |  |
| `ZON-03` | Node temperatures for a given heating or cooling power | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#zon-03-node-temperatures-for-a-given-heating-or-cooling-power) |  |
| `ZON-04` | Hourly heating and cooling need with setpoints and capacity | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#zon-04-hourly-heating-and-cooling-need-with-setpoints-and-capacity) | yes |
| `ZON-05` | Steady-state identity (unit test, not a tool) | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#zon-05-steady-state-identity-unit-test-not-a-tool) |  |
| `ZON-06` | Monthly quasi-steady cross-check (the degree-day sanity test) | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#zon-06-monthly-quasi-steady-cross-check-the-degree-day-sanity-test) |  |
| `INF-01` | Air flow to heat transfer coefficient | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#inf-01-air-flow-to-heat-transfer-coefficient) | yes |
| `INF-02` | Blower-door leakage to effective leakage area | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#inf-02-blower-door-leakage-to-effective-leakage-area) | yes |
| `INF-03` | Hourly infiltration (Sherman-Grimsrud, the ASHRAE "basic" model) | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#inf-03-hourly-infiltration-sherman-grimsrud-the-ashrae-basic-model) | yes |
| `INF-04` | Combining infiltration with mechanical ventilation | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#inf-04-combining-infiltration-with-mechanical-ventilation) |  |
| `INF-05` | Office outdoor air and infiltration | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#inf-05-office-outdoor-air-and-infiltration) | yes |
| `INF-06` | Economizer | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#inf-06-economizer) | yes |
| `INF-07` | Latent load of outdoor air | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#inf-07-latent-load-of-outdoor-air) | yes |
| `WIN-01` | Solar gain through a window | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#win-01-solar-gain-through-a-window) | yes |
| `WIN-02` | Shading, films and screens | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#win-02-shading-films-and-screens) | yes |
| `HVAC-00` | System type, and what is assumed when it is unknown | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#hvac-00-system-type-and-what-is-assumed-when-it-is-unknown) |  |
| `HVAC-01` | Rating conversions | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#hvac-01-rating-conversions) | yes |
| `HVAC-02` | Outdoor-temperature dependence and the 35 °C rating point (single-stage cooling) | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#hvac-02-outdoor-temperature-dependence-and-the-35-c-rating-point-single-stage-cooling) |  |
| `HVAC-03` | Hourly cooling electricity (single-stage equipment) | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#hvac-03-hourly-cooling-electricity-single-stage-equipment) |  |
| `HVAC-04` | Seasonal method (two-stage and variable-speed equipment, and the cross-check for HVAC-03) | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#hvac-04-seasonal-method-two-stage-and-variable-speed-equipment-and-the-cross-check-for-hvac-03) | yes |
| `HVAC-05` | Heat pump heating | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#hvac-05-heat-pump-heating) | yes |
| `HVAC-06` | Furnace, boiler and electric resistance | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#hvac-06-furnace-boiler-and-electric-resistance) |  |
| `HVAC-07` | Rooftop units rated by IEER | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#hvac-07-rooftop-units-rated-by-ieer) | yes |
| `HVAC-08` | Duct losses | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#hvac-08-duct-losses) |  |
| `DHW-01` | Cold water (mains) temperature | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#dhw-01-cold-water-mains-temperature) |  |
| `DHW-02` | Daily hot water volume (homes) | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#dhw-02-daily-hot-water-volume-homes) |  |
| `DHW-03` | Energy delivered and energy used | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#dhw-03-energy-delivered-and-energy-used) |  |
| `LGT-01` | Lighting energy | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#lgt-01-lighting-energy) | yes |
| `LGT-02` | Plug and miscellaneous loads | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#lgt-02-plug-and-miscellaneous-loads) | yes |
| `LGT-03` | Internal gains to the zone model, and the interaction with heating and cooling | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#lgt-03-internal-gains-to-the-zone-model-and-the-interaction-with-heating-and-cooling) | yes |
| `DEF-01` | Home opaque envelope by vintage | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-01-home-opaque-envelope-by-vintage) | yes |
| `DEF-02` | Solar absorptance and emittance | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-02-solar-absorptance-and-emittance) |  |
| `DEF-03` | Windows | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-03-windows) | yes |
| `DEF-04` | Air leakage (homes), ACH50 | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-04-air-leakage-homes-ach50) |  |
| `DEF-05` | Heating and cooling equipment efficiency | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-05-heating-and-cooling-equipment-efficiency) |  |
| `DEF-06` | Duct leakage class (homes with ducts outside the conditioned space) | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-06-duct-leakage-class-homes-with-ducts-outside-the-conditioned-space) |  |
| `DEF-07` | Water heaters | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-07-water-heaters) |  |
| `DEF-08` | Thermostat setpoints | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-08-thermostat-setpoints) | yes |
| `DEF-09` | Schedules | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-09-schedules) | yes |
| `DEF-10` | Lighting and plug power density | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-10-lighting-and-plug-power-density) |  |
| `DEF-11` | Office envelope by vintage | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-11-office-envelope-by-vintage) |  |
| `DEF-12` | Exterior walls when the scan has no wall graph | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-12-exterior-walls-when-the-scan-has-no-wall-graph) |  |
| `DEF-13` | Storey of a suite whose floor label says nothing | see entry | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#def-13-storey-of-a-suite-whose-floor-label-says-nothing) |  |
| `BEN-01` | Site energy use intensity | V | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#ben-01-site-energy-use-intensity-v) |  |
| `BEN-02` | The comparison cut | V for the table, J for the order | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#ben-02-the-comparison-cut-v-for-the-table-j-for-the-order) |  |
| `BEN-03` | Position, band and warning | J | [`physics/02-thermal-systems.md`](physics/02-thermal-systems.md#ben-03-position-band-and-warning-j) |  |
| `DAY-01` | Daylight factor and its components | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#day-01-daylight-factor-and-its-components-v) |  |
| `DAY-02` | CIE overcast sky | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#day-02-cie-overcast-sky-v) |  |
| `DAY-03` | Sky component at a point from a vertical rectangular window | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#day-03-sky-component-at-a-point-from-a-vertical-rectangular-window-v) |  |
| `DAY-04` | External obstruction and externally reflected component | V geometry; P luminance rule | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#day-04-external-obstruction-and-externally-reflected-component-v-geometry-p-luminance-rule) |  |
| `DAY-05` | Internally reflected component, split-flux method | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#day-05-internally-reflected-component-split-flux-method-v) |  |
| `DAY-06` | Average daylight factor (room-level sanity check only) | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#day-06-average-daylight-factor-room-level-sanity-check-only-v) |  |
| `DAY-07` | Outdoor illuminance from irradiance: Perez luminous efficacy | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#day-07-outdoor-illuminance-from-irradiance-perez-luminous-efficacy-v) |  |
| `DAY-08` | Hourly indoor illuminance | V as a method; simplification stated | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#day-08-hourly-indoor-illuminance-v-as-a-method-simplification-stated) | yes |
| `DAY-09` | Annual metrics: daylight autonomy | V definition | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#day-09-annual-metrics-daylight-autonomy-v-definition) | yes |
| `DAY-10` | Target illuminances | V as quoted from open reproductions | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#day-10-target-illuminances-v-as-quoted-from-open-reproductions) |  |
| `GLR-01` | Vertical illuminance at the eye from geometry | V arithmetic; simplification | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#glr-01-vertical-illuminance-at-the-eye-from-geometry-v-arithmetic-simplification) |  |
| `GLR-02` | Simplified daylight glare probability, DGPs | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#glr-02-simplified-daylight-glare-probability-dgps-v) |  |
| `GLR-03` | Full daylight glare probability (reference only, not computed) | V form; coefficients from open secondaries | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#glr-03-full-daylight-glare-probability-reference-only-not-computed-v-form-coefficients-from-open-secondaries) |  |
| `GLR-04` | Direct sun in the field of view | V geometry; rule is a design simplification | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#glr-04-direct-sun-in-the-field-of-view-v-geometry-rule-is-a-design-simplification) |  |
| `GLR-05` | Annual glare risk for a desk | V arithmetic; thresholds from S7; orientation rule is a design choice | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#glr-05-annual-glare-risk-for-a-desk-v-arithmetic-thresholds-from-s7-orientation-rule-is-a-design-choice) | yes |
| `CMF-01` | Predicted mean vote, PMV | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#cmf-01-predicted-mean-vote-pmv-v) |  |
| `CMF-02` | Predicted percentage dissatisfied, PPD | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#cmf-02-predicted-percentage-dissatisfied-ppd-v) |  |
| `CMF-03` | Operative temperature | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#cmf-03-operative-temperature-v) |  |
| `CMF-04` | Inside surface temperature of the glazing | V derivation; P film coefficient | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#cmf-04-inside-surface-temperature-of-the-glazing-v-derivation-p-film-coefficient) |  |
| `CMF-05` | Mean radiant temperature at the body | V formula; view factor is a simplification | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#cmf-05-mean-radiant-temperature-at-the-body-v-formula-view-factor-is-a-simplification) |  |
| `CMF-06` | Radiant temperature asymmetry near a cold window | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#cmf-06-radiant-temperature-asymmetry-near-a-cold-window-v) |  |
| `CMF-07` | Direct and diffuse solar load on the occupant, SolarCal | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#cmf-07-direct-and-diffuse-solar-load-on-the-occupant-solarcal-v) |  |
| `CMF-08` | Annual comfort figure for a desk | V arithmetic; aggregation is a design choice | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#cmf-08-annual-comfort-figure-for-a-desk-v-arithmetic-aggregation-is-a-design-choice) | yes |
| `LCT-01` | Electric lighting output and power under daylight control | V | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#lct-01-electric-lighting-output-and-power-under-daylight-control-v) |  |
| `LCT-02` | Annual lighting energy displaced | V arithmetic; behavioural factor U | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#lct-02-annual-lighting-energy-displaced-v-arithmetic-behavioural-factor-u) | yes |
| `LCT-03` | Desk score | design choice, not physics | [`physics/03-daylight-comfort.md`](physics/03-daylight-comfort.md#lct-03-desk-score-design-choice-not-physics) | yes |
| `ECO-01` | Real and nominal rates | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-01-real-and-nominal-rates) |  |
| `ECO-02` | Single present value factor (SPV) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-02-single-present-value-factor-spv) |  |
| `ECO-03` | Uniform present value factor (UPV) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-03-uniform-present-value-factor-upv) |  |
| `ECO-04` | Modified uniform present value factor (UPV*), constant escalation | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-04-modified-uniform-present-value-factor-upv-constant-escalation) |  |
| `ECO-05` | Default economic parameters | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-05-default-economic-parameters) | yes |
| `ECO-06` | Energy price escalation: equivalent constant real rate | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-06-energy-price-escalation-equivalent-constant-real-rate) | yes |
| `ECO-07` | Net present value of a measure (net savings) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-07-net-present-value-of-a-measure-net-savings) | yes |
| `ECO-08` | Replacement cost and residual value | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-08-replacement-cost-and-residual-value) |  |
| `ECO-09` | Savings-to-investment ratio (SIR) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-09-savings-to-investment-ratio-sir) | yes |
| `ECO-10` | Rates of return: AIRR and IRR | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-10-rates-of-return-airr-and-irr) | yes |
| `ECO-11` | Simple and discounted payback | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-11-simple-and-discounted-payback) | yes |
| `ECO-12` | Level payment on an assessment or loan (C-PACE scenario) and first-year net cash flow | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-12-level-payment-on-an-assessment-or-loan-c-pace-scenario-and-first-year-net-cash-flow) |  |
| `ECO-12b` | Program SIR for a Texas PACE assessment (not the same as ECO-09) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-12b-program-sir-for-a-texas-pace-assessment-not-the-same-as-eco-09) |  |
| `ECO-13` | Timing of incentives in the cash flow | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#eco-13-timing-of-incentives-in-the-cash-flow) | yes |
| `TAR-01` | Bill with a flat energy charge, and bill savings | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#tar-01-bill-with-a-flat-energy-charge-and-bill-savings) | yes |
| `TAR-02` | Bill with time-of-use energy charges | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#tar-02-bill-with-time-of-use-energy-charges) |  |
| `TAR-03` | Export compensation for rooftop solar | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#tar-03-export-compensation-for-rooftop-solar) | yes |
| `TAR-04` | Gas bill | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#tar-04-gas-bill) |  |
| `TAR-06` | Default electricity price where no utility tariff exists (Houston) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#tar-06-default-electricity-price-where-no-utility-tariff-exists-houston) |  |
| `TAR-05` | Unit conversions | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#tar-05-unit-conversions) |  |
| `EMI-01` | Grid electricity emission factors | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#emi-01-grid-electricity-emission-factors) | yes |
| `EMI-02` | Natural gas combustion | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#emi-02-natural-gas-combustion) |  |
| `EMI-03` | Net effect of fuel switching | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#emi-03-net-effect-of-fuel-switching) |  |
| `INC-01 to INC-06` | Federal tax incentives | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#inc-01-to-inc-06-federal-tax-incentives) |  |
| `INC-07` | Federal home energy rebates run by the states (HOMES and HEEHRA) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#inc-07-federal-home-energy-rebates-run-by-the-states-homes-and-heehra) |  |
| `INC-10 to INC-19` | Utility programs, Los Angeles | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#inc-10-to-inc-19-utility-programs-los-angeles) |  |
| `INC-30 to INC-34` | Utility programs, Houston (CenterPoint Energy Houston Electric) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#inc-30-to-inc-34-utility-programs-houston-centerpoint-energy-houston-electric) |  |
| `INC-40` | Computing an incentive amount | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#inc-40-computing-an-incentive-amount) | yes |
| `COST-00` | Bringing source costs to the base date | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#cost-00-bringing-source-costs-to-the-base-date) |  |
| `COST-01` | Installed cost by measure | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#cost-01-installed-cost-by-measure) | yes |
| `COST-02` | Useful life | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#cost-02-useful-life) | yes |
| `MV-01` | The savings equation and the four IPMVP options | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#mv-01-the-savings-equation-and-the-four-ipmvp-options) |  |
| `MV-02` | Baseline regression models with weather normalisation | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#mv-02-baseline-regression-models-with-weather-normalisation) |  |
| `MV-03` | Goodness-of-fit statistics | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#mv-03-goodness-of-fit-statistics) |  |
| `MV-04` | Calibration tolerances for the simulation model (Option D) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#mv-04-calibration-tolerances-for-the-simulation-model-option-d) |  |
| `MV-05` | Savings and savings uncertainty | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#mv-05-savings-and-savings-uncertainty) |  |
| `MV-06` | Calibration procedure: fitting the simulation to twelve monthly bills (Option D) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#mv-06-calibration-procedure-fitting-the-simulation-to-twelve-monthly-bills-option-d) |  |
| `UNC-01` | What low, expected and high mean | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#unc-01-what-low-expected-and-high-mean) |  |
| `UNC-02` | One-at-a-time runs combined in quadrature | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#unc-02-one-at-a-time-runs-combined-in-quadrature) | yes |
| `UNC-03` | Sensitivity ranking used by the ask rule (SPEC 5.3) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#unc-03-sensitivity-ranking-used-by-the-ask-rule-spec-53) |  |
| `VAL-01` | Capitalised savings (income approach), commercial and multifamily | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#val-01-capitalised-savings-income-approach-commercial-and-multifamily) |  |
| `VAL-02` | Rent uplift (stub) | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#val-02-rent-uplift-stub) |  |
| `VAL-03` | Homes with owned rooftop solar | see entry | [`physics/04-economics-emissions-mv.md`](physics/04-economics-emissions-mv.md#val-03-homes-with-owned-rooftop-solar) |  |

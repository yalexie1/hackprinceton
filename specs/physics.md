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

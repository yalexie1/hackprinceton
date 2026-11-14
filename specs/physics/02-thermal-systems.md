# Physics spec 02: thermal model and building systems

Status: complete draft, written and checked on 2026-11-14 (resumed after an interruption on 2026-11-13). Every entry has been through both checking passes described in section 11. What could not be verified is in section 10 and nowhere else.

Covers: envelope conduction (`ENV`), hourly zone model (`ZON`), infiltration and ventilation (`INF`), window solar gain (`WIN`), HVAC (`HVAC`), water heating (`DHW`), lighting and plug loads (`LGT`), default tables (`DEF`).

## 0. Conventions

**Units.** SI everywhere: m, m², m³, W, W/K, W/(m²·K), J, K or °C for temperatures, kg, s. Energy leaves the physics functions in kWh (1 kWh = 3.6 MJ). Gas is kWh thermal on a higher-heating-value basis, because AFUE and UEF are defined on that basis. Hourly quantities are averages over the hour unless stated.

**Gas.** Gas is carried as kWh of higher heating value, 1 therm = 29.3071 kWh, as fixed in physics 04. Prices and emission factors are that file's job; this file stops at kWh of electricity and kWh of gas.

**Azimuth.** Surface azimuths are true azimuths, degrees clockwise from north. For a wall edge, `azimuth_true = azimuth_in_model + north_offset_deg`, where `azimuth_in_model` is the outward normal's angle clockwise from the model frame's +y axis and `BuildingModel.north_offset_deg` is the azimuth of the model +y axis (contract definition; the direction of the underlying quaternion is a pending check of the Data lane under physics 01 ROOF-02).

**Irradiance and sun position** come from physics 01 and are not restated here: sun position SOL-01 (or SOL-05), angle of incidence IRR-04, plane-of-array total irradiance IRR-10 (beam IRR-05, sky diffuse IRR-08, ground-reflected IRR-09). `I_sol` in this file always means the IRR-10 total on the surface's plane, with the hourly time convention of SOL-07.

**Sign.** Heat flow into the zone is positive. `phi_hc` is positive for heating and negative for cooling. Cooling need is reported as a positive number where a function name says `cooling_need`.

**Imperial conversions** used in this file (exact or to six figures):

| From | To | Multiply by |
|---|---|---|
| R-value, h·ft²·°F/Btu | m²·K/W | 0.176110 |
| U-factor, Btu/(h·ft²·°F) | W/(m²·K) | 5.678263 |
| F-factor, Btu/(h·ft·°F) | W/(m·K) | 1.730735 |
| Btu/h | W | 0.293071 |
| Btu/(W·h) (EER, SEER, HSPF) | W/W (COP) | 0.293071 (divide by 3.412142) |
| ft² | m² | 0.092903 |
| cfm | m³/s | 0.000471947 |
| US gallon | m³ | 0.00378541 |
| °F difference | K | 5/9 |
| W/ft² | W/m² | 10.7639 |

**Ranges.** Every inferred input is an `Assumption` with low/expected/high. Physics functions take plain floats. The caller runs them at the expected value and perturbs one assumption at a time (master spec section 5.3). Where an entry below says "carry as a range", the low and high values to use are in section 8 (`DEF`).

**Data that is measured, not assumed** (contract `SCHEMA_VERSION = "0.3.0"`):

- Window and door area and position come from `WallEdge.openings` (`Opening`: `type`, `width_m`, `height_m`, `lower_elevation_m`, `relative_center`), source `measured`. `Opening.type == "window"` means glazing; `"doorway"` is a door (opaque unless vision says it is glazed); `"opening"` and `"divider"` are not envelope elements. `relative_center` is a fraction of the edge length in [0, 1], not metres; this file needs only width, height and the edge's azimuth. A window `Surface` built from an opening carries `source_edge_id` and `source_opening_id`; one built from vision has `source_opening_id = None`. When a model has no openings of a window type (the first live check returned only `doorway` openings, so this case is real), window count and size come from the panorama reading, source `vision`, with a wider range (section 8, `DEF-03`). Glazing performance (U-value, SHGC) is always an assumption.
- Surface azimuth comes from `MatterportData.georeference` (rotation to true north). It is data, not a wide range.
- For offices, occupant count, plug-load intensity and schedule type are driven by `CostarData.occupancy` (tenancies with employee counts and industry) when present; the assumption tables are the fallback (sections 7 and 8).
- Vintage for every default table is `CostarData.year_built`, which the Data lane fills from CoStar's `constructionEvents[]` (the construction-complete event is preferred; `year_built_event` records which event was used, since CoStar has no scalar year built). Envelope areas scale with `building_area_m2` (gross building area). `rentable_area_m2` is a leasing figure and is never used for envelope or load areas.

**Source keys.** Sources opened and read for this file. "Opened" means the text was downloaded and the passage read on the date in section 11.

| Key | Source |
|---|---|
| S1 | ISO 13790:2008, *Energy performance of buildings: calculation of energy use for space heating and cooling*. Paywalled and withdrawn (replaced by ISO 52016-1:2017). Read through the public bilingual text of the Ukrainian national adoption DSTU B EN ISO 13790:2011, `https://dnaop.com/html/61992_N.html` (N = 1 to 47), which carries the English clause text. Its equations are partly illegible, so clause wording, constants and tables were checked there, and the equations themselves were taken from S2 and S3. |
| S2 | RC_BuildingSimulator, ETH Zurich Architecture and Building Systems, `rc_simulator/building_physics.py` and `tests/testRCmodel.py`, `https://github.com/architecture-building-systems/RC_BuildingSimulator`. Each function cites its ISO 13790 Annex C equation number. |
| S3 | Independent implementations of the same model: tsib `tsib/thermal/model5R1C.py` (Forschungszentrum Jülich, `https://github.com/FZJ-IEK3-VSA/tsib`) and City Energy Analyst `cea/demand/rc_model_SIA.py` (ETH Zurich). |
| S4 | Ballarini, Costantino, Fabrizio, Corrado (2019), "The dynamic model of EN ISO 52016-1 for the energy assessment of buildings compared to simplified and detailed simulation methods", Building Simulation 2019, DOI 10.26868/25222708.2019.210431. |
| S5 | Anderson, *Conventions for U-value calculations*, BRE report BR 443, 2006 edition. Open reproduction of the ISO 6946 surface resistances and combined method. |
| S6 | California Energy Commission, *2022 Reference Appendices*, CEC-400-2022-010-AP, Joint Appendix JA4 "U-factor, C-factor, and Thermal Mass Data". |
| S7 | BRE, *RdSAP 10 Specification*, section 5.12 "U-values of floors next to the ground". Open reproduction of the ISO 13370 slab-on-ground formula. |
| S8 | US DOE, *EnergyPlus 24.1 Engineering Reference* and *Input Output Reference*, `https://bigladdersoftware.com/epx/docs/24-1/`. |
| S9 | Loga and Diefenbach, *TABULA Calculation Method: Energy Use for Heating and Domestic Hot Water*, IWU, 2013 (`TABULA_CommonCalculationMethod.pdf`, episcope.eu). |
| S10 | Wilson, Engebrecht Metzger, Horowitz, Hendron, *2014 Building America House Simulation Protocols*, NREL/TP-5500-60988 (OSTI 1221086). |
| S11 | Deru et al., *U.S. Department of Energy Commercial Reference Building Models of the National Building Stock*, NREL/TP-5500-46861, 2011 (OSTI 1009264). |

Further keys are introduced in the sections that use them.

ISO 6946, ISO 13370, ISO 13789, the ASHRAE Handbook of Fundamentals and ASHRAE Standards 62.1, 62.2, 90.1, 140 and 152 are paywalled and were **not** opened. Wherever this file relies on their content it says which open document reproduced it.

## 1. ENV: envelope conduction

### ENV-01 Assembly U-value from layers

```
R_T = R_si + sum_j (d_j / lambda_j) + sum_k R_k + R_se
U   = 1 / R_T
```

| Symbol | Meaning | Unit |
|---|---|---|
| `d_j` | thickness of homogeneous layer j | m |
| `lambda_j` | design thermal conductivity of layer j | W/(m·K) |
| `R_k` | resistance of a layer given directly (rated insulation, air space) | m²·K/W |
| `R_si`, `R_se` | internal and external surface resistance | m²·K/W |
| `R_T`, `U` | total resistance, thermal transmittance | m²·K/W, W/(m²·K) |

Surface resistances (ISO 6946 values as reproduced in S5 section 4.1):

| Heat flow direction | Element | `R_si` | `R_se` |
|---|---|---|---|
| horizontal | wall, window | 0.13 | 0.04 |
| upwards | roof, ceiling in the heating season | 0.10 | 0.04 |
| downwards | floor, and ceiling under cooling | 0.17 | 0.04 |

US tables use the ASHRAE films instead: exterior R-0.17 (0.030 m²·K/W), interior wall R-0.68 (0.120), interior ceiling with heat flow up R-0.61 (0.107) (S6, assumptions under Tables 4.2.1 and 4.3.1). The two sets differ by 0.02 m²·K/W in total for a wall. Rule: when a U-factor is taken from a US table (section 8), use it as published; when an assembly is built up from layers, use the ISO set above.

Validity: plane, homogeneous layers, one-dimensional steady heat flow. Not valid for a layer bridged by framing (use ENV-02) or by metal (not supported; a steel-framed wall takes its U-factor from a table).

Primary: ISO 6946 clause 6 (not opened), as reproduced in S5 sections 3.1 and 4.1. Second source: S6 Table 4.1.1, which sums the layers of a wood-framed wall in series with the ASHRAE films.

Worked example (S6 Table 4.1.1, cavity path of a 2x4 wall): outside film 0.17, stucco 0.08, R-4 sheathing 4.0, building paper 0.06, R-15 batt 15, gypsum 0.45, inside film 0.68 h·ft²·°F/Btu. Sum = 20.44 (the table prints 20.44). In SI: `R_T` = 20.44 × 0.176110 = 3.5997 m²·K/W, `U` = 0.2778 W/(m²·K). Checked by converting each layer to SI first and summing (3.5997), and by `5.678263 / 20.44` (0.2778).

Tool: `assembly_u_value(layers: list[{thickness_m, conductivity_w_mk} | {r_m2k_w}], heat_flow: "horizontal"|"up"|"down") -> u_w_m2k`.

### ENV-02 Framing correction (parallel path)

```
U = (1 - f) / R_c + f / R_f
```

| Symbol | Meaning | Unit |
|---|---|---|
| `R_c` | total resistance (ENV-01, films included) through the insulated cavity | m²·K/W |
| `R_f` | total resistance through the framing member | m²·K/W |
| `f` | framing fraction of the wall area | - |

Framing fraction: 0.25 for studs at 16 in. centres, 0.22 at 24 in. centres (S6, assumptions under Table 4.3.1). Softwood framing is R-0.99 per inch in S6 Table 4.1.1, which is `lambda` = 0.0254 / (0.99 × 0.176110) = 0.146 W/(m·K).

Validity: wood framing only. The parallel-path result is the lower bound on U (it is the "upper limit of resistance" in ISO 6946). The ISO 6946 combined method averages that with the isothermal-planes limit and gives a higher U; the true value lies between. Carry the parallel-path value as expected and the ISO combined value as high.

```
R_upper = 1 / U_parallel
R_lower = sum(homogeneous layers and films) + 1 / ((1 - f)/R_ins + f/R_wood)     # bridged layer only
U_iso   = 2 / (R_upper + R_lower)
```

Primary: ASHRAE Handbook of Fundamentals parallel-path method (not opened), as reproduced and worked in S6 section JA4.1.2 and Table 4.1.1. Second source: S5 section 3.1, which describes the ISO 6946 combined method (upper and lower limits, arithmetic mean).

Worked example (S6 Table 4.1.1): `R_c` = 20.44, `R_f` = 8.91 h·ft²·°F/Btu, `f` = 0.25. `U` = 0.75/20.44 + 0.25/8.91 = 0.0648 Btu/(h·ft²·°F); the table prints 0.065. In SI: 0.3677 W/(m²·K), obtained both by converting the result and by converting `R_c` and `R_f` first. ISO combined method on the same wall: `R_upper` = 15.444, `R_lower` = 5.44 + 1/(0.75/15 + 0.25/3.47) = 13.634, `U_iso` = 0.0688 Btu/(h·ft²·°F) = 0.3906 W/(m²·K), 6.2 % above the parallel-path value.

Tool: `parallel_path_u_value(r_cavity_m2k_w, r_frame_m2k_w, framing_fraction) -> u_w_m2k`.

### ENV-03 Transmission heat transfer coefficient (UA summation)

```
H_tr,w  = sum over windows and doors      A_i * U_i
H_tr,op = sum over opaque surfaces  b_i * A_i * U_i,eff  + H_g  + sum_k l_k * psi_k
```

| Symbol | Meaning | Unit |
|---|---|---|
| `A_i` | surface area. Opaque wall area is net of its openings | m² |
| `U_i` | thermal transmittance (ENV-01, ENV-02, or a default from section 8) | W/(m²·K) |
| `b_i` | adjustment factor by `Surface.boundary`, table below | - |
| `H_g` | ground floor coefficient (ENV-04) | W/K |
| `l_k`, `psi_k` | length and linear transmittance of thermal bridges | m, W/(m·K) |

| `Surface.boundary` | Treatment | Source |
|---|---|---|
| `exterior` | `b` = 1 | S1 clause 8.3.1 |
| `adjacent_conditioned` | `b` = 0 (no heat flow) | S1 clause 8.3.1; design decision that neighbours hold the same temperature |
| `adjacent_unconditioned` | `b` = 1 with `U_eff = 1 / (1/U + 0.3)` | S9 Table 2, additional resistance 0.3 m²·K/W for a construction bordering an unheated room or attic |
| `ground` | not summed here; use ENV-04 | S1 clause 8.3.2 |

Thermal bridges: `psi` values are not known for these buildings. US framed-wall tables already contain the framing; set the bridge term to zero and say so in the assumption list.

Validity: steady-state coefficients for use in the zone model of section 2. Windows and doors are kept apart from opaque elements because the zone model treats them as massless (S1 clause 7.2.2.1, note 2).

Primary: S1 clause 8.3.1 (opened: `H_x = b_tr,x [sum A_i U_i + sum l_k psi_k + sum chi_j]`, summed over elements to the exterior, the ground, unconditioned and adjacent conditioned spaces). Second source: S9 equation (4), `H_tr = sum b_tr A_env,i (U_eff,i + dU_tbr)`.

Worked example: wall 95 m² at 0.368, roof 120 m² at 0.20, windows 18 m² at 2.8, door 3.8 m² at 2.0, all exterior. `H_tr,w` = 50.40 + 7.60 = 58.00 W/K. Opaque without ground = 34.96 + 24.00 = 58.96 W/K. With `H_g` = 74.32 W/K from ENV-04, `H_tr,op` = 133.28 W/K. (The zone examples in section 2 use 133.26, from unrounded inputs.) Checked by script and by hand.

Tool: `transmission_coefficients(surfaces: list[Surface], ground_h_w_k) -> {h_tr_w_w_k, h_tr_op_w_k}`.

### ENV-04 Slab-on-grade floor

```
B'  = 2 * A / P
d_t = w + lambda_g * (R_si + R_f + R_se)
U_g = 2 * lambda_g / (pi * B' + d_t) * ln(pi * B' / d_t + 1)        if d_t <  B'
U_g = lambda_g / (0.457 * B' + d_t)                                 if d_t >= B'
H_g = A * U_g
```

| Symbol | Meaning | Unit |
|---|---|---|
| `A` | slab area in contact with the ground | m² |
| `P` | exposed perimeter: the length of slab edge that faces outdoors or an unconditioned space. Edges shared with a conditioned neighbour are excluded | m |
| `B'` | characteristic dimension | m |
| `w` | full thickness of the external wall | m |
| `lambda_g` | ground conductivity; 1.5 W/(m·K) for clay (S7). Carry 1.5 as expected and 2.0 as high | W/(m·K) |
| `R_f` | resistance of all-over floor insulation, 0 for a bare slab. The slab itself is neglected | m²·K/W |
| `R_si`, `R_se` | 0.17 and 0.04 | m²·K/W |
| `U_g`, `H_g` | floor transmittance referred to the indoor–outdoor air temperature difference, and its coefficient | W/(m²·K), W/K |

Use in the hourly model: add `H_g` to `H_tr,op`, driven by the outdoor air temperature of the hour. This overstates the hourly swing of ground loss and is correct on the annual mean; the zone capacitance absorbs part of the swing. ISO 13370 gives a monthly formulation with a phase lag that was not opened (see section 10).

`w` comes from `WallEdge.thickness_m` when present, otherwise 0.15 m for a framed wall. An upper-floor apartment or an office suite above the ground floor has no ground surface.

Validity: slab on ground, uninsulated or insulated over its whole area. Edge-only insulation needs the ISO 13370 edge correction, which was not opened; treat edge insulation as no insulation and note it (US slabs in climate zones 2 and 3 are normally uninsulated; `DEF-01`).

Primary: ISO 13370 (not opened), as reproduced in S7 section 5.12, steps 1 to 4 for solid ground floors. Second source, independent method: the perimeter F-factor method, `H_g = P * F`, as stated in S8 Engineering Reference "Ground heat transfer calculations using C and F factor constructions" (`U_eff = P_exp * F / Area`), with `F` = 0.73 Btu/(h·ft·°F) = 1.263 W/(m·K) for an unheated, uninsulated slab (S6 Table 4.4.7, taken there from ASHRAE 90.1-2004 Appendix A).

Worked example: `A` = 120 m², `P` = 44 m, `w` = 0.15 m, bare slab, clay. `B'` = 5.4545 m, `d_t` = 0.15 + 1.5 × 0.21 = 0.465 m, `U_g` = 3.0 × ln(36.851 + 1) / 17.601 = 0.6193 W/(m²·K), `H_g` = 74.32 W/K. Recomputed twice (math.log and numpy.log1p), 0.619342 both times. With `lambda_g` = 2.0: `U_g` = 0.7762, `H_g` = 93.15 W/K. F-factor method on the same slab: 44 × 1.2634 = 55.59 W/K.

The two methods differ by 25 % here (55.6 against 74.3 W/K). They are different models with different soil assumptions, so this is the honest size of the uncertainty and not an arithmetic error. Carry the F-factor value as low, ISO 13370 with clay as expected, and ISO 13370 with `lambda_g` = 2.0 as high.

Tool: `slab_on_grade_coefficient(area_m2, exposed_perimeter_m, wall_thickness_m, r_floor_m2k_w=0.0, ground_conductivity_w_mk=1.5) -> {u_w_m2k, h_g_w_k}` and `slab_f_factor_coefficient(exposed_perimeter_m, f_factor_w_mk=1.263) -> h_g_w_k`.

### ENV-05 Sol-air temperature and roof solar absorptance

For an opaque exterior surface, the heat flow into the zone is

```
theta_sa = theta_e + R_se * (alpha * I_sol - F_r * h_r * dtheta_er)
Phi      = U * A * (theta_sa - theta_i)
```

which is the same as the ISO 13790 form used by the zone model, where the outdoor-air part goes through `H_tr,op` and the rest is a solar gain term:

```
Phi_sol,op = F_sh,ob * A_sol * I_sol - F_r * Phi_r
A_sol      = alpha * R_se * U * A
Phi_r      = R_se * U * A * h_r * dtheta_er
h_r        = 4 * eps * sigma * (theta_ss + 273.15)^3      (about 5 * eps at 10 °C)
```

| Symbol | Meaning | Unit |
|---|---|---|
| `theta_e`, `theta_i` | outdoor and indoor air temperature | °C |
| `theta_sa` | sol-air temperature | °C |
| `alpha` | solar absorptance of the outer surface (1 minus solar reflectance) | - |
| `I_sol` | total solar irradiance on the surface plane (physics 01, IRR-10) | W/m² |
| `R_se` | external surface resistance, 0.04 | m²·K/W |
| `F_r` | form factor to the sky: 1 for an unshaded horizontal roof, 0.5 for an unshaded vertical wall | - |
| `h_r` | external radiative coefficient | W/(m²·K) |
| `eps` | thermal emittance of the surface, 0.90 by default | - |
| `sigma` | 5.67e-8 | W/(m²·K⁴) |
| `theta_ss` | mean of surface and sky temperature | °C |
| `dtheta_er` | outdoor air temperature minus apparent sky temperature; 11 K when the weather file has no sky temperature | K |
| `F_sh,ob` | shading factor for external obstacles on the surface, 1 if unknown | - |
| `A_sol` | effective solar collecting area | m² |

Cool roof measure (`ROOF_COOL`): changing the absorptance from `alpha_1` to `alpha_2` changes the hourly gain by

```
dPhi = U * A * R_se * (alpha_1 - alpha_2) * I_sol
```

The saving therefore scales with the roof U-value: a well-insulated roof gains little from a cool surface. The annual energy effect comes from running the zone model with both absorptances, because the cool roof also raises the heating need.

Validity and limits:

- Linearised long-wave exchange and a constant `R_se`. Against a full non-linear surface balance the linear form overstates the roof gain by 5 to 7 % at peak sun (worked example). `R_se` = 0.04 corresponds to a combined coefficient of 25 W/(m²·K); S8 "Simple Combined" gives `h = 10.79 + 4.192 * v` for a medium-rough surface, which is 25 at a wind speed of 3.4 m/s. At lower wind the gain is larger. Carry `R_se` as 0.04 expected, 0.06 high.
- **Vented attics.** S1 clause 11.3.4 warns that for an element with a layer ventilated by outdoor air this formula overstates the solar gain unless the U-value used in it is corrected. A pitched roof over a vented attic is such an element. The attic correction was not sourced (section 10), so for a home with a vented attic the `ROOF_COOL` saving from this entry is an upper bound and must be shown with that warning. For low-slope roofs with insulation at the deck (most small offices and flat-roofed apartment buildings) the formula applies as written.
- Default absorptances are in `DEF-02`.

Primary: S1 clauses 11.3.1 (eq. 43), 11.3.4 (eq. 45), 11.3.5 (eq. 46) and 11.4.6 (eq. 51, form factors, 11 K), opened; the note in 11.3.5 allows the same physics to be written with an external operative (sol-air) temperature. Second source: S8 Engineering Reference "Outside Surface Heat Balance": `q_asol + q_LWR + q_conv - q_ko = 0`, with the statement that simplified procedures combine the first three terms into a sol-air temperature; and S3 (tsib uses `R_se` = 0.04, `h_r` = 5 eps, 11 K in the same product form). The sol-air equation in the ASHRAE Handbook of Fundamentals was not opened.

Worked example: roof `A` = 150 m², `U` = 0.30, `theta_e` = 32, `theta_i` = 24, `I_sol` = 800, `eps` = 0.9 (so `h_r` = 4.5), 11 K, `F_r` = 1.

| `alpha` | `theta_sa` | `Phi` sol-air route | `Phi` ISO route | non-linear balance |
|---|---|---|---|---|
| 0.85 (dark) | 57.22 °C | 1494.9 W | 1494.9 W | 1394.7 W (−6.7 %) |
| 0.30 (cool) | 39.62 °C | 702.9 W | 702.9 W | 665.5 W (−5.3 %) |

Reduction 792.0 W, equal to `U A R_se dalpha I` = 0.30 × 150 × 0.04 × 0.55 × 800 = 792.0 W. The non-linear column solves `alpha I + eps sigma (T_sky⁴ − T_s⁴) + h_c (T_e − T_s) = (T_s − T_i) / (1/U − R_se)` for the surface temperature with `h_c` = 20.5 W/(m²·K), by root finding.

Tool: `sol_air_temperature(t_out_c, irradiance_w_m2, absorptance, r_se=0.04, emittance=0.9, sky_form_factor, dt_sky_k=11.0) -> t_sol_air_c` and `opaque_solar_gain(u_w_m2k, area_m2, irradiance_w_m2, absorptance, sky_form_factor, r_se=0.04, emittance=0.9, dt_sky_k=11.0, shading_factor=1.0) -> gain_w`.

### ENV-06 Surface heat transfer coefficients `h_i` and `h_e`

```
h_i = 1 / R_si          h_e = 1 / R_se
```

| Surface, heat flow | `R_si` | `h_i` | `R_se` | `h_e` | Source |
|---|---|---|---|---|---|
| wall or window, horizontal | 0.13 | 7.69 | 0.04 | 25.0 | ISO 6946 values as reproduced in S5 section 4.1 |
| ceiling or roof, upward | 0.10 | 10.0 | 0.04 | 25.0 | same |
| floor, downward | 0.17 | 5.88 | 0.04 | 25.0 | same |
| wall or window, US tables | 0.120 (R-0.68) | 8.35 | 0.030 (R-0.17) | 33.4 | ASHRAE films as stated under S6 Tables 4.2.1 and 4.3.1 |

Units: `R` in m²·K/W, `h` in W/(m²·K). These are combined coefficients (convection plus long-wave radiation).

**For physics 03 (CMF-04, inside glass surface temperature):** use `h_i` = 7.69 W/(m²·K) as expected, with 7.69 to 8.35 as the range. The round number 8.0 used there as a placeholder lies inside this range; on its worked example (21 °C inside, −5 °C outside, `U_w` = 2.8) the glass temperature is 11.54 °C at 7.69 and 12.28 °C at 8.35, against 11.90 °C at 8.0. Use the value that matches the origin of the U-value: 8.35 with a US (NFRC or S6) window U-factor, 7.69 with a U-value built by ENV-01.

Do not confuse `h_i` with the zone model's `h_is` = 3.45 W/(m²·K) (ZON-01). `h_is` couples the air node to the model's surface node and is specific to the 5R1C network; `h_i` is the film between room and a real surface.

`h_e` at 25 corresponds to a wind speed of about 3.4 m/s on a medium-rough surface (S8 "Simple Combined", `h = 10.79 + 4.192 v`); see ENV-05 for the range.

Primary: ISO 6946 (not opened) via S5 section 4.1. Second source: S6 (ASHRAE films in US assembly tables). Worked example: 1/0.13 = 7.692; 1/(0.68 × 0.176110) = 8.350; 1/0.04 = 25.0; 1/(0.17 × 0.176110) = 33.40. Recomputed by script.

Tool: `surface_coefficients(kind: "wall"|"window"|"roof"|"floor", convention: "iso"|"ashrae") -> {h_i_w_m2k, h_e_w_m2k}`.

## 2. ZON: hourly zone thermal model

### ZON-00 Choice of method

The baseline uses the **ISO 13790:2008 simple hourly method** (five resistances, one capacitance, "5R1C"), one zone per building or per unit.

Reasons, against the ISO 52016-1 hourly method:

1. **Inputs match what is known.** 5R1C needs four conductances, one capacitance and one mass area. ISO 52016-1 needs the layer structure or a mass-distribution class for every construction element, and a node per layer. Layer structure is not measured here; it would be invented.
2. **Closed-form hourly solution.** Heating or cooling need per hour comes from two evaluations of an explicit formula, with no matrix solve. It is deterministic and fast enough to re-run for every assumption perturbation and every measure.
3. **It can be tested against published numbers.** S2 ships unit tests with expected values, and section 2 reproduces them to the published precision.
4. **Accuracy is adequate for ranking measures.** S4 compared both ISO hourly methods with EnergyPlus on its case-study building: ISO 13790 was 2.0 % high on annual heating need and 4.1 % high on annual cooling need. S4 also shows the weakness: the single capacitance responds faster than a layered construction (in a temperature-decay test the time constant was 81 h with ISO 13790 against 296 h in EnergyPlus), so **hourly peak timing is less reliable than annual energy**. `peak_cooling_w` and `peak_heating_w` are indicative.

ISO 13790 is withdrawn in favour of ISO 52016-1. That is a change of the standard's status, not a finding that the method is wrong, and S4 shows the two agree within a few percent on annual needs.

The model gives sensible heating and cooling need only. Latent cooling load is added in `INF-06`.

### ZON-01 Model parameters

```
A_tot   = 4.5 * A_f
H_tr,is = 3.45 * A_tot
H_tr,ms = 9.1 * A_m
H_tr,em = 1 / (1/H_tr,op - 1/H_tr,ms)
C_m, A_m  from the table below
H_ve    = rho_a c_a * q_ve          (section 3; may change every hour)
```

| Symbol | Meaning | Unit |
|---|---|---|
| `A_f` | conditioned floor area of the zone (`Zone.floor_area_m2`) | m² |
| `A_tot` | area of all surfaces facing the zone | m² |
| `H_tr,is` | coupling between air node and surface node; `h_is` = 3.45 W/(m²·K) | W/K |
| `H_tr,ms` | coupling between mass node and surface node; `h_ms` = 9.1 W/(m²·K) | W/K |
| `H_tr,op` | opaque transmission coefficient, ground included (ENV-03, ENV-04) | W/K |
| `H_tr,em` | coupling between mass node and outdoors | W/K |
| `H_tr,w` | windows and doors (ENV-03) | W/K |
| `C_m` | internal heat capacity | J/K |
| `A_m` | effective mass area | m² |
| `rho_a c_a` | volumetric heat capacity of air, 1200 (S1 clause 9.3.1) | J/(m³·K) |
| `q_ve` | outdoor air flow into the zone | m³/s |

| Class | `C_m` (J/K) | `A_m` (m²) |
|---|---|---|
| very light | 80 000 × `A_f` | 2.5 × `A_f` |
| light | 110 000 × `A_f` | 2.5 × `A_f` |
| medium | 165 000 × `A_f` | 2.5 × `A_f` |
| heavy | 260 000 × `A_f` | 3.0 × `A_f` |
| very heavy | 370 000 × `A_f` | 3.5 × `A_f` |

Default class: medium as expected, light as low, heavy as high, for every building type. The standard gives the classes but no mapping to US construction types, so no finer mapping is used (section 10). S9 uses 45 Wh/(m²·K) = 162 000 J/(m²·K) as its single standard value, which is the medium class.

Validity: `H_tr,op < H_tr,ms` is required (otherwise `H_tr,em` is negative). `H_tr,ms` is at least 22.75 × `A_f` W/K, so this fails only for an absurd envelope; raise an error if it does. If `H_tr,op` = 0 (a unit with no exterior opaque surface) set `H_tr,em` = 0.

Primary: S1 clause 7.2.2.2 eq. (9) with `h_is` = 3.45 and the ratio 4.5; clause 12.2.2 eqs. (63) and (64) with `h_ms` = 9.1; clause 12.3.1.2 Table 12. All opened. Eq. (63) is illegible in S1 and was taken from S3 (CEA `calc_h_em`: `1 / (1/h_op_m - 1/h_mc)`). Second source: S3 tsib constants (`h_is` 3.45, `lambda_at` 4.5, `h_ms` 9.1, `f_Am` 2.5, 2.5, 2.5, 3.0, 3.5) and S2 (`h_tr_ms = 9.1 * mass_area`, `h_tr_is = total_internal_area * 3.45`, 165 000 J/(m²·K) for medium).

Note on S2: it sets `H_tr,em = U_walls * A_walls` directly and skips eq. (63). That is a simplification in that code, not the standard. This spec uses eq. (63).

Worked example (150 m² house, medium class, envelope of ENV-03 and ENV-04, 375 m³ at 0.5 air changes per hour): `A_m` = 375 m², `A_tot` = 675 m², `C_m` = 2.475e7 J/K, `H_tr,is` = 2328.75 W/K, `H_tr,ms` = 3412.50 W/K, `H_tr,op` = 133.26 W/K, `H_tr,em` = 1/(1/133.26 − 1/3412.5) = 138.675 W/K, `H_tr,w` = 58.00 W/K, `H_ve` = 1200 × 0.5 × 375 / 3600 = 62.500 W/K.

Tool: `zone_rc_parameters(floor_area_m2, h_tr_op_w_k, h_tr_w_w_k, mass_class="medium") -> {a_m_m2, a_tot_m2, c_m_j_k, h_tr_is_w_k, h_tr_ms_w_k, h_tr_em_w_k}`.

### ZON-02 Distribution of gains to the nodes

```
Phi_ia = 0.5 * Phi_int
Phi_m  = (A_m / A_tot) * (0.5 * Phi_int + Phi_sol)
Phi_st = (1 - A_m/A_tot - H_tr,w / (9.1 * A_tot)) * (0.5 * Phi_int + Phi_sol)
```

| Symbol | Meaning | Unit |
|---|---|---|
| `Phi_int` | sensible internal gain of the hour: occupants, lighting, plug loads, water-heater standby (sections 6, 7) | W |
| `Phi_sol` | solar gain of the hour: windows (section 4) plus opaque elements net of sky radiation (ENV-05) | W |
| `Phi_ia`, `Phi_st`, `Phi_m` | gain to the air node, the surface node and the mass node | W |

The three parts sum to slightly less than the total: the fraction `H_tr,w / (9.1 A_tot)` of the radiant part is treated as lost straight back through the glazing. `Phi_sol` may be negative at night (sky radiation); the same split applies.

Primary: S1 Annex C clause C.2, eqs. (C.1) to (C.3) (clause text opened; the factor 0.5, `A_t` and "9,1 A_t" are legible; equations taken from S2 `calc_heat_flow`). Second source: S3 tsib `gainAirNode` (0.5 × internal gain to air) and `gainSurNode` (the `1/h_ms/A_tot × U_window` loss term).

Worked example: `Phi_int` = 600 W, `Phi_sol` = 1500 W, parameters of ZON-01. `Phi_ia` = 300.0, `Phi_m` = (375/675) × 1800 = 1000.00, `Phi_st` = (1 − 0.5556 − 58/(9.1 × 675)) × 1800 = 783.00 W. Sum 2083.0 W of 2100 W; 17.0 W lost through glazing.

Tool: `distribute_gains(internal_w, solar_w, a_m_m2, a_tot_m2, h_tr_w_w_k) -> {phi_ia_w, phi_st_w, phi_m_w}`.

### ZON-03 Node temperatures for a given heating or cooling power

For one hour, with `Phi_HC` the power delivered to the air node (positive heating, negative cooling):

```
H_tr,1 = 1 / (1/H_ve + 1/H_tr,is)
H_tr,2 = H_tr,1 + H_tr,w
H_tr,3 = 1 / (1/H_tr,2 + 1/H_tr,ms)

Phi_mtot = Phi_m + H_tr,em * theta_e
           + H_tr,3 * ( Phi_st + H_tr,w * theta_e
                        + H_tr,1 * ( (Phi_ia + Phi_HC) / H_ve + theta_sup ) ) / H_tr,2

theta_m,t = ( theta_m,t-1 * ( C_m/3600 - 0.5 * (H_tr,3 + H_tr,em) ) + Phi_mtot )
            / ( C_m/3600 + 0.5 * (H_tr,3 + H_tr,em) )

theta_m   = ( theta_m,t + theta_m,t-1 ) / 2
theta_s   = ( H_tr,ms * theta_m + Phi_st + H_tr,w * theta_e
              + H_tr,1 * ( theta_sup + (Phi_ia + Phi_HC) / H_ve ) )
            / ( H_tr,ms + H_tr,w + H_tr,1 )
theta_air = ( H_tr,is * theta_s + H_ve * theta_sup + Phi_ia + Phi_HC ) / ( H_tr,is + H_ve )
theta_op  = 0.3 * theta_air + 0.7 * theta_s
```

| Symbol | Meaning | Unit |
|---|---|---|
| `theta_e` | outdoor air temperature of the hour | °C |
| `theta_sup` | temperature of the air entering the zone; equal to `theta_e` for infiltration and for ventilation without heat recovery | °C |
| `theta_m,t-1`, `theta_m,t` | mass temperature at the start and end of the hour (instantaneous) | °C |
| `theta_m`, `theta_s`, `theta_air`, `theta_op` | hour-average mass, surface, air and operative temperature | °C |
| `C_m / 3600` | capacity in W·h/K, because the time step is one hour | W·h/K |

Dimensional check: every term in `Phi_mtot` is W (W/K × °C, or W); numerator and denominator of `theta_m,t` are W and W/K. `theta_s` and `theta_air` likewise.

Validity: time step exactly one hour (Crank-Nicolson on the mass node). `H_ve` must be greater than zero; if the zone has no air exchange in an hour use a floor of 1e-6 W/K. All conductances may change from hour to hour (S1 clause 7.2.2.1).

Primary: S1 Annex C clause C.3, eqs. (C.4) to (C.12). Clause text opened; legible fragments match (`[(C_m/3600) − 0,5 × (H_tr,3 + H_tr,em)]`, the Crank-Nicolson statement, `0,3 × theta_air + 0,7 × theta_s` with the note on 3/8 and 5/8 weighting). The full equations were taken from S2 (`calc_phi_m_tot`, `calc_t_m_next`, `calc_t_m`, `calc_t_s`, `calc_t_air`, `h_tr_1`, `h_tr_2`, `h_tr_3`, `t_opperative`). Second source, independent derivation: the three node heat balances written directly and solved as a linear system (script `zon.py`, function `direct_solve`):

```
air:     H_ve (theta_sup - theta_air) + H_tr,is (theta_s - theta_air) + Phi_ia + Phi_HC = 0
surface: H_tr,is (theta_air - theta_s) + H_tr,w (theta_e - theta_s) + H_tr,ms (theta_m - theta_s) + Phi_st = 0
mass:    (C_m/3600) (theta_m,t - theta_m,t-1) = H_tr,ms (theta_s - theta_m) + H_tr,em (theta_e - theta_m) + Phi_m
```

The linear solve and the Annex C closed form agree to all printed digits in every case below, which confirms the transcription term by term.

Worked example: see ZON-04.

Tool: `rc_step(theta_m_prev_c, t_out_c, t_supply_c, phi_ia_w, phi_st_w, phi_m_w, phi_hc_w, h_ve_w_k, params) -> {theta_m_end_c, theta_m_c, theta_s_c, theta_air_c, theta_op_c}`.

### ZON-04 Hourly heating and cooling need with setpoints and capacity

```
1. Free-floating:  run ZON-03 with Phi_HC = 0                  -> theta_air,0
   if  theta_set,H <= theta_air,0 <= theta_set,C :  Phi_HC,nd = 0, keep this state, stop.
2. Choose the setpoint:  theta_set = theta_set,H if theta_air,0 < theta_set,H, else theta_set,C.
   Run ZON-03 with Phi_HC,10 = 10 * A_f                         -> theta_air,10
   Phi_HC,un = Phi_HC,10 * (theta_set - theta_air,0) / (theta_air,10 - theta_air,0)
3. Capacity:  Phi_HC,nd = min( max(Phi_HC,un, -Phi_C,max), Phi_H,max )
4. Run ZON-03 with Phi_HC,nd for the final temperatures. theta_m,t carries to the next hour.
```

| Symbol | Meaning | Unit |
|---|---|---|
| `theta_set,H`, `theta_set,C` | heating and cooling setpoint of the hour, on air temperature (`DEF-08`) | °C |
| `Phi_HC,un` | unrestricted need to hold the setpoint | W |
| `Phi_H,max`, `Phi_C,max` | available heating and cooling capacity, positive numbers; infinite if unknown | W |
| `Phi_HC,nd` | actual need of the hour, positive heating, negative cooling | W |

The zone response is linear in `Phi_HC`, so two evaluations fix the line exactly; step 2 is exact, not an approximation. When capacity limits, the air temperature drifts past the setpoint and the result of step 4 gives it. A thermostat setback or a schedule is expressed only through hourly `theta_set,H` and `theta_set,C`. "Heating off" is `theta_set,H` = −50; "no cooling system" is `theta_set,C` = +80.

Year run: start with `theta_m` = 20 °C, simulate the last 14 days of December of the typical year as warm-up, discard them, then run 8760 hours. (The mass time constant `C_m / (3600 (H_tr,3 + H_tr,em))` is one to four days for these buildings, so 14 days removes the start value. This is an implementation rule, not from the standard.) Hourly outputs of the zone model, one value per hour of the year (8760), exposed to the other physics files and to the server:

| Output | Meaning | Unit | Used by |
|---|---|---|---|
| `theta_air_c` | zone air temperature, hour average | °C | physics 03 CMF-01, CMF-04 (`T_i`) |
| `theta_s_c` | surface-node temperature (a mix of air and mean radiant temperature) | °C | diagnostics |
| `theta_op_c` | operative temperature, `0.3 theta_air + 0.7 theta_s` | °C | physics 03 CMF-03 as a zone-level fallback |
| `theta_m_c` | mass temperature at the end of the hour | °C | state carried to the next hour |
| `phi_hc_w` | heating (+) or cooling (−) need | W | section 5 |
| `mode` | `"heating"` if `phi_hc_w` > 0, `"cooling"` if < 0, `"off"` if 0 | - | physics 03 (clothing level and comfort season), section 5 |
| `q_ve_m3_s` | outdoor air flow used in the hour | m³/s | INF-07, diagnostics |
| `phi_int_w`, `phi_sol_w` | internal and solar gains used | W | diagnostics, LGT-03 |

Summed outputs: annual and monthly heating and cooling need in kWh, and the largest hourly values as `peak_heating_w` and `peak_cooling_w`.

Primary: S1 Annex C clause C.4.2, steps 1 to 4 and eq. (C.13) (clause text opened: the response is "a linear function of Phi_HC,nd" fixed "for two values"; the four cases with and without sufficient power are described). Equation taken from S2 `calc_energy_demand` and `calc_energy_demand_unrestricted`. Second source: the direct linear solve of ZON-03 with `theta_air` fixed at the setpoint and `Phi_HC` as an unknown.

Worked example 1, reproduction of published test values (S2 `tests/testRCmodel.py`; zone `A_f` = 34.3 m², `A_m` = 85.75, `A_tot` = 142.38, `H_tr,w` = 14.85, `H_tr,em` = 0.338 as S2 defines it, `H_ve` = 70.887 W/K, `C_m` = 5 659 500 J/K, setpoints 20 and 26 °C, capacity 12 W/m² = 411.6 W):

| Case | `theta_e` | `theta_m,t-1` | `Phi_int` | `Phi_sol` | This spec: `Phi_HC,nd`, `theta_m` | Published in S2 | Direct linear solve |
|---|---|---|---|---|---|---|---|
| no demand | 10 | 22 | 10 | 2000 | 0 W, 22.33 | 0, 22.33 | n/a |
| cooling | 25 | 24 | 10 | 4000 | −264.75 W, 25.15 | −264.75, 25.15 | −264.75, 25.15 |
| heating | 10 | 20 | 10 | 2000 | 328.09 W, 20.46 | 328.09, 20.46 | 328.09, 20.46 |
| cooling at capacity | 30 | 25 | 10 | 5000 | −411.60 W, 26.49 | −411.6, 26.49 | n/a |

Worked example 2 (house of ZON-01, setpoints 20 and 25 °C, unlimited capacity):

- Cooling hour: `theta_e` = 34, `theta_m,t-1` = 26, `Phi_int` = 600, `Phi_sol` = 1500. Result `Phi_HC,nd` = −2888.8 W, `theta_m,t` = 26.1926, `theta_s` = 25.870, `theta_air` = 25.000, `theta_op` = 25.609 °C. Direct solve: −2888.8 W, 26.1926, 25.870.
- Heating hour: `theta_e` = 5, `theta_m,t-1` = 19, `Phi_int` = 600, `Phi_sol` = 0. Result 2377.0 W, `theta_m,t` = 18.8947, `theta_s` = 19.253. Direct solve: 2377.0 W, 18.8947.

Tool: `solve_hour(theta_m_prev_c, t_out_c, internal_w, solar_w, setpoint_heat_c, setpoint_cool_c, max_heat_w, max_cool_w, h_ve_w_k, params, t_supply_c=None) -> {phi_hc_w, theta_m_end_c, theta_air_c, theta_op_c}` and `simulate_year(weather, gains, schedules, params) -> {heating_need_kwh, cooling_need_kwh, monthly, hourly, peak_heating_w, peak_cooling_w}`.

### ZON-05 Steady-state identity (unit test, not a tool)

With constant outdoor temperature, no gains and the air held at the setpoint, the hourly model must converge to

```
Phi_HC = H_eff * (theta_set - theta_e)
H_eff  = H_ve + 1 / ( 1/H_tr,is + 1 / ( H_tr,w + 1 / (1/H_tr,ms + 1/H_tr,em) ) )
```

This follows from the network topology alone (series and parallel conductances seen from the air node). It is a strict test of the implementation.

`H_eff` is lower than the plain sum `H_tr,op + H_tr,w + H_ve`, because the air-to-surface coupling `H_tr,is` sits in series with the envelope and the thermostat controls air temperature. This is a property of the ISO model, not an error.

Worked example (house of ZON-01, `theta_e` = 5, setpoint 20): closed form `H_eff` = 239.2440 W/K, 3588.660 W. The hourly model iterated for 3000 hours gives 3588.660 W. Plain sum for comparison: 253.760 W/K, 3806.4 W (6 % higher).

### ZON-06 Monthly quasi-steady cross-check (the degree-day sanity test)

A degree-day estimate is a steady heat balance on the mean temperature difference: `H * (theta_set - theta_e,mean) * hours` equals `24 * H * HDD` when no hour is above the base. The ISO 13790 monthly method is that balance with a sourced rule for how much of the gains is useful, so it is used as the cross-check.

```
Q_ht   = H_tot * (theta_set,H - theta_e,m) * t / 1000              kWh, t in hours
Q_gn   = (Phi_int,mean + Phi_sol,mean) * t / 1000                  kWh
gamma  = Q_gn / Q_ht
tau    = (C_m / 3600) / H_tot                                      h
a      = 1.0 + tau / 15
eta    = (1 - gamma^a) / (1 - gamma^(a+1))    if gamma > 0 and gamma != 1
eta    = a / (a + 1)                          if gamma == 1
Q_H,nd = Q_ht - eta * Q_gn                                         kWh for the month, not below 0
```

| Symbol | Meaning | Unit |
|---|---|---|
| `H_tot` | `H_tr,op + H_tr,w + H_ve` with a month-mean `H_ve` | W/K |
| `theta_e,m` | month-mean outdoor temperature | °C |
| `t` | hours in the month | h |
| `gamma` | gain-to-loss ratio | - |
| `tau` | building time constant | h |
| `a` | numerical parameter; reference values 1.0 and 15 h for the monthly method | - |
| `eta` | gain utilisation factor | - |

The matching cooling formula (loss utilisation factor, S1 clause 12.2.1.2) was not legible in S1 and is not used; see section 10. The cooling cross-check is ZON-05 plus the published test values of ZON-04.

Validity: continuous heating at a constant setpoint. Apply only to months where `Q_ht` is positive; in any other month set `Q_H,nd` = 0.

Use: a test, not a tool the agent calls. For each golden property, the sum over months of `Q_H,nd` must be within 15 % of the hourly model's annual heating need when both run at a constant setpoint. A larger gap means a wiring error (a wrong area, a missing surface, a unit slip), which is what this test is for.

Primary: S1 clauses 7.2.1.1 (eq. 3), 7.2.1.3 (eqs. 7 and 8), 12.2.1.1 (eqs. 52 to 56) and Table 9 (1,0 and 15 h monthly; 0,8 and 30 h seasonal), clause text and table opened, equations illegible. Second source: S9 section 2.5, eqs. (11) to (14), which print `eta = (1 - gamma^a)/(1 - gamma^(a+1))`, `gamma = Q_gn/Q_ht`, `a = a_0 + tau/tau_0` and `tau = c_m A / (H_tr + H_ve)` (read from the PDF page image as well as the text).

Worked example (house of ZON-01, January, 744 h, `theta_e,m` = 10 °C, setpoint 20 °C, mean internal gain 600 W, mean solar gain 250 W): `H_tot` = 253.76 W/K, `tau` = 27.09 h, `a` = 2.806, `Q_ht` = 1888.0 kWh, `Q_gn` = 632.4 kWh, `gamma` = 0.3350, `eta` = 0.9686, `Q_H,nd` = 1275.4 kWh. The hourly model run on the same month with a ±6 K daily temperature swing and the same mean gains gives 1191.4 kWh, 6.6 % lower, inside the 15 % tolerance. Most of the gap is the `H_eff` effect of ZON-05.

## 3. INF: infiltration and ventilation

Additional source keys:

| Key | Source |
|---|---|
| S12 | Sherman and Grimsrud (1980), *Measurement of Infiltration Using Fan Pressurization and Weather Data*, Lawrence Berkeley Laboratory report LBL-10852 (OSTI 6345084). The original paper of the model; read from the scanned pages. |

### INF-01 Air flow to heat transfer coefficient

```
H_ve = rho_a c_a * q_ve          rho_a c_a = 1200 J/(m³·K)
q_ve = n * V / 3600              when the flow is given as air changes per hour
```

| Symbol | Meaning | Unit |
|---|---|---|
| `q_ve` | outdoor air volume flow entering the zone in the hour (infiltration plus ventilation, combined by INF-04) | m³/s |
| `n` | air change rate | 1/h |
| `V` | zone air volume (`Zone.volume_m3`) | m³ |
| `H_ve` | ventilation heat transfer coefficient, used in ZON-03 | W/K |

Validity: sensible heat only; supply at outdoor temperature. With heat recovery of efficiency `eta_hr` on a balanced flow, multiply that flow by `(1 - eta_hr)` (S1 clause 9.3.1 calls this the adjustment factor `b_ve`).

Primary: S1 clause 9.3.1 (opened: "the heat capacity of air per volume = 1200 J/(m³·K)"). Second source: S9, which uses 0.34 Wh/(m³·K) = 1224 J/(m³·K), 2 % higher.

Worked example: `V` = 375 m³, `n` = 0.5 1/h. `q_ve` = 0.05208 m³/s, `H_ve` = 62.50 W/K. Second route: (1200/3600) × 0.5 × 375 = 62.50 W/K.

Tool: `ventilation_coefficient(flow_m3_s) -> h_ve_w_k`.

### INF-02 Blower-door leakage to effective leakage area

```
Q_50 = ACH50 * V / 3600
Q_4  = Q_50 * (4 / 50)^n
A_L  = Q_4 * sqrt( rho / (2 * 4) )
```

| Symbol | Meaning | Unit |
|---|---|---|
| `ACH50` | air changes per hour at 50 Pa (`DEF-04`) | 1/h |
| `Q_50`, `Q_4` | leakage flow at 50 Pa and at the 4 Pa reference pressure | m³/s |
| `n` | flow exponent of the power law `Q = C dP^n`; 0.65 expected, 0.60 to 0.70 as the range | - |
| `rho` | air density, 1.2 | kg/m³ |
| `A_L` | effective leakage area at 4 Pa | m² |

`Systems.infiltration_ach` in the contract is a natural air change rate. To keep one meaning, the registry key `infiltration.ach50` holds the blower-door value and INF-03 produces the hourly natural rate; `Systems.infiltration_ach` reports the annual mean of that result (section 12).

Validity: single-family houses and individual dwelling units. For an apartment unit, use only the leakage to outdoors: `ACH50_unit = ACH50 * T`, where `T` is the exposed share of the unit's enclosing surface (exterior walls, plus roof or ground floor where the unit has them, over all six sides) (S10 Table 14).

Primary: S12 Appendix II, eqs. (II.1) to (II.3) (opened: `Q = A sqrt(2 dP / rho)`, `A = Q(dP_r) sqrt(rho / (2 dP_r))` at the 4 Pa reference pressure, power law for extrapolation). Second source: S11 section on infiltration ("converted to a pressure of 0.016 in. w.c. (4 Pa), assuming a flow exponent of 0.65") and S8 Input Output Reference, `ZoneInfiltration:FlowCoefficient` ("the pressure exponent generally lies between 0.6 and 0.7").

Worked example: `ACH50` = 7, `V` = 375 m³, `n` = 0.65. `Q_50` = 0.7292 m³/s, `Q_4` = 0.14120 m³/s, `A_L` = 0.05469 m² = 546.9 cm². With `n` = 0.60: 620.5 cm²; with 0.70: 482.0 cm². Second route: 1545 cfm at 50 Pa gives 84.8 in², a ratio of 0.0549 in² per cfm50, which is the 0.055 rule of thumb used by US auditors.

Tool: `leakage_area_from_ach50(ach50, volume_m3, exponent=0.65) -> leakage_area_m2`.

### INF-03 Hourly infiltration (Sherman-Grimsrud, the ASHRAE "basic" model)

```
Q_inf = (A_L,cm2 / 1000) * sqrt( C_s * |theta_i - theta_e| + C_w * v^2 )
```

| Symbol | Meaning | Unit |
|---|---|---|
| `Q_inf` | infiltration flow | m³/s |
| `A_L,cm2` | effective leakage area at 4 Pa, in cm² (INF-02 result × 10⁴) | cm² |
| `C_s` | stack coefficient | (L/s)²/(cm⁴·K) |
| `C_w` | wind coefficient | (L/s)²/(cm⁴·(m/s)²) |
| `theta_i`, `theta_e` | zone air and outdoor air temperature | °C |
| `v` | wind speed of the hour from the weather file | m/s |

| Stories | 1 | 2 | 3 |
|---|---|---|---|
| `C_s` | 0.000145 | 0.000290 | 0.000435 |

| Shelter class | Description | `C_w`, 1 story | 2 stories | 3 stories |
|---|---|---|---|---|
| 1 | no obstructions or local shielding | 0.000319 | 0.000420 | 0.000494 |
| 2 | isolated rural house | 0.000246 | 0.000325 | 0.000382 |
| 3 | other buildings across the street | 0.000174 | 0.000231 | 0.000271 |
| 4 | urban buildings on larger lots | 0.000104 | 0.000137 | 0.000161 |
| 5 | buildings immediately adjacent | 0.000032 | 0.000042 | 0.000049 |

Default shelter class 4 for both cities; class 3 as the high-infiltration case and class 5 as the low case. Stories from `PropertySummary.floor_count`, capped at 3. Shelter class and exponent are assumption keys (`infiltration.shelter_class`, `infiltration.exponent`).

Use in the hourly model: `theta_i` is taken as the previous hour's `theta_air` to avoid an iteration. The dependence is weak (square root), so the lag error is small.

Validity: detached and attached houses up to three stories. Not for offices (INF-05). Not for a mid-rise apartment unit: use the table with the unit's own height (1 story) and the exposed-surface scaling of INF-02.

Primary: S8 Engineering Reference "Infiltration by Effective Leakage Area" and Input Output Reference `ZoneInfiltration:EffectiveLeakageArea` (opened; both give the equation and attribute the coefficient tables to the ASHRAE Handbook of Fundamentals 2001 chapter 26 and 2005 chapter 27, which were not opened). Second source: S12 eqs. (3.1), (3.2) and (7): `Q = A_0 sqrt(f_s*² dT + f_w*² v²)` with `f_s* = ((1 + R/2)/3) (1 − X²/(2 − R)²)^(3/2) sqrt(g H / T)`.

Coefficient check from the original paper: with `R` = 0.5, `X` = 0, `H` = 2.5 m, `T` = 295 K, `f_s*` = 0.1201 m/(s·K^0.5). In the handbook units `C_s = (0.1 f_s*)²` = 0.000144, against the tabulated 0.000145 for one story. The stack table is therefore the original model at 2.5 m per story.

Worked example: `A_L` = 546.9 cm², one story, shelter class 4.

| `theta_i − theta_e` | `v` | `Q_inf` | air changes per hour (375 m³) |
|---|---|---|---|
| 15 K | 3.0 m/s | 0.03050 m³/s | 0.293 |
| 8 K | 4.0 m/s | 0.02906 m³/s | 0.279 |
| 0 K | 2.0 m/s | 0.01115 m³/s | 0.107 |

Second route for the first row, original S12 form in SI with `A_0` = 0.05469 m², `f_s*` = 0.1201 and `f_w*` = sqrt(0.000104)/0.1: 0.03045 m³/s (0.2 % apart, from the rounding of `C_s`).

Tool: `infiltration_flow_sg(leakage_area_m2, t_in_c, t_out_c, wind_m_s, stories=1, shelter_class=4) -> flow_m3_s`.

### INF-04 Combining infiltration with mechanical ventilation

```
Q_bal   = min(Q_supply, Q_exhaust)
Q_unbal = |Q_supply - Q_exhaust|
q_ve    = Q_bal + sqrt( Q_unbal^2 + Q_inf^2 )
```

| Symbol | Meaning | Unit |
|---|---|---|
| `Q_supply`, `Q_exhaust` | mechanical supply and exhaust flow of the hour | m³/s |
| `Q_bal`, `Q_unbal` | balanced and unbalanced parts of the mechanical flow | m³/s |
| `Q_inf` | natural infiltration (INF-03) | m³/s |
| `q_ve` | total outdoor air flow for INF-01 | m³/s |

An unbalanced fan shifts the pressure of the house, so its flow and the natural infiltration do not simply add. Homes: existing homes are assumed to have no whole-house mechanical ventilation (`Q_supply = Q_exhaust = 0`) unless the user says otherwise; intermittent bath and kitchen exhaust is neglected.

Primary: S12, section "Superposition law", eq. (13) (opened: balanced flow adds simply, unbalanced flow adds in quadrature with the stack and wind flows). Second source: S10 section 2.1.6 ("whole-house mechanical ventilation air shall be added to the natural infiltration rate in quadrature").

Worked example: `Q_inf` = 0.03050 m³/s, exhaust-only fan 0.025 m³/s. `q_ve` = sqrt(0.025² + 0.0305²) = 0.03944 m³/s; a plain sum would give 0.05550 m³/s.

Tool: `combine_air_flows(infiltration_m3_s, supply_m3_s=0.0, exhaust_m3_s=0.0) -> flow_m3_s`.

### INF-05 Office outdoor air and infiltration

```
Q_oa        = N_occ * q_person                         during occupied (HVAC-on) hours, else 0
Q_inf,off   = I_75 * (4 / 75)^0.65 * A_env / 1000      HVAC off
Q_inf,on    = 0.25 * Q_inf,off                         HVAC on
q_ve        = Q_oa + Q_inf
```

| Symbol | Meaning | Unit |
|---|---|---|
| `N_occ` | design occupant count. From `Systems.occupants` when CoStar tenancy data gives employees; otherwise `A_f / 18.59` | persons |
| `q_person` | outdoor air per person, 0.00944 (20 cfm) | m³/s |
| `I_75` | envelope leakage at 75 Pa per unit above-grade envelope area: 7.5 for buildings built in 2004 or earlier, 2.0 from 2005 | L/(s·m²) |
| `A_env` | above-grade exterior wall plus roof area of the zone | m² |

The design occupant count sets ventilation; the hourly occupancy schedule (`DEF-09`) does not modulate it (no demand-controlled ventilation assumed).

Validity: mechanically ventilated commercial buildings. The infiltration rule is the one used for the DOE reference buildings and is deliberately simple; its own authors say a fixed rate "may not be realistic for hourly modeling" but represents the annual effect. The source gives a mean leakage (Persily 1998, 139 buildings, "wide scatter") and no spread, so carry `I_75` as low 2.0, expected 7.5, high 7.5 for pre-2004 buildings.

Primary: S11 section 5.1.2 and Tables 5 and 6 (office: 18.59 m²/person, 9.44 L/s per person, 0.51 L/(s·m²) total, from ASHRAE 62-1999) and the infiltration section (7.5 and 2.0 L/(s·m²) at 75 Pa, exponent 0.65 to 4 Pa, 25 % with the ventilation system running). Second source: none independent was opened for the office rates; ASHRAE 62.1 itself is paywalled. Listed in section 10 as single-sourced.

Worked example: office suite `A_f` = 500 m², no tenant data. `N_occ` = 26.9, `Q_oa` = 0.2539 m³/s (0.508 L/(s·m²), matching the table's 0.51), `H_ve` from ventilation alone = 304.7 W/K. Envelope 1036.6 m² (two sets of four 22.36 m × 3 m walls plus the roof, as the printed values need (four walls plus the roof alone is 768.3 m²)), pre-2004: leakage at 4 Pa = 7.5 × 0.1488 = 1.1159 L/(s·m²); `Q_inf,off` = 1.1567 m³/s, `Q_inf,on` = 0.2892 m³/s.

Tool: `office_outdoor_air(occupants, envelope_area_m2, hvac_on: bool, leakage_75pa_l_s_m2=7.5) -> flow_m3_s`.

### INF-06 Economizer

An economizer raises the outdoor air flow above the minimum when outdoor air can do the cooling. Fixed dry-bulb control, as an hourly rule on top of ZON-04:

```
1. Solve the hour with q_ve = q_min (INF-05).                       -> Phi_HC,min
2. If Phi_HC,min >= 0 (no cooling need), or theta_e > theta_limit,
      or theta_e >= theta_set,C:                                    keep step 1.
3. Otherwise solve the hour with q_ve = q_max.                      -> Phi_HC,max
      If Phi_HC,max < 0:  cooling need = Phi_HC,max at q_max  (economizer fully open, compressor makes up the rest).
      Else: find q in [q_min, q_max] by bisection so that the free-floating air temperature equals theta_set,C;
            cooling need = 0 at that q.
```

| Symbol | Meaning | Unit |
|---|---|---|
| `q_min` | minimum outdoor air flow (INF-05) | m³/s |
| `q_max` | maximum outdoor air flow, the unit's supply air flow. If unknown: 0.005 m³/s per m² of floor (section 10: this default is an engineering figure, not sourced) | m³/s |
| `theta_limit` | high-limit dry-bulb temperature above which the economizer returns to minimum | °C |

The `HVAC_ECON` measure is the difference between a year run without this rule and a year run with it. Fan energy is unchanged in this model (the supply fan runs either way). In Houston the humid outdoor air limits the benefit: outdoor air that is cool but humid adds latent load (INF-07), which must be charged against the saving, and a dry-bulb economizer saves less than the sensible calculation suggests. Report the saving net of INF-07.

Validity: single-zone packaged units. No treatment of damper leakage, sensor error or a stuck damper (a common real fault; the measure description should say that a functional test is part of the work).

Primary: S8 Input Output Reference `Controller:OutdoorAir`, fields "Economizer Control Type" and "Economizer Maximum Limit Dry-Bulb Temperature" (opened: with `FixedDryBulb` the outdoor air flow goes to minimum when outdoor temperature exceeds the limit; otherwise it modulates between minimum and maximum). Second source: S1 clause 7.2.2.1, which allows every input of the hourly model, `H_ve` included, to change each hour. The bisection step is an implementation of "modulate to hold the setpoint" and has no formula of its own. `theta_limit` values required by energy codes were not opened; see section 10.

Worked example (script `econ.py`): office suite of INF-05, `A_f` = 500 m², medium mass, walls 268 m² with 30 % glazing (wall U 0.852, window U 6.93), roof 500 m² at 0.375, so `H_tr,op` = 347.5 and `H_tr,w` = 557.8 W/K; `q_min` = 0.2539 + 0.2892 = 0.5431 m³/s, `q_max` = 2.5 m³/s; `theta_m,t-1` = 24.5 °C, internal gain 12 000 W, solar gain 6000 W, setpoints 21 and 24 °C, `theta_limit` = 21 °C.

| `theta_e` | Without economizer | With economizer |
|---|---|---|
| 15.0 °C | −2445.3 W | 0 W at `q` = 0.7695 m³/s, air 24.000 °C |
| 20.5 °C | −7568.1 W | 0 W at `q` = 2.3450 m³/s, air 24.000 °C |
| 30.0 °C | −16 416.6 W | −16 416.6 W at `q_min` (above the limit) |

Tool: `solve_hour_with_economizer(..., q_min_m3_s, q_max_m3_s, limit_c) -> {phi_hc_w, flow_m3_s, theta_air_c}`.

### INF-07 Latent load of outdoor air

```
Phi_lat = rho * q_ve * h_fg * max(0, w_e - w_i)
```

| Symbol | Meaning | Unit |
|---|---|---|
| `Phi_lat` | latent cooling load from outdoor air in an hour with cooling | W |
| `rho` | air density, 1.2 | kg/m³ |
| `h_fg` | enthalpy of vaporisation of water, 2.50e6 | J/kg |
| `w_e` | outdoor humidity ratio of the hour, from the weather file | kg/kg |
| `w_i` | indoor humidity ratio held by the cooling coil; 0.0093 (24 °C, 50 % relative humidity at sea level) | kg/kg |

Count `Phi_lat` only in hours where the zone model returns a cooling need, and add it to the cooling need before the HVAC conversion of section 5. Occupant latent gain (`DEF-09`) is added the same way. Without this term the Houston cooling energy is understated; in Los Angeles it is small.

Validity: a steady moisture balance with a fixed indoor humidity. No moisture storage, no dehumidification when the coil is off.

Primary: S8 Engineering Reference "Moisture Predictor-Corrector" (opened: the zone moisture balance contains the infiltration term `m_inf (W_inf − W_z)` and the system term). The conversion from a moisture flow to a load is the product with `h_fg`. Second source: not opened; the ASHRAE Handbook writes the same expression with a lumped constant. The value of `h_fg` and the indoor humidity ratio are standard property values that were not checked against an opened table: see section 10, tier B.

Worked example: `q_ve` = 0.05 m³/s, `w_e` = 0.0180, `w_i` = 0.0093. `Phi_lat` = 1.2 × 0.05 × 2.50e6 × 0.0087 = 1305 W. The sensible load of the same air at 8 K difference is 480 W, so in humid hours the latent part is the larger one. (Script value 1305.5 W with 2.501e6.)

Tool: `outdoor_air_latent_load(flow_m3_s, w_out_kg_kg, w_in_kg_kg=0.0093) -> load_w`.

## 4. WIN: window solar gain

Additional source key:

| Key | Source |
|---|---|
| S13 | NREL, *OpenStudio-HPXML documentation*, "Workflow Inputs" (`https://openstudio-hpxml.readthedocs.io/en/latest/workflow_inputs.html`). The input reference of the engine behind ResStock and the RESNET-accredited rating tools; it states each default and the standard it comes from. |

### WIN-01 Solar gain through a window

```
Phi_sol,w = F_sh,ob * F_sh,gl * F_w * SHGC * A_w * I_sol  -  F_r * R_se * U_w * A_w * h_r * dtheta_er
```

| Symbol | Meaning | Unit |
|---|---|---|
| `A_w` | whole window area, frame included: `Opening.width_m × Opening.height_m` | m² |
| `SHGC` | whole-window solar heat gain coefficient at normal incidence, as rated by NFRC (`Surface.shgc`) | - |
| `F_w` | correction from normal incidence to the time-average angle of incidence, 0.90 | - |
| `F_sh,gl` | reduction by movable shading, films and screens (WIN-02), 1 if none | - |
| `F_sh,ob` | reduction by external obstacles (overhangs, neighbours, trees) from the shading entries (SHD) of physics 01; 1 if not computed | - |
| `I_sol` | total (beam plus diffuse plus ground-reflected) irradiance on the window plane: physics 01 IRR-10, for the window's tilt and true azimuth | W/m² |
| `F_r`, `R_se`, `h_r`, `dtheta_er` | sky term, exactly as in ENV-05 (`F_r` = 0.5 for a vertical window) | |
| `U_w` | window U-value | W/(m²·K) |

The result is `Phi_sol` for ZON-02, summed over all windows and added to the opaque gain of ENV-05.

Two differences from the ISO form, both deliberate:

1. ISO 13790 eq. (44) multiplies by `(1 − F_F)`, the glazed fraction, because the European `g` value is for the glass alone. The US `SHGC` is a whole-product rating that already includes the frame (S13: "full-assembly NFRC solar heat gain coefficient"). So `(1 − F_F)` is **not** applied. If a glass-only value is ever supplied, multiply by `(1 − F_F)` with `F_F` = 0.20 to 0.30 (S1 clause 11.4.5 note).
2. Incidence-angle dependence is **not** modelled hour by hour. The constant `F_w` = 0.90 stands for it, as ISO 13790 specifies for the hourly method. S8 documents why an hourly angular model built from U and SHGC alone is "inherently approximate": products with the same SHGC have different angular behaviour. Carry `F_w` as 0.85 / 0.90 / 0.95.

Window position and size: measured openings first (`source = measured`). If the model has no window-type openings, use the vision reading of count and size (`source = vision`) and widen the area range to ±30 % (`DEF-03`). Orientation is the azimuth of the wall edge that carries the opening, rotated by the georeference.

Primary: S1 clauses 11.3.2 (eq. 43), 11.3.3 (eq. 44), 11.4.2 (eq. 47, "in the absence of national values, the value for the correction factor is F_w = 0,90") and 11.4.3.2 ("for the simple hourly method the choice between g_gl and g_gl+sh shall be made each hour"), opened. Second source: S3 tsib, which computes window gain as irradiance × area × `(1 − F_f)` × `F_w` × `g` minus the same sky term; and S8 Engineering Reference "Simple Window Model" for the meaning and limits of U and SHGC as the only window inputs.

Worked example: `A_w` = 2.0 m², `SHGC` = 0.60, interior shading `F_sh,gl` = 0.70, no obstacles, `I_sol` = 500 W/m², `U_w` = 2.8, `eps` = 0.9. Solar part = 2.0 × 0.9 × 0.60 × 0.70 × 500 = 378.0 W. Second route through the effective collecting area: `A_sol` = 0.70 × (0.9 × 0.60) × 2.0 = 0.756 m², × 500 = 378.0 W. Sky term = 0.5 × 0.04 × 2.8 × 2.0 × 4.5 × 11 = 5.54 W. Net 372.5 W.

Tool: `window_solar_gain(area_m2, shgc, irradiance_w_m2, u_w_m2k, shading_factor=1.0, obstacle_factor=1.0, f_w=0.90, sky_form_factor=0.5) -> gain_w`.

### WIN-02 Shading, films and screens

```
F_sh,gl = F_int * F_ext
F_int   = f_cov * (C1 - C2 * SHGC) + (1 - f_cov)          interior shades, blinds, curtains
F_ext   = f_cov * C_ext + (1 - f_cov)                      exterior screen or applied film
```

| Symbol | Meaning | Unit |
|---|---|---|
| `f_cov` | fraction of the window covered during the hour or season; default 1.0 for blinds, screens and film, 0.5 for shades and curtains | - |
| `C1`, `C2` | interior attenuation coefficients, table below | - |
| `C_ext` | exterior coefficient: solar screen 0.30, applied solar film 0.70 | - |

| Interior device | `C1` | `C2` |
|---|---|---|
| light curtains | 0.84 | 0.42 |
| medium curtains | 0.94 | 0.37 |
| dark curtains | 0.98 | 0.25 |
| light shades | 0.82 | 0.42 |
| medium shades | 0.90 | 0.38 |
| dark shades | 0.98 | 0.33 |
| light blinds, closed | 0.78 | 0.47 |
| medium blinds, closed | 0.90 | 0.41 |
| dark blinds, closed | 0.98 | 0.25 |
| light blinds, half open | 0.93 | 0.38 |
| medium blinds, half open | 0.95 | 0.26 |
| dark blinds, half open | 1.00 | 0.19 |

Baseline for homes when nothing is observed: `F_int` = 0.70 all year (S10). Baseline for offices: 0.70 as well, carried as 0.5 / 0.7 / 1.0 (no office-specific value was opened).

Measures:

- `WIN_SHADE` interior: replace the baseline `F_int` with the value for the proposed device, in cooling-season hours only if the device is operable.
- `WIN_SHADE` exterior screen: `C_ext` = 0.30.
- `WIN_FILM`: `C_ext` = 0.70 as the default, or better, replace `SHGC` by the film manufacturer's rated SHGC for the glass type when it is known. A film also lowers useful winter gain; the zone model accounts for that when the factor is applied all year.
- `WIN_REPLACE`: new `U_w` and `SHGC` from `DEF-03`; both ENV-03 and WIN-01 change.

Validity: the interior coefficients describe closed or half-open devices on ordinary glazing. The lower the SHGC of the glass, the less an interior shade adds, which the `C2` term captures.

Primary: S13, sections "HPXML Interior Shading" and "HPXML Exterior Shading" (opened). It attributes the interior formula and coefficients to the ASHRAE Handbook of Fundamentals 2021, chapter 15, Table 14, and the exterior values 0.30 and 0.70 to the MulTEA Engineering Manual, Table A.3.4; neither original was opened. Second source: S10 section 4.2.2 for existing homes ("a constant interior shading multiplier of 0.7"), which sits inside the range the table gives; and S1 clause 11.4.3 for the structure (a separate transmittance with the shade in use, chosen each hour). The film and screen values are single-sourced (section 10, tier B).

Worked example at `SHGC` = 0.60: light blinds closed, 0.78 − 0.47 × 0.60 = 0.498; medium shades over half the window, 0.5 × (0.90 − 0.228) + 0.5 = 0.836; light curtains over half, 0.794. The window of WIN-01 with a film, the film's 0.70 multiplied with the interior factor 0.70 (the printed number needs both): 264.6 W; with an exterior screen: 113.4 W. Recomputed by script.

Tool: `shading_factor(interior_type=None, exterior_type=None, shgc, fraction_covered=None) -> factor`.

## 5. HVAC

Additional source keys:

| Key | Source |
|---|---|
| S14 | Cutler, Winkler, Kruis, Christensen, Brandemuehl, *Improved Modeling of Residential Air Conditioners and Heat Pumps for Energy Calculations*, NREL/TP-5500-56354, 2013 (OSTI 1219902). |
| S15 | Electronic Code of Federal Regulations, 10 CFR 430.32 (consumer products) and 10 CFR 431.92 and 431.97 (commercial package air conditioners), current text read 2026-11-13 and 2026-11-14. |
| S16 | Trane, *Engineers Newsletter* volume 55-4, "Energy Metrics for Unitary HVAC Equipment", August 2026. Open restatement of the AHRI 340/360 IEER definition. AHRI 340/360 itself refused download. |
| S17 | NREL, *ResStock Technical Reference Documentation* v3.3.0 and its distribution files; full entry in section 8. |

The zone model gives hourly sensible heating need and cooling need. The total cooling load on the equipment in an hour is

```
Q_cool = ( |Phi_HC,nd| + Phi_lat,oa + Phi_lat,occ ) / DSE_cool          for hours with Phi_HC,nd < 0
Q_heat =   Phi_HC,nd / DSE_heat                                         for hours with Phi_HC,nd > 0
```

with the latent terms of INF-07 and LGT-03 and the distribution efficiency of HVAC-08.

### HVAC-00 System type, and what is assumed when it is unknown

The system type decides which entries apply. It comes, strongest first, from the user, from interior vision (thermostat, registers, wall or window units, an air handler or furnace closet), from Vexcel roof-object detection (rooftop units), and last from the default below.

| Building | Default when the type is unknown | Entries | Source of the default |
|---|---|---|---|
| home with gas at the site | central split air conditioner with a gas furnace, ducted | HVAC-02, HVAC-03, HVAC-06, HVAC-08 | S10 Table 6 and benchmark (gas furnace and SEER 13 air conditioner where gas is available) |
| home without gas | ducted split heat pump | HVAC-02 to HVAC-05, HVAC-08 | S10 (heat pump where gas is not available) |
| apartment unit | as a home; `DSE` = 1 if no ducts outside the unit are seen | as above | S10 |
| office | packaged single-zone constant-volume unit with gas furnace | HVAC-02, HVAC-03 or HVAC-07, HVAC-06 | S11 Tables 29 and 30 (small office: furnace, packaged air-conditioning unit, single zone constant air volume) |

Efficiency for an unknown system follows `DEF-05`. Whether gas is at the site comes from the CoStar or listing record or the tariff lookup; if that is unknown too, run both home rows and carry the spread.

**No rooftop unit detected on an office** (the golden office is such a case: Vexcel counts no rooftop AC unit). Absence in the aerial view does not show there is no packaged equipment: units can sit on the ground, behind a parapet, in a mechanical room, or the suite can be served by a building-wide plant. Rule:

1. The baseline still uses the office default above for its efficiency class, because every air-cooled direct-expansion system of that vintage falls under the same efficiency tables. `hvac_type` is set to `"unknown"` and a `Flag` with key `hvac.system_type` and status `unknown` is raised.
2. `HVAC_RTU` and `HVAC_ECON` are returned with `applicable = false` and the reason "no packaged rooftop unit confirmed" unless interior vision or the user confirms a packaged unit serving the space. They are not silently evaluated on an assumed unit.
3. If vision indicates a central plant (fan-coil units, chilled-water piping, no furnace), this file has no chiller or boiler-plant model: the baseline uses the default efficiency with the range widened to −25 % / +25 % and a warning, and only load-side measures (envelope, lighting, plug, controls) are evaluated.
4. The uncertainty is a candidate question under the ask rule of the master spec, since it changes which measures appear.

### HVAC-01 Rating conversions

```
COP              = EER  * 0.293071            (EER in Btu/(W·h); 1 W = 3.412142 Btu/h)
COP_seasonal,c   = SEER * 0.293071
COP_seasonal,h   = HSPF * 0.293071
SEER2 = 0.95 * SEER      EER2 = 0.95 * EER      HSPF2 = 0.85 * HSPF       (ducted split systems)
SEER2 = SEER             EER2 = EER                                       (ductless)
eta_furnace      = AFUE                        (fraction, higher heating value basis)
```

`Systems.cooling_cop` and `Systems.heating_efficiency` in the contract hold the seasonal values in W/W (or the AFUE fraction). The original rating and its metric are kept in the assumption registry (`hvac.cooling_rating`, with unit `SEER`, `SEER2`, `EER` or `IEER`), because HVAC-02 to HVAC-07 need to know which metric it was.

Validity: the 2023 ratings (SEER2, EER2, HSPF2) come from a test with higher external static pressure, so the same unit rates lower. The factors are for split systems; a single-package factor was not opened, use the split value and note it.

Primary: unit conversion (exact). The 2023 factors: S13 ("converted to SEER2 using ANSI/RESNET/ICC 301-2022 Addendum C ... SEER2 = SEER × 0.95 if split system", "EER2 = EER × 0.95", "HSPF2 = HSPF × 0.85"); RESNET 301 itself was not opened. Second source, consistency only: S15 10 CFR 430.32(c)(5), where the 2023 national minimum for split air conditioners is 13.4 SEER2 and for split heat pumps 14.3 SEER2 and 7.5 HSPF2; 0.95 × 14 = 13.3 and 0.95 × 15 = 14.25, 0.85 × 8.8 = 7.48, so the factors map those minimums onto whole-number SEER and HSPF levels.

Worked example: SEER 10 → 2.931; SEER 13 → 3.810 (12.35 SEER2); SEER 14 → 4.103 (13.30 SEER2); SEER 16 → 4.689 (15.20 SEER2); HSPF 8.2 → 2.403 (6.97 HSPF2); EER 11 → 3.224. Recomputed by multiplying by 0.293071 and by dividing by 3.412142.

Tool: `rating_to_cop(value, metric: "SEER"|"SEER2"|"EER"|"EER2"|"HSPF"|"HSPF2"|"IEER"|"COP"|"AFUE", ducted=True) -> cop_or_fraction`.

### HVAC-02 Outdoor-temperature dependence and the 35 °C rating point (single-stage cooling)

```
f_T(theta_e) = g(theta_e) / g(35),      g(theta) = 0.69815 - 0.015397 * theta + 0.00070 * theta^2
EER_A        = SEER * f_T(27.78) / (1 - 0.5 * C_D)          f_T(27.78) = 0.7973
COP_A        = EER_A * 0.293071
```

| Symbol | Meaning | Unit |
|---|---|---|
| `f_T` | energy input ratio at outdoor temperature `theta_e`, relative to 35 °C (95 °F), at the rated indoor condition (entering wet bulb 19.44 °C) | - |
| `EER_A`, `COP_A` | net efficiency at the 35 °C rating point | Btu/(W·h), W/W |
| `C_D` | cycling degradation coefficient: 0.10 expected, 0.05 low, 0.25 high | - |

`g` is the single-stage air-conditioner EIR curve of S14 Table 17 (SI), `y = a + b T_ewb + c T_ewb² + d T_odb + e T_odb² + f T_ewb T_odb` with a = −0.30428, b = 0.11805, c = −0.00342, d = −0.00626, e = 0.00070, f = −0.00047, evaluated at `T_ewb` = 19.44 °C. The second line inverts the single-stage SEER definition `SEER = (1 − 0.5 C_D) × EER_B` (S14 eq. 16), where `EER_B` is the efficiency at the 27.78 °C (82 °F) test point.

If the unit's certified EER at 95 °F is known, use it directly and skip the second line.

Validity: single-stage, air-cooled split or packaged units, outdoor temperature 18 to 46 °C. The curve was fitted to compressor-plus-outdoor-fan input; applying it to a net rating that also contains indoor fan power is an approximation. The construction of `EER_A` makes the model return the nameplate SEER exactly at the SEER test condition, which removes most of that error for residential units. For rooftop units rated by IEER the same curve overstates part-load efficiency (worked example in HVAC-07), so HVAC-07 uses a different route.

Primary: S14 Table 17 and eq. (16), opened. Second source: two published SEER-to-EER mappings that the formula can be compared with: S14 Table 6 (the BEopt library) and the regression in S13 (`EER2 = 0.73 × SEER2 + 1.47` for single-stage units, "based on a regression analysis of ENERGY STAR products").

| SEER | `EER_A`, this entry (`C_D` = 0.10) | S14 Table 6 | S13 regression (as EER) |
|---|---|---|---|
| 13 | 10.91 | 11.1 | 11.04 |
| 14 | 11.75 | 12.0 | 11.77 |
| 15 | 12.59 | 13.0 | 12.50 |
| 16 | 13.43 | 14.0 | 13.23 |

All three agree within 4 %. Curve values: `g(35)` = 1.01676; `f_T` = 0.6592 at 20 °C, 0.7384 at 25, 0.7973 at 27.78, 0.8520 at 30, 1.0000 at 35, 1.1825 at 40, 1.3993 at 45 °C.

Tool: `cooling_eir_modifier(t_out_c) -> f_t` and `eer_a_from_seer(seer, cd=0.10) -> eer`.

### HVAC-03 Hourly cooling electricity (single-stage equipment)

```
PLR  = Q_cool / Q_cap
PLF  = 1 - C_D * (1 - PLR)
P_el = Q_cool * f_T(theta_e) / ( COP_A * PLF )
```

| Symbol | Meaning | Unit |
|---|---|---|
| `Q_cool` | total cooling load on the equipment in the hour | W |
| `Q_cap` | rated cooling capacity. If unknown: 1.2 × the largest hourly `Q_cool` of the baseline year (sizing factor 1.2, S11) | W |
| `PLR`, `PLF` | part-load ratio (capped at 1) and part-load factor | - |
| `P_el` | electric input, compressor and fans | W |

Validity: as HVAC-02. Capacity change with temperature is ignored in `PLR`; with `C_D` = 0.10 that changes `PLF` by under 1 %.

Primary: S14 eqs. for `EIR = EIR_rated × EIR_f(T)` and `PLF` as a function of `PLR`, and the statement `PLF(0.5) = 1 − 0.5 C_D`; opened. Second source: S8 Engineering Reference "Coils", single-speed DX cooling coil, which is the model S14 parameterises. Self-consistency test (run): at 27.78 °C and `PLR` = 0.5 the entry returns the SEER it was built from (10.000 for SEER 10).

Worked example: SEER 10 unit, `C_D` = 0.10: `EER_A` = 8.392, `COP_A` = 2.4596. Hour with `Q_cool` = 5000 W, `Q_cap` = 8000 W, `theta_e` = 38 °C: `f_T` = 1.1053, `PLR` = 0.625, `PLF` = 0.9625, `P_el` = 2334.6 W (effective COP 2.142). Second route, `P_el = Q × EIR_rated × f_T / PLF` with `EIR_rated = 1 / COP_A`: 2334.6 W.

Tool: `cooling_power_single_stage(load_w, t_out_c, cop_a, capacity_w, cd=0.10) -> power_w`.

### HVAC-04 Seasonal method (two-stage and variable-speed equipment, and the cross-check for HVAC-03)

```
E_cool = Q_cool,year / (SEER * 0.293071)                 kWh, with Q_cool,year in kWh
```

Use for two-stage and variable-speed units, whose part-load behaviour the single-stage curve does not describe, and as a sanity test for HVAC-03: for a single-stage unit the hourly result summed over the year should be within 20 % of this figure. The seasonal method assumes the national test-procedure climate. Houston has more hours above 35 °C than the test assumes and coastal Los Angeles fewer, so expect the hourly result to be higher than the seasonal one in Houston and lower in Los Angeles. Carry ±15 % on a result from this entry.

Primary: definition of SEER as seasonal cooling output over seasonal electric input (S15 10 CFR 430.32(c) uses the metric; the test procedure, appendix M to subpart B of part 430, was not opened). Second source: S14 section 6, which calculates SEER from rated values in the same way.

Worked example: 3000 kWh of cooling load. SEER 10: 1023.6 kWh. SEER 16: 639.8 kWh.

Tool: `seasonal_cooling_energy(cooling_load_kwh, seer) -> kwh`.

### HVAC-05 Heat pump heating

```
f_T,h(theta_e) = g_h(theta_e) / g_h(8.33),    g_h(theta) = 1.168249 - 0.030675 * theta + 0.000738 * theta^2
P_el           = Q_heat * f_T,h(theta_e) / COP_47                      hourly, when COP_47 is known
E_heat         = Q_heat,year / (HSPF * 0.293071)                       seasonal fallback
```

| Symbol | Meaning | Unit |
|---|---|---|
| `COP_47` | certified heating COP at 8.33 °C (47 °F) outdoor | W/W |
| `f_T,h` | heating energy input ratio relative to 8.33 °C, indoor 21.11 °C | - |

`g_h` is the single-stage heat-pump heating EIR curve of S14 Table 19 (SI) with a = 0.704658, b = 0.008767, c = 0.000625, d = −0.009037, e = 0.000738, f = −0.001025, evaluated at an indoor dry bulb of 21.11 °C. The fitted curve gives 0.96394 at the rating point, not 1, so it is normalised.

`COP_47` from the rating, S14 Table 11: HSPF 7.7 → 3.05, HSPF 8.2 → 3.35, HSPF 8.5 → 3.50; interpolate linearly between these. Outside 7.7 to 8.5 do not extrapolate: use the unit's certified `COP_47` (the measure library must carry it for the proposed heat pump), or fall back to the seasonal line.

The seasonal fallback is conservative for both cities: HSPF is defined for a colder climate than Los Angeles or Houston, with defrost and resistance backup in the average, so the real seasonal COP there is higher. The worked example shows the size of the difference.

Validity: single-stage, outdoor temperature above −5 °C. No defrost penalty, no supplemental resistance heat, no capacity limit. Hours below −5 °C are rare in both cities; count them and warn if there are more than 50 in the weather year.

Primary: S14 Tables 11 and 19, opened. Second source: S15 10 CFR 430.32(c) for HSPF and HSPF2 as the regulated seasonal metric, and HVAC-01 for the unit conversion. No second published mapping from HSPF to `COP_47` was opened (section 10, tier B).

Worked example: `COP_47` = 3.35 (HSPF 8.2). `f_T,h` = 1.3902 at −5 °C, 1.2120 at 0, 1.0720 at 5, 1.0000 at 8.33, 0.9403 at 12, 0.9069 at 15 °C, so COP = 2.410, 2.764, 3.125, 3.350, 3.563, 3.694. Hour with `Q_heat` = 4000 W at 5 °C: `P_el` = 1280.0 W. Seasonal fallback on the same hour: COP 2.403, 1664.5 W, 30 % higher.

Tool: `heat_pump_heating_power(load_w, t_out_c, cop_47=None, hspf=None) -> power_w`.

### HVAC-06 Furnace, boiler and electric resistance

```
E_gas  = Q_heat,year / AFUE          kWh of gas, higher heating value
E_elec = Q_heat,year / 1.0           electric resistance
```

Validity: AFUE is a seasonal efficiency that already contains cycling losses, so it is applied to the annual or hourly load without a part-load correction. Furnace blower electricity is not part of AFUE and is **not** added here (no sourced value was opened). This understates the electricity of a furnace baseline slightly and therefore understates, not overstates, the saving from `HVAC_HP`.

`HVAC_HP` evaluation: baseline = HVAC-03 (or HVAC-04) cooling plus HVAC-06 heating; proposed = HVAC-04 cooling with the new SEER2 converted by HVAC-01, plus HVAC-05 heating. Gas saved and electricity added are reported separately; cost and CO2 are computed in physics 04.

Primary: AFUE as the regulated metric for consumer furnaces, S15 10 CFR 430.32(e) (minimum values in `DEF-05`). Second source: S10, which applies AFUE and the distribution efficiency as multipliers on the heating load. The definition text of AFUE (appendix N to subpart B of part 430) was not opened.

Worked example: 10 000 kWh heating load. AFUE 0.80: 12 500 kWh gas. AFUE 0.95: 10 526 kWh gas.

Tool: `fuel_heating_energy(heating_load_kwh, afue) -> kwh_fuel`.

### HVAC-07 Rooftop units rated by IEER

```
IEER   = 0.020 * A + 0.617 * B + 0.238 * C + 0.125 * D
E_cool = Q_cool,year / (IEER * 0.293071)
P_peak = Q_cool,peak / (EER * 0.293071)
```

| Symbol | Meaning |
|---|---|
| `A` | EER at 100 % load, 35.0 °C (95 °F) outdoor |
| `B` | EER at 75 % load, 27.5 °C (81.5 °F) |
| `C` | EER at 50 % load, 20.0 °C (68 °F) |
| `D` | EER at 25 % load, 18.3 °C (65 °F) |

The first line is the definition, given so that a unit's four test points can be combined if a data sheet lists them. The tool uses the second line: annual cooling electricity from the IEER, and peak demand from the full-load EER.

Why not the hourly curve of HVAC-02 here: applying that curve to a full-load EER of 11.0 predicts `B` = 13.9, `C` = 16.7, `D` = 17.2 and an IEER of 14.9, which is far above what an EER-11 unit is actually rated (the 2023 federal minimum for a much better unit is 14.8). The curve has no fan power at part load and no staging losses. The IEER contains them, by test.

`HVAC_RTU` evaluation: `saving = Q_cool,year × (1/IEER_old − 1/IEER_new) / 0.293071`. For an existing unit with no IEER on its nameplate (older units carry only an EER), use the EER as its IEER, which is a conservative baseline (it credits the old unit with no part-load loss, and so understates the saving). Carry ±15 % for climate, as in HVAC-04.

Units under 19 kW (65 000 Btu/h) are rated by SEER or SEER2: use HVAC-02 to HVAC-04.

Validity: air-cooled packaged units of 19 kW and above. The IEER weights describe a national-average load profile.

Primary: AHRI Standard 340/360 (not opened: the AHRI site refused download), as restated in S16 (opened: the four points with their loads and outdoor temperatures, and the formula with its four weights). Second source: S15 10 CFR 431.92, definition of IEER ("a weighted average calculation of mechanical cooling EERs determined for four load levels and corresponding rating conditions"), and 431.97 Table 1 for the minimum values (14.8 for 19 to 40 kW air conditioners with electric or no heat from 1 January 2023).

Worked example: `A` = 11.0, `B` = 12.5, `C` = 13.4, `D` = 12.8 gives IEER = 0.220 + 7.7125 + 3.1892 + 1.600 = 12.722. Annual: 20 000 kWh cooling load at IEER 11.2: 6093 kWh; at IEER 14.8: 4611 kWh; saving 1482 kWh.

Tool: `ieer_from_points(a, b, c, d) -> ieer` and `seasonal_cooling_energy(cooling_load_kwh, ieer)` (same function as HVAC-04).

### HVAC-08 Duct losses

```
Q_equipment = Q_zone / DSE
DSE        <= 1 - f_leak,supply                 upper bound for ducts outside the conditioned space
DSE         = 1                                 ducts inside the conditioned space, or ductless
DSE         = 0.95                              hydronic distribution
```

| Symbol | Meaning | Unit |
|---|---|---|
| `DSE` | seasonal distribution system efficiency, one value for heating and one for cooling | - |
| `f_leak,supply` | supply-side duct leakage to outside as a fraction of system air flow | - |

The definition (first line) and the hydronic value are sourced. **Values of DSE for leaky attic ducts are not**: they come from ASHRAE Standard 152, which is paywalled, and no open table of results was found. What is sourced is the leakage itself: ResStock describes ducts in unconditioned space by total leakage to outside of 10, 20 or 30 % of flow, two thirds on the supply side (S17, Table 112). Conditioned air that leaks from a supply duct in an attic is lost, so `1 − f_leak,supply` is an upper bound on DSE: 0.933, 0.867 and 0.800 for the three classes. Return leakage and conduction through the duct wall lower it further by an amount this file cannot source.

Rule until a DSE table is sourced (section 10, tier A for the measure):

- Baseline: `DSE` = `1 − f_leak,supply` with the leakage class from `DEF-06`, flagged as an upper bound (the baseline HVAC energy of a home with attic ducts is therefore understated by an unknown few percent).
- `HVAC_DUCT` (duct sealing) is **not evaluated**. Its saving is the difference between two DSE values, neither of which is known well enough. The measure returns `applicable = false` with the reason "distribution efficiency not sourced".

Primary: S10 sections 2.1.3 and 3.1.3 (opened: two seasonal DSE values "applied to the heating and cooling system efficiencies to represent typical losses from ducts", determined with ASHRAE Standard 152; hydronic 95 %). Second source: S17 for the leakage classes.

Worked example: zone load 5000 W, 20 % leakage class: `f_leak,supply` = 0.133, `DSE` = 0.867, `Q_equipment` = 5767 W.

Tool: `apply_distribution_efficiency(zone_load_w, dse) -> equipment_load_w`.

## 6. DHW: water heating

Sources: S10 (hot water use, mains temperature), S8 (mains temperature, second source), S15 (uniform energy factor standards and the test conditions in appendix E to subpart B of 10 CFR part 430).

### DHW-01 Cold water (mains) temperature

In the source's units (°F, sine argument in degrees):

```
T_mains = (T_amb,avg + 6) + ratio * (dT_amb,max / 2) * sin( 0.986 * (day - 15 - lag) - 90 )
ratio   = 0.4 + 0.01 * (T_amb,avg - 44)
lag     = 35 - 1.0 * (T_amb,avg - 44)
```

The same in SI (°C and K):

```
theta_mains = theta_avg + 3.3333 + ratio * (dtheta_max / 2) * sin( 0.986 * (day - 15 - lag) - 90 )
ratio       = 0.4 + 0.018 * (theta_avg - 6.6667)
lag         = 35 - 1.8 * (theta_avg - 6.6667)
```

| Symbol | Meaning | Unit |
|---|---|---|
| `theta_avg` | annual mean outdoor dry-bulb temperature of the weather file | °C |
| `dtheta_max` | largest difference between monthly mean outdoor temperatures (warmest month minus coldest) | K |
| `day` | day of year, 1 to 365 | - |

Validity: an empirical fit to US utility data; no site-specific pipe depth. Implement the SI form and unit-test it against the °F form.

Primary: S10 section 4.3, eq. (21), opened. Second source: S8 Engineering Reference "Water Systems", water mains temperature correlation, opened; identical constants (6, 0.986, 15, 90, 0.4 + 0.01 (T − 44), 35 − (T − 44)), credited there to Christensen and Burch.

Worked example (illustrative climate, `theta_avg` = 20.0 °C, `dtheta_max` = 17.0 K):

| Day | °F form, converted | SI form |
|---|---|---|
| 15 | 17.991 °C | 17.990 °C |
| 105 | 22.192 °C | 22.192 °C |
| 196 | 28.647 °C | 28.647 °C |
| 288 | 24.434 °C | 24.433 °C |

Annual mean 23.335 °C, equal to `theta_avg` + 3.333 as the formula implies.

Tool: `mains_temperature(day_of_year, t_avg_c, dt_monthly_max_k) -> t_mains_c`.

### DHW-02 Daily hot water volume (homes)

```
V_hot = V_cw + V_dw + (V_shower + V_bath + V_sink) * (theta_mix - theta_mains) / (theta_set - theta_mains)
```

| End use | Volume, US gallons per day | Temperature |
|---|---|---|
| clothes washer `V_cw` | 2.35 + 0.78 × `N_br` | hot only, at set point |
| dishwasher `V_dw` | 2.26 + 0.75 × `N_br` | hot only, at set point |
| showers | 14.0 + 4.67 × `N_br` | mixed, 43.3 °C (110 °F) |
| baths | 3.5 + 1.17 × `N_br` | mixed, 43.3 °C |
| sinks | 12.5 + 4.16 × `N_br` | mixed, 43.3 °C |

`N_br` is the number of bedrooms, counted from Matterport room labels. `theta_set` = 51.7 °C (125 °F). Multiply gallons by 0.00378541 for m³. Because the mixed uses depend on `theta_mains`, compute `V_hot` per day (or per month with `day = 30 × month − 15`).

Validity: US average behaviour, single-family and multifamily units. Carry ±30 % on the volume (household size and habits; no spread is given in the source, so this range is a judgment, section 10 tier B). Offices: hot water is a minor end use and is not modelled; `Systems.dhw_*` is ignored for the office flow, and the office baseline reports 0 kWh for water heating with a warning (the office examples show 600 and 1,200 kWh, which are illustrative).

Primary: S10 section 2.1.4, Table 11, and section 4.3 (set point 125 °F, mixed temperature 110 °F), opened. Second source for magnitude: S15 appendix E, whose "medium" test draw pattern is 55 gallons (208 L) per day and "high" is 84 gallons; the three-bedroom result below is 52.8 gallons.

Worked example: `N_br` = 3, `theta_mains` = 21.11 °C (70 °F). Clothes washer 4.69, dishwasher 4.51, showers 28.01, baths 7.01, sinks 24.98 gallons; mixed total 60.00. Hot fraction of mixed water = (43.33 − 21.11)/(51.67 − 21.11) = 0.7271 (0.7273 from the °F values). `V_hot` = 52.83 gallons = 0.2000 m³ per day.

Tool: `daily_hot_water_volume(bedrooms, t_mains_c, t_set_c=51.67, t_mix_c=43.33) -> volume_m3`.

### DHW-03 Energy delivered and energy used

```
Q_dhw  = rho_w * c_w * V_hot * (theta_set - theta_mains) / 3.6e6        kWh per day
E_dhw  = Q_dhw / UEF                                                    kWh per day of gas or electricity
```

| Symbol | Meaning | Unit |
|---|---|---|
| `rho_w`, `c_w` | density and specific heat of water: 990 kg/m³ and 4180 J/(kg·K) | |
| `UEF` | uniform energy factor of the water heater (`Systems.dhw_efficiency`; defaults in `DEF-07`) | - |

`DHW_HPWH` evaluation: `saving = Q_dhw,year × (1/UEF_old − 1/UEF_new)`, in the fuel of the old heater, minus the electricity of the new one when the fuel changes.

Validity and limits:

- UEF is measured at one draw pattern, 51.7 °C delivery, 14.4 °C inlet and 19.7 °C ambient (S15 appendix E, sections 2.2 to 2.4). It contains standby loss as a share of that test load. For a household that uses much less water than the test pattern, standby is a larger share and real efficiency is below UEF; for a storage gas heater this can be 10 to 20 % worse. A heat pump water heater in a warm garage (both cities) performs better than its rating; in a cold space, worse. Carry ±15 % on `E_dhw`.
- A heat pump water heater inside the conditioned space cools that space. That interaction is not modelled; the tool assumes the heater is in a garage, closet with outdoor air, or outdoors, which is the common case in both cities. State the assumption.
- Water properties are standard values near 45 °C, not taken from an opened table (section 10, tier B); the effect is under 1 %.

Primary: energy balance on the heated water, as used in the test procedure S15 appendix E (which defines the delivered energy with the density and specific heat of the stored water) and the definition of UEF as delivered energy over consumed energy. Second source: S10 section 3.1.4, which applies the rated energy factor to the hot water load in the same way.

Worked example: `V_hot` = 0.2000 m³/day, 51.67 − 21.11 = 30.56 K. `Q_dhw` = 990 × 4180 × 0.2000 × 30.56 / 3.6e6 = 7.025 kWh/day = 2564 kWh/yr. Imperial route: 52.83 gal × 8.2619 lb/gal × 0.9984 Btu/(lb·°F) × 55 °F = 23 965 Btu = 7.024 kWh. Then:

| Heater | UEF | `E_dhw` per year |
|---|---|---|
| gas storage, 40 gal, federal minimum (0.6483 − 0.0017 × 40) | 0.5803 | 4418 kWh gas |
| electric resistance storage, 50 gal, federal minimum (0.9307 − 0.0002 × 50) | 0.9207 | 2785 kWh |
| heat pump, 2029 federal minimum | 2.30 | 1115 kWh |
| heat pump, UEF 3.5 | 3.50 | 733 kWh |

Tool: `dhw_energy(volume_m3, t_mains_c, uef, t_set_c=51.67) -> {delivered_kwh, input_kwh}`.

## 7. LGT: lighting and plug loads

### LGT-01 Lighting energy

Offices and any zone described by a power density:

```
P_light(h) = LPD * A_f * f_light(h)
E_light    = sum over the year of P_light(h) / 1000          kWh
```

Homes (annual energy from floor area, then spread over the hours):

```
E_light,base = 0.542 * A_f,ft2 + 334                          kWh per year, interior lighting, benchmark lamp mix
E_light      = E_light,base * { [ (F_inc + 0.34) + (F_cfl - 0.21) * 0.27 + F_led * ER_led + (F_lf - 0.13) * 0.17 ] * SAF * 0.9 + 0.1 }
SAF          = 1.1 F_inc^4 - 1.9 F_inc^3 + 1.5 F_inc^2 - 0.7 F_inc + 1
P_light(h)   = E_light * 1000 * share_day(h) * m_month / 365
```

| Symbol | Meaning | Unit |
|---|---|---|
| `LPD` | installed lighting power density (`Systems.lighting_w_per_m2`; `DEF-10`) | W/m² |
| `f_light(h)` | hourly schedule fraction (`DEF-09`) | - |
| `A_f,ft2` | finished floor area in ft² (`A_f` / 0.092903) | ft² |
| `F_inc`, `F_cfl`, `F_led`, `F_lf` | fractions of lamps that are incandescent, compact fluorescent, LED, linear fluorescent | - |
| `ER_led` | efficacy ratio, incandescent to LED: 0.30 in the source (LED at 50 lm/W, a 2014 figure). For current lamps use 15/90 = 0.17 and say so | - |
| `SAF` | smart replacement factor of the source (the most-used lamps are replaced first) | - |
| `share_day(h)`, `m_month` | hourly share of a day's lighting energy and monthly multiplier (`DEF-09`) | - |

Baseline for a home: `E_light,base` as it stands (the lamp mix is not observed; the benchmark mix is 66 % incandescent, 21 % compact fluorescent, 13 % linear fluorescent). If the panorama reading reports mostly LED lamps, use the all-LED factor for the baseline and skip the measure. `LGT_LED` for a home: `F_led` = 1, other fractions 0, so `SAF` = 1.

`LGT_LED` for an office: new `LPD` from `DEF-10`. `LGT_CTRL`: multiply `f_light(h)` by a control factor in the hours it applies; the daylight part comes from physics 03 (LCT-01, LCT-02). No control savings fraction was sourced in this file (section 10).

Validity: the home formula is the Building America benchmark, a US-average house of about 2010; the 0.1 constant is the part of lighting energy the source treats as unaffected by lamp type.

Primary: S11 Table A-2 and Table B-13 (office power densities and schedules); S10 section 2.1.7, eqs. (6), (7) and (10), Table 18 (home formula, lamp fractions, efficacy ratios), all opened. The first home line is the sum of eq. (6) (hard-wired, 80 %) and eq. (7) (plug-in, 20 %); eq. (10) is written in the source for the hard-wired part and is applied here to both parts. Second source: S13 default lighting schedule (hourly shares and monthly multipliers, credited there to ANSI/RESNET/ICC 301-2022 Addendum C, Tables C.3(3) and C.3(4)).

Worked example, home: 150 m² = 1615 ft². `E_light,base` = 0.542 × 1615 + 334 = 1209 kWh/yr. All LED with the source's ratio 0.30: factor = (0.34 − 0.0567 + 0.30 − 0.0221) × 1 × 0.9 + 0.1 = 0.6051, 732 kWh/yr, saving 478 kWh/yr. With `ER_led` = 15/90 (0.1667): factor 0.4851; the rounded 0.167 gives 0.4854.

Worked example, office: the small-office lighting schedule (`DEF-09`) sums to 10.50 on a weekday, 2.80 on a Saturday and 1.20 on other days, which is 2939 equivalent full-power hours per year (260 weekdays, 52 Saturdays, 53 other days). For 500 m²: `LPD` 19.48 W/m² → 28 628 kWh/yr; 10.76 → 15 813 kWh/yr; 6.5 → 9552 kWh/yr.

Tool: `lighting_power(hour, lpd_w_m2, area_m2, schedule) -> power_w` and `home_lighting_energy(floor_area_m2, f_inc, f_cfl, f_led, f_lf, er_led=0.30) -> kwh_per_year`.

### LGT-02 Plug and miscellaneous loads

```
P_plug(h) = PPD * A_f * f_equip(h)                                  offices
E_mel     = 1185.4 + 180.2 * N_br + 0.3188 * A_f,ft2                 homes, kWh per year, miscellaneous loads
```

| Symbol | Meaning | Unit |
|---|---|---|
| `PPD` | plug power density (`Systems.plug_w_per_m2`; `DEF-10`) | W/m² |
| `f_equip(h)` | hourly schedule fraction (`DEF-09`) | - |

Homes add the major appliances of the same source table: refrigerator 434 kWh/yr; electric range 250 + 83 `N_br`; dishwasher 87.6 + 29.2 `N_br`; clothes washer 38.8 + 12.9 `N_br`; electric dryer 538.2 + 179.4 `N_br`. Hourly spread: `share_day(h)` for plug loads, `DEF-09`.

Offices with CoStar tenancy data: when `Systems.occupants` is set from tenant employee counts, scale `PPD` by `(N_occ / A_f) / (1 / 18.59)`, limited to the range 0.5 to 2.0, on the reasoning that plug load follows workstations. This scaling rule is a design choice, not from a source (section 10, tier B); the unscaled default is the fallback.

`PLUG_MGMT`: lowers `f_equip(h)` in unoccupied hours toward a floor. The reference schedule holds 0.40 on weekday nights and 0.30 on weekends and holidays; the measure's achievable floor was not sourced (section 10).

Primary: S11 Table A-2 and Table B-13; S10 section 2.1.8, Table 25, opened. Second source: S13 default plug-load schedule.

Worked example: office 500 m² at 10.76 W/m²: the equipment schedule sums to 4487 equivalent full-power hours per year, 24 140 kWh/yr. Home, 3 bedrooms, 1615 ft²: `E_mel` = 2241 kWh/yr.

Tool: `plug_power(hour, ppd_w_m2, area_m2, schedule) -> power_w` and `home_misc_energy(bedrooms, floor_area_m2) -> kwh_per_year`.

### LGT-03 Internal gains to the zone model, and the interaction with heating and cooling

```
Phi_int(h) = 1.00 * P_light(h) + f_sens,plug * P_plug(h) + N_occ * occ(h) * q_sens
Phi_lat,occ(h) = N_occ * occ(h) * q_lat                      (added to the cooling load, section 5)
```

| Quantity | Homes | Offices | Source |
|---|---|---|---|
| lighting, sensible fraction | 1.00 | 1.00 | S10: "100 % of interior lighting energy contributes to the internal sensible load" |
| plug or miscellaneous, sensible fraction `f_sens,plug` | 0.93 (latent 0.02) | 1.00 | S10 Table 25 (miscellaneous loads; multifamily office space 1.00) |
| appliances, sensible / latent | refrigerator 1.00 / 0; washer 0.80 / 0; dryer 0.15 / 0.05; dishwasher 0.60 / 0.15; range 0.40 / 0.30 | n/a | S10 Table 25 |
| occupant sensible `q_sens` | 64.5 W (220 Btu/h) | 73.3 W (250 Btu/h) | S10 Table 48 |
| occupant latent `q_lat` | 48.1 W (164 Btu/h) | 58.6 W (200 Btu/h) | S10 Table 48 |
| occupant count `N_occ` | 0.59 `N_br` + 0.87 (single-family); 0.92 `N_br` + 0.63 (multifamily) | `Systems.occupants` from CoStar tenancy, else `A_f` / 18.59 | S10 eqs. (23), (24); S11 Table 4 |
| presence `occ(h)` | hourly share × 16.5 h per day | schedule fraction | S10 Figure 25 (16.5 h/day per person) and S13 hourly shares; S11 Table B-13 |

For homes the daily total of occupant heat (16.5 person-hours per person) is from S10 and its hourly shape from S13; `occ(h)` may exceed 1 in the evening peak because it is a gain weight, not a head count.

**Interaction with heating and cooling.** There is no separate interaction factor. A lighting or plug measure changes `Phi_int(h)`; the zone model is run again; the change in heating and cooling need is the interaction. A watt of lighting removed in a cooling hour removes one watt of cooling load; in a heating hour it adds one watt of heating need (less whatever the dynamics store). The measure result reports three numbers: electricity saved at the lamp or plug, cooling electricity saved, and heating energy added.

Sanity estimate for a unit test (not the method): if a share `s_c` of the saved energy falls in hours with a cooling need and `s_h` in hours with a heating need, then cooling saving ≈ `dE × s_c / COP` and added heating ≈ `dE × s_h / efficiency`. For 1000 kWh saved, `s_c` = 0.6, COP 3.0, `s_h` = 0.25, AFUE 0.80: 200 kWh less cooling electricity and 312 kWh more gas. The hourly result should fall within 25 % of the estimate made with its own `s_c` and `s_h`.

Validity: all gains are treated as instantaneous inputs to ZON-02; the split between air, surface and mass nodes is done there.

Primary: S10 sections 2.1.7, 2.1.8 and 4.6, Tables 25 and 48; S11 Tables 4, A-2, B-13; all opened. Second source: S1 clause 10.2 treats internal gains from occupants, appliances and lighting as the heat flow `Phi_int` of the hourly model, which is what ZON-02 distributes; S8 Engineering Reference "Zone Internal Gains" describes the same sensible and latent split.

Worked example: home, 3 bedrooms, single-family: `N_occ` = 2.64. At an hour with share 0.082: `occ` = 1.353, occupant sensible gain = 2.64 × 1.353 × 64.5 = 230 W, latent 172 W.

Tool: `internal_gains(hour, lighting_w, plug_w, occupants, schedule, building_type) -> {sensible_w, latent_w}`.

## 8. DEF: default tables

Additional source key:

| Key | Source |
|---|---|
| S17 | NREL, *ResStock Technical Reference Documentation* v3.3.0, NREL/TP-5500-91621, 2025 (OSTI 2583488), and the distribution files it documents, `project_national/housing_characteristics/*.tsv` in `https://github.com/NREL/resstock` (branch `develop`, read 2026-11-14): `Infiltration`, `Insulation Ceiling`, `Insulation Wall`, `Windows`, `Duct Leakage and Insulation`, `Location Region`. |

How to read these tables:

- **Vintage** is `CostarData.year_built`. If `year_built_event` shows it came from anything other than the construction-complete event (a renovation, for example), widen low and high to the adjacent vintage rows. With no year at all, use the Vexcel or vision evidence to choose a row and span low and high across all rows.
- **Climate.** Houston is IECC climate zone 2A; Los Angeles is zone 3B (the DOE reference buildings use "3B-CA" for it). ResStock regions: Texas is `CR09`, California `CR11` (S17 `Location Region`).
- **Low / expected / high** are in the order low value, expected value, high value of the quantity itself (so for a U-value, "high" is the leakiest case). For ResStock distributions, expected is the median and low and high are the 10th and 90th percentiles of the option distribution, averaged without weights over the dependency bins that do not concern us (floor-area bins for infiltration; income and tenure bins for windows). That averaging is a simplification of this file.
- A stronger source in the assumption registry (user, measured, vision) replaces the default.
- U-values from US tables are whole-assembly values with the ASHRAE films, used as published (ENV-01).

**Year boundaries in every DEF table and in INF-05.** A building built in 2004 takes the older row: "1980–2004", "2004 or earlier" and "before 2004" in older text all include 2004, and "after 2004" means 2005 on. The same applies to any boundary year: the year printed at the end of a range belongs to that range.

### DEF-01 Home opaque envelope by vintage

Wood-frame wall, U in W/(m²·K) (Btu/(h·ft²·°F) in brackets). Cavity insulation by vintage from S17 `Insulation Wall` (wood frame; Texas and California agree except where noted) and S10 Table 29; assembly U from S6 Table 4.3.1 column A (2x4 at 16 in.: none 0.356, R-11 0.110, R-13 0.102, R-15 0.095; 2x6 R-19 0.074). R-7 is not in that table and is computed with ENV-02 on the same layers (0.138; the same calculation returns 0.1098 for R-11 and 0.1015 for R-13, against the published 0.110 and 0.102).

| Vintage | Cavity insulation, low U / expected / high U | U low | U expected | U high |
|---|---|---|---|---|
| before 1970 | R-11 (retrofitted) / none / none | 0.625 (0.110) | 2.021 (0.356) | 2.021 (0.356) |
| 1970–1979 | R-11 / R-7 / none | 0.625 (0.110) | 0.782 (0.138) | 2.021 (0.356) |
| 1980–1989 | R-19 / R-11 / R-7 | 0.420 (0.074) | 0.625 (0.110) | 0.782 (0.138) |
| 1990–1999 | R-19 / R-11 / R-11 | 0.420 (0.074) | 0.625 (0.110) | 0.625 (0.110) |
| 2000 and later, Texas | R-19 / R-11 / R-11 | 0.420 (0.074) | 0.625 (0.110) | 0.625 (0.110) |
| 2000 and later, California | R-19 / R-19 / R-11 | 0.420 (0.074) | 0.420 (0.074) | 0.625 (0.110) |

The two sources agree on the pattern (S10: none before 1980, R-11 for 1980–1989, R-13 from 1990; S17: none before 1970, half R-7 in the 1970s, 90 % R-11 in the 1980s). The "retrofitted" low value before 1970 is this file's allowance for blown-in insulation, not a distribution value.

Ceiling under a vented attic. Insulation by vintage from S17 `Insulation Ceiling` (vented attic; Texas and California are the same to within one option except after 1990); assembly U from S6 Table 4.2.1 column A (none 0.300, R-11 0.079, R-13 0.071, R-19 0.049, R-30 0.032, R-38 0.026).

| Vintage | Attic insulation p90 / p50 / p10 | U low | U expected | U high |
|---|---|---|---|---|
| before 1950 | R-30 / R-13 / none | 0.182 (0.032) | 0.403 (0.071) | 1.703 (0.300) |
| 1950–1959 | R-30 / R-19 / none | 0.182 | 0.278 (0.049) | 1.703 |
| 1960–1969 | R-30 / R-13 / R-7 | 0.182 | 0.403 | 0.61 (see note) |
| 1970–1979 | R-30 / R-19 / R-7 | 0.182 | 0.278 | 0.61 |
| 1980–1989 | R-30 / R-19 / R-13 | 0.182 | 0.278 | 0.403 |
| 1990 and later | R-38 / R-30 / R-19 | 0.148 (0.026) | 0.182 | 0.278 |

Note: R-7 is not in S6 Table 4.2.1. The value 0.61 W/(m²·K) (0.108 Btu/(h·ft²·°F)) is obtained by interpolating 1/U linearly in the rated R-value between the published "none" and R-11 rows; replace it at build time by an ENV-01 and ENV-02 calculation on the table's layers (section 10, tier B). `ENV_ATTIC` raises the attic to R-38 or R-49 (U 0.148 or 0.114).

A flat or low-slope roof with no attic, and cathedral ceilings: S10 Table 30 gives cavity R by vintage (2x6 rafters: none before 1950, R-7 for 1950–1979, R-9 for 1980–1989, R-13 from 1990). Assembly U to be built with ENV-01 and ENV-02.

Slab on grade: uninsulated in both climate zones for every vintage (S10 Table 31 gives R-0 for floors in all regions other than cold ones; S11 Table 22 was located but not read for the slab rows). Use ENV-04 with the range given there.

### DEF-02 Solar absorptance and emittance

| Surface | Absorptance low / expected / high | Source |
|---|---|---|
| asphalt (composition) shingle roof, colour unknown | 0.75 / 0.85 / 0.92 | S10 Table 33: light 0.75, medium 0.85, dark 0.92 |
| concrete or cement tile roof | 0.60 / 0.75 / 0.90 | S10 Table 33: light 0.60, medium 0.75, dark 0.90; white 0.30 |
| clay tile or slate roof | 0.60 / 0.75 / 0.90 | S10 Table 33: light 0.60, terra cotta 0.65, medium 0.75, dark 0.90 |
| wood shingle roof | 0.80 / 0.80 / 0.90 | S10 Table 33: medium 0.80, dark 0.90 |
| low-slope membrane, metal, or unknown commercial roof | 0.40 / 0.65 / 0.90 | S13 defaults for synthetic sheeting: light 0.40, medium 0.65, dark 0.90 |
| cool roof after `ROOF_COOL` | 0.25 / 0.30 / 0.40 | S13: "reflective" 0.25, "white" 0.30 for tile, concrete and sheeting; S10: white concrete 0.30 |
| exterior walls | 0.30 / 0.60 / 0.80 | S10: default 0.60 for existing homes; light vinyl 0.30; the high value is this file's bound |
| thermal emittance, all roofs and walls | 0.90 | S10 |

The roof material comes from Vexcel roof attributes and its colour from the ortho image reading. Cool-roof products lose reflectance as they soil; 0.30 to 0.40 is the range to use for a roof that has aged. Rated aged values (Cool Roof Rating Council) were not opened.

### DEF-03 Windows

Types and their whole-window properties (S17 Table 69; U in Btu/(h·ft²·°F), converted):

| Type | U, W/(m²·K) | SHGC |
|---|---|---|
| single, clear, metal frame | 6.59 (1.16) | 0.76 |
| single, clear, non-metal frame | 4.77 (0.84) | 0.63 |
| double, clear, metal frame | 4.32 (0.76) | 0.67 |
| double, clear, non-metal frame | 2.78 (0.49) | 0.56 |
| double, low-e, non-metal frame | 2.16 (0.38) | 0.44 |
| triple, low-e, non-metal frame | 1.65 (0.29) | 0.26 |

Default type by vintage, single-family homes: the 10th, 50th and 90th percentile of the U-value distribution in S17 `Windows` (built there from the 2020 RECS survey), after removing its "void" rows and averaging over income and tenure bins:

| Vintage | Houston (2A): best / expected / worst | Los Angeles (3B): best / expected / worst |
|---|---|---|
| before 1960 | double low-e / single clear non-metal / single clear metal | double low-e / single clear non-metal / single clear metal |
| 1960–1979 | double low-e / single clear non-metal / single clear metal | double low-e / double clear metal / single clear metal |
| 1980–1999 | double low-e / single clear non-metal / single clear metal | double low-e / double clear metal / single clear metal |
| 2000–2009 | double low-e / double clear metal / single clear metal | double low-e / double clear non-metal / double clear metal |
| 2010 and later | double low-e / double clear metal / single clear metal | double low-e / double low-e / double low-e |

The "best" column is low-e in every row because at least a tenth of homes of every vintage have had their windows replaced. Apartment units (buildings of five or more units) follow the same table with two differences in the source: the Houston median before 1960 is single clear metal, and the Los Angeles median for 1980–1999 is single clear non-metal. The vintage bins of the source are before 1940, 1940–59, 1960–79, 1980–99, 2000–09 and 2010s.

A panorama reading of pane count and frame material replaces the default type. `WIN_REPLACE` installs "double, low-e, non-metal" by default.

Window area: measured openings, ±5 %. From vision when no window openings exist: ±30 %. With neither: window-to-wall ratio 0.15 / 0.18 / 0.25 of exterior wall area for homes and 0.20 / 0.30 / 0.40 for offices; these ratios are **not sourced** (section 10, tier A) and exist only so the pipeline does not stop.

### DEF-04 Air leakage (homes), ACH50

From S17 `Infiltration` (LBNL Residential Diagnostics Database), percentiles over the option distribution:

| Vintage | Houston (2A): p10 / p50 / p90 | Los Angeles (3B): p10 / p50 / p90 |
|---|---|---|
| before 1960 | 10 / 25 / 50 | 6 / 15 / 30 |
| 1960–1979 | 8 / 20 / 40 | 5 / 15 / 25 |
| 1980–1989 | 7 / 20 / 40 | 4 / 10 / 20 |
| 1990–1999 | 5 / 15 / 25 | 3 / 8 / 15 |
| 2000 and later | 5 / 15 / 25 | 3 / 7 / 15 |

All values are from single-family detached blower-door tests (S17). For an apartment unit apply the exposed-surface factor of INF-02. A current new house built to the Building America benchmark is 7 (S10). `ENV_AIRSEAL` target: no reduction fraction was sourced (section 10); the measure takes its target ACH50 as a parameter.

Offices: INF-05.

### DEF-05 Heating and cooling equipment efficiency

Homes, central air conditioner or heat pump, by year the **equipment** was installed:

| Installed | SEER | HSPF (heat pumps) | Source |
|---|---|---|---|
| before 1981 | 6.5 | 6.0 | S10 Table 34 |
| 1981–1991 | 8 | 6.6 | S10 Table 34 |
| 1992–2005 | 10 | 7.1 | S10 Table 34 ("after 1991") |
| 2006–2014 | 13 | 7.7 | S10 Table 6 and benchmark (SEER 13, HSPF 7.7) |
| 2015–2022 | 14 (Texas and California) | 8.2 | S15 10 CFR 430.32(c)(1) to (3) |
| 2023 and later | 14.3 SEER2 (= 15.05 SEER) | 7.5 HSPF2 (= 8.8 HSPF) | S15 10 CFR 430.32(c)(5), (6) |

The equipment year is rarely the building year. Rule: if the building is 2006 or newer, use the building year. If older and nothing is observed, carry SEER 10 / 13 / 14 as worst / expected / best (the unit has probably been replaced at least once), and for a heat pump HSPF 7.1 / 7.7 / 8.2, the same rows of the table. That rule is a judgment (section 10, tier B); the vision reading of the outdoor unit's age band replaces it.

Room air conditioner: EER 6.5 before 1981, 7.5 for 1981–1991, 9.75 after 1991 for units under 5.9 kW (S10 Table 34).

Gas furnace AFUE:

| Type or year | AFUE | Source |
|---|---|---|
| natural draft, standing pilot, in unconditioned space | 0.64 | S10 Table 35 |
| natural draft, standing pilot, in conditioned space | 0.75 | S10 Table 35 |
| natural draft, vent damper, electronic ignition; federal minimum before 19 November 2015 | 0.78 | S10 Table 35; S15 10 CFR 430.32(e)(1)(i) |
| induced draft; federal minimum from 19 November 2015 | 0.80 | S10 Table 35; S15 10 CFR 430.32(e)(1)(ii) |
| condensing | 0.90 | S10 Table 35 |

Unknown furnace: 0.64 / 0.78 / 0.80 for a building older than 1992; 0.78 / 0.80 / 0.90 otherwise (vintage split is a judgment, tier B). Electric resistance: 1.0.

Offices (packaged unit with gas furnace, single zone, constant volume: S11 Tables 29 and 30 for small offices):

| Building vintage | Cooling | Heating | Source |
|---|---|---|---|
| before 1980 (equipment since replaced) | SEER 11.06 under 19 kW; EER 9.63 for 19 to 40 kW | combustion efficiency 0.80 | S11 Tables 31 and 34 |
| 1980–2004 | as above (the 90.1-1989 values were not opened) | 0.80 | S11 |
| 2005–2022 | as above: no value for this period was opened, so the 1980–2004 row is carried (judgment, section 10, tier B) | 0.80 | S11 |
| new or replaced from 2023 | IEER 14.8 (19 to 40 kW, electric or no heat); 14.6 with other heat | 0.80 | S15 10 CFR 431.97 Table 1 |

Carry the office cooling rating as −10 % / expected / +15 %.

### DEF-06 Duct leakage class (homes with ducts outside the conditioned space)

S17 `Duct Leakage and Insulation`: for every vintage, 26 % of homes at 10 % leakage to outside, 47 % at 20 %, 27 % at 30 %; duct insulation R-4 before 2000, R-8 after. Supply share two thirds (S17 Table 112). So `f_leak,supply` = 0.067 / 0.133 / 0.200 and the HVAC-08 upper-bound `DSE` = 0.933 / 0.867 / 0.800. Ducts inside the conditioned space, ductless systems and room units: `DSE` = 1.

### DEF-07 Water heaters

| Type | Efficiency | Source |
|---|---|---|
| gas storage, old, pilot, poorly insulated | EF 0.45 | S10 Table 37 |
| gas storage, pilot, 1 in. insulation | EF 0.54 | S10 Table 37 |
| gas storage, federal minimum (20 to 55 gal, medium draw) | UEF 0.6483 − 0.0017 × volume in gallons (0.580 at 40 gal) | S15 10 CFR 430.32(d)(1) |
| gas tankless | EF 0.76 (derated) | S10 Table 37 |
| electric storage, old | EF 0.79 | S10 Table 37 |
| electric storage, federal minimum (20 to 55 gal, medium draw) | UEF 0.9307 − 0.0002 × volume (0.921 at 50 gal) | S15 10 CFR 430.32(d)(1) |
| electric storage over 55 gal, federal minimum (medium draw) | UEF 2.1171 − 0.0011 × volume (heat pump level) | S15 10 CFR 430.32(d)(1) |
| heat pump water heater, federal minimum from 6 May 2029 (20 to 55 gal) | UEF 2.30 | S15 10 CFR 430.32(d)(2) |

EF (the pre-2017 metric) and UEF are not identical; they are treated as equal here, inside the ±15 % of DHW-03. Unknown gas heater: 0.54 / 0.58 / 0.64. Unknown electric heater: 0.87 / 0.92 / 0.93. The UEF of the proposed heat pump water heater is a measure-library parameter taken from the product's certificate; 2.30 is the floor.

### DEF-08 Thermostat setpoints

| Building | Heating | Cooling | Source |
|---|---|---|---|
| home, all hours | 21.7 °C (71 °F) | 24.4 °C (76 °F), no setup | S10 section 4.2 |
| office, occupied (06:00–22:00 weekdays, 06:00–18:00 Saturdays) | 21.0 °C | 24.0 °C | S11 Table B-13 |
| office, unoccupied (other hours, Sundays and holidays) | 15.6 °C | 26.7 °C | S11 Table B-13 |

Range ±1 K on each. `CTRL_TSTAT` for a home: a setback or setup schedule entered as hourly setpoints; its saving is the difference between two year runs (ZON-04). No default setback depth was sourced; it is a measure parameter. No home setback hours were sourced either. The implementation uses this project's judgment, a common programmable-thermostat pattern: setback and setup apply at night from 22:00 to 06:00 every day and on weekdays from 08:00 to 18:00, and only when the home has a setback set (section 10, tier B).

### DEF-09 Schedules

Small office (S11 Table B-13; hour 1 is midnight to 01:00):

| Schedule | Day | Hours 1 to 24 |
|---|---|---|
| occupancy | weekday | 0 0 0 0 0 0 0.1 0.2 0.95 0.95 0.95 0.95 0.5 0.95 0.95 0.95 0.95 0.3 0.1 0.1 0.05 0.05 0.05 0.05 |
| occupancy | Saturday | 0 0 0 0 0 0 0.1 0.1 0.3 0.3 0.3 0.3 0.1 0.1 0.1 0.1 0.1 0 0 0 0 0 0 0 |
| occupancy | other | 0 for all hours |
| lighting | weekday | 0.05 0.05 0.05 0.05 0.05 0.1 0.1 0.3 0.9 0.9 0.9 0.9 0.9 0.9 0.9 0.9 0.9 0.5 0.3 0.3 0.2 0.2 0.1 0.05 |
| lighting | Saturday | 0.05 0.05 0.05 0.05 0.05 0.05 0.1 0.1 0.3 0.3 0.3 0.3 0.15 0.15 0.15 0.15 0.15 0.05 0.05 0.05 0.05 0.05 0.05 0.05 |
| lighting | other | 0.05 for all hours |
| equipment | weekday | 0.4 0.4 0.4 0.4 0.4 0.4 0.4 0.4 0.9 0.9 0.9 0.9 0.8 0.9 0.9 0.9 0.9 0.5 0.4 0.4 0.4 0.4 0.4 0.4 |
| equipment | Saturday | 0.3 0.3 0.3 0.3 0.3 0.3 0.4 0.4 0.5 0.5 0.5 0.5 0.35 0.35 0.35 0.35 0.35 0.3 0.3 0.3 0.3 0.3 0.3 0.3 |
| equipment | other | 0.3 for all hours |
| HVAC on (ventilation on, infiltration at 25 %) | weekday | hours 7 to 22 |
| HVAC on | Saturday | hours 7 to 18 |
| HVAC on | other | off |

Office with CoStar tenancy data: the tenant's industry may shift the occupied window (for example a medical or retail tenant in an office building). No sourced mapping from industry to schedule was opened; the default schedule is used and the tenancy data sets only the occupant count (LGT-03). A vacant suite (no current tenancy) uses the "other" row every day.

Schedule keys for `Systems.occupancy_schedule`: `"home"`, `"office"`, `"office_vacant"`.

Home (S13 default schedules, credited there to ANSI/RESNET/ICC 301-2022 Addendum C; each row is the share of the day's total in each hour and sums to 1; same on weekdays and weekends):

| Schedule | Hours 1 to 24 |
|---|---|
| occupants | 0.035 0.035 0.035 0.035 0.035 0.059 0.082 0.055 0.027 0.014 0.014 0.014 0.014 0.014 0.019 0.027 0.041 0.055 0.068 0.082 0.082 0.070 0.053 0.035 |
| interior lighting | 0.012 0.010 0.010 0.010 0.011 0.018 0.030 0.038 0.041 0.041 0.039 0.037 0.036 0.035 0.037 0.041 0.050 0.065 0.086 0.106 0.110 0.079 0.040 0.018 |
| plug and miscellaneous loads | 0.036 0.036 0.036 0.036 0.036 0.036 0.038 0.041 0.042 0.042 0.042 0.042 0.042 0.042 0.042 0.044 0.047 0.050 0.051 0.050 0.048 0.044 0.040 0.037 |

Interior lighting monthly multipliers, January to December: 1.19 1.11 1.02 0.93 0.84 0.80 0.82 0.88 0.98 1.07 1.16 1.20. Occupants and plug loads: 1.0 every month.

### DEF-10 Lighting and plug power density

| Building | Lighting W/m² low / expected / high | Plug W/m² low / expected / high | Source |
|---|---|---|---|
| office built in 2004 or earlier, lighting not yet upgraded | 10.76 / 19.48 / 19.48 | 8.61 / 10.76 / 10.76 | S11 Table A-2 (19.48 W/m² = 1.81 W/ft², ASHRAE 90.1-1989; 10.76 W/m² = 1.0 W/ft², 90.1-2004) |
| office built 2005 or later | 6.5 / 10.76 / 10.76 | 8.61 / 10.76 / 10.76 | S11 Table A-2 |
| office after `LGT_LED` | measure parameter | unchanged | not sourced: see below |
| home | by LGT-01 | by LGT-02 | S10 |

Two cautions. First, the plug value: S11 Table A-1 (imperial) prints 0.8 W/ft² (8.61 W/m²) for the small office and Table A-2 (SI) prints 10.76 W/m²; the two tables of the same report disagree, so both are carried. Second, an LED office typically runs well below 10.76 W/m², but no post-2004 code value (ASHRAE 90.1-2010 and later, or Title 24) was opened; 6.5 W/m² is this file's placeholder for "already LED" and the `LGT_LED` target (section 10, tier A). The panorama reading of fixture type decides which row applies.

### DEF-11 Office envelope by vintage

From S11 Tables 17 to 25, small office. U in W/(m²·K) (Btu/(h·ft²·°F) in brackets).

| Element | Vintage | Houston (2A) | Los Angeles (3B-CA) |
|---|---|---|---|
| roof | before 1980 | 0.568 (0.100) | 0.568 (0.100) |
| roof | 1980–2004 | 0.375 (0.066) | 0.568 (0.100) |
| roof | after 2004, insulation above deck / attic | 0.358 (0.063) / 0.193 (0.034) | 0.358 / 0.193 |
| wall, steel frame | before 1980 | 1.306 (0.230) | 1.306 (0.230) |
| wall, mass | before 1980 | not in the source; the 1980–2004 values are carried as the bound (judgment) | as left |
| wall, mass | 1980–2004 | 1.931 (0.340) | 5.678 (1.000) |
| wall, mass | after 2004 | 3.293 (0.580) | 0.857 (0.151) |
| wall, steel frame | 1980–2004 | 0.852 (0.150) | 1.249 (0.220) |
| wall, steel frame | after 2004 | 0.704 (0.124) | 0.704 (0.124) |
| window U | before 1980 | 6.93 (1.22) | 6.93 (1.22) |
| window U | 1980–2004 | 6.93 (1.22) | 6.93 (1.22) |
| window U | after 2004 | 6.93 (1.22) | 3.24 (0.57) |
| window SHGC | before 1980 | 0.54 | 0.54 |
| window SHGC | 1980–2004 | 0.25 | 0.44 |
| window SHGC | after 2004 | 0.25 | 0.25 |

S11 assigns the small office a steel-frame wall before 1980 and a mass wall afterwards, and a roof with insulation above deck before 1980 and an attic roof afterwards. The wall type of a real building comes from Vexcel and vision; when unknown, expected is the S11 type for the vintage and low and high span the other type. The 5.678 W/(m²·K) mass-wall value for Los Angeles is the code's "no requirement" entry (1.000 Btu/(h·ft²·°F)), not a measured wall; treat it as the high bound and use the steel-frame value as expected there. An apartment unit takes its envelope from DEF-01 and DEF-03 and has exterior boundaries only where its walls face outdoors; party walls and floors to other units are `adjacent_conditioned`.

## 9. Build-time test plan

Every tool function gets a unit test that reproduces the worked example in its entry to the precision printed there (relative tolerance 1e-3 unless stated). On top of those:

| Module | Reference the test compares against | Tolerance |
|---|---|---|
| ENV-01, ENV-02 | S6 Table 4.1.1 (0.065 Btu/(h·ft²·°F)) and S6 Table 4.3.1 column A for R-11 and R-13 walls (0.110, 0.102), rebuilt from the layers listed under that table | ±0.001 Btu/(h·ft²·°F), which is the table's rounding |
| ENV-04 | the worked example (0.6193 W/(m²·K)); and the branch `d_t >= B'` with a heavily insulated small slab, checked against the second formula by hand | 1e-4 |
| ENV-06 | the four conversions of the entry | 1e-3 |
| ENV-05 | the sol-air route and the ISO effective-area route must give the same heat flow; the non-linear balance of the worked example | identical to 1e-9; within 8 % for the non-linear check |
| ZON-03, ZON-04 | the four published cases of S2 `tests/testRCmodel.py` listed in ZON-04 (zone built with `H_tr,em` as S2 defines it) | energy to 0.01 W, temperature to 0.01 K, as published |
| ZON-03 | direct 3×3 linear solve of the node balances for the same inputs | 1e-9 relative |
| ZON-05 | closed-form `H_eff` against the model iterated to steady state | 1e-6 relative |
| ZON-04 year run | energy conservation: over the year, sum of `Phi_HC` + gains reaching the nodes + all conductance flows = change in stored heat of `C_m` | 0.1 % of annual gains |
| ZON-06 | monthly quasi-steady heating need against the hourly model on each golden property, constant setpoint | within 15 % on the annual sum |
| ZON, whole model | optional, if time allows: an EnergyPlus run of the same single-zone box with the same schedules; S4 found ISO 13790 within about 2 % (heating) and 4 % (cooling) of EnergyPlus on its case study. ASHRAE Standard 140 cases were not opened and are not a test here | within 15 % on annual heating and cooling need |
| INF-02, INF-03 | worked examples; and the coefficient identity `C_s = (0.1 f_s*)²` from S12 eq. (7) | 1e-3; 1 % on the identity |
| INF-04 | quadrature against a hand value; limits (no fan gives `Q_inf`; balanced fan adds linearly) | exact |
| INF-06 | the three hours of the INF-06 example: at 15 °C mechanical cooling 0 W and air at the setpoint; at 30 °C the result without economizer; at 20.5 °C zero cooling with a flow between minimum and maximum | 0.1 W, 0.001 K |
| WIN-01, WIN-02 | worked examples | 1e-3 |
| HVAC-02, HVAC-03 | self-consistency: at 27.78 °C and part-load ratio 0.5 the model returns the SEER it was built from; the `EER_A` table against S14 Table 6 and the S13 regression | exact to 1e-6; table within 5 % |
| HVAC-03 against HVAC-04 | annual hourly result against the seasonal method for a single-stage unit on each golden property | within 20 % |
| HVAC-05 | curve values of the worked example; hourly result must be below the seasonal-HSPF result in both cities | 1e-3; inequality |
| HVAC-07 | `ieer_from_points(11.0, 12.5, 13.4, 12.8)` = 12.722 | 1e-3 |
| DHW-01 | SI form against the °F form of the source on days 15, 105, 196, 288 | 0.002 K |
| DHW-02, DHW-03 | worked examples (52.83 gal, 7.025 kWh/day) | 1e-3 |
| LGT-01 | 2939 equivalent hours from the `DEF-09` lighting schedule; home example 1209 kWh/yr and factor 0.6051 | 1e-3 |
| LGT-03 | the interaction estimate of LGT-03 against the hourly result with its own shares | within 25 % |
| DEF tables | every table value loads from a data file whose rows carry the source key; a test checks low ≤ expected ≤ high for every row and that each imperial value converts to the SI value printed here | exact |

A schema test also checks that every `MeasureResult.formula_ids` entry is an ID that exists in this file.

## 10. Unverified, do not implement

Two tiers. Tier A items must not be implemented as sourced physics; where the pipeline needs a number, the item is a labelled placeholder and the result that depends on it carries a warning. Tier B items may be implemented; each names the residual check.

### Tier A: not sourced

| Item | Where it would be used | Why unverified | Effect |
|---|---|---|---|
| Distribution system efficiency of leaky ducts (ASHRAE Standard 152) | HVAC-08, `HVAC_DUCT` | standard paywalled; no open table of results found | `HVAC_DUCT` returns not applicable; baseline uses an upper-bound DSE |
| Attenuation of roof solar gain by a vented attic | ENV-05, `ROOF_COOL` on homes | ISO 13790 says a correction is needed but gives none; ISO 6946 roof-space resistances not opened | `ROOF_COOL` on a vented-attic home is an upper bound, shown with a warning |
| ISO 13370 monthly ground heat flow with phase lag, and edge-insulation correction | ENV-04 | standard paywalled; RdSAP reproduces only the steady U-value | ground loss follows outdoor air temperature hour by hour |
| ISO 13790 loss utilisation factor for cooling (monthly method) | ZON-06 | equations illegible in the open text | no monthly cross-check for cooling |
| Mapping of ISO 13790 mass classes to US construction types | ZON-01 | the standard gives classes only | medium for all, light and heavy as the range |
| Window-to-wall ratio defaults (0.15 / 0.18 / 0.25 homes, 0.20 / 0.30 / 0.40 offices) | DEF-03, only when there are neither measured openings nor a vision reading | not sourced | result flagged; the ask rule of the master spec should fire |
| Office lighting power density after an LED retrofit (6.5 W/m²) and any 90.1 or Title 24 value after 2004 | DEF-10, `LGT_LED` | ASHRAE 90.1-2010 and later and Title 24 Part 6 lighting tables not opened | `LGT_LED` target is a measure parameter that the finance and measure library must source |
| Savings fractions for lighting controls, the plug-load floor for `PLUG_MGMT`, the leakage reduction for `ENV_AIRSEAL`, the setback depth for `CTRL_TSTAT` | LGT-01, LGT-02, DEF-04, DEF-08 | no source opened | each is a measure parameter; this file gives only the physics that turns the parameter into energy |
| Economizer high-limit temperatures and economizer requirements by climate zone (ASHRAE 90.1 section 6.5.1) | INF-06 | paywalled | `theta_limit` is a parameter; a default of 21 °C was used only in the worked example |
| Maximum outdoor air flow default of 0.005 m³/s per m² | INF-06 | engineering figure, not sourced | take the unit's supply air flow from the equipment record when known |
| Furnace blower electricity | HVAC-06 | no sourced value opened (S10 Table 36 exists and was not read) | omitted; conservative for `HVAC_HP` |
| Hourly incidence-angle model for glazing | WIN-01 | deliberately not used; the EnergyPlus correlations need 28 bins of coefficients | constant `F_w` = 0.90 |
| ASHRAE Standard 140 test cases | section 9 | paywalled | replaced by the S2 published cases and an optional EnergyPlus comparison |
| Hourly schedule by tenant industry | DEF-09 | no source opened | default office schedule for every tenant |

### Tier B: implement, with a named residual check

| Item | Entry | Status | Residual check |
|---|---|---|---|
| ISO 13790 Annex C equations (C.1) to (C.13), and eq. (63) | ZON-01 to ZON-04 | clause text, constants and tables read in the open adoption; equations taken from open implementations, confirmed by an independent derivation and by published test values | compare once against a licensed copy of the standard if the team has one |
| ISO 6946 surface resistances and combined method | ENV-01, ENV-02 | from BR 443, not from the standard | none needed for US table values |
| ASHRAE basic-model coefficient tables | INF-03 | from EnergyPlus documentation, which cites the Handbook; stack coefficient confirmed from the original paper, wind coefficients not independently confirmed | spot-check one wind coefficient against the Handbook if available |
| Office outdoor air and infiltration | INF-05 | single source (S11) | compare with the tenant's or owner's ventilation records where they exist |
| Latent load constants (`h_fg` = 2.50e6 J/kg, indoor humidity ratio 0.0093) and water properties (990 kg/m³, 4180 J/(kg·K)) | INF-07, DHW-03 | standard property values, not read from an opened table | check against any steam table or psychrometric chart; expected error under 2 % |
| Interior shading coefficients; film 0.70 and screen 0.30 | WIN-02 | from S13, which cites the ASHRAE Handbook and the MulTEA manual; originals not opened; film and screen values single-sourced | use the manufacturer's rated SHGC for a specific film |
| SEER2, EER2, HSPF2 conversion factors | HVAC-01 | from S13, citing RESNET 301-2022 Addendum C; consistent with the federal minimum pairs | none |
| Applying a gross-input curve to net ratings | HVAC-02, HVAC-03 | approximation, calibrated so the nameplate SEER is reproduced | compare one unit against its manufacturer's expanded performance table |
| HSPF to `COP_47` mapping | HVAC-05 | single source (S14 Table 11), three points | use the certified `COP_47` whenever the product is known |
| IEER weights | HVAC-07 | from a manufacturer's newsletter restating AHRI 340/360, plus the federal definition | compare with AHRI 340/360 if obtainable |
| Unweighted averaging of ResStock distributions over income, tenure and floor-area bins; "equipment has been replaced" rule; furnace vintage split; ±30 % on hot water volume | DEF-01, DEF-03, DEF-04, DEF-05, DHW-02 | simplifications and judgments of this file, stated where used | replace with a weighted calculation or with observed data |
| R-7 attic U-value (0.61 W/(m²·K)) | DEF-01 | interpolated in resistance between the published "none" and R-11 rows | recompute with ENV-01 and ENV-02 from the layers |
| Plug-load scaling by tenant head count | LGT-02 | design choice | review after the first office run |
| Imperial and SI versions of S11 tables disagree for small-office plug load (0.8 W/ft² against 10.76 W/m²) and ventilation flow | DEF-10, INF-05 | discrepancy inside the source | both values carried as the range |

## 11. Verification log

Pass 1 was the writing of each entry from the opened source. Pass 2 re-opened the source passage, checked each term and its units, and re-ran every worked example. Dates: S2, S3 (City Energy Analyst), S7, S8, S9 and S15 (10 CFR 430) were first downloaded on 2026-11-13; the other sources were downloaded on 2026-11-14; everything was read, checked and recomputed on 2026-11-14. Scripts are in the scratch directory outside the repository (`zon.py`, `env.py`, `inf.py`, `hvac.py`, `dhw.py`, `econ.py`, `rs.py`, `rs2.py`), run with Python 3.12, numpy and scipy.

| Entry | Primary source | Second source | Checked | Result | How the example was recomputed |
|---|---|---|---|---|---|
| ENV-01 | ISO 6946 via S5 §4.1 | S6 Table 4.1.1 | 2026-11-14 | pass | `env.py`: imperial sum then convert; layer-by-layer SI sum; both 0.2778 |
| ENV-02 | ASHRAE parallel path via S6 JA4.1.2 | S5 §3.1 (combined method) | 2026-11-14 | pass; published 0.065 reproduced (0.0648) | `env.py`: imperial and SI routes; ISO combined value computed separately |
| ENV-03 | S1 §8.3.1 | S9 eq. (4) | 2026-11-14 | pass | `env.py` and by hand |
| ENV-04 | ISO 13370 via S7 §5.12 | S8 F-factor method with S6 Table 4.4.7 | 2026-11-14 | formula pass; the two methods differ by 25 % on the example and both are carried as the range | `env.py`: `math.log` and `numpy.log1p` forms; F-factor route |
| ENV-05 | S1 §11.3.4, §11.3.5, §11.4.6 | S8 outside surface heat balance; S3 | 2026-11-14 | pass; linear form 5 to 7 % above a non-linear balance | `env.py`: sol-air route, ISO route, closed-form difference, root-finding on the non-linear balance |
| ENV-06 | ISO 6946 via S5 §4.1 | S6 (ASHRAE films) | 2026-11-14 | pass | `patch.py` arithmetic check: 7.692, 8.350, 25.0, 33.4; glass temperature 11.54 and 12.28 °C |
| ZON-01 | S1 §7.2.2.2, §12.2.2, Table 12 | S2, S3 constants | 2026-11-14 | pass; eq. (63) from S3 only | `env.py` |
| ZON-02 | S1 Annex C.2 | S3 | 2026-11-14 | pass | `env.py`; sum of parts checked against the total |
| ZON-03 | S1 Annex C.3 via S2 | independent nodal derivation | 2026-11-14 | pass; closed form equals 3×3 linear solve | `zon.py` `step` against `direct_solve` |
| ZON-04 | S1 Annex C.4.2 via S2 | S2 published test values | 2026-11-14 | pass; four published cases reproduced to the published digits | `zon.py` |
| ZON-05 | network topology | hourly model iterated to steady state | 2026-11-14 | pass; 3588.660 W both ways | `env.py` |
| ZON-06 | S1 §12.2.1.1, Table 9 | S9 §2.5 eqs. (11) to (14) | 2026-11-14 | pass for heating; cooling form not verified (tier A) | `env.py`: monthly formula against the hourly model on the same month (6.6 % apart) |
| INF-01 | S1 §9.3.1 | S9 (0.34 Wh/(m³·K)) | 2026-11-14 | pass | `inf.py`, two routes |
| INF-02 | S12 App. II eqs. (II.1) to (II.3) | S11 (exponent 0.65), S8 (0.6 to 0.7) | 2026-11-14 | pass | `inf.py`: SI route; imperial route reproduces 0.055 in² per cfm50 |
| INF-03 | S8 Eng. Ref. and I/O Ref. | S12 eqs. (3.1), (3.2), (7) | 2026-11-14 | pass; stack coefficient re-derived (0.000144 against 0.000145) | `inf.py`: handbook-unit form and original SI form (0.2 % apart) |
| INF-04 | S12 eq. (13) | S10 §2.1.6 | 2026-11-14 | pass | `inf.py` |
| INF-05 | S11 §5.1.2, Tables 5 and 6, infiltration section | none | 2026-11-14 | single-sourced (tier B) | `inf.py`; 0.508 L/(s·m²) against the table's 0.51 |
| INF-06 | S8 I/O Ref. `Controller:OutdoorAir` | S1 §7.2.2.1 | 2026-11-14 | logic pass; limit values not sourced (tier A) | `econ.py`, three hours |
| INF-07 | S8 moisture balance | none opened | 2026-11-14 | balance pass; constants tier B | `inf.py` |
| WIN-01 | S1 §11.3.2, §11.3.3, §11.4.2 | S3; S8 simple window model | 2026-11-14 | pass | `hvac.py`: direct product and effective-area route |
| WIN-02 | S13 interior and exterior shading | S10 §4.2.2 | 2026-11-14 | pass; film and screen single-sourced (tier B) | `hvac.py` |
| HVAC-00 | S10 Table 6; S11 Tables 29, 30 | none | 2026-11-14 | defaults read from the sources; the no-rooftop-unit rule is a design rule, not physics | no numeric example |
| HVAC-01 | unit conversion; S13 | S15 §430.32(c) | 2026-11-14 | pass | `hvac.py`: multiply by 0.293071 and divide by 3.412142 |
| HVAC-02 | S14 Table 17, eq. (16) | S14 Table 6; S13 regression | 2026-11-14 | pass; three mappings within 4 % | `hvac.py` |
| HVAC-03 | S14 | S8 DX coil model | 2026-11-14 | pass; self-consistency returns SEER 10.000 | `hvac.py`, two routes |
| HVAC-04 | SEER definition | S14 §6 | 2026-11-14 | pass; test procedure text not opened | `hvac.py` |
| HVAC-05 | S14 Tables 11, 19 | S15 (metric only) | 2026-11-14 | curve pass; mapping single-sourced (tier B) | `hvac.py` |
| HVAC-06 | S15 §430.32(e) | S10 | 2026-11-14 | pass | `hvac.py` |
| HVAC-07 | AHRI 340/360 via S16 | S15 §431.92, §431.97 | 2026-11-14 | pass; standard itself not opened (tier B) | `hvac.py`; by hand 0.220 + 7.7125 + 3.1892 + 1.600 |
| HVAC-08 | S10 §2.1.3, §3.1.3 | S17 Table 112 | 2026-11-14 | definition pass; DSE values not sourced (tier A) | `hvac.py` |
| DHW-01 | S10 eq. (21) | S8 water mains correlation | 2026-11-14 | pass; two sources identical | `dhw.py`: °F form and SI form on four days |
| DHW-02 | S10 Table 11 | S15 App. E draw patterns | 2026-11-14 | pass | `dhw.py`: hot fraction in °C and in °F |
| DHW-03 | energy balance; S15 App. E | S10 §3.1.4 | 2026-11-14 | pass; property constants tier B | `dhw.py`: SI and imperial routes (7.025 and 7.024 kWh) |
| LGT-01 | S11 Tables A-2, B-13; S10 eqs. (6), (7), (10) | S13 schedules | 2026-11-14 | pass | `dhw.py` |
| LGT-02 | S11; S10 Table 25 | S13 | 2026-11-14 | pass; S11 internal discrepancy noted | `dhw.py` |
| LGT-03 | S10 Tables 25, 48, eqs. (23), (24) | S1 §10; S8 zone internal gains | 2026-11-14 | pass | `dhw.py` and by hand |
| DEF-01 | S17 tsv; S6 Tables 4.2.1, 4.3.1 | S10 Tables 29, 30 | 2026-11-14 | pass; R-7 values computed or interpolated (tier B) | `rs.py`; conversions by script; ENV-02 reproduces the published R-11 and R-13 walls |
| DEF-02 | S10 Table 33, Table 5 | S13 roof colour defaults | 2026-11-14 | pass | read directly |
| DEF-03 | S17 Table 69 and `Windows.tsv` | S11 Tables 24, 25 (offices) | 2026-11-14 | pass; first draft used modal types and was replaced by the percentile calculation | `rs2.py` |
| DEF-04 | S17 `Infiltration.tsv` | S10 (benchmark 7 ACH50) | 2026-11-14 | pass | `rs.py` |
| DEF-05 | S10 Tables 34, 35; S15 | S11 Tables 31, 34 | 2026-11-14 | pass; replacement rule is a judgment (tier B) | conversions by script |
| DEF-06 | S17 `Duct Leakage and Insulation.tsv`, Table 112 | S10 (benchmark 15 % leakage) | 2026-11-14 | pass | `rs.py` |
| DEF-07 | S15 §430.32(d) | S10 Table 37 | 2026-11-14 | pass | `dhw.py` |
| DEF-08 | S10 §4.2 | S11 Table B-13 | 2026-11-14 | pass | conversions by script |
| DEF-09 | S11 Table B-13; S13 default schedules | none | 2026-11-14 | pass; each home row sums to 1.000; office sums 10.50, 2.80, 1.20 | `dhw.py` and by hand |
| DEF-10 | S11 Table A-2 | S11 Table A-1 | 2026-11-14 | pass with the noted discrepancy; LED value not sourced (tier A) | conversions by script |
| DEF-11 | S11 Tables 17 to 25 | none | 2026-11-14 | single-sourced | conversions by script |

Corrections made during pass 2: the zone examples were first computed with 1211 J/(m³·K) and were redone with the standard's 1200; a from-memory branch of the utilisation factor was removed; the window default table was recomputed from percentiles; an arithmetic slip in the interpolated R-7 attic value (0.71) was corrected to 0.61; the Building America lighting equation numbers were corrected to (6) and (7).

## 12. Contract notes for `specs/SPEC.md`

Checked against section 9 of the master spec at `SCHEMA_VERSION = "0.3.0"` on 2026-11-14. Nothing is changed here; these are requests to the spec owner.

**Already in the contract and used by this file as they are:** `Opening` (`type`, `width_m`, `height_m`, `lower_elevation_m`, `relative_center`), `WallEdge.openings`, `WallEdge.thickness_m`, `Surface.source_edge_id`, `Surface.source_opening_id`, `Surface.shgc`, `Surface.u_value`, `BuildingModel.north_offset_deg` and `north_source`, `Systems.occupants`, `CostarData.year_built` and `year_built_event`, `CostarData.building_area_m2`, `CostarData.occupancy`, `ClimateSite.weather_time_convention`.

**Fields this file needs that the contract does not have** (exact name and type requested; all additive and optional):

| Class | Field | Type | Needed by |
|---|---|---|---|
| `Surface` | `solar_absorptance` | `Optional[Ranged] = None` | ENV-05, `ROOF_COOL` (opaque surfaces) |
| `Surface` | `emittance` | `Optional[float] = None` (default 0.90 when absent) | ENV-05 |
| `Surface` | `exposed_perimeter_m` | `Optional[float] = None` (floors with `boundary == "ground"`) | ENV-04 |
| `Zone` | `mass_class` | `Literal["very_light", "light", "medium", "heavy", "very_heavy"] = "medium"` | ZON-01 |
| `BuildingModel` | `bedrooms` | `Optional[int] = None` | DHW-02, LGT-02, LGT-03 |
| `Systems` | `infiltration_ach50` | `Optional[Ranged] = None` | INF-02 (homes) |
| `Systems` | `envelope_leakage_l_s_m2_75pa` | `Optional[Ranged] = None` | INF-05 (offices) |
| `Systems` | `cooling_rating` | `Optional[Ranged] = None` | HVAC-01 to HVAC-07 |
| `Systems` | `cooling_rating_metric` | `Optional[Literal["SEER", "SEER2", "EER", "EER2", "IEER"]] = None` | HVAC-01 |
| `Systems` | `heating_rating` | `Optional[Ranged] = None` | HVAC-05, HVAC-06 |
| `Systems` | `heating_rating_metric` | `Optional[Literal["HSPF", "HSPF2", "AFUE", "COP"]] = None` | HVAC-01 |
| `Systems` | `compressor_type` | `Literal["single", "two_stage", "variable", "unknown"] = "unknown"` | choice between HVAC-03 and HVAC-04 |
| `Systems` | `cooling_capacity_w` | `Optional[float] = None` | HVAC-03 (part-load ratio) |
| `Systems` | `heating_cop_47f` | `Optional[float] = None` | HVAC-05 |
| `Systems` | `hvac_install_year` | `Optional[int] = None` | DEF-05 |
| `Systems` | `distribution_efficiency` | `Optional[Ranged] = None` | HVAC-08 |
| `Systems` | `duct_location` | `Literal["conditioned", "attic", "garage", "crawlspace", "none", "unknown"] = "unknown"` | HVAC-08, DEF-06 |
| `Systems` | `outdoor_air_m3_s` | `Optional[Ranged] = None` | INF-05 |
| `Systems` | `has_economizer` | `Optional[bool] = None` | INF-06, `HVAC_ECON` |
| `Systems` | `economizer_limit_c` | `Optional[float] = None` | INF-06 |
| `Systems` | `heating_setpoint_c`, `cooling_setpoint_c` | `Optional[Ranged] = None` each (occupied values) | ZON-04, DEF-08 |
| `Systems` | `heating_setback_c`, `cooling_setup_c` | `Optional[float] = None` each (unoccupied values) | ZON-04, `CTRL_TSTAT` |
| `Systems` | `dhw_location` | `Literal["conditioned", "garage", "outdoor", "unknown"] = "unknown"` | DHW-03, `DHW_HPWH` |
| `BaselineResult` | `heating_need_kwh`, `cooling_need_kwh` | `float` each (zone need before equipment) | ZON-04, tests of section 9 |
| `BaselineResult` | `latent_cooling_kwh` | `float = 0.0` | INF-07 |
| `BaselineResult` | `hourly_path` | `Optional[str] = None` (file with the hourly outputs listed in ZON-04: `theta_air_c`, `theta_s_c`, `theta_op_c`, `phi_hc_w`, `mode`, `q_ve_m3_s`) | physics 03 |

Also requested: make `Systems.hvac_type` a closed list, `Literal["central_ac_furnace", "heat_pump", "rooftop_unit", "room_ac", "central_plant", "none", "unknown"]`, and `Systems.dhw_type` `Literal["storage", "tankless", "heat_pump", "unknown"]`.

**Meanings to state in the contract (no new field):**

1. `Systems.infiltration_ach` is the annual mean natural air change rate that the model reports, not an input. Inputs are the two leakage fields above.
2. `Systems.cooling_cop` and `Systems.heating_efficiency` are seasonal values in W/W (or the AFUE fraction), derived by HVAC-01 from the rating fields above. When only these two are filled, the model can use only the seasonal method (HVAC-04, HVAC-05 fallback, HVAC-06).
3. `Systems.dhw_efficiency` is a uniform energy factor (or the older energy factor, treated as equal, DEF-07).
4. `Systems.occupancy_schedule` keys into `DEF-08` and `DEF-09` of this file: `"home"`, `"office"`, `"office_vacant"`.
5. `BaselineResult.end_use_kwh` keys: `heating`, `cooling`, `water_heating`, `lighting`, `plug`, `appliances`. Furnace fan energy is not modelled. `peak_cooling_w` and `peak_heating_w` are indicative (ZON-00).
6. `ClimateSite.weather_path` must supply, hourly: dry-bulb temperature, humidity ratio (or dew point and pressure), wind speed, and if available sky temperature or horizontal infrared radiation. Plane irradiance comes from physics 01 (IRR-10).
7. A window `Surface` is built from an `Opening` with `type == "window"`. A `"doorway"` on an exterior edge becomes a `door` surface. Still open on the Data lane and immaterial here: which vertex `relative_center` is measured from.
8. `rentable_area_m2` must not be used in physics. Envelope and loads use measured Matterport areas for the scanned unit and `building_area_m2` for whole-building scaling.
9. `MeasureResult.formula_ids` are the entry IDs of this file (`ENV-01` … `DEF-11`).

**Measure library, section 6.2:**

- `HVAC_DUCT` cannot be evaluated to the required standard (section 10, tier A). Either drop it from P1 or accept `applicable = false` with the stated reason until a source for distribution efficiency is obtained.
- `ROOF_COOL` on a home with a vented attic returns an upper bound with a warning. On low-slope roofs it is fully supported. Its physics modules are "envelope, sol-air, zone model".
- `LGT_LED` (offices), `LGT_CTRL`, `PLUG_MGMT`, `ENV_AIRSEAL` and `CTRL_TSTAT` each need one parameter that this file could not source (target power density, control saving fraction, plug floor, target ACH50, setback depth). The measure library must carry each with its own citation.
- `HVAC_HP` needs the proposed product's SEER2, HSPF2 and, where possible, its certified COP at 47 °F.
- `HVAC_RTU` and `HVAC_ECON` are returned as not applicable when no packaged unit is confirmed (HVAC-00). That is the case on the golden office until interior vision or the user confirms the system.
- `HVAC_ECON`: the saving is reported net of the added latent load (INF-06, INF-07).
- `DHW_HPWH` assumes the heater is outside the conditioned space.
- Section 13 lists `HVAC_HP` or `HVAC_RTU` in P0. For the golden office, P0 can rely on `HVAC_RTU` only if the system type is confirmed; otherwise the P0 office measures from this file are `LGT_LED` (with a sourced target), `ENV_ATTIC`, `ENV_AIRSEAL` and `ROOF_COOL`.

**Assumption registry, section 5:** section 5.1 says the vintage tables are in `physics.md`; they are in section 8 of this file. Suggested keys: `wall.u_value`, `roof.u_value`, `roof.absorptance`, `floor.ground_conductivity`, `window.type`, `window.u_value`, `window.shgc`, `window.area_m2`, `window.interior_shading`, `window.f_w`, `infiltration.ach50`, `infiltration.exponent`, `infiltration.shelter_class`, `zone.mass_class`, `hvac.system_type`, `hvac.cooling_rating`, `hvac.heating_rating`, `hvac.install_year`, `hvac.cd`, `hvac.distribution_efficiency`, `dhw.uef`, `dhw.volume_factor`, `lighting.lpd`, `plug.ppd`, `occupancy.count`, `setpoint.heating`, `setpoint.cooling`. Section 5.2 should say that windows come from `WallEdge.openings` first and from vision second.

**Office occupancy:** when `CostarData.occupancy` gives employees, `Systems.occupants` drives ventilation (INF-05), occupant gains (LGT-03) and, by a design rule, plug load (LGT-02). A suite with no current tenancy is modelled as vacant (`"office_vacant"`); the master spec should say whether a vacant suite is a valid audit target.

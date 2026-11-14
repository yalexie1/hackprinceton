# Physics 03: daylight, glare, thermal comfort, lighting credit

Status: draft, written and checked 2026-11-14. Owner: @yalexie1 (Analysis lane).
Feeds: `LAYOUT` measure (SPEC.md section 6.4), the daylight part of `LGT_CTRL`, tool `score_desk_positions`, work package A5.

Entry ID prefixes: `DAY-nn` daylight at a point, `GLR-nn` glare, `CMF-nn` thermal comfort, `LCT-nn` lighting credit and desk score.

Tags follow SPEC.md: **[V]** checked against the named source on 2026-11-14, **[P]** pending, **[U]** unverified. Every worked example below was recomputed by a script that was run; section 7 lists how. Anything that could not be opened in primary or authoritative form is in section 6 and must not be implemented from this file.

What this method is and is not. It is a geometric daylight-factor method with a split-flux interreflection term, an illuminance-based glare index and the ISO 7730 comfort model. It needs no ray tracer and no photometry. It does not model furniture, internal partitions, blinds, specular reflections, or the bright sky region around the sun. Those limits are stated in each entry.

## 0. Conventions and inputs

### 0.1 Units and symbols

SI throughout. Angles in degrees at tool boundaries and radians inside formulas unless stated. Illuminance in lux (lx = lm/m2), luminance in cd/m2, irradiance in W/m2, temperature in degrees C (K where a fourth power appears).

| Symbol | Meaning | Unit |
|---|---|---|
| `E_dh`, `E_dn`, `E_gh` | outdoor diffuse horizontal, direct normal, global horizontal illuminance | lx |
| `Dh`, `I`, `I0` | diffuse horizontal, direct normal, extraterrestrial normal irradiance | W/m2 |
| `gamma` | altitude of a sky element above the horizon | rad |
| `h`, `A_s` | sun altitude; sun azimuth (0 = north, clockwise) | deg |
| `A_w` | azimuth of a window's outward normal (0 = north, clockwise) | deg |
| `tau` | visible transmittance of the glazing for diffuse light | - |
| `M` | maintenance (dirt) factor of the glazing | - |
| `k_f` | glazed fraction of the measured opening (1 minus frame and bars) | - |
| `tau_eff` | `tau * M * k_f` | - |
| `DF`, `SC`, `ERC`, `IRC` | daylight factor and its components, as fractions (multiply by 100 for %) | - |

### 0.2 Geometry inputs and where they come from

| Input | Primary source | Fallback | Contract |
|---|---|---|---|
| Room polygon, ceiling height | scan: `Room.polygon` (ordered list of x, y in the model frame), `Room.height_m`; wall edges through `Room.boundary_edge_ids` | `Room.width_m`, `Room.depth_m` as a rectangle | `Room`, `WallEdge` |
| Window rectangle: width, height, sill height, position along the wall | scan: `WallEdge.openings[]` with `type == "window"`, fields `width_m`, `height_m`, `lower_elevation_m`, `relative_center` (source `measured`); a window `Surface` points back to them through `source_edge_id` and `source_opening_id` | vision-read window count and size (source `vision`), placed centred on the wall segment, sill 0.9 m, with the size range widened to plus or minus 25 % (placement, sill and width of range are design choices; `source_opening_id` is then `None`) | `Opening`, `Surface` |
| Window orientation | `MatterportData.georeference` rotation, carried as `BuildingModel.north_offset_deg` with `north_source = "georeference"` | `north_source = "footprint_registration"` or `"assumed"`, with the wider `north_offset_deg` range | `BuildingModel` |
| Glazing transmittance, reflectances, obstructions, any photometry | not measured: assumptions, table in 0.4 | | `Assumption` |

Opening types. `Opening.type` is one of `"divider"`, `"doorway"`, `"opening"`, `"window"`; only `"window"` means glazing, and only those become daylight apertures here. [V] Data lane, 2026-11-14, on the golden house: window sills 0.63 to 1.11 m, widths 0.51 to 2.69 m, heights 0.91 to 1.49 m. A model whose wall graph has no `"window"` openings uses the vision fallback. The tool must run on either source and report which one it used in `LayoutResult.window_source` (`"measured"` or `"vision"`).

Opening to rectangle. For an opening on the wall edge between vertices `a` and `b` (model frame, metres) with edge length `L = |b - a|`: `relative_center` is a dimensionless fraction of the edge length in [0, 1], not metres, and the centre lies `relative_center * L` metres along the edge [V] Data lane, 2026-11-14, on 41 real openings. Which end it is measured from is [P] Data lane; this file writes the centre as `a + relative_center * (b - a)` with `a` the first of `WallEdge.vertex_ids`, and the other reading is `b + relative_center * (a - b)`. The two agree only at 0.5. The window spans `width_m / 2` each side of the centre along the edge, from `z1 = lower_elevation_m` to `z2 = z1 + height_m` above the floor. Example: `a = (2, 1)`, `b = (6, 1)`, `L = 4.0 m`, `relative_center = 0.3`: the centre is 1.2 m from the reference vertex, at `(3.2, 1)` from `a` or at `(4.8, 1)` from `b`. Until the end is confirmed, a mistake mirrors every off-centre window along its wall: the room-wide `IRC` (DAY-05) is unaffected, but `SC`, glare and comfort at a point are not.

Wall frame used by every formula below. For each window: `e_n` is the horizontal outward unit normal, `e_t` is the horizontal unit vector 90 degrees clockwise from `e_n` seen from above (to the right of someone inside looking out), `e_z` is up. A point has coordinates `(u, d, z)`: `u` along `e_t`, `d >= 0` the perpendicular distance from the glass plane into the room, `z` the height above the floor.

Azimuth. `BuildingModel.north_offset_deg` is the azimuth of the model frame's +y axis, in degrees clockwise from true north (SPEC.md section 9; physics 01 ROOF-02). For a horizontal vector `(n_x, n_y)` in the model frame:

```
azimuth_in_model = degrees(atan2(n_x, n_y)) mod 360          clockwise from model +y
azimuth_true     = (azimuth_in_model + north_offset_deg) mod 360
```

`A_w` is `azimuth_true` of a window's outward normal `e_n`; `A_v` is `azimuth_true` of the view direction. Sun azimuth `A_s` from physics 01 is already true. Which way the Matterport quaternion rotates, and hence the sign of the value that arrives in `north_offset_deg`, is [P] Data lane (ROOF-02); this file only consumes the contract value.

Worked example: outward normal `(0, -1)` in the model frame, `north_offset_deg = 30`. `azimuth_in_model = 180`, `A_w = 210`. With the sun at `A_s = 230`, `Delta = A_s - A_w = 20` degrees (the first row of the GLR-04 example). Normal `(1, 0)`: `azimuth_in_model = 90`, `azimuth_true = 120`. Checked three ways: the formula, an explicit east-north basis for the model axes, and `scipy.spatial.transform.Rotation`; they agree to 1e-13 degrees on 1000 random cases. A sign error is not small: subtracting the offset would give `A_w = 150` and `Delta = 80` in the first case.

### 0.3 Reference heights (configuration, `backend/config.py`)

| Constant | Value | Basis |
|---|---|---|
| `WORKPLANE_HEIGHT_M` | 0.85 | reference plane 0.85 m above the floor: UK National Annex of BS EN 17037 as quoted in S9, and the BR 209 working plane for housing as quoted in S4 [V as quoted] |
| `EYE_HEIGHT_SEATED_M` | 1.20 | seated view position in the DGP validation rooms, Wienold 2009 (S7) [V] |
| `BODY_CENTRE_SEATED_M` | 0.60 | seated abdomen height; convention attributed to ISO 7726 [U], used only as the evaluation height |
| `DESK_GRID_M`, `WALL_CLEARANCE_M` | 0.5, 0.6 | SPEC.md 6.4 |
| `AREA_PER_DESK_M2` | 8 | design choice, used only when the zone gives no desk count (LCT-02) |
| `SCORE_WEIGHTS`, `G_MAX`, `PPD_MAX` | (0.4, 0.3, 0.3), 0.20, 25 | design choice (LCT-03) |
| `OCCUPIED_HOURS` | 08:00 to 18:00 local, Monday to Friday, unless `Systems.occupancy_schedule` says otherwise | design choice |

### 0.4 Assumption keys (not measured; low / expected / high)

These are design ranges for the assumption registry, not measured facts. "Basis" says what was checked.

| Key | Low | Expected | High | Basis |
|---|---|---|---|---|
| `glazing.visible_transmittance` (`tau`) | 0.40 | 0.68 | 0.80 | 0.68 is the "BRE standard" diffuse visible transmittance quoted in S4 [V as quoted]; bounds are a design range [U] |
| `glazing.maintenance_factor` (`M`) | 0.70 | 0.90 | 1.00 | S3 gives 0.5 to 0.9 [V]; expected and high are a design choice |
| `glazing.glazed_fraction` (`k_f`) | 0.65 | 0.80 | 0.90 | design range [U]; BR 209 asks for net glazed area (S4) |
| `interior.reflectance_ceiling` | 0.60 | 0.70 | 0.85 | design range [U] |
| `interior.reflectance_walls` | 0.30 | 0.50 | 0.70 | design range [U] |
| `interior.reflectance_floor` | 0.10 | 0.20 | 0.40 | design range [U] |
| `interior.reflectance_glass` | 0.10 | 0.10 | 0.10 | "use 0.1 as reflectance for glass", S3 [V] |
| `site.ground_reflectance` (`rho_g`) | 0.10 | 0.20 | 0.30 | design range [U]; the BRE numeric formula implies 0.10 (DAY-05) |
| `site.obstruction_angle_deg` (`theta_o`) | 0 | 10 | 30 | design range [U]; replace with a value from Vexcel neighbouring structures when available |
| `site.obstruction_reflectance` (`rho_o`) | 0.10 | 0.20 | 0.40 | design range [U] |
| `glazing.solar_transmittance` (`T_sol`) | from `Surface.shgc` | | | SHGC approximates `T_sol` and over-predicts gain on the occupant, Arens 2015 (S12) [V] |
| `comfort.met` | 1.0 | 1.2 | 1.4 | 1.2 met is the sedentary case of the ISO 7730 validation table (S11) [V as used there] |
| `comfort.clo_heating`, `comfort.clo_cooling` | | 1.0, 0.5 | | same table [V as used there] |
| `comfort.air_speed_m_s`, `comfort.rh_percent` | | 0.1, 50 | | design choice |
| `comfort.shortwave_absorptivity` | 0.57 | 0.70 | 0.84 | range and default in the reference implementation of SolarCal (S11) [V]; Arens gives about 0.67 (S12) |
| `comfort.floor_reflectance_solar` | 0.2 | 0.6 | 0.6 | 0.6 is the default behind the ASHRAE 55 table values (S11) [V]; Arens uses 0.5 in examples (S12) |
| `comfort.body_exposed_fraction` (`f_bes`) | 0.2 | 0.5 | 1.0 | 0.5 for a person at a desk in an Arens example (S12) [V]; range is a design choice |
| `lighting.setpoint_lux` | 300 | 500 (office), 300 (home desk) | 500 | DAY-10 |
| `lighting.control_type` | | `none` | | LCT-02 |
| `lighting.manual_switch_fraction` (`k_m`) | 0 | 0.5 | 1.0 | placeholder with no source [U], LCT-02 |
| `lighting.min_light_fraction`, `lighting.min_power_fraction` | | 0.2, 0.3 | | design values for LCT-01 [U] |

Low, expected and high runs: run the whole chain three times with the daylight-unfavourable set, the expected set and the daylight-favourable set. Do not mix signs inside one run.

### 0.5 Hourly climate inputs (from physics 01, work package A1)

Per hour of the typical year: sun altitude `h` and azimuth `A_s`, `Dh`, `I`, global horizontal irradiance, `I0`, dew point `T_d`, outdoor dry bulb `T_out`. This file converts irradiance to illuminance itself (DAY-07) so that the result does not depend on optional illuminance columns in the weather file.

### 0.6 Reference room R0 (used by every worked example)

Room 4.0 m wide (along the window wall) by 6.0 m deep by 2.8 m high. One window centred on the 4.0 m wall: opening 2.0 m wide by 1.5 m high, sill 0.9 m, so `u` from -1.0 to 1.0 and `z` from 0.9 to 2.4. `tau = 0.68`, `M = 0.9`, `k_f = 0.8`, so `tau_eff = 0.4896`. Reflectances: ceiling 0.7, walls 0.5, floor 0.2, glass 0.1. `rho_g = 0.2`. No obstruction unless stated. Desk point P: on the window centreline, 2.0 m from the glass, on the work plane: `(u, d, z) = (0, 2.0, 0.85)`. Far point F: `(0, 5.0, 0.85)`. The window is comparable with what the scans return (golden house: sills 0.63 to 1.11 m, widths 0.51 to 2.69 m, heights 0.91 to 1.49 m). All examples are written in the wall frame, so none of their numbers depends on `north_offset_deg`.

### 0.7 Sources

| ID | Source | Access |
|---|---|---|
| S1 | Perez, Ineichen, Seals, Michalsky, Stewart (1990), "Modeling daylight availability and irradiance components from direct and global irradiance", Solar Energy 44(5) 271-289, doi:10.1016/0038-092X(90)90055-H | primary, scan from the University of Geneva open archive, read page by page |
| S2 | EnergyPlus 24.1 Engineering Reference, "Daylight Factor Calculation" and "Time-Step Daylighting Calculation" (bigladdersoftware.com/epx/docs/24-1/engineering-reference), and source `WeatherManager.cc` `DayltgLuminousEfficacy` | open, read in full |
| S3 | MIT OpenCourseWare 4.493 Natural Light in Design (2006), lecture "Daylight factor", slides 6 and 10 | open, slides read as images |
| S4 | Right of Light Consulting (2015), daylight and sunlight study, West End Lane, London NW6 (Camden planning record 5462872), quoting BR 209 (Littlefair 2011) and BS 8206-2 | open secondary reproduction of a paid guide |
| S5 | Bryan (1980), "A procedure for calculating interior daylight illumination with a programmable hand calculator", LBL-11186, escholarship.org/uc/item/2hq8p944 | open primary |
| S6 | Radiance source, `src/gen/gensky.c` and `src/gen/skybright.cal` (LBNL-ETA/Radiance) | open reference implementation |
| S7 | Wienold (2009), "Dynamic daylight glare evaluation", Building Simulation 2009, pp. 944-951 (AIVC copy) | open primary |
| S8 | Radiance `src/util/evalglare.c` (Wienold); and Atzeri, Cappelletti, Gasparella (2017), "Comparison of different glare indices through metrics for long term and zonal visual comfort assessment", Building Simulation 2017, pp. 1194-1199, doi:10.26868/25222708.2017.311 | open |
| S9 | Digital Dimensions (2024), daylight and sunlight assessments, Coolaghknock Glebe, Co. Kildare (Kildare County Council consultation file 8968, item 78), reproducing EN 17037:2018 Table A.1 and the Dublin row of Table A.3 | open secondary reproduction of a paid standard |
| S10 | Hraska and Curpek (2024), "The practical implications of the EN 17037 minimum target daylight factor for building design and urban daylight in several European countries", Heliyon 10, e23297 | open access |
| S11 | `pythermalcomfort` 4.8.1 (`pmv_ppd_iso`, `solar_gain`, `operative_tmp`) and its validation tables `ts_pmv_ppd.json`, `ts_solar_gain.json` (FedericoTartarini/validation-data-comfort-models), which transcribe table values labelled "ISO 7730 2005" and "ASHRAE 55 2017" | open reference implementation; the standards themselves are paid and were not opened |
| S12 | Arens, Hoyt, Zhou, Huang, Zhang, Schiavon (2015), "Modeling the comfort effects of short-wave solar radiation indoors", Building and Environment 88, 3-9, doi:10.1016/j.buildenv.2014.09.004 (eScholarship 89m1h2dg) | open primary |
| S13 | `ladybug-comfort` `pmv.py` (`fanger_pmv`, `ppd_from_pmv`) | open, second implementation |
| S14 | Howell, "A Catalog of Radiation Heat Transfer Configuration Factors", entries B-3 and B-4 (thermalradiation.net) | open |
| S15 | Marino, Misiani, Nucara, Pietrafesa (2017), "The effect of the climatic condition on the radiant asymmetry", Int. J. Heat and Technology 35, Special Issue 1, S419-S426, doi:10.18280/ijht.35Sp0157, reproducing the ISO 7726 plane radiant temperature method | open access; ISO 7726 itself not opened |
| S16 | Huizenga, Zhang, Mattelaer, Yu, Arens (2006), "Window performance for human thermal comfort", CBE report to NFRC, escholarship.org/uc/item/6rp85170, Table 4 | open |
| S17 | ASHRAE interpretation IC 55-2004-2 (27 Jan 2007) of Standard 55-2004 section 5.2.4.1 | open, issued by ASHRAE |
| S18 | Zhou, Liu, Luo, et al. (2019), "Thermal comfort under radiant asymmetries of floor cooling system in 2 h and 8 h exposure durations", Energy and Buildings 188-189, 98-110, doi:10.1016/j.enbuild.2019.02.009, Table 7 | open (eScholarship 8h49f5vr) |
| S19 | DIALux knowledge base, "Standard values for office interiors", reproducing EN 12464-1 | open secondary reproduction of a paid standard |
| S21 | Cannistraro, Cannistraro, Restivo (2015), "Some observations on the radiative exchanges influence on thermal comfort in rectangular open-space environments", Int. J. Heat and Technology 33(2), doi:10.18280/ijht.330213 | open access |
| S20 | Daylighting Pattern Guide, "Daylight Autonomy" (advancedbuildings.net) and VELUX "Designing with daylight", chapters 15 and 16 | open secondary |

Paid standards not opened: EN 17037:2018, EN 12464-1, ISO 7730:2005 and 2025, ISO 7726, ANSI/ASHRAE 55, IES LM-83, BR 209, BS 8206-2, CIE S 011 / ISO 15469. Paid papers not opened (the DOI of S1 and the Wienold and Christoffersen DOI were resolved on 2026-11-14 and return the stated papers; the Leukos DOI was not resolved): Wienold and Christoffersen (2006), Energy and Buildings 38, 743-757, doi:10.1016/j.enbuild.2006.03.017; Hopkinson, Longmore and Petherbridge (1954); Reinhart, Mardaljevic and Rogers (2006), Leukos 3(1), doi:10.1582/LEUKOS.2006.03.01.001. Where an entry depends on one of these, it says which open reproduction was read.

## 1. DAY: daylight at a point

### DAY-01 Daylight factor and its components [V]

```
DF = E_in / E_h = SC + ERC + IRC
```

- `E_in` illuminance at the interior point on the work plane, lx.
- `E_h` simultaneous illuminance on an unobstructed outdoor horizontal plane from the sky, direct sun excluded, lx.
- `SC` sky component (light straight from the sky), `ERC` externally reflected component, `IRC` internally reflected component. All dimensionless fractions.

Validity: defined for a sky without direct sun; here always the CIE overcast sky (DAY-02). With several windows, `SC`, `ERC` and `IRC` each add over windows.

Primary: Bryan 1980 (S5), the paragraph before its section 3, "Daylight Factor = SC + ERC + IRC", with the definition above. Second source: MIT OCW slides 8 to 10 (S3), "D [%] = E_P / E_h = sum of SC, ERC, IRC".

Worked example (R0, point P): `SC = 0.019944` (DAY-03), `ERC = 0` (DAY-04, no obstruction), `IRC = 0.005358` (DAY-05), so `DF = 0.02530`, that is 2.53 %. At the far point F: `DF = 0.001589 + 0.005358 = 0.00695`, 0.69 %.

Tool: `daylight_factor_point(point_xyz_m, room, windows, assumptions) -> {sc, erc, irc_sky, irc_ground, df}` (all fractions).

### DAY-02 CIE overcast sky [V]

```
L(gamma) = L_z * (1 + 2 sin(gamma)) / 3
E_h      = (7 pi / 9) * L_z
f_s0     = E_vert / E_h = (3 pi + 8) / (14 pi) = 0.39618
```

- `L(gamma)` sky luminance at altitude `gamma`, cd/m2; `L_z` zenith luminance, cd/m2.
- `E_h` horizontal illuminance from the whole sky, lx.
- `f_s0` ratio of the illuminance on an unobstructed vertical plane (sky only) to `E_h`. This is the "vertical sky component" of 39.6 %.

Derivation of the two integrals (dimensionally lx = cd/m2 times sr): `E_h = integral over the hemisphere of L sin(gamma) dOmega = 2 pi L_z/3 * (1/2 + 2/3)`; `E_vert = integral over the half hemisphere of L cos(gamma) cos(alpha) dOmega = (2 L_z / 3)(pi/4 + 2/3)`.

Validity: fully overcast sky; independent of sun position and of azimuth. The zenith is three times as bright as the horizon.

Primary: EnergyPlus Engineering Reference (S2), "Overcast Sky", citing Moon and Spencer 1942. Second source: Radiance (S6): `cloudysky = A2 * (1 + 2*Dz)/3` in `skybright.cal`, and `normfactor = 0.777778` (7/9) for the overcast sky in `gensky.c`. Third: S3 slide 2. CIE S 011 / ISO 15469 was not opened.

Worked example: `E_h = 10 000 lx` gives `L_z = 10 000 / 2.44346 = 4092.6 cd/m2`, horizon luminance 1364.2 cd/m2, luminance at 30 degrees 2728.4 cd/m2. Check: analytic `7 pi/9 = 2.443461` and numerical quadrature 2.443461; analytic `f_s0 = 0.396177` and numerical double quadrature 0.396177.

Tool: `cie_overcast_luminance(gamma_rad, e_h_lux) -> cd/m2`.

### DAY-03 Sky component at a point from a vertical rectangular window [V]

```
SC = tau_eff * (1 / E_h) * integral over the visible sky seen through the window of
         L(gamma) * sin(gamma) * dOmega
dOmega = dA * cos(B) / D^2
```

For a window element at `(u, 0, z)` and a point at `(u_p, d_p, z_p)`: `D = sqrt((u-u_p)^2 + d_p^2 + (z-z_p)^2)`, `sin(gamma) = (z - z_p) / D`, `cos(B) = d_p / D`. Elements with `z <= z_p` contribute nothing. With `L` from DAY-02 and `E_h = (7 pi/9) L_z`, `L_z` cancels.

Equivalent single integral (use this in code; it is exact in altitude):

```
SC = tau_eff * (9 / (7 pi)) * integral from phi_1 to phi_2 of [ G(s_hi(phi)) - G(s_lo(phi)) ] dphi
G(s)   = s^2 / 6 + 2 s^3 / 9
phi_i  = atan((u_i - u_p) / d_p)                 azimuth of the two window jambs from the normal
r(phi) = d_p / cos(phi)                          horizontal distance to the glass in direction phi
s(z)   = max(0, z - z_p) / sqrt(r^2 + max(0, z - z_p)^2)     s_lo uses z1 (or z_b, DAY-04), s_hi uses z2
```

- `tau_eff = tau * M * k_f`, dimensionless. `tau` is the diffuse visible transmittance, taken as constant with angle.
- All lengths in m, angles in rad, `SC` a fraction.

Validity and assumptions: vertical window, CIE overcast sky, point not in the glass plane (`d_p > 0`, in practice `d_p >= 0.6 m` from SPEC 6.4), thin wall (no reveal shading), no interior obstruction, constant `tau`. Constant `tau` overstates light arriving at grazing incidence, so points right under a window are slightly optimistic.

Primary: EnergyPlus Engineering Reference (S2), "Direct Component of Interior Daylight Illuminance": `dE_h = L_w dOmega cos(gamma)`, `dOmega = dx dy cos(B) / D^2`, summed over window elements. Note: that text also writes `L_w = L tau_vis cos(B)`, a second `cos(B)`; it is not adopted here because it breaks the flux check below. Second source: Bryan 1980 (S5) section 3.1, the overcast sky component as a function of sky luminance, window transmission and solid angle.

Worked example (R0, P): unglazed `SC` = 0.040734 by the single integral, 0.040735 by an 800 by 800 midpoint sum over the window plane. With `tau_eff = 0.4896`: `SC = 0.019944` (1.99 %). Far point F: unglazed 0.003246, glazed 0.001589.

Independent checks run:
1. Uniform sky instead of CIE: numeric 0.052805, closed-form configuration factor (Howell B-4 by corner superposition, S14) 0.052805.
2. Flux conservation: the integral of unglazed `SC` over the whole plane at sill height is 1.1872 m2 on a 400 m square against `A_open * f_s0 = 3.0 * 0.39618 = 1.1885 m2` (the remainder is the tail beyond 400 m).
3. Infinite vertical window, point at its foot: 0.5000, as symmetry requires.

Tool: `sky_component(point_udz_m, window_rect, tau_eff, obstruction_angle_deg=0) -> fraction`.

### DAY-04 External obstruction and externally reflected component [V geometry; P luminance rule]

No obstruction data is measured, so this entry is driven by the assumption `site.obstruction_angle_deg` (`theta_o`, the profile angle of a long obstruction parallel to the window, seen from the window).

```
z_b  = z_p + d_p * tan(theta_o)                 height on the glass below which the view is blocked
SC   : DAY-03 with z1 replaced by max(z1, z_b)
ERC  = tau_eff * k_obs * F_B4(blocked part of the window, z1 .. min(z2, z_b))
k_obs = rho_o * (f_s0 + 0.5 * rho_g)            so that L_obs = k_obs * E_h / pi
```

- `F_B4` is the configuration factor from a horizontal element to a perpendicular rectangle, defined in CMF-06, applied by corner superposition. Only the part of the window above the work plane counts.
- `L_obs` luminance of the obstruction, cd/m2: a diffuse vertical face of reflectance `rho_o` lit by the half sky (`f_s0 E_h`) and by the ground (`0.5 rho_g E_h`).

Validity and assumptions: the obstruction is far compared with the room depth (the same angle is used at the point as at the window), infinitely long, parallel to the window, diffuse. A blocked ray satisfies `tan(gamma) < tan(theta_o) cos(alpha)`, which for a point at perpendicular distance `d_p` is simply `z - z_p < d_p tan(theta_o)`.

Sources: the treatment "consider as sky component with different luminance" is S3 slide 9 [V]. The value of the obstruction luminance is derived here from first principles and is [P]: with `rho_o = 0.2` and `rho_g = 0.2`, `k_obs = 0.0992`, one tenth of the mean sky luminance `E_h / pi`, which is the classical BRE rule of thumb; that rule itself was not opened (section 6). Second source for the geometry: none beyond the numerical cross-check; treat `ERC` as an estimate with wide uncertainty.

Worked example (R0, P, `rho_o = 0.2`): 

| `theta_o` | `z_b` m | `SC` | `ERC` |
|---|---|---|---|
| 0 | 0.850 | 0.019944 | 0 |
| 10 | 1.203 | 0.018896 | 0.000198 |
| 20 | 1.578 | 0.015059 | 0.000783 |
| 30 | 2.005 | 0.007871 | 0.001693 |
| 40 | 2.528 | 0 | 0.002566 |

Each row computed two ways: split window with the DAY-03 integral plus Howell B-4, and a 2000 by 2000 ray-by-ray grid with the per-ray blocking test; they agree to 5e-6.

Tool: `externally_reflected_component(point_udz_m, window_rect, tau_eff, theta_o_deg, rho_o, rho_g) -> fraction`.

### DAY-05 Internally reflected component, split-flux method [V]

```
IRC = IRC_sky + IRC_ground
IRC_sky    = tau * M * A_g * f_s(theta_o) * R_fw / (A * (1 - R))
IRC_ground = tau * M * A_g * (0.5 * rho_g) * R_cw / (A * (1 - R))
```

- `A_g` net glazed area, m2 (`k_f` times the opening area). Sum over windows of the room.
- `A` total area of ceiling, floor and walls including windows, m2.
- `R` area-weighted mean reflectance of all those surfaces, glass at 0.1.
- `R_fw` area-weighted mean reflectance of the floor and the parts of the walls below the mid-height of the window, excluding the window wall.
- `R_cw` the same for the ceiling and the walls above the window mid-height, excluding the window wall.
- `f_s(theta_o)` window factor for sky light: ratio of the illuminance on the outside of the window from the sky (plus the obstruction, if any) to `E_h`. Unobstructed: `f_s0 = 0.39618` (DAY-02). With an obstruction at profile angle `theta_o`: `f_s = f_sky(theta_o) + k_obs sin(theta_o) / 2`, where `f_sky` is the DAY-02 vertical integral restricted to `tan(gamma) > tan(theta_o) cos(alpha)`, by quadrature. Values of `f_sky`: 0.3535, 0.3016, 0.2436, 0.1833, 0.1253 at 10, 20, 30, 40, 50 degrees.
- `0.5 rho_g` window factor for ground light (a horizontal ground plane fills half of the window's view).

This is the general form of the BRE formula `IRC[%] = 0.85 W / (A (1 - R)) * (C R_fw + 5 R_cw)`: `0.85` is the glass transmittance, `C = 100 f_s` (39 unobstructed), and `5 = 100 * 0.5 * rho_g` with `rho_g = 0.1`.

Validity and assumptions: the room acts as an integrating sphere, so `IRC` is one average value for the whole room. It is best for rooms near cubical with matte surfaces and no partitions; it becomes unreliable when the depth from the window wall exceeds three times the ceiling height (S2). It overstates light at the back of deep rooms. For L-shaped or open-plan rooms, apply it to the daylit zone within three ceiling heights of the window wall and report a warning.

Primary: Bryan 1980 (S5) eq. (4), `IRC = T W / (A (1 - R)) * (f_s R_fw + f_g R_cw) * 100 %`, with every symbol defined as above and `f_g = R_g * 0.5`. Second source: EnergyPlus Engineering Reference (S2), "Internally-Reflected Component": `E_r = (Phi_FW rho_FW + Phi_CW rho_CW) / (A (1 - rho))`, the same flux balance in lumens, citing Hopkinson et al. 1954 and Lynes 1968. Third: the BRE numeric form on S3 slide 10. Hopkinson, Longmore and Petherbridge (1954) was not opened.

Worked example (R0): `A = 2*24 + 2*(4+6)*2.8 = 104 m2`. `A_g = 0.8 * 3.0 = 2.4 m2`. Window mid-height 1.65 m. Walls excluding the window wall have perimeter 16 m: lower part 26.4 m2, upper part 18.4 m2. `R_fw = (24*0.2 + 26.4*0.5) / 50.4 = 0.3571`. `R_cw = (24*0.7 + 18.4*0.5) / 42.4 = 0.6132`. `R = (24*0.2 + 24*0.7 + 53*0.5 + 3*0.1) / 104 = 0.4654`. Prefactor `0.68*0.9*2.4 / (104 * 0.5346) = 0.02642`. `IRC_sky = 0.02642 * 0.39618 * 0.3571 = 0.003738`. `IRC_ground = 0.02642 * 0.1 * 0.6132 = 0.001620`. `IRC = 0.005358` (0.54 %).

Second computation, by lumens for `E_h = 10 000 lx`: sky flux in `0.68*0.9*2.4*0.39618*10 000 = 5819 lm`, ground flux in `1469 lm`, `E_r = (5819*0.3571 + 1469*0.6132) / (104*0.5346) = 53.58 lx`, that is 0.5358 % of `E_h`. Third: the BRE numeric form with its own constants (T = 0.85, C = 39, ground 0.1) gives 0.6235 % against 0.6316 % from the general form with the same inputs; the 1.3 % gap is the rounding of 39.62 to 39.

Check of `f_s(theta_o)` against the BRE coefficient table: `100 (f_sky + k_obs sin(theta_o)/2)` gives 39.6, 36.2, 31.9, 26.8, 21.5, 16.3 at 0 to 50 degrees, against table values 39, 35, 31, 25, 20, 14 that were seen only in a search-result excerpt of a BRS digest (section 6). `f_sky` was computed by double quadrature and by Monte Carlo (4 million cosine-weighted rays); they agree to 2e-4.

Tool: `internally_reflected_component(room, windows, reflectances, tau, m, rho_g, theta_o_deg, rho_o) -> {irc_sky, irc_ground}` (fractions).

### DAY-06 Average daylight factor (room-level sanity check only) [V]

```
ADF[%] = tau * M * A_g * theta / (A * (1 - R^2))
```

- `theta` vertical angle of visible sky from the centre of the window, degrees (90 for an unobstructed vertical window; `90 - theta_o` with an obstruction).
- Other symbols as DAY-05. The result is in percent as written; `theta` carries the unit.

Validity: empirical, for side-lit rooms of ordinary proportions; a room average on the work plane, not a point value.

Primary: BR 209 and BS 8206-2 as quoted in S4: "df = T A_w theta / (A (1 - R^2)) %", with T the diffuse visible transmittance, A_w the net glazed area, A the total area of the room surfaces, R their average reflectance, theta the angle of visible sky in degrees. Second source: S3 slide 6, the same formula with the maintenance factor `m` (0.5 to 0.9) written out.

Worked example (R0): `0.68 * 0.9 * 2.4 * 90 / (104 * (1 - 0.4654^2)) = 1.62 %`.

Use and limit: this is not a second computation of DAY-01. On R0 the mean of DAY-01 over a 0.25 m grid of the work plane is 2.48 % (median 1.10 %, range 0.62 to 19.2 %). The grid mean conserves flux (80.4 % of the sky lumens that enter land on the work plane inside the room, check 2 of DAY-03), so the two methods differ by a factor of about 1.5 on this room. Use `ADF` only as a coarse guard: flag the room if the grid mean of DAY-01 is outside 0.5 to 2.0 times `ADF`.

Tool: `average_daylight_factor(room, windows, reflectances, tau, m, theta_deg) -> percent`.

### DAY-07 Outdoor illuminance from irradiance: Perez luminous efficacy [V]

```
E_dh = Dh * [ a_i + b_i W + c_i cos(Z) + d_i ln(Delta) ]                       (Perez eq. 7)
E_dn = max(0, I * [ a_i + b_i W + c_i exp(5.73 Z - 5) + d_i Delta ])           (Perez eq. 8)
E_gh = E_dh + E_dn * cos(Z)

epsilon = [ (Dh + I) / Dh + kappa Z^3 ] / [ 1 + kappa Z^3 ],   kappa = 1.041    (eq. 1)
Delta   = Dh * m / I0                                                           (eq. 2)
W       = exp(0.07 T_d - 0.075)                                                 (eq. 3)
m       = 1 / [ cos(Z) + 0.15 (93.885 - Z_deg)^(-1.253) ]                       (Kasten 1966)
```

- `Dh` diffuse horizontal irradiance, `I` direct normal irradiance, `I0` extraterrestrial normal irradiance, W/m2.
- `Z` solar zenith angle in radians (`Z_deg` in degrees); `T_d` surface dew point, degrees C; `W` precipitable water, cm.
- `epsilon` sky clearness, `Delta` sky brightness, `m` relative optical air mass, all dimensionless.
- The brackets are luminous efficacies in lm/W. `i` is the clearness bin.

Clearness bins (Perez Table 1), by lower bound: 1 (overcast) from 1.000, 2 from 1.065, 3 from 1.230, 4 from 1.500, 5 from 1.950, 6 from 2.800, 7 from 4.500, 8 (clear) from 6.200.

Coefficients (Perez Table 4):

| bin | diffuse a | b | c | d | direct a | b | c | d |
|---|---|---|---|---|---|---|---|---|
| 1 | 97.24 | -0.46 | 12.00 | -8.91 | 57.20 | -4.55 | -2.98 | 117.12 |
| 2 | 107.22 | 1.15 | 0.59 | -3.95 | 98.99 | -3.46 | -1.21 | 12.38 |
| 3 | 104.97 | 2.96 | -5.53 | -8.77 | 109.83 | -4.90 | -1.71 | -8.81 |
| 4 | 102.39 | 5.59 | -13.95 | -13.90 | 110.34 | -5.84 | -1.99 | -4.56 |
| 5 | 100.71 | 5.94 | -22.75 | -23.74 | 106.36 | -3.97 | -1.75 | -6.16 |
| 6 | 106.42 | 3.83 | -36.15 | -28.83 | 107.19 | -1.25 | -1.51 | -26.73 |
| 7 | 141.88 | 1.90 | -53.24 | -14.03 | 105.75 | 0.77 | -1.26 | -34.44 |
| 8 | 152.23 | 0.35 | -45.27 | -7.98 | 101.18 | 1.58 | -1.10 | -8.29 |

Validity: sun above the horizon, `Dh > 0`. Design choice: below `h = 2 deg` set all three illuminances to zero. Fitted to 15-minute and hourly data from 13 US and European sites. If `Dh = 0`, `E_dh = 0`.

Primary: Perez et al. 1990 (S1), eqs (1), (2), (3), (7), (8), Tables 1 and 4, read from the scan. Second source: EnergyPlus `DayltgLuminousEfficacy` (S2), whose 64 coefficients, bin limits, `kappa`, `W` and air mass match the paper digit for digit. Radiance `gendaylit.c` also uses `W = exp(0.07 T_d - 0.075)`. Kasten (1966) was not opened; the air-mass formula is as coded in S2 and as cited by Perez.

Implementation warning: the `ladybug` function `estimate_illuminance_from_irradiance` differs from the paper in three places (`W = exp(0.08 T_d - 0.075)`, diffuse `c` of bin 3 written as -5.52, `I0` fixed at 1360). Do not port it unchanged.

Worked example (clear hour, 21 June, day 172): `I = 800`, `Dh = 120`, `Z = 30 deg`, `T_d = 15 C`, `I0 = 1361 (1 + 0.033 cos(2 pi 172/365)) = 1316.8`. `epsilon = (7.6667 + 1.041*0.5236^3) / (1 + 1.041*0.5236^3) = 6.800`, bin 8. `m = 1.1536`. `Delta = 120*1.1536/1316.8 = 0.1051`. `W = exp(0.975) = 2.6512`. Diffuse efficacy `152.23 + 0.35*2.6512 - 45.27*0.86603 - 7.98*ln(0.1051) = 131.93 lm/W`, `E_dh = 15 831 lx`. Direct efficacy `101.18 + 1.58*2.6512 - 1.10*exp(-2.0) - 8.29*0.1051 = 104.35 lm/W`, `E_dn = 83 479 lx`. `E_gh = 15 831 + 83 479 * cos(30) = 88 127 lx`.

Second computation: a line-by-line transliteration of the EnergyPlus routine (which forms `Delta` from monthly extraterrestrial illuminance divided by 93.73 lm/W) gives `E_dh = 15 830 lx` (-0.01 %) and `E_dn = 83 478 lx`. Two further cases: overcast (`I = 0`, `Dh = 150`, `Z = 60`, `T_d = 5`, 15 January) gives bin 1, 116.42 lm/W, `E_dh = 17 463 lx` against 17 458 lx; intermediate (`I = 300`, `Dh = 250`, `Z = 45`, `T_d = 8`, 15 March) gives bin 4, `E_dh = 30 124 lx` against 30 130 lx and `E_dn = 29 543 lx` against 29 543 lx.

Tool: `perez_luminous_efficacy(dni_w_m2, dhi_w_m2, zenith_deg, dew_point_c, i0_w_m2) -> {e_dh_lux, e_dn_lux, e_gh_lux, epsilon, delta, bin}`.

### DAY-08 Hourly indoor illuminance [V as a method; simplification stated]

```
E_in(t) = DF_sky * E_dh(t) + DF_gnd * E_gh(t)
DF_sky  = SC + ERC + IRC_sky
DF_gnd  = IRC_ground
```

- `E_in` daylight illuminance on the work plane at the point, lx. Direct sunlight falling on the desk is not counted (see below).

Assumptions, stated plainly:
1. Sky light is distributed as the CIE overcast sky scaled to the hour's diffuse illuminance. This is the logic of the daylight-factor route of EN 17037 (DAY-10), applied hour by hour. It ignores orientation for sky light and the bright region near the sun, so it underestimates clear-sky daylight for windows facing the sun and overestimates it for windows facing away.
2. Light reflected from the ground scales with global illuminance, because the sun lights the ground. This follows Bryan 1980 (S5) eq. (5), which scales the ground window factor by `(E_sun + E_sky) / E_sky`.
3. The direct beam into the room is excluded from the daylight credit. Where the sun reaches a desk, occupants draw blinds; the hour is handled as a glare hour (GLR-04), not as extra useful light. This is conservative for the lighting credit.

Primary: daylight-factor method, `E_in = DF * E_h` (S5 section 6; S2 "Interior Illuminance", which multiplies sky daylight factors by exterior horizontal illuminance from the sky). Second source: EN 17037 method 1 as described in S9, S10 and S20.

Worked example (R0, P, the three DAY-07 hours and three more): `DF_sky = 0.019944 + 0 + 0.003738 = 0.023681`, `DF_gnd = 0.001620`.

| `E_dh` lx | `E_gh` lx | `E_in` lx |
|---|---|---|
| 4 000 | 4 000 | 101.2 |
| 9 000 | 12 000 | 232.6 |
| 15 831 | 88 127 | 517.7 |
| 22 000 | 30 000 | 569.6 |
| 12 000 | 15 000 | 308.5 |
| 2 500 | 2 500 | 63.3 |

Check of row 3 by components: `SC` 315.7 lx, `IRC_sky` 59.2 lx, `IRC_ground` 142.8 lx, sum 517.7 lx.

Tool: `indoor_illuminance_hourly(df_sky, df_gnd, e_dh_lux[], e_gh_lux[]) -> e_in_lux[]`.

### DAY-09 Annual metrics: daylight autonomy [V definition]

```
DA_T  = (1 / N_occ) * sum over occupied hours of [ E_in(t) >= T ]
cDA_T = (1 / N_occ) * sum over occupied hours of min(1, E_in(t) / T)
```

- `T` target illuminance, lx. `N_occ` number of occupied hours in the year (section 0.3). Both results are fractions from 0 to 1.
- `cDA` (continuous daylight autonomy) gives partial credit below the target. It equals one minus the mean lighting output fraction of an ideal dimming system (LCT-01).

`DeskScore.daylight` is `DA_300` over occupied hours, a fraction from 0 to 1.

Primary definition: "the percentage of occupied time (or daylight hours) that a target illuminance is met by daylight at a point in a space", S20 (VELUX chapter 16), and "a percentage of annual daytime hours that a given point in a space is above a specified illumination level", S20 (Daylighting Pattern Guide), which credits Reinhart 2001 to 2004. The original papers (Reinhart and Walkenhorst 2001; Reinhart, Mardaljevic, Rogers 2006) were not opened; `cDA` is taken from the pattern guide's list of metrics and its definition here is the standard one but [P] until the 2006 paper is read.

Worked example: the six hours of DAY-08 as a toy occupied period. `DA_300 = 3/6 = 0.500` (hours 3, 4, 5). `DA_500 = 2/6 = 0.333`. `cDA_300 = (0.3373 + 0.7753 + 1 + 1 + 1 + 0.2110) / 6 = 0.721`. `cDA_500 = 0.569`. Second computation: `1 - cDA` equals the mean `f_L` of LCT-01, 0.2794 at 300 lx and 0.4315 at 500 lx, computed there independently.

Tool: `daylight_autonomy(e_in_lux[], occupied_mask[], target_lux) -> {da, cda}`.

### DAY-10 Target illuminances [V as quoted from open reproductions]

| Use | Target | Source |
|---|---|---|
| Daylight provision, any regularly occupied room | 300 lx on at least 50 % of the reference plane and 100 lx on at least 95 %, each for at least half of the daylight hours (minimum level). Medium: 500 and 300 lx. High: 750 and 500 lx. | EN 17037:2018 Table A.1, as reproduced in S9; minimum level also in S10 |
| Office desk work: writing, typing, reading, data processing | 500 lx maintained illuminance | EN 12464-1, as reproduced in S19 |
| Office filing, copying, circulation | 300 lx | same |
| Home desk or reading spot | no standard found that sets a value for dwellings; use 300 lx for the daylight score (EN 17037 does not vary by room type) and the office value of 500 lx as the high case for the lighting credit | design choice |

Target daylight factor (EN 17037 method 1):

```
D_T = T / E_v,d,med
```

- `E_v,d,med` median outdoor diffuse horizontal illuminance over the daylight hours, lx. Daylight hours are the 4380 hours of the year with the highest diffuse horizontal illuminance (S9).
- Under the daylight-factor model `E_in = DF * E_v,d`, a point meets "T lx for half of the daylight hours" exactly when `DF >= D_T`.

Primary: S10 eq. (2), `D_T = 300 lx / E_v,d,med * 100 %`. Second source: S9, Tables 3 and 4 and the Dublin value.

Worked example: Dublin `E_v,d,med = 14 900 lx` gives `D_T = 300/14 900 = 2.01 %` and `100/14 900 = 0.67 %`; S9 prints 2 % and 0.7 %. Germany 13 900 lx gives 2.16 % (S10 prints 2.2), Slovakia 16 300 lx gives 1.84 % (1.8), Sweden 12 100 lx gives 2.48 % (2.5). Point P of R0 (`DF = 0.02530`) meets 300 lx on half of the daylight hours wherever `E_v,d,med >= 300 / 0.02530 = 11 857 lx`.

For US sites the standard has no table: compute `E_v,d,med` from the weather file with DAY-07 and report `D_T` alongside `DA_300`.

Tool: `target_daylight_factor(target_lux, e_dh_lux[]) -> {e_vd_med_lux, d_t}`.

## 2. GLR: glare risk for a seated viewer

What is original and what is a simplification here. The glare index is the simplified daylight glare probability (DGPs) of Wienold, which needs only the vertical illuminance at the eye. The published method obtains that illuminance from a Radiance or DAYSIM simulation. This spec obtains it from the same geometric model as section 1 (GLR-01), and adds a geometric rule for the hours when DGPs is not valid because the sun is in view (GLR-04). GLR-01 and GLR-04 are this project's simplifications; GLR-02 is the published formula.

The viewer: eye at `(u_e, d_e, z_e)` with `z_e = EYE_HEIGHT_SEATED_M`, looking horizontally along the unit vector `v` with compass azimuth `A_v`.

### GLR-01 Vertical illuminance at the eye from geometry [V arithmetic; simplification]

```
E_v(t)  = V_sky * E_dh(t) + V_gnd * E_gh(t)
V_sky   = tau_eff * SC_v + IRC_sky
V_gnd   = tau_eff * GC_v + IRC_ground
SC_v    = (9 / (7 pi)) * integral over window elements above eye level of
              ((1 + 2 sin(gamma)) / 3) * max(0, r.v) * dOmega
GC_v    = (rho_g / pi) * integral over window elements below eye level of max(0, r.v) * dOmega
dOmega  = dA * cos(B) / D^2
```

- `E_v` illuminance on a vertical plane at the eye, facing `v`, lx.
- `r` unit vector from the eye to the window element; `D`, `B`, `gamma` as in DAY-03, measured from the eye.
- `SC_v` sky factor and `GC_v` ground factor for the vertical plane, dimensionless. Elements above eye level show sky (CIE overcast distribution scaled to `E_dh`), elements below show ground of luminance `rho_g E_gh / pi`.
- `IRC_sky`, `IRC_ground` from DAY-05: the split-flux interreflected illuminance is the same on every surface of the room, so it applies to a vertical plane as well (S2: "which in this method is uniform throughout the room").
- With an obstruction (DAY-04), elements above eye level and below the profile angle use `L_obs` instead of sky.

Evaluate the two integrals by a midpoint sum over the window with cells no larger than `D / 4` (S2 gives 1 % accuracy for that cell size), or by adaptive quadrature.

Validity and limits: as DAY-03 and DAY-05, plus one more. The sky is treated as overcast-shaped, so the bright sky around the sun on clear days is missing; `E_v` is underestimated for a viewer facing a window that faces the sun. GLR-04 covers the sun itself but not that bright surround. Glare from diffuse sky is therefore a lower bound.

Primary: Wienold 2009 (S7) for the vertical eye illuminance as the quantity that drives glare, and for evaluating it at 1.2 m height. The photometric law is that of DAY-03 (S2). Second source: none for the geometric shortcut itself; it is checked numerically.

Worked example (R0, eye at `(0, 2.0, 1.2)`):

| View | `SC_v` | `GC_v` | `V_sky` | `V_gnd` |
|---|---|---|---|---|
| parallel to the window wall (either way) | 0.010104 | 0.000942 | 0.008685 | 0.002081 |
| facing the window | 0.087119 | 0.008134 | 0.046392 | 0.005602 |
| back to the window | 0 | 0 | 0.003738 | 0.001620 |

Each factor was computed by adaptive double quadrature and by a 1500 by 1500 midpoint sum; they agree to the digits shown. Uniform-luminance check for the facing view: numeric configuration factor 0.177116, Howell B-3 by corner superposition (S14) 0.177116.

Illuminance for two DAY-07 hours: overcast (`E_dh = E_gh = 17 463 lx`): 188 lx parallel, 908 lx facing, 94 lx back. Clear with the sun out of view (`E_dh = 15 831`, `E_gh = 88 127`): 321 lx parallel, 1228 lx facing, 202 lx back.

Tool: `vertical_eye_illuminance_factors(eye_udz_m, view_azimuth_deg, room, windows, assumptions) -> {v_sky, v_gnd}`.

### GLR-02 Simplified daylight glare probability, DGPs [V]

```
DGPs = 6.22e-5 * E_v + 0.184
```

- `E_v` vertical illuminance at the eye, lx. `DGPs` dimensionless, read as the probability that a person is disturbed by glare.

| DGP | Glare rating | Class limit (S7 Table 5) |
|---|---|---|
| <= 0.35 | imperceptible | class A |
| 0.35 to 0.40 | perceptible | class B |
| 0.40 to 0.45 | disturbing | class C |
| > 0.45 | intolerable | outside the classes |

A class is met when the limit is exceeded in no more than 5 % of office time (S7 adds a cap on the mean DGP inside that 5 % band, not used here). In `E_v`, the three limits are 2669, 3473 and 4277 lx.

Validity: "can be applied only if no direct sun or specular reflection of it hits the eye of the observer" (S7). Low light: `evalglare.c` prints a notice below 100 lx and carries an optional low-light correction below 1000 lx that is off by default (S8). That range does not matter here because only the limits at 2669 lx and above are used.

Primary: Wienold 2009 (S7) eq. (1), which attributes the fit to Wienold 2007 and to the user tests of Wienold and Christoffersen 2006. Second source: Atzeri, Cappelletti and Gasparella 2017 (S8) eq. (3), same coefficients.

Worked example: `E_v = 908 lx` gives `6.22e-5 * 908 + 0.184 = 0.2405` (imperceptible). `E_v = 1228 lx` gives 0.2604. `E_v = 3473 lx` gives 0.4000. Second computation: inverse, `(0.40 - 0.184) / 6.22e-5 = 3473 lx`.

Tool: `dgp_simplified(e_v_lux) -> dgps`.

### GLR-03 Full daylight glare probability (reference only, not computed) [V form; coefficients from open secondaries]

```
DGP = c1 * E_v + c2 * log10( 1 + sum over glare sources i of  L_s,i^2 * omega_s,i / (E_v^1.87 * P_i^2) ) + c3
c1 = 5.87e-5,  c2 = 9.18e-2,  c3 = 0.16
```

- `L_s,i` luminance of glare source `i`, cd/m2; `omega_s,i` its solid angle, sr; `P_i` Guth position index, dimensionless.

Not implemented: it needs a luminance map of the field of view and the position index. It is here so that nobody mistakes DGPs for it, and because GLR-02 is its illuminance-only reduction.

Sources: S8 (Atzeri 2017 eq. (2) and nomenclature) prints this form with these constants, as the formula of the enhanced simplified DGP attributed to Wienold 2009, which shares the form of the full DGP. `evalglare.c` (S8), function `get_dgp`, codes the same form with exponents 2, 1, 1.87, 2 and `c1 = 5.87e-05`, but with `c2 = 0.092` and `c3 = 0.159`, and caps DGP at 1. The original paper (Wienold and Christoffersen 2006) is paid and was not opened, so which pair of constants it prints is not confirmed here.

Worked example: one source, `L_s = 5000 cd/m2`, `omega = 0.5 sr`, `P = 2`, `E_v = 2000 lx`. Sum term `5000^2 * 0.5 / (2000^1.87 * 4) = 2.0986`. `DGP = 0.1174 + 0.0918 * log10(3.0986) + 0.16 = 0.3225`; with the `evalglare.c` constants, 0.3216.

Tool: none.

### GLR-04 Direct sun in the field of view [V geometry; rule is a design simplification]

```
Delta  = wrap180(A_s - A_w)
in front of the wall:  h > 0  and  cos(Delta) > 0
u_hit  = u_e + d_e * tan(Delta)
z_hit  = z_e + d_e * tan(h) / cos(Delta)
visible = in front  and  u1 <= u_hit <= u2  and  z1 <= z_hit <= z2  and  tan(h) > tan(theta_o) * cos(Delta)
cos_sv = cos(h) * cos(A_s - A_v)
sun_in_view = visible and cos_sv > 0
E_v,sun = tau * M * E_dn * cos_sv        (reported, not used for the class)
```

- `(u_hit, z_hit)` is where the ray from the eye to the sun crosses the glass plane, in the wall frame of section 0.2.
- `cos_sv` cosine of the angle between the line of sight and the sun.
- Rule: an hour with `sun_in_view` is a glare hour (treated as intolerable) whatever DGPs says, because DGPs is not valid for it (GLR-02).

The same test from the desk point at work-plane height gives `sun_on_desk`, reported as a count of hours (`direct_sun_hours`) and used in CMF-07.

Validity and assumptions: the sun is a point; the window is unshaded (no blinds, overhang or reveal); "in view" means anywhere in the forward hemisphere of the eye, which is the hemisphere that the vertical illuminance refers to. This is deliberately strict. With blinds the hour stops being a glare hour and stops being a daylight hour; neither is credited.

Source for the rule: the validity statement of DGPs in S7. The geometry is plane trigonometry, checked two ways. No second published source prescribes this exact rule; it is a design simplification.

Worked example (R0, eye `(0, 2.0, 1.2)`, view parallel to the wall along `+e_t`):

| `Delta` | `h` | `u_hit` | `z_hit` | visible | `cos_sv` |
|---|---|---|---|---|---|
| 20 | 25 | 0.728 | 2.192 | yes | 0.310 |
| 20 | 40 | 0.728 | 2.986 | no (above the head, 2.4 m) | 0.262 |
| -60 | 10 | -3.464 | 1.905 | no (beyond the jamb) | -0.853 |
| 100 | 30 | - | - | no (sun behind the wall) | 0.853 |

Computed from the formulas above and again by intersecting the sun vector with the glass plane in Cartesian coordinates; identical. For the first row with `E_dn = 83 479 lx`: `E_v,sun = 0.68 * 0.9 * 83 479 * 0.310 = 15 836 lx`, almost four times the 4277 lx limit, which is why the rule does not need a finer treatment.

Tool: `sun_visible_through_window(point_udz_m, window_rect, a_w_deg, sun_alt_deg, sun_az_deg, theta_o_deg=0) -> {visible, u_hit, z_hit}`.

### GLR-05 Annual glare risk for a desk [V arithmetic; thresholds from S7; orientation rule is a design choice]

```
glare_hour(t) = sun_in_view(t)  or  DGPs(E_v(t)) > 0.40
glare_risk    = (1 / N_occ) * sum over occupied hours of glare_hour(t)
```

- `glare_risk` is `DeskScore.glare_risk`, a fraction from 0 to 1. 0.40 is the class B limit; with it, `glare_risk <= 0.05` means class B or better.

View direction. A desk has no orientation in the scan. Evaluate the two directions parallel to the nearest window wall (`A_w + 90` and `A_w - 90`), keep the lower `glare_risk`, and return that direction as the recommended facing. Also compute the facing-the-window value and add a warning if it exceeds 0.05, because people do turn their desks.

Worked example: the six toy hours of DAY-08 at R0, parallel view. `E_v` = 43, 103, 321, 254, 135, 27 lx, all far below 3473 lx, so no DGPs glare hours. If the sun is in view in one of the six hours (as in row 1 of GLR-04), `glare_risk = 1/6 = 0.167`, worse than class C. Second computation of hour 3: `0.008685 * 15 831 + 0.002081 * 88 127 = 137.5 + 183.4 = 320.9 lx`.

Tool: `glare_risk_annual(eye_udz_m, room, windows, hourly_climate, occupied_mask, assumptions) -> {glare_risk, view_azimuth_deg, glare_risk_facing_window, direct_sun_hours}`.

## 3. CMF: thermal comfort

The comfort chain for a seated person near glazing: glass surface temperature (CMF-04), mean radiant temperature at the body (CMF-05), solar load on the body (CMF-07), then PMV and PPD (CMF-01, CMF-02). Radiant asymmetry (CMF-06) is a separate local-discomfort check. ISO 7730, ISO 7726 and ASHRAE 55 are paid and were not opened; each entry names the open reproduction that was read, and the PMV and SolarCal implementations were checked against table values transcribed from the standards (S11).

### CMF-01 Predicted mean vote, PMV [V]

```
PMV = [0.303 exp(-0.036 M) + 0.028] * L
L   = (M - W)
      - 3.05e-3 * [5733 - 6.99 (M - W) - p_a]
      - 0.42 * [(M - W) - 58.15]                      (only if M - W > 58.15, else 0)
      - 1.7e-5 * M * (5867 - p_a)
      - 0.0014 * M * (34 - t_a)
      - 3.96e-8 * f_cl * [(t_cl + 273)^4 - (t_r + 273)^4]
      - f_cl * h_c * (t_cl - t_a)

t_cl = 35.7 - 0.028 (M - W) - I_cl * { 3.96e-8 f_cl [(t_cl + 273)^4 - (t_r + 273)^4] + f_cl h_c (t_cl - t_a) }
h_c  = max( 2.38 |t_cl - t_a|^0.25 , 12.1 sqrt(v_ar) )
f_cl = 1.00 + 1.290 I_cl   if I_cl <= 0.078,   else 1.05 + 0.645 I_cl
p_a  = RH * 10 * exp(16.6536 - 4030.183 / (t_a + 235))
```

- `M` metabolic rate, W/m2 (1 met = 58.15 W/m2); `W` external work, W/m2 (0 for desk work).
- `I_cl` clothing insulation, m2K/W (1 clo = 0.155 m2K/W); `f_cl` clothing area factor.
- `t_a` air temperature, `t_r` mean radiant temperature, `t_cl` clothing surface temperature, degrees C.
- `v_ar` relative air speed, m/s; `p_a` water vapour pressure, Pa; `RH` relative humidity, %.
- `h_c` convective coefficient, W/m2K. `L` thermal load on the body, W/m2. PMV is on the seven-point scale from -3 (cold) to +3 (hot).

`t_cl` is implicit: solve its equation by bracketed root finding (it has one root between -50 and 100 degrees C) or by the fixed-point iteration of the reference implementation.

Validity (ISO 7730 clause 4 limits as coded in S11): `t_a` 10 to 30, `t_r` 10 to 40, `v_ar` 0 to 1 m/s, `M` 0.8 to 4 met, `I_cl` 0 to 2 clo, `p_a` 0 to 2700 Pa, PMV within -2 to +2. Steady state, whole-body. With a solar-adjusted `t_r` above 40 degrees C, clamp the result to +3 and add a warning.

Primary: the ISO 7730 PMV equations as implemented in `pythermalcomfort` `pmv_ppd_iso` (S11), read line by line; the constants above are those of that code (which writes 308.7 for 35.7 + 273). Second source: `ladybug-comfort` `fanger_pmv` (S13), which carries the same constants (0.303, 0.036, 0.028, 3.96, 12.1, 2.38). Third: the twelve cases labelled "ISO 7730 2005" in the S11 validation table. Clause and equation numbers of the standard are not quoted because the standard was not opened.

Worked example (seated 1 m from the R0 window on a winter night): `t_a = 21`, `t_r = 20.360` (CMF-05), `v_ar = 0.1`, `RH = 40`, 1.2 met, 1.0 clo. `M = 69.78`, `I_cl = 0.155`, `f_cl = 1.150`, `p_a = 994.4 Pa`. Root: `t_cl = 26.081`, `h_c = max(3.573, 3.826) = 3.826`. Terms of `L`: skin diffusion 12.965, sweat 4.885, latent respiration 5.780, dry respiration 1.270, radiation 27.091, convection 22.359. `L = 69.78 - 74.35 = -4.57`. Coefficient 0.05257. `PMV = -0.240`. With no cold window (`t_r = 21`): -0.177.

Second computation: `pythermalcomfort.pmv_ppd_iso(tdb=21, tr=20.360, vr=0.1, rh=40, met=1.2, clo=1.0, model="7730-2005")` returns -0.2396 (own solver -0.2403); with `tr=21`, -0.1759 (own -0.1766). The 2005 and 2025 model options return identical values. Table check: all twelve ISO 7730 cases reproduce, for example (22, 22, 0.1 m/s, 60 %, 1.2 met, 0.5 clo) table -0.8 and 16.9 %, own -0.753 and 16.9 %; (27, 27, 0.3, 60, 1.6, 0.5) table 0.9 and 24.1 %, own 0.950 and 24.1 %. Largest difference from the one-decimal table values 0.05 PMV and 0.1 PPD.

Tool: `pmv_ppd(t_air_c, t_mrt_c, v_rel_m_s, rh_percent, met, clo) -> {pmv, ppd_percent}`.

### CMF-02 Predicted percentage dissatisfied, PPD [V]

```
PPD = 100 - 95 * exp(-0.03353 PMV^4 - 0.2179 PMV^2)
```

- PPD in percent. Minimum 5 % at PMV = 0, symmetric in PMV.

Primary: the ISO 7730 PPD equation as coded in S11. Second source: `ladybug-comfort` `ppd_from_pmv` (S13), same constants. Comfort zone: PMV between -0.5 and +0.5 (PPD up to 10 %), as used for the comfort zone in Arens 2015 (S12).

Worked example: `PMV = -0.240` gives `100 - 95 exp(-0.03353*0.00333 - 0.2179*0.0577) = 6.20 %` (reference implementation 6.19 %). Anchors: PPD(0) = 5.00, PPD(0.5) = 10.23, PPD(1) = 26.12, PPD(2) = 76.76.

Tool: part of `pmv_ppd`.

### CMF-03 Operative temperature [V]

```
t_o = A t_a + (1 - A) t_r          A = 0.5 for v < 0.2 m/s;  0.6 for 0.2 <= v < 0.6;  0.7 for 0.6 <= v <= 1.0
```

Alternative form (ISO 7726 as coded in S11): `t_o = (t_a sqrt(10 v) + t_r) / (1 + sqrt(10 v))`.

- `t_o` operative temperature, degrees C; `v` air speed, m/s.

Validity: moderate indoor conditions, `v <= 1 m/s`, `|t_r - t_a|` small (the ASHRAE form is stated for differences below about 4 K; that limit is from memory of the standard, [U]).

Primary: `pythermalcomfort.utilities.operative_tmp` (S11), which cites ISO 7726:1998 and carries the ASHRAE coefficients. Second source: S21 eq. (2), `T_op = (T_a + T_mr) / 2` for still indoor air.

Worked example: `t_a = 21`, `t_r = 20.360`, `v = 0.1`: `t_o = 20.68` by both forms (at 0.1 m/s `sqrt(10 v) = 1`). `t_a = 24`, `t_r = 30`, `v = 0.3`: ASHRAE form 26.40, ISO form 26.20. Both values match the reference implementation.

Tool: `operative_temperature(t_air_c, t_mrt_c, v_m_s, form="ashrae") -> t_o_c`. Reported for the user; PMV uses `t_a` and `t_r` separately.

### CMF-04 Inside surface temperature of the glazing [V derivation; P film coefficient]

```
T_gi = T_i - U_w * (T_i - T_out) / h_i
```

- `T_gi` inside glass surface temperature, `T_i` room air temperature, `T_out` outdoor air temperature, degrees C.
- `U_w` window U-value, W/m2K (`Surface.u_value`); `h_i` inside surface coefficient, W/m2K (radiation plus convection).

Derivation: steady one-dimensional heat flow `q = U_w (T_i - T_out)` equals the flow across the inside film `h_i (T_i - T_gi)`.

Validity: steady state; no solar absorption in the glass (sunlit glass is warmer, so winter discomfort is overstated in sun and summer radiant warmth understated); centre-of-glass and frame lumped in `U_w`. S16 reports that using one area-weighted window temperature in place of separate frame and glass temperatures changes the comfort result little.

Sources: derivation from the definition of U-value; S16 for the role of the inside surface temperature in winter comfort. `h_i` must be the same value that physics 02 uses in `ENV` for a vertical surface; no value was verified here. The worked example uses 8.0 W/m2K as a round number.

Worked example: `T_i = 21`, `T_out = -5`, `U_w = 2.8`, `h_i = 8.0`: `q = 72.8 W/m2`, `T_gi = 21 - 72.8/8 = 11.90`. Second computation by resistance divider: `T_gi = T_out + (T_i - T_out)(1/U_w - 1/h_i) / (1/U_w) = 11.90`.

Tool: `glass_inside_surface_temperature(t_in_c, t_out_c, u_w, h_i) -> t_gi_c`.

### CMF-05 Mean radiant temperature at the body [V formula; view factor is a simplification]

```
T_r^4 = sum over surfaces i of F_i * T_i^4            (temperatures in K, sum of F_i = 1)
F_i   = Omega_i / (4 pi)                              (person treated as a small sphere)
Omega_corner(a, b, c) = atan( a b / (c sqrt(a^2 + b^2 + c^2)) )
```

- `T_r` mean radiant temperature, `T_i` surface temperatures, K.
- `F_i` angle factor from the person to surface `i`; `Omega_i` solid angle of the surface seen from the body centre, sr.
- `Omega_corner` solid angle of an `a` by `b` rectangle seen from a point at distance `c` on the normal through one of its corners. Any rectangle in a wall follows by adding and subtracting four corner terms with signs, as for B-3 below.

Two-temperature form used by the tool: `T_r^4 = F_w T_gi^4 + (1 - F_w) T_s^4`, with `F_w` summed over the room's windows and `T_s` the temperature of all other room surfaces (set to `t_a` unless the zone model supplies surface temperatures).

Validity and assumptions: surfaces are black for long-wave radiation (building materials have high emissivity); the person is a point at `BODY_CENTRE_SEATED_M`, radiating equally in all directions. A real body is not a sphere; the size of that error is not quantified here. ISO 7726 gives posture-specific angle factors; the open copies of its fitted coefficients disagree with each other, so they are not used (section 6).

Primary: ISO 7726 method as reproduced in S21 eq. (1) (fourth-power sum with angle factors, black surfaces) and in S15 eq. (3) for the plane form. Second source: Arens 2015 (S12) eq. (1), `ERF = f_eff h_r (MRT - T_a)`, the linearised statement of the same exchange, used in CMF-07. The corner solid angle is a geometric identity, checked numerically.

Worked example (R0, body centre `(0, 1.0, 0.6)`, `T_gi = 11.90`, `T_s = 21`): window solid angle 0.923483 sr by corner terms and 0.923483 sr by numerical integration of `c / D^3` over the rectangle; `F_w = 0.07349`. `T_r = (0.07349 * 285.05^4 + 0.92651 * 294.15^4)^(1/4) - 273.15 = 20.360`. Linear average for comparison 20.331. At 2.0 m from the glass: `F_w = 0.03779`, `T_r = 20.671`. Closure: the six faces of R0 seen from the body centre give factors 0.2275, 0.0309, 0.1189, 0.1189, 0.3534, 0.1505, sum 1.000000000.

Tool: `mean_radiant_temperature_point(body_udz_m, room, windows, t_gi_c[], t_surfaces_c) -> {t_mrt_c, f_window}`.

### CMF-06 Radiant temperature asymmetry near a cold window [V]

```
T_pr^4  = sum over surfaces i of F_pl,i * T_i^4                       (K)
dt_pr   = T_pr(half-space facing the room) - T_pr(half-space facing the window)

F_B3(a, b, c) = (1 / 2 pi) * [ A / sqrt(1 + A^2) * atan(B / sqrt(1 + A^2)) + B / sqrt(1 + B^2) * atan(A / sqrt(1 + B^2)) ]
                A = a / c,  B = b / c
F_B4(a, b, c) = (1 / 2 pi) * [ atan(1 / C) - (C / Y) * atan(1 / Y) ]
                A = a / b,  C = c / b,  Y = sqrt(A^2 + C^2)
```

- `T_pr` plane radiant temperature of a small vertical plane element at the body centre; `dt_pr` radiant temperature asymmetry, K.
- `F_B3`: small plane element to a parallel rectangle `a` by `b` at distance `c`, element on the normal through a corner. `F_B4`: small plane element to a perpendicular rectangle of height `a` and width `b`, element at distance `c` from the rectangle's plane, level with its base and in line with a corner.
- Corner superposition for a window `[u1, u2] x [z1, z2]` seen from `(u_p, d_p, z_p)`: `F = G(u2, z2) - G(u1, z2) - G(u2, z1) + G(u1, z1)`, `G(u, z) = sign(u - u_p) sign(z - z_p) F_B3(|u - u_p|, |z - z_p|, d_p)`.

Limits (asymmetry that leaves fewer than 5 % dissatisfied):

| Case | Limit |
|---|---|
| cool wall (cold window) | < 10 K |
| warm wall | < 23 K |
| warm ceiling | < 5 K |
| cool ceiling | < 14 K |

Rule: flag the desk (`warnings`, and not `recommended`) if `dt_pr >= 10 K` at the winter design hour. The asymmetry does not enter PMV.

Percentage dissatisfied for a cool wall, informative only: `PD = 100 / (1 + exp(6.61 - 0.345 dt_pr))`, for `dt_pr < 15 K`. [P]: one open source (S18 Table 7, citing Fanger 1985); it is consistent with the limit (4.1 % at 10 K) but ISO 7730 clause 6.5 was not opened.

Validity: black surfaces; element at the body centre; the window wall is treated as one plane.

Primary for the method: ISO 7726 as reproduced in S15 eqs (2) to (5) (plane radiant temperature, asymmetry as the difference of two opposite half-spaces, and the two angle-factor formulas). Second source for the formulas: Howell catalog B-3 and B-4 (S14), identical. Limits: ASHRAE 55-2004 Table 5.2.4.1 as reproduced in S16 Table 4; S17 (ASHRAE's own interpretation) confirms 5 K for a warm ceiling and 10 K for a cool wall. Note: S18 Table 1 prints the same four numbers under shifted column labels (cool wall under 23); the PD curves and S16 and S17 show that 10 K is the cool-wall value.

Worked example (R0, element at `(0, 1.0, 0.6)` facing the window, `T_gi = 11.90`, other surfaces 21): `F = 0.212544` by B-3 superposition and 0.212544 by numerical quadrature. `T_pr(window side) = (0.212544 * 285.05^4 + 0.787456 * 294.15^4)^(1/4) - 273.15 = 19.136`. Room side 21.000. `dt_pr = 1.86 K`, well inside the limit; PD 0.3 %. Severe case for contrast: single glazing `U_w = 5.8`, `T_out = -10`, glass wall 4.0 by 2.8 m, element 0.6 m away: `T_gi = -1.47`, `F = 0.8171`, `dt_pr = 17.9 K`, over the limit.

Tool: `radiant_asymmetry_window(body_udz_m, windows, t_gi_c[], t_surfaces_c) -> {dt_pr_k, exceeds_cool_wall_limit}`.

### CMF-07 Direct and diffuse solar load on the occupant, SolarCal [V]

```
E_diff   = 0.5 * f_eff * f_svv * T_sol * I_diff
E_refl   = 0.5 * f_eff * f_svv * T_sol * I_TH * R_floor          I_TH = I_dir sin(beta) + I_diff
E_dir    = f_eff * f_p * f_bes * T_sol * I_dir
ERF_sol  = (E_diff + E_refl + E_dir) * alpha_SW / alpha_LW
dMRT     = ERF_sol / (f_eff * h_r)
t_r,adj  = t_r + dMRT
```

- `I_dir` direct normal irradiance, `I_diff` diffuse horizontal irradiance, `I_TH` global horizontal irradiance, all outdoors, W/m2. `beta` solar altitude.
- `T_sol` total solar transmittance of glazing and shades, dimensionless.
- `f_eff` fraction of the body surface that exchanges radiation with the surroundings: 0.696 seated, 0.725 standing.
- `f_svv` fraction of the sky vault in the occupant's view; `f_bes` fraction of the body exposed to direct sun (shading by surroundings only); `f_p` projected area factor (table below).
- `R_floor` reflectance of floor and lower furnishings, including a long-wave allowance.
- `alpha_SW` short-wave absorptivity of skin and clothing; `alpha_LW = 0.95`.
- `h_r = 6.0 W/m2K` radiative coefficient. `ERF_sol` W/m2 of body surface; `dMRT` K.

Inputs from geometry:
- `f_svv = d_az * d_el / (180 * 360)`, with `d_az` and `d_el` the horizontal and vertical angles in degrees that the window subtends at the body centre: `d_az = atan((u2 - u_b)/d_b) - atan((u1 - u_b)/d_b)`, `d_el = atan((z2 - z_b)/d_b) - atan((z1 - z_b)/d_b)`. For a window centred on the occupant this is exactly the paper's eq. (8), `atan(h/2d) atan(w/2d) / (90 * 180)`. Sum over windows. Do not reduce it for exterior obstructions (S12).
- Direct term: applies only in hours when the sun reaches the body, by the GLR-04 test at the body centre. Then `f_bes = comfort.body_exposed_fraction`, else 0.
- `f_p`: bilinear interpolation in the seated table by solar altitude and by the solar horizontal angle relative to the front of the person, `SHARP = |wrap180(A_s - A_v)|`, 0 to 180 degrees.
- `I_diff`: the weather file value. (The paper offers `0.17 I_dir sin(beta)` and the ASHRAE implementation uses `0.2 I_dir` when no diffuse value is known; neither is needed here.)
- `T_sol`: `Surface.shgc` as an approximation. S12 notes that SHGC includes heat absorbed in the glass, so it over-predicts gain on the occupant, and that the designer must reduce `T_sol` for oblique incidence; use the angular function of physics 02 `WIN` for the beam if that file provides one.

Seated projected area factor `f_p` (rows: SHARP in degrees; columns: solar altitude in degrees), as tabulated in S11 for the ASHRAE 55 method:

| SHARP | 0 | 15 | 30 | 45 | 60 | 75 | 90 |
|---|---|---|---|---|---|---|---|
| 0 | 0.290 | 0.324 | 0.305 | 0.303 | 0.262 | 0.224 | 0.177 |
| 15 | 0.292 | 0.328 | 0.294 | 0.288 | 0.268 | 0.227 | 0.177 |
| 30 | 0.288 | 0.332 | 0.298 | 0.290 | 0.264 | 0.222 | 0.177 |
| 45 | 0.274 | 0.326 | 0.294 | 0.289 | 0.252 | 0.214 | 0.177 |
| 60 | 0.254 | 0.308 | 0.280 | 0.276 | 0.241 | 0.202 | 0.177 |
| 75 | 0.230 | 0.282 | 0.262 | 0.260 | 0.233 | 0.193 | 0.177 |
| 90 | 0.216 | 0.260 | 0.248 | 0.244 | 0.220 | 0.186 | 0.177 |
| 105 | 0.234 | 0.258 | 0.236 | 0.227 | 0.208 | 0.180 | 0.177 |
| 120 | 0.262 | 0.260 | 0.224 | 0.208 | 0.196 | 0.176 | 0.177 |
| 135 | 0.280 | 0.260 | 0.210 | 0.192 | 0.184 | 0.170 | 0.177 |
| 150 | 0.298 | 0.256 | 0.194 | 0.174 | 0.168 | 0.168 | 0.177 |
| 165 | 0.306 | 0.250 | 0.180 | 0.156 | 0.156 | 0.166 | 0.177 |
| 180 | 0.300 | 0.240 | 0.168 | 0.152 | 0.152 | 0.164 | 0.177 |

Validity: whole-body, steady, seated or standing person; solar altitude 0 to 90; the model does not know the glazing orientation, so `T_sol` must already reflect it.

Primary: Arens et al. 2015 (S12) eqs (1) to (8), method and input sections read in full: `f_eff` values, `alpha_LW = 0.95`, the three flux terms and the conversion to MRT. Second source: `pythermalcomfort.solar_gain` (S11), same terms with `h_r = 6` and the `f_p` tables, and the 26 seated cases labelled "ASHRAE 55 2017" in its validation table. `ladybug-comfort` `solarcal.py` carries the same 0.696, 0.725 and 0.95. The paper does not print `h_r`; its examples imply about 6.1.

Notes on the sources: (1) the paper's second example quotes `f_svv = 0.32` for a 3 m by 3 m window at 1 m, while its own eq. (8) gives 0.196; the value 0.32 is `atan(h/d) atan(w/d) / (90 * 180)`. Eq. (8) as printed matches the reference implementation and is used here. (2) The exact solid-angle fraction of the full sphere for that window is 0.243, so eq. (8) is itself an approximation.

Worked example (seated at `(0, 1.0, 0.6)` in R0, sun reaching the body): `beta = 25`, `SHARP = 70`, `I_dir = 800`, `I_diff = 120`, `T_sol = 0.6`, `f_bes = 0.5`, `alpha_SW = 0.7`, `R_floor = 0.6`. `d_az = 90.0`, `d_el = atan(1.8) - atan(0.3) = 44.246`, `f_svv = 0.06145`. `f_p` from corners 0.308, 0.282 (altitude 15) and 0.280, 0.262 (altitude 30): 0.2756. `I_TH = 800 sin(25) + 120 = 458.1`. `E_diff = 0.5*0.696*0.06145*0.6*120 = 1.540`. `E_refl = 0.5*0.696*0.06145*0.6*458.1*0.6 = 3.527`. `E_dir = 0.696*0.2756*0.5*0.6*800 = 46.029`. `ERF_sol = 51.095 * 0.7/0.95 = 37.65 W/m2`. `dMRT = 37.65 / (0.696*6.0) = 9.02 K`.

Second computation: with `I_diff` set to `0.2 I_dir = 160` (the fixed assumption inside the reference implementation), own formulas give ERF 38.254 and dMRT 9.161; `pythermalcomfort.solar_gain(25, 70, 800, 0.6, f_svv=0.06145, f_bes=0.5, asw=0.7, floor_reflectance=0.6, posture="sitting")` returns 38.254 and 9.161. Table check: own implementation reproduces all 26 seated ASHRAE 55 cases within 0.05 W/m2 and 0.05 K, for example (altitude 45, SHARP 0, 700 W/m2, `T_sol` 0.8, `f_svv` 0.2, `f_bes` 0.5) table 64.9 and 15.5, own 64.88 and 15.54. Paper check: the skylight example (altitude 87, 925 W/m2, `T_sol` 0.2, `f_bes` 0.9, `R_floor` 0.5, `f_svv` 0.0122) gives 16.35 W/m2 and 3.92 K against the printed 16.5 and 3.9.

Effect on comfort: at `t_a = t_r = 24`, 50 %, 0.1 m/s, 1.2 met, 0.5 clo, PMV is -0.215 (PPD 6.0 %). With `t_r = 24 + 9.02`, PMV is +1.079 (PPD 29.6 %); reference implementation +1.079 and 29.6 %.

Tool: `solar_gain_delta_mrt(sun_alt_deg, sharp_deg, i_dir, i_diff, t_sol, f_svv, f_bes, alpha_sw, r_floor, posture="seated") -> {erf_w_m2, delta_mrt_k}`.

### CMF-08 Annual comfort figure for a desk [V arithmetic; aggregation is a design choice]

For every occupied hour:

1. `t_a(t)`: zone air temperature from the hourly zone model of physics 02, or the active setpoint if only setpoints are known.
2. `T_gi(t)` per window from CMF-04 with `T_out(t)`.
3. `t_r(t)` from CMF-05, other surfaces at `t_a(t)`.
4. `dMRT(t)` from CMF-07; add to `t_r(t)`.
5. PMV and PPD from CMF-01 and CMF-02 with `comfort.met`, `comfort.air_speed_m_s`, `comfort.rh_percent`, and clothing `comfort.clo_heating` when the zone is heating in that hour (or `T_out < 15` if the zone model gives no mode), else `comfort.clo_cooling`.

```
comfort_ppd = (1 / N_occ) * sum over occupied hours of PPD(t)
```

- `comfort_ppd` is `DeskScore.comfort_ppd`, percent, between 5 and 100. Also return the fraction of occupied hours with `|PMV| > 0.5` and the largest `dt_pr` (CMF-06).

The mean of PPD, the clothing switch and the use of setpoints are design choices, not part of any standard.

Worked example (three toy hours at the R0 desk 1 m from the glass): winter night PPD 6.20 %, summer hour without sun 5.96 %, summer hour with sun on the body 29.55 %; `comfort_ppd = 13.90 %`; one hour in three outside the comfort zone. Second computation with the reference implementation: 6.19, 5.94, 29.57, mean 13.90.

Tool: `comfort_ppd_annual(body_udz_m, room, windows, hourly_climate, hourly_zone, occupied_mask, assumptions) -> {comfort_ppd, frac_outside_comfort, max_dt_pr_k}`.

## 4. LCT: lighting credit and desk score

### LCT-01 Electric lighting output and power under daylight control [V]

```
f_L = max(0, (E_set - E_in) / E_set)

continuous dimming:      f_P = f_P,min                                              if f_L < f_L,min
                         f_P = (f_L + (1 - f_L) f_P,min - f_L,min) / (1 - f_L,min)  if f_L,min <= f_L <= 1
continuous/off dimming:  as continuous, but f_P = 0 for f_L < f_L,min
stepped, N steps:        f_P = 0 if f_L = 0;   (int(N f_L) + 1) / N if 0 < f_L < 1;   1 if f_L = 1
automatic on/off:        stepped with N = 1
no daylight control:     f_P = 1
```

- `E_set` illuminance setpoint at the desk, lx (`lighting.setpoint_lux`); `E_in` daylight illuminance from DAY-08, lx.
- `f_L` fraction of full electric light output needed; `f_P` fraction of full lighting input power.
- `f_L,min`, `f_P,min` lowest light output and the power drawn there (`lighting.min_light_fraction`, `lighting.min_power_fraction`).

Assumption: the electric lighting at full power delivers exactly `E_set` at the desk (S2). Power rises linearly from `f_P,min` to 1 as light output rises from `f_L,min` to 1.

Primary: EnergyPlus Engineering Reference (S2), "Lighting Control System Simulation", "Continuous Dimming Control", "Continuous/Off Dimming Control", "Stepped Control". Second source: no independent text was opened. Two consistency checks stand in for it: the dimming line passes through `(f_L,min, f_P,min)` and `(1, 1)`; and with `f_L,min = f_P,min = 0` the saved fraction `1 - f_P` equals `min(1, E_in / E_set)`, whose mean is `cDA` (DAY-09).

Worked example (`E_set = 500 lx`, `f_L,min = 0.2`, `f_P,min = 0.3`, the six hours of DAY-08):

| `E_in` lx | `f_L` | continuous | continuous/off | on/off | 3 steps |
|---|---|---|---|---|---|
| 101.2 | 0.7976 | 0.8229 | 0.8229 | 1 | 1 |
| 232.6 | 0.5348 | 0.5929 | 0.5929 | 1 | 0.6667 |
| 517.7 | 0 | 0.3000 | 0 | 0 | 0 |
| 569.6 | 0 | 0.3000 | 0 | 0 | 0 |
| 308.5 | 0.3830 | 0.4601 | 0.4601 | 1 | 0.6667 |
| 63.3 | 0.8734 | 0.8892 | 0.8892 | 1 | 1 |
| mean saved fraction `1 - f_P` | | 0.4391 | 0.5391 | 0.3333 | 0.4444 |

Hand check of row 5: `f_L = (500 - 308.5)/500 = 0.3830`; `f_P = (0.3830 + 0.6170*0.3 - 0.2)/0.8 = 0.4601`. Ideal dimming saves `cDA_500 = 0.5685`. At `E_set = 300 lx` the mean saved fractions are 0.5430, 0.6930, 0.5000, 0.6667, and ideal 0.7206.

Tool: `lighting_power_fraction(e_in_lux, e_set_lux, control_type, f_l_min=0.2, f_p_min=0.3, n_steps=3) -> f_p`.

### LCT-02 Annual lighting energy displaced [V arithmetic; behavioural factor U]

```
E_saved = (P_ctrl / 1000) * sum over occupied hours of [1 - f_P(t)] * dt        kWh per year
P_ctrl  = LPD * A_ctrl                                                           W
```

- `LPD` installed lighting power density, W/m2 (`Systems.lighting_w_per_m2`); `A_ctrl` floor area lit by the luminaires that serve the desk, m2 (configuration `AREA_PER_DESK_M2`, or zone area divided by the number of desks); `dt = 1 h`.
- Baseline: lights fully on during occupied hours.

What may be claimed, by control type:

| `lighting.control_type` | Saving |
|---|---|
| `continuous`, `continuous_off`, `stepped`, `auto_on_off` | the formula above with LCT-01 |
| `none` (no daylight control, the usual case when the vision pass finds no sensor) | physically zero unless people switch the lights off. Report `E_saved = k_m * E_saved(auto_on_off)` with `lighting.manual_switch_fraction` `k_m` = 0 / 0.5 / 1.0 (low / expected / high) |

`k_m` has no verified source. Its expected value is a placeholder [U], and a `LAYOUT` saving that rests on it must carry the warning "depends on occupants switching lights off". A saving that does not depend on behaviour needs the controls of `LGT_CTRL`; when both measures are in a plan, `LGT_CTRL` evaluated at the chosen desk positions holds the saving and `LAYOUT` adds only the difference between daylight at the new and the old positions.

Interaction with heating and cooling: return the hourly lighting power reduction `P_ctrl (1 - f_P(t))` so that the zone model of physics 02 can remove that heat gain. Do not estimate the HVAC effect here.

Worked example: `LPD = 10 W/m2`, `A_ctrl = 8 m2`, so `P_ctrl = 80 W`; 2600 occupied hours; continuous dimming at 500 lx with the toy-day mean saved fraction 0.4391: `E_saved = 0.080 * 2600 * 0.4391 = 91.3 kWh/yr` out of a baseline `0.080 * 2600 = 208 kWh/yr`. With no control: automatic on/off potential `208 * 0.3333 = 69.3 kWh/yr`, reported as 0 / 34.7 / 69.3. Second computation: summing `80 W * (1 - f_P)` over the six rows of LCT-01 gives 210.8 Wh of 480 Wh, the same 0.4391.

Tool: `lighting_energy_saved(e_in_lux[], occupied_mask[], e_set_lux, control_type, lpd_w_m2, area_m2, k_m) -> {lighting_kwh_saved: Ranged, hourly_w_reduction[]}`.

### LCT-03 Desk score [design choice, not physics]

```
s_d   = DA_300                                             daylight sub-score
s_g   = 1 - min(1, glare_risk / G_MAX)                     G_MAX = 0.20
s_c   = 1 - min(1, max(0, comfort_ppd - 5) / (PPD_MAX - 5))    PPD_MAX = 25
score = w_d s_d + w_g s_g + w_c s_c                        w_d, w_g, w_c = 0.4, 0.3, 0.3
```

- All sub-scores and the score run from 0 to 1. `DA_300` from DAY-09, `glare_risk` from GLR-05, `comfort_ppd` from CMF-08.
- A desk is not recommended, whatever its score, if `dt_pr >= 10 K` (CMF-06) or if it breaks the clearance rules of SPEC 6.4.

The weights, `G_MAX` and `PPD_MAX` are design choices that live in `backend/config.py`. Only the 5 % floor of PPD is physics (CMF-02). The score ranks positions inside one building; it is not a rating and must not be compared across buildings.

Worked example:

| Position | `DA_300` | `glare_risk` | `comfort_ppd` | `s_d` | `s_g` | `s_c` | score |
|---|---|---|---|---|---|---|---|
| P, 2 m from the window | 0.50 | 0.03 | 8.0 | 0.500 | 0.850 | 0.850 | 0.710 |
| far point | 0.05 | 0 | 6.0 | 0.050 | 1.000 | 0.950 | 0.605 |
| at the glass | 0.90 | 0.25 | 18.0 | 0.900 | 0 | 0.350 | 0.465 |

Hand check of the first row: `0.4*0.50 + 0.3*(1 - 0.03/0.20) + 0.3*(1 - 3/20) = 0.710`; the script gives 0.7100.

Tool: `desk_score(da_300, glare_risk, comfort_ppd, weights) -> {score, s_d, s_g, s_c}`, and the top-level tool `score_desk_positions(model, bundle, desks_requested) -> LayoutResult`, which builds the candidate grid (SPEC 6.4), calls DAY, GLR, CMF and LCT for each candidate, and picks the top N with minimum spacing.

## 5. Build-time test plan

All tests run offline. Tolerances are relative unless a unit is given. "Spec" means the worked example of the named entry.

| ID | Module | Test | Reference | Tolerance |
|---|---|---|---|---|
| T-GEO-1 | section 0.2 | `azimuth_true = azimuth_in_model + north_offset_deg`: normals (0, -1) and (1, 0) with offset 30; 1000 random vectors against `scipy.spatial.transform.Rotation` | 210, 120; SciPy | 1e-9 deg |
| T-GEO-2 | section 0.2 | opening rectangle from `relative_center`: edge (2, 1) to (6, 1), 0.3 gives a centre 1.2 m from the reference vertex; values outside [0, 1] are rejected | spec | 1e-9 m |
| T-DAY-1 | DAY-02 | `E_h / L_z` and `f_s0` by quadrature | `7 pi / 9`, `(3 pi + 8) / (14 pi)` | 1e-6 |
| T-DAY-2 | DAY-03 | `SC` at P and F of R0 | spec: 0.019944, 0.001589 | 1e-3 |
| T-DAY-3 | DAY-03 | uniform-sky kernel against Howell B-4 | closed form | 1e-5 |
| T-DAY-4 | DAY-03 | flux conservation: integral of unglazed `SC` over a 400 m plane at sill height | `A_open * f_s0` | 2e-3 |
| T-DAY-5 | DAY-03 | monotonic: `SC` falls with distance on the centreline; a point beside the window beats a point 6 m in (workplan A5) | ordering | exact |
| T-DAY-6 | DAY-04 | obstruction table at 10, 20, 30, 40 degrees | spec | 1e-3 |
| T-DAY-7 | DAY-05 | `IRC_sky`, `IRC_ground` of R0; lumen balance | spec: 0.003738, 0.001620 | 1e-3 |
| T-DAY-8 | DAY-05 | BRE numeric form with T 0.85, C 39, ground 0.1 against the general form | equal within the rounding of C | 2 % |
| T-DAY-9 | DAY-06 | `ADF` of R0; guard ratio | 1.62 %; grid mean within 0.5 to 2.0 times `ADF` | 1e-2 |
| T-DAY-10 | DAY-07 | three weather cases | spec values; and an independent transliteration of EnergyPlus `DayltgLuminousEfficacy` kept in the test file | 1e-3 against spec, 2e-3 against the transliteration |
| T-DAY-11 | DAY-07 | every coefficient of the table equals the EnergyPlus arrays | S2 | exact |
| T-DAY-12 | DAY-08, DAY-09 | toy day | spec table, `DA_300 = 0.5`, `cDA_300 = 0.7206` | 1e-3 |
| T-DAY-13 | DAY-10 | `D_T` for 14 900 lx | 2.01 %, 0.67 % | 1e-2 |
| T-GLR-1 | GLR-01 | four view factors at R0; uniform kernel against Howell B-3 | spec; closed form | 1e-3; 1e-5 |
| T-GLR-2 | GLR-02 | DGPs at 908, 3473 lx and inverse | 0.2405, 0.4000 | 1e-4 absolute |
| T-GLR-3 | GLR-04 | the four sun cases; formula against vector intersection | spec table | 1e-6 m |
| T-GLR-4 | GLR-05 | in a room with one window: back to the window gives no sun-in-view hours; facing gives at least as many glare hours as parallel | ordering | exact |
| T-CMF-1 | CMF-01, 02 | twelve "ISO 7730 2005" rows of `ts_pmv_ppd.json` (copy the rows into the test fixture) | table | 0.1 PMV, 1 PPD (the file's own tolerance) |
| T-CMF-2 | CMF-01, 02 | 200 random points inside the validity box against `pythermalcomfort.pmv_ppd_iso(model="7730-2005", limit_inputs=False, round_output=False)` (test-only dependency) | reference implementation | 0.01 PMV, 0.1 PPD |
| T-CMF-3 | CMF-03 | two cases, both forms | spec | 0.01 K |
| T-CMF-4 | CMF-04 | example and resistance divider | 11.90 | 0.01 K |
| T-CMF-5 | CMF-05 | solid angle closed form against quadrature; closure over a box at five random interior points | 1 | 1e-6 |
| T-CMF-6 | CMF-06 | B-3 superposition against quadrature; R0 and severe cases | spec | 1e-4; 0.05 K |
| T-CMF-7 | CMF-07 | 26 seated "ASHRAE 55 2017" rows of `ts_solar_gain.json` with `I_diff = 0.2 I_dir`, `R_floor = 0.6` | table | 0.1 W/m2, 0.1 K (the file's own tolerance) |
| T-CMF-8 | CMF-07 | spec example; Arens skylight example | 37.65 W/m2, 9.02 K; 16.5 W/m2, 3.9 K | 1e-3; 2 % |
| T-LCT-1 | LCT-01 | table at 500 lx; end points of the dimming line; ideal limit equals `cDA` | spec | 1e-4 absolute |
| T-LCT-2 | LCT-02 | 91.3 kWh example; `none` gives low 0 | spec | 1e-3 |
| T-LCT-3 | LCT-03 | three rows; score rises with `DA_300`, falls with `glare_risk` and `comfort_ppd` | spec; ordering | 1e-4 |
| T-INT-1 | all | `score_desk_positions` on fixture `model`: `low <= expected <= high` for every `Ranged`; every `DeskScore` field inside its range; N recommended desks respect the spacing | contract | exact |

Reference implementations are test-only dependencies; the shipped code must not import `pythermalcomfort`.

## 6. Unverified, do not implement

Nothing in this list is used by the entries above unless the entry says so and carries a [P] or [U] tag. Each item needs the named source opened before it is built on.

| # | Item | Why it is here | What the spec does instead |
|---|---|---|---|
| U1 | BRS / BRE table of the coefficient `C` against obstruction angle (39, 35, 31, 25, 20, 14, ...) and the table converting average `IRC` to minimum `IRC` | seen only in a search-result excerpt of a BRS digest mirror that refused download; BRE Digests 309 and 310 and Hopkinson, Longmore and Petherbridge (1954) not opened | DAY-05 derives `f_s(theta_o)` and checks it against those numbers; only the average `IRC` is used |
| U2 | BRE rule that an obstruction has one tenth of the mean sky luminance (or `ERC = 0.2 SC` with CIE protractors) | recalled, not opened | DAY-04 derives `k_obs` from reflectances; `ERC` is [P] |
| U3 | Closed-form sky component of a vertical window under the CIE sky (Hopkinson, Petherbridge, Longmore, "Daylighting"; Tregenza and Wilson) | books not opened | DAY-03 integral, verified numerically and by flux conservation |
| U4 | ISO 7726 Annex B angle factors for seated and standing persons (`F_max`, A to E fit) | ISO 7726 not opened; two open papers print different coefficients for the same case | CMF-05 small-sphere factor |
| U5 | ISO 7730 clause 6.5 percentage-dissatisfied curves for radiant asymmetry | ISO 7730 not opened; one open source (S18) | CMF-06 uses the limit only; the cool-wall curve is informative [P] |
| U6 | ISO 7730 comfort categories A, B, C and its tables of design values (met, clo) | not opened | CMF-02 uses the comfort zone PMV within 0.5 quoted in S12; met and clo are assumptions |
| U7 | ASHRAE 55 text on the validity of the simple operative temperature (radiant-air difference below about 4 K) | not opened | CMF-03 flags it [U] |
| U8 | IES LM-83: sDA 300 lx / 50 % and ASE 1000 lx / 250 h, 8 am to 6 pm analysis period | paid, not opened | DAY-09 uses the generic daylight autonomy definition; `direct_sun_hours` is reported without a threshold |
| U9 | EN 17037 Table A.7 thresholds for the fraction of time above a DGP limit; Tables A.3 and A.4 beyond the five city values quoted | standard not opened | GLR-02 uses the Wienold 2009 classes; DAY-10 computes `E_v,d,med` from weather |
| U10 | Guth position index formula; any use of the full DGP | not opened; needs a luminance map | GLR-03 is reference only |
| U11 | Constants of the full DGP as printed in Wienold and Christoffersen (2006): 9.18e-2 and 0.16 (S8 paper) against 0.092 and 0.159 (`evalglare.c`) | paper not opened | not computed |
| U12 | Useful daylight illuminance bands (100 to 300, 300 to 3000 lx) | secondary source only (S20) | not used |
| U13 | Continuous daylight autonomy as defined by Rogers (2006) and Reinhart, Mardaljevic, Rogers (2006) | paper not opened | DAY-09 definition is [P] |
| U14 | Manual light-switching behaviour (Hunt 1979; Lightswitch-2002, Reinhart 2004); EN 15193 daylight dependency factors | not opened | LCT-02 placeholder `k_m` [U] |
| U15 | Inside surface coefficient `h_i` (ISO 6946 `R_si = 0.13 m2K/W`; ASHRAE 8.29 W/m2K) | not opened here | CMF-04 takes `h_i` from physics 02 |
| U16 | Default interior reflectances of any standard; low and high bounds of `glazing.visible_transmittance`, `glazing.glazed_fraction`, the obstruction defaults | design ranges with no source | section 0.4 marks them [U] |
| U17 | Angular dependence of glazing transmittance for the direct beam | belongs to physics 02 `WIN` | normal-incidence value used, which overstates the beam |
| U18 | Illuminance columns in EPW or TMY weather files | not checked | DAY-07 computes illuminance from irradiance |
| U19 | Kasten (1966) air-mass paper | not opened; formula taken as coded in EnergyPlus and as cited by Perez | DAY-07 |
| U20 | CIE S 011 / ISO 15469 sky types, CIE clear sky, Perez all-weather sky luminance model | not opened; not needed by this method | DAY-02 only |
| U21 | Minimum dimming fractions 0.2 and 0.3 as defaults of any product or code | recalled | section 0.4 marks them [U] |

Known limits of the method itself, not source gaps: no furniture, partitions, blinds, overhangs, reveals or specular surfaces; overcast-shaped sky at all hours; one `IRC` value per room; small-sphere body; steady-state glass temperature without absorbed solar heat.

## 7. Verification log

Date checked for every row: 2026-11-14. Scripts were run with `venv/bin/python -I` in a scratch directory outside the repo (Python 3.12, numpy 2.5, scipy 1.18, pythermalcomfort 4.8.1): `verify_day.py`, `verify_obs.py`, `verify_rest.py`, `verify_cmf2.py`. They are not part of the repo; section 5 turns the same checks into unit tests. The azimuth conversion and the opening placement of section 0.2 were checked by `verify_azimuth.py` after the contract fixed the sign of `north_offset_deg`; no worked example in sections 1 to 4 changed, because all of them are in the wall frame.

| Entry | Primary source | Second source | Result | How the example was recomputed |
|---|---|---|---|---|
| DAY-01 | Bryan 1980 (S5) | MIT OCW (S3) | pass | sum of DAY-03 and DAY-05 by script |
| DAY-02 | EnergyPlus Eng. Ref. (S2) | Radiance `skybright.cal`, `gensky.c` (S6) | pass | analytic and `scipy` quadrature, both integrals, 6 digits |
| DAY-03 | EnergyPlus Eng. Ref. (S2) | Bryan 1980 (S5) | pass | 1-D quadrature with closed form in altitude against 800 x 800 midpoint sum; uniform sky against Howell B-4; flux conservation |
| DAY-04 | MIT OCW slide 9 (S3) for the treatment; luminance derived | none | pass for arithmetic; luminance rule [P] | split-window analytic against 2000 x 2000 ray grid |
| DAY-05 | Bryan 1980 eq. (4) (S5) | EnergyPlus split-flux (S2); BRE numeric form (S3) | pass | fraction form, lumen balance, BRE numeric form; `f_sky` by quadrature and Monte Carlo |
| DAY-06 | BR 209 as quoted in S4 | MIT OCW slide 6 (S3) | pass; differs from the grid mean of DAY-01 by a factor of 1.5 on R0, documented | direct arithmetic and 0.25 m grid of DAY-01 |
| DAY-07 | Perez et al. 1990 (S1), scan read | EnergyPlus `DayltgLuminousEfficacy` source (S2) | pass, all 64 coefficients identical | paper equations against a transliteration of the EnergyPlus routine, three cases, within 0.03 % |
| DAY-08 | Bryan 1980 (S5), EnergyPlus (S2) | EN 17037 method 1 via S9, S10 | pass | vector form and component-by-component sum |
| DAY-09 | S20 definitions | none opened for `cDA` | pass for arithmetic; `cDA` definition [P] | direct count; `1 - cDA` against mean `f_L` of LCT-01 |
| DAY-10 | S10 eq. (2); EN 17037 Table A.1 via S9 | S9 Tables 3 and 4; S19 for EN 12464-1 | pass | four city values against printed targets; inverse for point P |
| GLR-01 | Wienold 2009 (S7) for the quantity; S2 for the photometric law | none for the shortcut | pass for arithmetic; simplification | adaptive double quadrature against 1500 x 1500 sum; uniform case against Howell B-3 |
| GLR-02 | Wienold 2009 eq. (1) (S7) | Atzeri et al. 2017 eq. (3) (S8) | pass | forward and inverse |
| GLR-03 | Atzeri et al. 2017 eq. (2) (S8) | `evalglare.c` (S8) | form agrees; constants differ in the third digit, original paper not opened | both constant sets by script |
| GLR-04 | validity statement of S7; plane geometry | none | pass for geometry; rule is a design simplification | closed form against vector ray-plane intersection |
| GLR-05 | Wienold 2009 Table 5 (S7) | none | pass for arithmetic | six toy hours by script and one by hand |
| CMF-01 | `pythermalcomfort` (S11) for ISO 7730 | `ladybug-comfort` (S13); 12 table rows | pass | own solver (Brent root) against `pmv_ppd_iso` and against the table; max 0.05 PMV from one-decimal table values |
| CMF-02 | S11 | S13 | pass | own against reference implementation |
| CMF-03 | S11 (`operative_tmp`) | S21 eq. (2) | pass | both forms against the reference implementation |
| CMF-04 | derivation | S16 for context | pass; `h_i` [P] | direct and resistance divider |
| CMF-05 | S21 eq. (1), S15 eq. (3) for ISO 7726 | Arens 2015 eq. (1) (S12) | pass; small-sphere simplification | corner formula against quadrature; six-face closure to 1e-9 |
| CMF-06 | S15 eqs (2) to (5) for ISO 7726 | Howell B-3, B-4 (S14); limits S16 Table 4 and S17 | pass; PD curve [P] | superposition against quadrature |
| CMF-07 | Arens et al. 2015 (S12) | `pythermalcomfort.solar_gain` and 26 table rows (S11) | pass | own against reference implementation, table rows (max 0.05) and the paper's skylight example (1 %) |
| CMF-08 | CMF-01 to CMF-07 | none | pass for arithmetic; aggregation is a design choice | own chain against reference implementation |
| LCT-01 | EnergyPlus Eng. Ref. (S2) | none independent | pass | table by script, one row by hand, end-point and `cDA` identities |
| LCT-02 | arithmetic on LCT-01 | none | pass; `k_m` [U] | annual product and hourly sum |
| LCT-03 | design choice | none | pass for arithmetic | script and hand |

Entries without an independent second published source: DAY-04 (luminance rule), GLR-01, GLR-04, GLR-05, CMF-04, CMF-08, LCT-01, LCT-02, LCT-03. For these the arithmetic was verified twice, but the modelling choice rests on one source or on this spec.

## 8. Contract notes for `specs/SPEC.md`

Names below are the contract's names as settled on 2026-11-14. Items 2 to 4 and 6 were accepted from an earlier draft of this section and are listed so that code and contract use the same spelling.

1. `DeskScore` field meanings and units: `daylight` = `DA_300`, fraction 0 to 1 of occupied hours at or above 300 lx (DAY-09); `glare_risk` = fraction 0 to 1 of occupied hours that are glare hours (GLR-05); `comfort_ppd` = mean PPD in percent, 5 to 100 (CMF-08); `score` 0 to 1 (LCT-03).
2. `DeskScore` fields filled by this file: `daylight_factor` (fraction, DAY-01), `view_azimuth_deg` (true azimuth of the recommended facing, GLR-05), `direct_sun_hours` (GLR-04), `max_dt_pr_k` (CMF-06, CMF-08), `warnings`.
3. `LayoutResult` fields filled by this file: `target_lux` (300, DAY-09), `setpoint_lux` and `control_type` (LCT-01, LCT-02), `window_source` (`"measured"` or `"vision"`, section 0.2), `score_weights` (LCT-03), `occupied_hours_per_year` (section 0.3), `lighting_kwh_saved` (`Ranged`, LCT-02).
4. `Surface`: a window surface is tied to its rectangle through `source_edge_id` and `source_opening_id` (`None` when the window came from vision). `visible_transmittance` (`Ranged`, optional) carries `tau`; when it is absent the assumption `glazing.visible_transmittance` of section 0.4 applies. `shgc` alone is not enough for daylight.
5. `Opening`: settled: `type` is one of `"divider"`, `"doorway"`, `"opening"`, `"window"` and `"window"` means glazing; `relative_center` is a fraction of the edge length in [0, 1]. Still open, [P] Data lane: which vertex of the edge `relative_center` is measured from (section 0.2 assumes the first of `WallEdge.vertex_ids`).
6. `Room.polygon` (ordered list of x, y in the model frame) is the room outline this file uses.
7. `BuildingModel.north_offset_deg`: settled, `azimuth_true = azimuth_in_model + north_offset_deg` (section 0.2). Nothing open on this side; the direction of the Matterport quaternion is [P] Data lane under physics 01 ROOF-02.
8. Section 6.4 step 4 ("savings come from lighting energy displaced"): with no daylight control, moving a desk saves lighting energy only if people switch lights off. LCT-02 reports that case as a range from zero with a placeholder expected value. Suggested wording: the saving is claimed in full only with daylight controls (`LGT_CTRL`), and otherwise shown as a potential with its range.
9. Assumption keys introduced here (open item O10): section 0.4.
10. `Systems` has no lighting control type or setpoint; they are assumption keys here (`lighting.control_type`, `lighting.setpoint_lux`) and are echoed in `LayoutResult.control_type` and `LayoutResult.setpoint_lux`.
11. Interfaces this file needs from other physics files: hourly sun altitude and azimuth, direct normal, diffuse horizontal and global horizontal irradiance, extraterrestrial normal irradiance, dew point and dry bulb (physics 01); hourly zone air temperature, heating or cooling mode, the inside surface coefficient `h_i`, and optionally an angular transmittance function (physics 02).
12. Section 6.4 step 2 and the comment on `DeskScore.daylight` point at `physics.md`; the entries are in this file (open item O13).

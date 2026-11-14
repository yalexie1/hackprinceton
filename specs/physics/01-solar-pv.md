# Physics 01: Solar position, irradiance, PV, shading, roof, layout

Status: draft, verified 2026-11-14. Owner: @yalexie1 (Analysis lane). Part of the physics library referenced by `specs/SPEC.md` sections 6.3 and 9.

Every entry below has an ID (`SOL-`, `IRR-`, `PV-`, `SHD-`, `ROOF-`, `LAY-`). A tool result lists the IDs it used in `MeasureResult.formula_ids`.

## 0. Conventions

### 0.1 Units, angles, frames

| Quantity | Convention |
|---|---|
| Units | SI. Irradiance W/m2, power W, energy kWh, temperature degC, length m, wind m/s. |
| Angles | Degrees at every function boundary. Radians only inside trigonometric calls. |
| Azimuth (sun and surfaces) | 0 = true north, clockwise: 90 east, 180 south, 270 west. Same as the contract. |
| Tilt | 0 = horizontal, facing up. 90 = vertical. Same as the contract. |
| Zenith | 0 = sun overhead. Elevation = 90 - zenith. |
| Hour angle | Negative before solar noon, positive after. 15 degrees per hour. |
| Latitude, longitude | Degrees, north and east positive. |
| World frame | ENU: x east, y north, z up, right-handed, metres. |
| Time | Timezone-aware timestamps. Weather years are in local standard time, no daylight saving. |
| Night | When apparent zenith >= 90 degrees every irradiance component is 0. |

Symbols used throughout: `theta_z` solar zenith, `A` solar azimuth, `beta` surface tilt, `gamma` surface azimuth, `theta` angle of incidence, `GHI`, `DNI`, `DHI` global horizontal, direct normal and diffuse horizontal irradiance, `E0n` extraterrestrial normal irradiance, `rho` ground albedo.

### 0.2 Reference implementation

pvlib-python 0.16.1 (Anderson et al. 2023, J. Open Source Software 8(92) 5994; Holmgren et al. 2018, JOSS 3(29) 884) is the reference implementation for sections 1 to 3. The functions in this file may be thin wrappers around pvlib. The formulas written here are the contract: the unit tests in section 7 check the implementation against the worked examples in this file and against pvlib.

### 0.3 Status tags

- **[V]** formula read in the primary source, or in an authoritative open reproduction that is named, and the worked example computed twice by independent means on 2026-11-14.
- **[V-repro]** as [V], but the primary paper was not opened; the formula was read in two independent reproductions that agree. Named in each entry.
- **[P]** pending a decision or a live check by the named lane.
- **[U]** unverified. Listed in section 8. Do not build on it without checking.

### 0.4 Running example

Used by most entries so that the numbers chain from one entry to the next. The sun angles are round input values, not the real sun position at that time.

| Input | Value |
|---|---|
| Site | Los Angeles, latitude 34.05, longitude -118.25, time zone UTC-8, elevation 90 m |
| Day | 21 June, day of year n = 172 |
| Sun | theta_z = 30, A = 150 |
| Surface | beta = 20, gamma = 180 |
| Weather | GHI = 800 W/m2, air temperature 30 degC, wind 2 m/s at 10 m, albedo 0.2 |
| Array | 6.0 kW DC nameplate, temperature coefficient -0.35 %/degC, DC/AC ratio 1.2, nominal inverter efficiency 0.96 |

### 0.5 Sources and how each was obtained

| Key | Source | Obtained |
|---|---|---|
| SPA | Reda, I. and Andreas, A., "Solar Position Algorithm for Solar Radiation Applications", NREL/TP-560-34302, revised January 2008. Journal version: Solar Energy 76(5), 577-589, 2004, doi:10.1016/j.solener.2003.12.003 | Report PDF opened (archived copy of nrel.gov) |
| PVW5 | Dobos, A. P., "PVWatts Version 5 Manual", NREL/TP-6A20-62641, 2014, doi:10.2172/1158421 | Report PDF opened |
| SAM15 | Gilman, P., "SAM Photovoltaic Model Technical Reference", NREL/TP-6A20-64102, 2015 | Report PDF opened |
| KING04 | King, D. L., Boyson, W. E., Kratochvil, J. A., "Photovoltaic Array Performance Model", Sandia SAND2004-3535, 2004 | Report PDF opened (OSTI) |
| GAG16 | Gagnon, P., Margolis, R., Melius, J., Phillips, C., Elmore, R., "Rooftop Solar Photovoltaic Technical Potential in the United States: A Detailed Assessment", NREL/TP-6A20-65298, 2016 | Report PDF opened |
| JK12 | Jordan, D. C. and Kurtz, S. R., "Photovoltaic Degradation Rates: An Analytical Review", NREL/JA-5200-51664, 2012 (preprint of Prog. Photovolt. 21, 12-29, 2013, doi:10.1002/pip.1182) | Preprint PDF opened |
| NOAA | NOAA Global Monitoring Division, "General Solar Position Calculations" (solareqns.PDF) | PDF opened |
| PVPMC | Sandia PV Performance Modeling Collaborative, modelling guide pages: Perez sky diffuse, Hay and Davies sky diffuse, extraterrestrial radiation, ground-reflected irradiance, Sandia module temperature model | Web pages read through an automated page reader on 2026-11-13; equations restated by the reader, so every value taken from them was also checked against a second source |
| PVLIB | pvlib-python 0.16.1 source code | Installed and read |
| IFC21 | 2021 International Fire Code, Section 1205, full text as reproduced by the Fire Marshal's Office of the City of Wylie, Texas | PDF opened |
| CFC25 | 2025 California Fire Code (Title 24 Part 9), Section 1205, as reproduced by UpCodes | Web page read through an automated page reader |
| TXLGC | Texas Local Government Code section 214.212, as reproduced at texas.public.law | Web page read through an automated page reader; the official statute site could not be read by script |

Papers cited but **not opened** (paywalled or not found): Spencer 1971, Erbs et al. 1982, Perez et al. 1990, Hay and Davies 1980, Liu and Jordan 1963, De Soto et al. 2006, Kasten 1965, Passias and Kallback 1984, Anderson and Mikofski 2020, Michalsky 1988, Duffie and Beckman. Where an entry depends on one of them, the entry says which open reproductions were used instead.

## 1. Solar position (SOL)

Production code uses SOL-01. SOL-02 to SOL-05 are the classical closed-form algorithm, kept as an independent cross-check and for hand calculation; their measured error is given in SOL-05 and they must not replace SOL-01.

### SOL-01 Solar position, NREL SPA [V]

**Rule.** Compute topocentric solar zenith, apparent (refraction-corrected) zenith and azimuth with the NREL Solar Position Algorithm. The algorithm is a long series evaluation (heliocentric position from periodic terms, nutation, aberration, sidereal time, parallax); it is not retyped here. Implement it by calling `pvlib.solarposition.get_solarposition(time, latitude, longitude, altitude=..., pressure=..., temperature=..., method="nrel_numpy")`.

Two steps of the algorithm that matter to the rest of this file:

```
Refraction (SPA eq. 42 to 44), applied when the sun is above the horizon:
  de      = (P / 1010) * (283 / (273 + T)) * 1.02 / (60 * tan(e0 + 10.3 / (e0 + 5.11)))
  e       = e0 + de
  theta_z = 90 - e
Azimuth (SPA eq. 45, 46):
  Gamma = atan2(sin H', cos H' * sin(phi) - tan(delta') * cos(phi))     measured westward from south
  A     = (Gamma + 180) mod 360                                         measured eastward from north
```

**Symbols.** `e0` topocentric elevation without refraction (deg; the argument of tan is in degrees); `de` refraction correction (deg); `P` annual average local pressure (mbar); `T` annual average local temperature (degC); `H'` topocentric local hour angle (deg); `phi` latitude (deg); `delta'` topocentric declination (deg); `A` azimuth (deg, 0 = north, clockwise).

**Validity.** Years -2000 to 6000, stated uncertainty +/-0.0003 degrees in zenith and azimuth (SPA abstract and section 2). Needs Delta T (terrestrial time minus universal time); pvlib's default of 67 s is used. A 10 s error in Delta T moves the sun by about 0.04 degrees (the earth turns 15 arc-seconds per second), which is negligible here.

**Inputs for refraction.** `P` from site elevation (pvlib `atmosphere.alt2pres`) and `T` = annual mean air temperature of the weather file. Using 12 degC instead of 20 degC changed annual beam irradiance on the running-example plane by 0.0014 % (computed), so this choice is not critical.

**Which zenith to use downstream.** Apparent zenith for incidence angle, transposition and air mass. This is what pvlib's `ModelChain` does.

**Primary source.** SPA, section 3 (steps 3.1 to 3.16) and appendix A.5.
**Second source.** PVLIB `solarposition.spa_python`, an independent implementation (NumPy, not NREL's C code) that reproduces the published test case below.

**Worked example (SPA Table A5.1).** 17 October 2003, 12:30:30 local standard time, time zone -7 h, latitude 39.742476, longitude -105.1786, elevation 1830.14 m, pressure 820 mbar, temperature 11 degC, Delta T 67 s.

| Quantity | Published (Table A5.1) | pvlib 0.16.1 | Difference |
|---|---|---|---|
| Topocentric zenith, refraction-corrected | 50.11162 | 50.111622 | 2e-6 deg |
| Topocentric azimuth, eastward from north | 194.34024 | 194.340241 | 5e-7 deg |
| Equation of time | 14.641503 min | 14.641511 min | 8e-6 min |

Refraction step alone: e0 = 39.87205, eq. 42 by hand gives de = 0.016332 degrees; pvlib's apparent minus true elevation gives 0.016332 (difference 2e-15).

**Tool function.** `solar_position(times, lat_deg, lon_deg, elevation_m, pressure_pa=None, temperature_c=12.0) -> table[time; zenith_deg, apparent_zenith_deg, azimuth_deg, equation_of_time_min]`. `times` are timezone-aware. Angles in degrees.

### SOL-02 Equation of time, Spencer series [V-repro]

```
Gamma = 2 * pi * (n - 1) / 365                                                  [rad]
E     = 229.18 * (0.0000075 + 0.001868 cos(Gamma) - 0.032077 sin(Gamma)
                  - 0.014615 cos(2 Gamma) - 0.040849 sin(2 Gamma))             [minutes]
```

**Symbols.** `n` day of year (1 = 1 January); `Gamma` day angle (rad); `E` equation of time (minutes), apparent solar time minus mean solar time.

**Validity.** Any day of year. A fit to almanac data; in 2026 it differs from SPA by up to 1.1 minutes (computed over the year at the running-example site). Not for production; see SOL-05.

**Day angle.** NOAA adds the time of day, Gamma = 2 pi (n - 1 + (hour - 12) / 24) / 365. pvlib uses the whole day as written above, and this file follows pvlib. Measured over 2026 against SPA the two variants are equally accurate (maximum zenith error 0.57 and 0.58 degrees).

**Constant term.** NOAA prints the first constant as 0.000075. pvlib uses 0.0000075 and documents that Spencer himself reported 0.000075 as a misprint in the original paper. This file follows pvlib. The two differ by 0.0155 minutes (0.9 s), far below the error of the series itself.

**Primary source.** Spencer, J. W., "Fourier series representation of the position of the sun", Search 2(5), 172, 1971. Not opened.
**Reproductions used.** NOAA (official); PVLIB `solarposition.equation_of_time_spencer71`. Both agree on every coefficient except the constant term discussed above.

**Worked example.** n = 172: Gamma = 2.943591 rad, E = -1.3437 min. pvlib: -1.3437 min (difference 2e-5 min, from 229.18 against 1440/2pi). With the NOAA constant: -1.3282 min. SPA for the same day at 12:00 local standard time: -1.8867 min.

**Tool function.** `equation_of_time_spencer(day_of_year) -> minutes`.

### SOL-03 Declination, Spencer series [V-repro]

```
delta = 0.006918 - 0.399912 cos(Gamma) + 0.070257 sin(Gamma)
        - 0.006758 cos(2 Gamma) + 0.000907 sin(2 Gamma)
        - 0.002697 cos(3 Gamma) + 0.00148 sin(3 Gamma)                          [rad]
```

**Symbols.** `delta` solar declination (rad, north positive); `Gamma` as in SOL-02.

**Validity.** Any day of year; same limits as SOL-02.

**Primary source.** Spencer 1971 (not opened).
**Reproductions used.** NOAA; PVLIB `solarposition.declination_spencer71`. All seven coefficients agree.

**Worked example.** n = 172: delta = 0.409316 rad = 23.4520 degrees. pvlib: 23.4520 (difference 0).

**Tool function.** `declination_spencer(day_of_year) -> degrees`.

### SOL-04 True solar time and hour angle [V]

```
tst   = 60 * hr + mn + sc / 60 + E + 4 * lon - 60 * tz                          [minutes]
omega = tst / 4 - 180                                                           [degrees]
```

**Symbols.** `hr`, `mn`, `sc` local standard clock time; `E` equation of time (min, SOL-02); `lon` longitude (deg, east positive); `tz` offset from UTC (hours, UTC-8 is -8); `tst` true solar time (minutes after solar midnight); `omega` hour angle (deg, negative before solar noon).

**Validity.** Any location. Clock time must be standard time, not daylight time.

**Primary source.** NOAA, "true solar time" and "solar hour angle" equations.
**Second source.** PVLIB `solarposition.hour_angle`, which evaluates `15 * (hours_utc - 12) + lon + E / 4`, algebraically the same.

**Worked example.** 21 June 2026, 12:00:00, lon = -118.25, tz = -8, E = -1.3437 min: tst = 720 - 1.3437 - 473 + 480 = 725.656 min (12.0943 h); omega = 1.4141 degrees. pvlib: 1.4141 (difference 5e-15).

**Tool function.** `hour_angle(time, lon_deg, equation_of_time_min) -> degrees`.

### SOL-05 Zenith and azimuth from latitude, declination and hour angle [V]

```
cos(theta_z) = sin(phi) sin(delta) + cos(phi) cos(delta) cos(omega)
A            = atan2( -cos(delta) sin(omega),
                      sin(delta) cos(phi) - cos(delta) sin(phi) cos(omega) )  mod 360
```

**Symbols.** `phi` latitude; `delta` declination (SOL-03); `omega` hour angle (SOL-04); `theta_z` true zenith (no refraction); `A` azimuth, 0 = north, clockwise. The two arguments of atan2 are the east and north components of the sun's unit vector, so the quadrant is always right.

**Validity.** All latitudes and hour angles. At theta_z = 0 the azimuth is undefined; return 180. No refraction and no parallax.

**Primary source.** NOAA zenith equation, and its azimuth equation `cos(180 - A) = -(sin(phi) cos(theta_z) - sin(delta)) / (cos(phi) sin(theta_z))`, which gives the same angle but needs a separate morning or afternoon branch.
**Second source.** PVLIB `solarposition.solar_zenith_analytical` and `solar_azimuth_analytical`.

**Worked example.** phi = 34.05, delta = 23.4520, omega = 1.4141: theta_z = 10.6698, A = 187.0234. pvlib analytical: 10.6698 and 187.0234 (differences 0 and 2e-12). SPA (SOL-01) for the same instant: true zenith 10.6719, azimuth 186.3420.

**Measured accuracy of SOL-02 to SOL-05 against SOL-01.** All 4,096 hourly midpoints of 2026 with zenith below 85 degrees at the running-example site: maximum zenith error 0.57 degrees (mean 0.27), maximum azimuth error 0.78 degrees. The sun's disc is 0.53 degrees wide, so this is about one sun diameter. Cause: the Spencer series is fitted to a fixed reference year and uses a whole-day index. Acceptable only as a sanity check on SOL-01 with a tolerance of 1 degree.

**Tool function.** `solar_position_simple(time, lat_deg, lon_deg, tz_hours) -> (zenith_deg, azimuth_deg)`. Test helper, not used in production.

### SOL-06 Sun unit vector [V]

```
s = ( sin(theta_z) sin(A),  sin(theta_z) cos(A),  cos(theta_z) )        (east, north, up)
```

**Symbols.** `s` unit vector from the site toward the sun in the ENU frame; `theta_z` apparent zenith; `A` azimuth.

**Validity.** Follows from the angle conventions in section 0.1. Use only when theta_z < 90.

**Source.** Definition of zenith and azimuth; the same components appear in PVLIB `shading.projected_solar_zenith_angle` ("Sun's x, y, z coords") and `irradiance.aoi_projection`.

**Worked example.** theta_z = 30, A = 150: s = (0.250000, -0.433013, 0.866025), length 1.000000. Check by a second route: with the surface normal of ROOF-01 for beta = 20, gamma = 180, n = (0, -0.342020, 0.939693), the dot product n.s = 0.961897, equal to cos(theta) from IRR-04 and from `pvlib.irradiance.aoi` (15.8675 degrees), difference below 1e-12.

**Tool function.** `sun_vector(apparent_zenith_deg, azimuth_deg) -> (east, north, up)`.

### SOL-07 Which instant an hourly weather value stands for [V rule, P data]

**Rule.** An hourly irradiance value is an average or total over one hour. Evaluate SOL-01 at the midpoint of that hour. For the hour that contains sunrise or sunset, use the midpoint of the part of the hour when the sun is up.

**Why it matters.** One hour is 15 degrees of hour angle. Taking the end of the hour instead of the midpoint shifts the sun by 7.5 degrees, about 14 sun diameters.

**Primary source.** PVW5 section 5: "The sun position is calculated at the midpoint of the hour". 
**Second source.** SAM15 sections 3.1 and 4.1: default is the midpoint of the time step; in NSRDB typical-year files the first row is the hour ending at 1 a.m.

**Pending [P], Data lane.** The weather file must state which hour each row covers (hour ending, hour beginning, or an instantaneous value at the half hour). The Data lane confirms this for Open-Meteo's radiation variables from its documentation, normalises every weather file so that row k covers the hour from k-1 to k local standard time, and records the original convention in `ClimateSite.weather_source`. Until that is confirmed, a half-hour timing error is the largest unquantified risk in this file.

**Resolved.** The Data lane confirmed `hour_end` for Open-Meteo on 2026-11-14 (`ClimateSite.weather_time_convention`; physics.md section 3). For the sunrise and sunset hours, the sun counts as up when the apparent zenith is below 90 degrees, the same horizon as the night rule in section 0.1.

**Tool function.** `interval_midpoints(hour_ending_times, lat_deg, lon_deg) -> times` (shifts by 30 minutes and handles the sunrise and sunset hours).

## 2. Irradiance (IRR)

**Required path.** The weather source (Open-Meteo, chosen by the Data lane) supplies GHI, DNI and DHI already separated. IRR-04 gives the incidence angle; IRR-05, IRR-08 (Perez) and IRR-09 give the three plane-of-array components; IRR-10 adds them.

**Fallback path.** If a weather file has GHI only, IRR-02 (Erbs) estimates DNI and DHI first, and the result carries a warning. IRR-06 and IRR-07 are simpler sky models kept for the shading module and as cross-checks; IRR-07 is the substitute if IRR-08 cannot be evaluated.

Irradiance inputs each entry needs:

| Entry | GHI | DNI | DHI | Other inputs |
|---|---|---|---|---|
| IRR-01 extraterrestrial | | | | day of year |
| IRR-02 Erbs (fallback) | x | | | zenith, IRR-01 |
| IRR-03 air mass | | | | apparent zenith |
| IRR-04 incidence angle | | | | sun and surface angles |
| IRR-05 beam on plane | | x | | IRR-04 |
| IRR-06 isotropic sky | | | x | tilt |
| IRR-07 Hay and Davies sky | | x | x | IRR-01, IRR-04, zenith, tilt |
| IRR-08 Perez sky (required) | | x | x | IRR-01, IRR-03, IRR-04, apparent zenith, tilt |
| IRR-09 ground reflected | x | | | albedo, tilt |
| IRR-10 total | x | x | x | all of the above |

The three inputs should satisfy GHI = DNI cos(theta_z) + DHI. The implementation logs the residual for each file; no rejection threshold is set here.

### IRR-01 Extraterrestrial normal irradiance [V-repro]

```
Gamma = 2 * pi * (n - 1) / 365                                                                 [rad]
E0n   = Esc * (1.00011 + 0.034221 cos(Gamma) + 0.00128 sin(Gamma)
               + 0.000719 cos(2 Gamma) + 0.000077 sin(2 Gamma))                                [W/m2]
Esc   = 1366.1 W/m2
```

**Symbols.** `n` day of year, taken from the timestamp in UTC (this is what pvlib does when given timestamps); `E0n` irradiance on a plane normal to the sun at the top of the atmosphere; `Esc` solar constant.

**Validity.** Any day. Taking the local day instead of the UTC day changes E0n by at most 0.81 W/m2 (0.06 %), computed.

**Solar constant.** 1366.1 W/m2 is pvlib's default. PVPMC and SAM15 (eq. 6.17) use 1367. The difference is 0.07 % and only enters IRR-02, IRR-07 and IRR-08 through ratios. The standard behind 1366.1 (ASTM E490) was not opened; see section 8.

**Primary source.** Spencer 1971 (not opened).
**Reproductions used.** PVLIB `irradiance.get_extra_radiation(method="spencer")`; PVPMC "Extraterrestrial radiation" page, same five coefficients (that page prints the day angle as 2 pi n / 365 and shows the third term with a division sign, an evident typo).

**Worked example.** n = 172: E0n = 1321.62 W/m2. n = 3: 1414.02 W/m2. pvlib: 1321.62 and 1414.02 (difference 0).

**Tool function.** `extraterrestrial_normal_irradiance(day_of_year) -> W/m2`.

### IRR-02 Clearness index and Erbs decomposition of GHI [V-repro]

Fallback path only: used when the weather file has GHI but not DNI and DHI. Not needed with Open-Meteo data.

```
kt  = GHI / (E0n * max(cos(theta_z), 0.065)),  limited to 0 <= kt <= 1
DF  = 1 - 0.09 kt                                                        for kt <= 0.22
DF  = 0.9511 - 0.1604 kt + 4.388 kt^2 - 16.638 kt^3 + 12.336 kt^4        for 0.22 < kt <= 0.80
DF  = 0.165                                                              for kt > 0.80
DHI = DF * GHI
DNI = (GHI - DHI) / cos(theta_z)
If theta_z > 87 or GHI < 0 or DNI < 0:  DNI = 0 and DHI = GHI
```

**Symbols.** `kt` clearness index (dimensionless); `DF` diffuse fraction (dimensionless); irradiances in W/m2; `theta_z` zenith (deg).

**Validity.** Hourly values. An empirical correlation fitted to hourly data from US stations; individual hours scatter widely around it, so measured or satellite DNI and DHI are always preferred. The 0.065 floor and the 87 degree cut-off are pvlib's guards against division by a small cosine, not part of the original correlation.

**Primary source.** Erbs, D. G., Klein, S. A., Duffie, J. A., "Estimation of the diffuse radiation fraction for hourly, daily and monthly-average global radiation", Solar Energy 28(4), 293-302, 1982, doi:10.1016/0038-092X(82)90302-4, eq. 1. Not opened.
**Reproductions used.** PVLIB `irradiance.erbs`; the R package TrenchR (`RadiationPartitioningFunctions.R`, Erbs branch). Both give the same three ranges and the same seven coefficients.

**Worked example.** GHI = 800, theta_z = 30, n = 172 (E0n = 1321.62): kt = 0.69896, DF = 0.24560, DHI = 196.48 W/m2, DNI = 696.89 W/m2. pvlib: kt 0.69896, DHI 196.48, DNI 696.89 (difference 0).

**Tool function.** `decompose_ghi_erbs(ghi_w_m2, zenith_deg, day_of_year) -> (dni_w_m2, dhi_w_m2, kt)`.

### IRR-03 Relative air mass, Kasten [V]

```
AM = 1 / ( cos(theta_z) + 0.15 * (93.885 - theta_z)^(-1.253) )
```

**Symbols.** `AM` relative optical air mass (dimensionless, 1 at the zenith, not corrected for pressure); `theta_z` apparent zenith in degrees inside the bracket.

**Validity.** theta_z < 90. Used only for the brightness term of IRR-08.

**Primary source.** SAM15 eq. 6.16, the air mass used inside NREL's Perez implementation; it prints the constant rounded to 93.9. The original is Kasten, F., "A New Table and Approximation Formula for the Relative Optical Air Mass", CRREL Technical Report 136, 1965 (not opened).
**Second source.** PVLIB `atmosphere.get_relative_airmass(model="kasten1966")`, constant 93.885.

**Worked example.** theta_z = 30: AM = 1.153608. theta_z = 80: AM = 5.580339. pvlib: same (difference 0). With 93.9: 1.153608 and 5.580573. For comparison, 1/cos gives 1.154701 and 5.758770, and the Kasten and Young 1989 formula (pvlib's `ModelChain` default) gives 1.153992 and 5.586036; any of these changes the Perez result by far less than its own uncertainty.

**Tool function.** `relative_air_mass(apparent_zenith_deg) -> dimensionless`.

### IRR-04 Angle of incidence on a tilted plane [V]

```
cos(theta) = cos(beta) cos(theta_z) + sin(beta) sin(theta_z) cos(A - gamma)
```

**Symbols.** `theta` angle between the sun direction and the surface normal; `beta` tilt; `gamma` surface azimuth; `theta_z`, `A` apparent solar zenith and azimuth. All in degrees, azimuths from north clockwise. Equivalent to the dot product of ROOF-01's normal and SOL-06's sun vector.

**Validity.** Any orientation. cos(theta) < 0 means the sun is behind the plane.

**Primary source.** PVW5 eq. 1.
**Second source.** SPA eq. 47 (it measures both azimuths from south; only the difference enters). PVLIB `irradiance.aoi`.

**Worked example 1 (published).** SPA Table A5.1: slope 30, surface azimuth rotation -10 from south (gamma = 170), with the SOL-01 sun (50.111622, 194.340241): theta = 25.18700. Published: 25.18700. pvlib: 25.187000.
**Worked example 2 (running).** beta = 20, gamma = 180, theta_z = 30, A = 150: cos(theta) = 0.961897, theta = 15.8675. pvlib: 15.8675 (difference 0).

**Tool function.** `incidence_angle(tilt_deg, surface_azimuth_deg, apparent_zenith_deg, solar_azimuth_deg) -> degrees`.

### IRR-05 Beam irradiance on the plane [V]

```
Eb = DNI * max(cos(theta), 0)
```

**Symbols.** `Eb` beam plane-of-array irradiance (W/m2).

**Primary source.** PVW5 section 7 ("the beam normal input multiplied by the cosine of the angle of incidence").
**Second source.** PVLIB `irradiance.beam_component`.

**Worked example.** DNI = 696.885, cos(theta) = 0.961897: Eb = 670.33 W/m2. pvlib: 670.33.

**Tool function.** `poa_beam(dni_w_m2, incidence_deg) -> W/m2`.

### IRR-06 Isotropic sky diffuse [V]

```
Ed,iso = DHI * (1 + cos(beta)) / 2
```

**Symbols.** `(1 + cos(beta)) / 2` is the view factor from the tilted plane to an unobstructed sky of uniform radiance.

**Validity.** Exact for a uniform sky. Real skies are brighter near the sun and near the horizon, so this underestimates on sun-facing planes; production uses IRR-08. Used directly in SHD-02.

**Primary source.** SAM15 eq. 6.4, attributed there to Liu and Jordan (1963).
**Second source.** PVLIB `irradiance.isotropic`.

**Worked example.** DHI = 196.480, beta = 20: Ed,iso = 190.56 W/m2. pvlib: 190.56.

**Tool function.** `sky_diffuse_isotropic(dhi_w_m2, tilt_deg) -> W/m2`.

### IRR-07 Hay and Davies sky diffuse [V-repro]

```
Ai = DNI / E0n
Rb = max(cos(theta), 0) / max(cos(theta_z), 0.01745)
Ed,hd = DHI * ( Ai * Rb + (1 - Ai) * (1 + cos(beta)) / 2 )
```

**Symbols.** `Ai` anisotropy index (dimensionless), the share of diffuse treated as coming from the sun's direction; `Rb` ratio of beam on the plane to beam on the horizontal. The 0.01745 floor is pvlib's guard.

**Validity.** Hourly values, theta_z < 90. No horizon brightening. Fallback and cross-check only.

**Primary source.** Hay, J. E. and Davies, J. A., "Calculations of the solar radiation incident on an inclined surface", Proc. First Canadian Solar Radiation Data Workshop, 1980. Not opened.
**Reproductions used.** PVPMC "Hay and Davies sky diffuse model" page; PVLIB `irradiance.haydavies`. Same three equations.

**Worked example.** Ai = 696.885 / 1321.624 = 0.52729, Rb = 0.961897 / 0.866025 = 1.11070: Ed,hd = 205.15 W/m2. pvlib: 205.15.

**Tool function.** `sky_diffuse_haydavies(dhi, dni, e0n, tilt_deg, incidence_deg, zenith_deg) -> W/m2`.

### IRR-08 Perez 1990 sky diffuse, production model [V-repro]

```
kappa = 1.041                      (theta_z in radians below; 5.535e-6 if in degrees)
eps   = ( (DHI + DNI) / DHI + kappa * theta_z^3 ) / ( 1 + kappa * theta_z^3 )       sky clearness
Delta = DHI * AM / E0n                                                              sky brightness
F1    = max(0, f11 + f12 * Delta + f13 * theta_z)                                   circumsolar coefficient
F2    =        f21 + f22 * Delta + f23 * theta_z                                    horizon coefficient
a     = max(0, cos(theta))
b     = max(cos(85 deg), cos(theta_z))

Ed,iso  = DHI * (1 - F1) * (1 + cos(beta)) / 2
Ed,circ = DHI * F1 * a / b
Ed,hor  = DHI * F2 * sin(beta)
Ed      = max(0, Ed,iso + Ed,circ + Ed,hor)
```

Coefficients, chosen by the bin of `eps` (Perez et al. 1990, Table 6, irradiance set):

| Bin | eps from | to (below) | f11 | f12 | f13 | f21 | f22 | f23 |
|---|---|---|---|---|---|---|---|---|
| 1 | 1.000 | 1.065 | -0.008 | 0.588 | -0.062 | -0.060 | 0.072 | -0.022 |
| 2 | 1.065 | 1.230 | 0.130 | 0.683 | -0.151 | -0.019 | 0.066 | -0.029 |
| 3 | 1.230 | 1.500 | 0.330 | 0.487 | -0.221 | 0.055 | -0.064 | -0.026 |
| 4 | 1.500 | 1.950 | 0.568 | 0.187 | -0.295 | 0.109 | -0.152 | -0.014 |
| 5 | 1.950 | 2.800 | 0.873 | -0.392 | -0.362 | 0.226 | -0.462 | 0.001 |
| 6 | 2.800 | 4.500 | 1.132 | -1.237 | -0.412 | 0.288 | -0.823 | 0.056 |
| 7 | 4.500 | 6.200 | 1.060 | -1.600 | -0.359 | 0.264 | -1.127 | 0.131 |
| 8 | 6.200 | no limit | 0.678 | -0.327 | -0.250 | 0.156 | -1.377 | 0.251 |

**Symbols.** `eps`, `Delta`, `F1`, `F2` dimensionless; `AM` from IRR-03 (relative, not pressure-corrected); `E0n` from IRR-01; `theta_z` apparent zenith; the three parts are the isotropic background, the circumsolar part (treated as a point source at the sun, hence the same geometry factor a/b as the beam) and the horizon band. All irradiances W/m2.

**Validity.** Hourly or shorter values with DHI > 0 and theta_z < 90; otherwise Ed = 0. Empirical, fitted to measurements at several US and European sites.

**Primary source.** Perez, R., Ineichen, P., Seals, R., Michalsky, J., Stewart, R., "Modeling daylight availability and irradiance components from direct and global irradiance", Solar Energy 44(5), 271-289, 1990, doi:10.1016/0038-092X(90)90055-H. Not opened.
**Reproductions used.** (1) PVPMC "Perez sky diffuse model" page: same equations and the same 48 coefficients. (2) PVLIB `irradiance.perez(model="allsitescomposite1990")`: coefficient array compared value by value with the table above, identical. (3) SAM15 section 6.2 and Table 6: same structure; its coefficients carry seven decimals and agree with the table above within 0.0007 (checked by script).

**Differences between the reproductions, and the choice made here.**

- SAM15 eq. 6.14 prints `b = max(cos 85, cos AOI)`. PVPMC and pvlib use cos(theta_z). This file uses cos(theta_z); the SAM15 line is taken to be a misprint.
- SAM15 and PVW5 switch to the isotropic model for 87.5 <= theta_z <= 90. pvlib does not. This file follows pvlib; the energy in those hours is negligible.
- SAM15 fixes E0n at 1367 in Delta. pvlib and PVPMC use the day's E0n. This file uses the day's E0n.
- PVPMC calls AM "absolute" air mass. pvlib states relative, and SAM15's formula has no pressure term. This file uses relative air mass.

**Worked example.** DHI = 196.480, DNI = 696.885, E0n = 1321.624, theta_z = 30 (0.523599 rad), AM = 1.153608, beta = 20, cos(theta) = 0.961897:
eps = 4.0857 (bin 6), Delta = 0.17150, F1 = 0.70413, F2 = 0.17618, a/b = 1.11070.
Ed,iso = 56.380, Ed,circ = 153.663, Ed,hor = 11.839, Ed = 221.881 W/m2.
pvlib (with `return_components=True`): 56.380, 153.663, 11.839, 221.881 (differences below 1e-13).

**Tool function.** `sky_diffuse_perez(dhi, dni, e0n, tilt_deg, incidence_deg, apparent_zenith_deg, air_mass) -> {sky_diffuse, isotropic, circumsolar, horizon}` in W/m2. The three parts are returned because SHD-03 treats them differently.

### IRR-09 Ground-reflected irradiance [V]

```
Eg = GHI * rho * (1 - cos(beta)) / 2
```

**Symbols.** `rho` albedo of the surroundings (dimensionless); `(1 - cos(beta)) / 2` view factor from the plane to an infinite horizontal ground.

**Validity.** Isotropic reflection from an unshaded, infinite, horizontal ground. For a roof plane the "ground" it sees is mostly the roof and the neighbourhood; the term is small at roof tilts (3 % of rho * GHI at 20 degrees).

**Default.** rho = 0.2, or the hourly value in the weather file when present (PVW5 section 7).

**Primary source.** SAM15 eq. 6.20 (with GHI written as DNI cos(theta_z) + DHI).
**Second source.** PVPMC "POA ground reflected" page; PVLIB `irradiance.get_ground_diffuse`.

**Worked example.** GHI = 800, rho = 0.2, beta = 20: Eg = 4.82 W/m2. pvlib: 4.82.

**Tool function.** `poa_ground_reflected(ghi_w_m2, albedo, tilt_deg) -> W/m2`.

### IRR-10 Plane-of-array total [V]

```
Epoa = Eb + Ed + Eg
```

**Primary source.** PVW5 eq. 2. **Second source.** PVLIB `irradiance.get_total_irradiance(model="perez")`.

**Worked example.** 670.332 + 221.881 + 4.825 = 897.04 W/m2. pvlib: 897.04 (difference 0).

**Tool function.** `plane_of_array_irradiance(ghi, dni, dhi, day_of_year, apparent_zenith_deg, solar_azimuth_deg, tilt_deg, surface_azimuth_deg, albedo=0.2) -> {poa_global, poa_beam, poa_sky_isotropic, poa_sky_circumsolar, poa_sky_horizon, poa_ground}` in W/m2.

## 3. PV production (PV)

Chain per hour: IRR-10 components, PV-01 (reflection at the glass), PV-02 (cell temperature), PV-03 (DC power), PV-04 (losses), PV-05 (inverter), PV-06 (sum over the year), PV-07 (later years). This is the PVWatts Version 5 model, except that cell temperature uses the Sandia model (PV-02) instead of the Fuentes model, because the Sandia model is algebraic and its coefficients are published.

### PV-01 Incidence angle modifier and transmitted irradiance [V]

```
theta_r = asin( sin(theta) / n )                                                    Snell's law, n_air = 1
tau(theta) = exp(-K L / cos(theta_r)) * ( 1 - 0.5 * ( sin^2(theta_r - theta) / sin^2(theta_r + theta)
                                                     + tan^2(theta_r - theta) / tan^2(theta_r + theta) ) )
tau(0)     = exp(-K L) * ( 1 - ((n - 1) / (n + 1))^2 )
IAM(theta) = tau(theta) / tau(0);   IAM = 0 for theta >= 90
Etr = Eb * IAM(theta) + Ed + Eg
n = 1.526,  K = 4 1/m,  L = 0.002 m
```

**Symbols.** `theta` incidence angle (IRR-04); `theta_r` refraction angle in the glass; `n` refractive index of the cover glass; `K` glazing extinction coefficient (1/m); `L` glass thickness (m); `tau` transmittance; `IAM` dimensionless, 1 at normal incidence; `Etr` transmitted plane-of-array irradiance (W/m2). The modifier is applied to the beam component only.

**Validity.** Plain glass, unpolarised light, 0 <= theta < 90. For anti-reflective glass PVW5 uses a two-layer version (eq. 3 to 7) and reports about 0.5 % more annual energy; this file uses plain glass for all modules, which is slightly conservative.

**Primary source.** PVW5 section 8 (correction applied to the direct beam; n = 1.526; eq. 4 and 6 give the Fresnel bracket). PVW5 drops the absorption factor because it is below 0.1 %.
**Second source.** SAM15 eq. 9.13 to 9.15: the same expression with the absorption factor and n = 1.526, L = 0.002 m, K = 4 1/m. PVLIB `iam.physical` (same defaults). The original is De Soto, Klein and Beckman, Solar Energy 80, 78-88, 2006, doi:10.1016/j.solener.2005.06.010 (not opened).

**Worked example.** theta = 15.8675: IAM = 0.999758 with the defaults above (K = 4); 0.999890 without the absorption factor (K = 0). theta = 60: IAM = 0.946003 (0.947628 without the absorption factor). theta = 80: 0.6357 (without absorption). pvlib: 0.999758 with defaults, 0.999890 at K = 0, 0.946003 with defaults, 0.947628 at K = 0 (differences 0). Running example, **computed at K = 0**: Etr = 670.332 * 0.999890 + 221.881 + 4.825 = 896.96 W/m2. With the default K = 4 it is 670.332 * 0.999758 + 221.881 + 4.825 = 896.88 W/m2.

**Note (2026-11-14, found while building A4).** The running-example numbers that follow from this entry (Etr 896.96, the PV-03 input 896.963 and the SHD-03 transmitted value 611.88) were computed at K = 0. The implementation keeps K = 4, as this entry and the PV-06 ModelChain reference do; tests that reproduce those printed numbers pass K = 0 explicitly.

**Tool function.** `incidence_angle_modifier(incidence_deg, n=1.526, k_per_m=4.0, thickness_m=0.002) -> dimensionless`; `transmitted_irradiance(poa_beam, poa_sky_diffuse, poa_ground, incidence_deg) -> W/m2`.

### PV-02 Cell temperature, Sandia model [V]

```
Tm = Epoa * exp(a + b * WS) + Ta
Tc = Tm + (Epoa / 1000) * dT
```

| Module construction | Mount | a | b (s/m) | dT (degC) | Use in this project |
|---|---|---|---|---|---|
| Glass / cell / glass | Open rack | -3.47 | -0.0594 | 3 | |
| Glass / cell / glass | Close roof mount | -2.98 | -0.0471 | 1 | Expected value for modules mounted parallel to a pitched roof |
| Glass / cell / polymer sheet | Open rack | -3.56 | -0.0750 | 3 | Tilted racks on flat roofs; cool bound for pitched roofs |
| Glass / cell / polymer sheet | Insulated back | -2.81 | -0.0455 | 0 | Hot bound for pitched roofs |

**Symbols.** `Tm` module back-surface temperature (degC); `Tc` cell temperature (degC); `Ta` ambient air temperature (degC); `Epoa` incident plane-of-array irradiance from IRR-10, before PV-01 (W/m2); `WS` wind speed at the standard 10 m height (m/s); `a` dimensionless; `b` in s/m; `dT` cell-to-back temperature difference at 1000 W/m2.

**Validity.** Flat-plate modules near thermal equilibrium. Stated accuracy about +/-5 degC, which the report says gives less than 3 % effect on power. KING04 has no row for the common glass / polymer module on a close roof mount; the glass / glass close-mount row is the nearest published case and is used as the expected value, with the two rows marked above as bounds.

**Primary source.** KING04 eq. 11 and 12 and Table 1.
**Second source.** PVPMC "Sandia module temperature model" page (same a and b). PVLIB `temperature.sapm_cell` and `TEMPERATURE_MODEL_PARAMETERS["sapm"]` (same a, b, dT).

**Worked example.** Epoa = 897.037, Ta = 30, WS = 2.

| Row | Tm | Tc | pvlib Tc |
|---|---|---|---|
| Glass/glass, close roof mount | 71.467 | 72.364 | 72.364 |
| Glass/polymer, open rack | 51.957 | 54.648 | 54.648 |
| Glass/polymer, insulated back | 79.309 | 79.309 | 79.309 |
| Glass/glass, open rack | 54.786 | 57.478 | 57.478 |

**Tool function.** `cell_temperature_sapm(poa_global_w_m2, air_temp_c, wind_speed_m_s, a, b, delta_t) -> degC`.

### PV-03 Array DC power [V]

```
Pdc = (Etr / 1000) * Pdc0 * (1 + gamma * (Tc - 25))
```

| Module type (PVW5 Table 3) | Approximate efficiency | gamma |
|---|---|---|
| Standard | 15 % | -0.0047 per degC |
| Premium | 19 % | -0.0035 per degC |
| Thin film | 10 % | -0.0020 per degC |

**Symbols.** `Pdc` array DC power (W); `Pdc0` DC nameplate at 1000 W/m2 and 25 degC (W); `Etr` from PV-01 (W/m2); `Tc` from PV-02 (degC); `gamma` power temperature coefficient (1/degC, negative).

**Validity.** Crystalline silicon and thin film at the array level; linear in irradiance (PVW5 removed the low-light correction of version 1). Negative results are set to 0.

**Default.** gamma = -0.0035 (premium) as the expected value, -0.0047 as the low-yield bound. Replace with the data-sheet value of the chosen module when known.

**Primary source.** PVW5 eq. 8 and Table 3.
**Second source.** PVLIB `pvsystem.pvwatts_dc`.

**Worked example.** Etr = 896.963, Pdc0 = 6000, Tc = 72.364, gamma = -0.0035: Pdc = 0.896963 * 6000 * (1 - 0.0035 * 47.364) = 4489.62 W. pvlib: 4489.62 (difference 0).

**Tool function.** `pv_dc_power(transmitted_irradiance_w_m2, cell_temp_c, pdc0_w, gamma_per_c) -> W`.

### PV-04 System losses [V]

```
Ltotal = 100 * ( 1 - product over i of (1 - Li / 100) )          [percent]
Pdc,net = Pdc * (1 - Ltotal / 100)
```

| Loss | PVW5 default (%) | In this project |
|---|---|---|
| Soiling | 2 | 2 |
| Shading | 3 | 0 for a panel whose shading was computed by section 4; 3 otherwise |
| Snow | 0 | 0 |
| Mismatch | 2 | 2 |
| Wiring | 2 | 2 |
| Connections | 0.5 | 0.5 |
| Light-induced degradation | 1.5 | 1.5 |
| Nameplate rating | 1 | 1 |
| Age | 0 | 0 (handled by PV-07) |
| Availability | 3 | 3 |

**Validity.** The losses multiply; they are not summed. PVW5 states that its 3 % shading default stands for distant horizon obstructions on systems described as unshaded. The ray casting of section 4 covers near objects only; setting shading to 0 for ray-cast panels therefore ignores the far horizon, which is accepted and stated in the result's `warnings`.

**Primary source.** PVW5 eq. 9 and Table 6.
**Second source.** PVLIB `pvsystem.pvwatts_losses`.

**Worked example.** All defaults: Ltotal = 14.0757 %. pvlib: 14.0757; PVW5 quotes 14 %; GAG16 Table 1 quotes 14.08 %. With shading 0: Ltotal = 11.4182 % (pvlib 11.4182), so Pdc,net = 4489.62 * 0.885818 = 3976.99 W.

**Tool function.** `system_loss_fraction(losses_percent: dict) -> fraction`.

### PV-05 Inverter and DC/AC ratio [V]

```
Pac0     = Pdc0 / r                         AC nameplate from the array nameplate and the DC/AC ratio r
Pdc0,inv = Pac0 / eta_nom                   DC input at which the inverter reaches its AC nameplate
zeta     = Pdc,net / Pdc0,inv
eta      = (eta_nom / eta_ref) * ( -0.0162 * zeta - 0.0059 / zeta + 0.9858 )
Pac      = min( eta * Pdc,net , Pac0 );     Pac = 0 when Pdc,net <= 0
eta_nom = 0.96,  eta_ref = 0.9637
```

**Symbols.** `r` DC/AC ratio (dimensionless); `Pac0` inverter AC nameplate (W); `eta_nom` nominal inverter efficiency; `eta_ref` reference efficiency of the inverter the curve was fitted to; `zeta` load fraction; `eta` efficiency at that load; `Pac` AC power (W).

**Validity.** A typical post-2010 inverter from the California Energy Commission list. Output is clipped at the AC nameplate.

**Default.** r = 1.2 (GAG16 Table 1). PVW5's own default is 1.1. Both are configuration values.

**Primary source.** PVW5 eq. 10 and 11.
**Second source.** PVLIB `inverter.pvwatts`.

**Worked example.** Pdc0 = 6000, r = 1.2: Pac0 = 5000 W, Pdc0,inv = 5208.33 W. Pdc,net = 3976.99: zeta = 0.76358, eta = 0.96200, Pac = 3825.84 W. pvlib: 3825.84 (difference 0). Clipping: Pdc,net = 5600 gives eta * Pdc = 5371.51, so Pac = 5000 (pvlib 5000). Low load: Pdc,net = 250 gives eta = 0.85880, Pac = 214.70 (pvlib 214.70). Check on the ratio: PVW5 says a 4 kW array at r = 1.1 has a 3.63 kW inverter; 4000 / 1.1 = 3636 W.

**Tool function.** `inverter_ac_power(pdc_net_w, pac0_w, eta_nom=0.96) -> W`.

### PV-06 Annual energy [V]

```
E_year1 = sum over the 8760 hours of Pac(h) * 1 h / 1000                 [kWh]
Yield   = E_year1 / (Pdc0 / 1000)                                         [kWh per kW DC]
```

**Validity.** Hourly steps with SOL-07 timing. Per panel, the same chain is run with that panel's shaded irradiance (SHD-03) and Pdc0 equal to the module rating; this assumes each module works at its own maximum power point (module-level electronics). With one string inverter, partial shading costs more than this linear sum; that case is flagged in `warnings`, not modelled.

**Source.** PVW5 section 13 (hourly AC aggregated to annual totals). Reference implementation: `pvlib.modelchain.ModelChain` configured with `transposition_model="perez"`, `airmass_model="kasten1966"`, `aoi_model="physical"`, `spectral_model="no_loss"`, `temperature_model="sapm"`, `dc_model="pvwatts"`, `ac_model="pvwatts"`, `losses_model="pvwatts"`.

**Worked example (whole chain, 8760 hours).** Running-example site and array, tilt 20, azimuth 180, glass/glass close-mount temperature row, shading loss 0, air 20 degC and wind 2 m/s all year. Irradiance input is a synthetic clear-sky year (Haurwitz clear-sky GHI from pvlib, split by IRR-02), so the result is a test of the chain, not a production estimate for Los Angeles.

| Annual quantity | Own NumPy code written from this file | pvlib ModelChain | Difference |
|---|---|---|---|
| Plane-of-array irradiation (kWh/m2) | 2543.682 | 2543.682 | below 1e-9 |
| Transmitted irradiation (kWh/m2) | 2498.739 | 2498.739 | below 1e-9 |
| DC energy after losses (kWh) | 11832.986 | 11832.986 | below 1e-9 |
| AC energy (kWh) | 11358.305 | 11358.305 | below 1e-9 |

Largest hourly AC difference: below 0.0001 W. Yield 1893 kWh/kW for this cloudless input.

Two details that had to match before the two columns agreed, and that the implementation must copy: the day of year in IRR-01 is the UTC day, and the refraction temperature in SOL-01 is the one given to both.

How the synthetic year was built (recorded 2026-11-14, when A4 reproduced the table): calendar year 2026; timestamps at the hour midpoints in fixed UTC-8; refraction temperature 20 degC; the Haurwitz clear-sky model and the IRR-02 Erbs split both run on the apparent zenith. Any other choice changes the totals in the fourth significant figure.

**Tool function.** `pv_annual_energy(weather, site, plane_or_panel, array_config) -> {annual_kwh, monthly_kwh[12], hourly_ac_w[8760], yield_kwh_per_kw}`.

### PV-07 Degradation over the analysis period [V]

```
E(y) = E_year1 * (1 - d)^(y - 1),   y = 1, 2, ...
sum of years 1..N = E_year1 * (1 - (1 - d)^N) / d
d = 0.005 per year
```

**Symbols.** `d` annual degradation rate (fraction per year); `y` year of operation.

**Validity.** A fleet median applied as a constant geometric rate. First-year light-induced loss is already in PV-04.

**Primary source.** JK12: nearly 2000 reported degradation rates, median 0.5 % per year, mean 0.8 % per year, 78 % of values below 1 % per year.
**Second source.** PVW5 section 11: long-term degradation "about 0.5 %/year".

**Default.** Expected 0.005; low-yield bound 0.008 (the JK12 mean).

**Worked example.** E_year1 = 9000 kWh: year 10 = 8603.01 kWh, year 25 = 7979.88 kWh, 25-year sum = 212,003.56 kWh by summation and by the closed form.

**Tool function.** `degraded_energy(year1_kwh, year, rate=0.005) -> kWh`; `lifetime_energy(year1_kwh, years, rate=0.005) -> kWh`.

### PV-08 Array rating from the module count [V arithmetic, U defaults]

```
Pdc0 = N * Pmod
```

**Symbols.** `N` number of modules; `Pmod` module rating at standard test conditions (W). Fills `SolarDesign.system_kw_dc = Pdc0 / 1000` and `panel_count = N`.

**Defaults [U].** Pmod = 430 W, module 1.722 m by 1.134 m (1.9527 m2, 220 W/m2, 22.0 %). These are typical of current residential modules but were not taken from a cited data sheet; set them from the product actually quoted. For comparison GAG16 used 160 W/m2 for the 2015 fleet.

**Worked example.** 14 modules: 6.02 kW. 15 modules: 6.45 kW.

**Tool function.** `array_rating(panel_count, module_w) -> kW DC`.

### PV-09 Range of the annual energy [V method]

`SolarDesign.annual_kwh` is a `Ranged`. It is produced by running PV-06 several times, not by a formula:

1. **Expected.** Every input at its expected value: expected tilt of each plane (ROOF-03), primary ridge direction (ROOF-05), temperature row "close roof mount", gamma = -0.0035, d as in PV-07.
2. **Tilt.** For each plane that carries panels, run PV-06 at the low, expected and high tilt. Yield is not monotonic in tilt for planes facing the equator, so take the minimum and the maximum of the three, not the values at the two ends.
3. **Ridge direction.** If the ridge direction is not confirmed (ROOF-05), repeat step 2 for the alternative ridge direction with the same number of panels on the best plane of that alternative.
4. **Other bounds.** Low: hot temperature row and gamma = -0.0047. High: cool temperature row.
5. **Model and input range.** `L_in` = smallest result of steps 1 to 4, `H_in` = largest. The layout itself (which planes, how many panels) is fixed at step 1.
6. **Weather variability, kept separate.** Year-to-year weather is not an input error, so it is not mixed into steps 2 to 4. PVGIS returns `SD_y`, the standard deviation of the annual yield between years, with its own annual yield `E_y`. Take `sigma_w = SD_y / E_y` and widen by the one-sided 10 % and 90 % points of a normal distribution (z = 1.2816):

```
low  = L_in * (1 - 1.2816 * sigma_w)
high = H_in * (1 + 1.2816 * sigma_w)
expected = result of step 1
```

   Stacking the two effects end to end, instead of adding them in quadrature, is a deliberate conservative choice. `sigma_w`, `L_in` and `H_in` are also written to `MeasureResult.params` so the two contributions can be shown separately.

**Worked example (tilt and ridge only).** Golden house lot, latitude 34.0935, longitude -118.3171, gable roof, pitch range 15.8 / 28.4 / 41.1 degrees (ROOF-03), 14 modules of 430 W (6.02 kW), PVWatts default losses including 3 % shading because the parametric roof has no ray casting. Synthetic clear-sky year as in PV-06, so the kWh illustrate the method only.

| Plane azimuth | Yield at 15.8 | at 28.4 | at 41.1 | Range relative to expected |
|---|---|---|---|---|
| 180 (south) | 1807.5 | 1867.5 | 1853.1 | -3.2 % to 0 % |
| 90 (east) | 1601.0 | 1540.8 | 1458.1 | -5.4 % to +3.9 % |
| 270 (west) | 1599.8 | 1538.7 | 1455.0 | -5.4 % to +4.0 % |
| 0 (north) | 1365.3 | 1104.2 | 863.7 | -21.8 % to +23.7 % |

Yields in kWh per kW DC. Every cell was computed by the own NumPy chain and by pvlib ModelChain; all twelve agree to better than 1e-6.

- Ridge confirmed to run east-west (planes face south and north), all 14 modules on the south plane: 10,881 / 11,242 / 11,156 kWh at the three tilts, so `annual_kwh` = Ranged(low 10,881, expected 11,242, high 11,242).
- Ridge direction not confirmed, alternative is a north-south ridge (planes face east and west): the best alternative plane gives 9,638 / 9,275 / 8,778 kWh, so `annual_kwh` = Ranged(low 8,778, expected 11,242, high 11,242).

Weather step for the confirmed-ridge case: the Data lane reports from a live PVGIS call (PVGIS-ERA5, 4 kW at 20 degrees facing south at this lot) 7,017 kWh per year with SD_y = 161 kWh, so sigma_w = 0.02294 and 1.2816 * sigma_w = 0.02941. Then low = 10,881 * 0.97059 = 10,561 kWh and high = 11,242 * 1.02941 = 11,573 kWh: `annual_kwh` = Ranged(low 10,561, expected 11,242, high 11,573). The PVGIS figures were not opened by the author of this file; they are quoted as reported.

The ridge direction is worth 22 % of the range here, the pitch 3 % and one year's weather 3 %. A fine tilt grid on the south plane has its maximum, 1870.6 kWh/kW, at 33.5 degrees, 0.17 % above the largest of the three sampled values; the three-point rule is kept and this is the size of what it can miss.

**Tool function.** `pv_energy_range(weather, site, design, building_model) -> Ranged(kWh)`.

## 4. Shading from 3D geometry (SHD)

Runs only where an exterior mesh exists (the 232 models with an aerial splat) or for row-to-row shading on flat roofs, where the rows themselves are the geometry. On the parametric roof of the P0 path there is nothing to cast rays against: the 3 % default of PV-04 stays and `shading_loss_fraction` is reported as 0.03 with a warning.

Scene: triangles in the ENU frame (exterior mesh, extruded tree masks from SHD-04, and the other module rows). Beam is shaded per hour (SHD-01). Sky diffuse is shaded by a factor computed once per panel (SHD-02). Ground-reflected irradiance is not reduced. SHD-03 combines them.

### SHD-01 Beam shading by ray casting [V]

```
For each sample point p_k on the panel (k = 1..K) and each hour with theta_z < 90 and cos(theta) > 0:
  origin    = p_k + 0.02 m * n               (lifted off the surface so the panel does not hit itself)
  direction = s                              (SOL-06)
  blocked_k = 1 if the ray hits any scene triangle at a distance t > 1e-6 m, else 0
f_b = (1 / K) * sum of blocked_k             beam shading fraction of the panel for that hour, 0..1
```

**Symbols.** `p_k` sample points in ENU metres, a 3 by 3 grid at the centres of nine equal cells of the module (K = 9); `n` unit normal of the panel (ROOF-01); `s` sun unit vector; `f_b` dimensionless.

**Validity.** Opaque obstructions, the sun treated as a point (no penumbra; the sun's 0.53 degree disc blurs a shadow edge by about 1 % of the distance to the obstruction). Mesh errors pass straight into the result. The 0.02 m lift and K = 9 are design choices, not from a source.

**Geometry behind the test.** A ray toward a sun at elevation `alpha` and azimuth `A` clears a long wall of height `h` at horizontal distance `d`, whose face is perpendicular to azimuth `gamma_w`, when `tan(alpha) > h * cos(A - gamma_w) / d`. This is the profile-angle relation of LAY-02 (SAM15 eq. 8.15).

**Source.** Geometric optics. Any correct ray-triangle intersection may be used (for example the Moller and Trumbore 1997 algorithm, J. Graphics Tools 2(1), 21-28, as implemented in common mesh libraries; the paper was not opened and is not needed, because the test below is analytic).
**Second source.** SAM15 section 7.2 applies an hourly beam shading factor to the beam component only (eq. 7.4), which is the same use of `f_b`.

**Worked example.** Point at the origin; vertical wall 4 m high, 10 m to the south, very long east-west. Sun due south (A = 180): threshold elevation atan(4/10) = 21.8014 degrees. Sun at A = 150: threshold atan(4 cos(30) / 10) = 19.1066 degrees. An independent NumPy ray-triangle routine (wall as two triangles) returns blocked at 0.05 degrees below each threshold and clear at 0.05 degrees above, for both azimuths.

**Tool function.** `beam_shading_fraction(sample_points_enu, normal_enu, sun_vector_enu, scene_mesh) -> fraction 0..1`.

### SHD-02 Sky view factor and diffuse shading factor [V]

```
SVF = (1 / pi) * integral over the sky hemisphere of V(w) * max(0, n . w) dOmega
    ~ (1 / pi) * sum over directions j of V_j * max(0, n . w_j) * dOmega_j
w_j = (cos(el_j) sin(az_j), cos(el_j) cos(az_j), sin(el_j)),   dOmega_j = cos(el_j) * d_el * d_az
S_d = SVF / ( (1 + cos(beta)) / 2 )
```

**Symbols.** `w` unit direction in the sky (elevation `el` > 0, azimuth `az`); `V` = 1 if a ray from the panel centre along `w` hits nothing, else 0; `n` panel normal; `dOmega` solid angle of the cell (sr); `SVF` sky view factor of the obstructed panel (dimensionless); `S_d` diffuse shading factor, 1 when nothing is in the way.

**Validity.** Uniform (isotropic) sky radiance, the same assumption SAM makes for diffuse shading (SAM15 section 8.3). Computed once per panel, not per hour. One ray origin per panel (its centre).

**Checks with closed forms.** Open sky: SVF = (1 + cos(beta)) / 2 (IRR-06). Horizontal panel and an infinitely long obstruction that rises to elevation `psi` on one side: SVF = (1 + cos(psi)) / 2, a loss of 1 - cos^2(psi / 2), which is the Passias and Kallback expression used by SAM (SAM15 eq. 8.9) and by `pvlib.shading.sky_diffuse_passias`. Panel tilted by `beta` and facing the same obstruction: SVF = (1 + cos(beta + psi)) / 2, which is what `pvlib.bifacial.utils.vf_row_sky_2d` returns for a point on a row (checked: 0.858309 from both for beta = 15, psi = 29.2241).

**Caution on the simpler expression.** SAM15 eq. 8.9 applies the horizontal-receiver loss, DHI * (1 - cos^2(psi / 2)), to tilted rows. For a tilted receiver the exact loss is DHI * (cos(beta) - cos(beta + psi)) / 2, which is larger: 0.125 against 0.064 of DHI at beta = 15, psi = 29.2. This file uses the exact view factor.

**Primary source.** SAM15 section 8.3 (isotropic assumption, eq. 8.7 to 8.10) for the principle; the integral is the standard definition of a view factor from a surface element to the visible sky.
**Second source.** PVLIB `shading.sky_diffuse_passias` for the horizontal case and `bifacial.utils.vf_row_sky_2d` for the tilted case.

**Worked example.** Midpoint grid 180 by 720 in elevation and azimuth (0.5 degree cells), visibility from the SHD-01 ray routine, wall with psi = 30 degrees (height 5.7735 m at 10 m).

| Case | Numerical | Closed form | Difference |
|---|---|---|---|
| beta = 20, open sky | 0.969855 | 0.969846 | 9e-6 |
| Horizontal, wall psi = 30 | 0.932958 | 0.933013 | 5e-5 |
| Loss, same case, against pvlib | 0.067042 | 0.066987 | 5e-5 |
| beta = 20 facing the wall | 0.821302 | 0.821394 | 9e-5 |

For the last case S_d = 0.821394 / 0.969846 = 0.84693.

**Grid size.** Largest error over the three cases, measured: 0.0038 with 9 by 36 rays, 0.0013 with 18 by 72, 0.0009 with 30 by 120, 0.0002 with 45 by 180. Default 30 by 120 (3,600 rays per panel).

**Tool function.** `sky_view_factor(point_enu, normal_enu, scene_mesh, n_el=30, n_az=120) -> SVF`; `diffuse_shading_factor(svf, tilt_deg) -> S_d`.

### SHD-03 Shaded plane-of-array irradiance for one hour [V arithmetic, design rule]

```
Eb,sh      = (1 - f_b) * Eb
Ecirc,sh   = (1 - f_b) * Ed,circ
Eiso,sh    = S_d * Ed,iso
Ehor,sh    = S_d * Ed,hor
Eg,sh      = Eg
Epoa,sh    = Eb,sh + Ecirc,sh + Eiso,sh + Ehor,sh + Eg,sh
Etr,sh     = Eb,sh * IAM(theta) + Ecirc,sh + Eiso,sh + Ehor,sh + Eg,sh
hourly shading factor = 1 - Epoa,sh / Epoa
```

**Symbols.** `f_b` from SHD-01; `S_d` from SHD-02; components from IRR-05, IRR-08, IRR-09; `IAM` from PV-01. PV-02 takes `Epoa,sh`; PV-03 takes `Etr,sh`.

**Rule and its basis.** SAM15 eq. 7.4 applies the beam factor to the beam, one diffuse factor to all sky diffuse, and leaves ground-reflected irradiance unreduced unless rows shade each other. This file follows that, with one change: the circumsolar part of the Perez sky diffuse is shaded with the beam. In the Perez model that part is a point source at the sun's position (it carries the same factor a/b as the beam, IRR-08), so an object that hides the sun hides it too. This is a design choice of this spec; no source was opened that states it. The two treatments differ by `Ed,circ * |f_b - (1 - S_d)|` in any hour.

**Validity.** Irradiance on a partly shaded module is averaged over the module; see PV-06 for the electrical caveat. Reflections from the obstructions are ignored.

**Worked example.** Running example with f_b = 3/9 and S_d = 0.84693: (670.332 + 153.663) * 2/3 + (56.380 + 11.839) * 0.84693 + 4.825 = 549.330 + 57.776 + 4.825 = 611.93 W/m2 against 897.04 unshaded; hourly shading factor 0.3178; transmitted 611.88 W/m2. Computed by script and by hand from the component values, which are the pvlib-checked values of IRR-05 and IRR-08. With SAM's treatment (one diffuse factor on all sky diffuse) the result would be 639.63 W/m2.

**Tool function.** `shaded_poa(poa_components, beam_shading_fraction, diffuse_shading_factor, incidence_deg) -> {poa_global_shaded, transmitted_shaded, shading_factor}`.

### SHD-04 Trees and neighbours as shading geometry [U inputs]

**Rule.** SAM 3 through Vexcel returns roof fragments and tree masks as map polygons; it gives area, not height.

1. Roof area under a tree mask is removed from usable area (ROOF-04). No panel is placed there.
2. For ray casting, a tree mask is extruded into an opaque prism from the ground to a height `H_tree`, and a neighbouring structure footprint into a prism of height `H_nb`.

**Unverified inputs.** No measured height comes with the masks. `H_tree` and `H_nb` are assumptions, entered in the assumption registry with a range and editable by the user; no default value is set in this file because none could be sourced. Trees are treated as opaque all year (a conservative choice); leaf-off transmission is not modelled.

**Tool function.** `extrude_mask(polygon_wkt, base_z_m, height_m) -> triangles`.

### SHD-05 Annual shading loss of a panel [V definition]

```
shading_loss_fraction = 1 - ( sum over hours of Epoa,sh ) / ( sum over hours of Epoa )
```

**Symbols.** Sums over the 8760 hours of the year, per panel. Fills `PanelPlacement.shading_loss_fraction`. It is an irradiation ratio; the energy ratio differs slightly because of temperature and inverter effects.

**Source.** Definition, consistent with the "POA total irradiance after shading only" output of SAM15 section 7.4.

**Worked example.** Unshaded 1900.0 kWh/m2, shaded 1750.0 kWh/m2: 1 - 1750 / 1900 = 0.0789.

**Screening rule.** GAG16 section 3.5 excluded roof area that received too little sun to produce 80 % of the energy of an unshaded system of the same orientation. Adapted here as: a panel position with `shading_loss_fraction` above 0.20 is not used. The 0.20 is this file's translation of that criterion, not a number printed in GAG16.

**Tool function.** `annual_shading_loss(hourly_poa_unshaded, hourly_poa_shaded) -> fraction`.

## 5. Roof geometry inputs (ROOF)

Two paths, as in `specs/SPEC.md` section 6.3:

- **Fitted planes** (`geometry_source = "splat"`, the 232 models with an aerial splat): plane normals come from the fit; ROOF-01 gives tilt and azimuth; usable area uses the polygon method of ROOF-04.
- **Parametric roof** (`geometry_source = "vexcel_parametric"`, the P0 path): Vexcel footprint plus roof shape class. Tilt is a range looked up by shape (ROOF-03), azimuth comes from the footprint's long axis (ROOF-05), usable area uses the area method of ROOF-04. Vexcel's roof height is not used to derive pitch.

### ROOF-01 Tilt and azimuth from a plane normal [V]

```
n = (nE, nN, nU), normalised, flipped if nU < 0
beta  = acos(nU)
gamma = atan2(nE, nN) mod 360                     undefined when beta = 0: store azimuth as None
Inverse:  n = ( sin(beta) sin(gamma), sin(beta) cos(gamma), cos(beta) )
From three points of the plane:  n = (p2 - p1) x (p3 - p1)
```

**Symbols.** `n` outward unit normal of the roof plane in ENU; `beta` tilt (deg, 0 = horizontal); `gamma` azimuth of the downslope direction, which is the direction the plane faces (deg, 0 = north, clockwise).

**Validity.** Any plane with 0 <= beta <= 90. Below beta = 2 degrees the azimuth is numerically meaningless; treat the plane as horizontal.

**Source.** Definition of the angle conventions in section 0.1; the inverse form is the surface normal used in PVLIB `irradiance.aoi_projection`.

**Worked example.** Points (ENU, metres) p1 = (0, 0, 3), p2 = (10, 0, 3), p3 = (0, 4, 5): n = (0, -0.44721, 0.89443), beta = 26.565 (a 6:12 pitch, atan(0.5) = 26.565), gamma = 180 (faces south, since the roof rises toward the north). Round trip beta, gamma to n and back for 1000 random orientations: largest error 2e-13 degrees. Independent check: n . s equals pvlib's cos(incidence) to 1e-12 (see SOL-06).

**Tool function.** `plane_orientation(normal_enu) -> (tilt_deg, azimuth_deg or None)`; `plane_normal(tilt_deg, azimuth_deg) -> (east, north, up)`.

### ROOF-02 Model frame to true north [V mathematics, P convention]

The Matterport Model API returns `Model.geocoordinates` with a rotation quaternion (`GeoReference.rotation` in the contract). North alignment is therefore data, not an inferred quantity. Registration of the floor outline to the Vexcel footprint is a cross-check, and the fallback when the georeference is missing.

```
Unit quaternion q = (w, x, y, z).  Rotation matrix:
    | 1 - 2(y^2 + z^2)   2(xy - wz)         2(xz + wy)       |
R = | 2(xy + wz)         1 - 2(x^2 + z^2)   2(yz - wx)       |
    | 2(xz - wy)         2(yz + wx)         1 - 2(x^2 + y^2) |
v_enu = R v_model
psi   = atan2( R[0][1], R[1][1] ) mod 360          azimuth of the model +y axis, clockwise from true north
gamma_true = (gamma_model + psi) mod 360           for a level model; tilt is unchanged
```

**Symbols.** `q` as returned (normalise before use); `R` rotation from the model frame to ENU; `psi` is the value stored in `BuildingModel.north_offset_deg.expected`; `gamma_model` an azimuth measured clockwise from the model +y axis.

**Validity.** `gamma_true = gamma_model + psi` holds when the rotation is about the vertical axis only (a level model). In general rotate the normal with R and apply ROOF-01.

**Pending [P], Data lane.** Confirm in `data-integration.md` section 3.2: (a) that the returned quaternion rotates model coordinates into an east-north-up frame and is not the inverse; (b) the model's axis convention (which axis is up). A wrong direction flips the sign of psi. The acceptance test is the cross-check itself: after rotation the floor outline must overlay the Vexcel footprint.

**Azimuth uncertainty.** `north_offset_deg` is no longer a wide range. Set low and high to psi -/+ Delta, where Delta is the absolute difference between psi from the georeference and psi from footprint registration when both exist, and `north_source = "georeference"`. Roof plane azimuths carry the same Delta. Sensitivity of annual AC energy to azimuth error, running-example site, synthetic clear-sky year, pvlib only (a single computation, not double-checked): south-facing plane at 20 degrees tilt, +/-5 degrees changes energy by 0.05 %; east- or west-facing at 20 degrees, +/-2 degrees changes it by 0.6 % and +/-5 degrees by 1.5 %; west-facing at 30 degrees, +/-5 degrees by 2.1 %. A Delta of a few degrees is therefore minor next to the pitch and ridge terms of PV-09.

**Source.** Standard unit-quaternion rotation matrix. Second source: `scipy.spatial.transform.Rotation.from_quat(...).as_matrix()`.

**Worked example.** Model +y points 25 degrees east of true north, so the model frame must be turned by -25 degrees about the up axis: q = (w, x, y, z) = (cos(-12.5), 0, 0, sin(-12.5)) = (0.976296, 0, 0, -0.216440). R from the formula equals SciPy's matrix to 1e-16; psi = 25.000; a plane facing "model south" (gamma_model = 180) at 20 degrees tilt comes out at gamma_true = 205.000, tilt 20.000. A random general quaternion also matches SciPy to 1e-16.

**Tool function.** `rotation_from_quaternion(x, y, z, w) -> 3x3 matrix`; `north_offset(rotation) -> degrees`; `to_true_azimuth(model_azimuth_deg, north_offset_deg) -> degrees`.

### ROOF-03 Roof pitch range by roof shape class [V for the sourced values, U where marked]

Lookup used on the parametric path to fill `RoofPlane.tilt_deg` (a `Ranged`, degrees). Key: Vexcel `roof-characteristics.shape.value` and the footprint size class of GAG16 (small: footprint below 5,000 ft2 = 464.5 m2; medium and large above).

| Shape class | Footprint | Low | Expected | High | Basis |
|---|---|---|---|---|---|
| flat | any | 0 | 1.2 | 9.5 | GAG16 section 3.3 defines flat as below 9.5 degrees. 1.2 degrees is a quarter unit in 12; see the covering table below. Modules on flat roofs sit on tilted racks (LAY-02), so this value has little effect on yield. |
| gable | small | 15.8 | 28.4 | 41.1 | GAG16 Table A-3, see below |
| hip | small | 15.8 | 28.4 | 41.1 | Same as gable. No published pitch statistics split by gable against hip were found. [U] |
| gable or hip | medium, large | covering minimum, or 1.2 if the covering is unknown | 15.8 | 28.4 | GAG16 Tables A-1 and A-2 plus the covering table; low confidence, see below. [U] |
| any other or unknown shape | any | 0 | 28.4 | 47.4 | Widest range (`geometry_source = "assumed"`): flat through the upper edge of the highest populated GAG16 class |

**Where the small-building numbers come from.** GAG16 processed lidar for 26.9 million buildings in 128 US cities, kept roof planes suitable for PV (not north-facing, not heavily shaded, tilt below 60 degrees) and binned tilted planes into four classes that split 9.5 to 60 degrees equally: edges 9.5, 22.125, 34.75, 47.375, 60; midpoints 15.8, 28.4, 41.1, 53.7. National average shares for small buildings (Table A-3, summed over the five azimuth classes): flat 0.26, the 15.8-degree class 0.16, the 28.4-degree class 0.48, the 41.1-degree class 0.10, the 53.7-degree class none shown. Of the tilted planes that is 22 %, 65 % and 14 %. Expected = midpoint of the dominant class; low and high = midpoints of the lowest and highest populated classes. If planes are spread evenly inside each class (an assumption), those two midpoints sit at about the 11th and 93rd percentile.

**Limits of this source, stated plainly.** (1) The classes are 12.6 degrees wide, so nothing finer than the midpoints can be claimed. (2) The statistics cover planes judged suitable for PV, by building size, not by roof shape. Knowing that a roof is a gable tells us only that it is not flat. (3) Medium and large buildings: 74 % and 93 % of suitable planes are below 9.5 degrees (Tables A-2 and A-1); of the tilted planes on medium buildings 38 % fall in the 15.8-degree class, 58 % in the 28.4-degree class and 4 % in the 41.1-degree class. A commercial roof that Vexcel labels gable may be a low-slope metal roof that GAG16 would count as flat, so the range for that row is deliberately wide and starts at the minimum slope of the roof covering. For such a building the pitch should be confirmed from the oblique images or by asking the user (`SPEC.md` section 5.3) before a quote relies on it.

**Roof covering minimum slopes** (optional floor on the low bound, keyed by Vexcel roof material). Source: 2021 International Building Code section 1507, as reproduced by UpCodes, read once through an automated page reader and not confirmed against a second copy, so listed in section 8. [U]

| Covering | Code minimum | Degrees |
|---|---|---|
| Asphalt shingles (1507.2.2) | 2 in 12 | 9.46 |
| Clay and concrete tile (1507.3.2) | 2.5 in 12 | 11.77 |
| Metal panels, lapped, no lap sealant (1507.4.2) | 3 in 12 | 14.04 |
| Metal panels, lapped, with lap sealant (1507.4.2) | 0.5 in 12 | 2.39 |
| Metal panels, standing seam (1507.4.2) | 0.25 in 12 | 1.19 |

Pitch conversion: `tilt = atan(rise / 12)`. 2:12 = 9.46, 4:12 = 18.43, 6:12 = 26.57, 8:12 = 33.69, 12:12 = 45.00 degrees (computed, and 6:12 checked against the ROOF-01 example).

**Golden lots.** House (gable, shingle, footprint 190.4 m2, small): 15.8 / 28.4 / 41.1; the shingle minimum of 9.46 does not bind. Both golden offices have flat membrane roofs: the Los Angeles office (PropertyId 246899, 17 storeys) and the Houston office (PropertyId 234088, 16 storeys). On a flat roof, tilt is a racking choice, not a roof property: use the flat-roof row and LAY-02 for row spacing. (The first golden office, a gabled metal warehouse, was dropped on 2026-11-14.)

**Footprints of towers and of different flights.** Two facts verified by the Data lane, 2026-11-14. (1) On both golden towers the Vexcel footprint outlines a podium or garage, not the tower: 1.7 and 4.6 times the CoStar typical floor plate. So for a building of more than three storeys, the roof area available for PV is taken as gross building area divided by storeys, not the footprint, and the footprint is used only as an upper bound. (2) A footprint depends on the layer set it was fetched with: on the LA office, `layer=urban` gave one structure of 2,207 m2, and the full layer list gave two structures, the primary 2,474 m2, from a different flight. The Data lane pins `layer=urban` and records the flight in `VexcelData.collection`; any area used here names that collection. Vexcel's calculated roof height is not used at all: its sign varies and it differs between identical calls.

**How the range reaches the yield.** PV-09, with a worked example on the golden house.

**Tool function.** `roof_pitch_range(shape_class, footprint_m2, roof_material=None) -> Ranged(deg)`.

### ROOF-04 Usable roof area [V geometry, U allowances]

**What the data can support.** SAM 3 through Vexcel returns roof fragments, not planes, so the masks give roof extent and tree overhang as areas. Obstructions (chimney, skylight, roof vent, AC unit) come from Vexcel's precomputed counts and have no positions.

**Area method (parametric roof).** For each plane from ROOF-05, with eave length `Le`, slope length `S` and tilt `beta`, all lengths measured in the plane:

```
A_plane   = A_plan / cos(beta)                                 sloped area from plan-view area
A_rect    = (Le - n_path * w_path) * (S - w_ridge)             after fire-code setbacks (ROOF-06)
A_obs     = share of plane * sum over obstruction types of count_t * (w_t + 2 c_t) * (l_t + 2 c_t)
A_tree    = area of tree mask over the plane / cos(beta)
A_usable  = max(0, A_rect - A_obs - A_tree)                    -> RoofPlane.usable_area_m2
N_plane   = floor( N_pack * A_usable / A_rect )                N_pack from LAY-01 on the setback rectangle
```

**Symbols.** `A_plan` plan-view area of the plane (m2); `n_path` number of pathways reserved on this plane (default 1 on each plane that carries modules); `w_path`, `w_ridge` setback widths (m, ROOF-06); `count_t` Vexcel count of obstruction type t; `w_t`, `l_t` assumed footprint of one obstruction (m); `c_t` assumed clearance around it (m); "share of plane" = the plane's plan area divided by the total roof plan area, because positions are unknown; `N_plane` module capacity of the plane.

**Obstruction allowances. Assumptions, not sourced [U].** No published allowance per roof object was found. The values below are engineering judgment and are entered in the assumption registry with their range.

| Obstruction | Assumed footprint (m) | Clearance each side (m) | Allowance, expected (m2) | Range (m2) |
|---|---|---|---|---|
| Roof vent | 0.3 x 0.3 | 0.3 | 0.81 | 0.4 to 1.5 |
| Skylight | 0.6 x 1.2 | 0.3 | 2.16 | 1.4 to 3.5 |
| Chimney | 0.6 x 0.9 | 0.5 | 3.04 | 2.0 to 5.0 |
| AC unit | 1.0 x 1.0 | 1.0 | 9.00 | 4.0 to 12.0 |

For the low end of the capacity range all counted obstructions are assigned to the best plane instead of being shared by area.

**Polygon method (fitted planes).** With the plane polygon in its own (u along the eave, v up the slope) coordinates: remove a strip `w_ridge` wide along the ridge edge and `w_path` wide along one rake edge (or the perimeter strip of ROOF-06 for commercial roofs), remove each located obstruction buffered by its clearance, remove tree mask area, then pack with LAY-01.

**Validity.** The area method cannot place individual modules around obstructions; it yields a count and an area. Eave overhang is ignored, which understates area slightly. The pathway rule (one strip on every plane that carries modules) is a conservative reading of ROOF-06, not a legal determination.

**Source.** Geometry, plus `SPEC.md` section 6.3 item 3 for the method. The proportional reduction of the module count is this file's rule.

**Worked example, area method (golden house).** Footprint 190.4 m2; bounding rectangle assumed 17.0 m by 11.2 m for this example (the real footprint polygon was not available when this was written); gable, ridge along the long side; beta = 28.4; Vexcel counts 1 chimney and 5 roof vents; module 1.722 m by 1.134 m with 0.0127 m gaps.

- Each plane: A_plan = 95.20 m2, S = 5.6 / cos(28.4) = 6.3662 m, A_plane = 108.23 m2.
- Setbacks w_path = 0.9144 m, w_ridge = 0.4572 m: A_rect = 16.0856 * 5.9090 = 95.05 m2.
- Obstructions: 3.04 + 5 * 0.81 = 7.09 m2 over the roof, half per plane: A_obs = 3.545 m2. A_usable = 91.50 m2.
- N_pack = 45 (landscape, 9 by 5). N_plane = floor(45 * 91.50 / 95.05) = 43 modules.
- Fire-code check: 43 modules cover 43 * 1.9527 * cos(28.4) = 73.9 m2 in plan view, 38.8 % of the 190.4 m2 roof, above the 33 % limit for the 18-inch ridge setback. Redo with w_ridge = 0.9144 m: A_rect = 16.0856 * 5.4518 = 87.70 m2, A_usable = 84.15 m2, N_pack = 42 (portrait, 14 by 3), N_plane = floor(42 * 84.15 / 87.70) = 40 modules, 36.1 % of plan area, consistent with the 36-inch setback. The alternative, staying at or below 33 % with the 18-inch setback, allows floor(0.33 * 190.4 / (1.9527 * cos(28.4))) = 36 modules. Capacity of the plane: 40 modules (17.2 kW).
- Computed by script and by hand.

**Worked example, polygon method.** Plane 10 m by 5 m, ridge strip 0.4572 m, one pathway 0.9144 m: usable 9.0856 * 4.5428 = 41.274 m2 (shapely: 41.274). Minus one vent of 0.3 m square buffered by 0.3 m (0.81 m2): 40.464 m2 (shapely: 40.464). Commercial roof 60 m by 30 m with a 4 ft perimeter: 57.5616 * 27.5616 = 1586.49 m2 (shapely negative buffer: 1586.49). Roof 100 m by 80 m with a 6 ft perimeter: 7355.01 m2 (shapely: 7355.01).

**Tool function.** `usable_area_parametric(plane, setbacks, obstruction_counts, tree_area_m2, module) -> {usable_area_m2, panel_capacity}`; `usable_polygon(plane_polygon, setbacks, obstruction_polygons, tree_polygons) -> polygon`.

### ROOF-05 Parametric roof planes and ridge direction [V geometry, U ridge assumption]

```
Minimum rotated rectangle of the footprint: sides L >= W, azimuth of the long side a_L (0..180).
Scale factor k = A_footprint / (L * W)            applies the rectangle's proportions to the real area

gable:  ridge along the long side (assumption).
        plane 1: gamma = (a_L + 90) mod 360,  plane 2: gamma = (a_L + 270) mod 360
        each:  A_plan = k * L * W / 2,   Le = L,   S = (W / 2) / cos(beta)
hip (equal pitch on all four sides):
        two trapezoids: gamma = (a_L + 90) mod 360 and (a_L + 270) mod 360,  A_plan = k * (L * W / 2 - W^2 / 4) each
        two triangles:  gamma = a_L and (a_L + 180) mod 360,                  A_plan = k * W^2 / 4 each
flat:   one plane, A_plan = A_footprint (towers: GBA / storeys), tilt from ROOF-03; the plane has no azimuth of its own,
        so RoofPlane.azimuth_deg (required in the contract) carries the azimuth chosen for the racks, 180 by default
All:    A_plane = A_plan / cos(beta)
```

**Symbols.** `L`, `W` sides of the minimum rotated rectangle (m); `a_L` compass bearing of the long side (deg); `gamma` plane azimuth; `Le` eave length; `S` slope length; `beta` tilt from ROOF-03.

**The two-way question on a gable.** A gable always has two planes facing opposite ways; both are created and LAY-03 decides which carries modules. What is uncertain is the ridge direction. "Ridge along the long side" is common but it is an assumption, not a sourced rule. [U] If it is wrong, the planes face a_L and a_L + 180 instead. The ridge counts as confirmed only when there is evidence (fitted planes from a splat, the oblique images read by the vision step, or the user). Until then `RoofPlane` carries the primary hypothesis and PV-09 step 3 widens `annual_kwh` with the alternative. In the PV-09 example this was the largest term in the range (22 %), so confirming the ridge from one oblique image is the cheapest way to narrow a P0 estimate.

**Validity.** Simple rectangular or near-rectangular footprints. L-shaped and more complex footprints are treated through the scale factor k, which keeps the total area right but not the individual plane shapes.

**Source.** Plane geometry.

**Worked example.** L = 17.0, W = 11.2, a_L = 90 (long side runs east-west), k = 1. Gable: planes face 180 and 0, A_plan = 95.20 m2 each, S = 6.3662 m at 28.4 degrees, A_plane = 108.23 m2 (also 190.4 / 2 / cos(28.4) = 108.23). Hip: triangles 31.36 m2 each, trapezoids 63.84 m2 each, total 190.40 m2; shapely polygon areas: 31.36, 63.84, 190.40.

**Tool function.** `parametric_roof_planes(footprint_wkt, shape_class, tilt: Ranged) -> list[RoofPlane]` with `geometry_source = "vexcel_parametric"`.

### ROOF-06 Fire-code access pathways and setbacks [V for the model-code text, U or P where marked]

These are design defaults for a feasibility study. The authority having jurisdiction decides what applies to a real permit. Dimensions are converted exactly (1 in = 0.0254 m).

**Houses and other Group R-3 buildings, roof slope steeper than 2 in 12.**

| Requirement | Value | Section |
|---|---|---|
| Pathways from lowest roof edge to ridge | at least two, each 36 in (0.914 m) wide, on separate roof planes; at least one on the street or driveway side | 1205.2.1.1 |
| Pathway for each plane with an array | at least one 36 in (0.914 m) pathway on the same plane, on an adjacent plane, or straddling both | 1205.2.1.1 |
| Setback on both sides of a horizontal ridge | 18 in (0.457 m) where arrays cover 33 % or less of the plan-view total roof area; 36 in (0.914 m) where they cover more | 1205.2.1.2 |
| Same, dwelling with automatic sprinklers (903.3.1.3) | 18 in up to 66 % of plan-view roof area; 36 in above | 1205.2.1.3 |
| Emergency escape and rescue openings | no modules on the roof portion below such an opening; a 36 in (0.914 m) pathway to it | 1205.2.2 |
| Not required | roofs with slope of 2 in 12 or less; detached non-habitable structures such as garages and carports; where the fire code official finds rooftop operations will not be used | 1205.2.1 exception 2, 1205.2 exceptions 1 and 2 |

**Other buildings (commercial).**

| Requirement | Value | Section |
|---|---|---|
| Clear perimeter around the roof edges | 6 ft (1.829 m); 4 ft (1.219 m) where either axis of the building is 250 ft (76.2 m) or less | 1205.3.1 |
| Interior pathways between array sections | at intervals of no more than 150 ft (45.72 m) along length and width; 4 ft (1.219 m) wide straight path to roof standpipes and ventilation hatches; 4 ft around roof access hatches with a path to a parapet or roof edge | 1205.3.2 |
| Smoke ventilation | 4 ft (1.219 m) pathway bordering all sides of non-gravity smoke and heat vents; 4 ft on at least one side of gravity-operated dropout vents; between array sections either an 8 ft (2.438 m) pathway or a 4 ft pathway bordering 4 ft by 8 ft venting cutouts every 20 ft (6.096 m) on alternating sides | 1205.3.3 |
| Roof shaped like a house roof | the fire code official may accept the house rules instead | 1205.3 exception |

**Sources.** IFC21: full text of 2021 International Fire Code section 1205 as reproduced by the Wylie, Texas Fire Marshal's Office, opened and read. CFC25: 2025 California Fire Code section 1205.2 to 1205.3.3 as reproduced by UpCodes. The two agree on every number in the tables. Both print the 36-inch ridge setback of 1205.2.1.2 with a metric equivalent of 457 mm, which is 18 inches; the alternative-setback paragraph prints 36 inches (914 mm), so the inch value is taken as the rule and the 457 is a misprint carried in the published text.

**What applies where, and what is not verified.**

- **California, commercial and other non-R-3 buildings.** 2025 California Fire Code 1205.3. [V-repro, one reproduction plus the matching model code]
- **California, houses.** Section 1205.2.1 exception 1 says the R-3 rules do not apply to structures built under the residential code. The governing text for a house is therefore the 2025 California Residential Code, section R329 "Solar Energy Systems" (R329.6, roof access and pathways). Its text could not be opened; only the section's existence in the 2025 table of contents was seen. The table above is used as the design default on the expectation that the residential code mirrors it. [U], section 8.
- **Texas.** There is no single statewide text for rooftop PV access. Local Government Code section 214.212 adopts the International Residential Code as it existed on 1 May 2012 as the municipal residential code and lets each municipality adopt amendments and later editions (read in a reproduction, not on the official site). Each city therefore has its own adopted edition. The table above (2021 IFC, as published by one Texas city) is the design default for Texas lots. The edition and amendments in force in Houston for the golden office were not verified. [P] Agent lane (`specs/legal/`), per city.

**Golden lots.** House in Los Angeles: pitched gable, slope above 2 in 12, so ridge setback and pathways apply (ROOF-04 example). Offices in Los Angeles and Houston: flat roofs; take the roof dimensions from gross building area over storeys (ROOF-03), check each axis against 76.2 m to choose the perimeter width, and confirm the local adoption (section 8). Interior pathways for spacing are needed only if a roof dimension exceeds 45.72 m; check the long side of the footprint against that.

**Tool function.** `fire_setbacks(state, building_group, roof_slope_deg, array_plan_share, sprinklered=False, building_axes_m=None) -> {ridge_setback_m, pathway_width_m, perimeter_m, interior_interval_m, basis, status}`.

## 6. Panel layout (LAY)

### LAY-01 Packing rectangular modules into the usable area [V]

```
Rectangle Wu by Hu, module a by b placed with side a along Wu, gap g between modules:
  n_cols = floor( (Wu + g) / (a + g) )
  n_rows = floor( (Hu + g) / (b + g) )
  N      = n_cols * n_rows
Evaluate portrait (a = short side, b = long side) and landscape (a = long, b = short); keep the larger N.

General polygon (fitted planes): for each orientation, slide a grid of period (a + g, b + g) over the polygon's
bounding box in 0.05 m steps of the grid origin in both directions, count the module rectangles that lie
entirely inside the polygon, keep the best origin and orientation.
```

**Symbols.** `Wu`, `Hu` usable width along the eave and usable length up the slope, measured in the roof plane (m); `a`, `b` module sides (m); `g` gap (m); `N` module count. Work in plane coordinates (u along the eave, v up the slope); the plan-view outline of a module is its plane rectangle with v multiplied by cos(beta).

**Default.** g = 0.0127 m: GAG16 section 4.4 assumes 1.27 cm between modules for racking clamps and from it a module-to-roof area ratio of 0.98 on tilted roofs. With the PV-08 module this gap gives 1.9527 / (1.7347 * 1.1467) = 0.982, consistent with that figure.

**Validity.** One orientation per plane, axis-aligned to the eave, no mixed layouts. The grid search is a heuristic for polygons, exact for rectangles. Output: one `PanelPlacement.polygon_wkt` per module in map coordinates, where positions are known; on the parametric path with the area method (ROOF-04) only the count and a schematic grid are available.

**Source.** Arithmetic; gap from GAG16.

**Worked example.** Usable rectangle 9.0856 m by 4.5428 m (ROOF-04 polygon example), module 1.722 by 1.134 m, g = 0.0127 m. Portrait: floor(9.0983 / 1.1467) = 7 columns, floor(4.5555 / 1.7347) = 2 rows, N = 14. Landscape: floor(9.0983 / 1.7347) = 5, floor(4.5555 / 1.1467) = 3, N = 15. Keep landscape, 15 modules, 6.45 kW. A brute-force search with shapely containment tests over all grid origins gives 14 and 15. For an L-shaped polygon with vertices (0,0), (9,0), (9,2.5), (5,2.5), (5,4.5), (0,4.5) the search gives 11 portrait and 12 landscape (single computation; no closed form to compare with).

**Tool function.** `pack_modules(usable_polygon_uv, module_w_m, module_h_m, gap_m=0.0127) -> list[rectangle_uv]`.

### LAY-02 Row spacing on flat roofs [V]

```
alpha_p = atan( tan(alpha) / cos(A - gamma) )                 profile angle, for cos(A - gamma) > 0
P_min   = L * ( cos(beta) + sin(beta) / tan(alpha_p) )        smallest row pitch with no beam shading at that sun position
GCR     = L / P
f       = max(0, 1 - P * sin(alpha_p) / ( L * sin(alpha_p + beta) ))      shaded fraction of the next row's slant length
psi     = atan( L sin(beta) / (P - L cos(beta)) )             mask angle seen from the bottom of a row
```

**Symbols.** `alpha` = 90 - theta_z solar elevation; `A` solar azimuth; `gamma` azimuth the rows face; `alpha_p` elevation of the sun projected onto the vertical plane perpendicular to the rows; `L` slant length of a row (m); `beta` tilt of the modules on their racks; `P` row pitch, front edge to front edge (m); `GCR` ground coverage ratio; `f` fraction of an interior row shaded from the bottom up (use as `f_b` in SHD-03 for interior rows; the first row is unshaded); `psi` (deg) feeds SHD-02 through SVF = (1 + cos(beta + psi)) / 2, evaluated at the bottom of the row, which is the worst case.

**Validity.** Long parallel rows on a horizontal roof, all at the same tilt; end effects ignored. Sun in front of the rows.

**Defaults.** beta = 15 degrees, gamma = 180, GCR = 0.70, so P = L / 0.70 (GAG16 Table 1: tilt 15 degrees and a module-to-roof area ratio of 0.70 for flat roofs, chosen there to keep self-shading losses near 2.5 %). Usable flat-roof area is first reduced by ROOF-06, then rows are laid at pitch P.

**Primary source.** SAM15 section 8: eq. 8.15 (shadow length along the pitch direction, `Py = B cos(beta) + B sin(beta) cos(gamma_eff) / tan(alpha)`, the same expression as P_min), eq. 8.4 (R = B / GCR) and eq. 8.6 (mask angle).
**Second source.** PVLIB `shading.projected_solar_zenith_angle` (90 minus its result is alpha_p), `shading.shaded_fraction1d`, `shading.masking_angle`.

**Worked example 1 (a design sun position).** Site latitude 34.05; winter solstice (n = 355, SOL-03 declination -23.420); three hours before solar noon (omega = -45): SOL-05 gives elevation 18.3644, azimuth 136.8688. Rows face 180, L = 1.722 m, beta = 15: alpha_p = 24.4597 degrees; P_min = 1.722 * (0.96593 + 0.25882 / 0.45487) = 2.6431 m; clear gap between rows 0.9798 m; GCR = 0.6515. pvlib projection gives alpha_p = 24.4597 (difference 0). Shaded fraction from the closed form and from `shaded_fraction1d`: 0 at P = 2.6431, 0.037834 at P = 2.5431, 0 at P = 2.7431 (differences below 1e-9).

**Worked example 2 (the default).** GCR = 0.70, beta = 15: no beam shading when alpha_p >= psi = 29.224 degrees (pvlib `masking_angle(15, 0.70, 0)` = 29.224). At this latitude the sun at solar noon on the winter solstice stands at 32.53 degrees, so the rows are clear at midday all year and shade each other early and late in winter. On the synthetic clear-sky year of PV-06 the beam lost to this shading, counted linearly with f, is 0.29 % of annual beam irradiation on the rows (single pvlib computation). The sky view factor at the bottom of a row is 0.8583, so S_d = 0.873 there. GAG16's "approximately 2.5 %" total was not reproduced and is not used as a check.

**Tool function.** `profile_angle(elevation_deg, solar_azimuth_deg, row_azimuth_deg) -> degrees`; `min_row_pitch(slant_length_m, tilt_deg, profile_angle_deg) -> metres`; `row_shaded_fraction(slant_length_m, pitch_m, tilt_deg, profile_angle_deg) -> fraction`; `flat_roof_rows(usable_polygon, module, tilt_deg=15, gcr=0.70, row_azimuth_deg=180) -> list[rectangle]`.

### LAY-03 Which planes to fill, in what order, and when to stop [V rule]

```
1. Candidate planes: every RoofPlane with usable area for at least one module.
   Excluded: tilted planes (tilt >= 9.5) facing between 292.5 and 67.5 degrees through north, and planes steeper than 60 degrees.
2. For each candidate, yield_p = PV-06 annual AC energy per kW DC at the plane's expected tilt and azimuth
   (per panel position where SHD ran, because shading differs between positions).
3. Sort positions by yield, highest first. Place modules one at a time in that order.
4. Stop at the first of:
     a. no usable position left;
     b. installed cost of the next module would exceed the budget;
     c. cumulative annual energy has reached the site's annual electricity use.
5. Positions with shading_loss_fraction > 0.20 are skipped (SHD-05).
```

**Symbols.** `yield_p` in kWh per kW DC per year. Outputs fill `SolarDesign.panels`, `panel_count`, `system_kw_dc` (PV-08) and `annual_kwh` (PV-09).

**Source.** Ordering and stop conditions: `specs/SPEC.md` section 6.3 item 6. Exclusion of north-facing and very steep planes: GAG16 section 3.5 (planes facing northwest through northeast, 292.5 to 67.5 degrees, and tilts above 60 degrees were treated as unsuitable). The PV-09 example shows why: at this latitude a north plane at 28.4 degrees yields 41 % less than the south plane.

**Validity.** Greedy by yield maximises energy for a given module count when modules are independent (module-level electronics). It does not optimise string lengths or the self-consumed share. The exclusion in step 1 is a default and can be switched off in configuration, in which case north planes simply sort last.

**Worked example.** Planes: S, 1650 kWh/kW, room for 10; W, 1380, room for 8; E, 1340, room for 8. Module 0.430 kW, target 9,000 kWh per year, budget not binding. Order S, W, E. After 10 modules on S: 7,095 kWh. Each W module adds 593.4 kWh: 11 modules 7,688; 12, 8,282; 13, 8,875; 14, 9,469, which reaches the target. Result: 14 modules (10 S, 4 W, 0 E), 6.02 kW, 9,468.6 kWh. Computed by script and by hand.

**Tool function.** `design_pv(building_model, weather, tariff, budget_usd, annual_use_kwh, config) -> SolarDesign`.

## 7. Build-time test plan

Reference implementation for unit tests: pvlib 0.16.x, pinned as a development dependency and run locally. The PVWatts web calculator and NSRDB are not used: `developer.nrel.gov` and `nsrdb.nrel.gov` do not resolve from the team's environment. PVGIS is a secondary, annual-only sanity band. Every worked example in this file is also a test case; the "value" columns below are the numbers printed in the entries.

| Module | Test | Reference | Tolerance |
|---|---|---|---|
| SOL | SOL-01 at the SPA Table A5.1 case | published zenith 50.11162, azimuth 194.34024 | 0.0001 deg |
| SOL | SOL-01 over one year, hourly, both golden lots | `pvlib.solarposition.get_solarposition` (if the wrapper calls pvlib this only guards the wiring: time zone, sign of longitude, midpoint rule) | 1e-6 deg |
| SOL | SOL-02 to SOL-05 single values | values in the entries; pvlib `equation_of_time_spencer71`, `declination_spencer71`, `hour_angle`, `solar_zenith_analytical`, `solar_azimuth_analytical` | 1e-3 min, 1e-4 deg |
| SOL | SOL-05 against SOL-01 over one year, zenith below 85 | SOL-01 | 1.0 deg (measured maximum 0.57 zenith, 0.78 azimuth) |
| SOL | SOL-06 | n . s equals cos of `pvlib.irradiance.aoi` for 1000 random plane and sun directions | 1e-9 |
| SOL | SOL-07 | a row labelled 15:00 (hour ending) is evaluated at 14:30 local standard time; sunrise hour uses the sun-up half | exact |
| IRR | IRR-01 to IRR-10 at the running example | values in the entries and the pvlib function named in each entry | 1e-6 relative |
| IRR | IRR-04 at the SPA case | published incidence 25.18700 | 0.0001 deg |
| IRR | IRR-08 coefficient table | `pvlib.irradiance._get_perez_coefficients("allsitescomposite1990")`, all 48 values | exact |
| IRR | IRR-08 over one year of real weather for each golden lot, tilt 20 and 40, azimuth 90, 180, 270 | `pvlib.irradiance.perez(..., return_components=True)` | 1e-6 W/m2 per hour |
| IRR | Closure of the weather file | GHI against DNI cos(theta_z) + DHI | report only |
| PV | PV-01 to PV-05 at the running example, plus the clipping and low-load cases | values in the entries; pvlib `iam.physical`, `temperature.sapm_cell`, `pvsystem.pvwatts_dc`, `pvsystem.pvwatts_losses`, `inverter.pvwatts` | 1e-6 relative |
| PV | PV-06 full year | `pvlib.modelchain.ModelChain` with the settings listed in PV-06 | 1e-4 relative on annual AC energy, 0.01 W per hour |
| PV | PV-06 annual sanity band, secondary | PVGIS (PVGIS-ERA5) annual yield for the same site, tilt, azimuth, size and loss setting; reported live for the golden house: 7,017 kWh per year for 4 kW at 20 degrees facing south. PVGIS's loss setting for that call must be matched before comparing. | +/-10 % (an assumed band for a 30 km reanalysis product; to be tuned by the Data lane) [P] |
| PV | PV-07 | closed-form sum against year-by-year sum | 1e-9 relative |
| PV | PV-09 | low <= expected <= high; twelve yields of the golden-house table | 1e-4 relative against ModelChain |
| SHD | SHD-01 | analytic wall case: thresholds 21.8014 and 19.1066 deg, blocked 0.05 deg below, clear 0.05 deg above | exact |
| SHD | SHD-02 | closed forms (1 + cos(beta)) / 2, (1 + cos(psi)) / 2, (1 + cos(beta + psi)) / 2; `pvlib.shading.sky_diffuse_passias`; `pvlib.bifacial.utils.vf_row_sky_2d` | 0.002 at the default 30 by 120 grid |
| SHD | SHD-03, SHD-05 | values in the entries; with f_b = 0 and S_d = 1 the shaded result equals IRR-10 | 1e-9 |
| ROOF | ROOF-01 | 6:12 plane gives 26.565 and 180; round trip for 1000 random normals | 1e-9 deg |
| ROOF | ROOF-02 | `scipy.spatial.transform.Rotation`; the 25 degree example; on live data, rotated floor outline against the Vexcel footprint | 1e-12; live check reported as Delta |
| ROOF | ROOF-03 | table lookup returns the printed triples; low <= expected <= high | exact |
| ROOF | ROOF-04, ROOF-05 | golden-house example (43, then 40 modules; 36 at the 33 % cap); hip areas against shapely polygons; polygon examples against shapely | exact counts; 1e-6 m2 |
| ROOF | ROOF-06 | printed metric values equal inches times 0.0254 | 1e-4 m |
| LAY | LAY-01 | 14 portrait and 15 landscape; brute-force containment search on random rectangles | exact |
| LAY | LAY-02 | `pvlib.shading.projected_solar_zenith_angle`, `shaded_fraction1d`, `masking_angle` | 1e-6 |
| LAY | LAY-03 | the 14-module example; stop conditions each triggered once | exact |

## 8. Unverified, do not implement without checking

| Item | Where used | Why unverified | What to do |
|---|---|---|---|
| 2025 California Residential Code R329.6 (roof access and pathways for houses) | ROOF-06 | Text not opened. Only the existence of section R329 in the 2025 table of contents was seen. The house values in ROOF-06 are those of fire code section 1205.2.1, assumed to be mirrored. | Agent lane reads R329.6 in the official code and confirms or corrects the house table. |
| Effective date and local amendments of the 2025 California codes; Los Angeles amendments | ROOF-06 | Not checked. | Agent lane. |
| Texas: edition and amendments adopted by Houston (and any other Texas city used) | ROOF-06 | Not checked. Texas Local Government Code 214.212 was read only in a third-party reproduction through an automated reader. | Agent lane, per city. |
| 2021 IBC section 1507 minimum roof slopes by covering | ROOF-03 | One reproduction (UpCodes), read once through an automated page reader. Minimum slopes for membrane roofs (1507.10 to 1507.13) were not readable at all. | Confirm before using the covering floor; until then the floor is optional. |
| Pitch statistics by roof shape (gable against hip) and for commercial pitched roofs | ROOF-03 | No published source found. Gable and hip share one range; the commercial row is judgment. | Confirm pitch from oblique images or the user for any quote. |
| Ridge runs along the long side of the footprint | ROOF-05, PV-09 | Assumption without a source. | Treated as unconfirmed; PV-09 widens the range. |
| Obstruction allowances (vent, skylight, chimney, AC unit) | ROOF-04 | Engineering judgment, no source. | Kept in the assumption registry with ranges. |
| Tree and neighbour heights | SHD-04 | No data and no sourced default. | User or a height source; otherwise no ray casting against trees. |
| Module rating and size (430 W, 1.722 m by 1.134 m) | PV-08, LAY-01 | Typical values, not from a cited data sheet. | Replace with the quoted product. |
| Solar constant 1366.1 W/m2 as the ASTM E490 value | IRR-01 | The standard was not opened; the number is pvlib's default. | None needed for accuracy (0.07 % against 1367). |
| Circumsolar diffuse shaded with the beam | SHD-03 | A design choice argued from the Perez model's geometry; no source opened that prescribes it. | Accept as stated, or switch to the SAM rule printed in the entry. |
| +/-10 % PVGIS sanity band; PVGIS figures themselves | section 7, PV-09 | Band is assumed. PVGIS values are quoted from the Data lane's live call, not opened here. | Data lane. |
| Open-Meteo time-stamp convention | SOL-07 | Not checked. | Data lane, before any yield is quoted. |
| Faiman (2008) cell temperature model; Fuentes (1987) model used by PVWatts itself; Kasten and Young (1989) air mass; Michalsky (1988) sun position | not used | Primary sources not opened. They are not part of this spec. | Do not add without opening them. |
| Electrical loss from partial shading on string inverters | PV-06 | Not modelled, no formula adopted. | Flag only. |
| Primary papers not opened (Spencer 1971, Erbs et al. 1982, Perez et al. 1990, Hay and Davies 1980, Liu and Jordan 1963, De Soto et al. 2006, Kasten 1965, Passias and Kallback 1984, Appelbaum and Bany 1979) | entries tagged [V-repro], and second-source lines | Paywalled or not found. Each formula was instead read in two open reproductions that agree (named in the entry) and checked numerically against pvlib. | Acceptable to implement; open the paper if a discrepancy ever appears. |

## 9. Verification log

Date checked for every row: 2026-11-14. "Own code" means a re-implementation written from the equations in this file with `math` and NumPy only. "pvlib" is pvlib 0.16.1 with NumPy 2.5.4, pandas 3.1.1, SciPy and shapely 2.2.0 in a scratch virtual environment outside the repository.

| Entry | Primary source | Second source | Result | How the example was recomputed |
|---|---|---|---|---|
| SOL-01 | SPA report, opened | pvlib `spa_python` | pass | pvlib against published Table A5.1 (2e-6 deg); refraction eq. 42 by own code against pvlib (2e-15) |
| SOL-02 | Spencer 1971, not opened | NOAA, pvlib | pass; constant term differs between NOAA and pvlib, documented | own code against pvlib (2e-5 min) |
| SOL-03 | Spencer 1971, not opened | NOAA, pvlib | pass | own code against pvlib (0) |
| SOL-04 | NOAA, opened | pvlib `hour_angle` | pass | own code against pvlib (5e-15 deg) |
| SOL-05 | NOAA, opened | pvlib analytical functions; SOL-01 | pass; simple algorithm is up to 0.57 deg (zenith) and 0.78 deg (azimuth) from SPA in 2026 | own code against pvlib (2e-12); full-year comparison with SPA |
| SOL-06 | definition | pvlib `aoi` | pass | dot product against pvlib incidence (1e-12) |
| SOL-07 | PVW5 section 5, opened | SAM15 sections 3.1, 4.1, opened | rule; weather convention pending | not numeric |
| IRR-01 | Spencer 1971, not opened | pvlib, PVPMC | pass | own code against pvlib (0); UTC-day convention found and documented |
| IRR-02 | Erbs 1982, not opened | pvlib, TrenchR | pass | own code against pvlib (0) |
| IRR-03 | SAM15 eq. 6.16, opened | pvlib `kasten1966` | pass; SAM rounds one constant | own code against pvlib (0) |
| IRR-04 | PVW5 eq. 1, opened | SPA eq. 47, pvlib | pass | own code against published 25.18700 (2e-7) and against pvlib (0) |
| IRR-05 | PVW5 section 7, opened | pvlib | pass | own code against pvlib (0) |
| IRR-06 | SAM15 eq. 6.4, opened | pvlib | pass | own code against pvlib (0) |
| IRR-07 | Hay and Davies 1980, not opened | PVPMC, pvlib | pass | own code against pvlib (3e-14) |
| IRR-08 | Perez 1990, not opened | PVPMC, pvlib, SAM15 Table 6 | pass; four differences between reproductions documented | own code against pvlib, each component (1e-13); table in this file parsed and compared with pvlib's array (identical) and SAM15's (within 0.0007) |
| IRR-09 | SAM15 eq. 6.20, opened | PVPMC, pvlib | pass | own code against pvlib (0) |
| IRR-10 | PVW5 eq. 2, opened | pvlib | pass | own code against pvlib (0) |
| PV-01 | PVW5 section 8, opened | SAM15 eq. 9.13 to 9.15, pvlib | pass | own code against pvlib at three angles, with and without absorption (0) |
| PV-02 | KING04 eq. 11, 12, Table 1, opened | PVPMC, pvlib | pass | own code against pvlib for four coefficient rows (0) |
| PV-03 | PVW5 eq. 8, Table 3, opened | pvlib | pass | own code against pvlib (0); hand calculation |
| PV-04 | PVW5 eq. 9, Table 6, opened | pvlib, GAG16 Table 1 | pass | own code against pvlib (0) and against the published 14 % and 14.08 % |
| PV-05 | PVW5 eq. 10, 11, opened | pvlib | pass | own code against pvlib at normal, clipped and low load (0); hand calculation |
| PV-06 | PVW5 section 13, opened | pvlib ModelChain | pass | own NumPy chain against ModelChain over 8760 hours: annual AC equal to 1e-9 kWh, hourly to 1e-4 W |
| PV-07 | JK12, opened | PVW5 section 11 | pass | summation against closed form (3e-10 kWh) |
| PV-08 | arithmetic | none | defaults unverified | hand |
| PV-09 | method of this file | pvlib ModelChain | pass | twelve yields, own chain against ModelChain (below 1e-6 kWh/kW); weather step by hand and by script |
| SHD-01 | geometry; SAM15 eq. 7.4 and 8.15, opened | own ray-triangle routine | pass | ray casting against analytic thresholds at two azimuths |
| SHD-02 | SAM15 section 8.3, opened | pvlib `sky_diffuse_passias`, `vf_row_sky_2d` | pass; SAM's simpler expression understates the loss on tilted rows, documented | hemisphere quadrature with ray casting against three closed forms (below 1e-4) and against pvlib |
| SHD-03 | SAM15 eq. 7.4, opened, with one stated change | none for the change | arithmetic pass; rule is a design choice | script and hand from pvlib-checked components |
| SHD-04 | none | none | unverified inputs | not numeric |
| SHD-05 | definition; GAG16 section 3.5 for the screen | SAM15 section 7.4 | pass | hand |
| ROOF-01 | definition | pvlib `aoi_projection` | pass | cross product by hand and script; 1000 round trips (2e-13 deg) |
| ROOF-02 | standard rotation formula | SciPy `Rotation` | mathematics pass; quaternion direction and axis convention pending with the Data lane | own matrix against SciPy (1e-16), yaw example and a random quaternion |
| ROOF-03 | GAG16 Tables A-1 to A-3, section 3.3, opened | IBC 2021 section 1507 through one reproduction | sourced values pass; gable against hip and the commercial row unverified | class edges, midpoints and shares recomputed by script from the table values |
| ROOF-04 | geometry; method from SPEC 6.3 | shapely | geometry pass; allowances unverified | script and hand (area method); shapely against closed form (polygon method) |
| ROOF-05 | geometry | shapely | pass; ridge assumption unverified | closed form against shapely polygon areas (below 1e-9 m2) |
| ROOF-06 | IFC 2021 section 1205 (Wylie, Texas reproduction), opened | 2025 California Fire Code section 1205 (UpCodes) | fire-code values pass, two reproductions agree; residential-code text and Texas local adoption unverified | unit conversions by script |
| LAY-01 | arithmetic; gap from GAG16 | shapely brute force | pass | closed form against brute-force containment search (14 and 15) |
| LAY-02 | SAM15 eq. 8.4, 8.6, 8.15, opened | pvlib `projected_solar_zenith_angle`, `shaded_fraction1d`, `masking_angle` | pass | own code against pvlib (below 1e-9) |
| LAY-03 | SPEC 6.3; GAG16 section 3.5 | none | rule; arithmetic pass | script and hand |

Scripts and their results (kept outside the repository, in the scratch directory of the session that wrote this file):

- `verify.py`: 77 numbered checks, 77 pass, 0 fail.
- `roofrange.py`: 15 checks (twelve yields, three hip areas), 15 pass.
- `sens.py`: azimuth and tilt sensitivity quoted in ROOF-02, pvlib only.
- Three short ad hoc checks: Perez table in this file against pvlib and SAM15; sky-view-factor error against grid size; `vf_row_sky_2d` against the closed form.

Web sources read through an automated page reader (PVPMC pages, UpCodes pages, the Texas statute reproduction) can be misread by that reader. Every number taken from them was compared with a second source where this log says so; where it was not possible the item is in section 8.

## 10. Requests to the shared contract and to SPEC.md

Not edited here; raised with the spec owner.

1. `BuildingModel.north_offset_deg`: fix the sign in the comment. This file defines it as the azimuth of the model +y axis, clockwise from true north, so that `azimuth_true = azimuth_model + north_offset_deg` (ROOF-02).
2. `RoofPlane`: add `ridge_confirmed: bool = False` (or a `Source` for the ridge direction) and, for the parametric path, `eave_length_m` and `slope_length_m`, which ROOF-04 needs. `obstructions: list[VexcelDetection]` cannot hold counts without positions; add `obstruction_counts: dict[str, int] = {}`.
3. `SolarDesign`: add `dc_ac_ratio`, `inverter_kw_ac`, `module_w`, `losses_percent` and `degradation_rate`, so a result can be reproduced from its own fields. `PanelPlacement.polygon_wkt` should be optional, because the area method yields a count, not positions.
4. `ClimateSite`: add the time-stamp convention of the weather file (SOL-07) and, if PVGIS is called, `pvgis_annual_kwh_per_kw` and `pvgis_sd_fraction` for PV-09 step 6.
5. `SPEC.md` section 6.3 item 4 says shading is computed by ray casting; on the parametric P0 path there is no exterior mesh, so shading there is the 3 % default of PV-04. Section 13 already lists ray-cast shading as P1; item 4 should say so.
6. `SPEC.md` refers to `physics.md`; the solar part is this file, `specs/physics/01-solar-pv.md`.

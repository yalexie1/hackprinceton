# Weather sample (fixture alias `weather`, workplan 2.3)

Two real hourly years, calendar year **2024**. These are not typical meteorological years. No sponsor data. Tests read these files and never fetch.

* **Temperature, relative humidity and wind** come from **NOAA station observations**: Global Hourly (ISD), with GHCN-Daily for one gap (see below). Each file uses the station that the Data lane's TMYx rule picks for live runs (data spec 5.1f), so the examples and live runs share a climate (#322).
* **Irradiance (GHI, DNI, DHI)** comes from the **Open-Meteo archive API**. It is byte-identical to the earlier Open-Meteo-only files.

Rebuild both files with one command from the repository root. It downloads into a temporary folder, or into `--cache DIR`:

    python specs/examples/weather/build_weather_sample.py --check

`--check` stops if the refetched Open-Meteo irradiance differs from the committed file. `fetch_weather_sample.py` holds the Open-Meteo request that the build calls. Run on its own, it writes the earlier Open-Meteo-only files.

| File | Site | Temperature, RH and wind | Irradiance: Open-Meteo grid point | Time zone, offset |
|---|---|---|---|---|
| `typical_year_hourly.csv` | golden house, Los Angeles (34.0934917, -118.3171); also the fallback for every CA example | **Los Angeles Downtown USC**, WMO 722874, ISD `722874-93134` (KCQT), GHCN `USW00093134`, 34.0236, -118.2911, 55 m, 8.1 km from the house; from 2024-05-20 on, **Hawthorne Municipal** `722956-03167` (KHHR) rescaled to USC's daily extremes | 34.059753, -118.350006, elevation 104 m | America/Los_Angeles, UTC-8 |
| `typical_year_hourly_houston.csv` | golden Houston office (29.7452, -95.4567) | **Houston William P. Hobby Airport**, WMO 722440, ISD `722440-12918` (KHOU), GHCN `USW00012918`, 29.6459, -95.2821, 13 m | 29.771528, -95.43555, elevation 26 m | America/Chicago, UTC-6 |

The Culver Connect office also falls back to the Los Angeles file. Its live station is Santa Monica (5.1f), whose TMYx year averages 62.9 °F against USC's 65.6 °F (5.1f), so for that example the file is warmer than its live run.

## Licences and attribution

* NOAA NCEI Global Hourly (Integrated Surface Database) and GHCN-Daily are works of the U.S. Government and in the **public domain**. The ISD files are read from NCEI's `global-hourly/access/<year>/<station>.csv`, through its open-data mirror `noaa-global-hourly-pds.s3.amazonaws.com`. GHCN-Daily is read through the NCEI Access Data Service, `dataset=daily-summaries`.
* Irradiance: **"Weather data by Open-Meteo.com"**, licensed under **CC BY 4.0** (https://open-meteo.com/, archive API, ERA5-based reanalysis). Attribution is required.

## Format

One row per hour, 8,784 rows. 2024 is a leap year, and the A1 reader drops 29 February so it returns 8,760 hours.

| Column | Unit | Source |
|---|---|---|
| `time_local` | ISO 8601 without offset, **local standard time** all year (no daylight saving) | the Open-Meteo stamps, unchanged |
| `temp_c` | degC, 0.1 | ISD `TMP` |
| `rh_pct` | %, integer | from ISD `TMP` and `DEW` by the Magnus formula |
| `ghi_w_m2` | W/m2 | Open-Meteo `shortwave_radiation` |
| `dni_w_m2` | W/m2 | Open-Meteo `direct_normal_irradiance` |
| `dhi_w_m2` | W/m2 | Open-Meteo `diffuse_radiation` |
| `wind_m_s` | m/s at 10 m, 0.1 | ISD `WND` speed (ASOS two-minute mean) |

Time convention: `hour_end`. Irradiance is the mean over the hour that ends at the stamp (data spec 5.1a). Temperature, RH and wind are the observation at the stamp, as in an EPW. The reader (`backend/analysis/physics/climate/weather.py`) also accepts an optional `albedo` column, explicit UTC offsets in `time_local`, and a file without `dni_w_m2` and `dhi_w_m2`. In the last case it splits GHI by Erbs (IRR-02) and warns.

## How the station hours are made

1. **Reports.** Only FM-15 (routine METAR) and FM-16 (special) reports are used. ISD `TMP`/`DEW` are `+0123,q`, tenths of degC plus a quality code. `WND` is `dir,q,type,speed,q`, with speed in tenths of m/s. These are dropped: `+9999` and `9999` (missing), and quality codes 2, 3, 6 and 7 (suspect or erroneous). Type `C` (calm) is 0 m/s.
2. **One value per hour.** Each local-standard stamp H corresponds to UTC H + 8 h (Los Angeles) or H + 6 h (Houston). For each variable separately, the build takes the valid report nearest H within 30 minutes, preferring FM-15 over FM-16. USC reports at :47 and Hobby at :53, so the 12:47 or 12:53 report stamps 13:00. The last local hours of 31 December use the first hours of the 2025 file.
3. **Relative humidity** uses Magnus with the Alduchov and Eskridge (1996) constants: RH = 100 · exp(a·Td/(b+Td)) / exp(a·T/(b+T)), with a = 17.625 and b = 243.04 degC, capped at 100 %.
4. **Gaps.** Runs of 1 to 3 missing hours are filled by linear interpolation. Longer runs take Open-Meteo's value for that hour; for dew point, that value comes from Open-Meteo's T and RH through the same Magnus constants.

### The Los Angeles gap: USC stops reporting on 2024-05-20

NOAA has **no hourly observations from Downtown USC after 2024-05-20 14:47 UTC**: ISD, GHCNh and the METAR archive (Iowa Environmental Mesonet) all end there. GHCN-Daily still has USC's TMAX and TMIN for all 366 days. Decision (lead, #322): take USC's own hours through local 2024-05-19 23:00. **From local 2024-05-20 00:00 to the end of the year**, take a donor station's hourly series and **rescale its temperature day by day** (stamp date, local standard time). The rescale is linear, so the day's minimum and maximum equal USC's GHCN-Daily TMIN and TMAX: T = TMIN + (T_donor − min_day) · (TMAX − TMIN) / (max_day − min_day). The donor's own dew point and wind are kept, with Td capped at the rescaled T. RH is then computed from the rescaled T. Of the 8,784 hours, 3,360 come from USC and 5,424 from the donor.

The donor was chosen by validation. On 1 January to 19 May, where USC has its own hours, each candidate was rescaled to USC's daily extremes the same way and compared with USC's actual hourly reports (3,333 hours for temperature, 3,329 for dew point):

| Candidate (ISD id) | T RMSE rescaled, degC (bias) | T RMSE raw, degC (bias) | Td RMSE, degC (bias) |
|---|---|---|---|
| **Hawthorne 722956-03167** (chosen) | **0.86** (+0.12) | 0.97 (−0.30) | **1.21** (+0.14) |
| Fullerton 722976-03166 | 0.98 (+0.09) | 1.28 (−0.41) | 1.96 (+0.58) |
| Burbank 722880-23152 | 1.07 (+0.08) | 2.08 (−1.47) | 2.80 (−1.92) |
| Santa Monica 722885-93197 | 1.07 (+0.29) | 1.57 (−1.15) | 2.99 (+1.34) |
| Long Beach 722970-23129 | 1.10 (+0.19) | 1.18 (+0.42) | 1.79 (+0.61) |
| LAX 722950-23174 | 1.12 (+0.20) | 1.73 (−1.19) | 1.67 (+0.76) |
| Van Nuys 722886-23130 | 1.20 (+0.08) | 2.13 (−0.94) | 3.05 (−1.98) |
| El Monte 747043-03165 | 1.26 (+0.04) | 2.71 (−1.69) | 1.96 (−0.54) |

The small positive bias of the rescaled series is expected. GHCN-Daily extremes come from continuous sensing, so they lie slightly outside the hourly reports.

### Gap counts (hours of 2024)

| Part | Variable | Observed | Interpolated (runs of 1-3 h) | Open-Meteo (longer runs) | Longest gap |
|---|---|---|---|---|---|
| LA, USC, to 2024-05-19 (3,360 h) | temperature | 3,333 | 8 | 19 (2 runs) | 10 h |
| | dew point | 3,329 | 12 | 19 | 10 h |
| | wind | 3,171 | 163 | 26 | 9 h |
| LA, Hawthorne, from 2024-05-20 (5,424 h) | temperature | 5,416 | 8 | 0 | 1 h |
| | dew point | 5,380 | 14 | 30 (2 runs) | 21 h |
| | wind | 5,395 | 29 | 0 | 3 h |
| Houston, Hobby (8,784 h) | temperature, dew point, wind | 8,781 each | 3 each | 0 | 1 h |

USC reports little wind: many of its reports carry no valid speed, hence the 163 interpolated wind hours.

## Before and after (#322)

Degree-days use NOAA's daily method: daily mean = (Tmax + Tmin)/2 of the day's hours by stamp date, base 65 °F, with 29 February dropped. The observed figures use the same method on GHCN-Daily TMAX/TMIN. "Mean" is the mean of the daily (Tmax + Tmin)/2; the hourly-mean figure is given in brackets.

| Site | File | Mean T °F | HDD °F·d | CDD °F·d |
|---|---|---|---|---|
| Los Angeles (USC) | old, Open-Meteo 2024 | 63.8 (62.3) | 1,562 | 1,135 |
| | **new, NOAA** | **65.4** (63.9) | **1,068** (+2.2 %) | **1,197** (−0.3 %) |
| | observed 2024, GHCN-Daily `USW00093134` | 65.4 | 1,045 | 1,201 |
| Houston (Hobby) | old, Open-Meteo 2024 | 71.9 (71.4) | 917 | 3,431 |
| | **new, NOAA** | **74.1** (73.6) | **707** (−1.0 %) | **4,045** (−1.0 %) |
| | observed 2024, GHCN-Daily `USW00012918` | 74.2 | 714 | 4,086 |

The remaining differences come from the hourly reports missing the true daily extremes, and from the hours that fall back to Open-Meteo.

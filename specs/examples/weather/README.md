# Weather sample (fixture alias `weather`, workplan 2.3)

Real hourly weather from the **Open-Meteo archive API** (public, keyless, CC BY 4.0), calendar year **2024**: one real year, not a typical meteorological year. No sponsor data. Written once by `fetch_weather_sample.py`, which makes the same request as the Data lane's D9 (`backend/data_layer/external.py`) and writes the same columns (data spec 5.1a). Tests read these files; they never fetch.

| File | Site | Open-Meteo grid point | Time zone, offset |
|---|---|---|---|
| `typical_year_hourly.csv` | golden house, Los Angeles (34.0934917, -118.3171) | 34.059753, -118.350006, elevation 104 m | America/Los_Angeles, UTC-8 |
| `typical_year_hourly_houston.csv` | golden Houston office (29.7452, -95.4567) | 29.771528, -95.43555, elevation 26 m | America/Chicago, UTC-6 |

Format, one row per hour, 8,784 rows (2024 is a leap year; the A1 reader drops 29 February and returns 8,760 hours):

| Column | Unit | Open-Meteo field |
|---|---|---|
| `time_local` | ISO 8601 without offset, **local standard time** (Open-Meteo returns one fixed offset, the zone's standard one, all year; checked by the script) | `hourly.time` |
| `temp_c` | degC | `temperature_2m` |
| `rh_pct` | % | `relative_humidity_2m` |
| `ghi_w_m2` | W/m2 | `shortwave_radiation` |
| `dni_w_m2` | W/m2 | `direct_normal_irradiance` |
| `dhi_w_m2` | W/m2 | `diffuse_radiation` |
| `wind_m_s` | m/s at 10 m (km/h x 1000/3600) | `wind_speed_10m` |

Time convention `hour_end`: a stamp is the mean over the hour ending at it (data spec 5.1a). The reader (`backend/analysis/physics/climate/weather.py`) also accepts an optional `albedo` column, explicit UTC offsets in `time_local`, and a file without `dni_w_m2` and `dhi_w_m2` (then GHI is split by Erbs, IRR-02, with a warning).

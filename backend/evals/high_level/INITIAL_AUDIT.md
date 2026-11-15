# Independent audit of the initial evaluation

Tracking: #405, stage 0 of #400. Source inspected: initial #403 commit `081a433fc63301fbb73b732ad01155042b34b85c`. This report does not replace or edit Vignesha's initial evaluation.

## Status

The owner explicitly delivered the initial results, manifest, scope and reproduction commands. OpenSolar is procedure-only/not run and PVWatts unavailable, as disclosed. That delivery opened independent review in the approved `backend/evals/high_level/` scope. **Vignesha subsequently confirmed both concrete bugs and withdrew the initial headline numbers pending a corrected rerun. New scored/model experiments wait for that revised final delivery.** Frontend integration remains the priority before larger experiments.

**Actual 494-building headline metrics have not been independently reproduced.** Corrected per-building outputs and immutable generated weather inputs have been requested from the owner. All four raw BDG2 files are independently downloaded and SHA256/size verified against the delivered manifest; see out/public_input_receipt.json. Raw bytes stay outside Git. Refetching an unversioned weather API would be a new input version, not exact reproduction. The following verified findings are source/arithmetic/input-unit checks, not accuracy results on a new building cohort.

## Verified findings

### 1. The factor-of-two headline excludes large underpredictions

`score_eval.describe()` counts `abs(percent_error) >= 100` as `factor_2_plus`. With nonnegative predictions and positive truth, this captures predictions at least twice the truth, but excludes predictions at most half the truth. A prediction of 20 kWh against 100 kWh is fivefold too low and has -80% percentage error; the delivered metric does not count it.

Executed independent counterexample: prediction/truth ratios `[0.2, 0.5, 1, 2]`. A symmetric factor-of-two-or-more metric counts 3/4 = 75%; the delivered scorer reports 1/4 = 25%. The generated artifact `out/initial_source_081.json` pins the exact scorer hash and labels these as synthetic arithmetic inputs. They are never presented as real building measurements.

Requested owner correction: use `ratio <= 0.5 or ratio >= 2` on eligible positive truth, or rename the existing metric to absolute percentage error at least 100% and remove factor-of-two descriptions. The actual corrected percentage cannot be calculated from the committed aggregate alone.

### 2. Weather wind speeds are stored with the wrong unit

`prep_weather.fetch_openmeteo()` requests `windspeed_10m` without a wind-unit parameter, then stores its numeric values as `wind_m_s` with no conversion. A direct one-day probe of that API returned `hourly_units.windspeed_10m = "km/h"`. The [official historical-weather documentation](https://open-meteo.com/en/docs/historical-weather-api) also documents km/h as the default. The production weather reader defines `wind_m_s` in m/s. Therefore the numeric wind speeds are 3.6 times the intended m/s values.

The production baseline passes this column to `zone_loads`; residential INF-03 uses wind-driven infiltration, so the mismatch can affect the residential-default path. **The effect on the 494-building headline metrics is not quantified here.** The owner should set `wind_speed_unit=ms` or convert explicitly, verify returned units, hash/version the corrected weather and recompute affected results. A label-only patch would not correct cached inputs or outputs.

### 3. Several conclusions exceed the study design

- A median signed percentage error near zero does not establish zero aggregate bias or accurate individual predictions. As an independently tested arithmetic example, truths `[10,100,1000]` and predictions `[5,100,1500]` have median signed percentage error zero but aggregate signed error about +44.6%. This example is illustrative mathematics, not building evidence.
- A scaled example box can mismatch actual building geometry, HVAC, occupancy and meter boundaries. It does not remove geometry error or establish a lower bound on error for a scanned property. Real geometry might improve or worsen a particular prediction; the study does not measure that comparison.
- The observed error difference between tall and single-storey groups is an association. Without a controlled same-building geometry comparison, it cannot be attributed causally to storey simplification.
- Low empirical coverage establishes miscalibration of the formerly advertised interval. A near-symmetric pooled split does not independently identify the cause; subgroup bias and model/input mismatch may coexist.

These findings and the two concrete code/input issues were posted to the owner on Message Board #1 before merge. Corrections belong to the initial evaluation owner; model changes remain in Yale's lane. The independent package does not patch their code.

## Reproduce this audit

In a separate source checkout pinned to the delivered commit, retain all files untouched. From the high-level validation checkout:

```bash
python -m backend.evals.high_level.audit_initial \
  --source-root /path/to/pinned-delivery \
  --output /tmp/initial-source-audit.json
python -m pytest backend/evals/high_level/tests -q
```

If the owner provides the exact `runs.json`, add `--runs /private/path/to/runs.json`. The output will independently score both the common successful cohort and all available predictions per arm, retaining missing-prediction counts and the input hash. Its status explicitly distinguishes rescoring owner outputs from rerunning the model. Do not commit per-building inputs or experiment caches.

Fourteen targeted tests passed: nine arithmetic tests and five acquisition safeguards. The acquire_bdg2 module downloads the four public inputs into a caller-selected cache, verifies the delivered byte counts and hashes, and rejects LFS pointers, truncated/changed files and oversized responses. It never trusts or overwrites mismatched existing inputs. No production source, model parameter, cached sponsor data or displayed financial result was changed by this audit.

## Next checkpoint

1. Receive the owner's response and pin the corrected initial revision, preserving this historical audit.
2. Acquire permitted exact per-building outputs and weather hashes, or label a separately hashed public-data rerun as a new input version. Reconcile truth, cohort selection and all reported metric denominators before quoting independently reproduced accuracy.
3. Freeze eligibility, mappings, development/test splits and intended-use acceptance criteria before scoring new cohorts. RECS anonymization and aggregate geography may permit only cohort comparisons; do not invent precise geometry or weather to create a property-level test.
4. Resume the six-track plan after the required frontend integrations, without tuning on the already-inspected initial evaluation set.

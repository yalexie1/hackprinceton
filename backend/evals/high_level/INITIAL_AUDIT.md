# Independent audit of the initial evaluation

Tracking: #405, stage 0 of #400. Source inspected: initial #403 commit `081a433fc63301fbb73b732ad01155042b34b85c`. This report does not replace or edit Vignesha's initial evaluation.

## Status

The owner delivered corrected initial results in #403 at `d65ad172dcd87424a80378316c1e6349cf280555`, now merged to main. Both concrete issues below were confirmed and fixed by the owner. The gate is open for independent review in the approved `backend/evals/high_level/` scope. OpenSolar remains procedure-only/not run. The owner's PVWatts attempt was unavailable; Yale subsequently reported cases using a different host, which have not been independently reproduced here. Frontend integration remains the priority before larger experiments.

**The corrected 494-building outputs have been independently rescored, and raw-meter truth/cohort membership reconciled. The model itself has not yet been rerun independently.** Exact generated weather inputs and end-use/model-area diagnostics are pending the owner's promised handoff. All four raw BDG2 files were independently downloaded and SHA256/size verified against the delivered manifest; see out/public_input_receipt.json. Raw bytes stay outside Git. Refetching an unversioned weather API would be a new input version, not exact reproduction.

## Corrected output and truth reconciliation

`out/corrected_rescore.json` pins the per-building artifact hash and independent scorer results. Both arms score all 494 buildings with no missing prediction. Corrected factor-of-two arithmetic passes the independent 75% boundary counterexample.

| Independent metric | BDG2 temperature | Open-Meteo temperature |
| --- | ---: | ---: |
| Median absolute percentage error | 55.90% | 55.64% |
| Median signed percentage error | -0.47% | -1.80% |
| Aggregate signed energy error | -11.69% | -12.55% |
| Weighted absolute percentage error | 56.61% | 56.49% |
| Two-sided factor-of-two misses | 43.52% | 43.72% |
| Fraction within displayed bounds | 17.00% | 16.19% |

These confirm the owner's rounded headline numbers while exposing aggregate underprediction that the median signed percentage hides. They are diagnostics on an already-inspected cohort, not fresh held-out results or retrofit-savings accuracy.

`out/truth_check.json` independently reconciles all 494 annual electricity truths against the hashed raw meter CSV: 530 metadata-eligible buildings become 494 after completeness/positive-total checks; the owner output contains exactly that set. The calendar contains all 8,760 unique 2017 hourly timestamps, with no duplicates. Maximum absolute total difference is below 0.000001 kWh (floating-point summation order). This makes a wrong truth total/cohort an unlikely explanation for the observed errors; it does not validate meter boundaries or the building model.

## New actionable input defects

1. **Unsupported climate zones silently fall back to CA/3B.** `registry.climate_zone()` accepts only `T.CLIMATES = ('2A', '3B')`. Four site labels (3C, 6A, 2B, 4A; 398/494 buildings) are not supported and fall back to the forced CA state. Only Panther/2A remains as requested. Site weather is still supplied, but the claim that forced CA cannot affect energy defaults is false for these inputs. Proposed owner action: disclose requested/effective zones and expand appropriately sourced tables or explicitly limit scope. No guessed substitute zone is evidence for the real one.
2. **The adapter carries unrelated example evidence into each model.** `scaled_bundle()` scales Matterport x/y dimensions and changes year/use/site/weather but retains the office example's CoStar tenancies (including post-2017 move-ins), class A, four stories, gross area 10,600.9 m2, and Vexcel roof records. The registry consumes those fields; `build_building_model()` also passes Vexcel and CoStar stories into geometry. Consequently this is not purely an area/vintage/defaults-only experiment, nor necessarily a flat one-storey model as its prose describes. Owner action: strip unrelated evidence, distinguish a generated geometric proxy from real data, then inspect resulting geometry and assumptions before rerunning.
3. **Whole-building residential meters use a dwelling-unit model.** All 73 Lodging/residential properties become `multifamily_unit` with a scaled house's unchanged bedroom labels. Registry occupancy and appliance/hot-water formulas depend on bedroom count, so an enlarged dormitory still has a single dwelling's bedroom/appliance structure. This group has median and aggregate errors of -84.1% and -83.1%, respectively. Do not infer an occupancy count or dwelling count by fitting to these meters; use independently sourced metadata or report the mapping unsupported.

These were sent to Vignesha and Yale in Message Board comment #6889126586. Vignesha owns adapter/archetype/meter-scope corrections; Yale owns registry/model changes. Their causal contribution and any improvement have **not** been measured. Wider ranges affect coverage, not the expected prediction's accuracy; that work needs a separate assessment.

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

Add `--runs /path/to/backend/evals/out/per_building.json` to rescore the corrected public output, or supply the owner's original full `runs.json`. Both schemas retain missing predictions and the input hash. Its status explicitly distinguishes rescoring owner outputs from rerunning the model. No new raw/per-building input copies are committed here.

```bash
python -m backend.evals.high_level.audit_truth \
  --cache-dir /private/path/to/bdg2 \
  --predictions backend/evals/out/per_building.json \
  --output /tmp/truth-check.json
```

Twenty targeted tests cover arithmetic, export/refusal preservation, acquisition safeguards and calendar/completeness failures. The acquire_bdg2 module downloads the four public inputs into a caller-selected cache, verifies the delivered byte counts and hashes, and rejects LFS pointers, truncated/changed files and oversized responses. It never trusts or overwrites mismatched existing inputs. No production source, model parameter, cached sponsor data or displayed financial result was changed by this audit.

## Next checkpoint

1. Receive the promised exact weather/end-use handoff and independently rerun the corrected original model; preserve the original and corrected baselines before owner fixes.
2. Have the responsible owners fix input provenance, climate/archetype scope and meter boundaries. Compare controlled diagnostic changes individually on the existing development cohort; do not call this a blind test or replace the original report with improved numbers.
3. Freeze eligibility, mappings, development/test splits and intended-use acceptance criteria before scoring new cohorts. RECS anonymization and aggregate geography may permit only cohort comparisons; do not invent precise geometry or weather to create a property-level test.
4. Resume the six-track plan after the required frontend integrations, without tuning on the already-inspected initial evaluation set.

# EBEWE evaluation (our scans vs real LA building energy use)

Tests our whole-building energy estimate on **real scanned buildings** (CoStar record + Matterport scan + Vexcel roof)
against the City of Los Angeles EBEWE benchmarking data (public, dataset 9yda-i4ya on data.lacity.org: whole-building
annual site EUI, floor area, type, year built). No BDG2 data is used. It is an ADDITIONAL eval beside the published
494-building one, not a replacement.

## Data rules
- **Nothing per-building is committed.** The join (kit address to EBEWE address) and every per-building file live in the
  git-ignored `data/runs/_ebewe/`. Only aggregate numbers (`results/`) are committed.
- The kit is sponsor data (CoStar and Matterport); do not republish addresses, ids or per-building kit fields.
- Panoramas for the vision arm go only to the Anthropic API.

## Run it (from the repo root, keys exported: `set -a; . ./.env; set +a`)
```
python -m backend.agent.ebewe_eval.match                 # join + pre-registered filter -> selected.json
python -m backend.agent.ebewe_eval.run 0 150 none 12      # true vintage defaults (no observations at all)
python -m backend.agent.ebewe_eval.run 0 20 vision 5      # real vision, about 1 USD per property
python -m backend.agent.ebewe_eval.score none --summary results/arm_none_run2.json
python -m backend.agent.ebewe_eval.solar results_none.jsonl --summary results/solar_vs_pvgis.json
```

## Pre-registered design (fixed before any score was seen)
- Join on normalised address; keep buildings with at least 3 usable EBEWE years (2016-19 and 2022-24, COVID 2020-21
  excluded), GFA of at least 20,000 ft2, EUI between 10 and 300 kBtu/ft2; one scan per address.
- Truth = median weather-normalised site EUI over the usable years; band = min to max across those years.
- Compare **EUI**, never totals: a scan is usually one suite or unit (model area under half the building in 115 of 116 cases).
- Arm A uses no observations at all (not even the hand-written example observations the demo properties fall back to).
- Metrics: median absolute error with a building-bootstrap 90% CI, median signed error, within 25%, two-sided factor-2
  misses, coverage of the stated low-to-high range, Spearman rank correlation, and a **naive constant predictor** (every
  building gets the cohort median EUI) beside every model number.

## Results (aggregates; revision b1429f7 = main with #442, #443, #444; 150 buildings selected)
Arm A, true defaults: 116 scored, 34 failed. Failures are counted, not dropped: 31 crash in the data layer
(`places.lookup` gets lat/lon None for scans with no georeference; was a clean refusal before #442) and 2 crash in the
solver (ZON-01 zero-mass zone).

| Cohort | n | Median abs error | Signed | Within 25% | Range held truth | Constant predictor |
|---|---|---|---|---|---|---|
| Office | 49 | 14.8% | -5.3% | 59% | 57% | 16.5% |
| Multifamily (unit scan vs whole building) | 66 | 51.0% | +44.2% | 33% | 32% | 17.6% |
| All | 116 | 36.3% | +7.3% | 44% | 42% | 15.3% |

Reading: for offices the model is barely better than guessing the cohort median (rank correlation about 0.2: it does not
separate one office from another); for unit scans it is much worse than the constant, and unit-vs-building is not a
like-for-like boundary. Do not quote the office number without the constant-predictor number beside it, and never pool
office with apartments.

Arm B, real vision, 20 offices that built in arm A (about 18 USD, about 0.92 per office): median abs error 17.2% against
13.2% for arm A on the same offices; paired difference median -0.3 points (90% CI -1.5 to +3.9); vision closer in 11 of 20,
farther in 7. No measurable effect on whole-building EUI at n=20; its value is in the plan (measures already done, windows,
shading), not in total energy.

Solar (our annual kWh per kW against PVGIS-ERA5, model vs model, coordinates rounded to 0.01 degree): see
`results/solar_vs_pvgis.json`; median difference about +2%, all within 10%, but nearly all flat south-default roofs, so
orientation is barely exercised.

## Not tested here
Daylight and comfort (no validation data), economics and tariffs, lighting and LED savings (EBEWE cannot validate them),
measured PV output (needs PVDAQ-type data).

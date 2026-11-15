# Evaluating the physics on real properties

Owner: @vigjay (data lane). Scope: `backend/evals/`.
Status: spec. Nothing here has been published. Numbers below come from a dry run
on 2026-11-15 and are reproducible with the command in section 8.

## 1. Why this exists

The published eval (`SCOPE.md`, `REPORT.md`) scores 424 Building Data Genome 2
buildings against real meters. It is the only eval we have with ground truth, and
it will stay the headline for accuracy. But it scores the **defaults path**: area,
vintage and type go into the DEF tables, one golden office layout is scaled by
sqrt(area ratio), and the 5R1C model runs on that. No scan geometry, no rooms,
no panoramas, no roof.

That is the path we take when we know nothing about a building. It is not the path
we demo. Every number we publish today therefore describes the product at its
worst input, and says nothing about the product a user actually gets after a
Matterport scan.

This spec covers the other half: run the real pipeline on real properties and
measure what can be measured without a meter.

## 2. What the real data is

61 cached bundles under `data/cache/<sid>/bundle.json`, each a full
`PropertyBundle` assembled from CoStar + Matterport + Vexcel. Measured, not assumed:

| Property | Count |
|---|---|
| Bundles | 61 |
| With Matterport rooms, floors and georeference | 61 |
| With CoStar record and `building_area_m2` | 61 |
| With Vexcel parcel, footprint and detections | 61 |
| With real TMYx hourly weather and a set `climate_zone` | 61 |
| **With utility bills** | **0** |
| **With panorama face images on disk** | **0** |

Segments: 47 commercial, 14 residential.
Use types: 16 office, 15 retail, 13 single-family, 10 multifamily unit, 7 other.
States: 31 TX, 30 CA.

Two facts shape everything below.

**Climate zones are 28x 3B and 25x 2A — every single property sits in a zone the
DEF tables actually carry.** The BDG2 eval had 96 of 494 in supported zones and
blended the rest. This cohort is the model read entirely on its own terms, which
makes it a *stricter* test of the tables, not a softer one.

**There are no bills.** No meter means no error can be computed. Anyone who
proposes an "accuracy" number from this cohort is proposing a fabrication. The
checks below are all consistency, coverage and plausibility checks, and each one
states what it cannot tell you.

## 3. Non-goals

- Any claim of the form "our predictions are within X% on real properties."
- Replacing the BDG2 numbers. These sit beside them and answer a different question.
- The vision path. Zero panorama faces are cached; `observe_interior` has nothing
  to read. Scoring vision needs a Matterport re-fetch first: the bundles reference
  2,533 panoramas and 15,198 face images, and `VISION_MAX_PANOS = 40` caps what the
  product reads, so a scoring run needs roughly 40 panoramas x 6 faces x 61
  properties, about 14,600 images. Separate work package, and it needs the API
  credentials.

## 4. The checks

### C1 — Does the pipeline survive real data?

**Question.** On 61 real properties, how many complete, how many refuse cleanly,
and how many crash?

**Method.** `build_building_model` then `run_baseline` on each bundle. Classify
each outcome as completed / refused with a stated reason / crashed with a traceback.

**Why it matters more than it sounds.** We spent today making every system
"comfortable saying I don't know." A crash is the opposite of that: it is the
system failing to say anything. This check is the audit of that work.

**Already measured. 53 of 61 complete; 8 crash. Zero refuse cleanly.** Three
classes, all traced:

| n | Error | Location |
|---|---|---|
| 5 | `Ranged requires low <= expected <= high` | `backend/analysis/model/geometry/build.py:461` |
| 2 | `H_tr,op ... must be below H_tr,ms 0.0 W/K (ZON-01)` | `backend/analysis/physics/zone/rc.py:57` |
| 1 | `ZeroDivisionError` | `backend/analysis/physics/zone/rc.py:80` |

The first is a one-line defect: ceiling height is built as
`Ranged(low=min(h), expected=round(mean(h), 4), high=max(h))`. When every
observed height is equal, rounding the mean to 4 dp can land *above* the
unrounded max, and the model rejects its own value. It fires on 8% of real
properties and on none of the three golden examples.

The other two are a zone with zero internal mass area reaching the 5R1C solver.
That is degenerate geometry arriving from a real scan and not being caught at
the boundary.

**Pass condition.** Zero crashes. Every property either completes or produces a
`not_analysed` result naming what was missing. **Today it fails.**

**This check belongs to @yalexie1's lane** (`backend/analysis/`). The eval
reports it; it does not fix it.

### C2 — Does the scan describe the building we are charging for?

**Question.** The model's conditioned floor area comes from the Matterport scan.
CoStar states the building's area independently. Do they agree?

**Method.** Ratio of summed zone `floor_area_m2` to `costar.building_area_m2`,
per property, stratified by use type. Two independent sources, no benchmark needed.

**Already measured, and this is the most serious finding in the cohort:**

| Use type | n | Median scan/CoStar | Min | Max |
|---|---|---|---|---|
| office | 12 | **0.018** | 0.002 | 0.19 |
| multifamily unit | 10 | 0.035 | 0.005 | 0.90 |
| other | 5 | 0.095 | 0.049 | 0.54 |
| retail | 13 | 0.161 | 0.032 | 1.20 |
| single-family | 13 | **1.944** | 0.359 | 5.62 |

34 of 53 scans cover less than half the CoStar area. The worst office models
89 m² against a 37,092 m² record — 0.2%. Homes run the other way: one models
1,020 m² against a 182 m² record, 5.6x.

The commercial cases are mostly not a bug in area extraction. They are scans of
*one suite* inside a large building, and CoStar describes the whole structure.
But the pipeline does not currently decide which of the two it is pricing. The
same ambiguity sank the BDG2 numbers in a different costume: there, 37% of
buildings were on district service, so the meter did not contain what we were
predicting. Here, the scan does not contain what CoStar describes.

**Pass condition.** Every property states which scope it reports — scanned suite
or whole building — and the area it used is consistent with that statement. A
property whose two sources disagree by more than 2x and which cannot say why is
a refusal, not a number.

The residential side is a genuine extraction question: a 5.6x ratio is not a
suite-versus-building story and needs a look.

### C3 — Is the energy intensity plausible against the EIA surveys?

**Question.** Does predicted site EUI land inside the RECS 2020 / CBECS 2018
distribution for comparable buildings?

**Method.** `backend.analysis.model.benchmark.checks.check_baseline`, which is
already wired into `run_baseline` via `_benchmarked`. Note it is wired for its
*warnings* only — the `EuiBenchmark` object is discarded. The eval calls
`check_baseline` directly to keep the structured result.

**Coverage.** 35 of 53 completed properties get a benchmark. 18 do not: 13 retail
and 5 other, because `BUILDING_TYPES` carries only single-family, multifamily and
office. Retail is our second largest segment and has no survey check at all.

**Already measured.** Of 35: 30 typical, 2 low, 2 very low, 1 high. Median
percentile 47.

**Read that result with suspicion, and this is the central caveat of the whole
spec.** EUI is energy divided by area, and 73% of our predicted electricity is
plug plus lighting, both computed as area x a DEF density. Numerator and
denominator carry the same area, so it largely cancels: the check is close to
asking whether DEF-09 and DEF-10 were set near survey central values. They were.
A median percentile of 47 is therefore mostly a statement about our table
defaults, not evidence the physics is right.

It retains three honest uses, and the spec claims only these:
1. **Tails.** The 4 low/very-low and 1 high are real signals worth opening.
2. **Gas and heating.** Gas does not cancel the same way; the envelope and the
   5R1C model drive it. Score the gas band separately and weight it higher.
3. **Gross area errors.** A C2 failure shows up here as an absurd EUI.

**Pass condition.** None as a headline. Report the tails and the gas band; do not
publish the aggregate "typical" share as validation.

### C4 — Does knowing the real geometry narrow the band?

**Question.** The BDG2 eval found coverage of 12.8% against a design intent of
80%, and the calibrated run moved it only 43.2 -> 45.5, which suggested the
interval problem is structural in UNC-02 rather than a lack of information. Real
geometry is the strongest extra information we have. Does it help?

**Method.** For each of the 53, compare band width as a percent of expected
against the BDG2 defaults-path distribution (mean 40.9% of expected). Same
`score_eval.describe` code, so the two are comparable by construction.

**Why it is worth running despite having no truth.** Coverage needs truth; width
does not. If real geometry does not narrow the band, that is direct evidence the
band is driven by the perturbation design and not by input uncertainty — which
would confirm the known `lighting.lpd` / `plug.ppd` defect where high == expected
and the band has no upside at all.

**Pass condition.** Diagnostic only. No pass or fail; the output is a number and
an interpretation.

### C5 — Does PV hold up on real roofs?

**Question.** The published PV cross-check ran on the golden examples. Does
modelled yield still agree with PVGIS on roofs derived from 61 real Vexcel
footprints?

**Method.** `design_pv` under both product constraints (roof-and-consumption, and
the $10,000 budget) exactly as `run_pv.py` does, then PV-10 against PVGIS per
plane. Compare kWh/kW, not system size: the published run established that
capacity varies 85x between constraints while kWh/kW is identical, so yield per
kW is the portable quantity and system size inherits the baseline error.

**What the roofs actually are.** Zero bundles carry Vexcel `roof_planes`. Planes
are generated by `build_parametric_roof` from the footprint plus state. Measured
plane counts: 35 properties get 1 plane, 10 get 4, 8 get 2. **A single flat plane
on 35 of 53 is a parametric default, not an observed roof**, and the eval must
label those rows as such. PV-10 agreement on a plane we invented tests the
transposition maths, not our roof reading.

**Pass condition.** Every property inside PV-10 tolerance, with the 1-plane rows
clearly marked as parametric.

## 5. What this cohort cannot tell us

Stated once, plainly, and repeated on any page that shows these numbers:

- **No accuracy.** Zero meters. Nothing here is an error against truth.
- **No vision.** Zero cached panorama faces.
- **No observed roofs.** Planes are parametric for most properties.
- **Two states.** CA and TX only. It is a strict test of zones 3B and 2A and
  silent about everywhere else.
- **n is small.** 61 properties, 53 completing, 35 benchmarkable, 13 single-family.
  Report counts next to every figure.

## 6. Relationship to the published eval

They answer different questions and neither replaces the other.

| | BDG2 (published) | Real properties (this spec) |
|---|---|---|
| n | 424 scored | 61, 53 completing |
| Truth | Metered annual kWh | None |
| Geometry | Golden layout scaled by sqrt(area) | Real scan: floors, rooms, georeference |
| Climate zones | 96 of 494 supported | 53 of 53 supported |
| Answers | How wrong are we | Does the real path work, and is it self-consistent |

The one-line framing for anyone presenting both: *accuracy is measured on meters
we did not scan; behaviour is measured on scans we cannot meter.*

## 7. Deliverables

- `backend/evals/run_real.py` — runs the 61, writes `data/cache/evals/out/real.json`
  with one record per property: outcome, areas, zones, bands, benchmark, PV, and
  the full traceback for any crash.
- `backend/evals/score_real.py` — C1 to C5 into `real_scorecard.json`, reusing
  `score_eval.describe` so widths are comparable to the published cohort.
- Extend `publish.py` with a `real_properties` slot. It stays `not_run` until C1
  passes; a page that shows consistency figures from a cohort where 13% crashed
  would be misleading.
- Tests under `backend/evals/tests/`, mirroring `test_score.py`: assert the
  no-truth invariant (no field named like an accuracy), assert crashes are counted
  rather than dropped, assert parametric-roof rows are labelled.

## 8. Cost

The dry run that produced every measured number above took **62 seconds** for all
61 properties, single process, ~1 s each. Adding PV under two constraints roughly
triples it. This is a sub-five-minute eval, not an eight-minute one like BDG2.

Build estimate: ~2 hours for `run_real.py` + `score_real.py` + tests, following
the shape of `run_eval.py` / `score_eval.py`.

Environment note: the repo has no committed virtualenv and the session's was lost.
`python3.14 -m venv .venv && .venv/bin/pip install pydantic numpy shapely pandas pytest`
reproduces it.

## 9. Open questions

1. **C1 crashes are @yalexie1's lane.** The ceiling-height rounding bug is a
   one-liner; the two ZON-01 zero-mass crashes need a decision about whether a
   degenerate zone refuses or is repaired. Needs a board post with
   `HANDOFF-REQUEST:` or a fix by the owner.
2. **C2 scope.** Does a scanned suite inside a large building get priced as the
   suite or as the building? This is a product decision, not an eval decision,
   and it changes what every commercial number means.
3. **Retail has no survey benchmark.** 15 of 61 properties and our second largest
   segment. CBECS covers retail; `build_eui_tables.py` currently filters to
   Office. Extending it is a contained piece of work.
4. **Vision.** Worth a re-fetch of panorama faces, or out of scope?

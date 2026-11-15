# What is actually wrong with our numbers, and what would fix it

Owner: @vigjay (data lane). Produced 2026-11-15 from the committed 494-building
run at `data/cache/evals/out/runs.json`, scored with `backend/evals/score_eval.py`.
Every figure below is reproducible; section 7 lists the commands.

This is a diagnosis document, not a scorecard. The published numbers live in
`REPORT.md` and on the Evals page; this explains where they come from.

## 0. The short version

| Claim | Evidence |
|---|---|
| **The model does not beat a predictor with no model in it** | A constant scores 42.5% against our 52.9%, and wins in **every** usage class (section 10) |
| Our "we underpredict by 17%" is mostly one archetype bug | Removing 73 lodging buildings moves the median from -17.1% to -2.6% |
| Tuning the default tables cannot take us below ~38% | An *oracle* per-class bias correction, fitted on the truth, only reaches 37.7% |
| The uncertainty band cannot be fixed by widening | 80% coverage needs 20-30x the current width, i.e. +/-400-600% |
| We cannot blame the cohort | The cleanest subset is *worse*: 71.9% median absolute, 7.8% coverage |
| Only per-building information helps materially | Bills take the same buildings from 18.1% to 4.1% |

## 1. The residential archetype is applied to buildings that are not homes

73 of 494 buildings (15%) route to the residential archetype. Every one is
`Lodging/residential`: hotels, dormitories and apartment blocks. They are
modelled as a single dwelling scaled to the whole building's floor area.

```
our median EUI    16.2 kWh/m2
metered           87.6 kWh/m2      we predict 1/5.4 of reality
median error     -84.4%            median absolute 84.4%
```

**Measured since: fixed in #443, verified 2026-11-15.** Two full 494-building runs,
control `origin/main` 667f25e against `origin/lodging-archetype` 1914c2e (main plus
that one commit), same inputs and weather. Lodging median absolute error went
**84.4% -> 43.7%**, within 25% **0.0% -> 28.8%**, coverage **2.7% -> 37.0%**, and the
predicted median EUI rose 16.2 -> 60.9 against 87.6 metered. The headline moved
52.9% -> 46.0% and coverage 12.8% -> 17.8%. A per-building diff of all 494
predictions found 422 identical and 72 changed, **all 72 lodging, none outside it**,
confirming the author's claim that one dwelling reproduces the old calculation
exactly. The residual ~30% under-prediction is the common-area load (corridors,
lifts, laundry) that the change deliberately does not model. Note it still does not
clear the bar in section 10: the constant scores 39.2% on this class against 43.7%.

A hotel modelled as a scaled-up house has no corridors, no lobby, no commercial
laundry or kitchen, no lifts, and carries single-family lighting and plug
densities. The error is structural, not a tuning problem.

What it costs the headline:

| Cohort | n | Median signed | Median absolute | Coverage |
|---|---|---|---|---|
| All buildings | 494 | -17.1% | 52.9% | 12.8% |
| Excluding lodging | 421 | **-2.6%** | 46.5% | 14.5% |
| Lodging bias-corrected x6.4 | 494 | **-2.2%** | 44.2% | - |

The published "the model underpredicts" is substantially this one class, not a
general property of the physics. **Fix: a lodging/multifamily archetype separate
from single-family.** Highest-value change available, and it is in
`backend/analysis/` (@yalexie1).

Corroboration from the other direction: @Sri-SriPod's EBEWE run shows multifamily
at +37% signed against whole-building EUI. Same defect class, opposite sign,
because his model area is a scanned unit and his truth denominator is whole-building
gross floor area.

## 2. Tuning the default tables has a measurable ceiling

Give the model an **oracle** bias correction: one multiplier per class, fitted on
the very truth it is scored against. That is cheating by construction, so whatever
it achieves bounds what any amount of honest table tuning could achieve.

| Oracle correction | Median absolute | Within 25% |
|---|---|---|
| None (actual) | 52.9% | 21.9% |
| One global multiplier | 57.6% | 22.5% |
| Per usage type | 42.6% | 27.9% |
| Per usage x site | 37.7% | 37.4% |
| Per usage x site x tall | 37.1% | 37.9% |

**About 71% of the error is within-class scatter, not between-class bias.** Perfect
archetypes still leave roughly 38% median absolute error on this cohort.

So table tuning is worth about 15 points and then stops. It is worth doing - 15
points is real - but it is not a route to a good number. Below that floor, only
per-building information helps, which is exactly what the calibrated arm measured:
the same 44 buildings go from 18.1% to 4.1% once a year of bills exists.

(A single global multiplier makes things *worse*. The classes pull in opposite
directions, so one number cannot serve them.)

## 3. The uncertainty band cannot be fixed by widening it

Scaling the published low/high around the expected value:

| Factor | Coverage | Mean width |
|---|---|---|
| x1 (today) | 12.8% | +/- 41% |
| x3 | 40.1% | +/- 124% |
| x5 | 50.6% | +/- 207% |
| x12 | 64.2% | +/- 497% |
| x20 | 76.7% | +/- 828% |
| x30 | 85.0% | +/- 1242% |

Reaching the 80% design intent takes 20 to 30 times the current width. A range of
+/-400 to 600% of the expected value is not a product.

The interval is not independently broken; it is downstream of the point estimate's
scatter. An honest band around a prediction this scattered is a useless band. The
two legitimate responses are to improve the point estimate (sections 1 and 2) and
to abstain where we cannot, not to inflate the range.

One genuine interval defect remains and is worth fixing on its own terms:
`lighting.lpd` and `plug.ppd` have `high == expected` in
`backend/analysis/model/registry/tables.py:234-243` (confirmed by @yalexie1), so
for 55% of the predicted electricity the band has no upside at all. That is why
the bins are so lopsided: 44.3% of buildings fall above our high.

## 4. The cohort is not the excuse

The obvious hypothesis is that 52.9% is contaminated - blended climate zones,
district service, type mismatch - and that a clean subset would look better.
It does not. It looks worse.

| Filter stack | n | Median signed | Median absolute | Coverage |
|---|---|---|---|---|
| All buildings | 494 | -17.1% | 52.9% | 12.8% |
| + supported zone (2A/3B) | 96 | -45.6% | 56.7% | 11.5% |
| + not on district service | 71 | -51.0% | 71.9% | 9.9% |
| + no gas meter | 51 | -53.9% | **71.9%** | 7.8% |

The pooled 52.9% benefits from error cancellation across heterogeneous groups.
On the cleanest subset we underpredict by 54%.

Two honest caveats on this table. All 96 supported-zone buildings sit at one site
(Panther, FL), so climate zone and site are confounded and cannot be separated
here. And the lodging defect of section 1 is concentrated in that site: within the
supported zone, `Lodging/residential` runs at -88.2% median (our EUI 17.0 against
144.2 metered). Sections 1 and 4 are not independent findings.

Single-filter view, for reference:

| Filter | n | Median | Median absolute | Coverage |
|---|---|---|---|---|
| Office only | 61 | +0.6% | 44.1% | 11.5% |
| 1 storey | 411 | -19.2% | 49.7% | 13.1% |
| No district service | 309 | -19.4% | 52.2% | 12.6% |
| No gas meter | 468 | -15.7% | 52.7% | 12.8% |

Office is where the defaults were built, and it shows: essentially no bias.

## 5. Two corrections to things this lane said earlier

**End-use shares.** This lane previously stated that plug plus lighting was 73% of
predicted electricity, and used that to argue the eval tested the DEF tables rather
than the 5R1C model. Measured over the 494:

| End use | Mean share | Median share |
|---|---|---|
| heating | 28.6% | 29.1% |
| lighting | 28.3% | 28.7% |
| plug | 26.3% | 26.0% |
| cooling | 16.4% | 11.9% |
| water heating | 0.2% | 0.0% |

Lighting plus plug is 54.6%, not 73%. The thermal model carries about 45% of the
prediction, so it is genuinely under test. The earlier claim understated how much
of the result the physics owns.

**Direction of the multifamily scope bias.** This lane predicted a systematic *low*
bias for unit scans against whole-building truth. @Sri-SriPod's run shows +37%,
high. The reasoning was about totals; the comparison is EUI, and a scanned unit is
all conditioned living space while whole-building gross floor area includes
corridors, garages and unconditioned space that dilute the denominator. Right
mechanism, wrong sign.

## 6. Recommendations, in priority order

1. **Lodging/multifamily archetype** (@yalexie1, `backend/analysis/`). Moves the
   headline median from -17.1% to about -2.6%. Largest single win available.
2. **Plausibility floor from the benchmark we already have.**
   `backend/analysis/model/benchmark/eui.py` already computes RECS/CBECS
   percentiles, and `_benchmarked` in `api.py:469` already calls it - but keeps only
   the warnings and discards the `EuiBenchmark` object. Our predicted EUI p10 is
   17.2 kWh/m2 against a metered p10 of 47.9. A BEN-03 floor would have flagged all
   73 lodging buildings automatically. Cheap, and it turns a silent wrong answer
   into a visible one.
3. **Per-class reporting as standard in the eval** (this lane). The lodging defect
   was invisible in the pooled number. Add the section 2 oracle diagnostic as a
   routine metric: it separates bias from scatter in one line and says when tuning
   is exhausted.
4. **Two-sided ranges for `lighting.lpd` and `plug.ppd`** (@yalexie1), section 3.
5. **Degenerate-zone abstention** - the `rc.py` zero-mass crashes. @yalexie1 has
   ruled these refuse with a stated reason rather than repair; see
   `REAL_PROPERTY_EVAL.md` section 4 C1.

Not recommended: widening the band (section 3), and chasing weather. Swapping
measured station temperatures for the reanalysis path moves the electricity median
by about 1% of truth, already published in `REPORT.md`.

## 7. Reproducing this

```bash
python -m venv .venv && .venv/bin/pip install pydantic numpy shapely pandas pytest
```

Every table comes from `data/cache/evals/out/runs.json` (produced by
`python -m backend.evals.run_eval 500`) read with `score_eval.describe`,
`score_eval.coverage` and `score_eval.err_pct`. The oracle correction of section 2
takes the median of `truth / predicted` within each class and re-scores; the
widening of section 3 scales `low` and `high` about `expected` and re-counts
containment. The district-service flag in section 4 is the presence of any of
`hotwater`, `chilledwater`, `steam` in BDG2 `metadata.csv` - 185 of 494, 37%.

## 10. The model does not beat a predictor with no model in it

This is the finding that should have come first, and it went unnoticed for hours
because nobody asked the prior question. We published "median absolute error 52.9%",
stratified it, bootstrapped it, and wrote sections 1 to 6 explaining *why* it was
52.9% - without ever establishing what a predictor containing no physics scores.

**The constant predictor.** Give every building the cohort's median intensity times
its own floor area. One number, one input, no model.

| Cohort | Our model | Constant | |
|---|---|---|---|
| **All 494** | 52.9% | **42.5%** | constant wins by 10.4 points |
| Education (234) | 47.7% | **46.1%** | constant wins |
| Lodging (73) | 84.4% | **39.2%** | constant wins |
| Office (61) | 44.1% | **38.2%** | constant wins |
| Entertainment (53) | 50.8% | **49.4%** | constant wins |
| Public services (41) | 32.1% | **24.5%** | constant wins |

It wins pooled, and in every single class.

**The fair version, because the constant above is an oracle.** It is fitted on the
same truth it is scored against, so it is a harder floor than anything deployable.
The honest comparator is a *published* reference median. Using CBECS 2018 office
median electricity EUI by climate group - a public table, no knowledge of our test
set - on the 61 BDG2 offices:

| | Median absolute | Within 25% |
|---|---|---|
| Our physics model | 44.1% | 18.0% |
| **CBECS p50 x area (public, deployable)** | **39.8%** | **26.2%** |
| Cohort median x area (oracle) | 38.2% | 27.9% |

A published lookup table beats our physics, and the oracle is only 1.6 points better
than the public table, so the finding is not an artifact of the oracle's advantage.

**Independently reproduced.** @Sri-SriPod hit the same wall on the LA EBEWE cohort -
a different dataset, a different truth source, a different baseline construction. On
his 20-office vision arm the constant scored 12.2%, better than both the defaults arm
(13.2%) and the vision arm (17.2%). Two evals, same verdict.

**What this does and does not mean.** It does not mean the physics is worthless: the
model produces an end-use breakdown, a measure plan and a sensitivity analysis that a
constant cannot, and those are the product. It does mean that **our annual-total
prediction has no demonstrated skill**, and that any sentence of the form "our median
error is X%" invites "better than what?" - to which the honest answer today is "worse
than median-intensity-times-area".

**Now enforced in code.** `score_eval.skill_section` computes this on every run,
pooled and per usage class, and names the winner rather than leaving it to the
reader. It is in the printed summary and in `scorecard.json` under `skill`, and the
caveat list says so. The reason it went unnoticed was that checking required someone
to remember to check; it no longer does.

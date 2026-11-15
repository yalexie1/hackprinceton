# Evals Implementation Plan (issue #394, time-boxed)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a defensible, published measurement of how reliable Leto's energy and PV projections are, with the metered-building eval and the PV cross-check landing first.

**Architecture:** Three independent evals, each writing one static JSON under `backend/evals/out/`, consumed by a single read-only `Evals.tsx` page. No `schema.py` change; no shared state between evals; each is runnable alone so a failure in one does not block the others.

**Tech Stack:** Python 3.14 (pydantic, pandas, numpy, shapely), existing `backend.analysis.api`, React + Vite frontend.

**Spec:** `specs/evals.md` (Task 1 writes it; it records scope and the caveats that must travel with every number). Board assignment: issue #394.

**Plan location note:** The writing-plans default is `docs/superpowers/plans/`, but AGENTS.md section 4 gives `docs/` to the board template ("change only by agreement on the board"). `backend/evals/` was assigned to @vigjay by the lead in the #394 post, so the plan lives with the work it describes.

## Global Constraints

- One writer per path. `backend/evals/` and `data/cache/evals/` are @vigjay's. **Do not edit** `backend/analysis/**`, `backend/schema.py`, or `frontend/src/App.tsx` without the board handoff; @vinayak-sinha's OK for `frontend/` was requested in #394 and is **not yet granted** — Task 6 is blocked until it is.
- Sponsor and bulk data are never committed. `data/cache/**` is git-ignored: commit manifests, scripts and `backend/evals/out/*.json` only.
- Energy only. `PropertySummary.state` is `Literal["CA","TX"]`, so eval buildings are labelled `CA`; cost, CO2 and incentives are therefore **not scored** and must not be published as validated.
- Every published number carries its `n`, its arm, and its caveat list. No number ships without them.
- Confidence intervals are bootstrapped over **sites**, never buildings: weather is site-level and there are only 5 sites.
- Nominal interval coverage is **80%** (`UNC-01`, 10th–90th percentile).
- Measured baseline to preserve: n=494, 0 refused, 0.97 s/building, median abs error 55.5%, coverage 17.6%.

## Review Focus

Input classes the eval implies but no current test exercises, most likely to bite first:

1. **A building whose metered year is partly missing** — `load_truth` scales the annual up by `hours/present`; at 90% completeness that silently invents 10% of the total. A building at exactly the 0.90 boundary must be included and its scaled total must be correct. Test in Task 2.
2. **A zero or negative metered total** — a dead meter reads 0 and makes `err_pct` divide by zero. Must be excluded, not crash. Test in Task 2.
3. **`coverage()` boundary equality** — truth exactly equal to `low`, `expected`, or `high`. Off-by-one here moves the headline number. Test in Task 2.
4. **An eval arm that refused** — `rec["arms"][arm]` has `refused` and no `elec`; every scorer path must skip it and the refusal must appear in the count, never be dropped. Test in Task 2.
5. **A single-site or single-building sample** — `cluster_bootstrap` with one cluster must return a degenerate interval rather than divide by zero, so a smoke run does not crash the scorer. Test in Task 2.

---

### Task 1: Relocate the eval into `backend/evals/` and record the scope

**Files:**
- Create: `backend/evals/__init__.py`, `backend/evals/prep_weather.py`, `backend/evals/run_eval.py`, `backend/evals/score_eval.py`, `backend/evals/manifests/bdg2.yaml`, `specs/evals.md`
- Delete: `data/fixtures/evals/prep_weather.py`, `data/fixtures/evals/run_eval.py`, `data/fixtures/evals/score_eval.py`
- Modify: `.gitignore` only if `backend/evals/out/` is not already covered

**Interfaces:**
- Consumes: nothing.
- Produces: `backend.evals.run_eval.main()`, `backend.evals.score_eval.main()`, `backend.evals.prep_weather.main()`, all `() -> int`. `ROOT` in each resolves to the repo root from the new depth (`parents[2]`, not `parents[3]`).

- [ ] **Step 1: Move the three scripts and fix `ROOT`**

`git mv` each file, then change `ROOT = Path(__file__).resolve().parents[3]` to `parents[2]` in all three.

- [ ] **Step 2: Verify the move did not break paths**

Run: `python -m backend.evals.score_eval`
Expected: reprints the existing scorecard, `n_scored 494`, `refused 0`.

- [ ] **Step 3: Write `backend/evals/manifests/bdg2.yaml`**

Record for each downloaded file: URL (the `media.githubusercontent.com` LFS endpoint — `raw.githubusercontent.com` returns LFS pointers), SHA256, byte size, licence, and the BDG2 citation (Miller et al., *Scientific Data*, arXiv:2006.02273).

- [ ] **Step 4: Write `specs/evals.md`**

Must state, in prose: that this is a **defaults-path** eval and not end-to-end; that geometry, vision, daylight and PV layout are excluded by construction because BDG2 carries no scan or roof inputs; the five-site clustering limit; the single-storey simplification; that irradiance is Open-Meteo in both arms so the arm difference isolates temperature only; and that cost/CO2 are unscored. Copy the caveat list from `score_eval.py` verbatim so the two cannot drift.

- [ ] **Step 5: Commit**

```bash
git add backend/evals specs/evals.md .gitignore
git commit -m "evals: move the BDG2 defaults-path eval into backend/evals, record scope"
```

---

### Task 2: Pin the scorer's arithmetic with tests

The headline numbers rest entirely on `coverage()` and `load_truth()`. This task exists because a boundary error in either silently changes what we publish.

**Files:**
- Create: `backend/evals/tests/__init__.py`, `backend/evals/tests/test_score.py`
- Modify: `backend/evals/score_eval.py`, `backend/evals/run_eval.py` (fixes the tests force)

**Interfaces:**
- Consumes: `score_eval.coverage(rows, arm) -> dict`, `score_eval.describe(errs) -> dict`, `score_eval.err_pct(row, arm) -> float | None`, `score_eval.cluster_bootstrap(rows, arm, stat, draws) -> list[float]`, `run_eval.load_truth(ids, fuel) -> dict[str, dict]`.
- Produces: no new interface; `load_truth` gains a documented exclusion of non-positive totals.

- [ ] **Step 1: Write the failing tests**

```python
def test_coverage_counts_boundaries_as_inside():
    band = {"low": 100.0, "expected": 150.0, "high": 200.0}
    rows = [{"site_id": "S", "truth_elec_kwh": t, "arms": {"a": {"elec": band}}}
            for t in (100.0, 150.0, 200.0)]
    assert coverage(rows, "a")["coverage_pct"] == 100.0

def test_coverage_splits_outside_by_side():
    band = {"low": 100.0, "expected": 150.0, "high": 200.0}
    rows = [{"site_id": "S", "truth_elec_kwh": t, "arms": {"a": {"elec": band}}}
            for t in (99.0, 201.0)]
    out = coverage(rows, "a")
    assert out["coverage_pct"] == 0.0
    assert out["bins_pct"] == {"below_low": 50.0, "low_to_expected": 0.0,
                               "expected_to_high": 0.0, "above_high": 50.0}

def test_coverage_skips_refused_arms():
    band = {"low": 1.0, "expected": 2.0, "high": 3.0}
    rows = [{"site_id": "S", "truth_elec_kwh": 2.0, "arms": {"a": {"elec": band}}},
            {"site_id": "S", "truth_elec_kwh": 2.0, "arms": {"a": {"refused": "X: y"}}}]
    assert coverage(rows, "a")["n"] == 1

def test_err_pct_is_none_for_refused_and_for_zero_truth():
    band = {"low": 1.0, "expected": 2.0, "high": 3.0}
    assert err_pct({"truth_elec_kwh": 10.0, "arms": {"a": {"refused": "X"}}}, "a") is None
    assert err_pct({"truth_elec_kwh": 0.0, "arms": {"a": {"elec": band}}}, "a") is None

def test_cluster_bootstrap_with_one_site_is_degenerate_not_a_crash():
    band = {"low": 1.0, "expected": 2.0, "high": 3.0}
    rows = [{"site_id": "S", "truth_elec_kwh": 2.0, "arms": {"a": {"elec": band}}}]
    draws = cluster_bootstrap(rows, "a", lambda rs, x: coverage(rs, x)["coverage_pct"], draws=10)
    assert draws == [100.0] * 10

def test_describe_is_empty_for_no_errors():
    assert describe([]) == {"n": 0}

def test_load_truth_scales_for_gaps_and_drops_dead_meters(tmp_path):
    # 4 hourly stamps in YEAR; building A reads 1.0 for 3 of 4 (75% -> excluded at 90%),
    # building B reads 2.0 for 4 of 4, building C reads 0.0 throughout (dead -> excluded).
    ...  # writes a tiny CSV to tmp_path and monkeypatches BDG2 to it
    assert set(out) == {"B"}
    assert out["B"]["annual_kwh"] == 8.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/evals/tests/test_score.py -v`
Expected: FAIL — `test_err_pct_is_none_for_refused_and_for_zero_truth` fails (current `err_pct` returns `None` for zero truth only via a falsy check that also swallows a legitimate `0.0` band), and `test_cluster_bootstrap_with_one_site_is_degenerate_not_a_crash` fails or errors.

- [ ] **Step 3: Fix `score_eval.py` and `run_eval.load_truth` so the tests pass**

In `load_truth`, make the non-positive exclusion explicit and comment why (a dead meter is not a zero-energy building). Leave the 0.90 completeness threshold and the `hours/present` scale-up as they are — they are correct, and the test pins them.

- [ ] **Step 4: Run the tests to verify they pass, and that the headline is unchanged**

Run: `python -m pytest backend/evals/tests/test_score.py -v && python -m backend.evals.score_eval`
Expected: PASS, and `n_scored 494` with coverage still `17.6` on the `bdg2temp` arm. **A changed headline here means the fix altered a published number — stop and account for it before committing.**

- [ ] **Step 5: Commit**

```bash
git add backend/evals/tests backend/evals/score_eval.py backend/evals/run_eval.py
git commit -m "evals: pin coverage and truth-loading arithmetic with tests"
```

---

### Task 3: Publish the metered-building result as a static JSON and a report

**Files:**
- Create: `backend/evals/publish.py`, `backend/evals/out/metered_buildings.json`, `backend/evals/REPORT.md`

**Interfaces:**
- Consumes: `data/cache/evals/out/scorecard.json` (Task 1's layout).
- Produces: `backend/evals/out/metered_buildings.json` with top-level keys `headline`, `by_usage`, `by_site`, `weather_decomposition`, `caveats`, `provenance`. `headline` is a list of `{label, value, unit, nominal, ci90, n}` so the page renders it without arithmetic. **The page must do no computation.**

- [ ] **Step 1: Write the failing test**

```python
def test_publish_emits_headline_rows_with_n_and_caveats(tmp_path):
    out = build_payload(json.loads(SCORECARD_FIXTURE))
    labels = {r["label"] for r in out["headline"]}
    assert "Interval coverage" in labels and "Median absolute error" in labels
    cov = next(r for r in out["headline"] if r["label"] == "Interval coverage")
    assert cov["nominal"] == 80.0 and cov["n"] == 494 and len(cov["ci90"]) == 2
    assert len(out["caveats"]) >= 5
    assert out["provenance"]["dataset"].startswith("Building Data Genome")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest backend/evals/tests/test_publish.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.evals.publish`.

- [ ] **Step 3: Implement `build_payload(scorecard: dict) -> dict` and `main() -> int` in `backend/evals/publish.py`**

`main()` reads the scorecard, calls `build_payload`, writes `backend/evals/out/metered_buildings.json`. Carry `n`, `nominal`, `ci90` and the caveat list onto the payload unchanged — this function selects and relabels, it does not recompute.

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest backend/evals/tests/test_publish.py -v && python -m backend.evals.publish`
Expected: PASS; the JSON exists and `headline` has a coverage row reading 17.6 against nominal 80.0.

- [ ] **Step 5: Write `backend/evals/REPORT.md`**

Lead with what the numbers mean, not the numbers: the model is a factor-of-two estimator of a specific building's annual electricity from area, vintage and type alone, and **its stated 10–90 band does not know that** (17.6% coverage against a nominal 80%, with truth falling below the band 38% of the time and above it 44% — near-symmetric, so this is a sharpness failure and not a bias). Then the weather decomposition (electricity −1.0% median, heating need +24.8% median), the per-usage table (Lodging/residential is the worst at −83.4% median; Public services the best at −2.0% median, 26.5% median abs), and the storey diagnostic (61.7% median abs at 4+ floors vs 51.9% at 1). Close with the two actions it implies: widen `UNC-02` or stop calling the band a 10–90, and require bill calibration (`calibrate_model`, which already exists) before quoting a guarantee.

- [ ] **Step 6: Commit**

```bash
git add backend/evals/publish.py backend/evals/out/metered_buildings.json backend/evals/REPORT.md backend/evals/tests/test_publish.py
git commit -m "evals: publish the metered-building scorecard and report"
```

- [ ] **Step 7: Post to the board**

`CONTRACT-CHANGE:` candidate for @yalexie1: measured coverage of the `UNC-01` 10–90 band is 17.6% on 494 metered buildings, so either `UNC-02`'s quadrature needs widening or the band must stop being described as a 10–90 percentile. Include the near-symmetric bin split as the evidence that it is sharpness and not bias.

---

### Task 4: PV cross-check against PVGIS

Cheapest remaining eval: `ClimateSite` already carries `pvgis_annual_kwh_per_kw` (1676.75 for the golden office) and `backend/analysis/model/benchmark/pv.py` already implements `cross_check_pv`. This task measures and records, it does not build physics.

**On PVWatts:** #394 asks for "PV vs PVWatts/PVGIS", but `specs/physics.md` section 5 records that `developer.nrel.gov` and `nsrdb.nrel.gov` do not resolve from the team's environment, so PVWatts is not reachable as a dependency. Step 0 is to retry it once and record the outcome; if it still does not resolve, PVGIS carries this eval alone and the JSON says so in a `pvwatts_unavailable` field rather than leaving the judge to assume it was checked.

**Files:**
- Create: `backend/evals/run_pv.py`, `backend/evals/out/pv_crosscheck.json`
- Test: `backend/evals/tests/test_pv_eval.py`

**Interfaces:**
- Consumes: `backend.analysis.api` for the solar design, `backend.analysis.model.benchmark.pv.cross_check_pv`.
- Produces: `backend/evals/out/pv_crosscheck.json`: per property `{sid, system_kw_dc, annual_kwh, kwh_per_kw, pvgis_kwh_per_kw, pct_diff, mountingplace, verdict}`.

- [ ] **Step 1: Write the failing test**

```python
def test_pv_payload_records_mountingplace_and_pct_diff():
    row = pv_row(sid="ZSPaQbkGcJJ", annual_kwh=16767.5, system_kw_dc=10.0,
                 pvgis_kwh_per_kw=1676.75, mountingplace="free")
    assert row["kwh_per_kw"] == 1676.75
    assert row["pct_diff"] == 0.0
    assert row["mountingplace"] == "free"
```

The `mountingplace` field is mandatory because PVGIS `free` vs `building` moves `E_y` by 4–5% (1754 vs 1677 kWh/kWp at LA); a cross-check that does not record it is not reproducible.

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest backend/evals/tests/test_pv_eval.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.evals.run_pv`.

- [ ] **Step 3: Implement `pv_row(...) -> dict` and `main() -> int` in `backend/evals/run_pv.py`**

Run the golden properties through the existing solar design, compare `kwh_per_kw` against `ClimateSite.pvgis_annual_kwh_per_kw`, and band the verdict with `pv_tolerance` from `benchmark/pv.py` rather than a new threshold.

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest backend/evals/tests/test_pv_eval.py -v && python -m backend.evals.run_pv`
Expected: PASS; the JSON lists each golden property with a `pct_diff` and a verdict.

- [ ] **Step 5: Commit**

```bash
git add backend/evals/run_pv.py backend/evals/out/pv_crosscheck.json backend/evals/tests/test_pv_eval.py
git commit -m "evals: PV yield cross-check against PVGIS"
```

---

### Task 5: Installed-cost check against Tracking the Sun

**Files:**
- Create: `backend/evals/run_cost.py`, `backend/evals/manifests/tracking_the_sun.yaml`, `backend/evals/out/cost_check.json`
- Test: `backend/evals/tests/test_cost_eval.py`

**Interfaces:**
- Consumes: `COST-01` installed cost per measure from the analysis lane.
- Produces: `backend/evals/out/cost_check.json`: `{measure, our_usd_per_w, ttos_median_usd_per_w, ttos_p25, ttos_p75, state, size_band, year, verdict}`.

- [ ] **Step 1: Write the failing test**

```python
def test_cost_verdict_is_inside_when_within_the_ttos_iqr():
    assert cost_row(our=3.1, p25=2.8, median=3.2, p75=3.6)["verdict"] == "inside_iqr"
    assert cost_row(our=5.0, p25=2.8, median=3.2, p75=3.6)["verdict"] == "above_iqr"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest backend/evals/tests/test_cost_eval.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.evals.run_cost`.

- [ ] **Step 3: Implement `cost_row(...) -> dict` and `main() -> int` in `backend/evals/run_cost.py`**

Filter the Tracking the Sun public file to the matching state, size band and most recent year, take the p25/median/p75 of `$/W_dc`, and compare. Record the row count behind each percentile; a percentile from under 20 systems is reported as indicative.

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest backend/evals/tests/test_cost_eval.py -v && python -m backend.evals.run_cost`
Expected: PASS; the JSON carries a verdict and an `n` per band.

- [ ] **Step 5: Commit**

```bash
git add backend/evals/run_cost.py backend/evals/manifests/tracking_the_sun.yaml backend/evals/out/cost_check.json backend/evals/tests/test_cost_eval.py
git commit -m "evals: installed-cost check against LBNL Tracking the Sun"
```

---

### Task 6: OpenSolar spot check on 2–3 properties

Not automatable: OpenSolar is an external tool a human drives. This task produces the comparison record, not a scraper. **Never enter credentials into OpenSolar on the user's behalf** — @vigjay runs the tool and supplies the numbers.

**Files:**
- Create: `backend/evals/out/opensolar_spotcheck.json`, `backend/evals/OPENSOLAR.md`

**Interfaces:**
- Consumes: `backend/evals/out/pv_crosscheck.json` for our own figures.
- Produces: `backend/evals/out/opensolar_spotcheck.json`: per property `{sid, address, our_system_kw, our_annual_kwh, opensolar_system_kw, opensolar_annual_kwh, pct_diff_kwh, pct_diff_kw, operator, date, notes}`.

- [ ] **Step 1: Write `backend/evals/OPENSOLAR.md`**

The exact manual procedure: which 2–3 golden properties, what to enter, which OpenSolar output fields to read, and that the module count and tilt/azimuth must be recorded so a difference can be attributed to layout rather than to yield.

- [ ] **Step 2: Run the procedure and fill the JSON**

Hand-authored from the operator's readings, with `operator` and `date` set. A field that was not read stays `null` — never estimated.

- [ ] **Step 3: Commit**

```bash
git add backend/evals/out/opensolar_spotcheck.json backend/evals/OPENSOLAR.md
git commit -m "evals: OpenSolar spot check on the golden properties"
```

---

### Task 7: `Evals.tsx` — handoff GRANTED, with a writer boundary

@vinayak-sinha granted this on the board (#6888130524) and scoped it: @vigjay owns `Evals.tsx`, eval-specific styles and tests, and `frontend/public/evals.json`. **`App.tsx` and `HowItWorks.tsx` stay with @vinayak-sinha as single writer — do not edit them.** Send him the component export, its props, and the navigation label and he wires the links. His constraints carry into the component: 16px minimum type, plain-language explanations, real data with explicit unavailable states.

**Files:**
- Create: `frontend/src/Evals.tsx`, `frontend/src/Evals.test.tsx`, `frontend/public/evals.json`
- Modify: none. (`App.tsx` and `HowItWorks.tsx` are @vinayak-sinha's.)

**Interfaces:**
- Consumes: `frontend/public/evals.json`, which is the three `backend/evals/out/*.json` merged by a step in this task. The page renders only — **no arithmetic in the component.**
- Produces: `export default function Evals(): JSX.Element`, no props (it fetches `/evals.json` itself, so @vinayak-sinha's link needs no data wiring). Navigation label: **"Evals"**.

- [ ] **Step 1: Merge the eval JSONs into `frontend/public/evals.json`**

A step in `backend/evals/publish.py` writes it, so the page and the scorecard cannot drift. Any eval that has not run yet appears with `"status": "not_run"` — rendered as an explicit unavailable state, never omitted and never zero.

- [ ] **Step 2: Write the failing test**

```tsx
it("shows coverage against its nominal and never hides the caveats", () => {
  render(<Evals />);
  expect(screen.getByText(/17.6/)).toBeInTheDocument();
  expect(screen.getByText(/nominal 80/i)).toBeInTheDocument();
  expect(screen.getAllByRole("listitem", { name: /caveat/i }).length).toBeGreaterThan(4);
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/Evals.test.tsx`
Expected: FAIL — no `Evals.tsx`.

- [ ] **Step 4: Implement `Evals.tsx`**

Headline figures as cards, each showing value, nominal where one exists, CI and `n`. The caveat list renders **on the page, not behind a disclosure** — a reliability page that hides its limits is worse than no page. Per-usage and per-site tables below.

- [ ] **Step 5: Run the test and verify in the browser**

Run: `cd frontend && npx vitest run src/Evals.test.tsx`
Expected: PASS. Then start the dev server and screenshot `/evals`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/Evals.tsx frontend/src/Evals.test.tsx frontend/src/App.tsx frontend/src/HowItWorks.tsx
git commit -m "frontend: add the Evals page"
```

---

## Time budget

The lead's #394 budget is ~5 h with an hour-4 check-in. Tasks are ordered so that stopping at any boundary leaves something shippable.

| Task | Minutes | Cumulative | If the clock runs out here |
|---|---|---|---|
| 1 Relocate + scope | 25 | 0:25 | Result exists on `main` with its caveats recorded |
| 2 Scorer tests | 30 | 0:55 | The headline number is trustworthy |
| 3 Publish + report | 40 | 1:35 | **Minimum shippable: the eval is public and honest** |
| 6 OpenSolar | 40 | 2:15 | The two checks the lead asked for first are both in |
| 4 PV vs PVGIS | 35 | 2:50 | Two of three evals done |
| 5 Cost vs TtS | 40 | 3:30 | All three evals done |
| 7 Evals.tsx | 60 | 4:30 | Published on the site |

Execution order is **1, 2, 3, 6, 4, 5, 7** — not numerical. The #394 post says to ship the metered-building eval and the OpenSolar check first, so Task 6 runs before Tasks 4 and 5 despite its number; it also needs a human in the loop, which is another reason not to leave it to the last hour. Task 5 is the first thing to cut. Task 7 may be cut to a link to the raw JSON if the handoff does not arrive.

## Decision needed from @vigjay before Task 3

Publishing a measured 17.6% coverage against a nominal 80% is a strong credibility move and an obvious thing for a judge to quote. The alternative is to publish the error distribution and hold the coverage figure for internal use until `UNC-02` is widened. Recommendation: **publish it**, framed as the sharpness finding it is, because a team that measured its own overconfidence is more trustworthy than one that reports only accuracy. This is a presentation call, so it is the owner's, not the plan's.

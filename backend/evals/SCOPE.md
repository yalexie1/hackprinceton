# What the metered-building eval does and does not measure

Owner: @vigjay (issue #394). Written 2026-11-15.

**Location note.** The plan called this `specs/evals.md`, but AGENTS.md section 4
gives all of `specs/` to @yalexie1, so it lives in `backend/evals/`, which the lead
assigned to this lane. Promote it to `specs/evals.md` whenever @yalexie1 wants it
there; nothing here depends on the path.

## The one-sentence version

Against 494 buildings with metered 2017 electricity, Leto's annual electricity
prediction has a median absolute error of **55.5%**, and its stated 10–90 band
contains the metered total **17.6%** of the time against a nominal **80%**.

## This is a defaults-path eval, not an end-to-end one

This is the single most important thing to understand before quoting any number here.

Leto's production path starts from a Matterport scan: rooms, a wall graph, measured
openings, and Vexcel roof planes. **No public dataset of hundreds of metered buildings
carries scan geometry.** The Building Data Genome Project 2 gives four usable facts per
building — floor area, year built, primary space usage, and site — and hourly meters.

So each eval building is the golden office (or house) bundle with its plan scaled to
the building's floor area and its vintage and type set. Plan dimensions scale as the
square root of the area ratio, so floor area scales exactly and wall area scales as
√area, which is the right behaviour for a scaled plan.

What that means:

| Graded here | Not graded here |
|---|---|
| The 5R1C zone model (`ZON`) | Geometry extraction from a scan |
| The `DEF-01`…`DEF-13` default tables | Vision (`observe_interior`) |
| Envelope, infiltration, window gain (`ENV`, `INF`, `WIN`) | Daylight, glare, comfort (`DAY`, `GLR`, `CMF`) |
| HVAC, DHW, lighting and plug loads | PV, shading, roof geometry, layout (`PV`, `SHD`, `ROOF`, `LAY`) |
| The `UNC-02` uncertainty band | Cost, CO2, incentives (see below) |

**Geometry error is excluded by construction.** A real property gets its geometry from
a scan; these buildings get a scaled golden box. The error measured here is therefore a
*floor*, not a ceiling: it is what remains when the geometry is idealised and only area,
vintage and type are known. It is also the error that applies whenever a scan is thin and
the defaults do the work.

## Energy only: cost and CO2 are not scored

`PropertySummary.state` is `Literal["CA", "TX"]` in `backend/schema.py`, so every eval
building is labelled `CA` regardless of where it is. State feeds the eGRID subregion for
emissions, the tariff defaults, and the incentive registry. So the dollars and kilograms
are not validated here: **do not publish a cost or CO2 figure on the strength of this
eval.**

**Correction (2026-11-15).** An earlier version of this file said the forced `CA` label
"does not touch the energy physics". That is true of the `state` field itself and
**false in effect**, because of the climate zone that travels with it.
`backend/analysis/model/registry/tables.py` defines `CLIMATES = ("2A", "3B")`, and
`registry.py` silently blends or defaults anything else to `3B`. Our five sites are 3C
(Bear), 6A (Cockatoo), 2B (Fox), 4A (Rat) and 2A (Panther) — so only Panther's 96
buildings get their stated zone, and the other **398 of 494 run on a fallback table**.
Weather is still site-specific, so this does not touch the hourly temperatures or
irradiance; it means the DEF envelope and equipment defaults are drawn from the wrong
climate. Found by @vinayak-sinha's independent audit. Every run now records
`effective_climate_zone` and `zone_source` (`stated` / `unsupported_fallback`) per
building rather than implying the stated zone was honoured.

This Literal is also what limited the eval to five US sites: BDG2's UK and Canadian
sites cannot be represented at all. A wider Literal would let the eval cover more
climates — raised with @yalexie1 on the board as a `CONTRACT-CHANGE` candidate, not
yet agreed.

## The two weather arms

BDG2 ships measured site air temperature but **no irradiance**. So both arms take
GHI/DNI/DHI from the Open-Meteo archive, and they differ only in temperature:

- **`bdg2temp`** — BDG2's measured station temperature + Open-Meteo irradiance
- **`openmeteo`** — Open-Meteo temperature + the same Open-Meteo irradiance

The difference therefore isolates **temperature error only**. It says nothing about
irradiance error, and a reader who takes it as "the weather source is validated" has
over-read it.

## Caveats, verbatim from `score_eval.py`

These are generated into every scorecard and must not drift from this list:

- Truth is one annual total per building: this is a cross-sectional error distribution,
  not a Guideline 14 time-series fit.
- Weather is site-level across only 5 sites, so the effective N for the weather-driven
  error term is 5, not the building count. CIs are bootstrapped over sites and are wide.
- Every building is modelled as a single zone at a single storey scaled to its floor
  area, so a tall building's surface-to-volume ratio is wrong by construction.
- Non-office uses (Education, Lodging, Entertainment, Public services, Healthcare) are
  run on office or residential defaults; type mismatch is inside the reported error.
- 398 of 494 buildings sit in a climate zone the DEF tables do not carry and fall back
  to a 3B/2A blend; `zone_source` records which.
- 37% of the sample buys chilled water, steam or hot water from a district plant, so
  their electricity meter does not contain the cooling (or heating) our model predicts.
- Irradiance is Open-Meteo in BOTH arms (BDG2 ships none), so the arm difference
  isolates temperature error only, not irradiance error.

## Two further limits worth stating plainly

**Guideline 14 bands do not apply.** `MV-04` sets NMBE ±5% and CV(RMSE) ≤15% monthly.
Those are defined for a fit against 12 or 8,760 points of *one* building. Truth here is
one annual total per building, so the numbers are a cross-sectional spread across
buildings and the G14 thresholds are deliberately **not** quoted as pass/fail.

**Parking is excluded.** A parking structure is unconditioned and has no `DEF` path;
modelled as an office it came out +1650% on a smoke test. That is a scope error, not
model error, so those buildings are dropped rather than carried as error. Every other
use type is kept, and the per-usage table shows what the type mismatch costs.

## Reproducing it

```bash
python -m backend.evals.prep_weather   # 5 sites x 2 arms -> data/cache/evals/weather/
python -m backend.evals.run_eval 500   # ~0.97 s/building, ~8 min, 0 refused
python -m backend.evals.score_eval     # -> data/cache/evals/out/scorecard.json
python -m backend.evals.publish        # -> backend/evals/out/, frontend/public/evals.json
```

Inputs and checksums: `backend/evals/manifests/bdg2.yaml`. The sample is seeded
(`random_state=17`), stratified by site, and the pool is every BDG2 building at a US
site with electricity, floor area, year built and coordinates, at ≥90% metered-hour
completeness in 2017.

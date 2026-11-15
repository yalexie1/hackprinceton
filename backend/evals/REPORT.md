# How reliable are Leto's energy projections?

494 buildings with metered 2017 electricity, from the Building Data Genome Project 2.
Five US sites. Zero model refusals. Run on 2026-11-15.

Scope and limits: [SCOPE.md](SCOPE.md). Inputs and checksums:
[manifests/bdg2.yaml](manifests/bdg2.yaml). Reproduce in about eight minutes with
`python -m backend.evals.run_eval 500`.

## What the numbers say

**Leto is a factor-of-two estimator of a specific building's annual electricity when
all it knows is floor area, vintage and use type — and its stated uncertainty band does
not know that.**

| | Value | Nominal |
|---|---|---|
| Median absolute error | **55.5%** | — |
| Median signed error | −0.5% | 0% |
| Within ±25% | 23.5% of buildings | — |
| Off by 2× or more | 19.6% of buildings | — |
| **Interval coverage** | **17.6%** (90% CI 13.7–22.2) | **80%** |
| Band width | 41.4% of expected | — |

The median signed error is essentially zero while the median absolute error is 55.5%.
The model is not systematically high or low. It is **scattered**.

## The interval is the real finding

We publish every result as low / expected / high and call it a 10th-to-90th percentile
band (`UNC-01`). On 494 metered buildings that band contained the truth **17.6%** of the
time. It should have been 80%.

Where the metered total actually fell:

| Position | Share |
|---|---|
| Below our low | 38.1% |
| Between low and expected | 11.7% |
| Between expected and high | 5.9% |
| Above our high | 44.3% |

Truth falls outside on **both** sides in near-equal measure. That is the diagnostic: a
biased model would pile up on one side. This is a **sharpness failure** — the band is
simply far too narrow.

Two structural reasons, both predictable from how `UNC-02` builds the band. It perturbs
each uncertain input one at a time to its low and high and combines the swings in
quadrature, which (a) treats the inputs as independent when vintage, U-value and air
leakage in fact move together, and (b) never samples interaction terms in a nonlinear
model. Both make the band too tight.

**What follows:** either widen `UNC-02`, or stop describing the output as a 10–90
percentile band. Raised with @yalexie1 as a `CONTRACT-CHANGE` candidate.

## Weather: the bias is real, and it lands on heating

Open-Meteo's reanalysis temperatures against the measured station temperatures at the
same site, heating degree days base 65 °F, NOAA's (T_max+T_min)/2 method:

| Site | Reanalysis HDD65 | Measured HDD65 | Bias |
|---|---|---|---|
| Bear (Berkeley, CA) | 2,907 | 2,243 | **+29.6%** |
| Fox (Tempe, AZ) | 785 | 632 | **+24.2%** |
| Rat (Washington, DC) | 3,844 | 3,313 | +16.0% |
| Panther (Orlando, FL) | 313 | 277 | +13.0% |
| Cockatoo (Ithaca, NY) | 6,134 | 6,498 | −5.6% |

The cold bias is worst in mild and warm climates and reverses in a cold continental one.
This independently reproduces the Los Angeles finding already logged by the analysis lane
and generalises it.

But running both arms shows where it lands:

| | Median shift |
|---|---|
| Annual electricity | **−1.0%** |
| Heating need (thermal, pre-efficiency) | **+24.8%** |

A 25% error in heating need barely reaches the electricity meter, because these buildings
are dominated by cooling, lighting and plug loads. **Judge a weather source against the
end use it actually drives.** A gas or heating eval would expose this; an annual-electricity
eval on commercial buildings largely hides it.

## Where the error lives

By use type, worst and best (full table in `out/metered_buildings.json`):

| Use | n | Median signed | Median abs | Coverage |
|---|---|---|---|---|
| Lodging/residential | 73 | **−83.4%** | 83.4% | 6.8% |
| Retail | 6 | +72.9% | 84.7% | 0.0% |
| Entertainment/public assembly | 53 | +34.6% | 56.8% | 15.1% |
| Education | 234 | +21.6% | 52.4% | 20.9% |
| Office | 61 | +8.6% | 40.7% | 13.1% |
| Public services | 41 | +2.0% | **26.5%** | 26.8% |

Office — the only clean type match, since non-residential buildings are run on office
defaults — is among the best at 40.7% median absolute error. Lodging/residential is
badly biased low at −83.4%, which is the clearest single lead for improving the defaults.

By site, median absolute error ranges 36.3% (Rat) to 77.1% (Bear). Coverage is between
12.0% and 26.8% everywhere: no site is calibrated.

The single-storey simplification costs about ten points: buildings of four or more
storeys show 61.7% median absolute error against 51.9% for single-storey ones. Real,
but not the main term.

## What this does and does not license us to say

**Can say:** that we measured ourselves against 494 real meters; that our expected value
is unbiased in the median and scattered by about 55%; that our uncertainty band is
overconfident by a factor of roughly four and we know by how much; that we can attribute
part of the error to the weather source and part to the single-zone geometry.

**Cannot say:** anything about cost or CO2 accuracy (not scored — the contract forces
every eval building to `CA`); anything about geometry, daylight or PV (excluded by
construction); or that this predicts performance on a scanned property, which has far
better inputs than area-and-vintage.

**The honest framing for a customer:** without a scan or a utility bill, treat a Leto
projection as an order-of-magnitude screen, not a guarantee. With bills, calibrate —
`calibrate_model` implements ASHRAE Guideline 14 Option D and exists today. The retrofit
literature puts realised savings at 25–85% of engineering projections (mean ~58%), and
nothing measured here contradicts that.

## Next

1. Re-run coverage after widening `UNC-02`, and report the before and after.
2. Run the same eval with `calibrate_model` on twelve monthly bills. The expectation is
   that coverage climbs sharply; if it does not, the band is wrong independently of the
   inputs.
3. Extend beyond five sites once `PropertySummary.state` admits more than `CA` and `TX`
   — five weather clusters is the binding limit on every interval here, not 494 buildings.

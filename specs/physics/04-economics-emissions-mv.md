# Physics spec part 4: economics, tariffs, emissions, incentives, costs, M&V, uncertainty, value uplift

Status: draft, sources checked 2026-11-13 and 2026-11-14. Owner: @yalexie1 (Analysis lane, finance package).

Sections (each marked when written):

1. ECO  Life-cycle economics: written
2. TAR  Energy cost and unit conversions: written
3. EMI  Emissions: written
4. INC  Incentive registry: written (federal entries verified in the statute; several utility amounts unverified, listed in section 9)
5. COST Measure cost data and useful life: written (three measures have no verified cost; most useful lives are placeholders, listed in section 9)
6. MV   Measurement and verification: written
7. UNC  Uncertainty propagation: written
8. VAL  Value uplift: written for capitalised savings and home solar; the rent module VAL-02 is a stub
9. Unverified, do not use: written
10. Verification log: written
11. Changes needed in `specs/SPEC.md`: written

## 0. Conventions for this file

- **Tags.** [V] = read in the primary source on the date given. [U] = not opened in primary form; do not build on it. [J] = a project judgement, not a published value; it is always labelled and can be changed in `backend/config.py`.
- **Money.** All amounts are constant US dollars of the base date (the day the analysis runs). Rates are real (net of general inflation) unless the symbol is a capital letter (D, I, E), which is nominal. This is the constant-dollar method of NIST Handbook 135, section 3.3.
- **Timing.** t = 0 is the base date, and the investment is paid at t = 0. Savings and recurring costs fall at the end of years 1..N. There is no planning or construction period (service date = base date).
- **Energy.** kWh for electricity; gas is carried in kWh of higher heating value in the contract (`EnergyUse.gas_kwh`) and converted with TAR-05.
- **Ranges.** Every reported quantity is a `Ranged` (low, expected, high). How the three numbers are produced is fixed in UNC-01 to UNC-03. Formulas below are written for a single set of inputs.
- **Worked examples.** Every example was computed twice by independent means (closed form against a year-by-year loop, or against `numpy-financial` 1.0.0, or against a value printed in the source). The method used is in the verification log, section 10.
- **No network at run time.** Every table in this file (discount factors, price indices, emission factors, incentives, costs) is a static data file checked into `backend/analysis/data/` with its source and retrieval date. Nothing here calls a web API when the product runs. In particular no NREL web service is a dependency: the `nrel.gov` hosts did not resolve during this work (NREL documents were reachable only at `docs.nlr.gov`).
- **Tool names.** Each entry names the Python function it maps to (suggested module `backend/analysis/finance.py`, `tariff.py`, `emissions.py`, `mv.py`, `uncertainty.py`).

Primary references used throughout this file:

| Short name | Full reference | Opened |
|---|---|---|
| HB135 | Kneifel, J. and Webb, D., *Life Cycle Costing Manual for the Federal Energy Management Program*, NIST Handbook 135, 2025 edition, August 2025. https://nvlpubs.nist.gov/nistpubs/hb/2025/NIST.HB.135e2025.pdf (doi:10.6028/NIST.HB.135e2025) | 2026-11-14, PDF, 302 pages |
| AS135-2025 | Kneifel, J., Parekh, P. and Lavappa, P., *Energy Price Indices and Discount Factors for Life-Cycle Cost Analysis, 2025, Annual Supplement to NIST Handbook 135*, NIST IR 85-3273-40, August 2025. https://nvlpubs.nist.gov/nistpubs/ir/2025/NIST.IR.85-3273-40.pdf (doi:10.6028/NIST.IR.85-3273-40). Data tables: doi:10.18434/mds2-3848, file `NISTIR85-3273-40 - V2.xlsx` | 2026-11-14, PDF and spreadsheet |
| 10 CFR 436A | Code of Federal Regulations, title 10, part 436, subpart A, "Methodology and Procedures for Life Cycle Cost Analyses", eCFR version in force 2026-11-01. https://www.ecfr.gov/current/title-10/part-436/subpart-A | 2026-11-14, eCFR XML |

Currency of the supplement: the FEMP page https://www.energy.gov/cmei/femp/building-life-cycle-cost-programs still listed the 2025 edition as the latest when fetched on 2026-11-13, and `NIST.IR.85-3273-41.pdf` returned HTTP 404. AS135-2025 states it "is intended for use until the publication of the 2026 edition". Re-check before the demo; if a 2026 edition exists, re-run ECO-05 and ECO-06 from its tables.

---

## 1. ECO: life-cycle economics

### ECO-01 Real and nominal rates

```
d = (1 + D) / (1 + I) - 1          D = (1 + I)(1 + d) - 1
e = (1 + E) / (1 + I) - 1
```

| Symbol | Meaning | Unit |
|---|---|---|
| d, D | real and nominal discount rate | 1/yr (fraction) |
| I | general inflation rate | 1/yr |
| e, E | real and nominal price escalation rate of an energy or cost stream | 1/yr |

- Validity: any rates greater than -1. Never mix: real rates with constant dollars, nominal rates with current dollars. Subtracting I from D is only an approximation.
- Primary: HB135 section 3.1.2, equations 3-9 and 3-11 [V 2026-11-14].
- Second source: 10 CFR 436.14(a)(2) (the real rate is the nominal Treasury yield "adjusted to exclude estimated increases in the general level of prices") [V]; AS135-2025 page 1 gives the consistent triple real 3.0 %, nominal 4.5 %, implied inflation 1.5 % [V].
- Example: D = 0.07, I = 0.04 gives d = 1.07/1.04 - 1 = 0.02885 (HB135 equation 3-10 prints 0.02885). d = 0.03, I = 0.04 gives D = 0.0712 (HB135 equation 3-12 prints 0.0712). DOE 2025: 1.045/1.03 - 1 = 0.01456, published as 1.5 %.
- Tool: `real_rate(nominal: float, inflation: float) -> float`; `nominal_rate(real: float, inflation: float) -> float`. Rates as fractions per year.

### ECO-02 Single present value factor (SPV)

```
PV = F_t * SPV(d, t)        SPV(d, t) = 1 / (1 + d)^t
```

| Symbol | Meaning | Unit |
|---|---|---|
| F_t | one amount at the end of year t, in base-date dollars | USD |
| t | years from the base date | yr (may be fractional) |
| PV | present value | USD |

- Validity: d > -1, t >= 0.
- Primary: HB135 section 3.2.1, equations 3-5 and 3-6 [V].
- Second source: AS135-2025 data table "Indices - Non-Energy", Table 1, SPV at 3 % for 1 year = 0.9709, 2 years = 0.9426 [V]; 10 CFR 436.16(d) ("single present worth factors") [V].
- Example: F = 1000 USD at t = 5, d = 0.03: PV = 1000 / 1.03^5 = 862.61 USD (HB135 prints $862.61).
- Tool: `spv(d: float, t: float) -> float`.

### ECO-03 Uniform present value factor (UPV)

```
PV = A * UPV(d, N)          UPV(d, N) = ((1 + d)^N - 1) / (d (1 + d)^N)     for d != 0
                            UPV(0, N) = N
```

| Symbol | Meaning | Unit |
|---|---|---|
| A | the same amount at the end of each of years 1..N | USD/yr |
| N | number of years | yr (integer) |

- Validity: d > -1, N >= 0 integer. Use the d = 0 branch when |d| < 1e-12.
- Primary: HB135 section 3.2.2.1, equation 3-7 [V].
- Second source: AS135-2025 data table "Indices - Non-Energy", Table 2, UPV at 3 % for 5 years = 4.5797 [V].
- Example: A = 100 USD/yr, N = 5, d = 0.03: PV = 100 * 4.5797 = 457.97 USD (HB135 prints $457.97). UPV(0.03, 15) = 11.938, UPV(0.03, 20) = 14.877, UPV(0.03, 25) = 17.413 (HB135 section 4.5.3 prints 11.938 and 17.413).
- Tool: `upv(d: float, n: int) -> float`.

### ECO-04 Modified uniform present value factor (UPV*), constant escalation

```
PV = A_0 * UPV*(e, d, N)
UPV*(e, d, N) = sum_{t=1..N} ((1 + e) / (1 + d))^t
              = (1 + e) / (d - e) * (1 - ((1 + e) / (1 + d))^N)     for d != e
              = N                                                     for d = e
```

| Symbol | Meaning | Unit |
|---|---|---|
| A_0 | the annual amount priced at the base date; the year-t amount is A_0 (1 + e)^t | USD/yr |
| e | constant real escalation rate of this stream | 1/yr |

- Validity: d > -1, e > -1. The closed form is singular at d = e; use the N branch when |d - e| < 1e-12. With e = 0 it reduces to ECO-03.
- Convention warning [V]: in this formula the first-year amount is A_0 (1 + e), one year of escalation after the base date (HB135: "the annual amount is specified at the price level of the base date"). The pre-computed energy factors in the AS135-2025 spreadsheet ("UPV - DOE") instead price year 1 at the base-year index of 1.0 (first factor 0.970874 = 1/1.03 for every fuel). This spec uses the HB135 formula with our own equivalent rate (ECO-06), and does not read factors from that sheet.
- Primary: HB135 section 3.2.2.2, equation 3-8 [V].
- Second source: HB135 cites Table A-3a of the Annual Supplement: UPV* for 5 years, 3 % discount, 2 % escalation = 4.86 [V as quoted in HB135].
- Example: A_0 = 100 USD/yr, e = 0.02, d = 0.03, N = 5: UPV* = 1.02/0.01 * (1 - (1.02/1.03)^5) = 4.8562, PV = 485.62 USD (HB135 prints $485.62). Loop sum gives 485.6240.
- Tool: `upv_star(e: float, d: float, n: int) -> float`.

### ECO-05 Default economic parameters

| Parameter | Contract field | Default | Source and date |
|---|---|---|---|
| Real discount rate d | `FinancialBreakdown.discount_rate` | 0.030 | DOE/FEMP rate for 2025, AS135-2025 page 1 (August 2025): "Real rate (excluding general price inflation): 3.0 %". It is the regulatory floor: 10 CFR 436.14(a)(2), "a ceiling of 10 percent and a floor of three percent". The market-derived value for 2025 was 2.2 % [V 2026-11-14] |
| Nominal discount rate D | not in contract; used only for nominal debt (ECO-12) | 0.045 | AS135-2025 page 1 [V] |
| General inflation I | not in contract | 0.0146 (= 1.045/1.03 - 1; published as 1.5 %) | AS135-2025 page 1, "Implied long-term average rate of inflation: 1.5 %" [V] |
| Analysis period N | `analysis_period_years` | `min(useful_life_years, 40)`, integer | 10 CFR 436.14(d)(1): "the study period is the expected life of the retrofit, or 40 years from the beginning of beneficial use, whichever is shorter" [V]. Useful lives: COST-02 |
| Real energy escalation e_elec, e_gas | `electricity_escalation`, `gas_escalation` | ECO-06 table, by city, sector and N | AS135-2025 data tables (EIA Annual Energy Outlook 2025 reference case) [V] |
| Real escalation of O&M and replacement costs | not in contract | 0.0 | HB135 section 3.2.2.2: non-energy prices "change at approximately the rate of general inflation, so that in a constant dollar analysis the real escalation rate is zero" [V] |
| Sensitivity discount rate (reported beside the default, never used for ranking) | not in contract; put in `notes` | 0.07 | OMB Circular A-94 (29 October 1992), section 8.b.1: "a real discount rate of 7 percent. This rate approximates the marginal pretax rate of return on an average investment in the private sector". Reinstated by OMB Memorandum M-25-23, 8 April 2025, which revoked the November 2023 revision [V both, 2026-11-14] |

Notes that the code and the user interface must carry:

1. The 3 % rate is a federal government rate. A private owner's required return is usually higher. `discount_rate` is user-editable; the plan also shows NPV at 7 % as a sensitivity line. Ranking (SPEC 6.5) does not depend on the discount rate.
2. The discount rate is a policy parameter, not an uncertain measurement. It is held fixed inside UNC-01 and is not one of the varied inputs.
3. Second source for the 3 % value: the "DiscountRateMemo" sheet of the AS135-2025 spreadsheet lists "DOE Real Discount Rate 0.03, Nominal Discount Rate 0.045, Implied Long-term Inflation Rate 0.015, Calculated Real Discount Rate 0.022" [V].

- Tool: `economic_defaults(city: Literal["los_angeles","houston"], sector: Literal["residential","commercial"], useful_life_years: int) -> EconomicParams` with fields `discount_rate`, `nominal_discount_rate`, `inflation`, `analysis_period_years`, `electricity_escalation: Ranged`, `gas_escalation: Ranged`, `source: str`.

### ECO-06 Energy price escalation: equivalent constant real rate

AS135-2025 publishes a real price index I_y for each calendar year y, census division, sector and fuel (sheet "Indices - Real", base 2025 = 1). The contract carries one escalation number per fuel, so the year-by-year index is replaced by the constant rate that gives the same present value of a level stream over the analysis period:

```
target(N) = sum_{t=1..N} (I_{y0+t} / I_{y0}) / (1 + d)^t
e_eq(N)   = the root e of   UPV*(e, d, N) = target(N)
```

| Symbol | Meaning | Unit |
|---|---|---|
| y0 | base year of the analysis (2026) | calendar year |
| I_y | AS135-2025 real price index for year y | dimensionless |
| e_eq | equivalent constant real escalation rate | 1/yr |

- Validity: N from 1 to 30 with the 2025 tables (indices run to 2058; EIA projections end in 2050 and NIST extrapolates beyond). Root is unique because UPV* is strictly increasing in e; solve by bisection or Brent on [-0.2, 0.2].
- Mapping [V]: California is in census division "Pacific"; Texas is in "West South Central" (sheet "State by Census Division").
- Primary: AS135-2025 data tables, doi:10.18434/mds2-3848, sheet "Indices - Real (Table E and Ca)" [V 2026-11-14]. The equivalence itself is this spec's construction from HB135 equation 3-8.
- Second source: NIST's Energy Escalation Rate Calculator (https://pages.nist.gov/eerc/) computes "a compound annual average rate of escalation for a specified time period" from the same projections (described in AS135-2025, preface item 4) [V description only; the calculator was not run].

Expected values, base year 2026, d = 0.03 (percent per year, real):

| Division (city) | Sector | Fuel | N=10 | N=15 | N=20 | N=25 | N=30 |
|---|---|---|---|---|---|---|---|
| Pacific (Los Angeles) | Residential | Electricity | -1.08 | -0.62 | -0.36 | -0.18 | -0.05 |
| Pacific (Los Angeles) | Residential | Natural gas | -1.74 | -1.08 | -0.70 | -0.47 | -0.33 |
| Pacific (Los Angeles) | Commercial | Electricity | -1.59 | -1.16 | -0.92 | -0.75 | -0.62 |
| Pacific (Los Angeles) | Commercial | Natural gas | -1.24 | -0.76 | -0.48 | -0.32 | -0.23 |
| West South Central (Houston) | Residential | Electricity | 0.31 | 0.10 | 0.08 | 0.13 | 0.14 |
| West South Central (Houston) | Residential | Natural gas | 0.34 | 0.50 | 0.55 | 0.56 | 0.55 |
| West South Central (Houston) | Commercial | Electricity | 0.55 | 0.22 | 0.17 | 0.21 | 0.22 |
| West South Central (Houston) | Commercial | Natural gas | 1.33 | 1.26 | 1.18 | 1.09 | 0.99 |

Rules:

1. For an analysis period between two columns, call the function with the actual N (the table is for checking, not for interpolation).
2. Range [J]: low = expected - 1.0 percentage point, high = expected + 1.0 percentage point. The published source gives one reference projection and no band; the width is a project judgement and is flagged as such in the output.
3. The EIA reference case projects falling real prices in the Pacific division in the late 2020s (index 2027/2026 = 0.918 for residential electricity). This is the published projection, it lowers Los Angeles savings, and it is used as is. A user who has a utility rate forecast may override it (10 CFR 436.14(b)(1) allows supplier escalation rates when supplier prices are used).
4. Export compensation (TAR-03) is escalated at the electricity rate unless the tariff fixes it by contract.

- Example: West South Central, commercial, electricity, N = 20. target(20) = 15.1265; solving UPV*(e, 0.03, 20) = 15.1265 gives e_eq = 0.0017 (0.17 %/yr). Check: UPV*(0.0017, 0.03, 20) = 15.13. Computed with `scipy.optimize.brentq` and with an independent 100-step bisection on the loop sum; the two agree to 1e-9 for all 40 table cells.
- Tool: `equivalent_escalation_rate(index_by_year: dict[int, float], base_year: int, d: float, n: int) -> float`; `default_escalation(city, sector, fuel, n) -> Ranged`.

### ECO-07 Net present value of a measure (net savings)

```
NPV = PV_S - PV_I

PV_S = S_e0 * UPV*(e_elec, d, N) + S_g0 * UPV*(e_gas, d, N) + S_x0 * UPV*(e_exp, d, N) + dOM * UPV(d, N)
PV_I = I_0 + sum_k R_k * SPV(d, t_k) - RV_N * SPV(d, N) - sum_j C_j * SPV(d, t_j)
```

General form (always valid, used as the cross-check in code): `NPV = sum_{t=0..N} CF_t / (1 + d)^t` with CF_0 = -I_0 and CF_t = S_t + dOM - R_t + C_t (+ RV_N at t = N).

| Symbol | Meaning | Unit |
|---|---|---|
| S_e0, S_g0 | first-year electricity and gas bill savings at base-date prices, from TAR-01 (baseline bill minus post-measure bill); a negative value is a penalty | USD/yr |
| S_x0 | first-year export compensation at base-date prices (rooftop solar only), TAR-03 | USD/yr |
| dOM | annual operation, maintenance and repair saving (baseline minus measure; negative if the measure costs more to maintain). `annual_om_change_usd` in the contract is the cost change, so dOM = -annual_om_change_usd | USD/yr |
| I_0 | net investment at t = 0: installed cost minus upfront rebates (`net_upfront_usd`) | USD |
| R_k, t_k | replacement cost k and the year it falls (ECO-08) | USD, yr |
| RV_N | residual value at the end of year N (ECO-08) | USD |
| C_j, t_j | tax credit or other incentive received later than t = 0 (ECO-13) | USD, yr |
| NPV | net present value; HB135 calls it net savings (NS) | USD |

- Validity: constant-dollar analysis, end-of-year cash flows, savings constant in energy terms over the period. If a measure's output degrades (PV modules), put the degradation into the stream by replacing e with (1 + e)(1 - g) - 1, where g is the annual degradation fraction from the solar spec.
- Decision rule: cost-effective if NPV > 0 (10 CFR 436.18(c)(2): "Net savings ... are estimated to be positive").
- Primary: HB135 section 6.1, equations 6-1 and 6-2 [V].
- Second source: 10 CFR 436.19 and 436.20 [V]. ASTM E917 (life-cycle costs) and E1074 (net benefits and net savings) are named in HB135 section 1 as consistent standards; the ASTM texts are paywalled and were not opened [U for anything beyond title].
- Example A (used again in ECO-09 to ECO-11): I_0 = 10 000 USD, S_e0 = 1 500 USD/yr, e_elec = -0.005, dOM = +100 USD/yr, d = 0.03, N = 15, no gas, no replacement, no residual.
  UPV*(-0.005, 0.03, 15) = 11.5030; UPV(0.03, 15) = 11.9379.
  PV_S = 1 500 * 11.5030 + 100 * 11.9379 = 18 448.32 USD. NPV = 18 448.32 - 10 000 = **8 448.32 USD**.
  Year-by-year loop: 8 448.32. `numpy_financial.npv(0.03, cashflows)`: 8 448.32.
- Tool: `npv_measure(net_upfront_usd, savings_elec_usd, savings_gas_usd, export_usd, om_saving_usd, d, e_elec, e_gas, e_export, n, replacements: list[tuple[int, float]] = [], residual_usd = 0.0, later_incentives: list[tuple[int, float]] = []) -> float` (USD). Also `cashflows(...) -> list[float]` of length N + 1 for the general form.

### ECO-08 Replacement cost and residual value

```
replacement at year t_k:        PV = R_k * SPV(d, t_k)
residual value (linear):        RV_N = I_gross * (L - N) / L      for L > N,   else 0
```

| Symbol | Meaning | Unit |
|---|---|---|
| R_k | cost of replacing a component during the period, base-date dollars | USD |
| I_gross | installed cost before incentives | USD |
| L | useful life of the measure (COST-02) | yr |
| RV_N | value of the remaining life at the end of the analysis period | USD |

- Validity: with the ECO-05 default N = min(L, 40), RV_N is zero unless L > 40, and no whole-measure replacement occurs. Component replacements inside the life (a PV inverter, see COST-02) are entered explicitly. Linear proration is the simplest of the options HB135 lists; it ignores market value.
- Primary: HB135 section 4.5.3 ("residual value ... by linearly prorating (depreciation) its initial cost") [V]; 10 CFR 436.11 definition of salvage value and 436.19(a) and (c) [V].
- Second source: HB135 gives a second method in the same section (present value of savings after the period, A_0 * (UPV_L - UPV_N)); the two bracket the estimate [V].
- Example 1 (HB135's own): I_gross = 30 000 USD, L = 25, N = 15, d = 0.03. RV = 30 000 * 10/25 = 12 000 USD; PV = 12 000 / 1.03^15 = 7 702 USD (HB135 prints $7702). Alternative method with 1 200 USD/yr: 1 200 * (17.413 - 11.938) = 6 570 USD (HB135 prints $6570).
- Example 2 (replacement plus residual, example B): I_0 = 30 000 USD, L = 25, N = 20, savings 2 400 USD/yr, e = 0, d = 0.03, inverter replacement 3 000 USD at year 13. PV_S = 2 400 * 14.8775 = 35 705.94. PV of replacement = 3 000 * 0.68095 = 2 042.85. RV = 30 000 * 5/25 = 6 000; PV = 6 000 * 0.55368 = 3 322.05. PV_I = 30 000 + 2 042.85 - 3 322.05 = 28 720.80. NPV = **6 985.14 USD**; `numpy_financial.npv` on the cash-flow list: 6 985.14. SIR = 35 705.94 / 28 720.80 = 1.243.
- Tool: `residual_value_linear(installed_cost_usd, useful_life_years, n) -> float` (USD at year N, undiscounted).

### ECO-09 Savings-to-investment ratio (SIR)

```
SIR = PV_S / PV_I            (PV_S and PV_I exactly as in ECO-07)
```

- Unit: dimensionless. Returns `None` when PV_I <= 0 (a measure with no net investment has no meaningful ratio).
- Decision rule: cost-effective if SIR > 1 (10 CFR 436.18(c)(3)). SIR > 1 if and only if NPV > 0.
- Primary: HB135 section 6.2, equations 6-3 and 6-4 [V].
- Second source: 10 CFR 436.21 ("the ratio of the present value savings to the present value costs ... The denominator ... is the present value of the net increase in investment and replacement costs less salvage value") [V]. ASTM E964 named in HB135; not opened [U beyond title].
- Example A: SIR = 18 448.32 / 10 000 = **1.845**. HB135's own example 5-1: 71 043 / 27 240 = 2.61 (reproduced: 2.608).
- Tool: `sir(pv_savings_usd, pv_investment_usd) -> Optional[float]`.

### ECO-10 Rates of return: AIRR and IRR

```
AIRR = (1 + r) * SIR^(1/N) - 1                         r = reinvestment rate = d
IRR  = the rate i for which  sum_{t=0..N} CF_t / (1 + i)^t = 0
```

| Symbol | Meaning | Unit |
|---|---|---|
| AIRR | adjusted internal rate of return (interim savings reinvested at r) | 1/yr, real |
| IRR | internal rate of return of the cash-flow list of ECO-07 | 1/yr, real |

- Validity of AIRR: SIR > 0 and PV_I > 0.
- Validity of IRR: report it only when the cash-flow list changes sign exactly once (one negative outlay followed by non-negative net flows). With a later replacement that makes a year negative, more than one root can exist; then return `None` and report AIRR. Solve by bracketing on [-0.99, 10]; if NPV at 0 % is not positive (undiscounted savings do not repay the cost), IRR is negative or absent and `None` is returned.
- Which goes in the contract field `irr`: the conventional IRR when it is unique, since that is what owners expect; AIRR is added to the measure's notes. HB135 states why AIRR is the safer measure: IRR "implicitly assumes that interim proceeds (savings) will be reinvested at the calculated rate of return", which overstates the yield.
- Both are real rates here (constant dollars). To quote a nominal figure use ECO-01.
- Primary: HB135 section 6.3, equation 6-6 and the text on IRR [V].
- Second source: 10 CFR 436.22 (AIRR as "subtracting 1 from the nth root of the ratio of the terminal value of savings to the present value of costs") [V]; ASTM E1057 named in HB135, not opened [U beyond title].
- Example A: AIRR = 1.03 * 1.84483^(1/15) - 1 = **0.0729**. Independent check by the 10 CFR 436.22 definition (terminal value of savings compounded at 3 %, divided by 10 000, 15th root): 0.0729. `numpy_financial.mirr(cashflows, 0.03, 0.03)`: 0.0729.
  IRR by Brent's method: **0.1312**; `numpy_financial.irr`: 0.1312.
  HB135's own AIRR example: 1.03 * 2.61^(1/20) - 1 = 0.0806 (reproduced: 0.0806).
- Tool: `airr(sir: float, d: float, n: int) -> float`; `irr(cashflows: list[float]) -> Optional[float]`.

### ECO-11 Simple and discounted payback

```
simple (screening) form:   SPB = I_0 / (S_0 + dOM)        S_0 = S_e0 + S_g0 + S_x0
general form:              payback = the smallest y with   sum_{t=1..y} CF_t / (1 + d)^t >= I_0
                           d = 0 gives simple payback, d = discount rate gives discounted payback
fractional year:           y - 1 + (I_0 - cum_{y-1}) / (CF_y / (1 + d)^y)
```

- Units: years. `simple_payback_years` (a `Ranged`) uses the screening form, so that it can be recomputed by hand from the two numbers shown to the user. `discounted_payback_years` uses the general form with escalation, O&M and replacements, with the fractional-year interpolation.
- Returns `None` when S_0 + dOM <= 0 (simple) or when the cumulative discounted sum never reaches I_0 within N years (discounted). Payback of 0 when I_0 <= 0.
- After the payback year is found, the code checks that a later replacement does not take the cumulative sum back below I_0 (HB135 section 6.4.2); if it does, the later crossing is reported.
- Validity: the screening form assumes level savings and no later one-time costs (HB135 section 6.4.4). HB135 notes that fractional precision is not really supported by the data; the fraction is kept only so that ranges are smooth.
- Primary: HB135 section 6.4, equations 6-11 to 6-13 [V].
- Second source: 10 CFR 436.23 ("the number of years required for the cumulative value of energy or water cost savings less future non-fuel or non-water costs to equal the investment costs ... without consideration of discount rates") [V]; ASTM E1121 named in HB135, not opened [U beyond title].
- Example A: screening SPB = 10 000 / (1 500 + 100) = **6.25 yr**. General form: undiscounted cumulative sum is 9 443.81 after year 6 and 10 992.09 after year 7, so simple payback falls in year 7 (interpolated 6.36). Discounted cumulative sum is 9 788.83 after year 7 and 11 005.34 after year 8, so discounted payback falls in **year 8** (interpolated **7.17 yr**). Loop and `numpy.cumsum` agree.
  Reproduction of HB135 Table 6-3 (27 000 USD investment, 6 000 USD/yr savings times the printed index, -1 000 USD/yr O&M, 3 %): cumulative 28 440 undiscounted at year 6 and 29 603 discounted at year 7, so SPB in year 6 and DPB in year 7, as printed. Screening form: 27 000 / 5 000 = 5.4, as printed in equation 6-14.
- Tool: `simple_payback(net_upfront_usd, first_year_net_savings_usd) -> Optional[float]`; `discounted_payback(cashflows: list[float], d: float) -> Optional[float]`.

### ECO-12 Level payment on an assessment or loan (C-PACE scenario) and first-year net cash flow

```
A      = P * i (1 + i)^n / ((1 + i)^n - 1)        for i > 0;     A = P / n  for i = 0
m payments per year:   A_m = P * (i/m) (1 + i/m)^(n m) / ((1 + i/m)^(n m) - 1),   annual total = m * A_m
NCF_1  = S_0 + dOM - A
SDR    = (S_0 + dOM) / A
PV of the payments in the constant-dollar NPV:   PV_A = A * UPV(D, n)       (D nominal, ECO-05)
NPV_financed = PV_S - (I_0 - P) - PV_A - other PV_I terms of ECO-07
```

| Symbol | Meaning | Unit |
|---|---|---|
| P | amount financed (`financed_usd`) | USD |
| i | annual interest rate of the assessment or loan (`rate`), nominal, fixed | 1/yr |
| n | term (`term_years`), integer, n <= useful life | yr |
| A | level annual payment (`annual_payment_usd`) | USD/yr |
| NCF_1 | first-year net cash flow (`net_cashflow_year1_usd`), at base-date prices | USD/yr |
| SDR | savings-to-debt-service ratio (put in `notes`) | dimensionless |

- Validity: fully amortising, fixed rate, level payments in arrears. Fees and capitalised interest, if any, must already be inside P. The payment is fixed in nominal dollars, so its present value in a constant-dollar analysis is taken at the nominal rate D (equivalently, deflate each payment by (1 + I)^t and discount at d). NCF_1 uses S_0 at base-date prices with no escalation, which is the number a lender or owner can check against the first bill.
- The rate i and the term are inputs (market quotes), not defaults from a publication. The statutory conditions on term, eligible costs and lender consent are in `specs/legal/california.md` and `specs/legal/texas.md`; this entry is only the arithmetic.
- Primary: HB135 section 9.1, equation 9-1, uniform capital recovery factor UCR = d (1 + d)^N / ((1 + d)^N - 1), "the inverse of the UPV factor"; printed check value 0.0672 for 20 years at 3 % [V].
- Second source: `numpy_financial.pmt` (independent implementation of the same annuity identity); amortisation loop ending at a zero balance.
- Example: P = 100 000 USD, i = 0.07, n = 20. A = 100 000 * 0.07 * 1.07^20 / (1.07^20 - 1) = **9 439.29 USD/yr**; `numpy_financial.pmt(0.07, 20, 100000)` = -9 439.29; a 20-step amortisation loop ends at balance 0.00. Total paid 188 785.85 USD, of which interest 88 785.85 USD. With S_0 = 12 000 USD/yr and dOM = -500 USD/yr: NCF_1 = 12 000 - 500 - 9 439.29 = **2 060.71 USD/yr**, SDR = 1.218. PV of the payments at D = 0.045: 9 439.29 * UPV(0.045, 20) = 122 785.72 USD (the deflate-then-discount loop gives the same). Semi-annual version: 4 682.73 USD per half year. UCR(0.03, 20) = 0.06722 = 1 / 14.8775 (HB135 prints 0.0672).
- Tool: `level_payment(principal_usd, rate, term_years, payments_per_year=1) -> float` (USD per payment); `financing_scenario(kind, net_upfront_usd, first_year_net_savings_usd: Ranged, rate, term_years, useful_life_years) -> FinancingScenario`. For `kind="cash"`: financed 0, payment 0, NCF_1 = S_0 + dOM (the investment itself is shown as `net_upfront_usd`, not netted into year 1).

### ECO-12b Program SIR for a Texas PACE assessment (not the same as ECO-09)

Two different ratios carry the name "SIR". They must never be shown under one label.

```
life-cycle SIR (ECO-09, NIST and 10 CFR 436.21):   SIR = PV_S / PV_I                          discounted at d
program SIR (Texas PACE Authority screen):          SIR_prog = sum_{t=1..n} (S_t + dOM_t) / C_total      not discounted
C_total = n * A + (I_0 - P)                          all assessment payments over the term (principal, interest and
                                                     any financed fees) plus any part of the project paid in cash
pass if SIR_prog >= 1.0;  warn if 1.0 <= SIR_prog < 1.05
```

| Symbol | Meaning | Unit |
|---|---|---|
| S_t + dOM_t | projected savings in year t of the assessment term; default S_t = S_0 (no escalation), which is the cautious choice | USD/yr |
| n, A, P, I_0 | term, level annual payment, financed amount and project cost, as in ECO-12 | yr, USD/yr, USD, USD |
| SIR_prog | program savings-to-investment ratio (`FinancingScenario.program_sir`, being added to the contract) | dimensionless |

- Source of the rule: `specs/legal/texas.md` section 6, which quotes the Texas PACE Authority *Program Guide*, version 4.3, pages 16 and 30 to 32 ("sum of savings over the life of assessment versus sum of investment over the life of assessment"; "SIR >= 1"). This file takes the rule from the legal spec; the guide and its "PACE in a Box Technical Standards" were **not opened here**, so the exact treatment of escalation and of which fees count is [U] until the Agent lane confirms it. The statute (Local Government Code chapter 399) has no such test; it requires an independent third-party review of projected savings and a term no longer than the useful life (same legal spec).
- With level savings and a fully financed project, SIR_prog equals the savings-to-debt-service ratio SDR of ECO-12.
- The independent reviewer, not this tool, determines the official figure. The tool's number is a screen.
- Eligibility notes for the scenario (not formulas; all from `specs/legal/texas.md` section 6): Texas C-PACE is for commercial, industrial and nonprofit property and residential property with five or more units, never a single-family home; the written consent of any mortgage holder is a statutory precondition; the term may not exceed the useful life of the improvement. `financing_scenario` sets `eligible = False` with the reason when the property type fails, and always adds the lien and lender-consent statements required by SPEC 6.6. California conditions are in `specs/legal/california.md`.
- Worked example, both ratios on the same measure (the ECO-12 case: project 100 000 USD fully financed at 7 % for 20 years, A = 9 439.29 USD/yr, savings 12 000 USD/yr, O&M cost up 500 USD/yr, no escalation):
  program SIR = 20 * 11 500 / (20 * 9 439.29) = 230 000 / 188 785.85 = **1.218** (passes the program screen).
  life-cycle SIR, cash basis, d = 0.03: PV_S = 11 500 * UPV(0.03, 20) = 11 500 * 14.8775 = 171 090.96; SIR = 171 090.96 / 100 000 = **1.711**.
  The two differ because one counts interest as a cost and does not discount, and the other discounts and counts only the investment. Check: loop sums give 1.2183; `numpy_financial.npv` gives 171 090.96.
  Variant: 10 000 USD paid in cash and 90 000 USD plus 3 % fees financed (P = 92 700, A = 8 750.22): SIR_prog = 230 000 / (175 004.48 + 10 000) = 1.243.
- Tool: `program_sir(annual_net_savings_usd: list[float] | float, annual_payment_usd: float, term_years: int, cash_portion_usd: float = 0.0) -> float`.

### ECO-13 Timing of incentives in the cash flow

| Incentive kind (`Incentive.kind`) | Where it enters | When |
|---|---|---|
| `upfront_rebate` (point of sale or paid on the invoice) | reduces I_0 and the budget cap test | t = 0 |
| `tax_credit` | C_j in ECO-07; does not reduce `net_upfront_usd` | t = 1 (filed with the return for the year of installation) |
| `tax_deduction` | C_j = deduction amount * marginal tax rate; the rate is a user input with no default, and the item is omitted if the rate is unknown | t = 1 |
| `performance_payment` | added to the annual stream for its stated years | years 1..k |
| rebate paid by mail after installation | C_j at t = 1; does not reduce `net_upfront_usd` [J: one year is the conservative choice] | t = 1 |

- Only incentives with `status == "verified"` enter any calculation. `unverified` and `expired` items are listed for the user and carry zero value (SPEC 6.6).
- Primary: SPEC 6.6 (the rule is the product's own); discounting by ECO-02.
- Example: a 3 000 USD tax credit received at t = 1, d = 0.03: PV = 3 000 / 1.03 = 2 912.62 USD.
- Tool: `incentive_cashflows(incentives: list[Incentive], marginal_tax_rate: Optional[float]) -> tuple[float, list[tuple[int, float]]]` returning (upfront total in USD, later items as (year, USD)).

---

## 2. TAR: energy cost and unit conversions

General rule from HB135 section 4.6.1 [V]: use the "current, local, energy price schedules", effective on the base date, not national or regional averages; with a flat price annual quantities are enough, with time-of-use prices "you must have hourly energy consumption data"; and when prices vary with the amount used "the price of the last unit used (aka, the 'marginal' unit) in each billing period is the most appropriate energy price" for a savings analysis.

### TAR-01 Bill with a flat energy charge, and bill savings

```
bill      = sum_{m=1..12} ( F_m + p * Q_m )  =  12 F + p Q         (F and p constant over the year)
savings   = bill(baseline) - bill(with measure) = p * (Q_base - Q_measure)
```

| Symbol | Meaning | Unit |
|---|---|---|
| Q_m, Q | energy bought from the utility in month m, and in the year | kWh |
| p | volumetric price including per-kWh riders and taxes (`Tariff.electricity_usd_per_kwh` or `gas_usd_per_kwh`) | USD/kWh |
| F | fixed charge (`Tariff.fixed_usd_per_month`) | USD/month |

- Validity: one price for all hours and all amounts. On a tiered (block) tariff, p must be the price of the marginal tier, not the average price (HB135 4.6.1.2); the Data lane sets `electricity_usd_per_kwh` to the marginal-tier price and records this in `Tariff.source`. Fixed charges cancel out of savings unless a measure removes a service entirely (for example full electrification that closes the gas account, which then saves 12 F_gas). Q can never be negative here; exports are handled in TAR-03.
- Gas: the same formula with gas in kWh (TAR-05) and `gas_usd_per_kwh`.
- Primary: HB135 section 4.6.1 [V]. Second source: 10 CFR 436.14(c) ("the price of energy ... in the base year is the actual price charged for energy ... delivered") [V].
- Sanity values for `p` (fallback and cross-check only, never the first choice): EIA, *Electric Power Monthly*, Table 5.6.A, data for August 2026, released 23 October 2026 (https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_5_6_a) [V 2026-11-14]: California residential 29.75 and commercial 30.02 cents/kWh; Texas residential 15.91 and commercial 8.96 cents/kWh; U.S. residential 18.16 and commercial 14.47 cents/kWh. These are state averages (revenue divided by sales), so they include fixed charges and are not marginal prices.
- Example: monthly use 900, 800, 750, 700, 800, 1100, 1400, 1500, 1200, 900, 800, 850 kWh (Q = 11 700 kWh), p = 0.25 USD/kWh, F = 10 USD/month. Bill = 11 700 * 0.25 + 120 = **3 045.00 USD** (month-by-month sum gives the same). A measure that cuts every month by 10 % saves 1 170 kWh * 0.25 = **292.50 USD/yr**.
- Tool: `annual_bill_flat(monthly_kwh: list[float], usd_per_kwh: float, fixed_usd_per_month: float) -> float` (USD/yr); `bill_savings(baseline: EnergyUse-like, measure: EnergyUse-like, tariff: Tariff) -> float` (USD/yr).

### TAR-02 Bill with time-of-use energy charges

```
bill = sum_{h=1..8760} p(h) * Q_h + 12 F  =  sum_k p_k * Q_k + 12 F
```

| Symbol | Meaning | Unit |
|---|---|---|
| Q_h | energy bought in hour h | kWh |
| p(h) | price in force in hour h (by season, day type and hour) | USD/kWh |
| k, Q_k, p_k | time-of-use period, energy bought in it, its price | -, kWh, USD/kWh |

- Validity: needs an hourly load profile (the zone model produces one). Demand charges (USD/kW of monthly peak) are not modelled; for a commercial tariff with demand charges the result understates the bill and may misstate savings, and the measure carries the warning "demand charges not modelled".
- Contract note: `Tariff` has no time-of-use field today. Until one is added (section 11), the Data lane supplies a single load-weighted average price and TAR-01 is used. SCE's net billing customers are all on time-of-use rates [V, TAR-03], so for SCE solar the flat approximation is a stated limitation.
- Primary: HB135 section 4.6.1.1 and 4.6.1.2 [V]. Second source: SCE help page "Understanding Solar Export Pricing" ("All NBT customers are TOU rate type") [V 2026-11-14].
- Example: 2 000 kWh in the peak period at 0.45 USD/kWh, 8 000 kWh off-peak at 0.25, F = 10 USD/month: 900 + 2 000 + 120 = **3 020.00 USD**. Script check with an 8 760-hour profile (9 636.0 kWh, of which 2 007.5 kWh between 16:00 and 21:00): hourly sum 2 930.50 USD, period sum 2 930.50 USD.
- Tool: `annual_bill_tou(hourly_kwh: list[float], hourly_price_usd_per_kwh: list[float], fixed_usd_per_month: float) -> float`.

### TAR-03 Export compensation for rooftop solar

Two regimes exist in the two cities. Both start from the hourly balance:

```
import_h = max(L_h - G_h, 0)        export_h = max(G_h - L_h, 0)
f_sc     = 1 - sum_h export_h / sum_h G_h          (self-consumption fraction, SolarDesign.self_consumption_fraction)
```

(a) Net billing (imports and exports priced separately every hour):

```
S_pv = f_sc * E_pv * p_import + (1 - f_sc) * E_pv * p_export
```

(b) Net energy metering (kWh netted over the billing period, credits carried forward at the energy price):

```
S_pv = min(E_pv, E_load) * p_energy              surplus = max(E_pv - E_load, 0) earns nothing in the model
```

| Symbol | Meaning | Unit |
|---|---|---|
| L_h, G_h | site load and PV generation in hour h | kWh |
| E_pv, E_load | annual PV generation and annual site load | kWh/yr |
| p_import | price of bought electricity (`electricity_usd_per_kwh`) | USD/kWh |
| p_export | export compensation (`export_usd_per_kwh`) | USD/kWh |
| p_energy | the energy (per-kWh) part of the retail rate | USD/kWh |
| S_pv | first-year bill savings from PV; this is S_e0 + S_x0 in ECO-07 | USD/yr |

Regime by utility:

| Territory | Regime today | What the source says | Model | Status |
|---|---|---|---|---|
| City of Los Angeles (LADWP) | Net energy metering, "Service Rider NEM" (rate effective 1 September 2008), systems up to 1 MW | If generation exceeds supply over the billing period, "A credit for the energy received will be calculated using the applicable Rate Schedule energy pricing"; the credit is applied "to charges under each subsequent bill except Taxes and Minimum Charges"; at termination of service "the balance will automatically be adjusted to zero". Source: LADWP, Residential Rates page, https://www.ladwp.com/account/customer-service/electric-rates/residential-rates; LADWP Net Energy Metering Guidelines (revised 28 August 2019, technical modification April 2021) | (b), with p_energy = `electricity_usd_per_kwh`; fixed and minimum charges are never offset | [V 2026-11-14] |
| Southern California Edison territory (parts of Los Angeles County outside the city) | Net Billing Tariff, called the Solar Billing Plan, for interconnection applications since 15 April 2023 (CPUC Decision 22-12-056) | CPUC: export compensation "is applied to a customer's bill at a rate reflecting the value of this generation to the grid", based on "CPUC Avoided Cost Calculator values (usually lower than import rates)"; residential PG&E and SCE customers who apply "before the end of 2027" receive an adder "for nine years"; nine-year legacy period. SCE: hourly Energy Export Credit prices by vintage year (NBT26 for 2026 applications), fixed for 9 years; all NBT customers are on time-of-use rates. Sources: https://www.cpuc.ca.gov/industries-and-topics/electrical-energy/demand-side-management/customer-generation/net-energy-metering-and-net-billing; https://www.sce.com/customer-service-center/help-center/solar/solar-billing-plan/understanding-export-pricing | (a); p_export must come from SCE's Energy Export Credit price file for the application year, as a PV-export-weighted average | regime [V 2026-11-14]; the numeric p_export is [P] Data lane (the price file was not downloaded) |
| Houston (CenterPoint Energy delivery area, retail competition) | No mandated export price. CenterPoint is the wires utility and does not buy energy | PUC of Texas Substantive Rule 25.217(f)(2) (effective 11 June 2012): "In areas in which customer choice has been introduced, DRGOs who choose to sell out-flows shall sell their out-flows to the REP that serves the premises at which the DRG is located at a value to which both parties agree." Source: https://ftp.puc.texas.gov/public/puct-info/agency/rulesnlaws/subrules/electric/25.217/25.217.pdf | (a); p_export is whatever the customer's retail plan pays. Default 0.0 with the note "export value depends on your retail electricity plan; none assumed" | rule [V 2026-11-14]; the statute behind it (Texas Utilities Code section 39.916) was not opened [U] |

Rules:

1. Net metering, monthly carry-forward: credits only move forward in time, so in the first year a system switched on in winter can pay for a few early-month deficits before credits build up (script check: 88 kWh billed in year 1 in a case where annual netting says 0). The model uses the steady-state annual form (b); this is stated in the output.
2. Fallback when `export_usd_per_kwh` is missing in a net-billing territory: p_export = 0, flagged. Never substitute the retail price.
2a. Texas has no statutory net metering (`specs/legal/texas.md`, TX-SOL-34, and the PUC rule above), so the model never assumes an export credit there. `tariff.export_usd_per_kwh` is an assumption with **low = 0 always**. With no plan information: low 0, expected 0, high 0, and the plan warns that all savings come from self-consumption. If the user gives the buy-back rate of their retail plan: low 0 (the plan can change at renewal), expected = high = that rate. Because of this, PV in Houston should be sized toward self-consumption, and the legal spec also notes a registration consequence if annual production exceeds annual consumption (TX-SOL-36).
3. Low/expected/high of S_pv come from the ranges of E_pv, f_sc and p_export through UNC-01.
4. Third-party sites report that LADWP may close net metering to new applicants; nothing to that effect was found on LADWP's own pages on 2026-11-14 [U]. Re-check the LADWP page before relying on regime (b) for a contract.

- Primary: the three official sources in the table. Second sources: CPUC page and SCE page agree with each other on the SCE regime; LADWP's rates page and LADWP's NEM Guidelines agree on the LADWP regime; for Texas only the PUC rule was opened.
- Example (a): E_pv = 8 000 kWh, f_sc = 0.45, p_import = 0.30, p_export = 0.06: S_pv = 0.45 * 8 000 * 0.30 + 0.55 * 8 000 * 0.06 = 1 080 + 264 = **1 344 USD/yr**. Hourly script check with a block PV profile against a flat 10 000 kWh/yr load: f_sc = 0.4167, bill difference 1 280.00 USD, formula 1 280.00 USD.
- Example (b): E_load = 10 000 kWh, p_energy = 0.30. E_pv = 8 000 gives **2 400 USD/yr**. E_pv = 12 000 gives 10 000 * 0.30 = **3 000 USD/yr**, with 2 000 kWh of credit that the model values at zero.
- Tool: `self_consumption_fraction(hourly_load_kwh, hourly_pv_kwh) -> float`; `pv_bill_savings(regime: Literal["net_billing","net_metering"], e_pv_kwh, e_load_kwh, f_sc, p_import, p_export) -> float` (USD/yr); `export_regime(tariff: Tariff) -> (Literal["net_billing","net_metering","none"], warnings)`: `Tariff.export_regime` when the Data lane set it (`none` in Texas, where no export price is mandated), otherwise read from the utility name. A `Tariff.utility` that names no utility (for example a state-average price) is unconfirmed: it is never taken as LADWP, and the result carries a warning.

### TAR-04 Gas bill

Same as TAR-01 with gas quantity in kWh (higher heating value) and `gas_usd_per_kwh`. Utilities bill in therms: `gas_usd_per_kwh = usd_per_therm / 29.3071` (TAR-05).

- Example: 500 therms/yr at 1.50 USD/therm and 5 USD/month: 500 * 1.50 + 60 = 810.00 USD. In contract units: 14 653.55 kWh * 0.051182 USD/kWh + 60 = 810.00 USD.
- Tool: `annual_bill_flat` (same function).

### TAR-06 Default electricity price where no utility tariff exists (Houston)

The Houston area is in ERCOT's competitive retail market: the wires utility (CenterPoint) has no retail energy tariff, each customer buys from a retail electric provider, and a tariff database lookup returns nothing. The price the model uses, in order of preference:

1. The customer's own price: total electricity charges divided by kWh on a recent bill, or the plan's energy charge plus delivery charges. The user-supplied value replaces everything below (source `user`).
2. Otherwise the published defaults in this table, carried as an assumption with a range so that the ask rule (SPEC 5.3) can ask for the bill when the price drives the result.

| Sector | Low | Expected | High | Unit | Where each number comes from |
|---|---|---|---|---|---|
| Residential (Houston, CenterPoint delivery area) | 0.118 | 0.133 | 0.160 | USD/kWh | Low and expected: 10th percentile and median of the all-in price at 1 000 kWh/month across the 96 fixed-rate, non-prepaid, non-time-of-use plans with a term of 12 months or more listed for "CENTERPOINT ENERGY HOUSTON ELECTRIC LLC" (English listings) in the Public Utility Commission of Texas "Power to Choose" export, http://www.powertochoose.org/en-us/Plan/ExportToCsv, retrieved 2026-11-14 (no key needed). The 90th percentile is 0.153. High: EIA Texas residential average, year to date through August 2026, 16.03 cents/kWh (*Electric Power Monthly* Table 5.6.B, released 23 October 2026, retrieved 2026-11-14); the August 2026 month alone is 15.91 (Table 5.6.A) |
| Commercial (office) | 0.086 | 0.090 | 0.133 | USD/kWh | Low: EIA Texas commercial average, year to date through August 2026, 8.60 cents/kWh (Table 5.6.B; 8.59 a year earlier). Expected: EIA Texas commercial average for August 2026, 8.96 cents/kWh (Table 5.6.A). High: the residential plan median above, as a ceiling for a small office buying on a small-business plan [J]; no dataset of small-commercial plan prices was opened |

- Why these are usable as marginal prices: the listed plan prices already include delivery charges, and across the same 96 plans the implied price of the next kWh between 1 000 and 2 000 kWh/month has median 0.1325 USD/kWh (10th to 90th percentile 0.1195 to 0.154), essentially the same as the all-in price at 1 000 kWh. Between 500 and 1 000 kWh the implied marginal price is lower (median 0.126) because many plans carry a fixed monthly charge or a usage credit. Fixed charges: `fixed_usd_per_month` = 0 with these defaults (the all-in price already contains them), so baseline bills are right at about 1 000 kWh/month and savings are not overstated.
- The commercial figures are state-wide averages over all commercial customers, including large ones on demand-metered service; a small office usually pays more. The low and expected values are therefore conservative for savings, and the wide range is deliberate.
- Validity: valid for the retrieval date. The export changes daily; the Data lane stores the file it used under `data/cache/` with its date and re-derives the three numbers with the filter above. No API key or NREL service is involved.
- Export compensation in this market: TAR-03 (default 0).
- California check values from the same EIA tables (not used when a utility tariff is available): residential 32.58 and commercial 26.96 cents/kWh year to date through August 2026.
- Contract mapping: `Tariff.electricity_usd_per_kwh` = expected; `Tariff.source` = "PUC of Texas Power to Choose export, CenterPoint area, median fixed 12+ month plan at 1000 kWh, retrieved 2026-11-14" (or the EIA table for commercial); the range goes into the assumption registry as `tariff.electricity_usd_per_kwh` (a `Ranged`, `user_editable = True`).
- Primary: the two official datasets named above [V 2026-11-14]. Second source: the two agree in level (plan median 13.3 cents at 1 000 kWh against a state residential average of 15.9 to 16.0 cents that also includes higher-priced variable and low-usage customers and non-competitive areas).
- Example: a Houston home saving 2 000 kWh/yr: 2 000 * (0.118, 0.133, 0.160) = **236 / 266 / 320 USD/yr** (price range only, before combining with the kWh range in UNC-01). Percentiles were computed with `numpy.percentile` and re-checked with a sort-and-rank calculation (0.118, 0.133, 0.153).
- Tool: `default_electricity_price(city: str, sector: str) -> Ranged`; `summarise_power_to_choose(csv_path: str, tdu: str) -> Ranged` (the filter and percentiles above).

### TAR-05 Unit conversions

| From | To | Factor | Exact? | Source |
|---|---|---|---|---|
| 1 kWh | MJ | 3.6 | exact | NIST SP 811 (2008), Appendix B.8: "kilowatt hour (kW·h) to megajoule (MJ) 3.6 E+00" [V] |
| 1 Btu (International Table) | J | 1 055.055 852 62 | exact by definition (4 186.8 J/(kg·K) * 0.453 592 37 kg * 5/9 K) | NIST SP 811 Appendix B.8 lists 1.055 056 E+03 and footnote 9 defines the IT calorie [V] |
| 1 therm (= 100 000 Btu_IT; SP 811 calls it "therm (EC)") | MJ | 105.505 585 262 | exact | NIST SP 811: "therm (EC) to joule 1.055 06 E+08" [V]; EIA: "1 therm = 100,000 Btu" [V] |
| 1 therm | kWh | 29.307 107 | derived (105.505 585 262 / 3.6) | derived |
| 1 therm (U.S.) | MJ | 105.480 4 | defined | NIST SP 811: "therm (U.S.) to joule 1.054 804 E+08"; footnote 24: "the therm (U.S.) is the legal unit used by the U.S. natural gas industry" [V] |
| 1 MMBtu (10^6 Btu_IT) | kWh | 293.071 07 | derived | derived |
| 1 kWh | Btu_IT | 3 412.141 6 | derived | EIA: "1 kilowatthour = 3,412 Btu" [V] |
| 1 lb | kg | 0.453 592 37 | exact | NIST SP 811 Appendix B.8, footnote 22: "The exact conversion factor is 4.535 923 7 E-01" [V] |

- Choice: the code uses 1 therm = 100 000 Btu_IT = 29.307 107 kWh, the convention of EIA and of EPA's reporting rule (40 CFR 98.33 equation C-1a: "0.1 = Conversion factor from therms to mmBtu") [V]. The U.S. legal therm is 0.024 % smaller (105.4804 against 105.5056 MJ), far below every other uncertainty here.
- Gas volumes: heat content varies by supplier. If a bill is in hundred cubic feet (Ccf), use the heat factor printed on the bill; fallback 1 036 Btu per cubic foot (EIA, "based on U.S. average for natural gas delivered to consumers in 2026; estimate") [V 2026-11-14]; EPA's default is 1 026 Btu/scf (40 CFR 98 Table C-1) [V].
- Primary: Thompson, A. and Taylor, B. N., *Guide for the Use of the International System of Units (SI)*, NIST Special Publication 811, 2008 edition, https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication811e2008.pdf [V]. Second source: EIA, "Units and calculators explained", https://www.eia.gov/energyexplained/units-and-calculators/ [V 2026-11-14].
- Example: 500 therms = 500 * 29.307 107 = **14 653.55 kWh** (via MJ: 500 * 105.505 585 / 3.6 = 14 653.55). 1.50 USD/therm = 1.50 / 29.307 107 = **0.051 182 USD/kWh**.
- Tool: `therms_to_kwh(x)`, `kwh_to_therms(x)`, `kwh_to_mj(x)`, `mmbtu_to_kwh(x)`, constants `KWH_PER_THERM = 29.3071070172`, `MJ_PER_KWH = 3.6`, `KG_PER_LB = 0.45359237`.

---

## 3. EMI: emissions

### EMI-01 Grid electricity emission factors

```
co2_kg = Q_elec * EF_avg                         (all contract co2_kg fields)
co2_avoided_nonbaseload_kg = dQ_elec * EF_nb     (reported in notes only)
```

| Symbol | Meaning | Unit |
|---|---|---|
| Q_elec, dQ_elec | annual electricity bought from the grid, and its reduction (including PV generation used on site or exported) | kWh/yr |
| EF_avg | eGRID subregion total output emission rate, CO2-equivalent | kg CO2e/kWh |
| EF_nb | eGRID subregion non-baseload output emission rate, CO2-equivalent | kg CO2e/kWh |

Values: EPA eGRID2023, revision 2, released 12 June 2025 (first release 15 January 2025). This was still the latest eGRID on the EPA summary page (page last updated 20 May 2026) when checked on 2026-11-13 and 2026-11-14.

The file was opened and read directly (both the xlsx and the PDF of the summary tables, downloaded from epa.gov on 2026-11-13); nothing in this table is from memory.

| Subregion | Covers | CO2 total output, lb/MWh | CO2 total output, kg/kWh | CO2e total output, lb/MWh | **EF_avg, kg CO2e/kWh** | CO2e non-baseload, lb/MWh | **EF_nb, kg CO2e/kWh** | Grid gross loss |
|---|---|---|---|---|---|---|---|---|
| CAMX (WECC California) | all 533 Los Angeles-area ZIP codes checked (prefixes 900-918) | 428.464 | 0.19435 | 429.983 | **0.19504** | 961.2 | **0.43599** | 4.1 % |
| ERCT (ERCOT All) | most Houston-area ZIP codes | 733.862 | 0.33287 | 736.629 | **0.33413** | 1 247.5 | **0.56586** | 4.2 % |
| U.S. | reference | 767.2 | 0.3480 | 770.9 | 0.3497 | 1 379.2 | 0.6256 | 4.2 % |

The product uses the CO2e column (EF_avg). The CO2-only column is given for anyone who needs to compare with CO2-only figures; EPA's own kg table prints 194.351 and 332.88 kg CO2/MWh for the two subregions.

- Conversion: kg/kWh = lb/MWh * 0.453 592 37 / 1000 (TAR-05).
- GWP basis: 100-year, IPCC Fifth Assessment Report, CH4 = 28, N2O = 265 (eGRID2023 Technical Guide, January 2025, section 3.1.1: "AR5 without climate-carbon feedbacks ... CH4 is 28 and N2O is 265"; the EPA hub prints the same two values) [V].
- Location: use the eGRID subregion of the site's ZIP code from EPA's Power Profiler ZIP code tool (v14.3, eGRID2023 rev 2). Of 415 ZIP codes with Houston-area prefixes (770, 772-775), 325 are ERCT only, 35 are SRMV only (Entergy territory east and north of the metro area) and 55 are split; a split or SRMV ZIP must be resolved by the utility on the bill (CenterPoint delivery area = ERCT). LADWP has its own balancing authority but lies in subregion CAMX.
- Average or marginal. EPA ("Using eGRID to Determine Emissions", January 2025): total output rates "represent the average emissions intensity of electricity for a region and are typically used to determine emissions from electricity use"; non-baseload rates "represent the average emissions intensity from nonbaseload units or marginal generation that might be avoided from efforts to reduce electricity generation, such as energy efficiency and/or renewable energy projects." Decision for the product: every `co2_kg` in the contract uses EF_avg, so that baseline minus savings equals the after-plan figure and the claim is the conservative one; the non-baseload figure is added to the measure's notes as "up to ... kg/yr on EPA's non-baseload basis". Hourly marginal rates are not used.
- Line losses: not applied (EPA's location-based convention multiplies metered purchases by the output rate). Dividing by (1 - grid gross loss) would raise the figures by about 4 %.
- Validity: the factor describes calendar 2023 generation. It is held constant over the analysis period for the first-year figure the contract reports; lifetime CO2 is not computed (both grids are decarbonising, so a constant-factor lifetime sum would overstate).
- Primary: EPA, *eGRID2023 Summary Tables*, revision 2, Table 1, https://www.epa.gov/system/files/documents/2025-06/summary_tables_rev2.xlsx and .pdf [V 2026-11-14].
- Second source: EPA Power Profiler ZIP code tool v14.3 (https://www.epa.gov/system/files/documents/2025-06/power_profiler_zipcode_tool_v14.3.xlsx), sheet "Subregion Rates (kg-MWh)": CAMX 195.04 and ERCT 334.135 kg CO2e/MWh, matching the conversion above [V]. Caution: EPA's GHG Emission Factors Hub dated 15 January 2025 prints the pre-revision values (CAMX CO2 436.7, ERCT CO2 738.0 lb/MWh); do not mix the two.
- Example: 10 000 kWh/yr saved in Houston: 10 000 * 0.33413 = **3 341 kg CO2e/yr** (from the kg table: 10 000 * 334.135 / 1000 = 3 341.35). Non-baseload basis: 10 000 * 0.56586 = 5 659 kg. Same saving in Los Angeles: 1 950 kg (non-baseload 4 360 kg).
- Tool: `grid_emission_factor(zip_code: str, basis: Literal["average","nonbaseload"] = "average") -> float` (kg CO2e/kWh); `egrid_subregion(zip_code: str) -> str`.

### EMI-02 Natural gas combustion

```
co2_kg = Q_gas_kwh * EF_gas          EF_gas = (53.06 + 1.0e-3 * 28 + 1.0e-4 * 265) / 293.07107 = 0.18123 kg CO2e/kWh (HHV)
```

| Quantity | Value | Unit |
|---|---|---|
| CO2 factor | 53.06 | kg CO2 per MMBtu (HHV) |
| CH4 factor | 1.0 | g CH4 per MMBtu |
| N2O factor | 0.10 | g N2O per MMBtu |
| CO2e factor (AR5 GWP: 28, 265) | 53.1145 | kg CO2e per MMBtu |
| **EF_gas** | **0.18123** | kg CO2e per kWh of gas (HHV) |
| per therm (100 000 Btu) | 5.3115 | kg CO2e per therm |
| CO2 only | 0.18105 | kg CO2 per kWh |
| default heat content | 0.001026 | MMBtu per standard cubic foot |

- Validity: combustion at the building only (Scope 1). Upstream methane leakage is not included.
- Primary: EPA, *GHG Emission Factors Hub*, version last modified 15 January 2025, Table 1 "Stationary Combustion", natural gas row; https://www.epa.gov/system/files/documents/2025-01/ghg-emission-factors-hub-2025.pdf [V 2026-11-14]. The hub page still described the January 2025 update as the latest on 2026-11-13.
- Second source: 40 CFR Part 98, Subpart C, Table C-1 (natural gas, weighted U.S. average: 1.026 x 10^-3 mmBtu/scf, 53.06 kg CO2/mmBtu) and Table C-2 (natural gas: 1.0 x 10^-3 kg CH4/mmBtu, 1.0 x 10^-4 kg N2O/mmBtu), eCFR version of 2026-11-01 [V].
- Example: 500 therms/yr of gas avoided = 14 653.55 kWh: 14 653.55 * 0.181234 = **2 655.7 kg CO2e/yr**; by therms: 500 * 5.31145 = 2 655.7 kg.
- Tool: `gas_emission_factor() -> float` (kg CO2e/kWh); `annual_co2_kg(electricity_kwh: float, gas_kwh: float, zip_code: str) -> float`.

### EMI-03 Net effect of fuel switching

For a measure that replaces gas with electricity (`HVAC_HP`, `DHW_HPWH`): `d_co2 = dQ_gas * EF_gas - dQ_elec_added * EF_avg`, where dQ_elec_added is the extra electricity. The result can be negative on a carbon-intensive grid; it is reported as computed, with its sign.

- Example (Houston): 14 653.55 kWh of gas removed, 4 500 kWh of electricity added: 2 655.7 - 4 500 * 0.33413 = 2 655.7 - 1 503.6 = **1 152.1 kg CO2e/yr avoided**.
- Tool: `annual_co2_kg` applied to baseline and to the post-measure state; the difference is `savings.co2_kg`.

## 4. INC: incentive registry

Checked 2026-11-13 and 2026-11-14. The question asked of every entry: can a project whose work starts in November 2026 use it?

Primary texts opened for the federal entries:

- Public Law 119-21 (139 Stat. 72, 4 July 2025; the 2025 budget reconciliation act), sections 70505 to 70513, GPO text: https://www.govinfo.gov/content/pkg/PLAW-119publ21/html/PLAW-119publ21.htm
- The amended code sections as published by Cornell LII (each page lists the Pub. L. 119-21 amendments in its notes): https://www.law.cornell.edu/uscode/text/26/25C, /25D, /45L, /48, /48E, /179D. The House `uscode.house.gov` pages could not be fetched (HTTP 404 on the URLs tried), so LII is the codified reproduction used; every termination date below was also read in the public law itself.
- IRS Fact Sheet FS-2025-05 (21 August 2025), "FAQs for modification of sections 25C, 25D, 25E, 30C, 30D, 45L, 45W, and 179D under Public Law 119-21": https://www.irs.gov/newsroom/faqs-for-modification-of-sections-25c-25d-25e-30c-30d-45l-45w-and-179d-under-public-law-119-21-139-stat-72-july-4-2025-commonly-known-as-the-one-big-beautiful-bill-obbb
- IRS Notice 2025-42 (beginning of construction for wind and solar facilities under sections 45Y and 48E): https://www.irs.gov/pub/irs-drop/n-25-42.pdf

Registry status values follow the contract: `verified` (in force and read in the primary text), `unverified`, `expired` (not available for work starting now). An incentive that is in force but whose eligibility depends on facts the tool cannot see is `verified` with a "needs confirmation" note and amount low = 0, expected = 0, high = the rule amount, until the user confirms the conditions (section 11 proposes a field for this).

### INC-01 to INC-06 Federal tax incentives

| ID | Incentive | Kind | Amount rule (when it applied) | Status for work starting November 2026 | Statutory text read |
|---|---|---|---|---|---|
| INC-01 | 26 U.S.C. 25C, energy efficient home improvement credit (insulation, windows, heat pumps, heat pump water heaters, audits) | `tax_credit` | 30 % of cost with annual caps | **expired.** Section 25C(i): "This section shall not apply with respect to any property placed in service after December 31, 2025." | Pub. L. 119-21 section 70505(a); 25C(i) on LII; FS-2025-05 Q1 [V] |
| INC-02 | 26 U.S.C. 25D, residential clean energy credit (homeowner-owned solar, batteries, geothermal) | `tax_credit` | 30 % of expenditures | **expired.** Section 25D(h): "The credit allowed under this section shall not apply with respect to any expenditures made after December 31, 2025." An expenditure is treated as made when installation is completed (FS-2025-05 Q7, citing 25D(e)(8)(A)), so paying a deposit in 2025 does not help | Pub. L. 119-21 section 70506(a); 25D(h) on LII; FS-2025-05 Q1 and Q7 [V] |
| INC-03 | 26 U.S.C. 179D, energy efficient commercial buildings deduction | `tax_deduction` | per square foot, by modelled savings | **expired.** Section 179D(i): "This section shall not apply with respect to property the construction of which begins after June 30, 2026." Still usable only if construction of the property began on or before 30 June 2026 | Pub. L. 119-21 section 70507; 179D(i) on LII; FS-2025-05 Q1 [V] |
| INC-04 | 26 U.S.C. 45L, new energy efficient home credit | `tax_credit` | per new dwelling unit, to the builder | **expired**, and never applied to retrofits. Section 45L(h): "This section shall not apply to any qualified new energy efficient home acquired after June 30, 2026." | Pub. L. 119-21 section 70508; 45L(h) on LII; FS-2025-05 Q1 [V] |
| INC-05 | 26 U.S.C. 48E, clean electricity investment credit, for a solar facility owned by a business taxpayer (a commercial owner, or the lessor of a residential system) | `tax_credit` | 30 % of the qualified investment for a facility "with a maximum net output of less than 1 megawatt (as measured in alternating current)" (48E(a)(2)(A)(ii)(I)); otherwise 6 % unless wage and apprenticeship rules are met | **verified, needs confirmation.** Three conditions: (1) section 48E(e)(4)(A): the credit "shall not apply to any qualified property placed in service by the taxpayer after December 31, 2027" that is part of a wind or solar facility; this applies "to facilities the construction of which begins after the date which is 12 months after the date of enactment" (section 70513(g)(5)), that is after 4 July 2026, which covers any project starting now. So: **placed in service by 31 December 2027, or no credit.** (2) Section 48E(b)(6): for construction beginning after 31 December 2025 the facility is not a qualified facility if its construction "includes any material assistance from a prohibited foreign entity"; the installer must document equipment sourcing. (3) The owner must be a taxpayer for whom the property is depreciable business property with tax liability to use the credit; a homeowner cannot claim it. Energy storage at such a facility is excepted from the 2027 cut-off (48E(e)(4)(C)) | Pub. L. 119-21 section 70513(a), (b), (g); 48E on LII; Notice 2025-42 (confirms the "after July 4, 2026" construction date) [V] |
| INC-05b | Section 48E for leased solar water heating or small wind | `tax_credit` | n/a | **expired** in effect. Section 48E(i) denies the credit for "property described in paragraph (1) or (4) of section 25D(d)" (solar water heating, small wind) that the taxpayer "rents or leases ... to a third party". Paragraph (2), solar electric, is not listed, so leased rooftop PV stays under INC-05 | Pub. L. 119-21 section 70513(c); 48E(i) and 25D(d) on LII [V] |
| INC-06 | 26 U.S.C. 48, energy credit | `tax_credit` | n/a | **expired** for every measure in SPEC 6.2. For solar energy property the 30 % (or 6 %) rate applies "only with respect to property the construction of which begins before January 1, 2025" (48(a)(2)(A)(i)(II)); other energy property is at "0 percent" (48(a)(2)(A)(ii), as amended by section 70513(e)). Ground-source heat pump property remains until construction beginning before 1 January 2035, but no measure in the library uses it | 48(a)(2) and (a)(3) on LII; Pub. L. 119-21 section 70513(e) [V] |

Confirmation of SPEC 6.6 (which quoted secondary sources): all four statements there are correct. Precise wording: 25C ends by placed-in-service date and 25D by expenditure date (both 31 December 2025); 179D by construction start (30 June 2026); 48E for solar by construction start after 4 July 2026 combined with a placed-in-service deadline of 31 December 2027. Two things SPEC 6.6 does not say and should: the prohibited-foreign-entity condition on 48E, and that 48E is a business credit that a homeowner cannot take.

Not modelled, stated so in the output: accelerated depreciation for business owners (Pub. L. 119-21 section 70509 removes one of the five-year classes for energy property whose construction begins after 31 December 2024; the remaining rules were not analysed) and state income tax effects.

Worked example (INC-05): commercial rooftop PV, 50 kW DC, installed cost 110 000 USD, all three conditions confirmed. Credit = 0.30 * 110 000 = **33 000 USD**, received at t = 1; present value at 3 %: 33 000 / 1.03 = 32 038.83 USD (ECO-13). It does not reduce `net_upfront_usd`. If any condition is unconfirmed the registry reports low 0, expected 0, high 33 000.

- Tool: `federal_incentives(measure_id, sector, owner_is_business: bool, in_service_date: date, construction_start: date, pfe_compliant: Optional[bool], installed_cost_usd: Ranged) -> list[Incentive]`.

### INC-07 Federal home energy rebates run by the states (HOMES and HEEHRA)

| Territory | Status | Source |
|---|---|---|
| California (HEEHRA, run through TECH Clean California) | **expired for new reservations**: "As of February 24, 2026, HEEHRA single-family rebates are fully reserved for projects statewide"; "As of September 1, 2026, multifamily HEEHRA rebates are fully reserved"; Southern California single-family funds were fully reserved on 7 January 2026 | https://techcleanca.com/incentives/ [V 2026-11-14] |
| Texas | **unverified**; no official page was opened | [U] |

### INC-10 to INC-19 Utility programs, Los Angeles

LADWP residential, Consumer Rebate Program (CRP). Source: https://www.ladwp.com/residential-services/assistance-programs/consumer-rebate-program [V 2026-11-14]. Common rules: LADWP residential customer with active electric service; apply after purchase and installation, within 12 months of purchase; most items need a finalled building permit; LADWP may inspect before "releasing your rebate check". These are rebates paid after installation, not point-of-sale discounts.

| ID | Measure ID | Item | Amount rule | Conditions | Status |
|---|---|---|---|---|---|
| INC-10 | `ROOF_COOL` | Cool roof | 0.20 or 0.60 USD per sq ft of cool roof over conditioned space | Low slope (<= 2:12): 3-year SRI >= 78 earns 0.20, >= 85 earns 0.60. Steep slope: SRI >= 20 earns 0.20, >= 35 earns 0.60. CRRC-rated product | verified |
| INC-11 | `WIN_REPLACE` | ENERGY STAR windows | 2.00 USD per sq ft | U-factor <= 0.30 and SHGC <= 0.25 (skylights 0.50 and 0.28). No new construction, additions or ADUs | verified |
| INC-12 | (central AC, not a library measure) | HVAC system | 100 USD/ton at 15.2 SEER2; 120 USD/ton at 16.0 SEER2 | AHRI certificate, permit | verified |
| INC-13 | `HVAC_HP` | Heat pump HVAC, central ducted, split or packaged | per ton: 1 000 (> 15.2 SEER2, > 7.7 HSPF2); 1 050 (> 16, > 8.0); 1 100 (> 16.9, > 8.1); 1 150 (> 17.8, > 8.1); 1 200 (> 18.7, > 8.5); 1 250 (> 19.6, > 8.9) | Minimum 7.7 HSPF2 and 15.2 SEER2; equipment purchased and installed on or after 1 November 2025; no new construction or ADUs; packaged terminal units excluded | verified |
| INC-14 | `HVAC_HP` | Heat pump HVAC, ductless mini-split or multi-split | per ton: 1 500 (> 15.2 SEER2, > 7.8 HSPF2); 1 650 (> 16, > 8.1); 1 800 (> 16.9, > 8.3); 1 950 (> 17.8, > 8.5); 2 100 (> 18.7, > 8.7); 2 250 (> 19.6, > 8.9); 2 500 (> 20.5, > 9.1) | as INC-13 | verified |
| INC-15 | `DHW_HPWH` | ENERGY STAR heat pump water heater | per unit, by tank size and UEF. 30 to 55 gal: 1 500 (UEF 3.3), 1 750 (3.5), 2 000 (3.75). 56 to 75 gal: 1 750, 2 100, 2 250. 76 gal and above: 1 950, 2 250, 2 500 | UEF >= 3.3, capacity >= 30 gal; application asks for the pre-existing gas water heater; no new construction, additions or ADUs | verified |
| INC-16 | (not a library measure) | Whole house fan | 200 USD per unit, one per residence | permit | verified |
| INC-17 | `ENV_ATTIC` | Attic Insulation Rebate Program (separate program): batt and roll insulation only | 0.50 USD per sq ft above R-19; 0.30 USD per sq ft at R-19 or below; plus a "Launch Special Extended" extra 0.25 USD per sq ft with no end date stated | Purchased and installed on or after 1 September 2025; finalled LADBS permit; before and after photos. Source: https://www.ladwp.com/residential-services/programs-and-rebates-residential/attic-insulation-rebate-program | verified [V 2026-11-14]; treat the extra 0.25 as `unverified` because no end date is given |

Caution: the CRP page still says "Homeowners may also receive up to $2,000 in Federal Tax Credit" beside the heat pump item. That refers to section 25C, which has expired (INC-01); the registry must not repeat it.

LADWP non-residential:

| ID | Measure IDs | Program | Amount rule | Conditions | Status |
|---|---|---|---|---|---|
| INC-18 | `HVAC_RTU`, `HVAC_ECON`, `ENV_*`, `PLUG_MGMT`, `CTRL_TSTAT` (office) | Business Offerings for Sustainable Solutions (BOSS), https://www.ladwp.com/commercial-services/programs-and-rebates-commercial/business-offerings-sustainable-solutions-boss | USD per kWh of first-year savings: HVAC cooling 0.60; HVAC heating 0.30; HVAC ventilation 0.25; appliance, plug, process and refrigeration 0.30; domestic hot water 0.15; building envelope 0.30 to 0.65 (paid at the rate of the affected HVAC system); whole building 0.25 (IPMVP Option C only). Electrification, prescriptive: heat pump water heater 1 800 to 2 850 USD each; packaged heat pump air conditioner 250 to 650 USD/ton | LADWP non-residential customer; **pre-installation verification and LADWP pre-approval before any installation**; must exceed California Energy Code minimums; normally replaces existing equipment; complete within 12 months of approval. Lighting only together with a non-lighting measure saving at least 100 000 kWh | verified [V 2026-11-14] |
| INC-19 | `LGT_LED`, `LGT_CTRL` (office) | Commercial Lighting Incentive Program (CLIP), https://www.ladwp.com/commercial-services/programs-and-rebates-commercial/commercial-lighting-incentive-program | USD per kWh of annualised savings ("as of July 1, 2024"): lamp only 0.08; fixture replacement or retrofit 0.20 (DLC Standard), 0.30 (DLC Premium), 0.40 (LADWP Preferred); controls 0.10 (wall or ceiling mounted), 0.20 (integrated), 0.30 (networked); interactive effects 0.08. "up to 100% of the project cost" | Commercial customer whose monthly demand (Facilities Charge) is **greater than 200 kW**; DLC-listed products; LADWP approval before purchase; at least 25 % energy savings; complete within 120 days of pre-approval | verified [V 2026-11-14] |

Southern California Edison (customers outside the City of Los Angeles):

| ID | Item | Finding | Status |
|---|---|---|---|
| INC-20 | SCE measure rebates for the library's measures | The SCE pages opened (https://www.sce.com/save-money/rebates-financial-assistance, https://www.sce.com/clean-energy-efficiency/home, https://www.sce.com/business/smart-energy-solar/energy-efficiency-programs) state no per-measure rebate amounts; they point to a marketplace and to statewide programs | unverified (no amount found) |
| INC-21 | SCE On-Bill Financing for business | "no interest or fees", repaid on the utility bill. This is financing, not an incentive; it could be offered as a third `FinancingScenario.kind` later | verified as described [V 2026-11-14]; terms and caps not opened |
| INC-22 | TECH Clean California heat pump incentives (`HVAC_HP`, `DHW_HPWH`) | Program exists and is budget-limited; on 2 November 2026 incentives opened for single-family homes in the San Fernando Valley. Amounts were not opened | unverified (amount) |
| INC-23 | South Coast AQMD "GO ZERO" heat pump rebate | Mentioned on LADWP's CRP page ("up to $3,000"); the program's own page was not opened | unverified |

SoCalGas, Home Energy Efficiency Rebate Program 2026 (https://www.socalgas.com/savings/rebates-and-incentives) [V 2026-11-14]: rebates are for efficient gas appliances (dryer 70 USD; tankless water heater 80 to 1 500; storage water heater 300 to 575; a furnace-type item at AFUE >= 92 %, 1.40 to 25 USD/kBtuh; pool heater, ovens, fireplace inserts; solar thermal water heating 2 500 to 5 000). **None maps to a measure in SPEC 6.2** (the library electrifies heating and hot water rather than replacing gas with gas), so the registry holds no SoCalGas entry. No insulation rebate appears on that page.

### INC-30 to INC-34 Utility programs, Houston (CenterPoint Energy Houston Electric)

Sources: CenterPoint pages https://www.centerpointenergy.com/en-us/savings-solutions/energy-efficiency/heating-cooling and .../solar-energy [V 2026-11-14]; "CenterPoint Energy Houston Electric, LLC 2026 Energy Efficiency Plan and Report" (errata filed 10 September 2026, PUC of Texas Project No. 59166), https://interchange.puc.texas.gov/Documents/59826_31_1681818.PDF [V 2026-11-14]. The plan lists 16 programs for 2026.

| ID | Measure IDs | Program | Amount rule | Conditions | Status |
|---|---|---|---|---|---|
| INC-30 | `HVAC_HP` (home) | Residential HVAC replacement incentives | "incentives that start at $200 and may increase, depending on your installation" | Through a participating contractor; "applied directly to your installation invoice" (so this one is point-of-sale); eligible equipment from 15.2 SEER2; central AC, heat pumps and mini-splits | verified for the 200 USD floor only; registry amount low 200, expected 200, high unknown (left at 200) |
| INC-31 | `PV_ROOF` (home) | Residential Solar Program | 135 USD per kW of rated DC size, capped at 15 kW (so at most 2 025 USD) | Existing single-family homes in the Houston Electric territory; through a participating service provider, as "a credit on your installation invoice"; interconnection agreement | verified |
| INC-32 | office measures | Commercial Standard Offer Program | "financial incentives for the installation of efficient measures in new or retrofit applications. Eligible measures include lighting, HVAC, chillers, motors, refrigeration, renewables, and other custom projects"; 2026 budget 7.415 million USD in incentives. Rates per kW and per kWh are in program workbooks that were not opened | project sponsor applies | program verified; amount unverified |
| INC-33 | `CTRL_TSTAT` | Smart thermostat discounts (online marketplace; Retail Electric Provider Smart Thermostat program) | amount not stated in the documents opened | | unverified (amount) |
| INC-34 | `DHW_HPWH`, `HVAC_HP` | Midstream program (HVAC and heat pump water heater distributors) | paid to distributors; already inside the price the customer sees | none for the customer | not an entry in a customer's breakdown |

CenterPoint's general efficiency page (https://www.centerpointenergy.com/en-us/savings-solutions/energy-efficiency) lists gas-appliance, insulation and window rebates "for Minnesota gas customers". Those do not apply in Houston and must not be scraped into the registry.

### INC-40 Computing an incentive amount

```
amount = rate * quantity,  capped at  cap  and at the installed cost
```

with quantity in the program's own unit: sq ft (1 m2 = 10.7639 sq ft), tons of cooling capacity (1 ton = 12 000 Btu/h = 3.5169 kW), units, kW DC, or first-year kWh saved.

- The low/expected/high of a per-kWh incentive follows the savings range; a per-area or per-unit incentive is a single number repeated three times.
- Example 1 (INC-10): 150 m2 low-slope cool roof, SRI 86, Los Angeles home: 150 * 10.7639 = 1 614.59 sq ft * 0.60 = **968.75 USD**, paid after installation.
- Example 2 (INC-18): office HVAC measure saving 40 000 kWh/yr (low 30 000, high 50 000) of cooling energy: 0.60 * 40 000 = **24 000 USD** (low 18 000, high 30 000), subject to pre-approval.
- Example 3 (INC-31): 8 kW DC home PV in Houston: 135 * 8 = **1 080 USD** off the invoice; a 20 kW system is capped at 135 * 15 = 2 025 USD.
- Tool: `utility_incentives(measure: MeasureResult, utility: str, sector: str, params: dict) -> list[Incentive]`; registry data in `backend/analysis/data/incentives.json` with fields `id`, `name`, `kind`, `rate`, `unit`, `cap`, `conditions`, `status`, `citation`, `date_checked`.

## 5. COST: measure cost data and useful life

Sources opened (all 2026-11-14):

| Short name | Reference |
|---|---|
| LBNL-2021 | Less, B. D., Walker, I. S., Casquero-Modrego, N. and Rainer, L. I., *The Cost of Decarbonization and Energy Upgrade Retrofits for US Homes*, Lawrence Berkeley National Laboratory, August 2021, doi:10.20357/B7FP4D. 1 739 projects, 6 165 costed measures, costs normalised to 2019 USD. Its Table 13 also quotes the NREL National Residential Efficiency Measures Database (REMDB) values beside its own |
| EIA-2023 | U.S. Energy Information Administration, *Updated Buildings Sector Appliance and Equipment Costs and Efficiencies*, released 23 March 2023 (contractor reports by Guidehouse and Leidos), https://www.eia.gov/analysis/studies/buildings/equipcosts/pdf/full.pdf. Costs in 2022 USD, with average equipment life |
| NREL-2023 | Ramasamy, V. et al., *U.S. Solar Photovoltaic System and Energy Storage Cost Benchmarks, With Minimum Sustainable Price Analysis: Q1 2023*, NREL/TP-7A40-87303, September 2023 (now served from https://docs.nlr.gov/docs/fy23osti/87303.pdf). 2022 USD |
| TTS-2024 | Barbose, G., Darghouth, N., O'Shaughnessy, E. and Forrester, S., *Tracking the Sun, 2024 Edition*, Executive Summary, Lawrence Berkeley National Laboratory, August 2024, https://eta-publications.lbl.gov/sites/default/files/2024-08/tracking_the_sun_2024_executive_summary.pdf. Systems installed in 2023 |
| PNNL-22656 | Wang, W., Katipamula, S., Ngo, H., Underhill, R., Taasevigen, D. and Lutes, R., *Advanced Rooftop Control (ARC) Retrofit: Field-Test Results*, PNNL-22656, 2013 |
| CEE-2014 | Center for Energy and Environment and PECI, *Advanced Rooftop HVAC Unit Controls Pilot*, final report for the Minnesota Department of Commerce, August 2014 |
| EPA-2008 | U.S. EPA, *Reducing Urban Heat Islands: Compendium of Strategies*, chapter "Cool Roofs", 2008 (draft), https://www.epa.gov/sites/default/files/2017-05/documents/reducing_urban_heat_islands_ch_4.pdf |
| BLS CPI | U.S. Bureau of Labor Statistics, CPI-U all items, series CUUR0000SA0, from the BLS public API: annual averages 2006 = 201.592, 2013 = 232.957, 2019 = 255.657, 2022 = 292.655; October 2026 = 337.511 |

Could not be opened: the NREL REMDB itself (`remdb.nrel.gov` no longer resolves; `remdb.nlr.gov` serves only a script shell), so REMDB values appear only as quoted in LBNL-2021 Table 13; the full Tracking the Sun report and its data file (`emp.lbl.gov` returned HTTP 403), so only the 2024 executive summary was read and no 2025 edition was found.

### COST-00 Bringing source costs to the base date

```
cost_2026 = cost_y * CPI(Oct 2026) / CPI(y)
```

Factors: from 2006, 1.6742; from 2013, 1.4488; from 2019, 1.3202; from 2022, 1.1533.

- Limits: CPI-U measures general consumer prices, not construction prices; LBNL-2021 itself used a construction index (RSMeans) to reach 2019. Installed costs in Los Angeles in particular may exceed these national figures. PV prices are not adjusted (TTS-2024 reports falling real prices), which is a project judgement [J].
- Range rule when a source gives only a central value [J]: low = 0.75 x, high = 1.5 x. Retrofit cost distributions are skewed to the high side (LBNL-2021 reports interquartile ranges such as 4 000 to 9 000 USD around a 5 930 USD median for central air conditioners).
- Every `FinancialBreakdown.cost_source` string names the source, its dollar year and "CPI-U adjusted to Oct 2026".
- Example: attic insulation at 1.91 USD/ft2 (2019): 1.91 * 337.511 / 255.657 = 2.52 USD/ft2 = 27.14 USD/m2.
- Tool: `adjust_cost(value, from_year: int) -> float`; table `CPI_FACTORS`.

### COST-01 Installed cost by measure

All figures are installed cost (materials and labour) before incentives, in October 2026 USD after COST-00, unless marked. "Src value" is what the source prints. Conversions: 1 m2 = 10.7639 ft2; 1 ton = 3.5169 kW of cooling capacity.

| Measure ID | Unit | Low | Expected | High | Src values and year | Source (second source) | Status |
|---|---|---|---|---|---|---|---|
| `ENV_ATTIC` | USD per m2 of attic floor | 20.75 | 27.14 | 40.93 | 1.46 / 1.91 / 2.88 USD/ft2, 2019. Blown insulation on the attic floor, median R-44 | LBNL-2021 section 10.3 and Table 13 (REMDB as quoted there: 1.90 USD/ft2 for R-38 blown cellulose) | [V], two sources agree |
| `ENV_WALL` | USD per m2 of wall treated | 24.16 | 31.83 | 41.21 | 1.70 / 2.24 / 2.90 USD/ft2, 2019. Cavity fill of existing walls; exterior insulation with new cladding is 5 to 10 times more and is not this measure | LBNL-2021 Table 13: 2.24 (1.70 to 2.53) (REMDB as quoted: 2.20, range 1.40 to 2.90, R-13 cellulose) | [V], two sources agree |
| `ENV_AIRSEAL` | USD per m2 of conditioned floor | 4.83 | 7.67 | 17.05 | 0.34 / 0.54 / 1.20 USD/ft2, 2019, for about 20 %, 40 % and (REMDB) 33 % leakage reduction | LBNL-2021 Table 13 and section 10.2 (whole-job 600 to 900 USD); REMDB as quoted is higher (1.20 to 2.80), used as the high | [V]; the two sources disagree by a factor of 2 to 4, so the range is wide |
| `WIN_REPLACE` | USD per m2 of window | 554 | 625 | 696 | 39 / 44 / 49 USD/ft2, 2019 | REMDB as quoted in LBNL-2021 Table 13 (39 to 49 USD/ft2, double glazed argon); LBNL-2021: 626 to 674 USD per window, about 39 USD/ft2 for a 4 ft by 4 ft unit. Expected is the midpoint [J] | [V] |
| `WIN_FILM` | USD per m2 of glass | - | - | - | none | no source opened | **[U]**, see section 9 |
| `WIN_SHADE` | USD per m2 of glass | - | - | - | none | no source opened | **[U]**, see section 9 |
| `ROOF_COOL` | USD per m2 of roof (field-applied coating on a sound low-slope roof) | 13.52 | 20.27 | 27.03 | 0.75 / 1.125 / 1.50 USD/ft2, 2006, "materials and labor, which includes routine surface preparation"; expected is the midpoint [J]. A cool single-ply membrane re-roof is 1.50 to 3.00 USD/ft2 (2006), of which only 0 to 0.20 USD/ft2 is the cool premium | EPA-2008 section 3.3, quoting a 2006 report (no second source) | [V] but old; one source |
| `HVAC_HP` | USD per ton of capacity (USD per kW: divide by 3.5169) | 2 668 | 4 472 | 5 805 | low: 6 940 USD for a 3-ton split system, 2022 (EIA-2023, 2023 "typical" and ENERGY STAR level). Expected: 3 387 USD/ton, 2019, median of 642 installs. High: 4 397 USD, 2019, median one-ton-class ductless system | EIA-2023 "Residential Air-Source Heat Pumps"; LBNL-2021 section 10.1.1 and Table 13 | [V], two sources; field data run about 65 % above the EIA engineering estimate |
| `HVAC_RTU` | USD per ton, full replacement, 7.5-ton class | 2 090 | 2 297 | 2 713 | 151 / 166 / 196 USD per kBtu/h, 2022: 2023 typical, ENERGY STAR v4.0, and high-efficiency | EIA-2023 "Commercial Rooftop Air Conditioners" (no second source) | [V], one source |
| `HVAC_ECON` | USD per rooftop unit (advanced controller with variable-speed fan and economizer control) | 4 274 | 6 044 | 7 088 | 2 950 / 4 172 / 4 892 USD, 2013: controller 2 200 (5 tons or less) to 4 142 (20 to 25 tons) plus 750 labour; 4 172 is the field-test average | PNNL-22656 Table ES-1 (CEE-2014: 3 265 USD per unit over 27 units, inside the range) | [V], two sources agree |
| `HVAC_DUCT` | USD per home | 781 | 1 042 | 1 562 | 789 USD median, 2019, "remarkably stable" across leakage reductions; range by the COST-00 rule | LBNL-2021 section 10.1.4 (no second source) | [V], one source |
| `DHW_HPWH` | USD per unit installed | 2 572 | 3 728 | 5 054 | low: 2 230 USD, 2022, top of EIA's installed range. Expected: 2 824 USD, 2019, median. High: 3 828 USD, 2019, 80-gallon median | EIA-2023 "Residential Heat Pump Water Heaters" (range 870 to 2 230); LBNL-2021 section 10.5 (50-gallon median 2 242; REMDB as quoted 2 000, range 1 400 to 2 600) | [V], two sources; replacing a gas unit usually adds electrical work, which the high is meant to cover |
| `LGT_LED` (office) | USD per 4-ft luminaire of about 5 000 lm | 214 | 390 | 517 | 185.54 / 338.08 / 448.60 USD, 2022. Expected and high are the printed "Total Installed Cost" for 2022 typical and high. Low is the printed typical luminaire price 152.54 plus 0.5 h at 66 USD/h; the source's own total is larger than its components, an inconsistency noted here | EIA-2023 "Commercial 4-ft Linear LED Luminaire to Replace 2-Lamp Systems" (no second source) | [V], one source |
| `LGT_LED` (home) | USD per lamp | 4.80 | 9.08 | 13.62 | expected: 6.88 USD per LED bulb, 2019. Low: 4.80 USD per 800-lumen LED (REMDB as quoted, not adjusted). High by the COST-00 rule | LBNL-2021 Table 13 | [V] |
| `LGT_CTRL` | USD per controlled fixture (occupancy sensor) | 168 | 224 | 336 | 161.34 USD sensor price, 2022, plus 0.5 h at 66 USD/h = 194.34; range by the COST-00 rule | EIA-2023 "Commercial 4-ft T8 ... with Occupancy Sensor" (no second source). Networked systems cost more; GSA's GPG-037 finding (2018) is that controls must cost about 70 USD per fixture for a 10-year payback at 0.11 USD/kWh | [V] component prices, one source |
| `PLUG_MGMT` | USD per workstation | - | - | - | none | no source opened | **[U]**, see section 9 |
| `CTRL_TSTAT` | USD per thermostat installed | 234 | 312 | 467 | 236 USD connected thermostat, 2019; range by the COST-00 rule | LBNL-2021 Table 13 (REMDB as quoted: 170 USD for a programmable, not connected, thermostat) | [V], one source for the connected type |
| `PV_ROOF` (home) | USD per W DC, not CPI-adjusted | 2.68 | 4.20 | 5.20 | low: NREL modelled market price for an 8 kW system, Q1 2023 (2022 USD); NREL states its benchmark sits near the 20th percentile of reported prices. High: top of the range of state median prices for 2023 installs (3.2 to 5.2 USD/W). Expected: midpoint of that range [J] | NREL-2023 Table 3; TTS-2024 executive summary (LBNL-2021 appendix G: 2 795 USD/kW in 2019 to 2020) | [V] for low and high; expected is a judgement |
| `PV_ROOF` (office, under 100 kW) | USD per W DC, not CPI-adjusted | 2.60 | 3.35 | 4.10 | range of state median prices for small non-residential systems installed in 2023; expected is the midpoint [J] | TTS-2024 executive summary (no second source) | [V] range, one source |
| `PV_ROOF` (office, 100 kW and above) | USD per W DC, not CPI-adjusted | 1.80 | 2.20 | 2.60 | range of state median prices for large non-residential systems installed in 2023 | TTS-2024 executive summary | [V] range, one source |
| `LAYOUT` | USD | 0 | 0 | 0 | defined as zero cost in SPEC 6.4 | SPEC | n/a |

Operation and maintenance (`annual_om_change_usd`): zero by default for every measure that replaces like with like (EIA-2023 gives 20 to 150 USD/yr for a residential heat pump, 20 USD/yr for a heat pump water heater and 370 USD/yr for a 7.5-ton rooftop unit, the same order as the equipment they replace). `PV_ROOF` adds 35.01 USD per kW DC per year (NREL-2023 Table 3: 30.36 USD/kWdc/yr, 2022 USD, residential modelled market price; CPI-adjusted). Whether that figure already covers inverter replacement was not checked, so no separate replacement cost is added by default and the output says so.

Measures with no verified cost (`WIN_FILM`, `WIN_SHADE`, `PLUG_MGMT`): the tool returns the measure with savings but `finance = None` and the warning "no verified cost source; get a quote", and the budget algorithm skips it with reason `no_cost_data` (SPEC 6.5), unless the user types in a quote. They are never given a made-up cost.

- Worked example: `ENV_ATTIC` on a 120 m2 attic: 120 * (20.75, 27.14, 40.93) = **2 490 / 3 257 / 4 912 USD**. Check from source units: 120 m2 = 1 291.67 ft2; 1 291.67 * 1.91 * 1.3202 = 3 257 USD. With the LADWP rebate INC-17 (0.50 USD/ft2 above R-19): 645.83 USD paid after installation.
- Worked example: `HVAC_HP`, 3 tons: 3 * (2 668, 4 472, 5 805) = **8 004 / 13 416 / 17 415 USD**.
- Worked example: `PV_ROOF`, 6 kW DC home: 6 000 * (2.68, 4.20, 5.20) = **16 080 / 25 200 / 31 200 USD**; O&M 6 * 35.01 = 210 USD/yr.
- Tool: `measure_cost(measure_id: MeasureId, quantity: float, sector: str) -> tuple[Ranged, str]` returning the installed cost and the `cost_source` string; data in `backend/analysis/data/costs.json` with fields `measure_id`, `sector`, `unit`, `low`, `expected`, `high`, `source`, `source_year`, `cpi_factor`, `status`.

### COST-02 Useful life

| Measure ID | Useful life, years | Basis | Status |
|---|---|---|---|
| `HVAC_HP` | 15 | EIA-2023: average life 15.3 years (Weibull, scale 15.88, shape 2, delay 1) | [V] |
| `DHW_HPWH` | 15 | EIA-2023: average life 15.1 years (2022 units; "assume same lifetime as electric resistance water heaters"); 13 years for older stock | [V] |
| `HVAC_RTU` | 21 | EIA-2023: average life 21 years | [V] |
| `LGT_LED` (office) | 15 | EIA-2023: 53 000 hours typical life at 3 431 h/yr = 15.4 years (50 000 hours for the high-efficacy product = 14.6 years) | [V] |
| `ROOF_COOL` | 20 | EPA-2008: "when applied properly, many cool roof coatings have been shown to last more than 20 years"; badly applied coatings fail "within a couple of years" | [V] wording, optimistic; coating maintenance not costed |
| `PV_ROOF` | 25 | HB135 section 4.5.3 uses "a service life of 25 years" for a PV system in its example; no PV lifetime study was opened | [J] |
| `HVAC_ECON` | 15 | no source opened; limited by the remaining life of the rooftop unit it controls | [J], unverified |
| `ENV_ATTIC`, `ENV_WALL`, `WIN_REPLACE` | 25 | no source opened; LBNL-2021 runs its levelised-cost cases at 15 and 25 years | [J], unverified |
| `ENV_AIRSEAL`, `HVAC_DUCT` | 15 | no source opened; lower LBNL-2021 case | [J], unverified |
| `LGT_LED` (home), `LGT_CTRL`, `CTRL_TSTAT` | 10 | no source opened | [J], unverified |
| `WIN_FILM`, `WIN_SHADE`, `PLUG_MGMT` | 10 | no source opened | [J], unverified |
| `LAYOUT` | 5 | no source; a layout lasts until the next move | [J] |

The [J] lives are placeholders that must be replaced from a published effective-useful-life table (for example the California DEER tables or a state technical reference manual) before the numbers are presented as sourced; they are repeated in section 9. Because analysis period N follows useful life (ECO-05), a wrong life moves NPV and SIR but not the ranking, simple payback or first-year figures.

- Tool: `useful_life(measure_id: MeasureId, sector: str) -> tuple[int, str]` (years, status).

## 6. MV: measurement and verification for a savings guarantee

Sources opened (2026-11-14):

| Short name | Reference |
|---|---|
| FEMP-MV4 | U.S. DOE Federal Energy Management Program, *M&V Guidelines: Measurement and Verification for Performance-Based Contracts*, Version 4.0, November 2015, https://www.energy.gov/sites/default/files/2016/01/f28/mv_guide_4_0.pdf. It states that its four options originate in the IPMVP and reproduces the ASHRAE Guideline 14 calibration tolerances |
| BPA-EMP | Bonneville Power Administration, *Verification by Meter-Based Energy Modeling Protocol*, September 2024, https://www.bpa.gov/-/media/Aep/energy-efficiency/measurement-verification/7-bpa-mv-energy-modeling-protocol.pdf. Reproduces the change-point model forms and the fractional savings uncertainty formula of ASHRAE Guideline 14, Annex B |
| BPA-REG | Bonneville Power Administration, *Regression for M&V: Reference Guide*, Version 3.0, May 2024, https://www.bpa.gov/-/media/Aep/energy-efficiency/measurement-verification/3-bpa-mv-regression-reference-guide.pdf |

Not opened: ASHRAE Guideline 14-2014 (and its 2023 edition) and the IPMVP Core Concepts document of the Efficiency Valuation Organization are sold or gated; everything attributed to them below is as reproduced in the three open documents above, and is marked so.

### MV-01 The savings equation and the four IPMVP options

```
Savings = (Baseline Energy - Post-Installation Energy) +/- Adjustments
```

(FEMP-MV4 section 2.1, Equation 2.1.) Savings are never measured directly; they are the difference between what the building would have used under reporting-period conditions (the adjusted baseline) and what it did use.

| Option | Name | What is measured | When it applies | Measures in SPEC 6.2 it suits |
|---|---|---|---|---|
| A | Retrofit isolation, key parameter measurement | The key performance parameter (for example fixture power) is measured; other factors (for example operating hours) are estimated and stipulated | Savings potential is mostly a property of the equipment; the customer accepts stipulated operating factors; lowest cost, highest uncertainty | `LGT_LED`, `PLUG_MGMT`, `DHW_HPWH` (rated performance times stipulated use) |
| B | Retrofit isolation, all parameter measurement | Energy use of the affected system is measured, short-term or continuously, before and after | A system can be sub-metered and its load varies | `HVAC_RTU`, `HVAC_ECON`, `HVAC_HP`, `PV_ROOF` (production meter) |
| C | Whole facility | Utility meter or sub-meter data for the whole building, with regression against weather and other drivers | FEMP-MV4 section 4.4: savings "greater than about 10% to 20% of the overall consumption measured by the utility or submeter on a monthly basis"; "At least 12 (preferably 24) months" of pre-installation data; "At least 9 (preferably 12) months" of reporting-period data; other loads on the meter stable or tracked. Useful for "multiple interactive ECMs" and for "insulation or other building envelope measures" that cannot be measured directly | A plan with several interacting measures; `ENV_*`, `WIN_*`, `ROOF_COOL`, `CTRL_TSTAT` |
| D | Calibrated simulation | A simulation model calibrated to metered data stands in for the baseline or the post case | No baseline meter data exists, or measures cannot be separated; the model must meet the MV-04 calibration tolerances | Any plan for which the zone model is calibrated to twelve months of bills (`BaselineResult.calibrated_to_bills`) |

- Guarantee rule for the product: the savings guarantee document names one option per measure from the last column; if the plan's expected savings are below 10 % of metered whole-building use, Option C is not offered for it (the signal is too small to see on the bill) and the guarantee falls back to Option A or B per measure.
- Primary: FEMP-MV4 sections 2.1 and 4.1 to 4.5, Table 4-1 [V]. Second source: BPA-EMP (states that it follows IPMVP Option C for whole-building models and Option B for system-level models, and treats a baseline of less than one year as an exception needing care) [V]. The IPMVP itself was not opened [U beyond what these documents reproduce].
- Tool: `mv_option_for(measure_id: MeasureId, plan_savings_fraction: float, has_12_months_bills: bool) -> Literal["A","B","C","D"]`.

### MV-02 Baseline regression models with weather normalisation

```
2P (linear):                 E = b0 + b1 * T
3P cooling (change point):   E = b0 + b1 * (T - Tb)+
3P heating:                  E = b0 + b1 * (Tb - T)+
4P:                          E = b0 + b1 * (Tb - T)+ + b2 * (T - Tb)+          (two slopes, one change point)
5P:                          E = b0 + b1 * (Tbh - T)+ + b2 * (T - Tbc)+        (heating and cooling change points, Tbh <= Tbc)
degree-day form:             E_month = b0 * days + b1 * HDD(Tbh) + b2 * CDD(Tbc)
(x)+ = x if x > 0, else 0
```

| Symbol | Meaning | Unit |
|---|---|---|
| E | energy use per day in the billing period (period use divided by days) | kWh/day |
| T | mean outdoor dry-bulb temperature over the same period | degC |
| Tb, Tbh, Tbc | change-point (balance) temperatures, fitted | degC |
| b0 | base load | kWh/day |
| b1, b2 | weather slopes | kWh/(day K) |
| HDD(Tb), CDD(Tb) | degree days of the period to base Tb, from daily mean temperatures | K day |

- Fitting: for each candidate change point on a 0.5 K grid (10 to 26 degC), fit the remaining coefficients by ordinary least squares; keep the candidate with the smallest sum of squared errors. Number of parameters p counts the change points (3P model: p = 3).
- Model choice: gas with space heating, 3P heating; electricity with cooling only, 3P cooling; electricity with electric heating and cooling, 5P; choose the simplest model that passes MV-03. A slope with the wrong sign (cooling slope negative) rejects the model.
- With monthly mean temperatures the 3P form and the degree-day form differ only by within-month variation; when daily temperatures are available the degree-day form at the fitted base is preferred because it keeps that variation.
- Normalised savings: evaluate baseline and reporting-period models on the same typical-year weather (the weather file in `ClimateSite`), so that a hot year does not hide or inflate savings. Avoided energy use: evaluate the baseline model on the reporting period's actual weather and subtract metered use (this is the form MV-05 applies to).
- Validity: at least 12 monthly points for the baseline (MV-01); extrapolation beyond the temperature range seen in the baseline is flagged.
- Primary: BPA-EMP section 3 (two-, three-, four- and five-parameter change-point models, with the (x)+ notation) [V]. Second source: BPA-REG section 4.3 and FEMP-MV4 section 4.4 (regression on heating degree days) [V]. The original formulation (ASHRAE Inverse Model Toolkit, research project RP-1050) is cited by BPA-REG and was not opened [U].
- Worked example (monthly electricity, 12 points): T = 12, 14, 18, 21, 25, 28, 29, 29, 27, 22, 17, 13 degC; E = 31.0, 29.2, 30.5, 36.3, 48.4, 54.6, 58.6, 56.8, 52.8, 39.1, 30.6, 29.6 kWh/day. Grid search gives Tb = 18.5 degC, **b0 = 30.161 kWh/day, b1 = 2.632 kWh/(day K)**, sum of squared errors 5.827. Closed-form simple regression at Tb = 18.5 and `scipy.stats.linregress` both give 30.1613 and 2.6323.
- Tool: `fit_change_point(temps_c: list[float], energy_per_day: list[float], kind: Literal["2P","3PC","3PH","4P","5P"]) -> ChangePointModel` (fields `b0`, `b1`, `b2`, `tb_heat`, `tb_cool`, `p`, `n`); `predict(model, temps_c) -> list[float]`; `degree_days(daily_mean_c: list[float], base_c: float, kind) -> float`.

### MV-03 Goodness-of-fit statistics

```
RMSE       = sqrt( sum_i (E_i - Ehat_i)^2 / (n - p) )
CV(RMSE)   = RMSE / mean(E)
NMBE       = sum_i (E_i - Ehat_i) / ((n - p) * mean(E))
NDBE       = sum_i (E_i - Ehat_i) / sum_i E_i
R2         = 1 - sum_i (E_i - Ehat_i)^2 / sum_i (E_i - mean(E))^2
t_k        = b_k / se(b_k)
```

| Symbol | Meaning |
|---|---|
| E_i, Ehat_i | measured and model-predicted energy for point i |
| n, p | number of points; number of model parameters |
| NMBE, NDBE | normalised mean bias error; net determination bias error (identical when p is set to 0) |

Acceptance criteria used by the product for a monthly baseline regression:

| Statistic | Criterion | Where it comes from |
|---|---|---|
| CV(RMSE) | <= 15 % for monthly data (<= 30 % for hourly data) | ASHRAE Guideline 14 tolerances as reproduced in FEMP-MV4 Table 4-2 ("Data in this table taken from ASHRAE Guideline 14 ... Section 5.3.3.3.10"); that table is written for calibrated simulation and is applied here to the regression baseline as well [J for that extension]; BPA-REG calls "10% or 15%" the usual reading of a low value |
| Bias (NMBE) | within +/- 5 % monthly (+/- 10 % hourly) | same table. An ordinary least-squares fit with an intercept has zero bias by construction; BPA-REG reports that Guideline 14-2014 accepts a regression when net determination bias is below 0.005 % |
| R2 | > 0.75 as a rule of thumb, not a pass or fail test | BPA-REG section 5.1.1 |
| t-statistic of each weather slope | absolute value above the two-sided critical t at 95 % (about 2 for large n) | BPA-REG section 5.2.2 |
| Fractional savings uncertainty | <= 50 % at 68 % confidence | MV-05 |

- Primary: FEMP-MV4 section 4.5.3.2, equations 4-1 to 4-4 and Table 4-2 [V]. Second source: BPA-REG sections 5.1 and 5.2, BPA-EMP section 5.5 (CV(RMSE) with n - p in the denominator) [V]. ASHRAE Guideline 14 itself not opened [U beyond the reproductions].
- Worked example (the MV-02 fit): RMSE = sqrt(5.827 / 9) = 0.805 kWh/day; mean(E) = 41.458; **CV(RMSE) = 1.94 %**; NMBE = 0.000 %; R2 = 0.9962; slope t = 48.8. Passes. (`numpy` least squares and the closed-form formulas agree on every figure.)
- Tool: `fit_statistics(measured: list[float], predicted: list[float], p: int) -> FitStats` (fields `rmse`, `cv_rmse`, `nmbe`, `ndbe`, `r2`); `model_acceptable(stats: FitStats, interval: Literal["monthly","hourly"]) -> tuple[bool, list[str]]`.

### MV-04 Calibration tolerances for the simulation model (Option D)

| Calibration data | Bias (MBE) | CV(RMSE) |
|---|---|---|
| Monthly | within +/- 5 % | <= 15 % |
| Hourly | within +/- 10 % | <= 30 % |

- These are the tolerances the zone model must meet against twelve months of bills before `calibrated_to_bills` is set to true. FEMP-MV4 defines MBE with simulated minus measured in the numerator; sign convention does not affect the test.
- Primary: FEMP-MV4 Table 4-2 [V]. Second source: BPA-REG section 5.1 (same indices) [V].
- Statistics for the calibration test: MV-03 with p = 0. FEMP-MV4 equation 4-1 divides the summed differences by the summed measured values, and the text of equation 4-2 divides the squared differences by "the number of points"; the simulation's inputs are not regression parameters [V 2026-11-14]. Bills against simulation are compared as calendar months, January first, `BaselineResult.monthly_*` against `UtilityBills.*` (in kWh, gas in kWh of higher heating value).
- Tool: `calibration_ok(measured_monthly: list[float], simulated_monthly: list[float]) -> tuple[bool, FitStats]`.

### MV-05 Savings and savings uncertainty

```
E_save   = sum over the m reporting points of (Ehat_baseline(T_i) - E_measured_i) * days_i
F        = E_save / sum_i Ehat_baseline(T_i) * days_i
FSU      = dE_save / E_save = t * 1.26 * CV(RMSE) * sqrt( (1 + 2/n) * (1/m) ) / F          (uncorrelated residuals: monthly data)
with autocorrelated residuals (daily, hourly):  replace sqrt(...) by sqrt( (n/n') * (1 + 2/n') * (1/m) ),  n' = n (1 - rho)/(1 + rho)
```

| Symbol | Meaning | Unit |
|---|---|---|
| E_save | avoided energy use over the reporting period | kWh |
| F | savings fraction of the adjusted baseline | dimensionless |
| FSU | fractional savings uncertainty, the half-width of the confidence interval divided by the savings | dimensionless |
| t | Student's t for the chosen two-sided confidence and n - p degrees of freedom | dimensionless |
| n, m | points in the baseline period and in the reporting period | - |
| rho | lag-1 autocorrelation coefficient of the baseline residuals (may be ignored below 0.5, BPA-REG citing Guideline 14 Annex D) | - |

- Acceptance: "the level of uncertainty must be less than 50% of the annual reported savings, at a confidence level of 68%" (BPA-EMP section 5.5, describing ASHRAE Guideline 14). The product reports FSU at 68 % (the test) and at 90 % (for the guarantee wording).
- Use in the guarantee: guaranteed savings should not exceed E_save,expected * (1 - FSU_90), so that a shortfall smaller than the measurement noise cannot trigger a claim. This is a drafting rule of the product [J], consistent with FEMP-MV4 section 5.3 ("uncertainty is often estimated to set the overall level of savings guarantee").
- Other error sources (meter accuracy, sampling, stipulated values) combine with the model term in quadrature: SE_project = sqrt(SE_measurement^2 + SE_sampling^2 + SE_estimation^2 + SE_modeling^2) (FEMP-MV4 section 5.3) [V].
- Validity: the constant 1.26 is an empirical coefficient from the Guideline 14 formula; BPA-EMP gives a refinement Y = -0.00022 m^2 + 0.03306 m + 0.94054 for monthly data (Y = 1.306 at m = 12, close to 1.26). Before the retrofit, F is the predicted savings fraction, which lets the tool tell the user in advance whether a whole-building guarantee is verifiable.
- Primary: BPA-EMP section 5.5 (formula printed with every symbol defined, attributed to ASHRAE Guideline 14 Annex B) [V]. Second source: BPA-REG section 2.5 (definition of FSU; cites Guideline 14-2014 section B4) and FEMP-MV4 section 4.1 (points to Guideline 14 Appendix B.2) [V]. Guideline 14 not opened [U beyond the reproduction].
- Worked example (continuing MV-02 and MV-03; reporting year with T = 13, 15, 17, 22, 26, 29, 30, 28, 26, 21, 16, 12 degC and metered use about 15 % below the old relation): adjusted baseline 15 236.4 kWh, measured 12 960.4 kWh, **E_save = 2 276.0 kWh, F = 0.1494**. At 68 % confidence t(9 d.f.) = 1.0525: FSU = 1.0525 * 1.26 * 0.01941 * sqrt((1 + 2/12)/12) / 0.1494 = **0.054** (+/- 122 kWh), far inside the 50 % limit. At 90 % confidence t = 1.8331: FSU = 0.094 (+/- 213 kWh); guaranteed level at most 2 276 * (1 - 0.094) = 2 063 kWh. Script and step-by-step manual evaluation agree (0.05373).
- Tool: `avoided_energy(model, reporting_temps_c, reporting_energy_per_day, days) -> tuple[float, float]` (kWh saved, savings fraction); `fractional_savings_uncertainty(cv_rmse, n, m, p, savings_fraction, confidence=0.68, rho=0.0) -> float`; `guarantee_level(expected_savings: float, fsu_90: float) -> float`.

### MV-06 Calibration procedure: fitting the simulation to twelve monthly bills (Option D)

MV-04 is the acceptance test; this entry is how the model is brought to it. FEMP-MV4 section 4.5.3 describes calibration as "an iterative process of adjusting model inputs and recomparing the results to measured data", to be applied to "electricity (kilowatt-hours), demand (kilowatts), and all other fuels used", with whole-facility monthly data as "the minimum level of calibration" (4.5.3.4) [V]. It does not prescribe which inputs to adjust or how; the procedure below is this project's [J], built from the pieces the sources do give.

```
u_i in [-1, +1]        x_i(u) = x_exp + u (x_exp - x_low)  for u < 0;   x_exp + u (x_high - x_exp)  for u >= 0
minimise   sum_f sum_m ( (S_fm(x(u)) - M_fm) / (0.05 * mean_m M_fm) )^2  +  sum_i (1.2816 u_i)^2
subject to lb_i <= u_i <= ub_i   (lb = -1 unless x_low = x_exp, then 0;  ub = +1 unless x_high = x_exp, then 0)
```

| Symbol | Meaning |
|---|---|
| f, m | fuel with usable bills (electricity, gas); calendar month |
| M_fm, S_fm | billed and simulated energy of fuel f in month m, kWh |
| x_low, x_exp, x_high | the assumption's `Ranged` before calibration |
| 1.2816 | z of the 90th percentile; low and high are P10 and P90 (UNC-01), so 1.2816 u is the input's z-score |

Steps:

1. **Bills and fuels.** Twelve finite, non-negative values per fuel. Electricity is always calibrated; gas when gas bills are given. A fuel whose bills are positive while the model burns none of it (or the reverse) is not fitted and is reported as a fuel-assignment finding; `calibrated_to_bills` is then false. A month below a quarter of what the model's own seasonal shape gives it is reported as possible vacancy or an estimated read [J].
2. **Split into base load and weather (MV-02).** The bills of each fuel are fitted with the degree-day form on the daily means of the site's weather file: gas 3PH; electricity the valid one of 3PC, 3PH, 5P with the smallest residual variance (slopes positive with t > 2, BPA-REG 5.2.2), else base only. The simulation is fitted at the bills' balance points. Comparing the parts (base kWh/day, heating and cooling slopes, annual base, heating and cooling kWh) says which part of the model disagrees; the words of step 6 and the reason given for each move come from this comparison.
3. **Inputs that may move.** Only the uncertain inputs that drive the bill and that `set_assumption` carries into `Systems`: `occupancy.count`, `plug.ppd`, `lighting.lpd`, `dhw.uef`, `setpoint.heating`, `setpoint.cooling`, `infiltration.ach50` (homes), `infiltration.leakage_75pa` (offices), `hvac.heating_rating` or `hvac.heating_efficiency`, `hvac.cooling_rating`, `hvac.distribution_efficiency`. An input is used only when it is a `Ranged` with low < high, `user_editable`, and its source is not `user` or `measured` (a value someone gave or measured is not overruled by a bill). Each is run at its low and its high; it is dropped when it moves no billed fuel by 0.5 % of that fuel's annual bill, or when it moves an unbilled fuel (relative to the model's annual use of that fuel) more than any billed one, so that electricity bills do not quietly rewrite the gas side [J]. Excluded on purpose: envelope U-values and window properties (they live on the model's surfaces, built once from the bundle, and with twelve monthly points they cannot be told apart from infiltration and setpoints); `ventilation.outdoor_air_m3_s` (for offices it is derived from `occupancy.count`).
4. **Fit.** Bounded least squares on the objective above (scipy `least_squares`, trust-region reflective, forward differences with a step of 0.02 in u, at most 25 trust-region steps and 400 simulations including step 3, start at the expected values). The parameterisation makes it impossible for any input to leave its stated range. The second term is a prior: the monthly residual scale of 5 % of the mean monthly bill [J] and the range-based z-score put bills and prior knowledge in the same currency, so inputs the bills cannot separate (lighting and plug density, say) share the correction in proportion to their ranges instead of one being driven to an end. Deterministic: the same model and bills give the same values.
5. **Acceptance.** MV-04 monthly, per billed fuel: |NMBE| <= 5 % and CV(RMSE) <= 15 %. `calibrated_to_bills` is true only when every fuel with bills passes and no fuel was blocked in step 1. Then, and only then, every input that moved by more than 1 % of its range is written with `set_assumption(model, key, value, "measured")`: the contract has no "calibrated" source, and `measured` is the one that says the value now rests on metered data of this building; its confidence is lowered to 0.7 because it is inferred, not measured [J]. The range collapses to the fitted value; the original range, its source and the statistics before and after are kept in an added `EvidenceRef(kind="user", ref="bills.electricity_kwh+bills.gas_kwh", note=...)` (the bills came from the user). Inputs that did not move keep their range and source.
6. **When it fails.** The model is returned unchanged; the best in-range values are reported as a proposal. The report names the fuel, the best-fit NMBE and CV(RMSE), every month whose residual exceeds 15 % of the mean month, the part of step 2 that the in-range model cannot reach (with the usual causes: a constant load such as a pool pump, an electric vehicle or a second refrigerator; a steeper cooling slope from a failing or undersized air conditioner; resistance heat; partial vacancy), and the inputs that sit at an end of their range. A consultant reads such a result as a missing piece of the model, not as a reason to widen the ranges.
7. **Savings uncertainty on the calibrated model.** MV-05 with n = 12, the CV(RMSE) of the calibrated model against the bills recomputed with n - p, p = the number of inputs the calibration moved (at least 1, at most 10) [J: Guideline 14's formula is written for a regression baseline; counting each tuned input as a fitted parameter is the conservative reading]. Reported at 68 % (the 50 % acceptance test) and 90 % (the guarantee wording). An uncalibrated model gives no verifiable savings.

- Limits. (a) Weather: FEMP-MV4 4.5.3.1 says "the first step in calibrating a model is updating and running the model using weather data that correspond precisely to the same calendar days as each utility bill" and that average weather files "are not suitable" [V]. The product compares the bills with the site's typical year, because `UtilityBills` carries no billing dates and the data layer serves a typical year; every calibration says so in its warnings, and a hot or mild billing year appears as a seasonal residual. (b) Bills of a building with existing rooftop solar are net of the array's output, which the baseline does not model; the result says so. (c) Calibration does not identify individual inputs when several share a signature (the synthetic tests recover inputs with distinct signatures to within 10 % of their range, and move every perturbed input toward its true value when all are free); the bills fix the sum, the prior fixes the split.
- Primary: FEMP-MV4 sections 4.5.1.3, 4.5.3, 4.5.3.1, 4.5.3.2 (equations 4-1 to 4-4), 4.5.3.4 and Table 4-2 [V]. Second source: BPA-EMP section 3 (change-point forms used in step 2) and section 5.5 (FSU, step 7); BPA-REG section 5.2.2 (t test) [V]. The optimisation, the prior, the 5 % residual scale, the screening thresholds and the provenance rules are this project's [J]; ASHRAE Guideline 14 and the IPMVP were not opened [U].
- Worked example (synthetic, golden house of `specs/examples/house/`, bills simulated with `plug.ppd` 6.5, `setpoint.heating` 21.0, `hvac.cooling_rating` 11.0 against expected 5.0, 21.7, 13.0, those three inputs free): before, electricity NMBE +11.2 % (model below the bills), CV(RMSE) 12.0 %; gas NMBE -12.4 % (model above), CV(RMSE) 13.2 %; both fail on bias. After 32 simulations (1.3 s): both fuels |NMBE| < 0.2 % and CV(RMSE) < 0.3 %, recovered values 6.51, 21.01 and 11.08 (test `test_recovers_identifiable_inputs_on_the_house`). Impossible case: the same house with 350 kWh a month added to the electricity bills (an unmodelled electric vehicle): electricity NMBE +43.5 % before, best in-range fit +18.0 % with CV(RMSE) 19.9 % and six inputs at an end of their range; the electricity base part is flagged as 2 348 kWh a year beyond reach, and the model is left unchanged (test `test_impossible_bills_stay_uncalibrated_with_a_clear_warning`). Figures from the scratch script and from the tests agree; they move if the A2 or A3 physics changes, the tests' tolerances do not.
- Tool: `calibrate_to_bills(bundle, model, bills, simulate, set_assumption, outdoor_temp_c=None, *, keys=None, max_simulations=400, apply_when_uncalibrated=False) -> CalibrationResult` in `backend/analysis/physics/calibration/`; `CalibrationResult.savings_uncertainty(fuel, savings_kwh) -> SavingsUncertainty`.

---

## 7. UNC: uncertainty propagation

Reference: Joint Committee for Guides in Metrology, *Evaluation of measurement data: Guide to the expression of uncertainty in measurement*, JCGM 100:2008 (GUM 1995 with minor corrections), https://www.bipm.org/documents/20126/2071204/JCGM_100_2008_E.pdf [V 2026-11-14]. The Monte Carlo supplement JCGM 101:2008 was not opened; the Monte Carlo run below is only this spec's own cross-check.

### UNC-01 What low, expected and high mean

- For an input (an `Assumption` with a `Ranged` value): **expected** is the best single estimate; **low** and **high** are values the true quantity is judged to fall below, respectively above, with about 10 % probability each. So [low, high] is an approximate 80 % interval, and the two sides may be unequal.
- For an output: **expected** is the model run with every input at its expected value (not a mean). **low** and **high** are the range that the input ranges produce through UNC-02. The contract invariant low <= expected <= high holds by construction.
- What the output range is not: it is not a measured 80 % interval and must not be described as one, to users or in the documents. UNC-02 carries only the uncertainty of the listed inputs, combined as if the groups were independent; it leaves out model-form error and correlations outside the groups below. Any text that explains it must call it the range from the uncertain inputs, not a likely or guaranteed range.
- Measured coverage (#394, 2026-11-15, after review fixed a wind-speed unit error and an eval adapter that leaked example-property data into the test buildings): on 494 non-residential buildings with hourly meters (Building Data Genome Project 2, 5 US sites, annual 2017 electricity), the baseline's annual electricity range, without calibration to bills, contained the metered value for 12.8 % of buildings (site-clustered 90 % CI 10.7 to 15.5 %), against the 80 % the 10th-to-90th reading would imply. The metered value fell below the range for 30.6 % and above it for 56.7 %: the range is too narrow, and the expected value runs low (median signed error -17.1 %; Lodging buildings far lower). The eval ran the defaults path (no scan geometry, no bills), and 398 of the 494 buildings sit in climate zones the default tables do not cover; bill-calibrated baselines and savings ranges were not measured.
- "Low" always means the numerically smaller value of that quantity, not the pessimistic case: low cost is good, low savings is bad. Text shown to users must say which.
- Source tables that give a minimum and maximum, or an interquartile range, are mapped to low and high as they stand, and the mapping is recorded in the assumption's evidence. This is a convention [J]; the 80 % reading is approximate.
- Policy parameters are not uncertain inputs and are not varied: discount rate, analysis period, incentive rules, emission factors. (Their effect is shown as separate sensitivity lines where ECO-05 says so.)
- Basis: JCGM 100 section 4.3 (a Type B evaluation assigns a distribution to an input from available information) and section 6 with Table G.1 (an interval is an estimate plus or minus a coverage factor times the standard uncertainty; k = 1.645 for 90 % under a normal distribution; the 80 % interval used here corresponds to k = 1.2816) [V; the 1.2816 value is the standard normal quantile computed with `scipy.stats.norm.ppf(0.9)`, it is not printed in Table G.1].

### UNC-02 One-at-a-time runs combined in quadrature

For an output y = f(x_1 .. x_N):

```
y_0    = f(expected values)
y_i^-  = f(x_i at low,  all others expected)          y_i^+ = f(x_i at high, all others expected)
dlo_i  = min(y_i^- - y_0, y_i^+ - y_0, 0)             dhi_i = max(y_i^- - y_0, y_i^+ - y_0, 0)
y_low  = y_0 - sqrt( sum_g (sum_{i in g} dlo_i)^2 )
y_high = y_0 + sqrt( sum_g (sum_{i in g} dhi_i)^2 )
```

where g runs over correlation groups: inputs in different groups are treated as independent (their effects add in quadrature), and inputs in the same group are treated as fully correlated (their effects add linearly). An input alone in its group gives the plain root-sum-square.

- Cost: 2N + 1 model runs. N is the number of `Ranged` assumptions that the output depends on; assumptions with low = high are skipped. A categorical assumption (string or boolean) is run at each alternative category and contributes its most negative and most positive deviation.
- Why min and max with zero: an input can move the output the same way at both ends (a non-monotonic response) or the "wrong" way round (a high price lowers payback). The rule sends each deviation to the side it actually falls on.
- Correlation groups (fixed list, `backend/config.py`):

| Group | Members | Reason |
|---|---|---|
| `price_level` | electricity price, gas price, export price | set by the same market and the same utility filings |
| `escalation` | electricity and gas escalation rates | both come from one EIA projection |
| `cost_level` | installed costs of all measures in a plan | same local labour market and contractor |
| `envelope_vintage` | wall, roof and window U-values and infiltration when all come from the same vintage default table | one construction-era guess drives all of them |
| (own group each) | every other assumption | treated as independent |

- Aggregation: plan totals (`Plan.total_annual_savings_usd`, `total_upfront_usd`, `total_co2_kg`) are computed by applying UNC-02 to the whole-plan function, never by adding the low values or the high values of the individual measures. Adding lows assumes everything goes wrong together and overstates the band; and measures share inputs, so their ranges are not independent either.
- Derived finance outputs (`npv_usd`, `simple_payback_years`, `net_cashflow_year1_usd`) are outputs like any other: each is evaluated in the same 2N + 1 runs.
- Validity: exact for a linear model with independent, roughly normal inputs, where it reproduces JCGM 100 equation (10) scaled by k = 1.2816; a good approximation when each input's effect is close to linear across its range and interactions are modest. It degrades for strongly non-linear outputs: payback when savings approach zero (then the high payback is reported as `None`, meaning "may never pay back"), and any output with a threshold. The unit tests compare UNC-02 with a 100 000-draw Monte Carlo on three reference buildings and fail if either bound differs by more than 10 % of the band width.
- Primary: JCGM 100:2008 section 5.1.2, equation (10), u_c^2(y) = sum_i (df/dx_i)^2 u^2(x_i) for uncorrelated inputs; section 5.1.3 Note 2: the contribution of input i "is evaluated numerically by calculating the change in y due to a change in x_i of +u(x_i) and of -u(x_i)"; section 5.2.2 Note 1: when all inputs have correlation coefficient +1 the combined uncertainty is the linear sum of the contributions [V].
- Second source: HB135 section 8.2 (sensitivity analysis: vary one input at a time and identify critical inputs) and 10 CFR 436.24 ("sensitivity and probabilistic analysis" for uncertain cost data) [V]. They support one-at-a-time analysis; the quadrature combination rests on JCGM 100.
- Worked example: annual bill savings y = a * b, with a = electricity saved (8 000 / 10 000 / 13 000 kWh) and b = price (0.118 / 0.133 / 0.160 USD/kWh), independent.
  y_0 = 1 330.00. Runs: a low 1 064, a high 1 729, b low 1 180, b high 1 600.
  dlo = (-266, -150); dhi = (+399, +270).
  y_low = 1 330 - sqrt(266^2 + 150^2) = 1 330 - 305.4 = **1 024.6 USD**; y_high = 1 330 + sqrt(399^2 + 270^2) = 1 330 + 481.8 = **1 811.8 USD**.
  Cross-check by independent means: Monte Carlo with 2 000 000 draws from two-piece normal distributions matched to each input's 10th and 90th percentiles gives P10 = 1 037.4 and P90 = 1 839.4 (differences of 1.2 % and 1.5 %; the Monte Carlo median is 1 370.8 because the inputs are skewed, while the contract's expected stays at 1 330.0 by definition). If a and b were in one correlation group the bounds would be 1 330 - 416 = 914 and 1 330 + 669 = 1 999 (the exact corners are 944 and 2 080).
- Tool: `propagate(f: Callable[[dict], float], assumptions: list[Assumption], groups: dict[str, str]) -> tuple[Ranged, list[SensitivityRow]]`, where `SensitivityRow` has `key`, `y_low_run`, `y_high_run`, `swing`, `share_low`, `share_high`.

### UNC-03 Sensitivity ranking used by the ask rule (SPEC 5.3)

Target output: the plan's total annual savings in USD, y, with the plan re-selected in every run (the budget algorithm of SPEC 6.5 is part of f).

```
swing_i   = | y_i^+ - y_i^- |                      USD/yr
w_i       = swing_i / y_0                           dimensionless, compared with ASK_WIDTH
share_i   = (dlo_i^2 + dhi_i^2) / sum_j (dlo_j^2 + dhi_j^2)      fraction of the band explained
changes_i = (set of selected measures at x_i low) != (set at x_i high)
```

- Ask if, for some user-editable assumption i, `changes_i` is true or w_i > ASK_WIDTH (default 0.40). Ask about one assumption per round: first any with `changes_i` true, largest swing first; then the largest w_i. Stop after ASK_MAX questions or when no assumption meets either test. This is the per-assumption reading of SPEC 5.3 step 3; the combined band of UNC-02 can exceed 40 % of expected without any single question being worth asking, and then nothing is asked and the range is simply shown.
- Assumptions with `user_editable = False`, and policy parameters, are never asked about. Ties are broken by lower `confidence`, then by key.
- The same rows, sorted by swing, are the tornado chart shown beside the plan.
- Primary: SPEC 5.3 (the rule is the product's own). Second source: HB135 section 8.2.1 ("Identifying Critical Inputs") [V heading and method].
- Worked example (the UNC-02 case): swing_a = 1 729 - 1 064 = 665, w_a = 0.50; swing_b = 1 600 - 1 180 = 420, w_b = 0.316. Shares: a 0.71, b 0.29. With ASK_WIDTH = 0.40 the agent asks about a (the quantity behind the kWh saving), not about the price.
- Tool: `rank_sensitivities(rows: list[SensitivityRow], y0: float) -> list[SensitivityRow]`; `next_question(rows, y0, selections_low, selections_high, ask_width, asked: set[str]) -> Optional[str]`.

---

## 8. VAL: value uplift (property value and rent)

Status: compact module, added after the original brief. It feeds the additive contract field `value_uplift`. It is an estimate of a market effect, much less certain than the energy and cost figures, and it is **never added to NPV, SIR, payback or the ranking**. It is shown beside them.

Sources opened (2026-11-14):

| Short name | Reference |
|---|---|
| EKQ | Eichholtz, P., Kok, N. and Quigley, J. M., "Doing Well by Doing Good? Green Office Buildings", Center for the Study of Energy Markets working paper CSEM WP 192, August 2009, https://escholarship.org/uc/item/4bf4j0gw (the working-paper version of the article later published in the *American Economic Review* 100(5), 2010, pages 2492 to 2509; the journal version was not opened). About 10 000 U.S. office buildings, rents and sale prices from CoStar |
| LBNL-SITS | Hoen, B., Wiser, R., Adomatis, S., Jackson, T., Graff-Zivin, J., Thayer, M. and Klise, G. T., *Selling into the Sun: Price Premium Analysis of a Multi-State Dataset of Solar Homes*, Lawrence Berkeley National Laboratory, LBNL-6942E, January 2015, https://eta-publications.lbl.gov/sites/default/files/lbnl-6942e.pdf. 22 822 home sales, 3 951 with host-owned PV, eight states, 2002 to 2013 |
| HB135 | section 4.5.3: "Some projects may add value through higher expected property values at resale", for example on-site renewable generation or sustainability certifications |

### VAL-01 Capitalised savings (income approach), commercial and multifamily

```
dNOI     = phi * (S_0 + dOM)
dV       = dNOI / R
```

| Symbol | Meaning | Unit |
|---|---|---|
| S_0 + dOM | first-year net operating saving of the plan, from the finance package | USD/yr |
| phi | share of the saving that reaches the owner's net operating income: 1.0 when the owner pays the utilities (gross or full-service lease, or owner-occupied); 0.0 when tenants pay them (triple-net lease) unless the lease lets the owner recover the saving | 0 to 1 |
| R | market capitalisation rate (net operating income divided by sale price) for comparable properties | 1/yr |
| dV | estimated change in property value | USD |

How R is obtained: from the CoStar `commercial-sale-comp` set, take sales of the same property type in the same metro area (and submarket where at least 10 sales remain), most recent five years; use the reported cap rate, or NOI divided by sale price where both are present. R_low, R_mid, R_high = 25th, 50th and 75th percentile of those cap rates. [P] Data lane: confirm which of these fields the dataset actually has and how many of the 6 120 sales carry a cap rate; with fewer than 10 usable comps the module returns `None` rather than a number.

Low / expected / high:

| Bound | Rule | Reason |
|---|---|---|
| low | 0 | The market may not price the saving at all (no label, no disclosure, buyer does not underwrite utility costs), or the lease passes it to tenants |
| expected | 0.5 * phi_expected * (S_0 + dOM)_expected / R_high | Half capitalisation at the least favourable cap rate. The factor 0.5 is a project judgement [J] for a retrofit without a recognised label; EKQ's evidence is for labelled buildings |
| high | phi_high * (S_0 + dOM)_high / R_low | Full capitalisation at the most favourable cap rate |

Cap on the result: dV_high may not exceed 16 % of the property's estimated value (comparable sale price per unit area times floor area), the sale-price premium EKQ found for green-rated offices.

- Cross-check range from the literature: EKQ, abstract, section IV and section V: "a dollar of energy savings yields 18.32 dollars in increased market value – implying a capitalization rate of about 5.5 percent"; rated buildings "command rental rates that are roughly three percent higher per square foot", effective rents "above six percent" higher, and "Selling prices of green buildings are higher by about 16 percent"; "A ten percent decrease in energy consumption leads to an increase in value of about one percent, over and above the rent and value premium for a labeled building." So the full-capitalisation bound (high) should land near 18 times the annual saving when R is near 5.5 %, which is the check the unit test applies.
- Limits, stated to the user every time: (1) EKQ studied Energy Star and LEED rated offices, data to 2007 to 2008; a retrofit without a label may earn less. (2) Value follows net operating income only if the saving reaches the owner. (3) Cap rates move with interest rates; comps older than five years are dropped. (4) This is not an appraisal.
- Primary: income capitalisation is standard appraisal practice; its use for energy savings is taken from EKQ, who divide by the prevailing capitalisation rate to turn annual effects into value [V]. Second source: HB135 section 4.5.3 (resale value as a residual-value method) [V]. No appraisal standard was opened [U for anything beyond this].
- Worked example: office plan, S_0 + dOM = 11 500 USD/yr (low 9 000, high 14 000), owner pays utilities (phi = 1), comps give R = 6.0 %, 7.0 %, 8.0 %.
  low = 0. expected = 0.5 * 11 500 / 0.08 = **71 875 USD**. high = 14 000 / 0.06 = **233 333 USD**.
  Cross-check: full capitalisation of the expected saving at the median rate is 11 500 / 0.07 = 164 286 USD; EKQ's multiple gives 11 500 * 18.32 = 210 680 USD; both lie between expected and high. Recomputed in a script.
- Tool: `cap_rate_from_comps(comps: list[SaleComp], property_type: str, metro: str) -> Optional[Ranged]`; `value_uplift_income(net_saving_usd: Ranged, owner_share: Ranged, cap_rate: Ranged, property_value_usd: Optional[float]) -> Optional[Ranged]`.

### VAL-02 Rent uplift (stub)

Offices: EKQ's roughly 3 % rent and above 6 % effective-rent premium apply to labelled buildings and are quoted as context only; the module does not predict a rent change for an unlabelled retrofit. Apartments: no study of rent premiums for efficient apartments was opened, so nothing is computed from `apartment-listing` yet.

What is missing before this can be written: a published, opened study of apartment rent or occupancy premiums for energy-efficient or solar-equipped units; a rule for who pays utilities by floor plan in the CoStar listing data; and enough listings per submarket to estimate an asking-rent baseline. Until then `value_uplift` carries no rent component.

### VAL-03 Homes with owned rooftop solar

```
dV_high     = 4.00 USD/W * P_dc           (LBNL-SITS average premium, sales 2002 to 2013)
dV_expected = min( dV_high, net installed cost of the system after incentives )
dV_low      = 0
```

- Reason for the expected rule: LBNL-SITS concludes that "Net cost estimates—which account for government and utility PV incentives—may be the best proxy for market premiums", and installed costs have fallen since the study period, so the premium is capped at today's net cost.
- Limits: host-owned systems only (leased systems were outside the study); "The market appears to depreciate the value of PV systems in their first 10 years at a rate exceeding the rate of PV efficiency losses and the rate of straight-line depreciation", so the figure is for a new system and falls with age; sales end in 2013; no Texas-specific result was read.
- Other home measures (insulation, heat pumps, windows): no opened study, so no value uplift is computed for them.
- Primary: LBNL-SITS abstract: "average premiums across the full sample equate to approximately $4/W or $15,000 for an average-sized 3.6-kW PV system" [V]. Second source: none opened [U beyond this one study].
- Worked example: 6 kW DC system with net installed cost 25 200 USD: dV_high = 4.00 * 6 000 = 24 000 USD; dV_expected = min(24 000, 25 200) = **24 000 USD**; dV_low = 0.
- Tool: `value_uplift_home_pv(system_kw_dc: float, net_installed_cost_usd: float) -> Ranged`.

---

## 9. Unverified, do not use

Nothing in this list may be presented as sourced. Each line says what is missing.

| Item | Where it would be used | Why it is unverified |
|---|---|---|
| Installed cost of `WIN_FILM`, `WIN_SHADE`, `PLUG_MGMT` | COST-01 | No source opened. The tool returns no finance block for these measures |
| Useful lives marked [J] in COST-02 (envelope, windows, air sealing, duct sealing, controls, thermostat, film, shades, plug loads, home LED, PV at 25 years, layout) | COST-02, ECO-05 | No effective-useful-life table was opened (California DEER, a state technical reference manual or ASHRAE equipment life data would do) |
| NREL REMDB values | COST-01 | The database could not be reached; values are as quoted in LBNL-2021 Table 13, which also warns that most were gathered around 2005 to 2010 |
| Tracking the Sun national median prices and any 2025 edition | COST-01 `PV_ROOF` | Only the 2024 executive summary was readable; the expected PV price is a midpoint judgement |
| Escalation band of +/- 1 percentage point | ECO-06 | Project judgement; the source publishes one reference projection |
| The 0.75 x / 1.5 x cost range rule; the 0.5 capitalisation factor in VAL-01 | COST-00, VAL-01 | Project judgements |
| ASTM E917, E964, E1057, E1074, E1121 | ECO second sources | Only their titles were read (in HB135); the standards are sold |
| ASHRAE Guideline 14 and IPMVP Core Concepts, as primary texts | MV | Not opened; used only as reproduced by FEMP-MV4, BPA-EMP and BPA-REG. The 15 % and 5 % tolerances are printed there for calibrated simulation; applying them to regression baselines is this spec's extension |
| Texas PACE Authority Program Guide v4.3 and "PACE in a Box Technical Standards" | ECO-12b | Not opened here; the rule is taken from `specs/legal/texas.md`. How escalation and fees enter the program SIR is unconfirmed |
| Texas Utilities Code section 39.916 | TAR-03 | The state's statute site returned only a script shell; the PUC rule 25.217 was read instead |
| SCE Energy Export Credit prices (numeric) | TAR-03 | Price files not downloaded; [P] Data lane |
| LADWP closing net metering to new applicants | TAR-03 | Third-party claim only; not found on LADWP pages |
| SCE measure rebates; TECH Clean California amounts; South Coast AQMD GO ZERO; CenterPoint commercial rates per kW and kWh; CenterPoint thermostat discount; LADWP attic "launch special" end date | INC-17, INC-20 to INC-23, INC-32, INC-33 | Amounts or terms not found on the pages opened |
| Texas home energy rebate programs (HOMES, HEEHRA) | INC-07 | No official page opened |
| Depreciation and state tax effects for business owners | INC | Not analysed |
| EPA AVERT or other hourly marginal emission rates | EMI-01 | Not opened; the non-baseload eGRID rate is the only marginal proxy used |
| Houston gas price default | TAR-04 | No source opened; [P] Data lane (the gas utility's tariff or EIA state gas prices) |
| Small-commercial retail electricity plan prices in Houston | TAR-06 | No dataset opened; the commercial high value is a judgement |
| Rent premiums for efficient apartments; value premiums for home measures other than PV | VAL-02, VAL-03 | No study opened |
| JCGM 101:2008 (Monte Carlo supplement) | UNC-02 | Not opened; the Monte Carlo check is this spec's own |
| A 2026 edition of the NIST annual supplement, of eGRID, or of the EPA emission factors hub | ECO-05, ECO-06, EMI | None was listed on the official pages on 2026-11-13 and 2026-11-14; re-check before release |

---

## 10. Verification log

Date checked is 2026-11-14 unless stated (sources for ECO, EMI and the federal statutes were first downloaded on 2026-11-13 and re-read on 2026-11-14). "Script" names a file in the scratch directory outside the repo; all were run with Python 3 in a virtual environment holding numpy 2.5.4, scipy 1.18.1 and numpy-financial 1.0.0.

| Entry | Primary source | Second source | Result | How the example was recomputed |
|---|---|---|---|---|
| ECO-01 | HB135 eq. 3-9, 3-11 | 10 CFR 436.14(a); AS135-2025 p. 1 | pass | `eco_check.py`: 0.028846, 0.0712, 0.014563; matches the values printed in HB135 |
| ECO-02 | HB135 eq. 3-5, 3-6 | AS135-2025 table 1 | pass | closed form and product loop: 862.6088; HB135 prints 862.61 |
| ECO-03 | HB135 eq. 3-7 | AS135-2025 table 2 (4.5797) | pass | closed form and loop: 457.9707; UPV 11.9379, 14.8775, 17.4131 |
| ECO-04 | HB135 eq. 3-8 | Table A-3a value 4.86 quoted in HB135 | pass | closed form and loop: 485.6240; d = e branch returns N |
| ECO-05 | AS135-2025 p. 1; 10 CFR 436.14 | AS135-2025 spreadsheet, sheet DiscountRateMemo; OMB A-94 (1992) and M-25-23 for the 7 % line | pass | values read, no arithmetic |
| ECO-06 | AS135-2025 spreadsheet, sheet "Indices - Real" | description of NIST EERC | pass (construction is this spec's) | `eco_check.py`: Brent root and independent bisection agree to 1e-9 on all 40 cells |
| ECO-07 | HB135 eq. 6-1, 6-2 | 10 CFR 436.19, 436.20 | pass | closed form 8 448.3206; loop 8 448.3206; `numpy_financial.npv` 8 448.3206 |
| ECO-08 | HB135 section 4.5.3 | second method in the same section | pass | 7 702.34 and 6 570.26 match HB135's 7702 and 6570; example B 6 985.14 by closed form and `npf.npv` |
| ECO-09 | HB135 eq. 6-3, 6-4 | 10 CFR 436.21 | pass | 1.84483 two ways; HB135's 2.61 reproduced as 2.608 |
| ECO-10 | HB135 eq. 6-6 | 10 CFR 436.22 | pass | AIRR 0.072921 by formula, by terminal value and by `npf.mirr`; IRR 0.131217 by Brent and by `npf.irr`; HB135's 0.0806 reproduced |
| ECO-11 | HB135 eq. 6-11 to 6-13 | 10 CFR 436.23 | pass | loop and `numpy.cumsum`: year 7 and year 8; HB135 Table 6-3 reproduced (28 440 at year 6, 29 603 at year 7) and 5.4 |
| ECO-12 | HB135 eq. 9-1 | `numpy_financial.pmt`; amortisation loop | pass | 9 439.2926 three ways; balance 0.00; UCR 0.067216 = 1/UPV |
| ECO-12b | `specs/legal/texas.md` section 6 (quoting the TPA Program Guide) | none opened | **partly unverified**: formula details rest on the legal spec | inline script: 1.21831 by ratio and by loop; 1.71091 with `npf.npv` |
| ECO-13 | SPEC 6.6 | ECO-02 | pass | 2 912.62 |
| TAR-01 | HB135 section 4.6.1 | 10 CFR 436.14(c); EIA EPM Table 5.6.A | pass | `tar_check.py`: month sum and annual form both 3 045.00; saving 292.50 |
| TAR-02 | HB135 section 4.6.1 | SCE page | pass | hourly sum and period sum both 2 930.50; hand case 3 020.00 |
| TAR-03 | LADWP rider NEM; CPUC net billing page; PUC of Texas rule 25.217 | LADWP NEM Guidelines; SCE page; `specs/legal/texas.md` | pass for regimes; SCE export price pending; Texas statute not opened | formula 1 344.00; hourly simulation 1 280.00 against formula 1 280.00; carry-forward loop |
| TAR-04, TAR-05 | NIST SP 811 (2008) | EIA units pages; 40 CFR 98.33 | pass | 14 653.5535 kWh via kWh factor and via MJ; 0.051182 |
| TAR-06 | PUC of Texas Power to Choose export; EIA EPM Tables 5.6.A and 5.6.B | the two agree in level | pass | `ptc.py`: `numpy.percentile` and sort-and-rank both 0.118, 0.133, 0.153 |
| EMI-01 | EPA eGRID2023 summary tables rev 2 (xlsx and PDF) | EPA Power Profiler ZIP tool v14.3 kg table | pass | lb to kg conversion 0.195037 and 0.334129 against EPA's printed 195.04 and 334.135 kg/MWh |
| EMI-02 | EPA GHG Emission Factors Hub (January 2025) | 40 CFR 98 Tables C-1, C-2 | pass | 0.181234 kg/kWh; 2 655.72 kg by kWh and by therms |
| EMI-03 | EMI-01, EMI-02 | n/a | pass | `misc_check.py`: 1 152.14 |
| INC-01 to INC-06 | Pub. L. 119-21 sections 70505 to 70513 (GPO text) | amended code on Cornell LII; IRS FS-2025-05; IRS Notice 2025-42 | pass; uscode.house.gov not reachable | 33 000 and 32 038.83 |
| INC-07 | TECH Clean California page | none | California pass; Texas unverified | n/a |
| INC-10 to INC-19 | LADWP program pages | none (single official source each) | pass | 968.75; 24 000 |
| INC-20 to INC-23 | SCE and TECH pages | none | unverified amounts | n/a |
| INC-30 to INC-34 | CenterPoint pages; 2026 Energy Efficiency Plan and Report | the two agree on program names | INC-31 pass; others partly unverified | 1 080; 2 025 |
| COST-00 | BLS CPI-U via public API | n/a | pass | `misc_check.py`: 1.6742, 1.4488, 1.3202, 1.1533 |
| COST-01 | LBNL-2021; EIA-2023; NREL-2023; TTS-2024; PNNL-22656; EPA-2008 | REMDB as quoted; CEE-2014 | pass where two sources; single-source rows marked; three measures unverified | `cost_check.py` for every row; examples in `misc_check.py` (3 256.98 from source units against 3 257) |
| COST-02 | EIA-2023; EPA-2008 | none | four lives verified; the rest judgement | 53 000 / 3 431 = 15.45 |
| MV-01 | FEMP-MV4 | BPA-EMP | pass (IPMVP itself not opened) | n/a |
| MV-02 | BPA-EMP section 3 | BPA-REG; FEMP-MV4 | pass | `mv_check.py`: grid plus `numpy.linalg.lstsq`, closed-form regression and `scipy.stats.linregress` all give 30.1613 and 2.6323 |
| MV-03, MV-04 | FEMP-MV4 Table 4-2, eq. 4-1 to 4-4 | BPA-REG; BPA-EMP | pass (Guideline 14 not opened) | CV(RMSE) 1.941 % two ways; R2 0.99624 two ways |
| MV-05 | BPA-EMP section 5.5 | BPA-REG section 2.5; FEMP-MV4 section 5.3 | pass (Guideline 14 not opened) | FSU 0.05373 by script and by manual steps; 0.0936 at 90 % |
| MV-06 | FEMP-MV4 sections 4.5.1.3, 4.5.3 to 4.5.3.4 (re-read 2026-11-14 for this entry) | BPA-EMP sections 3 and 5.5; BPA-REG 5.2.2 | procedure is a project judgement built on the sources; acceptance (MV-04) verified | `backend/analysis/physics/calibration/tests/test_a6_*.py`: the MV-02, MV-03 and MV-05 examples reproduced (Tb 18.5, b0 30.161, b1 2.632, t 48.8; CV(RMSE) 1.94 %; FSU 0.0537 and 0.0936); synthetic recovery on the golden house and the Houston office; the in-range guarantee checked on every value |
| UNC-01 | JCGM 100:2008 sections 4.3, 6, Table G.1 | `scipy.stats.norm.ppf(0.9)` = 1.28155 | pass | n/a |
| UNC-02 | JCGM 100:2008 eq. (10), 5.1.3 Note 2, 5.2.2 Note 1 | HB135 section 8.2; 10 CFR 436.24 | pass | `unc_check.py`: 1 024.6 and 1 811.8 by `sqrt` and by `numpy.hypot`; Monte Carlo 1 037.4 and 1 839.4 |
| UNC-03 | SPEC 5.3 | HB135 section 8.2.1 | pass | swings 665 and 420; shares 0.707 and 0.293 |
| VAL-01 | EKQ | HB135 section 4.5.3 | pass for the method; the 0.5 factor is judgement | `misc_check.py`: 71 875; 164 285.71; 210 680; 14 000 / 0.06 = 233 333 |
| VAL-02 | none | none | **stub, not written** | n/a |
| VAL-03 | LBNL-SITS | none | single source | 24 000 |

No double check failed. Double checks that could not be done by two independent means: INC amounts (single official page each, arithmetic only), ECO-12b (source not opened here), VAL-03 (one study).

---

## 11. Changes needed in `specs/SPEC.md`

| # | Where | Change | Why |
|---|---|---|---|
| 1 | 6.6, last paragraph | Replace the [U] sentence with: 25C expired for property placed in service after 2025-12-31; 25D expired for expenditures after 2025-12-31; 179D not available where construction begins after 2026-06-30; 45L not available for homes acquired after 2026-06-30; section 48 not available for solar whose construction began after 2024; **48E remains for business-owned solar only if placed in service by 2027-12-31, with the prohibited-foreign-entity sourcing condition, and never for a homeowner**. All confirmed against Pub. L. 119-21 and the amended code (INC-01 to INC-06). The four statements already in 6.6 were correct | primary sources now read |
| 2 | 9, `Incentive` | Add `eligibility: Literal["confirmed","needs_confirmation","not_eligible"] = "confirmed"` and `conditions: list[str] = []`. Add `"rebate_after_install"` to `kind` | 48E and the LADWP BOSS and CLIP programs depend on facts the tool cannot see (pre-approval, sourcing, in-service date). LADWP rebates are paid by cheque after installation, so they must not reduce `net_upfront_usd`, and `upfront_rebate` would be wrong. Until the literal exists, such a rebate is carried as `performance_payment` with one payment in year 1 |
| 3 | 6.6, "Net upfront cash" row | Say "point-of-sale rebates only (discount on the invoice); rebates claimed after installation and tax benefits arrive later and do not reduce the cap" | ECO-13 |
| 4 | 9, `FinancialBreakdown` | `irr` documented as the conventional IRR, `None` when not unique; add `airr: Optional[float]`. Document `discount_rate`, `electricity_escalation`, `gas_escalation` as real rates. Add `npv_sensitivity_usd: Optional[float]` (NPV at 7 %) or carry it in notes. `analysis_period_years` = min(useful life, 40) | ECO-05, ECO-10 |
| 5 | 9, `FinancingScenario` | `program_sir: Optional[float]` (already being added): document it as the undiscounted Texas PACE program ratio of ECO-12b, distinct from `FinancialBreakdown.sir`. `net_cashflow_year1_usd` is at base-date prices | ECO-12, ECO-12b |
| 6 | 9, `Tariff` | Add `export_regime: Literal["net_metering","net_billing","none"]`; optionally `tou_periods`. Document `electricity_usd_per_kwh` as the marginal price including per-kWh riders and taxes, and `gas_usd_per_kwh` as per kWh of higher heating value with 1 therm = 29.3071 kWh | TAR-01 to TAR-05. LADWP is net metering, SCE is net billing, Houston has no mandated export price |
| 7 | 9, `Tariff` or assumption registry | Price ranges (`tariff.electricity_usd_per_kwh`, `tariff.export_usd_per_kwh`) live in the assumption registry as `Ranged`; consider adding `"published_default"` to `Source` for defaults taken from EIA or Power to Choose, since `vintage_default` does not describe them | TAR-06 |
| 8 | 9, `EnergyUse.co2_kg` | Document as kg CO2-equivalent, eGRID total output (average) rate for electricity plus EPA combustion factor for gas, first year, no line-loss adjustment. Optional `co2_nonbaseload_kg: Optional[Ranged]` for the "up to" figure | EMI-01 |
| 9 | 5.3, step 3 | State that the 40 % width test is applied per assumption (swing of the plan's annual savings between that assumption's low and high runs, divided by expected), and that the plan is re-selected in each run | UNC-03; the present wording can be read either way |
| 10 | 9, `Ranged` docstring | Add: "low and high are approximate 10th and 90th percentiles; expected is the result at expected inputs" | UNC-01 |
| 11 | 6.5, rules | A measure with no verified cost source (`WIN_FILM`, `WIN_SHADE`, `PLUG_MGMT` today) is skipped with reason `no_cost_data` and the detail "no verified cost; needs a quote", unless the user enters a quote. Done in contract 0.3.0 | COST-01 |
| 12 | 9, new `value_uplift` | Type `Optional[Ranged]` in USD on `Plan` (commercial and multifamily, VAL-01) and on the `PV_ROOF` `MeasureResult` (homes, VAL-03), with a `value_uplift_basis: str`. It must not enter NPV, SIR, payback or ranking. No rent component yet (VAL-02 is a stub) | VAL |
| 13 | 1 (companion files table) | The table names `specs/physics.md`; the physics spec is now split into `specs/physics/01` to `04` | file layout |

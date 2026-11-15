# Higher-level energy savings validation

Planning: [#398](https://github.com/yalexie1/hackprinceton/issues/398). Deferred execution: [#400](https://github.com/yalexie1/hackprinceton/issues/400). Depends on Vignesha's initial [#394 evaluations](https://github.com/yalexie1/hackprinceton/issues/394).

## Objective and current state

Determine which predictions Leto can support: present energy consumption, savings from specific upgrades, solar production, bill savings and the reliability of displayed ranges. Report each separately, with the populations and inputs actually tested. Agreement between two models is different evidence from agreement with measured outcomes.

**State: stage-0 audit found two confirmed bugs; waiting for a corrected initial delivery.** Source revision `081a433` is pinned in draft #406 / audit task #405. Independent arithmetic/input-unit checks found asymmetric factor-of-two scoring and a km/h-to-m/s weather mapping error; Vignesha confirmed both bugs and withdrew the initial headline numbers pending a rerun. Fourteen arithmetic/acquisition tests passed; four raw public inputs were independently downloaded and hash/size verified outside Git. Exact 494-building headline reproduction remains unverified pending per-building outputs and archived weather inputs. No new scored cohort or model tuning has started. Frontend Evals/Solar map integration remains first priority once the owner PRs land.

Yale approved `backend/evals/high_level/` for the follow-on implementation on the team board; Vignesha keeps the rest of `backend/evals/` and `Evals.tsx`. Execution is tracked in #400 so the documentation task can close independently. No further ownership approval is needed within that scope.

Vignesha has reported an initial defaults-path test of 494 commercial buildings: median annual electricity absolute percentage error 55.5%, median signed percentage error -0.5%, and coverage of 17.6% for a nominal 80% interval. These initial numbers were withdrawn pending the wind-input correction and are not independently reproduced here. They do not validate residential retrofits, scan-derived geometry, vision, PV, bills or emissions. Near-zero median signed error does not establish accurate individual predictions; low coverage alone does not establish the cause of miscalibration.

## Start gate

All of the following must be available before higher-level validation begins:

1. Vignesha explicitly marks the initial #394 delivery complete and identifies its final commit or immutable result version. An ETA, interim board summary, partial PR or issue closure alone is insufficient.
2. The scored results, report, evaluation code, dataset version, inclusion/exclusion rules, input mappings and reproduction commands are available. The initial agreed scope must identify any benchmark left unrun, including OpenSolar, with its limitation; no missing result becomes zero.
3. The underlying public inputs or a permitted reproducible acquisition route are accessible. Restricted/private inputs stay outside Git and are never replaced with example building records.
4. Yale, the team lead, agrees implementation ownership for the follow-on work. Vignesha retains ownership of #394 and its Evals page. Until a scoped handoff is granted, this work may inspect public/committed outputs but must not edit her backend/evals/ files or take over her experiments.

The scheduled follow-up checks for this gate. While it is closed, it does not run new validation experiments. Once open, it starts the reproduction audit and advances through the plan without requesting the same authorization again. Required data access, cost approvals and team ownership rules still apply.

## Stage 0: independent reproduction and protocol freeze

- Pin the model commit, dependencies, dataset release, downloaded file hashes and evaluation configuration. Use an isolated environment and an issue branch from fresh main; do not change the running demo to run experiments.
- Reproduce the initial evaluation on the owner's stated cohort before trying to improve it. Independently check consumption totals, units, area scaling, missing/zero meters, weather-year alignment, leap days, timezone handling, exclusions and metric denominators. Test the truth-loading and coverage arithmetic with independently calculated cases.
- Record precisely what comes from the actual building and what comes from defaults or a scaled example. Scaled example geometry is a defaults-path test, not an end-to-end property test.
- Publish any discrepancies first. Freeze eligibility rules, cohort sampling, scoring definitions and decision criteria before examining the new test outcomes. Keep development data separate from final evaluation data; separate buildings and, where feasible, sites. Already inspected #394 buildings are diagnostic data, not a fresh blind test.
- Avoid circular validation: audit whether a reference dataset or model already supplied Leto's default tables, training, calibration or formulas. Describe shared inputs and methods when independence is limited.

## Six validation tracks

| Track | Proposed evidence and experiment | Required output and limits |
| --- | --- | --- |
| 1. Baseline consumption | Reproduce the BDG2 commercial evaluation; add an eligible residential cohort from EIA RECS. Compare electricity and gas separately by climate, building use, area, age and heating fuel. Where data allow, compare a defaults-only prediction with a bill-informed prediction on a different reporting period. | Annual and monthly errors where available; comparison with a simple peer energy-use-per-area baseline. RECS end-use values include estimates and are not independently metered end-use truth. Annual consumption alone cannot validate retrofit savings. |
| 2. Individual retrofit physics | Use version-pinned ResStock and, for commercial coverage, ComStock baseline/upgrade pairs. Start with a small mapping pilot, then a preselected stratified cohort. Match weather, building characteristics, equipment, thermostat assumptions and exact upgrade scope. Test wall/attic insulation, air sealing, lighting and HVAC only where the reference release contains an equivalent measure. | Baseline and upgrade energy by fuel, absolute savings, fraction of baseline saved, and disagreement by measure. This is a simulation benchmark. Whole-home packages cannot establish the effect of one measure; unsupported mappings remain not_tested. Check interactions rather than adding standalone savings. |
| 3. Delivered retrofit savings | First audit UK NEED metadata for consumption years, measure types/install years, normalization, anonymization and eligible controls. Exclude the installation year; select homes with sufficient before/after history and no recorded overlapping upgrade. Compare with similar untreated/not-yet-treated homes and check pre-intervention trends. Seek compatible US measured case studies to complement the UK evidence. | Cohort treatment-effect estimates with uncertainty and comparison with predictions for matched input profiles. UK construction, climate and anonymization limit transfer to CA/TX; do not force UK homes through a California label or claim address-level verification. Annual data do not support an hourly weather-normalization model. No raw before/after difference is treated as causal proof. |
| 4. Solar production | Reuse Vignesha's completed PVGIS/OpenSolar checks. Add eligible PVDAQ systems with documented capacity/orientation and adequate output/weather records. Match the observation year, DC/AC definitions, tilt, azimuth, losses, shading and availability; predeclare missing-data and outage handling. | Annual and monthly AC generation error and kWh/kW yield. Measured-system results and cross-model agreement remain separate. A few OpenSolar cases are case studies, not a population accuracy estimate. No solar generation figure is treated as equal to bill savings. |
| 5. Bill savings and financial arithmetic | After energy traces are credible, independently apply dated, published utility rate schedules to baseline and upgraded consumption. Include fixed charges, time-of-use pricing, demand charges where applicable, import/export compensation, taxes where supported and gas-to-electric fuel changes. Compare installation-cost assumptions separately against appropriate published cost evidence. | Bill-ledger reconciliation with worked cases, energy-versus-price error decomposition and sensitivity of simple payback. A tariff calculation validates arithmetic, not future realized savings. Annual energy totals cannot validate time-of-use/export value; absent hourly data or terms means not_tested. No assumed financing rate fills an unavailable field. |
| 6. Uncertainty and robustness | Use held-out outcomes from tracks 1–5, keeping each evidence type separate. Test the existing ranges first. On development data only, investigate correlated insulation, infiltration, geometry, occupancy, weather and equipment assumptions; then evaluate any revision on untouched data. | Coverage, interval width, coverage by building category and overprediction rates. Show abstentions/refusals and errors among accepted buildings. Distinguish uncertainty in an individual prediction from a confidence interval on a cohort metric. Do not relabel or widen a range using the final test outcomes and call it independently validated. |

Sources and access routes:

- [Building Data Genome 2](https://github.com/buds-lab/building-data-genome-project-2): commercial hourly meters, building metadata and weather. Audit metadata completeness and meter boundaries before selecting buildings.
- [EIA RECS 2020 microdata](https://www.eia.gov/consumption/residential/data/2020/index.php?view=microdata): household characteristics, consumption, expenditure and end-use estimates. Respect survey weights, imputation flags and geography limits. Do not assume precise addresses or scan geometry are available.
- [ResStock datasets](https://resstock.nlr.gov/datasets) and [ComStock](https://comstock.nlr.gov/): building-stock simulations. Verify the selected release's upgrade definitions, download size, license and overlapping inputs before acquisition.
- [NEED 2025 anonymised data](https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-anonymised-data-2025): published consumption histories, property characteristics and efficiency installations; begin with the 50,000-row sample and its metadata. It cannot be linked back to identified homes.
- [LBNL California retrofit case studies](https://bies.lbl.gov/publications/deep-energy-retrofit-performance-metr): supporting measured evidence; inspect individual study boundaries and underlying data access rather than treating published aggregate numbers as a ready-to-run dataset.
- [PVDAQ public datasets](https://data.openei.org/submissions/4568): measured solar performance and system metadata. Download selected systems, not the entire data lake.
- [OpenDSM methodology](https://opendsm.energy/stable/documentation/general_concepts/): candidate independent measurement-and-verification method when meter resolution and history meet its requirements. Its [bundled tutorial inputs](https://opendsm.energy/v1.0/documentation/eemeter/billing_model/example/) derive from ComStock simulations and do not count as measured retrofit evidence.

## Scoring and interpretation

Use the same definitions across reproducible result files:

- Baseline error: predicted minus reference energy, scored separately by fuel. Report mean signed error, median absolute percentage error on positive eligible reference totals, absolute kWh error and aggregate weighted absolute error. State weighting explicitly; show building-weighted and energy-weighted results where relevant. Do not describe a median signed percentage error as an aggregate bias.
- Upgrade error: predicted savings minus reference savings in kWh, plus error in savings as a percentage of baseline consumption (percentage points). Avoid percentage error divided by near-zero savings; retain negative savings and unsuccessful upgrades.
- Solar: generation error, monthly shape error and normalized yield, with completeness and outage exclusions reported.
- Ranges: fraction of reference outcomes within the displayed bounds, mean/median width and width relative to consumption. For a stated 80% range, assess coverage against 80% with sampling uncertainty; do not choose a post-hoc pass threshold.
- Cohorts: report n, exclusions, data completeness, defaulted inputs and refusals at every stage. Cluster uncertainty estimates by site/building as appropriate; use survey-design methods where required. Small or unrepresentative cohorts remain case studies.

Before scoring new cohorts, document what accuracy would support each intended use (ranking upgrades versus quoting individual savings), including an overprediction tolerance and uncertainty-coverage criterion. These are proposed product acceptance criteria to agree with the lead, not an assertion of compliance with an external standard. Existing results remain visible even if criteria are not met. A good total score cannot hide a failing climate, fuel or building category.

## Execution order and deliverables

1. **Wait:** complete the start gate and resolve ownership. The board gets an explicit waiting status, with no new experiments started.
2. **Reproduce:** audit #394 and issue a reproduction note with any differences and their causes.
3. **Freeze:** publish the dataset/mapping audit, development/test split, scoring protocol and acceptance criteria before running new scored cohorts.
4. **First wave:** run baseline extensions, matched individual-upgrade simulation comparisons and measured solar checks. Audit NEED feasibility alongside these; do not promise a compatible measured-retrofit result until its fields are checked.
5. **Second wave:** run eligible measured-retrofit cohorts and independent bill arithmetic. If inputs are insufficient, publish the missing requirement and the narrower conclusion available.
6. **Report:** deliver versioned aggregate results, reproducible commands and a plain-language report describing what is supported, what failed and what remains untested. Coordinate integration into Vignesha's Evals page rather than creating a competing page.

**Cut line:** the lead's hour-4 main-branch demo check-in and frontend integration of the Evals, ROI map and viewer work take priority over second-stage experiments. Do not delay those links, change the demo's environment or run an unbounded benchmark for this programme. If the check-in arrives before a validation track finishes, preserve its reproducible checkpoint, report it as incomplete and return to the required integration work. Resume after the check-in when the initial-results gate remains satisfied.

Each experiment records: model revision, dataset/release/hash, evidence type, cohort definition, reference/prediction units and periods, measures, provenance/defaults, inclusion/exclusion reasons, metric definitions, uncertainty method, known limitations and reproduction command. Proposed result status values are not_run, blocked, reproduced, evaluated, or insufficient_evidence; an evaluated result also states whether predeclared criteria were met. This is a report format proposal, not a shared-schema change.

No model tuning, uncertainty adjustment, schema change or accuracy claim is bundled into the validation itself. Any fix gets its own owner-approved issue/PR and an independent retest. Sponsor data, personal bills, credentials and restricted raw inputs remain outside the repository; only license-permitted artifacts and non-sensitive aggregate results are published.

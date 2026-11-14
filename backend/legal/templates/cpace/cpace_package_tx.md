<!-- doc: cpace_package / TX / template v0.1 -->
<!-- segments: commercial -->
<!-- optional: mortgage_block, lender_block, scenario_notes, excluded_measures_block, ltv_block -->
<!-- clause: TX-PACE-01 to -17 (statute), TX-PACE-30 to -42 (Texas PACE Authority programme rules, labelled as such) -->
<!-- source: specs/legal.md section 20 and section 15; statutory facts and programme rules from specs/legal/texas.md section 6. Our own wording, not copied from a published form. -->

{{disclaimer}}

# C-PACE APPLICATION PACKAGE — TEXAS

**This package is not the programme's contract.** Texas PACE requires a written owner
contract between the local government and the owner, and, where there is third-party
financing, a separate lender contract. This package is the data sheet and the supporting
statements the owner needs in order to apply. It does not replace the owner contract, the
lender contract, or the notice of contractual assessment the local government files.

**Statute and programme rule are marked separately throughout.** A line marked
*(programme rule)* comes from the Texas PACE Authority Program Guide, not from Chapter
399 of the Local Government Code. A programme may apply it differently; the statute does
not give it, and this package does not present it as law.

<!-- fmt: section -->
### 1. Summary
<!-- clause: TX-PACE-03, TX-PACE-07 -->

| | |
|---|---|
| Owner | {{owner_names}} |
| Property | {{property_address}}, {{property_city}}, Texas |
| Legal description | {{legal_description}} |
| Parcel number | {{parcel_number}} |
| Improvements to be financed | Schedule A |
| Amount to be assessed | ${{financed_usd}} |
| Rate | {{rate}} |
| Term | {{term_years}} years |
| Annual assessment | ${{annual_payment_usd}} |
| First-year net cash flow (low / expected / high) | {{net_cashflow_year1_low}} / {{net_cashflow_year1_expected}} / {{net_cashflow_year1_high}} |

The rate and the term are **quotes the owner obtains from a financing party**. They are
not computed here and nothing in this lane supplies a default for them; a blank means no
quote has been given yet.

<!-- fmt: section -->
### 2. Eligibility screen
<!-- clause: TX-PACE-01, TX-PACE-02, TX-PACE-03, TX-PACE-04, TX-PACE-34 -->

| Test | Source | This property |
|---|---|---|
| Privately owned commercial or industrial real property, or residential with **five or more** dwelling units | statute | {{eligibility_property_type}} |
| Not an undeveloped lot, and not undergoing development at the time of the assessment | statute | {{eligibility_development_status}} |
| Each improvement is a **permanent improvement fixed to real property** intended to decrease water or energy consumption or demand | statute | Schedule A marks each one |
| The property lies in a region a municipality or county has designated by resolution after a report and public hearing | statute | {{pace_region_name}} |
| Not government-owned | *(programme rule)* | {{eligibility_ownership}} |

{{excluded_measures_block}}

<!-- fmt: section -->
### 3. Sources and uses
<!-- clause: TX-PACE-07, TX-PACE-38 -->

| Use | Amount |
|---|---|
| Materials and labour for the qualified improvements | ${{use_materials_labour_usd}} |
| Permit fees | ${{use_permit_fees_usd}} |
| Inspection fees | ${{use_inspection_fees_usd}} |
| Lender's fees | ${{use_lender_fees_usd}} |
| Programme application and administration fees | ${{use_program_fees_usd}} |
| Independent third-party review fees | ${{use_review_fees_usd}} |
| **Total to be assessed** | **${{financed_usd}}** |

| Fees as a share of the total assessment | {{fee_share}} |
| Within the programme limit of 20 per cent | {{fee_share_within_limit}} |

*(programme rule)* The Program Guide limits other fees and costs incident to the project
to **no more than 20 per cent of the total assessment**. That is a programme figure, not a
statutory one.

*(programme rule)* Improvements must be **permanently affixed and may not be removed while
the assessment is in place**. An appliance counts only if it is fixed to the property and
meets the programme's efficiency conditions.

<!-- fmt: section -->
### 4. Savings test
<!-- clause: TX-PACE-30, TX-PACE-09 -->

**Programme savings-to-investment ratio (SIR).** *(programme rule)* The Program Guide
requires an SIR of at least **1** over the life of the assessment, validated by the
independent reviewer. It is the undiscounted savings over the term divided by all
assessment payments plus any cash the owner contributes.

| | |
|---|---|
| Programme SIR for this project | {{program_sir}} |
| Meets the programme's minimum of 1 | {{program_sir_meets_minimum}} |

{{scenario_notes}}

**This is not the plan's life-cycle SIR.** The plan reports a discounted
savings-to-investment ratio over each measure's useful life, on its own discount rate.
The programme's test is undiscounted and runs over the assessment term. The two answer
different questions and are reported separately on purpose; neither substitutes for the
other, and the independent reviewer validates the programme's figure, not ours.

**A project that does not meet the test is reported as not meeting it.** If the figure
above is below 1, this package is still produced, with the shortfall stated, so the owner
can see what would have to change — a longer term, a different measure set, or more cash
— rather than being told the application is simply unavailable.

<!-- fmt: section -->
### 5. Term against useful life
<!-- clause: TX-PACE-11, TX-PACE-31 -->

The statute requires the programme to ensure the assessment period does not exceed the
useful life of the qualified project. It sets no number.

*(programme rule)* For several improvements the Program Guide uses the **cost-weighted
average useful life**.

| | |
|---|---|
| Proposed assessment term | {{term_years}} years |
| Cost-weighted average useful life of the measures in Schedule A | {{weighted_useful_life_years}} years |
| Term within useful life | {{term_within_useful_life}} |

<!-- fmt: section -->
### 6. Loan to value
<!-- clause: TX-PACE-32 -->

{{ltv_block}}

*(programme rule)* The Program Guide states a maximum assessment as a share of the
property's appraisal-district value. **[Unverified: two passages of the guide disagree on
the variance, so the figure is not stated here — `texas.md` TX-PACE-32. Ask the programme
administrator for the one it applies.]*

<!-- fmt: section -->
### 7. Mortgage holder notice and consent
<!-- clause: TX-PACE-08 -->

**Statutory, and a condition of the owner contract.** Before the local government may
sign the owner contract, the holder of any mortgage lien on the property must be given
written notice, and must give written consent.

| | |
|---|---|
| Mortgage holder | {{mortgage_holder_name}} |
| Date written notice was sent | {{notice_sent_date}} |
| Earliest date the owner contract may be signed | {{earliest_contract_date}} |
| Written consent obtained | {{mortgage_consent_obtained}} |

{{mortgage_block}}

<!-- fmt: section -->
### 8. The assessment lien
<!-- clause: TX-PACE-13, TX-PACE-14, TX-PACE-15 -->

The owner should read this section before signing anything.

- The local government **files written notice of the assessment** in the real property
  records of the county.
- From the date that notice is filed, the assessment and any interest or penalties are a
  **first and prior lien** against the real property.
- The lien **runs with the land**. The part of the assessment that is not yet due is
  **not eliminated** by foreclosure of a property tax lien.
- In a sale, the unpaid balance stays with the property and transfers to the buyer unless
  the parties agree otherwise and the programme permits it.

<!-- fmt: section -->
### 9. Owner eligibility and underwriting
<!-- clause: TX-PACE-12, TX-PACE-33 -->

The programme must verify each of these. The owner states them here and the programme
checks them.

| Fact the programme verifies | Source | Owner's statement |
|---|---|---|
| The applicant is the legal owner, and all legal owners agree | statute | {{owner_is_legal_owner}} |
| Current on mortgage payments | statute | {{current_on_mortgage}} |
| Current on property tax payments | statute | {{current_on_property_tax}} |
| Not insolvent and not in bankruptcy | statute | {{not_insolvent}} |
| A private individual, business or nonprofit | *(programme rule)* | {{owner_entity_type}} |

<!-- fmt: section -->
### 10. Independent review and completion verification
<!-- clause: TX-PACE-09, TX-PACE-10, TX-PACE-36, TX-PACE-37 -->

**Before the assessment.** The programme must require a review of the water or energy
baseline conditions and of the projected savings, to establish the baseline the project
is measured against.

**After completion.** The local government must require written verification that the
project was properly completed and is operating as intended.

| | |
|---|---|
| Independent reviewer | {{reviewer_name}} |
| Baseline and savings review completed | {{review_completed}} |
| Completion verification method | {{completion_verification_method}} |

The energy analysis attached as **Schedule C** is owner-furnished information produced by
software. It is **not** the independent review the programme requires, and it is not a
substitute for it.

<!-- fmt: section -->
### 11. Installation contract
<!-- clause: TX-PACE-16 -->

The owner may purchase the equipment directly and contract directly for installation,
including by lease, power purchase agreement or other service contract. The construction
contract for the measures in Schedule A is a separate document — the commercial retrofit
contract, or for rooftop solar the solar installation agreement. Payment under it is tied
to the programme's disbursement schedule.

<!-- fmt: section -->
### 12. Data sheet for the programme's documents
<!-- clause: TX-PACE-13, TX-PACE-40, TX-PACE-41 -->

| Field | Value |
|---|---|
| Owner legal name | {{owner_names}} |
| Owner notice address | {{owner_mailing_address}} |
| Property address | {{property_address}}, {{property_city}}, Texas |
| Legal description | {{legal_description}} |
| Parcel number | {{parcel_number}} |
| Improvements | Schedule A |
| Assessment principal | ${{financed_usd}} |
| Payment schedule | Schedule B |
| Financing party | {{lender_name}} |
| Lender consent attached | {{lender_consent_attached}} |
| Mortgage holder consent attached | {{mortgage_consent_obtained}} |

{{lender_block}}

<!-- fmt: section -->
### 12a. The contracts the assessment requires
<!-- clause: TX-PACE-05, TX-PACE-06 -->

**Statutory.** An assessment may be imposed **only** under a written **owner contract**
between the local government, through its authorised representative, and the owner. Where
there is third-party financing, the authorised representative must **also** enter into a
written **lender contract** with the financing party.

| | |
|---|---|
| Owner contract signed | {{owner_contract_signed}} |
| Third-party financing | {{lender_name}} |
| Lender contract signed | {{lender_contract_signed}} |

Neither contract is this package. Both are the programme's documents.

<!-- fmt: section -->
### 13. Voluntary participation
<!-- clause: TX-PACE-17 -->

Participation is voluntary. A local government may not make a permit or any other
authorisation contingent on entering a PACE contract, and may not otherwise compel the
owner to participate. Nobody involved in preparing this package may represent otherwise.

<!-- fmt: section -->
### 14. Programme, region and how to apply
<!-- clause: TX-PACE-04, TX-PACE-34, TX-PACE-35, TX-PACE-36, TX-PACE-37, TX-PACE-38, TX-PACE-39, TX-PACE-42 -->

| | |
|---|---|
| PACE region | {{pace_region_name}} |
| Local government | {{programme_agency}} |
| Programme | {{programme_name}} |
| Authorised representative / administrator | {{programme_administrator}} |

**The region is determined from the incorporated place the property sits in, not from a
mailing city.** A property with a Houston mailing address may be in unincorporated Harris
County and outside the city's region; a blank above means the region could not be
confirmed and the owner must confirm it with the programme before applying.

*(programme rule)* **The closing documents are the programme's own uniform documents** -
the PACE Owner Contract, the PACE Lender Contract and the Notice of Contractual Assessment
Lien - and the programme administrator signs them for the local government. This package
is not any of them and does not replace them.

*(programme rule)* **The owner chooses the lender on the open market.** The programme does
not assign one; eligible lenders include federally insured depository institutions,
insurance companies and registered investment companies, among others listed in the guide.

Steps, in the order the statute and the guide put them: the owner applies to the
programme; the independent reviewer establishes the baseline and the projected savings;
the mortgage holder is given written notice and gives written consent; the local
government and the owner sign the owner contract; where there is third-party financing
the local government and the financing party sign the lender contract; the local
government files the notice of contractual assessment; the work is installed; completion
is verified in writing.

<!-- The figures the statutory checks read. A check sees only the rendered
     document, and a human label ('Proposed assessment term') is not a stable
     key, so each figure is also emitted here by its placeholder name. These
     are comments: they do not appear in a rendered document. -->
<!-- value: program_sir = {{program_sir}} -->
<!-- value: fee_share = {{fee_share}} -->
<!-- value: term_years = {{term_years}} -->
<!-- value: weighted_useful_life_years = {{weighted_useful_life_years}} -->

### Schedules

**Schedule A — Improvements to be financed.**

{{schedule_a_rows}}

**Schedule B — Assessment payment schedule.** {{schedule_b_rows}}

**Schedule C — Energy analysis, non-binding and not the independent review.**

{{schedule_c_table}}

{{disclaimer}}

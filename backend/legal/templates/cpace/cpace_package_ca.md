<!-- doc: cpace_package / CA / template v0.1 -->
<!-- segments: commercial -->
<!-- optional: mortgage_block, lender_block, scenario_notes, excluded_measures_block, route_b_block -->
<!-- clause: CA-PACE-01 to -11 (Route A, contractual assessment), CA-PACE-12 to -14 (Route B, Mello-Roos district), CA-PACE-15 to -17 (availability and licensing, reported as notes) -->
<!-- source: specs/legal.md section 20 and section 15; statutory facts from specs/legal/california.md section 8. Our own wording, not copied from a published form. -->

{{disclaimer}}

# C-PACE APPLICATION PACKAGE — CALIFORNIA

**This package is not the programme's contract.** A California contractual assessment is
created by the agency's own documents, including the recorded notices described in
section 8. This is the data sheet and the supporting statements the owner needs in order
to apply, and it does not replace any of them.

<!-- fmt: section -->
### 0. Availability — read this first
<!-- clause: CA-PACE-15, CA-PACE-16, CA-PACE-17 -->

**No California programme is named in this package, and that is a finding rather than an
omission.** As recorded in `specs/legal/california.md` section 8:

- Los Angeles County **ended its own residential PACE programme**; its contracts with the
  two administrators expired on 2020-04-03.
- The State Treasurer's list of programmes enrolled in the PACE Loss Reserve shows the
  Los Angeles County programmes as **inactive**.

A California contractual assessment can be levied only where **the agency has already
designated the area** by resolution of intention and a programme exists for the parcel
(CA-PACE-05). Until the owner names a programme that is open to this property, every
figure below is **hypothetical**: it shows what an assessment would look like, not one
that is available.

| | |
|---|---|
| Programme | {{programme_name}} |
| Agency | {{programme_agency}} |
| Administrator | {{programme_administrator}} |
| Status of this package | **hypothetical until a programme is confirmed** |

Some commercial programme administrators are licensed by the Department of Financial
Protection and Innovation (CA-PACE-17); ask any administrator for its licence before
signing.

<!-- fmt: section -->
### 1. Summary
<!-- clause: CA-PACE-01 -->

| | |
|---|---|
| Owner | {{owner_names}} |
| Property | {{property_address}}, {{property_city}}, California |
| Legal description | {{legal_description}} |
| Parcel number | {{parcel_number}} |
| Improvements | Schedule A |
| Amount that would be assessed | ${{financed_usd}} |
| Rate | {{rate}} |
| Term | {{term_years}} years |
| Annual assessment | ${{annual_payment_usd}} |
| First-year net cash flow (low / expected / high) | {{net_cashflow_year1_low}} / {{net_cashflow_year1_expected}} / {{net_cashflow_year1_high}} |

Rate and term are quotes the owner obtains; nothing here supplies a default, and a blank
means no quote has been given.

<!-- fmt: section -->
### 2. Eligibility screen
<!-- clause: CA-PACE-01, CA-PACE-02, CA-PACE-05 -->

| Test | This property |
|---|---|
| The improvements are distributed generation renewable energy, energy efficiency or water efficiency improvements **affixed to real property** | Schedule A marks each one |
| **Not** financeable: anything not permanently fixed to real property | {{excluded_measures_present}} |
| **Not** financeable: facilities in connection with the initial construction of a residential building | {{eligibility_not_new_construction}} |
| A programme already exists for this parcel, by the agency's resolution | {{programme_designated}} |

{{excluded_measures_block}}

<!-- fmt: section -->
### 3. Sources and uses
<!-- clause: CA-PACE-01 -->

| Use | Amount |
|---|---|
| Materials and labour for the improvements | ${{use_materials_labour_usd}} |
| Permit fees | ${{use_permit_fees_usd}} |
| Inspection fees | ${{use_inspection_fees_usd}} |
| Programme and administration fees | ${{use_program_fees_usd}} |
| **Total that would be assessed** | **${{financed_usd}}** |

<!-- fmt: section -->
### 4. Tax-burden test
<!-- clause: CA-PACE-07 -->

**Statutory, and specific to commercial property.** The agency may not let an owner
participate if, as a result, the total annual property taxes and assessments on the
property would exceed **5 per cent** of the property's market value.

| Input | Value |
|---|---|
| Current annual property taxes and assessments | ${{annual_property_tax_usd}} |
| Market value | ${{market_value_usd}} |
| Proposed annual assessment | ${{annual_payment_usd}} |
| Total as a share of market value | {{tax_burden_share}} |
| Within the 5 per cent cap | {{tax_burden_within_cap}} |

**Without both inputs the test is reported incomplete, not passed.** A blank in either
row above means the owner has not supplied the figure and the agency will compute it
itself; it does not mean the cap is satisfied.

<!-- fmt: section -->
### 5. Term against useful life
<!-- clause: CA-PACE-11 -->

For non-residential property, and residential property of four or more units, the bond
terms may follow an index rather than a fixed rate.

| | |
|---|---|
| Proposed term | {{term_years}} years |
| Cost-weighted average useful life of the measures | {{weighted_useful_life_years}} years |
| Term within useful life | {{term_within_useful_life}} |

*[Unverified: California statute sets no numeric term limit for a commercial contractual
assessment; matching the term to useful life is programme practice — `legal.md` section
20, CA-PACE-11.]*

<!-- fmt: section -->
### 6. Owner eligibility
<!-- clause: CA-PACE-03 -->

| Fact | Owner's statement |
|---|---|
| The owner of each lot or parcel consents **freely and willingly** | {{owner_consents_freely}} |
| The applicant is the legal owner, and all legal owners agree | {{owner_is_legal_owner}} |

<!-- fmt: section -->
### 7. Mortgage holder
<!-- clause: legal.md section 20 outline row 7 -->

California statute does **not** impose the 30-day mortgage-holder notice that Texas does
for a commercial contractual assessment. Consent or acknowledgment is **programme
practice**, and most lenders' loan documents require it independently.

| | |
|---|---|
| Mortgage holder | {{mortgage_holder_name}} |
| Consent or acknowledgment obtained | {{mortgage_consent_obtained}} |

{{mortgage_block}}

<!-- fmt: section -->
### 8. Recorded notices and the lien
<!-- clause: CA-PACE-08, CA-PACE-09, CA-PACE-10 -->

The owner should read this section before signing anything.

- The agency's clerk **records a notice** with the county recorder stating the existence
  and amount of each contractual assessment.
- Concurrently with the instrument creating the assessment, the agency records a separate
  document titled **"Payment of Contractual Assessment Required"**:

{{stat_ca_pace_payment_notice}}

- The assessment, with interest and penalties, **constitutes a lien** against the parcel
  until paid.

*[Unverified: the lien-priority provisions were not opened — `california.md` CA-PACE-10
and section 8.E2. Do not rely on any statement about where this lien ranks against an
existing mortgage without an attorney's opinion.]*

<!-- fmt: section -->
### 9. Owner may contract directly
<!-- clause: CA-PACE-06 -->

With the written consent of an authorised public agency official, the programme's
financing arrangements may authorise the owner to contract directly for the installation.
The construction contract is a separate document — the commercial retrofit contract, or
for rooftop solar the solar installation agreement.

<!-- fmt: section -->
### 10. Which route the programme uses
<!-- clause: CA-PACE-01 to -11 (Route A), CA-PACE-12 to -14 (Route B) -->

California has two routes and the programme the owner names decides which applies:

- **Route A, contractual assessment.** The agency designates an area by resolution and
  levies a contractual assessment on the consenting parcel. Sections 1 to 9 above are
  written for this route.
- **Route B, a community facilities district.** A district finances the improvements; a
  parcel is annexed only with the **unanimous approval of its owner or owners**, and the
  agency must comply with the two sections the statute names before annexing.

| | |
|---|---|
| Route this programme uses | {{pace_route}} |

{{route_b_block}}

<!-- fmt: section -->
### 11. Data sheet for the programme's documents
<!-- clause: CA-PACE-08, CA-PACE-09 -->

| Field | Value |
|---|---|
| Owner legal name | {{owner_names}} |
| Owner notice address | {{owner_mailing_address}} |
| Property address | {{property_address}}, {{property_city}}, California |
| Legal description | {{legal_description}} |
| Parcel number | {{parcel_number}} |
| Improvements | Schedule A |
| Assessment principal | ${{financed_usd}} |
| Payment schedule | Schedule B |
| Financing party | {{lender_name}} |
| Lender consent attached | {{lender_consent_attached}} |

{{lender_block}}

<!-- fmt: section -->
### 12. Voluntary participation
<!-- clause: CA-PACE-03 -->

An assessment may be levied only with the free and willing consent of the owner of each
lot or parcel at the time it is levied. Nobody involved in preparing this package may
represent otherwise.

{{scenario_notes}}

<!-- The figures the statutory checks read. A check sees only the rendered
     document, and a human label ('Proposed assessment term') is not a stable
     key, so each figure is also emitted here by its placeholder name. These
     are comments: they do not appear in a rendered document. -->
<!-- value: annual_property_tax_usd = {{annual_property_tax_usd}} -->
<!-- value: market_value_usd = {{market_value_usd}} -->
<!-- value: annual_payment_usd = {{annual_payment_usd}} -->
<!-- value: term_years = {{term_years}} -->
<!-- value: weighted_useful_life_years = {{weighted_useful_life_years}} -->

### Schedules

**Schedule A — Improvements.**

{{schedule_a_rows}}

**Schedule B — Assessment payment schedule.** {{schedule_b_rows}}

**Schedule C — Energy analysis, non-binding.**

{{schedule_c_table}}

{{disclaimer}}

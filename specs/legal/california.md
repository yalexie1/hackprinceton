# California legal requirements for retrofit documents

Status: COMPLETE DRAFT, all sections written. Sections 0 to 3 written 2026-11-13 from the official text and second-checked 2026-11-14 (two corrections, listed in section 10.1). Sections 4 to 10 written and checked 2026-11-14. Read section 0 for what "checked" means for each source tier, and section 8 for everything that is not verified. The exact statutory notice texts, with one stable anchor per template placeholder, are in section 2.5.

Draft for attorney review, not legal advice.

## 0. How to read this file

Scope: California law that a drafting agent must satisfy when it produces the five `DocType` documents in `specs/SPEC.md` section 9 for a property in Los Angeles. This file lists requirements only. It is not a template and contains no form language other than notices that statute requires word for word.

Every requirement has an ID (`CA-<area>-<nn>`). The template agent should emit one `StatutoryCheck` per applicable ID, with `requirement` = the short title, `citation` = the citation column. The verification log in section 10 lists the same IDs.

Columns used throughout:

- **Verbatim**: `YES` means statute prescribes exact wording, which is quoted in this file (statutory text is public domain) or located precisely. `SUBST.` means "substantially the following form": keep the wording and order, small adaptations allowed. `NO` means the content is required but the wording is free.
- **Format**: minimum type size, bold, placement, language.
- **Applies when**: the trigger. "HIC" = home improvement contract (section 2.1).
- Last amended: the latest amendment shown on the official page, with effective date. All sections were in force on 2026-11-13 unless noted.

Sources and how each requirement was checked. Three source tiers are used, and the verification log (section 10) says which tier each requirement rests on:

- **Tier L (official text).** Section text read in full from `leginfo.legislature.ca.gov`, rendered in a browser on 2026-11-13 (plain curl and fetch tools are blocked). URL pattern: `https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=<BPC|CIV|SHC|GOV|PUC>&sectionNum=<n>.` Everything in sections 1 to 3 (except the few rows marked Tier M or "one mirror" in their notes), plus BPC 7169, PUC 2869, BPC 7057, GOV 65850.5 and CIV 714 in section 4, is Tier L. Second pass on 2026-11-14: each statement was compared again, line by line, with the saved official text, and every quoted notice was machine-compared with it (all matched). The official site could not be re-opened on 2026-11-14 (no browser tool), so for the sections amended in 2025 (BPC 7159, BPC 7048, CIV 8811, CIV 1689.6, CIV 1689.7) the numbers were also confirmed on the mirror described next.
- **Tier M (two mirrors of the official text).** Sections first opened on 2026-11-14 could not be read on the official site. They were read on two independent republications: `california.public.law` (which states its text is taken from leginfo and showed "Verified: Nov. 11, 2026" on each page) and `codes.findlaw.com` (which showed "Current as of January 01, 2026"). The fetch tool returns a close paraphrase with short quotations, not the full text, so Tier M requirements have every number and scope limit confirmed on both mirrors but the complete wording was not read. Nothing in Tier M is a verbatim notice.
- **Tier A (agency page).** CSLB, CPUC, DFPI, LADWP, Los Angeles County or California State Treasurer pages, opened directly on the date shown in the log.

Anything that rests on a single reading, on a search-result summary, or on inference is in section 8, not in the requirement tables.

Code abbreviations: BPC = Business and Professions Code; CIV = Civil Code; SHC = Streets and Highways Code; GOV = Government Code; PUC = Public Utilities Code; FIN = Financial Code; LAB = Labor Code; CCR = California Code of Regulations.

Every generated draft carries the notice "Draft for attorney review, not legal advice" (project rule, `specs/HANDOFF.md` section 7), and leaves a visible blank rather than inventing a party, licence number, insurer, or legal description.

## 1. Rules that cut across all documents

### 1.1 Contractor licensing

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-LIC-01 | Anyone acting as a contractor needs a CSLB licence unless exempt. Minor-work exemption: the licensing chapter does not apply where the aggregate price for labour, materials and all other items on one project is **less than $1,000** AND the work does not require a building permit. The exemption is lost if the work is part of a larger operation, is split into contracts under $1,000 to evade the law, or the person advertises as a contractor or employs anyone to do the work. | BPC 7048 (amended Stats. 2025 ch. 67, AB 1170, eff. 2026-01-01) | NO | Almost every retrofit in the plan (insulation, HVAC, PV, windows) needs a permit, so treat the exemption as unavailable. |
| CA-LIC-02 | Unlicensed contractor cannot sue to collect for work requiring a licence, must have been licensed "at all times during the performance"; the owner may sue to recover **all compensation paid**; a security interest taken by an unlicensed contractor is unenforceable. Substantial-compliance exception is narrow (previously licensed, acted in good faith, cured promptly). | BPC 7031(a)-(e) (amended Stats. 2020 ch. 312, eff. 2021-01-01) | NO | Drives the licence-verification clause and representation in every contract and bid. |
| CA-LIC-03 | Licence number must appear in all construction contracts, subcontracts and calls for bid, and in advertising. | BPC 7030.5 (amended Stats. 1973 ch. 153) | NO | Applies to residential and commercial. Placeholder `{{contractor_license_number}}`; leave blank if unknown. |
| CA-LIC-04 | Workers' compensation: CSLB requires a current Certificate of Workers' Compensation Insurance or Certification of Self-Insurance on file as a condition of holding a licence, unless the licensee (1) has no employees and files an exemption statement AND (2) does not hold a C-8, C-20, C-22, C-39 or D-49 classification. Joint ventures with no employees may file the exemption. Wilful violation of workers' compensation law is cause for discipline. | BPC 7125 (version in force until 2028-01-01: amended Stats. 2024 ch. 485 §12, SB 1455, eff. 2025-01-01) | NO | This is a condition of holding the licence, owed to CSLB; it is not contract content (the contract content is the notice in CA-HIC-30). **Change scheduled 2028-01-01**: the later version (Stats. 2024 ch. 485 §13, operative 2028-01-01) removes the no-employee exemption for everyone except joint ventures with no employees, so from 2028 every licensee must carry workers' compensation. A contract that runs past 2027 should not rely on an exemption. Class names from the CSLB classification list (opened 2026-11-14): C-8 Concrete, C-20 Warm-Air Heating, Ventilating and Air-Conditioning, C-22 Asbestos Abatement, C-39 Roofing. So an HVAC contractor (heat pump, rooftop unit) and a roofing contractor (cool roof) cannot claim the exemption even now. |
| CA-LIC-05 | Contractor's bond of **$25,000** is a condition of holding a licence. | BPC 7071.6(a) (operative 2023-01-01) | NO | Tier M. A licence shown as active on the CSLB lookup implies the bond is on file; the documents need only a licence-status representation. |

Licence classifications that may install solar are in section 4.4. Classification names for the other retrofit trades, from the CSLB classification list (Tier A, names only; the scope text of each regulation in 16 CCR 832.xx was not opened): B General Building, B-2 Residential Remodeling, C-2 Insulation and Acoustical, C-10 Electrical, C-17 Glazing, C-20 Warm-Air Heating, Ventilating and Air-Conditioning, C-36 Plumbing, C-39 Roofing, C-43 Sheet Metal, C-46 Solar. Which class may perform which measure is an attorney or CSLB question (section 8).

### 1.2 Electronic signatures

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-ESIG-01 | A record or signature may not be denied legal effect solely because it is electronic; an electronic record satisfies a writing requirement and an electronic signature satisfies a signature requirement. | CIV 1633.7 (added Stats. 1999 ch. 428, eff. 2000-01-01) | NO | California Uniform Electronic Transactions Act. Applies only where both parties agreed to transact electronically (CIV 1633.5, not re-read; see section 8). |
| CA-ESIG-02 | **Exclusions that matter here.** UETA does not apply to (a) "a law that requires that specifically identifiable text or disclosures in a record or a portion of a record be separately signed, including initialed, from the record" and (b) transactions under CIV 1689.6, 1689.7 and 1689.13 (home solicitation cancellation notice and emergency waiver). The exclusion does not itself prohibit electronic means if another law allows them. Also excluded by 1633.3(c): transactions under CIV 1801 et seq. (retail installment contracts), which matters only if the contractor itself finances the job in instalments. | CIV 1633.3(b)(4), (c), (f) (amended Stats. 2023 ch. 374, AB 1697, eff. 2024-01-01) | NO | Consequence for templates: the separately signed or initialed pieces (the cancellation notice signed and dated by the owner, the arbitration initials under BPC 7191, the BPC 7159.1 lien warning, any emergency waiver under CIV 1689.13) cannot rely on California UETA. Whether federal E-SIGN (15 U.S.C. 7001) covers them is not verified here: see section 8. Default: provide a wet-signature path for those pieces in residential documents. |

### 1.3 Indemnity limits (all construction contracts)

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-IND-01 | Any clause in or collateral to a construction contract that indemnifies the promisee against liability arising from the promisee's **sole negligence or wilful misconduct** (or design defects furnished by the promisee's people) is void. Insurance contracts issued by admitted insurers are not affected. | CIV 2782(a) (amended Stats. 2011 ch. 707, SB 474, eff. 2012-01-01) | NO | Residential and commercial. |
| CA-IND-02 | Contracts entered on or after 2013-01-01 with the owner of privately owned real property (owner not acting as contractor or supplier): a clause that imposes liability on, or relieves the owner from liability toward, any contractor, subcontractor or supplier is unenforceable **to the extent of the owner's active negligence**. Does not apply to a homeowner doing a home improvement on his or her own single-family dwelling. | CIV 2782(c) | NO | The commercial owner-contractor contract's indemnity clause must carve out owner active negligence. |
| CA-IND-03 | Subcontract indemnity (contracts on or after 2013-01-01): a subcontractor's duty to indemnify or defend a general contractor, construction manager or other subcontractor is void to the extent claims arise from the indemnitee's **active negligence or wilful misconduct**, or fall outside the subcontractor's scope of work. Cannot be waived; California law applies regardless of choice of law. Tender rules: no duty until written tender; sub elects to defend (notice within 30 days) or pay an allocated share within 30 days of invoice. Exceptions include residential construction under CIV 895 et seq., direct owner contracts under 2782(c), wrap-up programmes, and insurance-procurement clauses. | CIV 2782.05 (added Stats. 2011 ch. 707, eff. 2012-01-01) | NO | Relevant to the commercial contract's flow-down clause and to the bid package's form of subcontract, if any. |
| CA-IND-04 | Residential construction under CIV 895 et seq. (contracts after 2009-01-01): sub-to-builder indemnity for construction-defect claims unenforceable to the extent of the builder's or contractor's negligence or outside the sub's scope; tender, 90-day election, and 30-day payment rules. | CIV 2782(d)-(i) | NO | CIV 895 et seq. is new residential construction; most retrofits are not "residential construction" under it. Flag for attorney if the retrofit adds dwelling units. |

### 1.4 Mechanics liens, preliminary notice, waivers (private works)

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-LIEN-01 | Preliminary notice is a prerequisite to a lien, stop payment notice, or payment bond claim. Given to owner, direct contractor, and construction lender. Laborers need not give it; a claimant in direct contract with the owner (the direct contractor) gives it only to the construction lender, if any. | CIV 8200 (added Stats. 2010 ch. 697, operative 2012-07-01) | NO | |
| CA-LIEN-02 | Preliminary notice due **not later than 20 days after the claimant first furnishes work**. Late notice is allowed but lien rights cover only work performed within 20 days before service and after. | CIV 8204(a) | NO | Matches the 20-day statement in the residential Mechanics Lien Warning. |
| CA-LIEN-03 | Preliminary notice content includes a general description of the work, an estimate of total price, and a boldface "NOTICE TO PROPERTY OWNER" statement whose exact text is in CIV 8202(a)(3). | CIV 8202 | YES (text at CIV 8202(a)(3)) | Issued by subcontractors and suppliers, not by our documents. The owner-facing documents should explain it (the residential warning already does). Note the 8202 statement tells the owner that after recording a notice of completion or cessation, the owner must send a copy within 10 days by registered or certified mail to the contractor and to each preliminary-notice claimant, except a residential homeowner of a dwelling of four or fewer units. |
| CA-LIEN-04 | Completion occurs on actual completion, owner occupation or use with cessation of labour, 60 days' continuous cessation, or recording a notice of cessation after 30 days' cessation. | CIV 8180 | NO | Drives retention timing (CA-PAY-04) and lien deadlines. |
| CA-LIEN-05 | Owner may record a notice of completion on or within 15 days after completion, signed and verified by the owner, with the content listed in 8182(c). | CIV 8182 | NO | Optional owner step; include as an owner checklist item in the commercial contract. |
| CA-LIEN-05a | An owner that records a notice of completion or cessation must, within **10 days** of recording, give a copy to the direct contractor and to each claimant that gave the owner a preliminary notice. If the owner does not, the recorded notice is ineffective to shorten that person's time to record a lien under CIV 8412 and 8414 (so the 90-day period applies). Does not apply to an owner who occupies the property as a personal residence in a dwelling of four or fewer units. | CIV 8190 | NO | Tier M, one mirror only (FindLaw, 2026-11-14); consistent with the owner statement in CIV 8202(a)(3), which is Tier L. Correct description of the effect: the deadline is not "extended", the shortening is lost. |
| CA-LIEN-05b | A written direct contract must provide a space for the owner to enter (1) the owner's name, address and place of business, if any, and (2) the name and address of the construction lender, if any. Item (2) does not apply to a home improvement or swimming pool contract under BPC 7150 et seq. A written subcontract must provide a space for the name and address of the owner, the direct contractor and the construction lender, if any. | CIV 8170 (added Stats. 2010 ch. 697, operative 2012-07-01) | NO | Tier M. Applies to both the residential and commercial contract and to any form of subcontract in the bid package. Placeholders `{{owner_name}}`, `{{owner_address}}`, `{{owner_place_of_business}}`, `{{construction_lender_name}}`, `{{construction_lender_address}}`. |
| CA-LIEN-06 | Lien recording deadlines: direct contractor, after completing its contract and before the earlier of 90 days after completion or 60 days after the owner records a notice of completion or cessation. Other claimants: after ceasing work and before the earlier of 90 days after completion or 30 days after a recorded notice of completion or cessation. | CIV 8412, 8414 | NO | |
| CA-LIEN-07 | Lien waivers and releases are effective only if in **substantially the statutory form** and signed; a conditional release also needs evidence of payment. Any other oral or written waiver is void unless the claimant was actually paid in full. Four statutory forms: conditional and unconditional, progress and final. | CIV 8124, 8126, 8132 (conditional progress), 8134 (unconditional progress), 8136 (conditional final), 8138 (unconditional final) | SUBST. (forms at CIV 8132-8138) | Contracts should require releases "in the form required by Civil Code sections 8132 to 8138" rather than reproduce the forms. All forms: added Stats. 2010 ch. 697, operative 2012-07-01, not since amended. |

### 1.5 Payment and retention on private works (residential and commercial unless noted)

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-PAY-01 | Unless otherwise agreed in writing, owner pays undisputed progress payments **within 30 days** after the contractor's payment demand notice; may withhold up to **150%** of a good-faith disputed amount; penalty **2% per month** on amounts wrongfully withheld (in place of interest); prevailing party gets fees. | CIV 8800 (added Stats. 2010 ch. 697, operative 2012-07-01) | NO | "Except as otherwise agreed in writing" means the contract may set a different schedule. For HICs the home improvement rules (CA-HIC-14, -15) also apply. |
| CA-PAY-02 | **Retention cap (new):** for private works contracts entered on or after 2026-01-01, retention withheld by owner from direct contractor, direct contractor from sub, and sub from sub-sub may not exceed **5% of each payment**, and total retention may not exceed **5% of the contract price**. A sub's retention percentage may not exceed the owner-direct contract percentage. Exceptions: (a) bond exception where the sub was told in writing before or at bid request that a performance and payment bond is required and failed to provide one from an admitted surety; (b) **residential projects that are not mixed-use and do not exceed four stories**. Fees to prevailing party. | CIV 8811 (added Stats. 2025 ch. 49, SB 61, eff. 2026-01-01) | NO | So the 5% cap binds the commercial contract and the bid package, and residential mixed-use or over four stories, but not a single-family home retrofit. |
| CA-PAY-03 | Retention article applies to retention withheld by owner from direct contractor or direct contractor from sub; it **does not apply to retention withheld by a lender** under a construction loan agreement. Waiver by contract is against public policy. | CIV 8810, 8820, 8822 | NO | |
| CA-PAY-04 | Owner pays retention to the direct contractor **within 45 days after completion**; may withhold up to 150% of a good-faith disputed amount from final payment. | CIV 8812 | NO | |
| CA-PAY-05 | Direct contractor pays each sub its share **within 10 days after receiving** a retention payment; may withhold up to 150% of estimated disputed value. | CIV 8814 | NO | |
| CA-PAY-06 | Disputed work notified as complete: acceptance or rejection notice within 10 days; pay related retention within 10 days of acceptance. | CIV 8816 | NO | |
| CA-PAY-07 | Late retention: **2% per month** penalty in place of interest; fees to prevailing party. | CIV 8818 | NO | |
| CA-PAY-08 | Prime contractor or sub pays each sub **within 7 days after receipt of each progress payment** unless otherwise agreed in writing; may withhold up to 150% of a disputed amount; violation is cause for discipline and a **2% per month** penalty payable to the sub. Applies to all private works. | BPC 7108.5 (amended Stats. 2011 ch. 700, eff. 2012-01-01) | NO | Flow-down term for the commercial contract and the bid package. |

## 2. Retrofit construction contract, residential (home improvement contract)

`DocType`: `retrofit_contract_residential`.

### 2.1 When these rules apply

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-HIC-00a | "Home improvement" = repairing, remodelling, altering, converting, modernising or adding to **residential property**, expressly including storm windows, **solar energy systems**, air conditioning or heating equipment, and goods affixed to the property. | BPC 7151(a), (b) (amended Stats. 2021 ch. 249, SB 757, eff. 2022-01-01) | NO | Covers every home-flow measure: insulation, air sealing, windows, cool roof, heat pump, water heater, lighting, PV. |
| CA-HIC-00b | "Home improvement contract" = agreement (oral or written, one or more documents) between a contractor and an owner, or a contractor and a tenant (any number of units, for work on the tenant's unit), or a salesperson and an owner or tenant. | BPC 7151.2 (amended Stats. 1991 ch. 1160) | NO | A landlord or tenant user of the home flow is covered. |
| CA-HIC-00c | BPC 7159's form and notice requirements apply when the aggregate contract price **exceeds $500** (labour, services and materials). | BPC 7159(b) (amended Stats. 2025 ch. 585, SB 517, eff. 2026-01-01) | NO | BPC 7159.5 payment rules apply to all HICs with no stated floor. |
| CA-HIC-00d | "Senior citizen" = 65 or older. | BPC 7150(b), CIV 1689.5(f) (both amended Stats. 2020 ch. 158, AB 2471, eff. 2021-01-01) | NO | Triggers five-day cancellation. The template needs a `{{buyer_is_senior}}` yes/no field. |

### 2.2 General form rules

| ID | Requirement | Citation | Verbatim | Format |
|---|---|---|---|---|
| CA-HIC-01 | Writing legible; printed form readable; unless a larger size is specified, text at least **10-point** and headings at least **10-point bold**. | BPC 7159(c)(1)-(2) | NO | 10 pt body, 10 pt bold headings |
| CA-HIC-02 | Contract and every change must be in writing and signed by the parties **before** the work it covers starts. | BPC 7159(d) | NO | |
| CA-HIC-03 | Before work starts, contractor gives buyer a copy signed and dated by both. Buyer's receipt starts the cancellation period. | BPC 7159(c)(3)(A) | NO | |
| CA-HIC-04 | **First page**, in type no smaller than the body: (i) date buyer signed; (ii) name, address **and email address** of the contractor to whom the Notice of Cancellation is sent, immediately preceded by a statement that the Notice of Cancellation may be sent to the contractor at that address or email address; (iii) telephone number of the contractor or representative to help the buyer locate and fill out the Notice of Cancellation. | BPC 7159(c)(3)(B); CIV 1689.7(b) (amended Stats. 2025 ch. 348, AB 1327, eff. 2026-01-01) | NO (content fixed, wording free) | First page |
| CA-HIC-05 | Contractor name, business address and licence number. | BPC 7159(d)(1) | NO | |
| CA-HIC-06 | If applicable, name and registration number of the home improvement salesperson who solicited or negotiated the contract. | BPC 7159(d)(2) | NO | |
| CA-HIC-07 | Heading identifying the contract type: **"Home Improvement."** | BPC 7159(d)(3) | YES | at least 10-point bold |
| CA-HIC-08 | Statement: **"You are entitled to a completely filled in copy of this agreement, signed by both you and the contractor, before any work may be started."** | BPC 7159(d)(4) | YES | at least 12-point bold |
| CA-HIC-09 | Heading **"Contract Price,"** followed by the amount in dollars and cents. Contract amount includes the entire cost (profit, labour, materials) but excludes finance charges. | BPC 7159(d)(5); 7159.5(a)(1) (amended Stats. 2023 ch. 403, SB 601, eff. 2024-01-01) | YES (heading) | |
| CA-HIC-10 | If a finance charge applies: heading **"Finance Charge,"** with amount in dollars and cents, set out separately from the contract amount. | BPC 7159(d)(6); 7159.5(a)(2) | YES (heading) | |
| CA-HIC-11 | Heading **"Description of the Project and Description of the Significant Materials to be Used and Equipment to be Installed,"** followed by those descriptions. | BPC 7159(d)(7) | YES (heading) | Fill from `measure_ids`: equipment model, R-values, U-factors, capacity. |
| CA-HIC-12 | Downpayment, if any, in substantially this form: heading **"Downpayment."**; a space showing the actual downpayment; and the statement **"THE DOWNPAYMENT MAY NOT EXCEED $1,000 OR 10 PERCENT OF THE CONTRACT PRICE, WHICHEVER IS LESS."** | BPC 7159(d)(8) | YES (statement); SUBST. (layout) | statement at least 12-point bold |
| CA-HIC-13 | **Downpayment cap:** may not exceed **$1,000 or 10% of the contract amount, whichever is less**. Violation is a misdemeanour (fine $100 to $5,000, up to one year jail, or both; maximum fine in a declared disaster area). | BPC 7159.5(a)(3), (b)(1) | NO | Template must compute min(1000, 0.10 x price) and refuse a larger figure. |
| CA-HIC-14 | Progress payments, if any, in substantially this form: heading **"Schedule of Progress Payments"**; each payment stated in dollars and cents and tied to the specific work, services, materials and equipment; and the statement: **"The schedule of progress payments must specifically describe each phase of work, including the type and amount of work or services scheduled to be supplied in each phase, along with the amount of each proposed progress payment. IT IS AGAINST THE LAW FOR A CONTRACTOR TO COLLECT PAYMENT FOR WORK NOT YET COMPLETED, OR FOR MATERIALS NOT YET DELIVERED. HOWEVER, A CONTRACTOR MAY REQUIRE A DOWNPAYMENT."** | BPC 7159(d)(9); 7159.5(a)(4) | YES (statement); SUBST. (layout) | statement at least 12-point bold |
| CA-HIC-15 | Except for the downpayment, contractor may neither request nor accept payment exceeding the value of work performed or material delivered, including advance payment from a lender or financier. Misdemeanour. | BPC 7159.5(a)(5), (b)(1) | NO | Payment schedule must be back-loaded to work progress. |
| CA-HIC-16 | Commencement: a statement of what constitutes **substantial commencement of work**; heading **"Approximate Start Date"**; the approximate start date. | BPC 7159(d)(10) | SUBST. (headings exact) | |
| CA-HIC-17 | Heading **"Approximate Completion Date"** and the approximate completion date. | BPC 7159(d)(11) | SUBST. (heading exact) | |
| CA-HIC-18 | If applicable, heading **"List of Documents to be Incorporated into the Contract,"** followed by the list. | BPC 7159(d)(12) | YES (heading) | Use for the audit report, plans, equipment spec sheets, savings guarantee addendum. |
| CA-HIC-19 | Heading **"Note About Extra Work and Change Orders,"** followed by: **"Extra Work and Change Orders become part of the contract once the order is prepared in writing and signed by the parties prior to the commencement of work covered by the new change order. The order must describe the scope of the extra work or change, the cost to be added or subtracted from the contract, and the effect the order will have on the schedule of progress payments."** | BPC 7159(d)(13) | YES | |
| CA-HIC-20 | A change-order form must be incorporated into the contract; a change order becomes part of the contract only if written and signed before the work it covers starts. | BPC 7159(c)(5) | NO | Attach a blank change-order form. |
| CA-HIC-21 | Change order enforceable against the buyer only if it states (1) scope, (2) amount added or subtracted, (3) effect on progress payments or completion date. Buyer cannot require extra work without written authorisation. Non-compliance does not bar unjust-enrichment recovery. | BPC 7159.6 (amended Stats. 2005 ch. 48, operative 2006-01-01); notice of these three points also required by BPC 7159(e)(3) | NO (7159.6); the 7159(e)(3) notice must contain statements (A)-(C), wording free | Change-order form fields. |
| CA-HIC-22 | Statement that, upon satisfactory payment for any portion of the work, the contractor, before any further payment, shall furnish a **full and unconditional release** from any potential lien claimant claim or mechanics lien under CIV 8400 and 8404 for that portion. | BPC 7159(c)(4) | NO (content fixed) | Pair with CA-LIEN-07 forms. |
| CA-HIC-23 | On each payment and before the next, contractor must, **if requested**, obtain and furnish the unconditional release; owner may withhold further payments until furnished. | BPC 7159.5(a)(6) | NO | |
| CA-HIC-24 | In close proximity to the owner's and contractor's signatures, a notice that the owner or tenant **has the right to require the contractor to have a performance and payment bond**. | BPC 7159(c)(6) | NO (content fixed) | Near signatures |
| CA-HIC-25 | Subcontractor statement with checkboxes `[__] Yes` / `[__] No`. If Yes, the disclaimer: **"One or more subcontractors will be used on this project, and the contractor is aware that a list of subcontractors is required to be provided, upon request, along with the names, contact information, license number, and classification of those subcontractors."** The same disclaimer must appear on each change order. | BPC 7159(c)(7) | YES | Added by SB 517, eff. 2026-01-01 (not in first-pass notes). |
| CA-HIC-26 | If the contract provides for joint control, the contractor may have no financial or other interest in it. | BPC 7159(c)(8); 7159.5(a)(8) | NO | |
| CA-HIC-27 | Salesperson commission paid from the contract price must be paid pro rata to the payment schedule. | BPC 7159.5(a)(7) | NO | Only if a salesperson is involved. |
| CA-HIC-28 | **Bond exemption:** a contractor furnishing a performance and payment bond, lien and completion bond, or registrar-approved bond equivalent or joint control covering full performance and payment is exempt from the downpayment cap, the progress-payment rule and the "no payment ahead of work" rule, and need not include the downpayment statement, the progress-payment statement, or the Mechanics Lien Warning. Blanket bond applicants must have held an active licence for at least two years. | BPC 7159.5(a)(8); 7159(d), (e) cross-refer | NO | Template branch: `{{contractor_full_bond}}` yes/no. Default no. |

### 2.3 Required notices (BPC 7159(e)), part of the contract or attached as stated

| ID | Requirement | Citation | Verbatim | Format |
|---|---|---|---|---|
| CA-HIC-29 | **Commercial General Liability Insurance (CGL)** notice: heading "Commercial General Liability Insurance (CGL)," then whichever is relevant and correct: (A) "(The name on the license or 'This contractor') does not carry commercial general liability insurance." (B) "(The name on the license or 'This contractor') carries commercial general liability insurance written by (the insurance company). You may call (the insurance company) at __________ to check the contractor's insurance coverage." (C) "(The name on the license or 'This contractor') is self-insured." (D) "(The name on the license or 'This contractor') is a limited liability company that carries liability insurance or maintains other security as required by law. You may call (the insurance company or trust company or bank) at ____ to check on the contractor's insurance coverage or security." May be an attachment if the contract states: "A notice concerning commercial general liability insurance is attached to this contract." | BPC 7159(e)(1) | YES | |
| CA-HIC-30 | **Workers' Compensation Insurance** notice: heading "Workers' Compensation Insurance," then whichever is correct: (A) "(The name on the license or 'This contractor') has no employees and is exempt from workers' compensation requirements." (B) "(The name on the license or 'This contractor') carries workers' compensation insurance for all employees." May be an attachment if the contract states: "A notice concerning workers' compensation insurance is attached to this contract." | BPC 7159(e)(2) | YES | Option (A) is unavailable to C-8, C-20, C-22, C-39, D-49 licensees (CA-LIC-04). |
| CA-HIC-31 | Extra work and change orders notice with the three statements described in CA-HIC-21. | BPC 7159(e)(3) | NO (content fixed) | |
| CA-HIC-32 | **Mechanics Lien Warning**, heading "Mechanics Lien Warning," text exactly as set out below (section 2.5). Omitted only under the bond exemption (CA-HIC-28). | BPC 7159(e)(4) | YES | Type size not specified beyond the 10-point default. |
| CA-HIC-33 | **CSLB information notice**, text exactly as set out below (section 2.5). | BPC 7159(e)(5); BPC 7030(b) | YES | at least 12-point. (The 10-point BPC 7030(a) notice is for non-HIC contracts and is **not** used here.) |
| CA-HIC-34 | **"Three-Day Right to Cancel"** (or **"Five-Day Right to Cancel"** for a senior citizen), text in section 2.5. Not required when the contract is negotiated at the contractor's place of business, or is subject to the seven-day disaster notice. Must be: at least **12-point bold**; in **immediate proximity to a space reserved for the owner's signature**; acknowledged by the owner signing and dating it; in the same language as principally used in any oral sales presentation. May be an attachment if the contract includes, in at least 12-point bold, a checkbox with: "The law requires that the contractor give you a notice explaining your right to cancel. Initial the checkbox if the contractor has given you a 'Notice of the Three-Day Right to Cancel.'" (senior: "...a 'Notice of the Five-Day Right to Cancel.'"). | BPC 7159(e)(6)(A)-(C); CIV 1689.7(a)(4) | YES | 12 pt bold; next to owner signature; signed and dated |
| CA-HIC-35 | **"Notice of Cancellation"** form: completed, **in duplicate**, attached and **easily detachable**, in the language of the contract, text in section 2.5. "three" becomes "five" for a senior. | BPC 7159(e)(6)(C)(vi) | YES | |
| CA-HIC-36 | **"Seven-Day Right to Cancel"** notice and seven-day Notice of Cancellation replace the three/five-day versions for repair or restoration of residential premises damaged by a sudden or catastrophic event under a declared federal, state or local emergency. Same format rules (12-point bold, next to signature, signed and dated, language, attachment checkbox wording with "Seven-Day"). | BPC 7159(e)(7); CIV 1689.6(c), 1689.7(e) | YES | Relevant in Los Angeles County after the January 2025 wildfires if a retrofit is part of a fire rebuild: flag, do not assume. The two statutes count the seven business days from different events: the BPC 7159(e)(7) notice says "after you received a signed and dated copy of the contract that includes this notice"; CIV 1689.6(c) says "after the buyer signs and dates the contract". Use the notice wording and list for attorney (section 8). |
| CA-HIC-37 | If the applicable Notice of Cancellation is missing, the buyer may complain to CSLB; any failure to provide the required information, notices and disclosures is cause for discipline. | BPC 7159(a)(5)-(6) | NO | |

### 2.4 Cancellation rights, financing, security interests, arbitration

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-CXL-01 | A home solicitation contract written under BPC 7151.2 may be cancelled until midnight of the **third business day** (fifth if the buyer is a senior citizen) after the buyer **receives a signed and dated copy** that complies with CIV 1689.7. | CIV 1689.6(a)(2) (amended Stats. 2025 ch. 348, AB 1327, eff. 2026-01-01) | NO | |
| CA-CXL-02 | "Home solicitation contract" = sale, lease or rental of goods or services of **$25 or more** made at other than "appropriate trade premises", defined as "premises where either the owner or seller normally carries on a business, or where goods are normally offered or exposed for sale in the course of a business carried on at those premises." A contract under which the buyer has a federal Truth in Lending rescission right is excluded from the definition. "Business day" = every calendar day **except Sunday** and the listed holidays (New Year's Day, Washington's Birthday, Memorial Day, Independence Day, Labor Day, Columbus Day, Veterans' Day, Thanksgiving Day, Christmas Day). Saturdays count. "Goods" are for personal, family or household purposes. | CIV 1689.5(a), (b), (c), (e) (amended Stats. 2020 ch. 158, eff. 2021-01-01) | NO | Template must compute the cancel-by date with this calendar. |
| CA-CXL-03 | Cancellation happens on written notice to the seller at the address **or email address** in the agreement; by mail, effective on deposit; any written form showing intent not to be bound is enough. | CIV 1689.6(d)-(f) | NO | |
| CA-CXL-04 | Seller must give the buyer a copy of the contract and the attached notice, and **inform the buyer orally** of the right to cancel and that cancellation must be in writing, at signing. Until the seller complies, the buyer may cancel. | CIV 1689.7(f), (g) | NO | Add a signing-procedure checklist item (oral notice cannot be done by the document). |
| CA-CXL-05 | **Emergency waiver**: the cancellation sections do not apply if (a) the buyer (or agent or insurer) initiated the contract, (b) it is for emergency or immediately necessary repairs needed for immediate protection of persons or property, and (c) the buyer gives a **separate, dated and signed statement** describing the situation and expressly acknowledging and waiving the right to cancel. | CIV 1689.13 (amended Stats. 2020 ch. 158, eff. 2021-01-01) | NO | Energy retrofits are planned work; do not offer this waiver in templates. |
| CA-CXL-06 | **Language of the contract.** A home solicitation contract written under BPC 7151.2 "shall be written in the same language, e.g., Spanish, as principally used in the oral sales presentation". The right-to-cancel notice follows the same rule, and the Notice of Cancellation form is in the language of the contract. | CIV 1689.7(a)(4)(A); BPC 7159(e)(6)(C)(iv), (vi) | NO | Tier L. This, not CIV 1632, is the language duty for a home improvement contract: CIV 1632 (translation of contracts negotiated in Spanish, Chinese, Tagalog, Vietnamese or Korean) says its term "contract" does not include "a home improvement contract as defined in Sections 7151.2 and 7159 of the Business and Professions Code", with the trailing condition "if the home improvement contract or installation contract is otherwise a part of a contract described in subdivision (b)" (CIV 1632(g)(2), Tier M, both mirrors, 2026-11-14). What that condition does is an attorney item. Template: `{{sales_language}}`; if it is not English, the draft is flagged for translation and not issued in English. For solar, BPC 7169(d) adds the marketing-material language (CA-SOL-07). |
| CA-FIN-01 | **Contract conditioned on financing**: if obtaining a loan is a condition precedent, or the contractor provides, assists with, or refers the buyer to financing, the contract is unenforceable against the buyer unless (1) the lender agrees to make the loan, (2) the buyer agrees to accept it, and (3) the buyer does not rescind within any federal Truth in Lending Act / Regulation Z rescission period. Until then the contractor may not deliver property or perform services other than obtaining permits or similar non-lienable preliminary services, and may not represent the contract as enforceable. If unenforceable, contractor must immediately return all money and property (it may take a lawful downpayment but must return it). Waiver void except a dated, written, owner-signed emergency waiver; printed-form waivers void. | BPC 7163 (amended Stats. 1993 ch. 589, eff. 1994-01-01) | NO | Template: if `{{financing_contingent}}` is yes, insert a financing-contingency clause and a "work starts only after" condition. |
| CA-FIN-02 | No HIC of **$5,000 or less** may provide for a security interest in real property other than a mechanics lien or interest arising by law; a violating lien is void. For HICs over $5,000 funded by a mortgage loan, the lender may pay the contractor only by an instrument payable to the borrower or jointly to borrower and contractor, or through a third-party escrow under a written agreement signed by borrower, lender and contractor before disbursement. | BPC 7159.2 (amended Stats. 1999 ch. 512, eff. 2000-01-01) | NO | |
| CA-FIN-03 | Door-to-door HIC that contains or is secured by a lien on real property: separate sheet, **18-point bold**, signed and dated by the buyer, same language as the contract, copy delivered at signing: **"WARNING TO BUYER: IF YOU SIGN THE CONTRACT WHICH ACCOMPANIES THIS NOTICE, YOU WILL BE PUTTING UP YOUR HOME AS SECURITY. THIS MEANS THAT YOUR HOME COULD BE SOLD WITHOUT YOUR PERMISSION AND WITHOUT ANY COURT ACTION IF YOU MISS ANY PAYMENT REQUIRED BY THIS CONTRACT."** Otherwise the security interest is void. Does not apply to mechanics liens, to contracts under CIV 1801 et seq. (retail installment), or to contracts covered by BPC 7159.2(a). | BPC 7159.1 (amended Stats. 2010 ch. 697, operative 2012-07-01) | YES | Only if the contractor takes a security interest. Our templates should not create one; include only as a guard. |
| CA-ARB-01 | Arbitration clause in a contract for work on **residential property with four or fewer units**: clearly titled **"ARBITRATION OF DISPUTES"**; printed contract: at least **10-point roman bold**, or contrasting **red print at least 8-point roman bold**; typed contract: capital letters. | BPC 7191(a) (added Stats. 1994 ch. 1135, eff. 1995-01-01) | YES (title) | |
| CA-ARB-02 | **Immediately after** the arbitration provision and **immediately before the line or space for the parties to indicate assent or non-assent to it** (initials), this text, same format rules: **"NOTICE: BY INITIALING IN THE SPACE BELOW YOU ARE AGREEING TO HAVE ANY DISPUTE ARISING OUT OF THE MATTERS INCLUDED IN THE 'ARBITRATION OF DISPUTES' PROVISION DECIDED BY NEUTRAL ARBITRATION AS PROVIDED BY CALIFORNIA LAW AND YOU ARE GIVING UP ANY RIGHTS YOU MIGHT POSSESS TO HAVE THE DISPUTE LITIGATED IN A COURT OR JURY TRIAL. BY INITIALING IN THE SPACE BELOW YOU ARE GIVING UP YOUR JUDICIAL RIGHTS TO DISCOVERY AND APPEAL, UNLESS THOSE RIGHTS ARE SPECIFICALLY INCLUDED IN THE 'ARBITRATION OF DISPUTES' PROVISION. IF YOU REFUSE TO SUBMIT TO ARBITRATION AFTER AGREEING TO THIS PROVISION, YOU MAY BE COMPELLED TO ARBITRATE UNDER THE AUTHORITY OF THE BUSINESS AND PROFESSIONS CODE OR OTHER APPLICABLE LAWS. YOUR AGREEMENT TO THIS ARBITRATION PROVISION IS VOLUNTARY."** followed by **"WE HAVE READ AND UNDERSTAND THE FOREGOING AND AGREE TO SUBMIT DISPUTES ARISING OUT OF THE MATTERS INCLUDED IN THE 'ARBITRATION OF DISPUTES' PROVISION TO NEUTRAL ARBITRATION."** | BPC 7191(b) | YES | Placement is relative to the arbitration initials line, not the contract signature line. A non-complying clause may not be enforceable against anyone other than the licensee (7191(c)). Initials are separately signed text: see CA-ESIG-02. |

### 2.5 Verbatim statutory notices (anchors for the template agent)

This section is the single source of the statutory words. The template agent copies from here and never paraphrases. Each anchor id equals the placeholder name used in `specs/legal.md`. Requirement rows elsewhere in this file quote the same words; if a row and a block here ever differ, the block here controls.

How the blocks were made and what was changed:

- Every block was cut by script from the official text of the section as displayed on `leginfo.legislature.ca.gov` on 2026-11-13 (BPC 7159 as amended by Stats. 2025 ch. 585, SB 517, effective 2026-01-01; BPC 7191 as added by Stats. 1994 ch. 1135; BPC 7030 as amended by Stats. 2020 ch. 312; BPC 7159.1 as amended by Stats. 2010 ch. 697). On 2026-11-14 every block in this section was compared again with that saved text by a second script (section 10.5). No block rests on a mirror.
- Three typographic changes only: (1) the official site prints typographic quotation marks; the blocks use straight ASCII quotation marks and apostrophes; (2) the outer quotation marks with which the statute encloses a quoted notice are removed (inner quotation marks are kept); (3) runs of spaces are single spaces. Paragraph breaks are as displayed on the official site. Capital letters are as enacted.
- Bracketed or slashed drafting instructions inside the statutory words, such as `(The name on the license or 'This contractor')`, `(the insurance company)`, `/name of seller/`, are part of the statute. The line under each anchor says what the drafter substitutes.
- **Four placeholders have no statutory wording at all.** For `stat_ca_commencement_statement`, `stat_ca_extra_work_notice` and `stat_ca_bond_notice` the statute prescribes what a statement must say but not its words; for the five-day variants the statute gives a substitution rule, not a second text. Each is stated plainly under its anchor. The blocks under those three anchors are the statute's description of the required content, labelled as such, and must not be printed in a contract as if they were the notice.

Index:

| Anchor (= placeholder) | Citation | Requirement ID | Verbatim statutory text? |
|---|---|---|---|
| `stat_ca_entitled_to_copy` | BPC 7159(d)(4) | CA-HIC-08 | yes |
| `stat_ca_downpayment_cap` | BPC 7159(d)(8)(C) | CA-HIC-12 | yes |
| `stat_ca_progress_payment_notice` | BPC 7159(d)(9)(C) | CA-HIC-14 | yes |
| `stat_ca_commencement_statement` | BPC 7159(d)(10)(A) | CA-HIC-16 | **no: content prescribed, wording free** |
| `stat_ca_change_order_note` | BPC 7159(d)(13) | CA-HIC-19 | yes |
| `stat_ca_extra_work_notice` | BPC 7159(e)(3) | CA-HIC-21, -31 | **no: content prescribed, wording free** |
| `stat_ca_subcontractor_disclaimer_if_yes` | BPC 7159(c)(7)(B) | CA-HIC-25 | yes |
| `stat_ca_cgl_statement` | BPC 7159(e)(1)(A)-(D) | CA-HIC-29 | yes, four options |
| `stat_ca_workers_comp_statement` | BPC 7159(e)(2)(A)-(B) | CA-HIC-30 | yes, two options |
| `stat_ca_mechanics_lien_warning` | BPC 7159(e)(4) | CA-HIC-32 | yes |
| `stat_ca_cslb_notice` | BPC 7159(e)(5); BPC 7030(b) | CA-HIC-33 | yes |
| `stat_ca_bond_notice` | BPC 7159(c)(6) | CA-HIC-24 | **no: content prescribed, wording free** |
| `stat_ca_right_to_cancel_notice` | BPC 7159(e)(6)(B); CIV 1689.7(a)(4) | CA-HIC-34 | three-day: yes. Five-day: three-day text with the statutory substitutions |
| `stat_ca_notice_of_cancellation_form` | BPC 7159(e)(6)(C)(vi) | CA-HIC-35 | three-day: yes. Five-day: statutory substitution |
| `stat_ca_arbitration_heading` | BPC 7191(a) | CA-ARB-01 | yes |
| `stat_ca_arbitration_notice` | BPC 7191(b) | CA-ARB-02 | yes |
| `stat_ca_notice_attached_cgl` | BPC 7159(e)(1) | CA-HIC-29 | yes |
| `stat_ca_notice_attached_wc` | BPC 7159(e)(2) | CA-HIC-30 | yes |
| extra: `stat_ca_headings` | BPC 7159(d), (e) | CA-HIC-07 to -19, -29 to -36 | yes |
| extra: `stat_ca_right_to_cancel_attached_checkbox` | BPC 7159(e)(6)(C)(v), (e)(7)(B)(v) | CA-HIC-34, -36 | yes |
| extra: `stat_ca_right_to_cancel_notice_seven_day` | BPC 7159(e)(7)(A) | CA-HIC-36 | yes |
| extra: `stat_ca_cslb_notice_commercial` | BPC 7030(a) | CA-COM-03 | yes |
| extra: `stat_ca_home_security_warning` | BPC 7159.1(a) | CA-FIN-03 | yes |

<a id="stat_ca_entitled_to_copy"></a>
#### `stat_ca_entitled_to_copy`

- Citation: BPC 7159(d)(4)
- Format the statute imposes: at least 12-point boldface type. No placement rule.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

```text
You are entitled to a completely filled in copy of this agreement, signed by both you and the contractor, before any work may be started.
```

<a id="stat_ca_downpayment_cap"></a>
#### `stat_ca_downpayment_cap`

- Citation: BPC 7159(d)(8)(C)
- Statutory heading: `Downpayment`
- Format the statute imposes: at least 12-point boldface type; capitals as enacted; follows the heading and a space showing the actual downpayment ("substantially the following form").
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.
- Note: Required "if a downpayment will be charged". Not required where the contractor has the full bond of BPC 7159.5(a)(8) (CA-HIC-28).

```text
THE DOWNPAYMENT MAY NOT EXCEED $1,000 OR 10 PERCENT OF THE CONTRACT PRICE, WHICHEVER IS LESS.
```

<a id="stat_ca_progress_payment_notice"></a>
#### `stat_ca_progress_payment_notice`

- Citation: BPC 7159(d)(9)(C)
- Statutory heading: `Schedule of Progress Payments`
- Format the statute imposes: at least 12-point boldface type; placed in the section of the contract reserved for the progress payments; capitals as enacted.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.
- Note: Required if payments other than the downpayment are made before completion. Not required under the bond exemption (CA-HIC-28).

```text
The schedule of progress payments must specifically describe each phase of work, including the type and amount of work or services scheduled to be supplied in each phase, along with the amount of each proposed progress payment. IT IS AGAINST THE LAW FOR A CONTRACTOR TO COLLECT PAYMENT FOR WORK NOT YET COMPLETED, OR FOR MATERIALS NOT YET DELIVERED. HOWEVER, A CONTRACTOR MAY REQUIRE A DOWNPAYMENT.
```

<a id="stat_ca_commencement_statement"></a>
#### `stat_ca_commencement_statement`

- Citation: BPC 7159(d)(10)
- Statutory heading: `Approximate Start Date`
- Format the statute imposes: none beyond the 10-point default; "substantially the following form".
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

**No verbatim statutory text exists.** The statute requires "a statement that describes what constitutes substantial commencement of work under the contract" and leaves the wording to the parties. Only the heading is fixed. The template must supply its own sentence (for example, naming the first physical work at the property) and must not mark it as statutory text. For reference, the provision reads:

```text
(10) The contract shall address the commencement of work to be performed in substantially the following form:
(A) A statement that describes what constitutes substantial commencement of work under the contract.
(B) The heading: "Approximate Start Date."
(C) The approximate date on which work will be commenced.
```

<a id="stat_ca_change_order_note"></a>
#### `stat_ca_change_order_note`

- Citation: BPC 7159(d)(13)
- Statutory heading: `Note About Extra Work and Change Orders`
- Format the statute imposes: none beyond the 10-point default; follows the heading.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

```text
Extra Work and Change Orders become part of the contract once the order is prepared in writing and signed by the parties prior to the commencement of work covered by the new change order. The order must describe the scope of the extra work or change, the cost to be added or subtracted from the contract, and the effect the order will have on the schedule of progress payments.
```

<a id="stat_ca_extra_work_notice"></a>
#### `stat_ca_extra_work_notice`

- Citation: BPC 7159(e)(3); the same three points are the operative rule in BPC 7159.6
- Format the statute imposes: none beyond the 10-point default; may be part of the contract form.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

**No verbatim statutory text exists.** The statute lists three statements the notice must contain, (A), (B) with its items (i) to (iii), and (C), and leaves the wording free. The template must write the notice in its own words covering each point, and the statutory check passes when all of (A), (B)(i)-(iii) and (C) are present. For reference, the provision reads:

```text
(3) A notice that provides the buyer with the following information about the performance of extra or change-order work:
(A) A statement that the buyer may not require a contractor to perform extra or change-order work without providing written authorization prior to the commencement of work covered by the new change order.
(B) A statement informing the buyer that extra work or a change order is not enforceable against a buyer unless the change order also identifies all of the following in writing prior to the commencement of work covered by the new change order:
(i) The scope of work encompassed by the order.
(ii) The amount to be added or subtracted from the contract.
(iii) The effect the order will make in the progress payments or the completion date.
(C) A statement informing the buyer that the contractor's failure to comply with the requirements of this paragraph does not preclude the recovery of compensation for work performed based upon legal or equitable remedies designed to prevent unjust enrichment.
```

<a id="stat_ca_subcontractor_disclaimer_if_yes"></a>
#### `stat_ca_subcontractor_disclaimer_if_yes`

- Citation: BPC 7159(c)(7)(B); repeated on every change order under (c)(7)(C)
- Format the statute imposes: none beyond the 10-point default. Printed when the "Yes" box of the subcontractor statement is checked. The statement itself must include "a portion to be checked in response" shown in the statute as `[__] Yes` and `[__] No`.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

```text
One or more subcontractors will be used on this project, and the contractor is aware that a list of subcontractors is required to be provided, upon request, along with the names, contact information, license number, and classification of those subcontractors.
```

<a id="stat_ca_cgl_statement"></a>
#### `stat_ca_cgl_statement`

- Citation: BPC 7159(e)(1)(A)-(D)
- Statutory heading: `Commercial General Liability Insurance (CGL)`
- Format the statute imposes: none beyond the 10-point default; under the statutory heading; may be an attachment if the contract carries `stat_ca_notice_attached_cgl`.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

Print whichever one option is "both relevant and correct". In each, replace `(The name on the license or 'This contractor')` with the licence name or the words This contractor, replace `(the insurance company)` or `(the insurance company or trust company or bank)` with the name, and fill the telephone blank.

Option A:

```text
(The name on the license or 'This contractor') does not carry commercial general liability insurance.
```

Option B:

```text
(The name on the license or 'This contractor') carries commercial general liability insurance written by (the insurance company). You may call (the insurance company) at __________ to check the contractor's insurance coverage.
```

Option C:

```text
(The name on the license or 'This contractor') is self-insured.
```

Option D:

```text
(The name on the license or 'This contractor') is a limited liability company that carries liability insurance or maintains other security as required by law. You may call (the insurance company or trust company or bank) at ____ to check on the contractor's insurance coverage or security.
```

<a id="stat_ca_workers_comp_statement"></a>
#### `stat_ca_workers_comp_statement`

- Citation: BPC 7159(e)(2)(A)-(B)
- Statutory heading: `Workers' Compensation Insurance`
- Format the statute imposes: none beyond the 10-point default; under the statutory heading; may be an attachment if the contract carries `stat_ca_notice_attached_wc`.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

Print whichever one option is "correct". Same substitution for the contractor name. Option A is not available to C-8, C-20, C-22, C-39 or D-49 licensees (CA-LIC-04).

Option A:

```text
(The name on the license or 'This contractor') has no employees and is exempt from workers' compensation requirements.
```

Option B:

```text
(The name on the license or 'This contractor') carries workers' compensation insurance for all employees.
```

<a id="stat_ca_mechanics_lien_warning"></a>
#### `stat_ca_mechanics_lien_warning`

- Citation: BPC 7159(e)(4)
- Statutory heading: `Mechanics Lien Warning`
- Format the statute imposes: none beyond the 10-point default; "written as follows"; capitals as enacted; the first line `MECHANICS LIEN WARNING:` is part of the text.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.
- Note: Not required under the bond exemption (CA-HIC-28).

```text
MECHANICS LIEN WARNING:

Anyone who helps improve your property, but who is not paid, may record what is called a mechanics lien on your property. A mechanics lien is a claim, like a mortgage or home equity loan, made against your property and recorded with the county recorder.

Even if you pay your contractor in full, unpaid subcontractors, suppliers, and laborers who helped to improve your property may record mechanics liens and sue you in court to foreclose the lien. If a court finds the lien is valid, you could be forced to pay twice or have a court officer sell your home to pay the lien. Liens can also affect your credit.

To preserve their right to record a lien, each subcontractor and material supplier must provide you with a document called a 'Preliminary Notice.' This notice is not a lien. The purpose of the notice is to let you know that the person who sends you the notice has the right to record a lien on your property if they are not paid.

BE CAREFUL. The Preliminary Notice can be sent up to 20 days after the subcontractor starts work or the supplier provides material. This can be a big problem if you pay your contractor before you have received the Preliminary Notices.

You will not get Preliminary Notices from your prime contractor or from laborers who work on your project. The law assumes that you already know they are improving your property.

PROTECT YOURSELF FROM LIENS. You can protect yourself from liens by getting a list from your contractor of all the subcontractors and material suppliers that work on your project. Find out from your contractor when these subcontractors started work and when these suppliers delivered goods or materials. Then wait 20 days, paying attention to the Preliminary Notices you receive.

PAY WITH JOINT CHECKS. One way to protect yourself is to pay with a joint check. When your contractor tells you it is time to pay for the work of a subcontractor or supplier who has provided you with a Preliminary Notice, write a joint check payable to both the contractor and the subcontractor or material supplier.

For other ways to prevent liens, visit CSLB's internet website at www.cslb.ca.gov or call CSLB at 800-321-CSLB (2752).

REMEMBER, IF YOU DO NOTHING, YOU RISK HAVING A LIEN PLACED ON YOUR HOME. This can mean that you may have to pay twice, or face the forced sale of your home to pay what you owe.
```

<a id="stat_ca_cslb_notice"></a>
#### `stat_ca_cslb_notice`

- Citation: BPC 7159(e)(5); BPC 7030(b)
- Format the statute imposes: at least 12-point typeface (boldface is not required). No heading is prescribed.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.
- Note: BPC 7030(b) prescribes the same notice for home improvement contracts with one difference: it has no comma after "disciplinary actions". This block is the BPC 7159(e)(5) text. The BPC 7030(b) text was captured on 2026-11-13 without its line breaks, so only its wording, not its layout, was compared.

```text
Information about the Contractors State License Board (CSLB): CSLB is the state consumer protection agency that licenses and regulates construction contractors.

Contact CSLB for information about the licensed contractor you are considering, including information about disclosable complaints, disciplinary actions, and civil judgments that are reported to CSLB.

Use only licensed contractors. If you file a complaint against a licensed contractor within the legal deadline (usually four years), CSLB has authority to investigate the complaint. If you use an unlicensed contractor, CSLB may not be able to help you resolve your complaint. Your only remedy may be in civil court, and you may be liable for damages arising out of any injuries to the unlicensed contractor or the unlicensed contractor's employees.

For more information:

Visit CSLB's internet website at www.cslb.ca.gov

Call CSLB at 800-321-CSLB (2752)

Write CSLB at P.O. Box 26000, Sacramento, CA 95826.
```

<a id="stat_ca_bond_notice"></a>
#### `stat_ca_bond_notice`

- Citation: BPC 7159(c)(6)
- Format the statute imposes: placed "in close proximity to the signatures of the owner and contractor"; no type size beyond the 10-point default.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

**No verbatim statutory text exists.** The statute requires "a notice stating that the owner or tenant has the right to require the contractor to have a performance and payment bond" and gives no wording. The template must write one sentence that says exactly that, addressed to the owner or tenant as the case may be. For reference, the provision reads:

```text
(6) The contract shall contain, in close proximity to the signatures of the owner and contractor, a notice stating that the owner or tenant has the right to require the contractor to have a performance and payment bond.
```

<a id="stat_ca_right_to_cancel_notice"></a>
#### `stat_ca_right_to_cancel_notice`

- Citation: BPC 7159(e)(6)(A)-(C); CIV 1689.7(a)(4)
- Format the statute imposes: at least 12-point boldface type; in immediate proximity to a space reserved for the owner's signature; the owner signs and dates the notice in that space; written in the same language as principally used in any oral sales presentation; may instead be attached if the contract carries the checkbox statement (`stat_ca_right_to_cancel_attached_checkbox`).
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.
- Note: Not required when the contract is negotiated at the contractor's place of business or when the seven-day notice applies (BPC 7159(e)(6)(A)). CIV 1689.7(a)(4)(A) sets out the same notice with one wording difference: where this text reads "as you received them, goods delivered to you", the Civil Code text reads "as you received it, any goods delivered to you". This block is the BPC 7159 text; the difference is an attorney item (8.B3). The Civil Code version is deliberately not reproduced.

Variant `three_day` (verbatim, BPC 7159(e)(6)(B)(i)). The first line is the title of the notice and is part of it:

```text
Three-Day Right to Cancel

You, the buyer, have the right to cancel this contract within three business days. You may cancel by emailing, mailing, faxing, or delivering a written notice to the contractor at the contractor's place of business by midnight of the third business day after you received a signed and dated copy of the contract that includes this notice. Include your name, your address, and the date you received the signed copy of the contract and this notice.

If you cancel, the contractor must return to you anything you paid within 10 days of receiving the notice of cancellation. For your part, you must make available to the contractor at your residence, in substantially as good condition as you received them, goods delivered to you under this contract or sale. Or, you may, if you wish, comply with the contractor's instructions on how to return the goods at the contractor's expense and risk. If you do make the goods available to the contractor and the contractor does not pick them up within 20 days of the date of your notice of cancellation, you may keep them without any further obligation. If you fail to make the goods available to the contractor, or if you agree to return the goods to the contractor and fail to do so, then you remain liable for performance of all obligations under the contract.
```

Variant `five_day` (buyer aged 65 or older). **The statute does not print a five-day text.** It says: "References to "three" and "third" in the notice set forth in clause (i) shall be changed to "five" and "fifth," respectively, for a buyer who is a senior citizen." (BPC 7159(e)(6)(B)(ii)), and BPC 7159(e)(6)(A) gives the title "Five-Day Right to Cancel". The block below is the three-day text with exactly those changes (one "Three-Day" in the title, one "three", one "third"), made by script; "10 days" and "20 days" are unchanged:

```text
Five-Day Right to Cancel

You, the buyer, have the right to cancel this contract within five business days. You may cancel by emailing, mailing, faxing, or delivering a written notice to the contractor at the contractor's place of business by midnight of the fifth business day after you received a signed and dated copy of the contract that includes this notice. Include your name, your address, and the date you received the signed copy of the contract and this notice.

If you cancel, the contractor must return to you anything you paid within 10 days of receiving the notice of cancellation. For your part, you must make available to the contractor at your residence, in substantially as good condition as you received them, goods delivered to you under this contract or sale. Or, you may, if you wish, comply with the contractor's instructions on how to return the goods at the contractor's expense and risk. If you do make the goods available to the contractor and the contractor does not pick them up within 20 days of the date of your notice of cancellation, you may keep them without any further obligation. If you fail to make the goods available to the contractor, or if you agree to return the goods to the contractor and fail to do so, then you remain liable for performance of all obligations under the contract.
```

<a id="stat_ca_notice_of_cancellation_form"></a>
#### `stat_ca_notice_of_cancellation_form`

- Citation: BPC 7159(e)(6)(C)(vi). Not CIV 1689.7(c), which excludes contracts written under BPC 7151.2.
- Format the statute imposes: a completed form, in duplicate, captioned "Notice of Cancellation", attached to the contract and easily detachable; written in the same language as used in the contract. BPC 7159 sets no type size for it beyond the 10-point default (the 10-point rule in CIV 1689.7(c) is for other home solicitation contracts).
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

Variant `three_day` (verbatim, BPC 7159(e)(6)(C)(vi)(I)), line by line as the official site displays it. The slashed and bracketed items are the statute's own blanks: the drafter replaces `/enter date of transaction/` with the transaction date, `/name of seller/` with the contractor's name, `/address of seller's place of business/` with the contractor's business address, and the `(Date)` after "not later than midnight of" with the last day to cancel; the final `(Date)` and `(Buyer's signature)` stay blank for the buyer. The official site shows the blanks as empty table cells, which is why "to ," and "midnight of ." appear with nothing between; print a line there. The quotation marks around the caption and around the four-paragraph statement are in the statute as displayed; whether a printed form keeps them is a layout choice.

```text
"Notice of Cancellation"
/enter date of transaction/
(Date)
"You may cancel this transaction, without any penalty or obligation, within three business days from the above date.
If you cancel, any property traded in, any payments made by you under the contract or sale, and any negotiable instrument executed by you will be returned within 10 days following receipt by the seller of your cancellation notice, and any security interest arising out of the transaction will be canceled.
If you cancel, you must make available to the seller at your residence, in substantially as good condition as when received, any goods delivered to you under this contract or sale, or you may, if you wish, comply with the instructions of the seller regarding the return shipment of the goods at the seller's expense and risk.
If you do make the goods available to the seller and the seller does not pick them up within 20 days of the date of your notice of cancellation, you may retain or dispose of the goods without any further obligation. If you fail to make the goods available to the seller, or if you agree to return the goods to the seller and fail to do so, then you remain liable for performance of all obligations under the contract."
To cancel this transaction, email, mail, or deliver a signed and dated copy of this cancellation notice, or any other written notice, or send a telegram
to ,
/name of seller/
at
/address of seller's place of business/
not later than midnight of .
(Date)
I hereby cancel this transaction.
(Date)
(Buyer's signature)
```

Variant `five_day`: the statute gives a rule, not a text: "The reference to "three" in the statement set forth in subclause (I) shall be changed to "five" for a buyer who is a senior citizen." (BPC 7159(e)(6)(C)(vi)(II)). Only the one line changes:

```text
"You may cancel this transaction, without any penalty or obligation, within five business days from the above date.
```

Seven-day (disaster) variant: BPC 7159(e)(7)(B)(vi) prints the whole form again; the script confirmed it is identical to the three-day form except "seven business days" in the same line.

<a id="stat_ca_arbitration_heading"></a>
#### `stat_ca_arbitration_heading`

- Citation: BPC 7191(a)
- Format the statute imposes: the provision "shall be clearly titled"; in a printed contract the provision is in at least 10-point roman boldface type, or in contrasting red print in at least 8-point roman boldface type; in a typed contract, in capital letters.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.
- Note: The statute prints the title as "ARBITRATION OF DISPUTES." with a full stop inside the quotation marks; the notice in BPC 7191(b) refers to the 'ARBITRATION OF DISPUTES' provision without one, so the full stop is treated as sentence punctuation. Applies to contracts for work on residential property with four or fewer units.

```text
ARBITRATION OF DISPUTES
```

<a id="stat_ca_arbitration_notice"></a>
#### `stat_ca_arbitration_notice`

- Citation: BPC 7191(b)
- Format the statute imposes: same type rules as the heading (10-point roman boldface, or contrasting red 8-point roman boldface; capitals if typed); placed immediately after the arbitration provision and immediately before the line or space where the parties indicate assent or non-assent (initials). The statute sets out two separately quoted passages, shown here as two paragraphs.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

```text
NOTICE: BY INITIALING IN THE SPACE BELOW YOU ARE AGREEING TO HAVE ANY DISPUTE ARISING OUT OF THE MATTERS INCLUDED IN THE 'ARBITRATION OF DISPUTES' PROVISION DECIDED BY NEUTRAL ARBITRATION AS PROVIDED BY CALIFORNIA LAW AND YOU ARE GIVING UP ANY RIGHTS YOU MIGHT POSSESS TO HAVE THE DISPUTE LITIGATED IN A COURT OR JURY TRIAL. BY INITIALING IN THE SPACE BELOW YOU ARE GIVING UP YOUR JUDICIAL RIGHTS TO DISCOVERY AND APPEAL, UNLESS THOSE RIGHTS ARE SPECIFICALLY INCLUDED IN THE 'ARBITRATION OF DISPUTES' PROVISION. IF YOU REFUSE TO SUBMIT TO ARBITRATION AFTER AGREEING TO THIS PROVISION, YOU MAY BE COMPELLED TO ARBITRATE UNDER THE AUTHORITY OF THE BUSINESS AND PROFESSIONS CODE OR OTHER APPLICABLE LAWS. YOUR AGREEMENT TO THIS ARBITRATION PROVISION IS VOLUNTARY.

WE HAVE READ AND UNDERSTAND THE FOREGOING AND AGREE TO SUBMIT DISPUTES ARISING OUT OF THE MATTERS INCLUDED IN THE 'ARBITRATION OF DISPUTES' PROVISION TO NEUTRAL ARBITRATION.
```

<a id="stat_ca_notice_attached_cgl"></a>
#### `stat_ca_notice_attached_cgl`

- Citation: BPC 7159(e)(1)
- Format the statute imposes: none beyond the 10-point default; printed in the contract when the CGL notice is an attachment.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

```text
A notice concerning commercial general liability insurance is attached to this contract.
```

<a id="stat_ca_notice_attached_wc"></a>
#### `stat_ca_notice_attached_wc`

- Citation: BPC 7159(e)(2)
- Format the statute imposes: none beyond the 10-point default; printed in the contract when the workers' compensation notice is an attachment.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

```text
A notice concerning workers' compensation insurance is attached to this contract.
```

<a id="stat_ca_headings"></a>
#### `stat_ca_headings` (extra)

Headings the statute fixes word for word (BPC 7159(d) and (e)), in at least 10-point boldface under BPC 7159(c)(2) unless stated. The statute prints most of them with a full stop or comma inside the quotation marks (for example "Home Improvement." and "Contract Price,"); that mark is sentence punctuation and is not part of the heading.

| Heading | Citation | When |
|---|---|---|
| `Home Improvement` | BPC 7159(d)(3) | always; "at least 10-point boldface type" is stated in the paragraph itself |
| `Contract Price` | BPC 7159(d)(5) | always |
| `Finance Charge` | BPC 7159(d)(6) | if a finance charge will be charged |
| `Description of the Project and Description of the Significant Materials to be Used and Equipment to be Installed` | BPC 7159(d)(7) | always |
| `Downpayment` | BPC 7159(d)(8)(A) | if a downpayment will be charged |
| `Schedule of Progress Payments` | BPC 7159(d)(9)(A) | if there are progress payments |
| `Approximate Start Date` | BPC 7159(d)(10)(B) | always |
| `Approximate Completion Date` | BPC 7159(d)(11)(A) | always |
| `List of Documents to be Incorporated into the Contract` | BPC 7159(d)(12) | if applicable |
| `Note About Extra Work and Change Orders` | BPC 7159(d)(13) | always |
| `Commercial General Liability Insurance (CGL)` | BPC 7159(e)(1) | always |
| `Workers' Compensation Insurance` | BPC 7159(e)(2) | always |
| `Mechanics Lien Warning` | BPC 7159(e)(4) | unless bond exemption |
| `Three-Day Right to Cancel` / `Five-Day Right to Cancel` / `Seven-Day Right to Cancel` | BPC 7159(e)(6)(A), (e)(7)(A) | title of the notice, part of the notice text |
| `Notice of Cancellation` | BPC 7159(e)(6)(C)(vi) | caption of the detachable form |

<a id="stat_ca_right_to_cancel_attached_checkbox"></a>
#### `stat_ca_right_to_cancel_attached_checkbox`

- Citation: BPC 7159(e)(6)(C)(v)(I), (II); (e)(7)(B)(v)
- Format the statute imposes: at least 12-point boldface type, with a checkbox the owner initials; used only when the right-to-cancel notice is attached instead of printed in the contract.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

(extra) Variant `three_day`:

```text
The law requires that the contractor give you a notice explaining your right to cancel. Initial the checkbox if the contractor has given you a 'Notice of the Three-Day Right to Cancel.'
```

Variant `five_day`:

```text
The law requires that the contractor give you a notice explaining your right to cancel. Initial the checkbox if the contractor has given you a 'Notice of the Five-Day Right to Cancel.'
```

Variant `seven_day`:

```text
The law requires that the contractor give you a notice explaining your right to cancel. Initial the checkbox if the contractor has given you a 'Notice of the Seven-Day Right to Cancel.'
```

<a id="stat_ca_right_to_cancel_notice_seven_day"></a>
#### `stat_ca_right_to_cancel_notice_seven_day`

- Citation: BPC 7159(e)(7)(A); CIV 1689.6(c), 1689.7(e)
- Format the statute imposes: same rules as the three-day notice (BPC 7159(e)(7)(B)): at least 12-point boldface; next to the space for the owner's signature; signed and dated; language of the oral sales presentation.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

(extra) For a contract to repair or restore residential premises damaged by a sudden or catastrophic event in a declared emergency (CA-HIC-36):

```text
Seven-Day Right to Cancel

You, the buyer, have the right to cancel this contract within seven business days. You may cancel by emailing, mailing, faxing, or delivering a written notice to the contractor at the contractor's place of business by midnight of the seventh business day after you received a signed and dated copy of the contract that includes this notice. Include your name, your address, and the date you received the signed copy of the contract and this notice.

If you cancel, the contractor must return to you anything you paid within 10 days of receiving the notice of cancellation. For your part, you must make available to the contractor at your residence, in substantially as good condition as you received them, goods delivered to you under this contract or sale. Or, you may, if you wish, comply with the contractor's instructions on how to return the goods at the contractor's expense and risk. If you do make the goods available to the contractor and the contractor does not pick them up within 20 days of the date of your notice of cancellation, you may keep them without any further obligation. If you fail to make the goods available to the contractor, or if you agree to return the goods to the contractor and fail to do so, then you remain liable for performance of all obligations under the contract.
```

<a id="stat_ca_cslb_notice_commercial"></a>
#### `stat_ca_cslb_notice_commercial`

- Citation: BPC 7030(a)
- Format the statute imposes: at least 10-point type, on every written contract on which the licensee is prime contractor, other than home improvement and service and repair contracts.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

(extra) For the commercial contract (CA-COM-03):

```text
Contractors are required by law to be licensed and regulated by the Contractors State License Board which has jurisdiction to investigate complaints against contractors if a complaint regarding a patent act or omission is filed within four years of the date of the alleged violation. A complaint regarding a latent act or omission pertaining to structural defects must be filed within 10 years of the date of the alleged violation. Any questions concerning a contractor may be referred to the Registrar, Contractors State License Board, P.O. Box 26000, Sacramento, CA 95826.
```

<a id="stat_ca_home_security_warning"></a>
#### `stat_ca_home_security_warning`

- Citation: BPC 7159.1(a)
- Format the statute imposes: 18-point boldface type; on a separate piece of paper; same language as the contract; signed and dated by the buyer; copy delivered at signing.
- Source matched: leginfo official text read 2026-11-13; block generated by script from the saved text and string-matched against it on 2026-11-14.

(extra) Only if a door-to-door home improvement contract contains or is secured by a lien on real property (CA-FIN-03). Our templates create no such lien.

```text
WARNING TO BUYER: IF YOU SIGN THE CONTRACT WHICH ACCOMPANIES THIS NOTICE, YOU WILL BE PUTTING UP YOUR HOME AS SECURITY. THIS MEANS THAT YOUR HOME COULD BE SOLD WITHOUT YOUR PERMISSION AND WITHOUT ANY COURT ACTION IF YOU MISS ANY PAYMENT REQUIRED BY THIS CONTRACT.
```

### 2.6 Residential retrofit: items that are not required but are commonly confused

- The commercial-contract CSLB notice in BPC 7030(a) (10-point) is not used in an HIC; BPC 7030(b) (12-point) is. (BPC 7030(a) opening words.)
- The 5% retention cap (CA-PAY-02) does not apply to a residential project that is not mixed-use and is four stories or fewer.
- The prompt-payment rule for owners (CA-PAY-01) does apply, but the HIC rules forbid any payment ahead of work in any case.

## 3. Retrofit construction contract, commercial (private works)

`DocType`: `retrofit_contract_commercial`. Office or other non-residential property, privately owned, no public funds.

### 3.1 Home improvement rules that do NOT apply

The home improvement article (BPC 7150-7170) is defined by "residential property" (BPC 7151(a)) and a contract with an owner or tenant of a residence or dwelling unit (BPC 7151.2). An office retrofit is not a home improvement, so none of CA-HIC-00 to CA-HIC-37 apply: no "Home Improvement" heading, no $1,000 / 10% downpayment cap, no 12-point notices, no Mechanics Lien Warning, no BPC 7159.6 change-order formalities, no BPC 7163 financing condition, no BPC 7159.2 $5,000 security-interest bar.

The home solicitation cancellation right (CIV 1689.5-1689.7): **corrected on the second pass.** The first draft said flatly that it does not apply to commercial work. The text is less clear than that. "Goods" are limited to goods bought "for use primarily for personal, family, or household purposes" (CIV 1689.5(c)), so equipment bought for an office is outside it. But "services" means "work, labor and services, including, but not limited to, services furnished in connection with the repair, restoration, alteration, or improvement of residential premises" (CIV 1689.5(d)): residential work is an example, not a limit. And a contract is a home solicitation contract only if made away from "appropriate trade premises", which are "premises where either the owner or seller normally carries on a business" (CIV 1689.5(b)). No statutory text was found that excludes a business buyer by name. Working rule for the template: do not put the three-day notice in the commercial contract, record where the contract is signed (`{{signing_location}}`), and list the question for the attorney (section 8). The BPC 7159 notices themselves are certainly not required, because BPC 7159 applies only to home improvement contracts.

BPC 7191 (arbitration formatting) applies only to residential property with four or fewer units.

Mixed-use buildings: if any part of the work is in, to or upon a residence or dwelling unit (for example apartments above ground-floor offices), the work on that unit is a home improvement and section 2 applies to it. Flag to the user; the template should not try to split one contract.

### 3.2 Rules that DO apply

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-COM-01 | Licence: contractor licensed in the correct classification for the work (CA-LIC-01, -02, -04). | BPC 7031, 7048, 7125 | NO | |
| CA-COM-02 | Licence number in the contract. | BPC 7030.5 | NO | |
| CA-COM-03 | CSLB notice for prime contractors on all written contracts other than HICs and service and repair contracts, in at least **10-point** type: **"Contractors are required by law to be licensed and regulated by the Contractors State License Board which has jurisdiction to investigate complaints against contractors if a complaint regarding a patent act or omission is filed within four years of the date of the alleged violation. A complaint regarding a latent act or omission pertaining to structural defects must be filed within 10 years of the date of the alleged violation. Any questions concerning a contractor may be referred to the Registrar, Contractors State License Board, P.O. Box 26000, Sacramento, CA 95826."** Failure is cause for discipline. | BPC 7030(a), (c) (amended Stats. 2020 ch. 312, SB 1474, eff. 2021-01-01) | YES | at least 10-point; placement free |
| CA-COM-04 | Progress payments: owner pays undisputed amounts within 30 days of payment demand unless the contract says otherwise; 150% disputed withholding cap; 2% per month penalty. | CIV 8800 | NO | Contract may set its own schedule in writing. State one. |
| CA-COM-05 | Retention: no more than **5% of each payment** and **5% of contract price** (contracts on or after 2026-01-01); same cap flows down to subs, and a sub's percentage may not exceed the prime's. Bond exception only as stated in CIV 8811(b)(2). | CIV 8811 | NO | Template field `{{retention_percent}}` must be validated as at most 5. |
| CA-COM-06 | Retention release: within 45 days after completion (owner to prime); within 10 days of receipt (prime to subs); 2% per month penalty; anti-waiver. | CIV 8812, 8814, 8818, 8820 | NO | |
| CA-COM-07 | Pay subs within 7 days of receiving each progress payment unless otherwise agreed in writing; 2% per month. | BPC 7108.5 | NO | Flow-down clause. |
| CA-COM-08 | Indemnity: no indemnity of a party for its sole negligence or wilful misconduct (2782(a)); owner's active negligence carved out of any contractor indemnity (2782(c)); sub-to-GC indemnity limits and tender procedure (2782.05). | CIV 2782(a), (c); 2782.05 | NO | |
| CA-COM-09 | Lien regime: preliminary notices from subs and suppliers within 20 days of first furnishing; statutory waiver forms; lien deadlines; owner's optional notice of completion within 15 days of completion, with the duty (CIV 8190, CA-LIEN-05a; also stated in the CIV 8202 notice) to send copies within 10 days to the contractor and preliminary-notice claimants by registered or certified mail. The four-unit residential exemption from that mailing does not apply to commercial owners. | CIV 8180-8182, 8200-8204, 8124-8138, 8412-8414 | NO (waiver forms SUBST.) | |
| CA-COM-10 | Electronic signatures valid under UETA where the parties agreed to transact electronically. The exclusions in CA-ESIG-02 are aimed at consumer transactions; none was found that is specific to a commercial construction contract. | CIV 1633.7, 1633.3 | NO | See section 3.1 on whether the home solicitation sections can reach a commercial contract. |
| CA-COM-11 | Space in the contract for the owner's name, address and place of business and the construction lender's name and address (CA-LIEN-05b). Unlike an HIC, the lender space is required. | CIV 8170 | NO | Tier M. |
| CA-COM-12 | **Sufficient-funds rule.** A person may not enter a contract for labour or services with a construction contractor if the person knows or should know the contract does not include funds sufficient for the contractor to comply with the laws governing the work. A rebuttable presumption of compliance arises if the contract is a single written document containing: names, addresses and telephone numbers of both parties; description of the labour or services and start and end dates; the contractor's state tax employer identification number; the contractor's workers' compensation policy number and the insurer's name, address and telephone number; for any contractor vehicle used, its VIN, liability policy number and insurer details; the address of any worker housing; the total number of workers, total wages and wage payment dates; any commission or other payment to the contractor; the number of independent contractors with their licence numbers and a copy of each one's agreement; and all parties' signatures and the date. Estimates are allowed where numbers are not yet known. Keep the contract at least **4 years** after it ends. Exempt: a person contracting for work on their own home residence where a family member lives there for at least part of the year, and parties to a collective bargaining agreement covering the workers. Employee remedy: the greater of actual damages or $250 per employee (first violation) / $1,000 (later violations), plus fees. | LAB 2810 | NO | Tier M. The commercial contract and the bid package should carry these fields so the owner gets the presumption. Not needed for a homeowner's own residence; a landlord's rental property is not within the exemption as worded. |

### 3.3 Not verified for the commercial contract (see section 8)

Pay-if-paid and pay-when-paid clauses, limitation-of-liability clauses, liquidated damages (CIV 1671), and the arbitration-notice rule for real property contracts (Code of Civil Procedure 1298) were not opened in this pass. Treat as attorney items.

## 4. Solar installation agreement

`DocType`: `solar_installation_agreement`. Purchase and installation of a rooftop photovoltaic (PV) system by the property owner. A lease or power purchase agreement is a different transaction (section 4.7) and is not what this document is.

The template needs three inputs before it can pick the right rules: `{{property_use}}` (residential or commercial), `{{electric_utility}}` (LADWP inside the City of Los Angeles; Southern California Edison in most of the rest of Los Angeles County; a few cities run their own utilities), and `{{buyer_is_senior}}`.

### 4.1 Which regime applies

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-SOL-01 | A solar energy system installed on residential property is a "home improvement": the statutory list names "solar energy systems". **Every rule in section 2 applies to a residential solar agreement** (CA-HIC-00a to CA-HIC-37, CA-CXL-01 to -05, CA-FIN-01 to -03, CA-ARB-01, -02): "Home Improvement" heading, $1,000 / 10% downpayment cap, progress payments only for work done or material delivered, no advance payment from a lender, Mechanics Lien Warning, CSLB notice, three- or five-day right to cancel with the Notice of Cancellation, financing condition. | BPC 7151(a); 7159; 7159.5 | as in section 2 | Tier L. The residential solar agreement is the residential contract of section 2 plus the items below. |
| CA-SOL-02 | "Solar energy system" for the home improvement article and for the disclosure rule = a solar energy device installed on a residential building (BPC 7151(c) adds "or residential property") whose primary purpose is collecting and distributing solar energy to generate electricity, producing **at least 1 kW and not more than 5 MW** alternating current rated peak electricity, and meeting the eligibility criteria under Public Resources Code 25782. | BPC 7151(c); 7169(g) (7169 amended Stats. 2021 ch. 188, SB 826, eff. 2022-01-01) | NO | Tier L. A PV system under 1 kW AC is still a home improvement under 7151(a) but is outside the 7169 disclosure rule. Public Resources Code 25782 was not opened (section 8). |
| CA-SOL-03 | BPC 7169 does not apply to a system installed as a standard feature on new construction. | BPC 7169(h) | NO | Tier L. Retrofits are never this case. |
| CA-SOL-04 | **Commercial property:** BPC 7169 and the home improvement article do not apply (both are limited to residential buildings or property). The commercial solar agreement follows section 3 (CA-COM-01 to -12), plus CA-SOL-13 to -20 below. | BPC 7151, 7169(g) | NO | Tier L. Mixed-use caution from section 3.1 applies. |

### 4.2 Solar Energy System Disclosure Document (residential only)

| ID | Requirement | Citation | Verbatim | Format |
|---|---|---|---|---|
| CA-SOL-05 | The solar energy system company must give the consumer the CSLB "solar energy system disclosure document" **before completion of a sale, financing or lease** of a solar energy system. It must be **printed on the front page or cover page of every solar energy contract**. | BPC 7169(b) | YES: use the CSLB document (text in section 4.8) | front page or cover page |
| CA-SOL-06 | The disclosure document must be printed in **boldface 16-point type** and include: (1) the total cost and payments for the system, including financing costs; (2) how and to whom customers may provide complaints; (3) the consumer's right to the applicable cancellation period under BPC 7159. | BPC 7169(b)(1)-(3) | YES (CSLB document) | 16-point bold |
| CA-SOL-07 | The contract for sale, financing or lease **and** the disclosure document must be written in the same language as was principally used in the oral sales presentation or in the print or digital marketing material given to the consumer. | BPC 7169(d) | NO | Template field `{{sales_language}}`; if not English, the draft must be flagged for translation, not issued in English. |
| CA-SOL-08 | CSLB may add supporting information after the front page: amounts and sources of financing; the calculations used by the salesperson to determine how many panels are needed and how much energy they will generate; additional monthly utility fees, turn-on charges, monitoring fees; terms of any guaranteed rebate; final contract price without possible rebates; contractor's licence number; impacts of installation not performed to code; types of malfunctions; lease versus purchase; effect of financing or contract terms on a later sale of the home; an output calculator. | BPC 7169(c)(1)-(12) | NO (optional content) | CSLB publishes a "Solar Energy System Supporting Information" document (linked from its Solar Smart page; not opened, section 8). Good practice for our draft: attach the audit's production estimate with its assumptions. |
| CA-SOL-09 | PACE-financed solar: the PACE Financing Estimate and Disclosure form (SHC 5898.17(b)) satisfies BPC 7169 for the **financing contract only**, not for the installation contract. | BPC 7169(e) | NO | The installation agreement still needs the CSLB disclosure document. Residential PACE is outside this product (section 7.6). |
| CA-SOL-10 | Two different money figures. The disclosure document states the **total cost including financing** (and "energy / power cost if applicable"); the HIC "Contract Price" **excludes** finance charges, which go under a separate "Finance Charge" heading (CA-HIC-09, -10). | BPC 7169(b)(1); 7159(d)(5), (6); 7159.5(a)(1), (2) | NO | Template computes both and checks disclosure total = contract price + finance charge. |

Placement conflict to resolve with the attorney: BPC 7169(b) puts the disclosure document on the "front page or cover page", and BPC 7159(c)(3)(B) requires the buyer's signing date, the contractor's name, address and email for the Notice of Cancellation, and the contractor's telephone number "on the first page". Working rule: the disclosure document is a cover page, and the first page of the contract proper carries the BPC 7159 first-page items. Listed in section 8.

### 4.3 CPUC Solar Consumer Protection Guide (investor-owned utility territory only)

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-SOL-11 | Solar providers submitting interconnection applications for **residential** customers of PG&E, SCE, SDG&E, Bear Valley Electric Service, PacifiCorp and Liberty must collect the customer's **initials and signature** on the California Solar Consumer Protection Guide. The customer must be given time to read it before signing. The Guide should be given in the language in which the customer was first contacted (Version 4 exists in English, Spanish, Chinese (Simplified), Korean, Vietnamese, Tagalog, Armenian, Dari and Portuguese). | CPUC Decision 18-09-044 as modified by Decision 20-02-011, as described on the CPUC "California Solar Consumer Protection Guide" page | YES: the Guide is a CPUC publication and is used unaltered; it is not part of our draft | Tier A, opened 2026-11-14. The decisions themselves were not opened (section 8). |
| CA-SOL-12 | **Version cut-over:** interconnection applications containing solar installation contracts signed on **2026-12-15 or later** must include **Version 4** of the Guide (published 2025). Earlier contracts use Version 3 (2022) with its 2025 addendum on the Solar Billing Plan. | same CPUC page | n/a | Tier A. The template must pick the version from `{{contract_sign_date}}`. |
| CA-SOL-13 | Under Decision 18-09-044 the provider uploads with the interconnection application: the signed pages of the Guide, the solar installation contract, and the CSLB Solar Energy System Disclosure Document (described for PG&E, SCE, SDG&E). | same CPUC page | n/a | Tier A. So in SCE territory the contract and disclosure document produced here are filed with the utility: they must be complete and signed. |

Los Angeles consequence. The Guide requirement names six utilities; LADWP, the municipal utility that serves the City of Los Angeles, is not one of them, and the CPUC page tells customers of other providers to contact their own utility. So: `{{electric_utility}}` = SCE means CA-SOL-11 to -13 apply to a residential job; `{{electric_utility}}` = LADWP means they do not, and the BPC 7169 disclosure document (which is state contractor law, not utility regulation) still does. The Guide and its signature pages are residential requirements; the CPUC page does not extend them to non-residential customers.

### 4.4 Licence classes that may install PV; salespersons

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-SOL-14 | **C-46 Solar Contractor:** "A solar contractor installs, modifies, maintains, and repairs thermal and photovoltaic solar energy systems. A licensee classified in this section shall not undertake or perform building or construction trades, crafts, or skills, except when required to install a thermal or photovoltaic solar energy system." | 16 CCR 832.46, as published on the CSLB C-46 classification page | NO | Tier A (CSLB page opened twice: 2026-11-13 in the browser, 2026-11-14). The CCR text itself was not read on the Office of Administrative Law site. |
| CA-SOL-15 | **C-10 Electrical Contractor:** places, installs, erects or connects "any electrical wires, fixtures, appliances, apparatus, raceways, conduits, solar photovoltaic cells or any part thereof, which generate, transmit, transform or utilize electrical energy in any form or for any purpose." | 16 CCR 832.10, as published on the CSLB C-10 classification page | NO | Tier A. |
| CA-SOL-16 | **A General Engineering** contractors "are authorized to install solar energy systems". **B General Building** contractors may do so "since a solar energy system constitutes the use of two unrelated building trades or crafts". C-4, C-36 and C-53 are listed for solar thermal or pool heating only, not PV. | CSLB "Solar Smart" page; for B see BPC 7057 (amended Stats. 2013 ch. 377, eff. 2014-01-01) | NO | Tier A for the CSLB statement; BPC 7057 is Tier L. BPC 7057(b) is the limit behind the B statement: a B contractor may not take a prime contract for a single trade other than framing or carpentry unless it holds the specialty class or subcontracts to an appropriately licensed contractor. The contract should state the class under which the PV work is performed: `{{pv_license_class}}` in {A, B, C-10, C-46}. |
| CA-SOL-17 | Workers' compensation: C-46 and C-10 are not among the classes barred from the no-employee exemption before 2028 (CA-LIC-04), so either statement in CA-HIC-30 may be correct for a solar contractor. If the same contractor also holds C-39 (roofing) or C-20, option (A) is unavailable. | BPC 7125(b)(2) | NO | Tier L. |
| CA-SOL-18 | Solar sales representatives must be registered with CSLB as home improvement salespersons, unless exempt (officers, partners and qualifiers of record of the licensee; sales begun by the buyer at a fixed-location general merchandise retailer; appointment setters; service repairpersons). Before soliciting, the salesperson must identify to the owner or tenant the contractor's business name and licence number. The salesperson's name and registration number go in the contract (CA-HIC-06). | BPC 7152(a)-(e); 7159(d)(2); CSLB Solar Smart page | NO | BPC 7152 is Tier M; the rest Tier L and Tier A. Placeholders `{{salesperson_name}}`, `{{salesperson_registration_number}}`. |

Battery storage is not settled. CSLB amended 16 CCR 810, 832.10 and 832.46 on battery energy storage systems; the Office of Administrative Law approved the amendment on 2024-06-05, but the CSLB laws page (opened 2026-11-14) says the effective date is "temporarily stayed by court order" in San Diego County Superior Court Case No. 27-2024-00029818-CU-TT-CTL, and it lists a new 2026 proposed rulemaking on 832.46. Until that is resolved, a draft that includes storage should require the storage scope to be performed by a C-10 licensee or by an A or B licensee acting within its class, and should list the question in its unfilled items. This product's measure list has no storage measure, so this is a guard only.

### 4.5 Permits, standards and interconnection: duties the contract must allocate

No statute opened in this review says which party must obtain the building permit, the association approval or the utility interconnection. The rules below define what has to be obtained; the contract must say who obtains each and that energizing waits for the utility's permission. CSLB's consumer advice (Solar Smart page) is to "make sure the contract specifies that the contractor will pull all required building permits".

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-SOL-19 | **Building permit.** A city or county must approve an application to install a solar energy system administratively, through a building permit or similar non-discretionary permit; review is limited to health and safety requirements. A use permit may be required only on a finding, on substantial evidence, of a specific adverse impact on public health or safety. Applies to all solar energy systems, not only residential. | GOV 65850.5(b), (c) (amended Stats. 2019 ch. 494, AB 754, eff. 2020-01-01) | NO | Tier L. Allocation clause: `{{permit_responsible_party}}`, default contractor. The permit authority is the Los Angeles Department of Building and Safety inside the city; the county or the other city elsewhere (local procedures not opened, section 8). |
| CA-SOL-20 | **Expedited residential permit.** Every city and county must have an expedited, streamlined process for "small residential rooftop solar energy systems": no larger than **10 kW AC** nameplate (or 30 kW thermal), on a single or duplex family dwelling, code-compliant, not above the legal building height. Complete applications that meet the local checklist must be approved; **one inspection** only (a separate fire inspection is possible where there is no agreement with the fire authority). Electronic submittal and electronic signatures on permit forms must be allowed unless the ordinance explains why not. | GOV 65850.5(g), (h), (j)(3) | NO | Tier L. Schedule clause can assume a single inspection for systems of 10 kW AC or less on a house or duplex. |
| CA-SOL-21 | **Online instant permitting.** Cities and counties above the size thresholds must offer an online, automated permitting platform (such as SolarAPP+) that verifies code compliance and issues permits in real time to a licensed contractor for residential solar systems, and paired storage, up to **38.4 kW AC**; compliance date 2023-09-30 for jurisdictions over 50,000 population. | GOV 65850.52 | NO | **One mirror only** (FindLaw, 2026-11-14; the second mirror's page was not found). Treat as background, not as a check. The permit goes to a licensed contractor, which supports the default allocation in CA-SOL-19. |
| CA-SOL-22 | **Dig notice.** A solar permit application must include a reference to the duty to notify the regional notification center before excavating, including before installing a grounding rod (GOV 4216 et seq.). | GOV 65850.5(f)(4) | NO | Tier L. Contractor duty clause. |
| CA-SOL-23 | **Equipment standards.** A solar energy system for producing electricity must meet all applicable safety and performance standards established by the California Electrical Code, the Institute of Electrical and Electronics Engineers, and accredited testing laboratories such as Underwriters Laboratories, and, where applicable, CPUC rules on safety and reliability. | GOV 65850.5(f)(3); CIV 714(c)(3) (CIV 714 amended Stats. 2014 ch. 521, AB 2188, eff. 2015-01-01) | NO | Tier L. Contractor warranty of compliance; equipment schedule lists the listing for modules and inverters. |
| CA-SOL-24 | **Covenants and owners' associations.** A covenant, deed restriction or governing-document provision that effectively prohibits or restricts installation or use of a solar energy system is void. Reasonable restrictions are allowed: for PV, one that does not raise cost by more than **$1,000** or cut efficiency by more than **10%** as originally specified. An association must approve or deny in writing; if it does not deny in writing within **45 days** of receiving the application, the application is deemed approved (unless the delay comes from a reasonable request for more information). A city or county may not condition a solar permit on association approval. | CIV 714(a), (b), (d)(1)(B), (e); GOV 65850.5(i) | NO | Tier L. Allocation clause: `{{hoa_approval_responsible_party}}`, default owner, with the contractor supplying drawings. Applies to common interest developments of either kind (CIV 714(a) refers to governing documents under CIV 4150 or 6552). |
| CA-SOL-25 | **Interconnection, state net metering statute.** The statutory net energy metering programme covers customer generators up to **1 MW** on the customer's premises, sized primarily to offset the customer's own load, on electrical corporations, publicly owned utilities and cooperatives. It **does not apply to a local publicly owned electric utility that serves more than 750,000 customers and also conveys water to its customers**. | PUC 2827(b)(3), (b)(4)(A) | NO | Tier M. The exclusion describes LADWP (the statute does not name it; that reading is an inference, section 8). So inside the City of Los Angeles, interconnection and export credit are governed by LADWP's own programme and agreement, not by PUC 2827 or CPUC tariffs. |
| CA-SOL-26 | **Interconnection, SCE territory.** New applications are on the Net Billing Tariff, adopted by CPUC Decision 22-12-056 as the successor to the second net metering tariff, for customers who submit an interconnection application on or after **2023-04-15**. | CPUC "Net Billing Tariff" page | NO | Tier A. The contract should name the tariff the system is designed for and say that export compensation is set by the utility tariff and can change; the savings numbers in the audit must use the same tariff. |
| CA-SOL-27 | **Prevailing wage on larger net-billing projects.** Construction after 2023-12-31 of a renewable electrical generation facility, and any associated battery storage, that will receive service under a tariff developed under PUC 2827.1 is a public works project for prevailing wage purposes. The contractor must pay prevailing wages (apprentices at apprentice rates), keep payroll records under LAB 1776, and send certified payroll records to the CPUC twice a year (July 1 and December 31). **Exempt:** a residential facility of **15 kW or less**; a residential facility on a single-family home; a project already a public work; a facility serving only a modular home, a modular home community, or multiunit housing of two stories or fewer. After an enforced wilful violation the facility stays eligible for the tariff only if restitution and all penalties are paid. The CPUC must require each large electrical corporation to put this in its 2827.1 tariff. | PUC 769.2(a)-(g) | NO | Tier M. **This reaches a commercial rooftop PV system in SCE territory on the Net Billing Tariff, whatever its size**, and a residential system over 15 kW that is not on a single-family home. The commercial solar agreement and the bid package need a prevailing-wage clause and price basis when `{{electric_utility}}` is SCE. Whether LADWP's programme triggers it is not answered by the text read (LADWP is not a "large electrical corporation" and its programme is not a 2827.1 tariff, which points to no): section 8. |

### 4.6 Production estimates, guarantees and warranties

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-SOL-28 | **No mandatory production guarantee or minimum warranty term was found** in the statutes opened for a purchase-and-install contract: BPC 7159, 7159.5 and 7169 contain none; PUC 2827 contains no warranty requirement (checked on both mirrors). | BPC 7159, 7169; PUC 2827 | n/a | Negative finding. A ten-year warranty condition is widely said to attach to systems on the CPUC net metering and net billing tariffs; it could not be confirmed on any official page opened (section 8). The template should offer warranty terms as business terms with blanks, not present any term as required by law. |
| CA-SOL-29 | If the seller states savings or production figures, the legislative standard for the disclosure material is "accurate, clear, and concise information regarding the installation of a solar energy system, total costs of installation, anticipated savings, the assumptions and inputs used to estimate the savings, and the implications of various financing options". | BPC 7169(a) | NO | Tier L. This is addressed to CSLB's document, not directly to the contract, but it is the benchmark: every estimate in the agreement states its assumptions and inputs. |
| CA-SOL-30 | False, misleading or deceptive advertising used to induce a contract for a work of improvement, and a substantial misrepresentation or false promise likely to induce one, are misdemeanours and cause for discipline. A person induced to contract by knowingly false or fraudulent representations may recover a **$500** penalty, reasonable attorney's fees and actual damages from the contractor or solicitor. | BPC 7161(a), (b); BPC 7160 | NO | Tier M. Applies to any work of improvement, so to commercial solar as well. Reason the agreement labels estimates as estimates and shows low, expected and high values. |
| CA-SOL-31 | A written warranty on consumer goods must be in "simple and readily understood language", must clearly identify the party making it, and must conform to the federal warranty disclosure standards (15 U.S.C. 2301 et seq.). No formal words such as "warrant" or "guarantee" are needed to create an express warranty, and using them creates one. | CIV 1793.1(a)(1); CIV 1791.2 | NO | Tier M. "Consumer goods" are new products bought primarily for personal, family or household purposes (CIV 1791(a), one mirror). Whether modules and inverters that become fixtures are consumer goods was not resolved (section 8). Either way, write the residential warranty clause to this standard and name the warrantor for each warranty (manufacturer for equipment, contractor for workmanship). |

CSLB's consumer advice, not law: "If you were promised a minimum amount of power generation, be sure it's written into the contract." If the plan promises a production figure, the template should carry it into the agreement or the guarantee addendum (section 6) rather than leave it in sales material.

### 4.7 Leases and power purchase agreements (guard only)

A contract under which a third party keeps ownership of the system and sells electricity or leases the system to a **residence** is an "independent solar energy producer" contract. It needs its own disclosure (good-faith estimate of kilowatt-hours to be delivered; plain-language pricing terms and a good-faith price per kilowatt-hour; operation and maintenance responsibilities; what happens on transfer of the residence; disposition at end of term) and the producer must record a "Notice of an Independent Solar Energy Producer Contract" against title within **30 days** of signing, with a 14-point title and the statutory statement in PUC 2869(b)(1). PUC 2869 (added Stats. 2008 ch. 535, eff. 2009-01-01), Tier L. None of that applies to a purchase. The template must refuse to draft a lease or power purchase agreement on the purchase form.

### 4.8 Text of the CSLB Solar Energy System Disclosure Document

Copied from the CSLB documents opened 2026-11-14: three-day version `https://www.cslb.ca.gov/Resources/Contractors/SolarDisclosureDoc.pdf` (form number 13L-6 (05/2018)); five-day version `https://www.cslb.ca.gov/Resources/Contractors/RightToCancel.Dec2020.Eng.pdf`. Spanish versions are linked from the CSLB Solar Smart page. Print in boldface 16-point type on the front page or cover page. Use the CSLB wording as published; do not paraphrase.

> SOLAR ENERGY SYSTEM DISCLOSURE DOCUMENT
>
> This disclosure shall be printed on the front page or cover page of every solar energy contract for the installation of a solar energy system on a residential building.
>
> The TOTAL COST for the solar energy system (including financing and energy / power cost if applicable) is: $ {{solar_total_cost_including_financing}}.
>
> To make a complaint against a contractor who installs this system and/or the home improvement salesperson who sold this system, contact the Contractors State License Board (CSLB) through their website at www.cslb.ca.gov (search: "complaint form"), by telephone at 800-321-CSLB (2752), or by writing to P.O. Box 26000, Sacramento, CA 95826.
>
> If the attached contract was not negotiated at the contractor's place of business, you have a Three-Day Right to Cancel the contract, pursuant to Business and Professions Code (BPC) section 7159, as noted below. For further details on canceling the contract, see the Notice of Cancellation, which must be included in your contract.
>
> Three-Day Right to Cancel
>
> You, the buyer, have the right to cancel this contract within three business days. You may cancel by e-mailing, mailing, faxing, or delivering a written notice to the contractor at the contractor's place of business by midnight of the third business day after you received a signed and dated copy of the contract that includes this notice. Include your name, your address, and the date you received the signed copy of the contract and this notice.
>
> This document was developed through coordination of the California Contractors State License Board and the California Public Utilities Commission pursuant to Business and Professions Code section 7169.

Five-day version (buyer aged 65 or older), differences only: the fourth paragraph reads "If the attached contract was not negotiated at the contractor's place of business, and you are 65 years of age or older, you have a Five-Day Right to Cancel the contract, pursuant to Business and Professions Code section 7159, as noted below."; the notice is headed "Five-Day Right to Cancel" with "five business days" and "fifth business day"; the telephone number is printed "800-321-CSLB (2-7-5-2)" and the address "PO Box 26000".

Notes for the template agent:

- The CSLB document prints "e-mailing"; the BPC 7159 notice (section 2.5) prints "emailing". Each text is reproduced as its source prints it.
- The CSLB document carries only the first paragraph of the right-to-cancel notice. The full two-paragraph notice of BPC 7159(e)(6), signed and dated by the owner, is still required in the contract (CA-HIC-34), with the Notice of Cancellation form (CA-HIC-35).
- CSLB publishes no seven-day (disaster) version. For a disaster-repair contract (CA-HIC-36) there is no CSLB disclosure document to copy: stop and refer to the attorney.
- The three-day form is numbered 13L-6 (05/2018) and has not been reissued since; it is still the document CSLB publishes and links from its Solar Smart page.

## 5. Contractor bid package / request for proposals

`DocType`: `bid_package_rfp`. The owner's invitation to licensed contractors to price the retrofit plan, with a bid form and the form of contract.

Finding that shapes this section: in the provisions opened, California law says very little about what a **private owner's** request for proposals must contain. The rules bind (a) the contractor's bid, (b) a contractor's own call for sub-bids, and (c) the contract that results. So the package does three jobs: it makes bidders supply what the law requires them to state; it gives, at bid time, the notices that must be given then or never; and it attaches a form of contract that already complies with section 2 (home) or section 3 (commercial), so that no bid can be accepted on non-compliant terms.

Not found in the provisions opened (so the template must not present them as legal requirements): any minimum number of bids, any statutory bid form, or any bid-bond requirement for private work. Public-works bidding law (Public Contract Code; BPC 7028.15) does not apply to a privately funded project and was not opened.

### 5.1 Licensing and identity items every bid must state

| ID | Requirement | Citation | Verbatim | Applies to | Notes |
|---|---|---|---|---|---|
| CA-BID-01 | A licensee must include its licence number in all construction contracts, in "subcontracts and calls for bid", and in advertising. | BPC 7030.5 | NO | home and commercial | Tier L. The duty is the licensee's: the bid a contractor returns, and any call for sub-bids it issues, must show its number. The bid form has a required field `{{bidder_license_number}}` plus class and expiry; a bid without it is non-responsive. |
| CA-BID-02 | Submitting a bid is itself acting as a contractor: "contractor" includes any person who "undertakes to or offers to undertake to, or purports to have the capacity to undertake to, or submits a bid to" construct, alter, repair or improve a building or structure. Acting as a contractor without a licence is a misdemeanour (first conviction: fine up to $5,000, up to six months in county jail, or both), unless exempt. | BPC 7026; BPC 7028(a), (b) | NO | home and commercial | BPC 7026 Tier M; BPC 7028 one mirror. Invitation text: bids are accepted only from contractors licensed in the class the work needs on the bid date and throughout the work (CA-LIC-02). The owner checks each number on the CSLB licence lookup before award: signing-procedure item, not document text. |
| CA-BID-03 | Classification fit. PV: A, B, C-10 or C-46 (CA-SOL-14 to -16). A general building (B) contractor may take a prime contract only if it involves at least two unrelated trades other than framing or carpentry, or the B contractor holds the specialty class, or it subcontracts that work to an appropriately licensed contractor. | BPC 7057(b); CSLB pages | NO | home and commercial | Tier L and Tier A. Bid form: bidder states the class under which each measure will be performed and names the licensed subcontractor for any measure outside its own class. The class-to-measure mapping for the non-solar measures was not verified (section 8). |
| CA-BID-04 | Workers' compensation: bidder states either that a current certificate is on file with CSLB (insurer, policy number) or that it has filed the no-employee exemption. The exemption is unavailable to C-8, C-20, C-22, C-39 and D-49 licensees, and ends for everyone except no-employee joint ventures on 2028-01-01. | BPC 7125 | NO | home and commercial | Tier L. Feeds the notice in CA-HIC-30 and the fields in CA-COM-12. |
| CA-BID-05 | Contractor's bond: $25,000 on file as a licence condition. | BPC 7071.6(a) | NO | home and commercial | Tier M. Bid form asks only for confirmation that the licence is active and bonded; the amount is statutory, not negotiable. |
| CA-BID-06 | Home improvement salespersons: anyone other than the licensee's officers, partners or qualifier of record who solicits or negotiates the home improvement contract for a bidder must be registered, must identify the contractor's business name and licence number before soliciting, and is named with registration number in the contract. | BPC 7152; 7159(d)(2) | NO | home | BPC 7152 Tier M. Bid form fields for the salesperson. |

### 5.2 Notices and terms that must be settled at bid time

| ID | Requirement | Citation | Verbatim | Applies to | Notes |
|---|---|---|---|---|---|
| CA-BID-07 | **Bond notice, or lose the retention exception.** The 5% retention cap does not apply to a direct contractor or subcontractor that gave a subcontractor written notice "before, or at, the time that the bid is requested" that a faithful performance and payment bond will be required, where the subcontractor then fails to furnish one from an admitted surety insurer. | CIV 8811(b)(2) | NO (content fixed, wording free) | commercial; residential that is mixed-use or over four stories | Tier L. If bonds will be required of subcontractors, the package (and each bidder's own call for sub-bids) must say so in writing at bid time. By its words the exception protects the direct contractor or subcontractor that gave the notice; it does not create an owner exception to the 5% cap against the direct contractor. |
| CA-BID-08 | Retention stated in the bid documents may not exceed 5% of each payment and 5% of the contract price, and no lower tier may be held at a higher percentage than the owner holds from the direct contractor. | CIV 8811(b)(1) | NO | commercial; residential mixed-use or over four stories | Tier L. `{{retention_percent}}` validated at most 5. For a residential project that is not mixed-use and does not exceed four stories the cap does not apply (CIV 8811(b)(3)). |
| CA-BID-09 | Home jobs: the payment terms a bidder may propose are fixed by law. Downpayment no more than $1,000 or 10% of the contract price, whichever is less; every other payment only for work performed or material delivered; no advance from a lender or financier. The exemption is a bidder that furnishes a full performance and payment bond, lien and completion bond, or approved equivalent or joint control. | BPC 7159.5(a)(3), (5), (8) | NO | home | Tier L. The invitation tells bidders that a bid proposing a larger deposit or front-loaded payments will be rejected unless it states the bond relied on. |
| CA-BID-10 | Home jobs: subcontractor disclosure. The contract must say whether subcontractors will be used and, if so, carry the statutory disclaimer that a list "is required to be provided, upon request, along with the names, contact information, license number, and classification of those subcontractors". | BPC 7159(c)(7) | YES (in the contract) | home | Tier L. The bid form makes the request now: a table of subcontractor name, contact, licence number and classification. |
| CA-BID-11 | Home jobs: insurance disclosure. The contract notice must state which is true: no commercial general liability insurance; insured (insurer and telephone number); self-insured; or, for a limited liability company, liability insurance or other security as required by law. | BPC 7159(e)(1) | YES (in the contract) | home | Tier L. Bid form collects the facts needed to choose statement (A), (B), (C) or (D). |
| CA-BID-12 | Home jobs: the owner's right to require a performance and payment bond must be stated in the contract near the signatures. | BPC 7159(c)(6) | NO | home | Tier L. The package asks each bidder to price the bond as an alternate, so the right is usable. |
| CA-BID-13 | Commercial jobs: sufficient-funds presumption. To give the owner the presumption, the single written contract must contain the items in CA-COM-12 (employer identification number, workers' compensation policy number and insurer, number of workers and total wages, independent contractors and their licence numbers, and so on). | LAB 2810(b), (d) | NO | commercial; rental residential (the exemption covers only the person's own home residence) | Tier M. Bid form collects these, with estimates allowed. |
| CA-BID-14 | Commercial jobs: flow-down terms each bidder accepts for its subcontracts: pay subcontractors within 7 days of each progress payment unless otherwise agreed in writing; pay retention on within 10 days of receipt; indemnity from subcontractors limited as in CIV 2782.05; subcontract form has spaces for owner, direct contractor and construction lender. | BPC 7108.5; CIV 8814; CIV 2782.05; CIV 8170(b) | NO | commercial | Tier L except CIV 8170 (Tier M). |
| CA-BID-15 | Form of contract attached to the package must itself comply: indemnity within CIV 2782 (no indemnity for the owner's sole negligence or wilful misconduct, and none to the extent of the owner's active negligence); payment and retention as in section 1.5; licence notice (BPC 7030(a) for commercial; the section 2 notices for home). | CIV 2782(a), (c); BPC 7030 | as in sections 2, 3 | home and commercial | Tier L. |
| CA-BID-16 | Solar scope in SCE territory: where the PV system will take service on the Net Billing Tariff and is not within an exemption (residential 15 kW or less; residential on a single-family home; two-story-or-lower multiunit housing; modular homes), the work is a public work for prevailing wage purposes. | PUC 769.2 | NO | commercial PV; larger multi-family PV | Tier M. The invitation must tell bidders to price on prevailing wages and to accept the payroll-record duties. See CA-SOL-27 for the LADWP question. |
| CA-BID-17 | Solar scope on a home: each bidder supplies the total cost including financing for the CSLB disclosure document, which must reach the owner before the sale is completed, and the language used in its sales presentation or marketing material. | BPC 7169(b), (d) | NO | home PV | Tier L. |

### 5.3 Conduct rules on what bidders say

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-BID-18 | False, misleading or deceptive advertising, substantial misrepresentation, or a false promise used to obtain a contract for a work of improvement is a misdemeanour and cause for discipline; a person so induced may recover $500, attorney's fees and actual damages. | BPC 7161(a), (b); BPC 7160 | NO | Tier M. The bid form asks bidders to state the basis of any savings, rebate or production figure they quote, and the package gives them the audit's assumptions so that bids are comparable. |

### 5.4 A bid is not the contract

For a home job, an accepted proposal is a home improvement contract and would have to carry every element of section 2, signed before work starts (CA-HIC-02). The package should therefore state that no bid is accepted, and no work or deposit is authorised, until the parties sign the attached form of contract. For a commercial job the same statement avoids a contract formed on the bidder's own terms. This is drafting guidance derived from BPC 7159(b) and (d), not a separate statutory rule.

Electronic delivery and signature of bids: valid under CIV 1633.7 where the parties have agreed to deal electronically; none of the separately-signed notices in CA-ESIG-02 is part of a bid.

## 6. Energy savings guarantee addendum

`DocType`: `energy_savings_guarantee`. An addendum to the retrofit contract or solar agreement in which the contractor promises a level of energy savings or PV production and a remedy if it is not reached.

### 6.1 What California law does and does not say

**No California statute was found that prescribes the content or form of an energy savings guarantee in a private contract, residential or commercial.** The addendum has no mandated notice, heading, type size or numeric limit of its own. What follows are the general rules that catch it. The template must present the guarantee terms (baseline, measurement method, term, remedy, exclusions) as business terms with blanks, and must not describe any of them as required by statute.

The one California statute written for guaranteed-savings contracts does not apply here: Government Code 4217.10 et seq. defines an "energy service contract" as a contract "entered into by a public agency" for energy or conservation services from an "energy conservation facility", which must be located in public buildings or on land owned by public agencies (GOV 4217.11, one mirror; the rest of that chapter was not opened). A privately owned home or office is outside it.

### 6.2 Rules that apply when a guarantee is given

| ID | Requirement | Citation | Verbatim | Applies to | Notes |
|---|---|---|---|---|---|
| CA-ESG-01 | The addendum is part of the home improvement contract: it must be in writing and signed by the parties before the work it covers starts, and it must be named under the heading "List of Documents to be Incorporated into the Contract". | BPC 7159(d), (d)(12) | YES (heading, in the main contract) | home | Tier L. If the guarantee is added after signing, it is a change to the contract: written and signed before the affected work (CA-HIC-02, -20). |
| CA-ESG-02 | The guarantee does not move the contract outside the home improvement payment rules. Any payment, holdback or "performance fee" tied to verified savings must still respect the downpayment cap and the bar on payment ahead of work; a savings-based bonus payable after completion is not barred by those rules. | BPC 7159.5(a)(3), (5) | NO | home | Tier L for the rules; the statement about a post-completion bonus is a reading of them, not text (section 8). |
| CA-ESG-03 | An express warranty exists whenever a written statement arising out of a sale of a consumer good to a consumer has the manufacturer, distributor or retailer undertake to preserve or maintain the utility or performance of the good, or to provide compensation if there is a failure in utility or performance (paraphrase; exact wording not read). Formal words such as "warrant" or "guarantee" are not needed, and using them creates a warranty. Statements of value, opinion or commendation do not. | CIV 1791.2(a), (b) | NO | home | Tier M. A promise to pay the shortfall if equipment under-performs fits the "provide compensation" limb as far as it concerns goods sold to a consumer. Consequence: do not call estimates "guaranteed" anywhere outside this addendum. |
| CA-ESG-04 | Form of a written warranty on consumer goods: "simple and readily understood language"; clearly identify the party making the warranty; conform to the federal warranty disclosure standards (15 U.S.C. 2301 et seq. and the Federal Trade Commission rules). | CIV 1793.1(a)(1) | NO | home | Tier M. Addendum must name the guarantor (`{{guarantor_legal_name}}`), be in plain language, and state what is covered, for how long, what the guarantor will do, and how to claim. The federal rules were not opened (section 8). |
| CA-ESG-05 | The consumer warranty chapter applies to "any equipment or mechanical, electrical, or thermal component of a system designed to heat, cool, or otherwise condition air" but not to "the system as a whole where such a system becomes a fixed part of a structure". | CIV 1795.1 | NO | home | Tier M. So a heat pump's components carry consumer-warranty protection even though the installed system is a fixture; a guarantee about whole-house savings is less clearly inside the chapter (section 8). |
| CA-ESG-06 | Warranty repairs on consumer goods: the work order or repair invoice must carry the statutory buyer's-rights statement in **10-point boldface** (text in CIV 1793.1(a)(2)); if printed on the back, the face must say "Notice to Consumer: Please read important information on back." in 10-point boldface. | CIV 1793.1(a)(2) | YES (text at CIV 1793.1(a)(2), not reproduced: full wording was not read) | home, after the sale | Tier M. Not part of the addendum. Listed so the guarantee's claim procedure does not contradict it. |
| CA-ESG-07 | A savings or production promise used to win the job is within the misrepresentation rules: false, misleading or deceptive advertising, a substantial misrepresentation, or a false promise likely to induce a contract for a work of improvement is a misdemeanour and cause for discipline; civil remedy $500 plus attorney's fees and actual damages for knowingly false statements. | BPC 7161(a), (b); BPC 7160 | NO | home and commercial | Tier M. The guaranteed figure must come from the audit's low case or another stated, conservative basis; the addendum states the baseline, the assumptions and the measurement method. |
| CA-ESG-08 | Solar on a home: the benchmark for savings information is accuracy, clarity, and disclosure of "the assumptions and inputs used to estimate the savings"; optional CSLB supporting information includes the calculations for panel count and energy generated and "the terms and conditions of any guaranteed rebate". | BPC 7169(a), (c)(2), (c)(3), (c)(5) | NO | home PV | Tier L. A production guarantee states the guaranteed kilowatt-hours per year, the degradation allowance, the weather adjustment, the measurement device and the remedy. |
| CA-ESG-09 | The addendum cannot contract out of the non-waivable rules: the retention article (CIV 8820), subcontractor indemnity limits (CIV 2782.05(d)), the financing condition (BPC 7163(g)), or the lien-release forms (CIV 8126). | as cited | NO | home and commercial | Tier L. In particular, a release or offset given in exchange for a guarantee payment must not purport to waive lien rights outside the statutory forms. |
| CA-ESG-10 | Commercial: if the guarantee is secured by holding back part of the price until savings are verified, the holdback is at risk of being treated as retention: capped at 5% of each payment and 5% of the contract price, and payable within 45 days after completion, with a 2% per month penalty and no waiver. | CIV 8811, 8812, 8818, 8820 | NO | commercial | Tier L for the rules. Whether a savings holdback is "retention" is not answered by the text (section 8). Working rule: secure the commercial guarantee by a separate payment obligation, bond or letter of credit, not by a holdback above 5% or beyond 45 days. |
| CA-ESG-11 | Electronic signature of the addendum is valid where the parties agreed to deal electronically; the addendum contains no separately signed or initialed statutory text. | CIV 1633.7; 1633.3 | NO | home and commercial | Tier L. |

### 6.3 Commercial energy service agreements

For a privately owned commercial building no statute specific to guaranteed-savings or energy service agreements was found (GOV 4217.10 et seq. is public-agency only, section 6.1). The agreement is governed by the general rules already listed: licensing (section 1.1), CSLB notice for the prime contract (CA-COM-03), payment, retention and lien rules (sections 1.4, 1.5), indemnity limits (section 1.3), the sufficient-funds rule (CA-COM-12), prevailing wage where the scope includes PV on the Net Billing Tariff (CA-SOL-27), and the misrepresentation rules (CA-ESG-07). The consumer warranty chapter does not apply (goods not bought for personal, family or household purposes).

Not opened, so listed in section 8: liquidated damages (CIV 1671) as it bears on a fixed shortfall payment; the Commercial Code warranty sections for equipment sold with the work; whether a guarantee backed by a third party for a fee is insurance or a regulated service contract; shared-savings structures in which the contractor owns equipment and sells energy (for PV on a residence that is a PUC 2869 contract, section 4.7).

## 7. C-PACE package (commercial only)

`DocType`: `cpace_package`. Property assessed clean energy financing for a commercial property: the owner agrees to an assessment (or special tax) on the parcel, a public agency levies it, and it is collected with the property tax bill. This product offers it only for commercial properties (`specs/SPEC.md` sections 1 and 6.6).

California has no single "C-PACE Act" and no state C-PACE administrator. There are two enabling routes, both voluntary and both run by a local public agency (often through a joint powers authority) with private administrators and capital providers. The statutes are thin on commercial transactions: most of the detailed rules (disclosure form, right to cancel, underwriting, confirmation call, licensing) were written for residential PACE and are limited to it. Section 7.5 lists those so the template does not import them.

### 7.1 Route A: contractual assessments under the Improvement Act of 1911 (Streets and Highways Code, Division 7, Part 3, Chapter 29)

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-PACE-01 | **What may be financed:** distributed generation renewable energy sources, energy efficiency improvements, and water efficiency improvements, in each case "permanently fixed to" real property; property may be "residential, commercial, industrial, agricultural, or other real property". "Efficiency improvements" are "permanent improvements fixed to" such property. | SHC 5898.12(b), (c); 5898.20(a)(2), (c)(1) | NO | Tier M. Maps to the office measure list: lighting and controls, rooftop units, economizer, cool roof, rooftop PV qualify in kind if permanently fixed. Plug-load devices and furniture or desk placement do not look like fixed improvements: exclude them from the financed amount. |
| CA-PACE-02 | **Not financeable:** appliances that are not permanently fixed to real property; facilities in connection with the initial construction of a residential building (unless undertaken by the intended owner or occupant). | SHC 5898.12(e), (f) | NO | Tier M. |
| CA-PACE-03 | **Voluntary.** Assessments may be levied "only with the free and willing consent of the owner of each lot or parcel" at the time the assessment is levied. | SHC 5898.12(g) | NO | Tier M. Package needs a signed owner consent; every owner of record should sign (the residential sections say so expressly, SHC 5898.16(d); for commercial property treat it as the safe reading). |
| CA-PACE-04 | **Who may run a programme** for renewable energy or energy efficiency improvements: "a county, city, city and county", or a municipal utility district, irrigation district or public utility district that owns and operates an electric distribution system. | SHC 5898.20(c)(3)(B) | NO | Tier M. A joint powers authority acts for its member cities and counties; the joint powers statute was not opened (section 8). |
| CA-PACE-05 | **Programme must already exist for the parcel.** The agency designates an area by resolution of intention (kinds of improvements, boundaries, financing arrangements including the criteria for judging an owner's creditworthiness, hearing), publishes hearing notice at least 20 days ahead, gives water and electric providers 60 days' written notice, and adopts a report containing a map, **a draft contract** between owner and agency, eligible improvements, the official authorised to sign, a maximum aggregate dollar amount, a priority method, and a financing plan (interest rate and term or the method to set them, reserve fund, split of costs, county auditor fees). | SHC 5898.20(b); 5898.22; 5898.24(a), (b) | NO | Tier M. These are the agency's steps, not package documents. They matter in two ways: the parcel must lie inside a designated area, and **the assessment contract is the agency's form** (the "draft contract" of 5898.22(b)), not something this product drafts. |
| CA-PACE-06 | **Owner may contract directly.** With the written consent of an authorised public agency official, the programme's financing arrangements may authorise the owner to purchase the equipment and materials directly and to contract directly for installation. | SHC 5898.21 | NO | Tier M. So the installation contract is the commercial retrofit contract of section 3 (and section 4 for PV), signed by the owner, with payment tied to programme disbursement. |
| CA-PACE-07 | **Tax-burden cap for commercial property.** The agency may not let an owner participate if, as a result, the total amount of annual property taxes and assessments on the property would exceed **5 percent** of the property's market value, "as determined at the time of approval of the owner's contractual assessment". This subdivision applies to the property types **not** covered by SHC 5898.16 and 5898.17, that is, to everything other than residential property of four or fewer units. | SHC 5898.15(a), (c) | NO | Tier M. **The only numeric eligibility limit found in the statute for commercial property.** Template check: (annual property taxes + existing assessments + new annual assessment) / market value at most 0.05, with the inputs shown and their source. |
| CA-PACE-08 | **Recorded notice 1.** The agency's clerk records with the county recorder a notice of each contractual assessment stating its existence and amount. | SHC 5898.32 | NO | Tier M. Agency document. |
| CA-PACE-09 | **Recorded notice 2.** Concurrently with the instrument creating the assessment, the agency records a separate document titled **"Payment of Contractual Assessment Required"** in at least **14-point boldface** type, containing: (A) names of all current owners, legal description and assessor's parcel number; (B) the annual amount of the assessment; (C) its expiration date or circumstances, or that it is perpetual; (D) the purpose for which the funds will be used; (E) the entity to which funds are paid and its contact information; (F) the signature of the agency's authorised representative. It may be combined with notice 1. | SHC 5898.24(d), (f) | YES (title only) | Tier M. Agency document. The package should give the owner the data items (A) to (E) so the agency's notice can be checked against them; legal description and parcel number are blanks, never invented. |
| CA-PACE-10 | **Lien and collection.** Assessments, with interest and penalties, "shall constitute a lien against the lots and parcels of land on which they are made, until they are paid". They are collected "in the same manner and at the same time as the general taxes" on real property unless another procedure is authorised. Lien priority and the penalties and remedies for delinquency are those of Division 10 (Improvement Bond Act of 1915) and Government Code Title 5, Division 2, Part 1, Chapter 4, Articles 13 and 13.5. | SHC 5898.30 | NO | Tier M. Supports the two plain statements `specs/SPEC.md` requires: the assessment is a lien on the property until paid, and it is billed with property taxes. **The statement that the lien outranks an existing mortgage rests on the incorporated provisions, which were not opened** (section 8). |
| CA-PACE-11 | **Bond terms special to non-residential property** (and residential property of four or more units): the interest rate may follow an index instead of being fixed at issue; the premium on redemption after an owner's prepayment is set by agreement of the agency, the owner and the initial bond purchaser; with the owner's prior written approval the agency may refund the bonds on terms outside the usual tests, but the new maturity may not extend "beyond the useful life of the financed improvements". | SHC 5898.28(a), (d), (f) | NO | Tier M. Consequences for the package: prepayment terms are negotiated per deal, so the summary must show the prepayment premium as a blank to be filled from the term sheet; and term at most useful life has statutory support only in this refunding rule (for residential it is express in FIN 22684(j)). For a new commercial assessment, "term not longer than useful life" is a programme rule. |

### 7.2 Route B: Mello-Roos community facilities district (Government Code 53311 et seq., as amended by SB 555 of 2011)

| ID | Requirement | Citation | Verbatim | Notes |
|---|---|---|---|---|
| CA-PACE-12 | A community facilities district may finance and refinance the acquisition, installation and improvement of energy efficiency, water conservation, wildfire safety and renewable energy improvements that are affixed (as in CIV 660) to or on real property and in buildings, publicly or privately owned. On privately owned property only "with the prior written consent of the owner or owners of the building or real property". Not for initial construction of a residential building unless undertaken by the intended owner or occupant. | GOV 53313.5(l) | NO | Tier M. This version of 53313.5 is in effect only until 2029-01-01 (53313.5(n)); a later version exists and was not read. |
| CA-PACE-13 | **Opt-in district.** A district may be formed with territory to be annexed later; each parcel comes in only with the **unanimous approval of its owner or owners**, which replaces the election and sets the maximum special tax rate and any prepayment terms for that parcel. No notice of special tax lien may be recorded against a parcel until its owners unanimously approve annexation; it is then recorded under GOV 53328.3. Such a district may finance only the facilities in 53313.5(i) (seismic) or (l). | GOV 53328.1(a), (d) | NO | Tier M. On this route the owner's document is a unanimous approval and annexation instrument, again the agency's form; the charge is a "special tax", not an "assessment". The template field `{{cpace_route}}` takes `contractual_assessment` or `special_tax` and switches the vocabulary. |
| CA-PACE-14 | Before annexing any parcel the agency must comply with SHC 5898.16 and 5898.17, and may not annex a residential property of four or fewer units unless the listed conditions are met. | GOV 53328.1(e) | NO | Tier M. Those two sections are themselves limited to residential property of four or fewer units (section 7.5), so this adds nothing for a commercial parcel. |

### 7.3 Who administers programmes available in Los Angeles County and the City of Los Angeles

What official pages opened on 2026-11-14 establish:

| ID | Fact | Source | Notes |
|---|---|---|---|
| CA-PACE-15 | **Los Angeles County ended its own residential PACE programme.** Its contracts with Renovate America and Renew Financial expired on 2020-04-03 and it stopped approving new assessments through PACE Funding Group on 2020-05-13. It continues to service existing assessments. The County's Internal Services Department page (last updated 2026-02-26) says the County "no longer administers a residential PACE program directly". | `https://pace.lacounty.gov/`; `https://isd.lacounty.gov/how-do-i-find-information-about-the-pace-program/` | Tier A. **Neither page mentions a commercial programme at all.** Whether the County's commercial PACE programme of the 2010s still accepts applications is not established (section 8). |
| CA-PACE-16 | The State Treasurer's list of PACE programmes enrolled in the PACE Loss Reserve shows the Los Angeles County programmes as inactive (LA HERO and CaliforniaFIRST in Los Angeles County, inactive April 2020; PACEFunding (LA County), inactive 2021-01-09) and three active programmes of the California Statewide Communities Development Authority (CSCDA) with statewide territory: CaliforniaFIRST (Renew Financial), Home Run Financing, FortiFi. | `https://www.treasurer.ca.gov/caeatfa/pace/participants.asp` | Tier A. This list concerns the loss reserve programme and does not say which programmes take commercial property. It confirms only that CSCDA is the public agency behind the statewide programmes. |
| CA-PACE-17 | **State licensing reaches some commercial administrators.** Since 2019-01-01 the Department of Financial Protection and Innovation licenses PACE "program administrators" under the California Financing Law (AB 1284, Stats. 2017 ch. 475). A program administrator is a person administering a PACE programme on behalf of, and with the written consent of, a public agency. **Excluded** is a person who meets both conditions: it does not administer a programme financing improvements on residential property with four or fewer units, **and** it does not administer a programme financing improvements on real property with a market value of less than **$1,000,000**. | FIN 22018(a), (b); DFPI "PACE Program Administrators" page | FIN 22018 Tier M; DFPI page Tier A. So an administrator that finances only commercial properties worth $1,000,000 or more is outside the licence; one that finances a commercial property worth less is a program administrator. Template: if `{{property_market_value}}` is under 1,000,000, add a check that the administrator holds the licence. DFPI lists three licensees: Renew Financial Group LLC (60DBO-90653, CaliforniaFirst), PACE Funding Group, LLC (60DBO-91769), Ygrene Energy Fund California LLC (60DBO-91942). |

What could not be established from an official page, and is therefore in section 8 and must stay a blank in the draft: which programme, public agency and administrator currently accept commercial applications for a parcel in the City of Los Angeles or in unincorporated Los Angeles County; whether the City or the County is an opted-in member of the CSCDA Open PACE programme for commercial property; the current list of CSCDA-approved commercial administrators. The draft therefore carries `{{cpace_public_agency}}`, `{{cpace_program_name}}` and `{{cpace_administrator}}` as unfilled placeholders and its first checklist item is "confirm the parcel lies in the territory of an active programme that accepts commercial property".

### 7.4 Eligibility conditions for a commercial parcel

Statutory (Route A):

1. The improvement is a distributed generation renewable energy source or an energy or water efficiency improvement, permanently fixed to the property (CA-PACE-01, -02).
2. The parcel is inside an area designated by a public agency with authority to run a programme (CA-PACE-04, -05).
3. Every owner gives free and willing consent in the agency's contract (CA-PACE-03).
4. Total annual property taxes and assessments, with the new assessment, do not exceed 5% of market value at approval (CA-PACE-07).

Statutory (Route B): improvements within GOV 53313.5(l), prior written consent and unanimous approval of the owners (CA-PACE-12, -13).

Programme-level conditions, not found in the statutes read and so to be taken from the chosen programme's handbook (all unverified, section 8): savings-to-investment ratio or audit requirement; maximum financed amount as a share of property value; term limited to useful life; minimum project size; property tax and mortgage payment history; title and lien search; **existing mortgage holder's consent or acknowledgment**; contractor licensing and completion certification; fees.

### 7.5 Rules that apply only to residential PACE (do not put these in the commercial package)

| Rule | Limited to | Citation |
|---|---|---|
| Right to cancel the assessment contract within three business days (five for an owner aged 65 or older), with the statutory "Right to Cancel" notice; 5% cap restated with further underwriting conditions | "a residential property with four or fewer units" | SHC 5898.16(a)-(c) (in effect until 2029-01-01; a later version follows) |
| Financing Estimate and Disclosure form, printed paper copy in at least 12-point type, delivered before the owner consummates the assessment; limits on statements about increased property value | "a residential property with four or fewer units" | SHC 5898.17(a)-(c) (in effect until 2029-01-01) |
| Recorded oral confirmation of key terms before signing; recording kept five years | assessment contracts handled by a "program administrator"; the section sits in Chapter 29.1 ("Clean Energy Assessment Contracts"), whose definitions were not opened | SHC 5913 (in effect until 2029-01-01) |
| Underwriting: no involuntary liens over $1,000, no bankruptcy in four years (with exception), mortgage current, financing under 15% of value up to $700,000 and under 10% above, total PACE plus mortgage debt at most 97% of market value, term at most useful life, no prepayment penalty | written for an assessment contract that finances "a home improvement contract" | FIN 22684 |
| PACE disclosure standing in for the solar disclosure on the financing contract | solar on a residential building | BPC 7169(e) |

All Tier M except BPC 7169 (Tier L). One caution: SHC 5913 and FIN 22684 are framed around "program administrators", and that term can include an administrator of commercial financing on property worth less than $1,000,000 (CA-PACE-17). Whether those sections then attach to such a commercial deal is not answered by the text read (section 8).

### 7.6 Lender consent

No provision in SHC 5898.12 to 5898.32 or GOV 53328.1, as read, requires the consent of, or notice to, an existing mortgage holder for an assessment on commercial property. Lender consent is (a) a condition that programmes and capital providers impose, and (b) a practical necessity because most commercial loan documents treat a new lien collected with taxes as a default. `specs/SPEC.md` section 6.6 says the consent "is normally required": correct as practice, but the draft must not cite a statute for it. The package includes a request-for-consent letter and a consent and acknowledgment form with blanks for the lender, loan number and recording data, marked "programme requirement: confirm the form with the administrator".

### 7.7 Disclosures the commercial package must make

Required by statute for commercial property: only the two recorded agency notices (CA-PACE-08, -09). No statutory borrower disclosure form exists for commercial property.

Statements the draft should make because they are true under the provisions read and `specs/SPEC.md` asks for them (wording free, each tied to an ID):

- The assessment and any interest and penalties are a lien on the parcel until paid (CA-PACE-10).
- It is collected with, and in the same manner as, general property taxes; delinquency carries the remedies that law provides for such assessments (CA-PACE-10).
- A notice titled "Payment of Contractual Assessment Required" will be recorded against the property showing the annual amount and the expiry (CA-PACE-09).
- The owner contracts directly with the installer; the public agency and the administrator are not the installer (CA-PACE-06).
- Savings are estimates from the audit, with their low, expected and high values; they are not guaranteed unless a guarantee addendum is signed (CA-ESG-07).
- Existing mortgage holder consent: programme requirement, status `{{lender_consent_status}}` (section 7.6).

### 7.8 Documents in a C-PACE financing

| # | Document | Who prepares it | Basis | In our draft package? |
|---|---|---|---|---|
| 1 | Programme application and eligibility checklist | owner, on the administrator's form | programme | summary sheet with the section 7.4 checks filled from the audit |
| 2 | Energy audit or technical review: measures, cost, savings, useful life, savings-to-investment ratio | auditor | programme | yes: the audit report and plan |
| 3 | Tax-burden computation (5% test) | owner or administrator | SHC 5898.15(a) | yes: computed, with blanks for tax bill figures not known |
| 4 | Owner consent; evidence of authority of signers; all owners of record | owner | SHC 5898.12(g); GOV 53313.5(l) | yes: consent form with blanks |
| 5 | Assessment contract (Route A) or unanimous approval and annexation instrument (Route B) | **public agency**, on its approved form | SHC 5898.22(b); GOV 53328.1(a) | no: placeholder page that names the document and lists the terms to check |
| 6 | Mortgage holder consent or acknowledgment | owner requests; lender signs | programme | yes: request letter and form, marked as programme requirement |
| 7 | Installation contract(s) and, at the end, completion certificate | owner and contractor | SHC 5898.21; section 3 | the section 3 or 4 draft; completion certificate is the programme's form |
| 8 | Notice of assessment and "Payment of Contractual Assessment Required" (Route A), or notice of special tax lien (Route B) | public agency records | SHC 5898.32, 5898.24(d); GOV 53328.1(a)(5) | no: data sheet for checking the recorded notice |
| 9 | Bond or other funding documents between agency and capital provider | agency and capital provider | SHC 5898.28 | no |
| 10 | Title report, property tax status, insurance | owner or administrator | programme | checklist line only |

## 8. Unverified, needs attorney check

Nothing in this section may be presented in a draft as a legal requirement. Each item says why it is here. The template agent should turn group B and C items into visible "confirm with attorney" lines where the draft touches them.

### 8.A Limits of this review

| # | Item | Why unverified |
|---|---|---|
| A1 | Full wording of every Tier M section (those first opened on 2026-11-14: BPC 7026, 7071.6, 7152, 7160, 7161; CIV 1791.2, 1793.1, 1795.1, 8170; FIN 22018, 22684; GOV 53313.5, 53328.1; LAB 2810; PUC 769.2, 2827; SHC 5898.12, 5898.15, 5898.16, 5898.17, 5898.20, 5898.21, 5898.22, 5898.24, 5898.28, 5898.30, 5898.32, 5913) | The official site blocks the tools available on 2026-11-14. Numbers and scope limits were confirmed on two mirrors, but through a tool that returns paraphrase and short quotations. An attorney or anyone with a browser should read each on leginfo once. Amendment chapter numbers for these sections were not captured; the log gives the text date the mirror shows. |
| A2 | Sections read on one mirror only: CIV 8190; CIV 1791(a); GOV 65850.52; GOV 4217.11; BPC 7028; FIN 22017 | The second mirror's page was not found or not fetched. Used only as background, each flagged where it appears. |
| A3 | Sections cited by other sections but never opened: CIV 1633.5; CIV 1671; CIV 1689.14 and 1689.15; CIV 1102.6b; CIV 8100 to 8102 (how notices are given); BPC 7159.10 to 7159.14 (service and repair contracts); BPC 7028.15; GOV 4216 et seq.; GOV 4217.10 and 4217.12 onward; GOV 53328.3; GOV 53930 to 53938 and SHC Division 10 (lien priority and remedies); SHC 5899 to 5899.4 and Chapter 29.1 definitions; FIN 22686, 22687; LAB 1776; LAB 218.7, 218.8 (direct contractor liability for subcontractors' unpaid wages); Public Resources Code 25782 and 26063; PUC 2827.1; Code of Civil Procedure 1298 | Not opened. |
| A4 | Lien waiver forms CIV 8134, 8136, 8138 | Only the opening and closing lines were captured on 2026-11-13 (CIV 8132 was read in full). The contract refers to the forms by section number and does not reproduce them, so the risk is low. |
| A5 | 16 CCR 832.10 and 832.46 | Read as published on CSLB's classification pages, not on the Office of Administrative Law site. Other classification regulations (C-2, C-17, C-20, C-36, C-39, C-43, B-2, D-65) were not read at all: names only. |
| A6 | CPUC Decisions 18-09-044, 20-02-011, 22-12-056 and Resolution E-5301 | Known only through the CPUC web pages that describe them. |
| A7 | Legislation after the official reading | The official text was read on 2026-11-13 and reflects law in force that day. Bills chaptered in 2026 that take effect on 2027-01-01 were not surveyed. One pending bill was noticed: SB 784 (2025-2026 session), which in an amended form would have lengthened the home improvement cancellation periods to five and seven days; search results on 2026-11-14 indicated it was held in committee and not enacted, but its status was not confirmed on the official site. Re-check before use in 2027. |

### 8.B Open legal questions on the residential and commercial contracts

| # | Question | Why it matters |
|---|---|---|
| B1 | Does federal E-SIGN (15 U.S.C. 7001 et seq.) allow electronic signature of the pieces California's UETA excludes (cancellation notice signed and dated by the owner, arbitration initials, BPC 7159.1 warning, CIV 1689.13 waiver)? | CA-ESIG-02. Until answered, residential drafts need a wet-signature path for those pieces. Federal law was outside the sources for this file. |
| B2 | Can CIV 1689.5 to 1689.7 reach a commercial owner who signs a services contract away from the contractor's premises? | Section 3.1. The "services" definition is not limited to residential work and no business-buyer exclusion was found. |
| B3 | Wording conflict in the Three-Day Right to Cancel: BPC 7159(e)(6) "as you received them, goods delivered" versus CIV 1689.7(a)(4)(A) "as you received it, any goods delivered". | Section 2.5 uses the BPC 7159 text. |
| B4 | Seven-day disaster cancellation: the period runs from receipt of a signed copy (BPC 7159(e)(7) notice) or from signing (CIV 1689.6(c))? And when is a contract void under CIV 1689.14 or subject to 1689.15? | CA-HIC-36. Relevant after the January 2025 Los Angeles County fires; which declarations cover which properties was not checked. |
| B5 | Pay-if-paid and pay-when-paid clauses; limitation of liability; liquidated damages (CIV 1671); waiver of consequential damages. | Section 3.3. Not opened. |
| B6 | Does Code of Civil Procedure 1298 (arbitration notice in real property contracts) apply to a commercial construction contract? | Not opened. If it does, the commercial arbitration clause has format rules. |
| B7 | Is a landlord's retrofit of rental housing a "home improvement" in every respect of section 2 (it is "residential property" under BPC 7151(a)), and how do the notices addressed to "your home" read for a non-occupant owner? | Home flow users include landlords. |
| B8 | Which licence classification may perform each non-solar measure (attic and wall insulation, air sealing, windows, cool roof, heat pump, heat pump water heater, lighting and controls, rooftop units, economizer)? | CA-BID-03. Class names were verified, scope texts were not. A B or B-2 contractor's ability to take single-trade jobs is limited by BPC 7057(b) (B-2 rules not opened). |
| B9 | Building permit, Title 24 Part 6 compliance forms and field verification for alterations, asbestos and lead rules for older buildings, Cal/OSHA duties, City of Los Angeles business tax registration. | Not opened. The contracts allocate "all permits and code compliance documents" in general words only. |
| B10 | Direct contractor liability for subcontractors' unpaid wages (LAB 218.7, 218.8) and its effect on the commercial flow-down clauses. | Not opened. |

### 8.C Open questions on solar

| # | Question | Why it matters |
|---|---|---|
| C1 | Is a ten-year warranty on equipment and installation a condition of the CPUC net metering or Net Billing Tariff, and does LADWP impose anything similar? | CA-SOL-28. Widely repeated; not found on any official page opened; PUC 2827 contains no warranty term. Do not state a statutory minimum warranty. |
| C2 | Front page: where do the BPC 7159(c)(3)(B) first-page items go when the CSLB disclosure document must be the front or cover page? | Section 4.2. |
| C3 | No CSLB disclosure document exists for the seven-day right to cancel. | Section 4.8. |
| C4 | CPUC Guide: which pages are initialed, the conditions for electronic signature under Decision 20-02-011, and whether any part applies to non-residential customers. | CA-SOL-11 to -13. The CPUC page does not say; a search summary said electronic signatures are allowed with an audit-trail document, not confirmed. |
| C5 | That the PUC 2827(b) exclusion (publicly owned utility with more than 750,000 customers that also conveys water) means LADWP. | CA-SOL-25. Inference from the description; the statute names no utility. |
| C6 | LADWP's interconnection terms. A search summary of LADWP's Net Energy Metering Guidelines (not opened directly) gave: systems up to 1 MW; an interconnection agreement needed above 10 kW AC, short form from 10 to 30 kW and long form above 30 kW; tenant may sign with the owner in some cases; no operation until inspection, signed agreement and meter installation. | Section 4.5. Take the terms from LADWP's current documents when drafting; treat these figures as leads only. |
| C7 | Does PUC 769.2 (prevailing wage) apply to a system interconnected to LADWP? | CA-SOL-27. The text ties the duty to PUC 2827.1 tariffs of large electrical corporations, which points to no. |
| C8 | Battery storage scope for C-46 licensees. | Section 4.4. Regulation approved 2024-06-05, effective date stayed by court order, new rulemaking proposed in 2026. |
| C9 | Are PV modules, inverters, heat pumps and water heaters that become fixtures "consumer goods" under CIV 1791(a)? | CA-SOL-31, CA-ESG-03 to -05. Decides whether the consumer warranty chapter governs the equipment warranties in a home job. |
| C10 | CSLB "Solar Energy System Supporting Information" document and the Spanish disclosure documents. | Linked from the CSLB Solar Smart page; not opened. |
| C11 | Other cities in Los Angeles County with their own electric utilities (for example Burbank, Glendale, Pasadena). | Their interconnection rules were not looked at; `{{electric_utility}}` must not be assumed to be LADWP or SCE. |

### 8.D Open questions on the guarantee addendum

| # | Question | Why it matters |
|---|---|---|
| D1 | Is a savings holdback "retention" under CIV 8810 to 8822? | CA-ESG-10. |
| D2 | Does a savings-based payment after completion fit BPC 7159.5(a)(5)? | CA-ESG-02 reads it as allowed because it is not payment ahead of work; not tested against any authority. |
| D3 | Is a savings guarantee an "express warranty" on consumer goods, a service contract, or (if a third party backs it for a fee) insurance? | CA-ESG-03; Insurance Code and the service contract statutes were not opened. |
| D4 | Federal warranty disclosure rules (Magnuson-Moss Act and Federal Trade Commission rules) that CIV 1793.1 incorporates. | CA-ESG-04. Not opened. |
| D5 | Enforceability of a fixed shortfall payment as liquidated damages (CIV 1671). | Section 6.3. |

### 8.E Open questions on C-PACE

| # | Question | Why it matters |
|---|---|---|
| E1 | Which public agency, programme and administrator currently accept commercial PACE applications for a parcel in the City of Los Angeles, and in unincorporated Los Angeles County? | Section 7.3. Official county pages are silent on commercial PACE. Leads from search summaries of CSCDA board packets, **not opened directly**: CSCDA's Open PACE programme approves several third-party commercial administrators (names seen: AXCS PACE, proposed February 2025; Petros PACE Finance; Green PACE Capital; LordCap PACE; REVL; Bayview Asset Management; Citizens Business Bank), with entry conditions said to include $25 million of committed capital and a $2 million minimum transaction. A 2016 secondary source said 85 of 88 cities in the county had opted into the County's programme. None of this is confirmed or current. |
| E2 | Lien priority over an existing mortgage, and the remedies on delinquency. | CA-PACE-10. Set by provisions not opened (A3). |
| E3 | Lender consent: form and whether any programme available in Los Angeles waives it. | Section 7.6. Programme rule. |
| E4 | Programme eligibility rules: savings-to-investment ratio, loan-to-value limits, term, minimum size, fees. | Section 7.4. `specs/SPEC.md` ties C-PACE to the savings-to-investment ratio; that is not a California statutory condition. |
| E5 | Do SHC 5913 and FIN 22684 (and the rest of the program-administrator rules) attach to commercial financing on a property worth less than $1,000,000? | Section 7.5. |
| E6 | Authority of a joint powers authority to act as the "public agency" for a member city (Government Code 6500 et seq.). | CA-PACE-04. Not opened. |
| E7 | The versions of SHC 5898.16, 5898.17, 5913 and GOV 53313.5 that take effect on 2029-01-01. | Not read. |

## 9. Differences from the first-pass notes in `specs/HANDOFF.md` section 7

Wrong or misleading in the first-pass notes:

| # | First-pass note | What the text says |
|---|---|---|
| 1 | BPC 7191: the arbitration clause must "sit immediately before the signature line with the statutory warning". | The statutory notice goes immediately **after the arbitration provision** and immediately **before the line or space where the parties indicate assent or non-assent to that provision** (their initials). It is not tied to the contract signature line. The clause itself has type rules: 10-point roman bold, or red 8-point roman bold, or capitals if typed (CA-ARB-01, -02). |
| 2 | Civil Code 1689.5 to 1689.7 and 1689.13 "(amended effective 2026-01-01)". | Only 1689.6 and 1689.7 were amended effective 2026-01-01 (Stats. 2025 ch. 348, AB 1327). Sections 1689.5 and 1689.13 were last amended effective 2021-01-01 (Stats. 2020 ch. 158, AB 2471). |
| 3 | Emergency waiver "only by a separate dated statement in the buyer's own words". | CIV 1689.13 requires a separate statement that is dated and signed, describes the situation requiring immediate remedy, and expressly acknowledges and waives the right to cancel. It also requires that the buyer initiated the contract and that the repairs are emergency or immediately necessary. "In the buyer's own words" is not in the section. |
| 4 | BPC 7125 "could not be retrieved; unverified". | Retrieved (CA-LIC-04). Two versions: the one in force until 2028-01-01 keeps a no-employee exemption except for C-8, C-20, C-22, C-39 and D-49 licensees; the one operative 2028-01-01 keeps it only for joint ventures with no employees. |
| 5 | The brief describes the C-PACE package as "tied to the SIR". | No California statute read makes the savings-to-investment ratio a condition. The only statutory numeric test found for commercial property is the 5% tax-and-assessment cap (CA-PACE-07). A ratio test, if any, is a programme rule (8.E4). |

Correct but incomplete in the first-pass notes (now filled in):

| # | Topic | Added |
|---|---|---|
| 6 | BPC 7159 | The subcontractor Yes / No statement and disclaimer added by SB 517 from 2026-01-01 (CA-HIC-25); email address on the first page (CA-HIC-04); the insurance and workers' compensation notices (CA-HIC-29, -30); the bond-right notice near the signatures (CA-HIC-24); the exact headings; the Notice of Cancellation in duplicate; the $500 threshold. |
| 7 | BPC 7030 | The 12-point notice of 7030(b) is for home improvement contracts; the commercial contract uses the different 10-point notice of 7030(a) (CA-COM-03). |
| 8 | BPC 7159.2 | Besides the $5,000 security-interest bar, a rule on how a mortgage lender may pay the contractor on contracts over $5,000 (CA-FIN-02). |
| 9 | BPC 7048 | The exemption is also lost if the person advertises as a contractor or employs anyone on the work. |
| 10 | BPC 7169 | Applies only to systems of 1 kW to 5 MW on a residential building, not to a standard feature of new construction; language rule also keys on marketing material; the document is a specific CSLB form (text in section 4.8). |
| 11 | CIV 8811 | Applies to contracts entered on or after 2026-01-01; the exceptions are the bid-time bond notice and residential projects that are not mixed-use and do not exceed four stories. |
| 12 | CIV 8800; BPC 7108.5 | Both timing rules yield to a different written agreement. |
| 13 | CIV 2782 | Besides sole negligence and wilful misconduct, a private owner cannot shift liability for its own active negligence (2782(c)), with an exception for a homeowner improving his or her own single-family dwelling. |
| 14 | Cancellation statement | The 12-point "Three-Day Right to Cancel" is the home improvement form; a general home solicitation contract uses a different 10-point statement (CIV 1689.7(a)(1)), which our documents never need. |

## 10. Verification log

Dates: pass 1 for sections 1 to 3 was 2026-11-13; everything else, and pass 2 for all sections, was 2026-11-14.

Source codes used in the table (tiers are defined in section 0):

- **L** = `https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=<CODE>&sectionNum=<n>.` (official; the trailing full stop is part of the URL). Pass 1: read in full on 2026-11-13. Pass 2: statement re-compared with the saved text on 2026-11-14; quoted notices machine-compared.
- **PL** = `https://california.public.law/codes/ca_<code>_section_<n>` with `<code>` = `bus_and_prof_code`, `civ_code`, `fin_code`, `gov't_code`, `lab_code`, `pub_util_code`, `sts_and_high_code`. Each page showed "Verified: Nov. 11, 2026".
- **FL** = `https://codes.findlaw.com/ca/<code-name>/<abbr>-sect-<n, dots as hyphens>/` with code names `business-and-professions-code` (bpc), `civil-code` (civ), `financial-code` (fin), `government-code` (gov), `labor-code` (lab), `public-utilities-code` (puc), `streets-and-highways-code` (shc). Each page showed "Current as of January 01, 2026".
- "Last amended" for sections read only on PL and FL is the text date the mirror shows; the amending chapter was not captured (8.A1).

Results: **confirmed** = both passes agree with the file; **corrected** = the second pass changed the file (what changed is stated); **one source** = read once, kept out of the requirement tables or flagged in place; **agency** = Tier A page.

### 10.1 Cross-cutting rules and the residential and commercial contracts

| Requirement IDs | Citation | Source | Last amended (effective) | Result |
|---|---|---|---|---|
| CA-LIC-01 | BPC 7048 | L; PL | Stats. 2025 ch. 67, AB 1170 (2026-01-01) | confirmed ($1,000; no permit; lost on advertising or employing) |
| CA-LIC-02 | BPC 7031 | L | Stats. 2020 ch. 312, SB 1474 (2021-01-01) | confirmed |
| CA-LIC-03, CA-COM-02, CA-BID-01 | BPC 7030.5 | L | Stats. 1973 ch. 153 | confirmed |
| CA-LIC-04, CA-COM-01, CA-SOL-17, CA-BID-04 | BPC 7125, both versions | L (via the multiple-version selection page) | Stats. 2024 ch. 485 §§ 12, 13, SB 1455 (2025-01-01; later version operative 2028-01-01) | confirmed; class names added from `https://www.cslb.ca.gov/About_Us/Library/Licensing_Classifications/` (agency, 2026-11-14) |
| CA-LIC-05, CA-BID-05 | BPC 7071.6 | PL; FL | text dated 2022-01-01, operative 2023-01-01 | confirmed ($25,000) |
| CA-ESIG-01, CA-COM-10, CA-ESG-11 | CIV 1633.7 | L | added Stats. 1999 ch. 428 (2000-01-01) | confirmed |
| CA-ESIG-02 | CIV 1633.3 | L | Stats. 2023 ch. 374, AB 1697 (2024-01-01) | confirmed; note on CIV 1801 et seq. added on pass 2 |
| CA-IND-01, -02, -04, CA-COM-08, CA-BID-15 | CIV 2782 | L | Stats. 2011 ch. 707, SB 474 (2012-01-01) | confirmed (90-day and 30-day periods in (e)) |
| CA-IND-03 | CIV 2782.05 | L | added Stats. 2011 ch. 707 (2012-01-01) | confirmed (30-day election, 30-day payment) |
| CA-LIEN-01, -02, -03 | CIV 8200, 8204, 8202 | L | added Stats. 2010 ch. 697, SB 189 (operative 2012-07-01) | confirmed (20 days; 10 days in the owner notice) |
| CA-LIEN-04, -05, -06 | CIV 8180, 8182, 8412, 8414 | L | same | confirmed (60 / 30 days; 15 days; 90 / 60 / 30 days) |
| CA-LIEN-05a | CIV 8190 | FL only | not captured | one source; effect described correctly as loss of the shortened period |
| CA-LIEN-05b, CA-COM-11 | CIV 8170 | PL; FL | text dated 2011-01-01 | confirmed |
| CA-LIEN-07 | CIV 8124, 8126, 8132; 8134, 8136, 8138 | L (8134 to 8138 opening and closing lines only) | added Stats. 2010 ch. 697 (operative 2012-07-01) | confirmed for 8124, 8126, 8132; forms 8134 to 8138 not compared (8.A4) |
| CA-PAY-01, CA-COM-04 | CIV 8800 | L | same | confirmed (30 days; 150%; 2% per month) |
| CA-PAY-02, CA-COM-05, CA-BID-07, CA-BID-08, CA-ESG-10 | CIV 8811 | L; PL | added Stats. 2025 ch. 49, SB 61 (2026-01-01) | confirmed (5% and 5%; bid-time bond notice; residential not mixed-use, four stories) |
| CA-PAY-03 to -07, CA-COM-06 | CIV 8810, 8812, 8814, 8816, 8818, 8820, 8822 | L | added Stats. 2010 ch. 697 (operative 2012-07-01) | confirmed (45 days; 10 days; 10 + 10 days; 2% per month) |
| CA-PAY-08, CA-COM-07, CA-BID-14 | BPC 7108.5 | L | Stats. 2011 ch. 700, SB 293 (2012-01-01) | confirmed (7 days; 150%; 2% per month) |
| CA-HIC-00a, CA-SOL-01, CA-SOL-02 | BPC 7151 | L | Stats. 2021 ch. 249, SB 757 (2022-01-01) | confirmed |
| CA-HIC-00b | BPC 7151.2 | L | Stats. 1991 ch. 1160 | confirmed |
| CA-HIC-00c, -01 to -08, -11, -12, -14, -16 to -20, -22, -24 to -26, -29 to -37; CA-BID-10 to -12; CA-ESG-01 | BPC 7159 | L; PL (thresholds, type sizes, first-page items, subcontractor statement) | Stats. 2025 ch. 585 § 1.5, SB 517 (2026-01-01) | confirmed; every quoted heading, statement and notice in sections 2.2 to 2.5 matched the saved official text character for character apart from quote marks and line breaks |
| CA-HIC-00d | BPC 7150; CIV 1689.5(f) | L | Stats. 2020 ch. 158, AB 2471 (2021-01-01) | confirmed (65) |
| CA-HIC-09, -10, -13, -15, -23, -27, -28; CA-BID-09; CA-ESG-02 | BPC 7159.5 | L | Stats. 2023 ch. 403, SB 601 (2024-01-01) | confirmed ($1,000 or 10%; $100 to $5,000; one year; two years for blanket bond) |
| CA-HIC-21 | BPC 7159.6 | L | Stats. 2005 ch. 48 (operative 2006-01-01) | confirmed |
| CA-CXL-01, -03 | CIV 1689.6 | L; PL | Stats. 2025 ch. 348, AB 1327 (2026-01-01) | confirmed |
| CA-CXL-02 | CIV 1689.5 | L | Stats. 2020 ch. 158 (2021-01-01) | **corrected**: the gloss "not at the seller's place of business" replaced by the statutory definition of appropriate trade premises; Truth in Lending exclusion added |
| CA-CXL-04, CA-HIC-04, CA-HIC-34 | CIV 1689.7 | L; PL | Stats. 2025 ch. 348, AB 1327 (2026-01-01) | confirmed |
| CA-CXL-05 | CIV 1689.13 | L | Stats. 2020 ch. 158 (2021-01-01) | confirmed |
| CA-CXL-06 | CIV 1689.7(a)(4)(A); BPC 7159(e)(6)(C)(iv), (vi); CIV 1632(g)(2) | L; CIV 1632 on PL and FL | as above; CIV 1632 text dated 2025-01-01 | confirmed; row added 2026-11-14 |
| CA-HIC-36 | BPC 7159(e)(7); CIV 1689.6(c), 1689.7(e) | L | as above | confirmed; mismatch in the start of the seven-day period noted on pass 2 |
| CA-FIN-01, CA-ESG-09 | BPC 7163 | L | Stats. 1993 ch. 589 (1994-01-01) | confirmed (60-day pick-up) |
| CA-FIN-02 | BPC 7159.2 | L | Stats. 1999 ch. 512 (2000-01-01) | confirmed ($5,000) |
| CA-FIN-03 | BPC 7159.1 | L | Stats. 2010 ch. 697 (operative 2012-07-01) | confirmed (18-point; text matched) |
| CA-ARB-01, -02 | BPC 7191 | L | added Stats. 1994 ch. 1135 (1995-01-01) | confirmed (10-point or red 8-point; text matched) |
| CA-COM-03 | BPC 7030 | L | Stats. 2020 ch. 312, SB 1474 (2021-01-01) | confirmed (10-point; text matched) |
| CA-COM-09 | CIV 8180 to 8204, 8124 to 8138, 8412, 8414 | L | as above | confirmed |
| CA-COM-12, CA-BID-13 | LAB 2810 | PL; FL | text dated 2025-01-01 | confirmed (4 years; $250 / $1,000; home-residence exemption) |
| Section 3.1 (home solicitation and commercial buyers) | CIV 1689.5(b)-(d) | L | Stats. 2020 ch. 158 (2021-01-01) | **corrected**: flat statement of non-application replaced by the text and an attorney question (8.B2) |

### 10.2 Solar

| Requirement IDs | Citation | Source | Last amended (effective) | Result |
|---|---|---|---|---|
| CA-SOL-03 to -10, -29; CA-BID-17; CA-ESG-08 | BPC 7169 | L; FL (summary) | Stats. 2021 ch. 188, SB 826 (2022-01-01) | confirmed (16-point bold; front or cover page; 1 kW to 5 MW) |
| Section 4.8 text | CSLB disclosure documents | agency: `https://www.cslb.ca.gov/Resources/Contractors/SolarDisclosureDoc.pdf`, `.../RightToCancel.Dec2020.Eng.pdf` (PDFs read directly, 2026-11-14) | form 13L-6 (05/2018); five-day file dated December 2020 | text copied from the PDFs; listing of the four versions confirmed on the CSLB Solar Smart page on 2026-11-13 and 2026-11-14 |
| CA-SOL-11, -12, -13 | CPUC Decisions 18-09-044, 20-02-011 (not opened) | agency: `https://www.cpuc.ca.gov/industries-and-topics/electrical-energy/demand-side-management/customer-generation/california-solar-consumer-protection-guide` (2026-11-14; same facts in a CPUC-site search summary the same day) | Version 4 published 2025; required for contracts signed from 2026-12-15 | agency; decisions themselves unverified (8.A6, 8.C4) |
| CA-SOL-14, -15 | 16 CCR 832.46, 832.10 | agency: `https://www.cslb.ca.gov/About_Us/Library/Licensing_Classifications/Licensing_Classifications_Detail.aspx?Class=C46` and `?Class=C10` (2026-11-14); C-46 also on the Solar Smart page (2026-11-13) | not captured; battery-storage amendment approved 2024-06-05 is stayed | agency; CCR not read at source (8.A5) |
| CA-SOL-16, CA-BID-03 | CSLB Solar Smart page; BPC 7057 | agency: `https://www.cslb.ca.gov/Consumers/Solar_Smart/` (2026-11-13, 2026-11-14); L for 7057 | BPC 7057: Stats. 2013 ch. 377, AB 433 (2014-01-01) | confirmed |
| CA-SOL-18, CA-BID-06 | BPC 7152 | PL; FL | text dated 2026-01-01 | confirmed |
| CA-SOL-19, -20, -22, -23 | GOV 65850.5 | L | Stats. 2019 ch. 494, AB 754 (2020-01-01) | confirmed (10 kW AC / 30 kW thermal; one inspection) |
| CA-SOL-21 | GOV 65850.52 | FL only | not captured | one source (38.4 kW AC; 2023-09-30) |
| CA-SOL-23, -24 | CIV 714 | L | Stats. 2014 ch. 521, AB 2188 (2015-01-01) | confirmed ($1,000; 10%; 45 days) |
| CA-SOL-25 | PUC 2827(b) | PL; FL | text dated 2023-01-01 | confirmed (1 MW; exclusion for publicly owned utility over 750,000 customers that conveys water); that this is LADWP is inference (8.C5) |
| CA-SOL-26 | CPUC Decision 22-12-056 (not opened) | agency: `https://www.cpuc.ca.gov/industries-and-topics/electrical-energy/demand-side-management/customer-generation/nem-revisit/net-billing-tariff` (2026-11-14) | decision adopted 2022-12-15 | agency |
| CA-SOL-27, CA-BID-16 | PUC 769.2 | PL; FL | text dated 2026-01-01 | confirmed (after 2023-12-31; 15 kW; single-family; two stories; July 1 and December 31) |
| CA-SOL-28 | BPC 7159, 7169; PUC 2827 | L; PL; FL | as above | negative finding: no warranty or production-guarantee term in the sections read (8.C1) |
| CA-SOL-30, CA-BID-18, CA-ESG-07 | BPC 7161, 7160 | PL; FL | 7161 operative 2021-07-01; 7160 text dated 1972-01-01 | confirmed ($500) |
| CA-SOL-31, CA-ESG-03, -04, -06 | CIV 1791.2, 1793.1 | PL; FL | text dated 1978-01-01; 2003-01-01 | confirmed (10-point bold in (a)(2)); CIV 1791(a) on PL only |
| Section 4.7 | PUC 2869 | L | added Stats. 2008 ch. 535 (2009-01-01) | confirmed (30 days; 14-point title; 10 days) |
| Battery storage note | 16 CCR 810, 832.10, 832.46 | agency: `https://www.cslb.ca.gov/About_Us/Library/Laws/` (2026-11-14) | approved 2024-06-05; effective date stayed | unverified outcome (8.C8) |

### 10.3 Bid package, guarantee addendum, C-PACE

| Requirement IDs | Citation | Source | Last amended (effective) | Result |
|---|---|---|---|---|
| CA-BID-02 | BPC 7026; BPC 7028 | 7026: PL; FL. 7028: PL only | text dated 2002-01-01; 2015-01-01 | 7026 confirmed; 7028 one source |
| CA-ESG-05 | CIV 1795.1 | PL; FL | text dated 1983-01-01 | confirmed |
| CA-ESG-09 | CIV 8820, 2782.05(d), 8126; BPC 7163(g) | L | as above | confirmed |
| Section 6.1 | GOV 4217.11 | FL only | not captured | one source |
| CA-PACE-01, -02, -03 | SHC 5898.12 | PL; FL | text dated 2015-01-01 | confirmed |
| CA-PACE-04, -05 | SHC 5898.20, 5898.22, 5898.24(a), (b) | PL; FL | text dated 2010-01-01; 2010-01-01; 2019-01-01 | confirmed (20 days; 60 days) |
| CA-PACE-06 | SHC 5898.21 | PL; FL | text dated 2010-01-01 | confirmed |
| CA-PACE-07 | SHC 5898.15 | PL; FL | text dated 2017-01-01 | confirmed (5 percent; applies outside 5898.16 and 5898.17) |
| CA-PACE-08 | SHC 5898.32 | PL; FL | text dated 1987-01-01 | confirmed |
| CA-PACE-09 | SHC 5898.24(d), (f) | PL; FL | text dated 2019-01-01 | confirmed (title; 14-point bold; items (A) to (F)) |
| CA-PACE-10 | SHC 5898.30 | PL; FL | text dated 2015-01-01 | confirmed; priority provisions not opened (8.E2) |
| CA-PACE-11 | SHC 5898.28 | PL; FL | text dated 2015-01-01 | confirmed |
| CA-PACE-12 | GOV 53313.5(l), (n) | PL; FL | text dated 2023-01-01; in effect until 2029-01-01 | confirmed |
| CA-PACE-13, -14 | GOV 53328.1 | PL; FL | text dated 2017-01-01 | confirmed |
| CA-PACE-15 | Los Angeles County pages | agency: `https://pace.lacounty.gov/`; `https://isd.lacounty.gov/how-do-i-find-information-about-the-pace-program/` (2026-11-14) | second page updated 2026-02-26 | agency; silent on commercial PACE (8.E1) |
| CA-PACE-16 | State Treasurer PACE programme list | agency: `https://www.treasurer.ca.gov/caeatfa/pace/participants.asp` (2026-11-14) | no date on page | agency |
| CA-PACE-17 | FIN 22018; DFPI page | PL; FL; agency: `https://dfpi.ca.gov/regulated-industries/property-assessed-clean-energy-pace-program-administrators/` (2026-11-14) | FIN 22018 text dated 2019-01-01 | confirmed (four units; $1,000,000; both conditions) |
| Section 7.5 table | SHC 5898.16, 5898.17, 5913; FIN 22684 | PL; FL | text dated 2021-01-01; in effect until 2029-01-01 (the three SHC sections) | confirmed (four or fewer units; 3 / 5 business days; 12-point; five years; $1,000, 15% / $700,000 / 10%, 97%) |

### 10.4 Count of requirements by document type

| Document type | IDs | Count | Of which rest on one source or an agency page only |
|---|---|---|---|
| Rules common to all documents | CA-LIC, CA-ESIG, CA-IND, CA-LIEN, CA-PAY | 28 | 1 (CA-LIEN-05a) |
| Retrofit contract, residential | CA-HIC, CA-CXL, CA-FIN, CA-ARB | 52 | 0 |
| Retrofit contract, commercial | CA-COM | 12 | 0 |
| Solar installation agreement | CA-SOL | 31 | 8 (CA-SOL-11 to -16 and -26 agency; CA-SOL-21 one mirror). CA-SOL-28 is a negative finding, not a requirement. |
| Bid package | CA-BID | 18 | 0 (BPC 7028 in CA-BID-02 is one mirror) |
| Energy savings guarantee addendum | CA-ESG | 11 | 0 |
| C-PACE package | CA-PACE | 17 | 2 (CA-PACE-15, -16 agency) |

A requirement shown as resting on an agency page is as reliable as the agency's own statement of its rule; it is separated here because the underlying decision or regulation was not read.

### 10.5 Verbatim anchors (section 2.5) and the six checks requested by the template owner, 2026-11-14

**Anchors.** Every fenced block in section 2.5 was generated by script from the official text saved on 2026-11-13 and then compared with it by a second script after removing whitespace and normalising quotation-mark glyphs: 77 paragraphs or lines checked, 0 mismatches.

| Anchor | Result |
|---|---|
| `stat_ca_entitled_to_copy`, `stat_ca_downpayment_cap`, `stat_ca_progress_payment_notice`, `stat_ca_change_order_note`, `stat_ca_subcontractor_disclaimer_if_yes`, `stat_ca_cgl_statement` (options A to D), `stat_ca_workers_comp_statement` (options A, B), `stat_ca_mechanics_lien_warning`, `stat_ca_cslb_notice`, `stat_ca_arbitration_heading`, `stat_ca_arbitration_notice`, `stat_ca_notice_attached_cgl`, `stat_ca_notice_attached_wc` | verbatim text present; matched against the official text (Tier L) |
| `stat_ca_right_to_cancel_notice` | three-day variant: verbatim, matched. Five-day variant: no separate statutory text exists; block is the three-day text with the substitutions BPC 7159(e)(6)(B)(ii) orders, checked by reversing them |
| `stat_ca_notice_of_cancellation_form` | three-day variant: verbatim, matched, with the statute's own blanks. Five-day: one-word statutory substitution. Seven-day form in (e)(7)(B)(vi) confirmed identical apart from the number |
| `stat_ca_commencement_statement`, `stat_ca_extra_work_notice`, `stat_ca_bond_notice` | **no verbatim text exists in the statute**; the statute prescribes content only. The anchor says so and reproduces the provision for reference. These three placeholders cannot be filled from statute and should be drafted text checked for content |
| extras: `stat_ca_headings`, `stat_ca_right_to_cancel_attached_checkbox`, `stat_ca_right_to_cancel_notice_seven_day`, `stat_ca_cslb_notice_commercial`, `stat_ca_home_security_warning` | verbatim, matched |

**Six checks.**

| # | Claim put to this file | Result | Text relied on |
|---|---|---|---|
| 1 | BPC 7159 was last amended by Stats. 2020 ch. 312, effective 2021, and not effective 2026-01-01 | **Not confirmed; this file keeps 2026-01-01.** | The official page read on 2026-11-13 ends: "(Amended by Stats. 2025, Ch. 585, Sec. 1.5. (SB 517) Effective January 1, 2026.)". public.law shows the section "updated Jan. 1, 2026". The FindLaw page (re-opened 2026-11-14) does print the credit "Stats.2020, c. 312 (S.B.1474), § 73.5, eff. Jan. 1, 2021", but its own text contains the provisions added in 2025: the "[__] Yes / [__] No" subcontractor statement in (c)(7) and "the name, address, and email address of the contractor" in (c)(3)(B)(ii). So the FindLaw credit line is out of date, not the text. A search summary also reported SB 517 chaptered on 2025-10-10 as chapter 585 (secondary, not opened). CIV 1689.6 and 1689.7 likewise show "Stats. 2025, Ch. 348 ... (AB 1327) Effective January 1, 2026" on the official page. |
| 2 | CIV 1689.7(a)(1) and (c) exclude BPC 7151.2 contracts; the notice title and the Notice of Cancellation form come from BPC 7159(e)(6); the 12-point statement and the language rule come from CIV 1689.7(a)(4) | Confirmed, with two refinements | (a)(1) and (c)(1) each open "Except for contracts written pursuant to Sections 7151.2 and 7159.10 of the Business and Professions Code". Refinement 1: the 12-point boldface rule and the language rule are in **both** CIV 1689.7(a)(4)(A) and BPC 7159(e)(6)(C)(i), (iv). Refinement 2: the title is also in the Civil Code: the statement quoted in CIV 1689.7(a)(4)(A) begins "Three-Day Right to Cancel" before "You, the buyer, have the right to cancel this contract within three business days." The template owner's note that the title is "not in §1689.7" does not match the official text as amended in 2025. |
| 3 | CIV 1689.13 waiver is a separate dated, signed statement; no "own words" or handwriting requirement | Confirmed | "(c) (1) The buyer gives the seller a separate statement that is dated and signed that describes the situation that requires immediate remedy, and expressly acknowledges and waives the right to cancel the sale within three, five, or seven business days, whichever applies." Conditions (a) and (b) (buyer-initiated; emergency or immediately necessary repairs) also apply. |
| 4 | CIV 8811 cap does not apply to non-mixed-use residential projects of four stories or fewer, under (b)(3) | Confirmed | "(3) Paragraph (1) does not apply to an owner, direct contractor, or subcontractor on a residential project if the project is not mixed-use and does not exceed four stories." |
| 5 | CIV 1632 translation duty excludes home improvement contracts under (g)(2) | Confirmed on both mirrors, with its condition | "does not include a home improvement contract as defined in Sections 7151.2 and 7159 of the Business and Professions Code" ... "if the home improvement contract or installation contract is otherwise a part of a contract described in subdivision (b)". Not read on the official site (Tier M). The separate language rule of CIV 1689.7(a)(4)(A) still applies (CA-CXL-06, added). |
| 6 | BPC 7125 is a licensing rule, operative until 2028-01-01 | Confirmed, with one refinement | It is a condition of holding a licence, owed to CSLB, not contract content. The present version says "This section shall remain in effect only until January 1, 2028"; a second version of the same section "shall become operative on January 1, 2028". The duty to have a certificate on file therefore continues after that date, with the no-employee exemption narrowed to joint ventures (CA-LIC-04). "Operative until 2028" is right only for the current wording. |

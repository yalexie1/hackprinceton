<!-- doc: retrofit_contract_residential / CA / template v0.1 -->
<!-- segments: residential -->
<!-- optional: contractor_license_classes, salesperson_block, finance_charge_block, downpayment_block, retention_block, additional_incorporated_documents, subcontractor_disclaimer_on_change_orders, stat_ca_subcontractor_disclaimer_if_yes, financing_contingency_block, pre_1978_lead_notice_block, arbitration_block, notice_attachment_statements -->
<!-- clause: CA-HIC-00a, CA-HIC-00b, CA-HIC-00c (routing in legal.md section 3: PV_ROOF excluded, price over $500, service-and-repair threshold) -->
<!-- source: specs/legal.md section 4. Our own wording, not copied from a published form. -->

> {{disclaimer}}

**First-page block** (B&P §7159(c)(3)(B); Civ. Code §1689.7(b); type no smaller than the body)

- Date the buyer signed: {{buyer_signature_date}}
- The Notice of Cancellation may be sent to the contractor at the following address or email address: {{contractor_name}}, {{contractor_business_address}}, {{contractor_cancellation_email}}
- Telephone number to call for help locating and filling out the Notice of Cancellation: {{contractor_phone}}

<!-- order is fixed: the "may be sent" sentence must immediately precede the name, address and email (B&P §7159(c)(3)(B)(ii), CA-HIC-04) -->
<!-- clause: CA-HIC-04 -->


<!-- fmt: 10pt bold heading -->
### Home Improvement
<!-- clause: CA-HIC-01, CA-HIC-07 -->

<!-- fmt: 12pt bold -->
{{stat_ca_entitled_to_copy}}
<!-- clause: CA-HIC-03, CA-HIC-08 -->

**4.1 Parties**
<!-- clause: CA-HIC-05, CA-LIC-03 -->

This contract is between {{owner_names}} ("Owner"), of {{owner_mailing_address}}, and {{contractor_name}} ("Contractor"), California contractor licence number {{contractor_license_number}}, licence classification(s) {{contractor_license_classes}}, business address {{contractor_business_address}}. {{salesperson_block}}

The work will be done at {{property_address}}, {{property_city}}, California ("the Property"). Owner states that Owner is the {{owner_role_text}} of the Property.

**4.2 What this contract is for**

Owner wants to reduce the energy use and energy cost of the home at the Property. Contractor will install the energy improvements listed in Schedule A. The improvements were selected with the help of an energy analysis of the Property (Schedule C). That analysis is for information only. It is not part of Contractor's promises unless a separate Energy Savings Guarantee is signed.

<!-- fmt: 10pt bold heading -->
### Contract Price
<!-- clause: CA-HIC-09, CA-HIC-10 -->

**4.3 Contract Price.** Owner will pay Contractor **${{contract_price_usd}}** for all labor, materials, equipment, permits and other costs of the work in Schedule A, including Contractor's profit. This amount does not include any finance charge.

{{finance_charge_block}}

<!-- fmt: 10pt bold heading -->
### Description of the Project and Description of the Significant Materials to be Used and Equipment to be Installed

<!-- clause: CA-HIC-11 -->
**4.4 Scope.** Contractor will perform the work described in **Schedule A**. Schedule A names, for each improvement, the work to be done, where in the home it will be done, the significant materials and equipment (make, model or the minimum performance rating where the model is not yet chosen), and the result that shows the work is complete. Materials and equipment of equal or better rated performance may be substituted only with Owner's written approval in a change order.

**4.5 Permits, code and inspection.** Contractor will obtain every permit the work requires, will do the work to meet the building and energy codes in force at the Property when the permit is issued, and will arrange the required inspections and any required third-party verification. The permit fees are included in the Contract Price. The work is not complete until each required final inspection has passed. *[Unverified: which energy-code verifications apply to each measure, see section 8.]*

<!-- fmt: 10pt bold heading -->
### Downpayment

{{downpayment_block}}
<!-- clause: CA-HIC-12, CA-HIC-13, CA-HIC-28 -->

<!-- fmt: 12pt bold -->
{{stat_ca_downpayment_cap}}

<!-- fmt: 10pt bold heading -->
### Schedule of Progress Payments

<!-- clause: CA-HIC-14 -->
**4.6 Progress payments.** After any down payment, Owner will pay Contractor in the stages listed below. Each payment is due only when the work or delivery it describes is done.

{{progress_payment_table}}

<!-- fmt: 12pt bold -->
{{stat_ca_progress_payment_notice}}
<!-- clause: CA-HIC-15 -->

<!-- clause: CA-HIC-22, CA-HIC-23 -->
**4.7 Payment terms and lien releases.** Contractor will send Owner a written request for each progress payment that names the stage completed. Owner will pay within {{payment_due_days}} days after receiving the request, unless Owner disputes in good faith that the stage is complete, in which case Owner will pay the undisputed part and tell Contractor in writing what is disputed and why. With each payment, Contractor will give Owner a full and unconditional release, in the form the law requires, of any mechanics lien claim for the work covered by that payment. Owner may withhold the next payment until that release is received.

{{retention_block}}
<!-- clause: CA-PAY-04 -->

<!-- fmt: 10pt bold heading -->
### Approximate Start Date

<!-- clause: CA-HIC-16 -->
**4.8 Start.** Work is substantially commenced on the first day Contractor or its subcontractors perform physical work at the Property under Schedule A. Obtaining permits, ordering materials and delivering materials to the Property are not, on their own, commencement of work. Approximate start date: **{{start_date}}**.

<!-- fmt: 10pt bold heading -->
### Approximate Completion Date

<!-- clause: CA-HIC-17 -->
**4.9 Completion.** Approximate completion date: **{{completion_date}}**. "Completion" means every item in Schedule A is installed and working, every required final inspection has passed, and Contractor has given Owner the documents listed in 4.12.

<!-- fmt: 10pt bold heading -->
### List of Documents to be Incorporated into the Contract

- Schedule A: Scope of work and significant materials and equipment
- Schedule B: Progress payment stages (repeated from 4.6)
- Schedule C: Energy analysis summary (for information, not binding)
- Notice of Cancellation, in duplicate
- Change Order form (blank; each completed change order repeats the subcontractor disclaimer if 4.11 is "Yes")
- {{additional_incorporated_documents}}

<!-- fmt: 10pt bold heading -->
### Note About Extra Work and Change Orders

{{stat_ca_change_order_note}}
<!-- clause: CA-HIC-02, CA-HIC-19, CA-HIC-20, CA-HIC-21, CA-HIC-31 -->

**4.10 Change orders.** A change to the work, the price or the dates is part of this contract only if it is written and signed by Owner and Contractor before the changed work starts. Each change order will state the scope of the change, the amount added to or subtracted from the Contract Price, and the effect on the progress payments and the completion date. {{subcontractor_disclaimer_on_change_orders}}

**Notice about extra work and change orders.** (A) You, the Owner, may not require Contractor to do extra work or change-order work unless you give written authorization before that work starts. (B) Extra work or a change order is not enforceable against you unless, before the work it covers starts, the change order states in writing (i) the scope of the work it covers, (ii) the amount added to or subtracted from the contract, and (iii) the effect it will have on the progress payments or the completion date. (C) If Contractor does not meet these requirements, Contractor may still be able to recover payment for work performed under legal or equitable remedies designed to prevent unjust enrichment.

<!-- clause: CA-HIC-25 -->
**4.11 Subcontractors.** Will Contractor use subcontractors on this project? {{subcontractor_yes_box}} Yes {{subcontractor_no_box}} No

{{stat_ca_subcontractor_disclaimer_if_yes}}

**4.12 Hand-over.** At completion Contractor will give Owner: copies of all permits and final inspection records; any third-party verification certificates; manufacturer warranties registered in Owner's name where the manufacturer allows it; operating and maintenance instructions for each piece of equipment; and the model and serial number of each major piece of equipment installed.

<!-- clause: CA-FIN-01 (block 4.13 when financing_contingent = yes) -->
{{financing_contingency_block}}

**4.14 Workmanship warranty.** Contractor warrants that the work will be done in a good and workmanlike manner, free of defects in workmanship, for {{workmanship_warranty_years}} year(s) from completion. If a defect in Contractor's workmanship appears in that period, Contractor will repair it at no charge within a reasonable time after Owner's written notice. Manufacturer warranties on materials and equipment are passed through to Owner and are in addition to this warranty. This warranty does not cover damage caused by misuse, by alterations made by others, or by events outside Contractor's control.

**4.15 Energy estimates are not a promise.** Schedule C shows estimated energy and cost savings, with low, expected and high values. They come from a computer model built from data about the Property and from stated assumptions. Actual savings depend on weather, energy prices, how the home is used and other factors. Contractor does not promise any level of savings under this contract.

**4.16 Rebates and incentives.** Schedule C lists rebates, credits and incentives that may apply, with their status at the date of the analysis. Contractor will {{incentive_paperwork_choice}}. The Contract Price does not depend on Owner receiving any incentive, unless this sentence is changed by a signed change order.

**4.17 Existing conditions and hazardous materials.** If Contractor finds a condition that could not reasonably have been seen before work began and that changes the work (for example hidden damage, or material that may contain asbestos or lead paint), Contractor will stop work on the affected area, tell Owner in writing, and not continue that part until a change order is signed. {{pre_1978_lead_notice_block}}

**4.18 Site, clean-up and access.** Owner will give Contractor reasonable access to the Property during {{work_hours}}. Contractor will protect floors, furnishings and landscaping in the work areas, keep the site reasonably clean each day, and remove its debris at completion.

<!-- clause: CA-IND-01 -->
**4.19 Insurance and responsibility for harm.** Contractor will keep the insurance described in the notices below for the length of the work. Each party is responsible for harm caused by its own negligence or wilful misconduct and that of the people it brings to the Property. Nothing in this contract makes either party responsible for harm caused by the other party's sole negligence or wilful misconduct.

<!-- clause: CA-FIN-02, CA-FIN-03 -->
**4.20 No security interest.** This contract does not give Contractor a mortgage, deed of trust or other security interest in the Property. This does not limit any mechanics lien right the law gives Contractor or its subcontractors and suppliers.

<!-- clause: CA-LIC-02 -->
**4.21 Licence.** Contractor states that it holds, and will hold for the whole of the work, an active California contractor licence in the classification(s) needed for the work.

**4.22 Disputes.** Owner and Contractor will first try to settle any dispute by talking to each other in good faith for at least 15 days after one gives the other written notice of the dispute. {{arbitration_block}}
<!-- clause: CA-ARB-01, CA-ARB-02 (block 4.22A when arbitration = yes) -->

**4.23 Whole agreement.** This contract, its schedules and signed change orders are the whole agreement between Owner and Contractor about the work. If a schedule conflicts with the body of this contract, the body controls. California law governs this contract.

<!-- fmt: notices section; each notice under its statutory heading -->
### Notices required by California law

{{notice_attachment_statements}}

<!-- fmt: 10pt bold heading -->
#### Commercial General Liability Insurance (CGL)
<!-- clause: CA-HIC-29 -->
{{stat_ca_cgl_statement}}

<!-- fmt: 10pt bold heading -->
#### Workers' Compensation Insurance
<!-- clause: CA-HIC-30 -->
{{stat_ca_workers_comp_statement}}

<!-- fmt: 10pt bold heading -->
#### Mechanics Lien Warning
<!-- clause: CA-HIC-32 -->
{{stat_ca_mechanics_lien_warning}}

<!-- fmt: 12pt -->
{{stat_ca_cslb_notice}}
<!-- clause: CA-HIC-33 -->

<!-- fmt: placed in close proximity to the signatures -->
**Performance and payment bond.** You, the {{owner_role_text}}, have the right to require Contractor to have a performance and payment bond.
<!-- clause: CA-HIC-24 -->

<!-- fmt: 12pt bold, immediately next to the buyer's signature, signed and dated by the buyer -->
{{stat_ca_right_to_cancel_notice}}
<!-- the statutory block begins with its own title line ("Three-Day Right to Cancel" / "Five-Day Right to Cancel"); do not add a second heading -->
<!-- clause: CA-HIC-00d, CA-HIC-34, CA-HIC-35, CA-CXL-01, CA-CXL-04, CA-CXL-06 -->
<!-- omit this notice and the form if the contract was negotiated at the contractor's place of business (B&P §7159(e)(6)(A)); field negotiated_at_contractor_premises -->
<!-- if attached rather than printed here, print stat_ca_right_to_cancel_attached_checkbox instead (CA-HIC-34) -->


<!-- clause: CA-ESIG-02 (cancel notice and arbitration need wet signatures) -->
**Signatures**

| | Owner | Contractor |
|---|---|---|
| Name | {{owner_names}} | {{contractor_signatory_name}}, {{contractor_signatory_title}} |
| Signature | | |
| Date | {{buyer_signature_date}} | {{contractor_signature_date}} |

Owner's signature and date for the {{cancel_title}} notice: ______________ Date: ______

---

**Notice of Cancellation** (attached in duplicate, easily detachable; B&P §7159(e)(6). Civ. Code §1689.7(c) does not apply: it excludes §7151.2 contracts)

{{stat_ca_notice_of_cancellation_form}}

---

**Schedule A: Scope of work.** One row per measure. Columns: improvement, location in the home, work to be done, significant materials and equipment, completion test.

{{schedule_a_rows}}

**Schedule B: Progress payment stages.** Same table as 4.6.

**Schedule C: Energy analysis summary (for information, not binding).** For each improvement: estimated installed cost range (low / expected / high) and its source, estimated annual savings range, simple payback range, incentives with status, and the main assumptions. Generated from `Plan`.

{{schedule_c_table}}

> {{disclaimer}}


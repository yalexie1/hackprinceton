import json
import re
from pathlib import Path

from backend.legal.checks import check_document
from backend.schema import DocumentDraft, StatutoryCheck

EX = Path(__file__).resolve().parents[4] / "specs" / "examples" / "house" / "document_draft.json"

COMPLIANT = """
> DRAFT FOR ATTORNEY REVIEW. NOT LEGAL ADVICE.
- Date the buyer signed: 2026-11-20
- The Notice of Cancellation may be sent to the contractor at the following address or email address: Acme, 1 Main St, a@x.com
- Telephone number: 555-0100
### Home Improvement
You are entitled to a completely filled in copy of this agreement, signed by both you and the contractor, before any work may be started.
**4.1 Parties** Acme, licence 123.
### Contract Price
**4.3 Contract Price.** Owner will pay **$10,000.00**.
### Description of the Project and Description of the Significant Materials to be Used and Equipment to be Installed
Schedule A rows: ENV_ATTIC.
### Downpayment
Down payment: $1,000.00.
THE DOWNPAYMENT MAY NOT EXCEED $1,000 OR 10 PERCENT OF THE CONTRACT PRICE, WHICHEVER IS LESS.
**4.6 Progress payments.** Stage 1 $4,000.00. Stage 2 $5,000.00.
The schedule of progress payments must specifically describe each phase of work.
**4.7 Payment terms and lien releases.** With each payment a full and unconditional release.
**4.8 Start.** Work is substantially commenced on the first day. Start 2026-12-01.
**4.9 Completion.** 2026-12-20.
Extra Work and Change Orders become part of the contract once the order is prepared in writing.
**4.10 Change orders.** Change order form attached.
(A) written authorization before that work starts. (B) the scope of the work it covers, the amount added to or subtracted from the contract, the effect it will have on the progress payments. (C) unjust enrichment.
**4.11 Subcontractors.** Will Contractor use subcontractors? [ ] Yes [X] No
**4.19 Insurance** Nothing makes either party responsible for harm caused by the other party's sole negligence or wilful misconduct.
**4.20 No security interest.** This contract does not give Contractor a mortgage.
### Notices required by California law
#### Commercial General Liability Insurance (CGL)
This contractor is self-insured.
#### Workers' Compensation Insurance
This contractor has no employees and is exempt from workers' compensation requirements.
#### Mechanics Lien Warning
MECHANICS LIEN WARNING: Anyone who helps improve your property, but who is not paid, may record a lien.
Information about the Contractors State License Board (CSLB): CSLB is the state agency.
**Performance and payment bond.** You, the owner, have the right to require Contractor to have a performance and payment bond.
Three-Day Right to Cancel
You, the buyer, have the right to cancel this contract within three business days.
**Signatures**
Notice of Cancellation: You may cancel this transaction, without any penalty or obligation, within three business days.
"""


def draft(markdown=COMPLIANT, unfilled=()):
    return DocumentDraft(doc_id="d", doc_type="retrofit_contract_residential", state="CA",
                         markdown=markdown, unfilled_placeholders=list(unfilled), statutory_checks=[],
                         disclaimer="x")


def by_id(checks):
    return {c.requirement_id: c for c in checks}


EXPECTED_FALSE_RULES = {"CA-R-02", "CA-R-04", "CA-R-05", "CA-R-08", "CA-R-10", "CA-R-14",
                        "CA-R-18", "CA-R-28"}


def test_every_check_has_citation_and_requirement_id():
    checks = check_document(draft())
    assert len(checks) == 50
    for c in checks:
        StatutoryCheck.model_validate(json.loads(c.model_dump_json()))
        assert c.citation and re.fullmatch(r"CA-[A-Z]+-\d+[a-z]?|CA-R-\d+", c.requirement_id)


def test_compliant_draft_fails_only_what_cannot_be_verified():
    failing = {c.requirement.split(":")[0] for c in check_document(draft()) if not c.satisfied}
    assert failing == EXPECTED_FALSE_RULES
    notes = {c.requirement.split(":")[0]: c.note for c in check_document(draft()) if not c.satisfied}
    assert all("type size enforced only in export" in notes[r] for r in
               EXPECTED_FALSE_RULES - {"CA-R-02", "CA-R-28"})


def test_removing_cancellation_clause_fails_that_check():
    stripped = COMPLIANT.replace("You, the buyer, have the right to cancel this contract within three business days.", "")
    c = by_id(check_document(draft(stripped)))["CA-HIC-34"]
    assert c.satisfied is False and "missing" in c.note


def test_other_clause_removals_and_blanks():
    base = lambda m, **k: {c.requirement.split(":")[0]: c for c in check_document(draft(m, **k))}
    assert base(COMPLIANT.replace("full and unconditional release", ""))["CA-R-13"].satisfied is False
    assert base(COMPLIANT.replace("sole negligence or wilful misconduct", ""))["CA-R-25"].satisfied is False
    assert base(COMPLIANT, unfilled=["contractor_license_number"])["CA-R-01"].satisfied is False
    assert base(COMPLIANT, unfilled=["stat_ca_cslb_notice"])["CA-R-27"].satisfied is False
    assert base(COMPLIANT.replace("Down payment: $1,000.00", "Down payment: $2,000.00"))["CA-R-08"].note.startswith("down payment exceeds")
    assert base(COMPLIANT.replace("$5,000.00", "$4,000.00"))["CA-R-09"].satisfied is False
    assert base(COMPLIANT + "\nPV_ROOF included")["CA-R-21"].satisfied is False


def test_example_fixture_draft_is_checked_not_satisfied():
    fx = DocumentDraft.model_validate_json(EX.read_text())
    checks = check_document(fx)
    assert len(checks) == 50 and not all(c.satisfied for c in checks)   # the fixture has blanks and stubs


def test_other_documents_return_nothing_yet():
    d = draft()
    d.doc_type = "retrofit_contract_commercial"          # the Texas residential contract has checks since L5
    assert check_document(d) == []

"""Statutory checks for the California commercial retrofit contract (L7, document 2).

One `StatutoryCheck` per `CA-COM-*` id of `specs/legal/california.md` section 3, which is
the id list `specs/legal.md` section 16 gives for this document. Separate module from
`checks.py` so the residential predicates (L3) are untouched; `check_document` dispatches.

The same three honesties as L3:

- **Type size and placement cannot be seen in Markdown.** A rule that depends on them
  reports `satisfied=False` with the note "type size enforced only in export" even when
  the content is there (`specs/legal.md` 1.1). The CSLB notice is the one that matters
  here: BPC 7030(a) requires at least 10-point type.
- **Some duties software cannot confirm at all**, and saying so is the answer. Whether a
  licence is current and in the right classification is a CSLB lookup; whether the Owner
  actually knew the price was sufficient is a state of mind. Those report `False` with the
  reason, and no amount of drafting changes them.
- **A blank is a failure, not an omission.** A requirement whose field is unfilled is
  reported unsatisfied, because the draft is not signable in that state.

Nothing here tests the *wording* of a clause this lane wrote. These check that the thing
the statute requires is present, filled, and within its numeric limit.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from backend.schema import DocumentDraft, StatutoryCheck

#: The California retention cap for a private works contract entered on or after
#: 2026-01-01 (CIV 8811, added Stats. 2025 ch. 49, SB 61). `california.md` CA-COM-05 and
#: CA-PAY-02 both state it, and section 16's placeholder table says `retention_percent`
#: "capped at 5 in California for contracts from 2026-01-01".
RETENTION_CAP_PERCENT = 5.0

SIZE_NOTE = "type size enforced only in export"
Result = tuple[bool, Optional[str]]

#: `(rule id, requirement, citation, requirement ids in california.md)`. The citations are
#: copied from the id table of `specs/legal/california.md` section 3, not from a statute
#: read here.
COM_RULES: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("CA-C-01", "Contractor licensed in a classification that covers the work",
     "BPC 7031, 7048, 7125", ("CA-COM-01", "CA-LIC-01", "CA-LIC-02")),
    ("CA-C-02", "Contractor's licence number appears in the contract",
     "BPC 7030.5", ("CA-COM-02", "CA-LIC-03")),
    ("CA-C-03", "CSLB notice for a prime contract that is not a home improvement or "
                "service-and-repair contract, in at least 10-point type",
     "BPC 7030(a), (c)", ("CA-COM-03",)),
    ("CA-C-04", "Progress payments: a stated schedule, 30 days for undisputed amounts, "
                "150 per cent withholding cap, 2 per cent per month penalty",
     "CIV 8800", ("CA-COM-04", "CA-PAY-01")),
    ("CA-C-05", f"Retention no more than {RETENTION_CAP_PERCENT:.0f} per cent of each "
                f"payment and of the contract price",
     "CIV 8811", ("CA-COM-05", "CA-PAY-02")),
    ("CA-C-06", "Retention release within 45 days of completion, 10 days to "
                "subcontractors, 2 per cent per month penalty, no advance waiver",
     "CIV 8812, 8814, 8818, 8820", ("CA-COM-06", "CA-PAY-04", "CA-PAY-07")),
    ("CA-C-07", "Subcontractors paid within 7 days of each progress payment",
     "BPC 7108.5", ("CA-COM-07", "CA-PAY-08")),
    ("CA-C-08", "Indemnity does not reach the promisee's sole negligence, wilful "
                "misconduct or active negligence, or owner-furnished design",
     "CIV 2782(a), (c); 2782.05", ("CA-COM-08", "CA-IND-01", "CA-IND-02")),
    ("CA-C-09", "Lien regime: 20-day preliminary notices, statutory waiver forms, notice "
                "of completion and the 10-day mailing duty",
     "CIV 8180-8182, 8200-8204, 8124-8138", ("CA-COM-09", "CA-LIEN-05a")),
    ("CA-C-10", "Electronic signature and records clause where the parties transact "
                "electronically",
     "CIV 1633.7, 1633.3", ("CA-COM-10", "CA-ESIG-01")),
    ("CA-C-11", "Space for the owner's name, address and place of business and for the "
                "construction lender's name and address",
     "CIV 8170", ("CA-COM-11",)),
    ("CA-C-12", "Sufficient-funds presumption: the single written document carries the "
                "LAB 2810(d) items, with estimates allowed, kept 4 years",
     "LAB 2810", ("CA-COM-12",)),
]


class _Draft:
    """Read-only view of a draft. Same shape as the L3 helper, kept local so this module
    does not import from `checks.py` and create a cycle."""

    def __init__(self, draft: DocumentDraft):
        self.raw = draft.markdown
        self.m = " ".join(draft.markdown.lower().split())
        self.unfilled = set(draft.unfilled_placeholders)

    def has(self, *phrases: str) -> bool:
        return all(" ".join(p.lower().split()) in self.m for p in phrases)

    def any_of(self, *phrases: str) -> bool:
        return any(" ".join(p.lower().split()) in self.m for p in phrases)

    def blank(self, name: str) -> bool:
        return (name in self.unfilled or f"[[blank: {name}" in self.m
                or "{{" + name + "}}" in self.raw)

    def any_blank(self, *names: str) -> bool:
        return any(self.blank(n) for n in names)

    def mentions(self, name: str) -> bool:
        """Whether the document carries a field at all, filled or blank.

        LAB 2810 allows an estimate where a number is not yet known, so the question for
        CA-C-12 is whether the *item* is in the document, which is different from whether
        it has a value yet.
        """
        return (name in self.unfilled or f"[[blank: {name}" in self.m
                or "{{" + name + "}}" in self.raw
                or name.replace("_", " ") in self.m)

    def percent_after(self, label: str) -> Optional[float]:
        m = re.search(re.escape(label.lower()) + r"[^%]{0,80}?([\d.]+)\s*per cent", self.m)
        return float(m.group(1)) if m else None


def c01(d: _Draft) -> Result:
    return False, "verify the licence and its classification on the CSLB site; software cannot verify"


def c02(d: _Draft) -> Result:
    return not d.blank("contractor_license_number"), None


def c03(d: _Draft) -> Result:
    if d.blank("stat_ca_cslb_notice_commercial"):
        return False, "the 10-point CSLB notice is blank; insert the verbatim text from california.md"
    return False, f"content present; {SIZE_NOTE} (BPC 7030(a) requires at least 10-point)"


def c04(d: _Draft) -> Result:
    if not d.has("30 days", "150 per cent", "2 per cent per month"):
        return False, "the 30-day, 150 per cent and 2 per cent per month terms are not all stated"
    if d.blank("schedule_b_rows"):
        return False, "a payment schedule is required; Schedule B is blank"
    return True, None


def c05(d: _Draft) -> Result:
    if d.blank("retention_percent"):
        return False, "retention percentage not stated; state one or state that none is withheld"
    pct = d.percent_after("retention of no more than")
    if pct is None:
        return False, "retention percentage stated but could not be read for the cap check"
    if pct > RETENTION_CAP_PERCENT:
        return False, (f"{pct:g} per cent exceeds the {RETENTION_CAP_PERCENT:.0f} per cent cap "
                       f"for a contract entered on or after 2026-01-01")
    return True, None


def c06(d: _Draft) -> Result:
    return d.has("45 days", "10 days", "2 per cent per month"), None


def c07(d: _Draft) -> Result:
    return d.has("7 days"), None


def c08(d: _Draft) -> Result:
    return d.has("sole negligence", "wilful misconduct", "active negligence"), None


def c09(d: _Draft) -> Result:
    if not d.has("20 days", "notice of completion", "10 days"):
        return False, "the 20-day preliminary notice, notice of completion or 10-day mailing is missing"
    if not d.any_of("statutory form", "the form the law requires", "waiver and release"):
        return False, "the statutory waiver and release forms are not referred to"
    return True, None


def c10(d: _Draft) -> Result:
    if not d.has("electronic"):
        return False, "no electronic records clause"
    if d.blank("signing_method"):
        return False, "signing method not stated"
    return True, None


def c11(d: _Draft) -> Result:
    owner = not d.blank("owner_names") and not d.blank("owner_mailing_address")
    lender_space = d.mentions("construction_lender_name") and d.mentions("construction_lender_address")
    if not lender_space:
        return False, "the construction lender space is required in a commercial contract, even if empty"
    if not owner:
        return False, "the owner's name or address is blank"
    return True, None


#: The LAB 2810(d) items, as `california.md` CA-COM-12 enumerates them. Presence is what
#: earns the rebuttable presumption; values may be estimates.
_LAB_2810_ITEMS = ("contractor_tax_ein", "contractor_wc_policy_number", "contractor_wc_insurer",
                   "total_workers", "total_wages_usd", "wage_payment_dates",
                   "contractor_vehicle_details", "worker_housing_address",
                   "contractor_commission", "independent_contractors")


def c12(d: _Draft) -> Result:
    absent = [n for n in _LAB_2810_ITEMS if not d.mentions(n)]
    if absent:
        return False, f"the document does not carry {len(absent)} of the LAB 2810(d) items: {absent[:4]}"
    if not d.has("four years"):
        return False, "the 4-year retention of the contract is not stated"
    unfilled = [n for n in _LAB_2810_ITEMS if d.blank(n)]
    if unfilled:
        return False, (f"{len(unfilled)} of the items are blank; an estimate is allowed but a "
                       f"blank does not earn the presumption")
    return True, None


PREDICATES: dict[str, Callable[[_Draft], Result]] = {
    rule_id: globals()[f"c{rule_id.split('-')[-1]}"] for rule_id, *_ in COM_RULES}


def check_commercial(draft: DocumentDraft) -> list[StatutoryCheck]:
    """Every `CA-COM-*` requirement, one `StatutoryCheck` per requirement id."""
    from backend.legal.checks._data import CITATIONS

    d = _Draft(draft)
    out: list[StatutoryCheck] = []
    for rule_id, requirement, citation, ids in COM_RULES:
        satisfied, note = PREDICATES[rule_id](d)
        for req_id in ids:
            out.append(StatutoryCheck(
                requirement_id=req_id, requirement=f"{rule_id}: {requirement}",
                citation=CITATIONS.get(req_id, citation), satisfied=satisfied, note=note))
    return out

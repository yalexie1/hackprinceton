"""Statutory checks for the California residential retrofit contract (L3).

One StatutoryCheck per california.md id of each CA-R rule (legal.md section 6). Checks read
only the DocumentDraft (markdown and unfilled_placeholders). Type size and placement cannot
be seen in Markdown, so a rule that depends on them reports satisfied=false with the note
"type size enforced only in export" even when the content is present (legal.md 1.1).
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from backend.legal.checks._data import CITATIONS, RULES
from backend.schema import DocumentDraft, StatutoryCheck

SIZE_NOTE = "type size enforced only in export"
Result = tuple[bool, Optional[str]]


class _Draft:
    def __init__(self, draft: DocumentDraft):
        self.raw = draft.markdown
        self.m = " ".join(draft.markdown.lower().split())
        self.unfilled = set(draft.unfilled_placeholders)

    def has(self, *phrases: str) -> bool:
        return all(" ".join(p.lower().split()) in self.m for p in phrases)

    def blank(self, name: str) -> bool:
        return (name in self.unfilled or f"[[blank: {name}" in self.m
                or "{{" + name + "}}" in self.raw)

    def any_blank(self, *names: str) -> bool:
        return any(self.blank(n) for n in names)

    def money_after(self, label: str) -> Optional[float]:
        m = re.search(re.escape(label.lower()) + r"[^$]{0,60}\$\s*([\d,]+(?:\.\d+)?)", self.m)
        return float(m.group(1).replace(",", "")) if m else None


def _with_size(content_ok: bool, what: str) -> Result:
    if not content_ok:
        return False, f"{what} missing or blank"
    return False, f"content present; {SIZE_NOTE}"


def r00(d: _Draft) -> Result:
    price = d.money_after("contract price")
    if d.blank("contract_price_usd") or price is None:
        return False, "contract price not filled"
    if price <= 500:
        return True, "price is $500 or less: a simpler form may be lawful (B&P 7159.10)"
    return True, None


def r01(d): return (not d.any_blank("contractor_name", "contractor_business_address",
                                    "contractor_license_number"), None)
def r02(d): return False, "verify licence on the CSLB site; software cannot verify"


def r03(d: _Draft) -> Result:
    ok = d.has("date the buyer signed", "notice of cancellation may be sent to the contractor") \
        and not d.any_blank("contractor_name", "contractor_business_address",
                            "contractor_cancellation_email", "contractor_phone")
    return ok, None if ok else "first-page block missing or has blanks"


def r04(d): return _with_size(re.search(r"^#+\s*home improvement\s*$", d.raw, re.I | re.M)
                              is not None, "Home Improvement heading")
def r05(d): return _with_size(d.has("you are entitled to a completely filled in copy")
                              and not d.blank("stat_ca_entitled_to_copy"), "statement")


def r06(d): return (not d.blank("contract_price_usd") and d.money_after("contract price") is not None,
                    None)


def r07(d: _Draft) -> Result:
    ok = d.has("description of the project") and not d.blank("schedule_a_rows") \
        and "schedule a" in d.m
    return ok, None if ok else "Schedule A empty or heading missing"


def r08(d: _Draft) -> Result:
    price, down = d.money_after("contract price"), d.money_after("down payment")
    if price is not None and down is not None and down > min(1000.0, 0.10 * price):
        return False, "down payment exceeds the lesser of $1,000 or 10% of the price"
    return _with_size(d.has("the downpayment may not exceed $1,000 or 10 percent of the contract price"),
                      "downpayment statement")


def r09(d: _Draft) -> Result:
    if d.blank("progress_payment_table"):
        return False, "progress payment table not filled"
    price, down = d.money_after("contract price"), d.money_after("down payment") or 0.0
    seg = re.search(r"4\.6 progress payments(.*?)4\.7 payment terms", d.m)
    amounts = [float(x.replace(",", "")) for x in re.findall(r"\$\s*([\d,]+\.\d\d)", seg.group(1))] if seg else []
    if price is None or not amounts:
        return False, "could not read the stage amounts"
    ok = abs(sum(amounts) - (price - down)) < 0.005
    return ok, None if ok else "stage amounts do not sum to the price less the down payment"


def r10(d): return _with_size(d.has("the schedule of progress payments must specifically describe each phase of work")
                              and not d.blank("progress_payment_table"), "progress payment statement or table")


def r11(d: _Draft) -> Result:
    ok = not d.any_blank("start_date", "completion_date") and d.has("substantially commenced")
    return ok, None if ok else "dates blank or clause 4.8 missing"


def r12(d: _Draft) -> Result:
    ok = d.has("extra work and change orders become part of the contract", "4.10 change orders",
               "written authorization", "scope of the work it covers", "amount added to or subtracted",
               "effect it will have", "unjust enrichment", "change order form")
    return ok, None if ok else "change order note, clause 4.10 or the five notice points missing"


def r13(d): return d.has("full and unconditional release"), None


def r14(d: _Draft) -> Result:
    ok = d.has("you, the buyer, have the right to cancel this contract within") and \
        d.has("you may cancel this transaction, without any penalty or obligation") and \
        bool(re.search(r"(three|five)[- ]day right to cancel", d.m))
    return _with_size(ok, "right-to-cancel notice or Notice of Cancellation form")


def r15(d): return True, "sales language is not recorded in the draft; this is an English draft"


def r16(d: _Draft) -> Result:
    cgl = d.has("commercial general liability insurance") and any(
        p in d.m for p in ("does not carry commercial general liability", "carries commercial general liability",
                           "is self-insured", "limited liability company that carries liability insurance"))
    wc = d.has("workers' compensation insurance") and any(
        p in d.m for p in ("exempt from workers' compensation", "carries workers' compensation"))
    return cgl and wc, None if cgl and wc else "CGL or workers' compensation statement missing"


def r17(d): return d.has("mechanics lien warning: anyone who helps improve your property"), None
def r18(d): return _with_size(d.has("information about the contractors state license board"), "CSLB notice")


def r19(d: _Draft) -> Result:
    i, j = d.m.find("right to require contractor to have a performance and payment bond"), d.m.find("**signatures**")
    ok = i != -1 and j != -1 and i < j
    return ok, None if ok else "bond sentence missing or not before the signatures"


def r20(d: _Draft) -> Result:
    if "4.11 subcontractors" not in d.m:
        return False, "clause 4.11 missing"
    yes = re.search(r"\[x\]\s*yes", d.m) is not None
    no = re.search(r"\[x\]\s*no", d.m) is not None
    if not (yes or no):
        return False, "subcontractor box not answered"
    if yes and not d.has("one or more subcontractors will be used on this project"):
        return False, "subcontractor disclaimer missing"
    return True, None


def r21(d): return "pv_roof" not in d.m, None
def r22(d): return d.has("4.20 no security interest", "does not give contractor a mortgage"), None
def r23(d): return True, "applies only when financing_contingent = yes; the draft does not record it"


def r24(d: _Draft) -> Result:
    if "binding arbitration" not in d.m:
        return True, None
    ok = d.has("arbitration of disputes", "notice: by initialing in the space below")
    return ok, None if ok else "arbitration clause lacks the statutory title or notice"


def r25(d): return d.has("sole negligence or wilful misconduct"), None


def r26(d: _Draft) -> Result:
    if "retention" not in d.m:
        return True, None
    return d.has("within 45 days after completion"), None


def r27(d: _Draft) -> Result:
    bad = (any(n.startswith("stat_") for n in d.unfilled) or "[[blank: stat_" in d.m
           or "{{stat_" in d.raw or "to be inserted from specs/legal/california.md" in d.m)
    return not bad, "a statutory text is still a blank" if bad else None


def r28(d): return False, "procedural duty at signing; software cannot confirm"
def r29(d): return True, "assumes paper signing; the cancellation and arbitration parts need wet signatures if signed electronically"


PREDICATES: dict[str, Callable[[_Draft], Result]] = {
    f"CA-R-{n:02d}": globals()[f"r{n:02d}"] for n in range(30)}


def check_document(draft: DocumentDraft) -> list[StatutoryCheck]:
    """Checks for the documents that have predicates. `[]` means **not checked**, not
    "nothing wrong", and a caller showing a checklist has to say which it is.

    Dispatch rather than one table, so each document's predicates live with the ids its
    own section of `specs/legal.md` lists: `texas.py` for document 1T, `commercial.py`
    for document 2, `cpace.py` for document 6 in either state, and the `CA-R-*`
    table below for document 1.
    """
    if (draft.doc_type, draft.state) == ("retrofit_contract_residential", "TX"):
        from backend.legal.checks import texas

        return texas.check_document(draft)
    if (draft.doc_type, draft.state) == ("retrofit_contract_commercial", "CA"):
        from backend.legal.checks.commercial import check_commercial

        return check_commercial(draft)
    if draft.doc_type == "cpace_package":
        from backend.legal.checks.cpace import check_cpace

        return check_cpace(draft)
    if (draft.doc_type, draft.state) != ("retrofit_contract_residential", "CA"):
        return []
    d = _Draft(draft)
    out: list[StatutoryCheck] = []
    for rule_id, requirement, citation, ids in RULES:
        satisfied, note = PREDICATES[rule_id](d)
        for req_id in ids:
            out.append(StatutoryCheck(
                requirement_id=req_id, requirement=f"{rule_id}: {requirement}",
                citation=CITATIONS.get(req_id, citation), satisfied=satisfied, note=note))
    return out

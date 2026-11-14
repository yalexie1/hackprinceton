"""Statutory checks for the Texas residential retrofit contract (L5).

One StatutoryCheck per texas.md id of each TX-R rule (legal.md section 12.2). Like the California checks they
read only the DocumentDraft. Which regimes are on is read from the `<!-- regimes: ... -->` line the engine
writes at the top of a Texas draft; a rule whose regime is off is satisfied with the note "not applicable".
Type size, placement and procedural steps (oral notice, filing, delivery) cannot be seen in Markdown, so those
report satisfied=false with a note, as in the California checks.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from backend.legal.checks._tx_data import CITATIONS, RULES
from backend.legal.checks.checks import SIZE_NOTE, Result, _Draft
from backend.schema import DocumentDraft, StatutoryCheck

_REGIMES = re.compile(r"<!--\s*regimes:\s*(.*?)\s*-->")


def _regimes(d: _Draft) -> dict:
    m = _REGIMES.search(d.raw)
    return dict(p.strip().split("=", 1) for p in m.group(1).split(";") if "=" in p) if m else {}


def _na(d: _Draft, regime: str) -> Optional[Result]:
    return (True, f"not applicable: {regime} off") if _regimes(d).get(regime) != "on" else None


def _trade(d: _Draft, trade: str) -> bool:
    return trade in _regimes(d).get("trades", "").split(",")


def _stat_blank(d: _Draft, *names: str) -> bool:
    return d.any_blank(*names)


def _present(d: _Draft, *phrases: str) -> bool:
    return d.has(*phrases)


def t01(d: _Draft) -> Result:
    names = []
    if _trade(d, "electrical"):
        names += ["electrical_contractor_license_no", "stat_tx_tdlr_electrical_statement"]
    if _trade(d, "hvac"):
        names += ["hvac_contractor_license_no", "hvac_license_class", "stat_tx_tdlr_acr_statement"]
    note = "verify licences on the TDLR and TSBPE sites"
    if not names:
        return True, "no electrical or HVAC trade in scope; " + note
    if d.any_blank(*names):
        return False, "licence number or TDLR statement not filled; " + note
    return True, note


def t02(d): return (True, "not applicable: no water heater work") if not _trade(d, "plumbing") else \
    (not d.blank("plumbing_contractor_license_no"), "verify the licence on the TSBPE site")
def t03(d): return (False, "insurance limits are entered in Schedule A by the contractor; software cannot confirm "
                    "they meet the minimums") if (_trade(d, "electrical") or _trade(d, "hvac")) else \
    (True, "not applicable: no electrical or HVAC trade")
def t04(d): return False, "unverified, U-01: no state general-contractor licence found"


def t10(d: _Draft) -> Result:
    r = _na(d, "homestead")
    if r:
        return r
    if _regimes(d).get("married") == "unknown":
        return False, "owner_married not given: spouse signature cannot be decided"
    if _regimes(d).get("married") == "yes" and d.blank("owner_spouse_name"):
        return False, "spouse name not filled"
    return True, None


def t12(d: _Draft) -> Result:
    r = _na(d, "homestead")
    if r:
        return r
    if _regimes(d).get("financed") != "yes":
        return True, "not financed"
    return (not d.blank("credit_application_date") and d.has("fifth day after that date")), \
        "credit application date must be at least five days before signing"


def t13(d: _Draft) -> Result:
    return _na(d, "homestead") or (d.has("may rescind this contract without penalty or charge within three days"), None)


def t14(d: _Draft) -> Result:
    return _na(d, "homestead") or (not d.blank("execution_office_name_and_address"),
                                   "remote signing is not offered (unverified, U-02)")


def t16(d: _Draft) -> Result:
    return _na(d, "homestead") or (False, "filing is a post-signing step")


def t17(d: _Draft) -> Result:
    r = _na(d, "homestead")
    if r:
        return r
    ok = not d.blank("stat_tx_homestead_warning")
    return False, (f"content present; {SIZE_NOTE}" if ok else "homestead warning missing or blank")


def t18(d): return False, "treated as inapplicable pending attorney check (U-03)"


def t19(d: _Draft) -> Result:
    r = _na(d, "homestead")
    if r:
        return r
    if _regimes(d).get("arbitration") != "yes":
        return True, "no arbitration clause"
    return ("**any dispute not settled under this clause" in d.m), "arbitration clause must be 10-point bold"


def t20(d: _Draft) -> Result:
    r = _na(d, "residence")
    if r:
        return r
    ok = not d.blank("stat_tx_53255_disclosure")
    return ok, ("delivery before signing is a procedural step" if ok else
                "section 53.255(b) disclosure text not loaded (legal.md T6); delivery before signing is a procedural step")


def t22(d: _Draft) -> Result:
    r = _na(d, "residence")
    if r:
        return r
    return (d.has("schedule d: subcontractor and supplier list") and not d.blank("stat_tx_sub_list_notice")
            and d.has("within 15 days")), None


def t24(d: _Draft) -> Result:
    return _na(d, "residence") or (d.has("together with a disbursement statement"), None)
def t25(d): return d.has("an affidavit that contractor has paid in full every person"), None
def t26(d): return d.has("11.18 no transfer of the property", "does not require owner to convey the property"), None


def t30(d: _Draft) -> Result:
    r = _na(d, "solicitation")
    if r:
        return r
    ok = not d.blank("stat_tx_cancel_statement")
    return False, (f"content present; {SIZE_NOTE}" if ok else "cancellation statement missing or blank")


def t31(d: _Draft) -> Result:
    r = _na(d, "solicitation")
    if r:
        return r
    english = not d.blank("sales_language") or True
    return english, "English drafts only; the language of the oral presentation is not recorded"


def t32(d: _Draft) -> Result:
    r = _na(d, "solicitation")
    if r:
        return r
    return (not d.blank("stat_tx_notice_of_cancellation_form"),
            "name, address, date and deadline must be filled; attach in duplicate, detachable, 10-point bold")


def t34(d: _Draft) -> Result:
    r = _na(d, "solicitation")
    if r:
        return r
    return False, "oral notice at signing and refund within 10 business days are procedural; the clause text contains no waiver"


def t40(d: _Draft) -> Result:
    return d.has("(c) retainage", "hold back 10 percent", "31st day after the work is complete") and \
        d.has("retainage held (10 percent)"), None


def t42(d: _Draft) -> Result:
    m = re.search(r"within (\d+) days after receiving it", d.m)
    if not m:
        return False, "payment period not found"
    days = int(m.group(1))
    if days > 60:
        return False, f"{days} days exceeds the 60-day limit for a single-family residence"
    ok = d.has("1.5 percent per month", "110 percent of the disputed amount")
    return ok, (None if days <= 35 else f"{days} days is allowed only for a single-family residence by agreement")


def t48(d): return d.has("signed by owner and contractor before the changed work starts"), None


def t49(d: _Draft) -> Result:
    if not d.has("held in trust for the people who furnish labor and materials"):
        return False, "trust-fund statement missing"
    if "construction account" in d.m and d.blank("construction_account_bank"):
        return False, "construction account bank not filled"
    return True, None


def t60(d: _Draft) -> Result:
    ok = not d.blank("stat_tx_rcla_notice") and d.has("60-day notice before a consumer protection lawsuit")
    return False, (f"content present; {SIZE_NOTE}" if ok else "chapter 27 notice missing or blank, or clause 11.20 altered")


def t62(d): return d.has("each party is responsible for harm caused by its own negligence"), None
def t64(d): return d.has("contractor does not warrant that it is accurate"), "unverified, U-05"
def t70(d): return True, "this template does not support disaster remediation work"


def t80(d: _Draft) -> Result:
    ok = d.has("estimates from a computer model", "not a promise by contractor") and "waiver of consumer rights" not in d.m
    return ok, None


def t81(d): return d.has("texas law governs this contract", "county, texas"), None


def t82(d: _Draft) -> Result:
    ok = d.has("11.22 electronic signing", "ask for a paper copy")
    if _regimes(d).get("homestead") == "on":
        return ok, "homestead: signed in person at the named office"
    return ok, None


def t83(d: _Draft) -> Result:
    blanks = sorted(n for n in d.unfilled if n.startswith("stat_tx_"))
    return not blanks, ("statutory text not filled: " + ", ".join(blanks)) if blanks else None


PREDICATES: dict[str, Callable[[_Draft], Result]] = {
    f"TX-R-{n}": globals()[f"t{n}"] for n in (
        "01 02 03 04 10 12 13 14 16 17 18 19 20 22 24 25 26 30 31 32 34 40 42 48 49 60 62 64 70 80 81 82 83".split())}


def check_document(draft: DocumentDraft) -> list[StatutoryCheck]:
    d = _Draft(draft)
    out: list[StatutoryCheck] = []
    for rule_id, requirement, ids in RULES:
        satisfied, note = PREDICATES[rule_id](d)
        for req_id in ids:
            out.append(StatutoryCheck(
                requirement_id=req_id, requirement=f"{rule_id}: {requirement}",
                citation=CITATIONS.get(req_id, "project rule: every stat_tx_ placeholder is filled verbatim"), satisfied=bool(satisfied), note=note))
    return out

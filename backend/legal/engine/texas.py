"""Texas residential retrofit contract: the four regimes and the conditional blocks (L5).

Source: specs/legal.md Part B, sections 10, 11.A and 11.B. Everything here only decides *which* clauses
a draft carries and fills the wording legal.md itself gives; verbatim statutory text is never written
here (those are `stat_tx_*` placeholders, blank until the texas.md anchors are loaded). A party name,
licence number, address or legal description has no binding: it comes from `DocumentRequest.fields`.

Regimes follow legal.md section 10. When an input is blank the default is the one that adds protections.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Callable, Optional

HVAC = {"HVAC_HP", "HVAC_RTU", "HVAC_ECON", "HVAC_DUCT", "CTRL_TSTAT"}
ELECTRICAL = {"LGT_LED", "LGT_CTRL", "PLUG_MGMT"}
PLUMBING = {"DHW_HPWH"}
LICENSED = HVAC | ELECTRICAL | PLUMBING


def _yes(v) -> Optional[bool]:
    s = str(v or "").strip().lower()
    return True if s in ("yes", "true", "y") else False if s in ("no", "false", "n") else None


def _measures(c) -> set[str]:
    return set(c.request.measure_ids)


def regimes(c) -> dict:
    """The switches of legal.md section 10 and the trades in scope."""
    role = c.run.request.role
    homestead = _yes(c.field("is_homestead"))
    homestead = (role == "owner_occupier") if homestead is None else homestead
    consumer = _yes(c.field("consumer_initiated")) is True
    at_premises = _yes(c.field("negotiated_at_contractor_premises")) is True
    ms = _measures(c)
    solicitation = not at_premises and not (consumer and ms and ms <= LICENSED)
    price = _price(c)
    return {
        "homestead": homestead, "residence": role == "owner_occupier", "solicitation": solicitation,
        "rcla": True, "tenant": role == "tenant",
        "married": _yes(c.field("owner_married")),
        "financed": _yes(c.field("financed")) is True,
        "arbitration": _yes(c.field("arbitration")) is True,
        "health_safety": _yes(c.field("immediate_health_safety_repair")) is True,
        "trade_hvac": bool(ms & HVAC), "trade_electrical": bool(ms & ELECTRICAL) or
        _yes(c.field("service_upgrade")) is True,
        "trade_plumbing": bool(ms & PLUMBING),
        "construction_account": homestead and (price is None or price > 5000),
        "deposit": (_num(c.field("deposit_usd")) or 0) > 0,
    }


def _num(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def _price(c) -> Optional[float]:
    return _num(c.field("contract_price_usd"))


_IF = re.compile(r"<!--\s*if:\s*([a-z_]+)\s*-->(.*?)<!--\s*endif\s*-->\n?", re.S)


def apply_conditions(body: str, flags: dict) -> str:
    """Drop every `<!-- if: flag --> ... <!-- endif -->` block whose regime is off."""
    return _IF.sub(lambda m: m.group(2) if flags.get(m.group(1)) else "", body)


# ---------- dates (legal.md 11.B; both are marked "check before signing") ----------

def _contract_date(c) -> Optional[date]:
    try:
        return date.fromisoformat(str(c.field("contract_date")))
    except (TypeError, ValueError):
        return None


def _solicitation_cancel_by(c) -> Optional[str]:
    d = _contract_date(c)
    if d is None:
        return None
    n = 0
    while n < 3:                       # Monday to Saturday; federal holidays are not excluded here
        d += timedelta(days=1)
        n += d.weekday() != 6
    return f"{d.isoformat()} (check before signing: business-day counting is unverified, T4)"


def _homestead_rescind_by(c) -> Optional[str]:
    d = _contract_date(c)
    return None if d is None else f"{(d + timedelta(days=3)).isoformat()} (check before signing: T5)"


# ---------- bindings ----------

def _on(flag: str, text: str) -> Callable:
    return lambda c: text if regimes(c)[flag] else None


def _regimes_comment(c) -> str:
    r = regimes(c)
    onoff = lambda k: "on" if r[k] else "off"
    married = {True: "yes", False: "no", None: "unknown"}[r["married"]]
    trades = ",".join(t for t in ("hvac", "electrical", "plumbing") if r[f"trade_{t}"]) or "none"
    return (f"<!-- regimes: homestead={onoff('homestead')}; residence={onoff('residence')}; "
            f"solicitation={onoff('solicitation')}; rcla=on; married={married}; trades={trades}; "
            f"financed={'yes' if r['financed'] else 'no'}; arbitration={'yes' if r['arbitration'] else 'no'} -->")


def _spouse_party(c):
    r = regimes(c)
    return "{{owner_spouse_name}}, Owner's spouse, joins in this contract." if r["homestead"] and r["married"] else None


def _spouse_header(c):
    r = regimes(c)
    return "Owner's spouse" if r["homestead"] and r["married"] is not False else ""


def _spouse_name(c):
    r = regimes(c)
    return None if r["homestead"] and r["married"] is not False else ""


def _tenant(c):
    return ("Owner of record {{property_owner_of_record}} has consented in writing to this work; the consent "
            "is attached. Texas homestead and lien rules then concern the owner of record, not the tenant."
            if regimes(c)["tenant"] else None)


def _legal_description(c):
    return "Legal description: {{legal_description}}." if regimes(c)["homestead"] else None


def _trade_table(c) -> str:
    r = regimes(c)
    rows = []
    if r["trade_hvac"]:
        rows.append("| Air conditioning and refrigeration | {{trade_company_hvac}} | Class {{hvac_license_class}}, "
                    "no. {{hvac_contractor_license_no}} | TDLR |")
    if r["trade_electrical"]:
        rows.append("| Electrical | {{trade_company_electrical}} | no. {{electrical_contractor_license_no}} | TDLR |")
    if r["trade_plumbing"]:
        rows.append("| Plumbing | {{trade_company_plumbing}} | no. {{plumbing_contractor_license_no}} | TSBPE |")
    if not rows:
        return "No state-licensed trade is in scope for the improvements in Schedule A. *(Envelope work: no state licence found, unverified U-01.)*"
    return "| Trade | Company | Licence | Authority |\n|---|---|---|---|\n" + "\n".join(rows)


def _deposit(c):
    r = regimes(c)
    if not r["deposit"]:
        return None
    due = ("the day after the cancellation period ends" if r["solicitation"] else "{{deposit_due_rule}}")
    return f"Owner will pay a deposit of ${{{{deposit_usd}}}} on {due}. The deposit is credited to the first payment stage."


def _disbursement(c):
    return (", together with a disbursement statement naming each subcontractor and supplier Contractor intends "
            "to pay from the requested funds, with their addresses, in the form in Schedule B"
            if regimes(c)["residence"] else None)


def _payment_days(c):
    return None if c.field("payment_due_days") else "35"


def _construction_account(c):
    return ("Contractor will deposit all payments under this contract in an account at {{construction_account_bank}} "
            "that the bank's statements call a construction account, and will keep the records of that account the "
            "law requires until at least the first anniversary of completion."
            if regimes(c)["construction_account"] else
            "Contractor will use these payments only for the work and for paying those people.")


def _earliest_start(c):
    r = regimes(c)
    parts = []
    if r["solicitation"] or r["homestead"]:
        which = [w for w, on in (("cancellation", r["solicitation"]), ("rescission", r["homestead"])) if on]
        parts.append(f"the end of the {' and '.join(which)} period(s) in clause 11.19")
    if r["homestead"]:
        parts.append("the filing of this contract with the {{property_county}} County Clerk")
    if r["residence"]:
        parts.append("Owner's receipt of the Schedule D list")
    return " and ".join(parts) if parts else "this contract is signed by both parties"


def _sub_list(c):
    return ("Before construction starts, Contractor will give Owner the list in Schedule D of each subcontractor and "
            "supplier, with name, address and telephone number, and will give Owner an updated list within 15 days "
            "after one is added or removed." if regimes(c)["residence"]
            else "Contractor will tell Owner the names of its subcontractors on request.")


def _cancellation_summary(c):
    r = regimes(c)
    out = []
    if r["homestead"]:
        out.append("Owner may rescind this contract without penalty or charge within three days after it is signed by "
                   "all parties; see the rescission notice below.")
    if r["solicitation"]:
        out.append("Owner may cancel this transaction until midnight of the third business day after it is signed; "
                   "see the notice next to Owner's signature and the attached Notice of Cancellation.")
    if r["homestead"] and r["solicitation"]:
        out.append("These are two separate rights with separate deadlines. Owner may use either. Last day to rescind: "
                   "{{homestead_rescind_by}}. Last day to cancel: {{solicitation_cancel_by}}.")
    return " ".join(out) or "Texas law does not give Owner a cancellation period for this contract."


def _rescission(c):
    r = regimes(c)
    if not r["homestead"]:
        return None
    text = ("**Owner's right to rescind (homestead).** Owner may rescind this contract without penalty or charge within "
            "three days after it has been signed by all parties, by written notice to Contractor at the address in "
            "clause 11.1. Last day to rescind: {{homestead_rescind_by}}.")
    if r["health_safety"]:
        text += (" Owner acknowledges in writing that the work is necessary to complete immediate repairs to conditions "
                 "that materially affect the health or safety of the Owner or a person residing in the home, and that "
                 "the three-day period therefore does not apply. Owner's signature: ______")
    return text


def _and_spouse(c):
    return " and Owner's spouse" if regimes(c)["married"] else ""


def _execution_place(c):
    r = regimes(c)
    if not r["homestead"]:
        return None
    text = ("Signed by Owner{{and_spouse}} at the office of {{execution_office_name_and_address}}, which is the office of "
            "a third-party lender making credit available for this work, an attorney at law, or a title company.")
    if r["financed"]:
        text += (" Owner applied in writing for credit for this work on {{credit_application_date}}; this contract is "
                 "signed on or after the fifth day after that date.")
    return text


def _arbitration(c):
    r = regimes(c)
    if not r["arbitration"]:
        return "If the dispute is not settled, either party may go to court."
    text = ("Any dispute not settled under this clause will be decided by binding arbitration before "
            "{{arbitration_provider}}, seated in {{property_county}} County, Texas, under its rules for residential "
            "construction disputes. Arbitration does not start until any notice period required by law has run.")
    return f"**{text}**" if r["homestead"] else text


def _county(c):
    return "Harris" if (c.run.property.city or "").strip().lower() == "houston" else None


BINDINGS: dict[str, Callable] = {
    "regimes_comment": _regimes_comment, "property_county": _county,
    "spouse_party_block": _spouse_party, "spouse_column_header": _spouse_header, "owner_spouse_name": _spouse_name,
    "tenant_consent_block": _tenant, "legal_description_block": _legal_description,
    "trade_licence_table": _trade_table, "deposit_block": _deposit,
    "disbursement_statement_clause": _disbursement, "payment_due_days": _payment_days,
    "construction_account_clause": _construction_account, "earliest_start_rule": _earliest_start,
    "subcontractor_list_clause": _sub_list, "cancellation_rights_summary": _cancellation_summary,
    "homestead_rescission_block": _rescission, "and_spouse": _and_spouse,
    "execution_place_block": _execution_place, "arbitration_block_tx": _arbitration,
    "solicitation_cancel_by": _solicitation_cancel_by, "homestead_rescind_by": _homestead_rescind_by,
}

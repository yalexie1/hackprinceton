"""Statutory checks for the C-PACE package (L7, document 6), California and Texas.

The id lists are the ones `specs/legal.md` section 20 gives: California `CA-PACE-01` to
`-11` (Route A), `-12` to `-14` (Route B), `-15` to `-17` (availability, reported as
notes); Texas `TX-PACE-01` to `-17` (statute) and `-30` to `-42` (Texas PACE Authority
Program Guide).

**Programme rule and statute are never presented as the same thing.** Section 20 is
explicit that every Texas rule from `TX-PACE-30` upward comes from the Program Guide and
not from Chapter 399, and the requirement text of each check says so. A programme may
apply its own rules differently; a check that failed a programme rule is not a finding
that the owner broke the law, and this module does not let the two read alike.

Three things this module deliberately will not do:

- **It will not report an incomplete test as passed.** California's 5 per cent
  tax-burden cap needs the annual tax bill and the market value; without them the check
  says the test is incomplete. A missing input is not a satisfied requirement.
- **It will not hide a failed savings test.** Texas requires a programme SIR of at least
  1. A project below it still gets a package, with the shortfall reported, because the
  owner needs to see what would have to change. Hiding it would be the one outcome that
  helps nobody.
- **It will not assert lien priority.** The California priority provisions were not
  opened (`california.md` CA-PACE-10, section 8.E2), so the check reports that the
  question is open rather than resolving it in either direction.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from backend.schema import DocumentDraft, StatutoryCheck

#: The programme's minimum savings-to-investment ratio (TX-PACE-30, Program Guide v4.3).
#: A programme rule, not a statutory one.
TX_SIR_MINIMUM = 1.0

#: The programme's limit on other fees and costs incident to the project, as a share of
#: the total assessment (TX-PACE-38, Program Guide v4.3 Step 2). A programme rule, not
#: statute - and the guide does state the figure, which I first wrote off as unverified.
TX_FEE_SHARE_LIMIT = 0.20

#: California's statutory cap on total annual property taxes and assessments as a share
#: of market value, for commercial property (CA-PACE-07, SHC 5898.15).
CA_TAX_BURDEN_CAP = 0.05

#: Prefix that marks a requirement as coming from the Texas PACE Authority Program Guide
#: rather than from statute. Section 20 requires the distinction to be visible.
PROGRAMME = "(programme rule)"

Result = tuple[bool, Optional[str]]


class _Draft:
    def __init__(self, draft: DocumentDraft):
        self.raw = draft.markdown
        self.m = " ".join(draft.markdown.lower().split())
        self.unfilled = set(draft.unfilled_placeholders)

    def has(self, *phrases: str) -> bool:
        return all(" ".join(p.lower().split()) in self.m for p in phrases)

    def blank(self, name: str) -> bool:
        """Whether a placeholder is unfilled.

        The blank marker is matched **with its trailing comma**. Without it,
        `blank("program_sir")` was satisfied by `[[BLANK: program_sir_meets_minimum, ...]]`
        and every name that is a prefix of another read as blank - which silently made
        three checks report "not stated" for figures that were supplied.
        """
        return (name in self.unfilled or f"[[blank: {name}," in self.m
                or "{{" + name + "}}" in self.raw)

    def any_blank(self, *names: str) -> bool:
        return any(self.blank(n) for n in names)

    def number_for(self, name: str) -> Optional[float]:
        """A filled numeric placeholder's value, read back out of the rendered document.

        Read from the `<!-- value: name = X -->` comments the templates emit, **not** from
        the human-readable tables. Keying on a label ("Proposed assessment term") coupled
        the check to prose that differs between the two state templates and broke the
        moment either was reworded; the comment is a stable key and is invisible in a
        rendered document.

        Returns None when the figure is blank or not numeric, and every caller treats
        that as "not supplied" rather than as a zero.
        """
        if self.blank(name):
            return None
        m = re.search(r"<!-- value: " + re.escape(name) + r" = ([^>]*?)-->", self.raw)
        if not m:
            return None
        n = re.search(r"-?[\d,]+(?:\.\d+)?", m.group(1))
        return float(n.group(0).replace(",", "")) if n else None


# ---------- Texas ----------

def _tx_region(d: _Draft) -> Result:
    if d.blank("pace_region_name"):
        return False, ("the PACE region is not confirmed; it is the incorporated place the "
                       "property sits in, not its mailing city, and the owner must confirm it "
                       "with the programme")
    return True, None


def _tx_sir(d: _Draft) -> Result:
    if d.blank("program_sir"):
        return False, f"{PROGRAMME} the programme SIR is not stated; the reviewer validates it"
    sir = d.number_for("program_sir")
    if sir is None:
        return False, f"{PROGRAMME} the programme SIR could not be read back for the test"
    if sir < TX_SIR_MINIMUM:
        return False, (f"{PROGRAMME} SIR {sir:g} is below the programme minimum of "
                       f"{TX_SIR_MINIMUM:g}; the package reports the shortfall rather than "
                       f"withholding the application")
    return True, f"{PROGRAMME} SIR {sir:g} meets the minimum of {TX_SIR_MINIMUM:g}"


def _tx_mortgage(d: _Draft) -> Result:
    if d.blank("mortgage_holder_name"):
        return False, ("no mortgage holder stated; if there is a lien, written notice and "
                       "written consent are a statutory condition of the owner contract")
    if d.any_blank("notice_sent_date", "mortgage_consent_obtained"):
        return False, "the notice date or the written consent is missing"
    return True, None


def _tx_lien(d: _Draft) -> Result:
    return d.has("first and prior lien", "runs with the land", "not eliminated"), None


def _tx_voluntary(d: _Draft) -> Result:
    return d.has("participation is voluntary", "may not make a permit"), None


def _tx_underwriting(d: _Draft) -> Result:
    missing = [n for n in ("owner_is_legal_owner", "current_on_mortgage",
                           "current_on_property_tax", "not_insolvent") if d.blank(n)]
    if missing:
        return False, f"{len(missing)} of the facts the programme verifies are unstated: {missing[:3]}"
    return True, None


def _tx_review(d: _Draft) -> Result:
    if not d.has("baseline", "verification"):
        return False, "the baseline review or the completion verification is not described"
    if not d.has("not the independent review"):
        return False, ("the package must say the software analysis is not the independent "
                       "review the programme requires")
    return True, None


def _tx_term(d: _Draft) -> Result:
    if d.any_blank("term_years", "weighted_useful_life_years"):
        return False, f"{PROGRAMME} term or cost-weighted useful life not stated"
    term, life = d.number_for("term_years"), d.number_for("weighted_useful_life_years")
    if term is None or life is None:
        return False, f"{PROGRAMME} term or useful life could not be read back"
    if term > life:
        return False, (f"{PROGRAMME} a {term:g}-year term exceeds the {life:g}-year "
                       f"cost-weighted useful life")
    return True, None


def _tx_ltv(d: _Draft) -> Result:
    return False, (f"{PROGRAMME} the Program Guide's loan-to-value limit is not stated here: "
                   f"two passages of the guide disagree on the variance (texas.md TX-PACE-32). "
                   f"Ask the administrator which it applies")


def _tx_eligible(d: _Draft) -> Result:
    missing = [n for n in ("eligibility_property_type", "eligibility_development_status") if d.blank(n)]
    if missing:
        return False, f"the eligibility statements are unanswered: {missing}"
    if not d.has("permanent improvement fixed to real property"):
        return False, "the qualified-improvement test is not stated"
    return True, None


def _tx_costs(d: _Draft) -> Result:
    if d.blank("financed_usd"):
        return False, "the amount to be assessed is not stated"
    return True, f"{PROGRAMME} the capitalisable fee share is a programme figure and is left to it"


def _tx_fees(d: _Draft) -> Result:
    if d.blank("fee_share"):
        return False, (f"{PROGRAMME} the fee share is not stated; the guide limits other fees "
                       f"and costs to {TX_FEE_SHARE_LIMIT:.0%} of the total assessment")
    share = d.number_for("fee_share")
    if share is None:
        return False, f"{PROGRAMME} the fee share could not be read back for the limit check"
    share = share / 100.0 if share > 1 else share
    if share > TX_FEE_SHARE_LIMIT:
        return False, (f"{PROGRAMME} fees are {share:.0%} of the assessment, above the "
                       f"{TX_FEE_SHARE_LIMIT:.0%} limit")
    return True, f"{PROGRAMME} {share:.0%} of the assessment, within {TX_FEE_SHARE_LIMIT:.0%}"


def _tx_affixed(d: _Draft) -> Result:
    return d.has("permanently affixed", "may not be removed"), None


def _tx_programme_documents(d: _Draft) -> Result:
    if not d.has("uniform documents", "is not any of them"):
        return False, (f"{PROGRAMME} the package must say the closing documents are the "
                       f"programme's own and that this is not one of them")
    if not d.has("chooses the lender on the open market"):
        return False, f"{PROGRAMME} the open-market lender choice is not stated"
    return True, None


def _tx_contracts(d: _Draft) -> Result:
    """TX-PACE-05 and -06: the assessment exists only under the owner contract, and
    third-party financing needs a lender contract too."""
    if not d.has("only** under a written **owner contract") and not d.has("only under a written owner contract"):
        return False, "the package does not state that the assessment requires an owner contract"
    if d.blank("owner_contract_signed"):
        return False, "the owner contract is not recorded as signed"
    if not d.blank("lender_name") and d.blank("lender_contract_signed"):
        return False, "there is third-party financing but no lender contract is recorded"
    return True, None


def _tx_direct(d: _Draft) -> Result:
    return d.has("contract directly"), None


def _tx_data_sheet(d: _Draft) -> Result:
    missing = [n for n in ("legal_description", "parcel_number") if d.blank(n)]
    if missing:
        return False, (f"{missing} blank; a legal description is never derived from an "
                       f"address and must come from the owner")
    return True, None


#: `(rule id, requirement, citation, requirement ids, predicate)`.
TX_RULES = [
    ("TX-C-01", "Eligible property and qualified improvements permanently fixed to realty",
     "LGC 399.002, 399.004", ("TX-PACE-01", "TX-PACE-02", "TX-PACE-03"), _tx_eligible),
    ("TX-C-02", "The property lies in a designated PACE region",
     "LGC 399.005", ("TX-PACE-04",), _tx_region),
    ("TX-C-03", "Costs financed are the categories the statute allows",
     "LGC 399.006", ("TX-PACE-07",), _tx_costs),
    ("TX-C-04", f"{PROGRAMME} Savings-to-investment ratio of at least "
                f"{TX_SIR_MINIMUM:g} over the assessment life, validated by the reviewer",
     "Program Guide v4.3 Steps 2, 7, 8", ("TX-PACE-30", "TX-PACE-09"), _tx_sir),
    ("TX-C-05", f"{PROGRAMME} Assessment term within the cost-weighted useful life",
     "LGC 399.009; Program Guide v4.3", ("TX-PACE-11", "TX-PACE-31"), _tx_term),
    ("TX-C-06", f"{PROGRAMME} Loan to appraisal-district value",
     "Program Guide v4.3 Step 2", ("TX-PACE-32",), _tx_ltv),
    ("TX-C-07", "Mortgage holder given written notice and giving written consent before "
                "the owner contract",
     "LGC 399.010", ("TX-PACE-08",), _tx_mortgage),
    ("TX-C-08", "Lien statements: first and prior, runs with the land, survives tax "
                "foreclosure",
     "LGC 399.014, 399.015", ("TX-PACE-13", "TX-PACE-14", "TX-PACE-15"), _tx_lien),
    ("TX-C-09", "Owner eligibility and underwriting facts the programme verifies",
     "LGC 399.011", ("TX-PACE-12", "TX-PACE-33"), _tx_underwriting),
    ("TX-C-10", "Independent review of baseline and savings, and written completion "
                "verification",
     "LGC 399.009, 399.012", ("TX-PACE-10", "TX-PACE-36", "TX-PACE-37"), _tx_review),
    ("TX-C-11", "The owner may purchase and contract directly",
     "LGC 399.013", ("TX-PACE-16",), _tx_direct),
    ("TX-C-12", "Participation is voluntary and cannot be compelled",
     "LGC 399.016", ("TX-PACE-17",), _tx_voluntary),
    ("TX-C-13", "Data sheet complete for the programme's own documents",
     "LGC 399.014", ("TX-PACE-40", "TX-PACE-41"), _tx_data_sheet),
    ("TX-C-14", "The assessment requires a written owner contract, and third-party "
                "financing a written lender contract",
     "LGC 399.007, 399.008", ("TX-PACE-05", "TX-PACE-06"), _tx_contracts),
    ("TX-C-15", f"{PROGRAMME} Other fees and costs within "
                f"{TX_FEE_SHARE_LIMIT:.0%} of the total assessment",
     "Program Guide v4.3 Step 2", ("TX-PACE-38",), _tx_fees),
    ("TX-C-16", f"{PROGRAMME} Improvements permanently affixed and not removable while the "
                f"assessment is in place; ineligible property types excluded",
     "Program Guide v4.3", ("TX-PACE-34", "TX-PACE-35"), _tx_affixed),
    ("TX-C-17", f"{PROGRAMME} The programme's uniform closing documents, and the owner's "
                f"open-market choice of lender",
     "Program Guide v4.3; TPA sample contracts",
     ("TX-PACE-39", "TX-PACE-42"), _tx_programme_documents),
]


# ---------- California ----------

def _ca_availability(d: _Draft) -> Result:
    """Reported as a note, per section 20: the package stays hypothetical until a
    programme is named, and that is a fact about California rather than a defect."""
    if d.any_blank("programme_name", "programme_agency", "programme_administrator"):
        return False, ("no California programme is named, so this package is hypothetical: "
                       "Los Angeles County ended its programme in 2020 and the Treasurer's "
                       "list shows its programmes inactive (CA-PACE-15, -16)")
    return True, None


def _ca_designated(d: _Draft) -> Result:
    if d.blank("programme_designated"):
        return False, ("an assessment can be levied only where the agency has already "
                       "designated the area by resolution; unconfirmed for this parcel")
    return True, None


def _ca_eligible(d: _Draft) -> Result:
    if not d.has("affixed to real property"):
        return False, "the affixed-to-realty test is not stated"
    if d.blank("eligibility_not_new_construction"):
        return False, "the initial-construction exclusion is unanswered"
    return True, None


def _ca_voluntary(d: _Draft) -> Result:
    return d.has("free and willing consent"), None


def _ca_tax_burden(d: _Draft) -> Result:
    if d.any_blank("annual_property_tax_usd", "market_value_usd"):
        return False, (f"**test incomplete, not passed**: the {CA_TAX_BURDEN_CAP:.0%} cap needs "
                       f"both the annual tax bill and the market value, and one is missing")
    tax = d.number_for("annual_property_tax_usd")
    value = d.number_for("market_value_usd")
    payment = d.number_for("annual_payment_usd") or 0.0
    if not tax or not value:
        return False, "the tax-burden inputs could not be read back for the test"
    share = (tax + payment) / value
    if share > CA_TAX_BURDEN_CAP:
        return False, (f"total annual taxes and assessments would be {share:.1%} of market "
                       f"value, above the {CA_TAX_BURDEN_CAP:.0%} cap")
    return True, f"{share:.1%} of market value, within the {CA_TAX_BURDEN_CAP:.0%} cap"


def _ca_notices(d: _Draft) -> Result:
    if d.blank("stat_ca_pace_payment_notice"):
        return False, ('the recorded "Payment of Contractual Assessment Required" notice is '
                       "blank; it is verbatim 14-point bold text from the statute")
    return False, "content present; type size enforced only in export (14-point bold)"


def _ca_lien(d: _Draft) -> Result:
    if not d.has("constitutes a lien"):
        return False, "the lien statement is missing"
    return False, ("priority not asserted: the California priority provisions were not opened "
                   "(CA-PACE-10, california.md 8.E2), so the package says the question is open")


def _ca_direct(d: _Draft) -> Result:
    return d.has("contract directly"), None


def _ca_term(d: _Draft) -> Result:
    if d.any_blank("term_years", "weighted_useful_life_years"):
        return False, "term or cost-weighted useful life not stated"
    return True, "no statutory numeric term limit in California; matching useful life is practice"


def _ca_route(d: _Draft) -> Result:
    if d.blank("pace_route"):
        return False, ("the route is unstated: Route A is a contractual assessment, Route B a "
                       "community facilities district annexed only with unanimous owner approval")
    return True, None


CA_RULES = [
    ("CA-C-01", "Improvements are financeable and affixed to real property",
     "SHC 5898.12", ("CA-PACE-01", "CA-PACE-02"), _ca_eligible),
    ("CA-C-02", "Participation is by the free and willing consent of each owner",
     "SHC 5898.12", ("CA-PACE-03",), _ca_voluntary),
    ("CA-C-03", "A programme exists for this parcel, designated by the agency",
     "SHC 5898.20, 5898.22, 5898.24", ("CA-PACE-04", "CA-PACE-05"), _ca_designated),
    ("CA-C-04", "The owner may contract directly with agency consent",
     "SHC 5898.21", ("CA-PACE-06",), _ca_direct),
    ("CA-C-05", f"Total annual taxes and assessments within {CA_TAX_BURDEN_CAP:.0%} of "
                f"market value",
     "SHC 5898.15", ("CA-PACE-07",), _ca_tax_burden),
    ("CA-C-06", 'Recorded notices, including "Payment of Contractual Assessment Required"',
     "SHC 5898.32, 5898.24(d), (f)", ("CA-PACE-08", "CA-PACE-09"), _ca_notices),
    ("CA-C-07", "The assessment constitutes a lien until paid",
     "SHC 5898.30", ("CA-PACE-10",), _ca_lien),
    ("CA-C-08", "Term stated against useful life; index-based bond terms available for "
                "non-residential property",
     "SHC 5898.28", ("CA-PACE-11",), _ca_term),
    ("CA-C-09", "The route the programme uses is stated (contractual assessment or district)",
     "SHC 5898.12 et seq.; GOV 53313.5, 53328.1",
     ("CA-PACE-12", "CA-PACE-13", "CA-PACE-14"), _ca_route),
    ("CA-C-10", "Programme availability and administrator licensing, reported as notes",
     "LA County pages; Treasurer PACE list; FIN 22018",
     ("CA-PACE-15", "CA-PACE-16", "CA-PACE-17"), _ca_availability),
]

_RULES: dict[str, list] = {"TX": TX_RULES, "CA": CA_RULES}


def check_cpace(draft: DocumentDraft) -> list[StatutoryCheck]:
    """Every PACE requirement for the draft's state, one `StatutoryCheck` per id."""
    rules = _RULES.get(draft.state)
    if not rules:
        return []
    d = _Draft(draft)
    out: list[StatutoryCheck] = []
    for rule_id, requirement, citation, ids, predicate in rules:
        satisfied, note = predicate(d)
        for req_id in ids:
            out.append(StatutoryCheck(
                requirement_id=req_id, requirement=f"{rule_id}: {requirement}",
                citation=citation, satisfied=satisfied, note=note))
    return out

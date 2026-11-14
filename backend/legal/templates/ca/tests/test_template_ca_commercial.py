"""Document 2, California: the commercial retrofit contract (L4) and its checks (L7).

Drafted from `specs/legal.md` section 16 (the 15-clause outline) and section 15 (the frame
shared by documents 2 to 6), with every statutory fact taken from the `CA-COM-*`, `CA-PAY-*`,
`CA-LIEN-*`, `CA-IND-*`, `CA-LIC-*` and `CA-ESIG-*` id tables of `specs/legal/california.md`.
The clause wording is this lane's own; no published form was copied, and no statute text is
written here - the one verbatim notice (BPC 7030(a), CA-COM-03) is a `stat_` placeholder.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.legal import api as legal
from backend.legal.checks import commercial
from backend.legal.engine import engine
from backend.schema import DocumentRequest, RunResult

SPEC = Path(__file__).resolve().parents[5] / "specs"
TEMPLATE = Path(__file__).resolve().parents[1] / "retrofit_contract_commercial.md"
KEY = ("retrofit_contract_commercial", "CA")


@pytest.fixture(scope="module")
def template():
    return engine.load_template(TEMPLATE.read_text())


@pytest.fixture(scope="module")
def draft():
    legal._registry.cache_clear()
    run = RunResult.model_validate_json((SPEC / "examples" / "office" / "run_result.json").read_text())
    return legal.fill_template(
        DocumentRequest(run_id="run_x", doc_type=KEY[0], state=KEY[1],
                        measure_ids=["ENV_ATTIC"], fields={}), run)


# ---------- the template itself ----------

def test_the_header_declares_a_commercial_only_document(template):
    assert template.doc_type == KEY[0] and template.state == KEY[1]
    assert template.segments == ("commercial",), \
        "a dwelling unit is a home improvement and routes to document 1 (california.md 3.1)"


def test_no_statutory_placeholder_is_optional(template):
    """**The bug this test exists for.** `stat_ca_cslb_notice_commercial` was in the
    `optional:` list, so the mandatory 10-point CSLB notice resolved to an empty string
    instead of a visible blank - and the CA-COM-03 check then read the silence as
    "content present". A required notice must never be optional in any template."""
    optional_stats = [n for n in template.optional if n.startswith("stat_")]
    assert not optional_stats, f"statutory text may not be optional: {optional_stats}"


def test_every_optional_name_is_a_placeholder_in_the_body(template):
    names = set(engine.placeholders_in(template.body))
    assert set(template.optional) <= names, \
        f"declared optional but not used: {set(template.optional) - names}"


def test_the_clause_comments_cite_ids_that_exist_in_the_state_file():
    """Section 21 of `specs/legal.md` promises every cited id is matched against the state
    file. This repeats it for the ids this template claims, so a renamed id fails here
    rather than leaving a clause citing nothing."""
    import re

    state_file = (SPEC / "legal" / "california.md").read_text()
    cited = set(re.findall(r"CA-[A-Z]+-\d+[a-z]?", TEMPLATE.read_text()))
    assert cited, "the template cites no ids"
    missing = sorted(i for i in cited if f"| {i} " not in state_file and f"`{i}`" not in state_file)
    assert not missing, f"cited but not in california.md: {missing}"


def test_the_statutory_numbers_match_the_state_file():
    """The figures are the ones california.md states: 30 days and 150 per cent (CIV 8800),
    a 5 per cent retention cap (CIV 8811), 45 and 10 days for release (CIV 8812, 8814),
    7 days to subcontractors (BPC 7108.5), 2 per cent per month throughout, 20-day
    preliminary notices and a 10-day mailing (CIV 8200-8204, 8190)."""
    body = TEMPLATE.read_text()
    for number in ("30 days", "150 per cent", "45 days", "10 days", "7 days",
                   "2 per cent per month", "20 days", "four years"):
        assert number in body, f"{number} is not stated"
    assert commercial.RETENTION_CAP_PERCENT == 5.0


def test_no_party_or_licence_number_is_invented(draft):
    """`specs/legal.md` 1.1: a party name, licence number, party address or legal
    description has no binding and can only come from the request's fields."""
    for name in ("owner_names", "contractor_name", "contractor_license_number",
                 "contractor_business_address", "legal_description"):
        assert name in draft.unfilled_placeholders, f"{name} was filled from somewhere"


def test_the_lender_space_is_printed_even_with_no_lender(draft):
    """CA-COM-11: unlike a home improvement contract, the construction lender space is
    required. It is printed as a blank rather than omitted when there is no lender."""
    assert "construction_lender_name" in draft.unfilled_placeholders
    assert "Construction lender" in draft.markdown


def test_the_notice_is_top_and_bottom(draft):
    assert draft.markdown.count("NOT LEGAL ADVICE") >= 2
    assert "California" in draft.disclaimer


def test_savings_are_not_warranted_by_this_contract(draft):
    """Section 16 outline row 12, and the reason document 5 exists separately."""
    assert "does not warrant any level of energy saving" in draft.markdown


def test_the_analysis_is_owner_furnished_not_engineered_design(draft):
    """Outline row 11. The plan comes from software, and the contract has to say so, or
    the contractor inherits design liability for it."""
    assert "owner-furnished" in draft.markdown
    assert "not engineered design" in draft.markdown or "not a design prepared" in draft.markdown


# ---------- the checks ----------

def test_every_com_id_of_section_16_has_a_check(draft):
    """Section 16 lists the California ids this document must be checked against:
    CA-COM-01 to -12."""
    checked = {c.requirement_id for c in legal.check_document(draft)}
    for n in range(1, 13):
        assert f"CA-COM-{n:02d}" in checked, f"CA-COM-{n:02d} has no check"


def test_the_unfilled_draft_fails_honestly(draft):
    checks = legal.check_document(draft)
    assert checks, "the commercial predicates did not run"
    assert any(not c.satisfied for c in checks)
    cslb = next(c for c in checks if c.requirement_id == "CA-COM-03")
    assert not cslb.satisfied and "blank" in (cslb.note or "")


def test_a_licence_check_says_software_cannot_confirm_it(draft):
    """Not a failure of the draft: whether a licence is current and correctly classified
    is a CSLB lookup. Reporting it as satisfied would be the lie."""
    note = next(c for c in legal.check_document(draft) if c.requirement_id == "CA-COM-01").note
    assert "cannot verify" in (note or "")


def test_retention_over_the_cap_is_caught():
    """CIV 8811 caps retention at 5 per cent for a contract entered on or after
    2026-01-01, and section 16 says `retention_percent` must be validated against it."""
    legal._registry.cache_clear()
    run = RunResult.model_validate_json((SPEC / "examples" / "office" / "run_result.json").read_text())

    def check_with(percent):
        d = legal.fill_template(
            DocumentRequest(run_id="r", doc_type=KEY[0], state=KEY[1],
                            measure_ids=["ENV_ATTIC"], fields={"retention_percent": percent}), run)
        return next(c for c in legal.check_document(d) if c.requirement_id == "CA-COM-05")

    assert check_with("5").satisfied is True
    over = check_with("10")
    assert over.satisfied is False and "exceeds" in (over.note or "")


def test_the_lab_2810_items_are_all_carried(draft):
    """CA-COM-12: presence of the items is what earns the owner the rebuttable
    presumption; LAB 2810 allows an estimate where a number is not yet known. So the
    document must carry every item even while the values are blank."""
    body = draft.markdown
    for name in commercial._LAB_2810_ITEMS:
        assert name in body or name.replace("_", " ") in body.lower(), f"{name} is not in the document"
    note = next(c for c in legal.check_document(draft) if c.requirement_id == "CA-COM-12").note
    assert "blank does not earn the presumption" in (note or "")


def test_a_residential_request_does_not_reach_these_checks():
    """Dispatch guard: the commercial predicates must not run on document 1, whose own
    30 CA-R-* predicates are a different list."""
    legal._registry.cache_clear()
    run = RunResult.model_validate_json((SPEC / "examples" / "house" / "run_result.json").read_text())
    d = legal.fill_template(
        DocumentRequest(run_id="r", doc_type="retrofit_contract_residential", state="CA",
                        measure_ids=["ENV_ATTIC"], fields={}), run)
    ids = {c.requirement_id for c in legal.check_document(d)}
    assert not any(i.startswith("CA-COM-") for i in ids)
    assert len(legal.check_document(d)) >= 30

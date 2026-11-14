"""The Texas residential retrofit contract (L5): structure, regimes, and checks against legal.md Part B."""
import re
from pathlib import Path

import pytest

from backend.legal.checks import _tx_data, checks, texas
from backend.legal.engine import engine
from backend.schema import DocumentRequest, RunResult

ROOT = Path(__file__).resolve().parents[5]
EX = ROOT / "specs" / "examples"
SPEC = (ROOT / "specs" / "legal.md").read_text()
TEXAS_MD = (ROOT / "specs" / "legal" / "texas.md").read_text()
TEMPLATE = Path(__file__).resolve().parents[1] / "retrofit_contract_residential.md"


REGISTRY = engine.load_templates(ROOT / "backend" / "legal" / "templates")


def run(role="owner_occupier"):
    r = RunResult.model_validate_json((EX / "office_houston" / "run_result.json").read_text())
    return r.model_copy(update={"request": r.request.model_copy(update={"role": role})})


def draft(measures=("HVAC_HP", "LGT_LED"), role="owner_occupier", **fields):
    req = DocumentRequest(run_id="r", doc_type="retrofit_contract_residential", state="TX",
                          measure_ids=list(measures), fields=fields)
    d = engine.fill_template(req, run(role), None, REGISTRY[("retrofit_contract_residential", "TX")])
    return d.model_copy(update={"statutory_checks": checks.check_document(d)})


def by_rule(d):
    out = {}
    for c in d.statutory_checks:
        out.setdefault(c.requirement.split(":")[0], []).append(c)
    return out


def test_the_texas_template_is_registered_and_offered():
    assert ("retrofit_contract_residential", "TX") in REGISTRY
    assert engine.list_templates(REGISTRY, "TX", "residential") == ["retrofit_contract_residential"]
    # Not `== []`: L6 added the Texas C-PACE package, which is commercial-only. What
    # matters for document 1T is that a *residential* contract is never offered to a
    # commercial property, not that nothing else is.
    assert "retrofit_contract_residential" not in engine.list_templates(REGISTRY, "TX", "commercial")


def test_every_cited_id_exists_in_texas_md():
    cited = set(re.findall(r"TX-(?:RC|ALL)-[0-9A-Z]{2}", TEMPLATE.read_text()))
    known = set(re.findall(r"^\| (TX-[A-Z]+-[0-9A-Z]+) \|", TEXAS_MD, re.M))
    assert cited and cited <= known
    assert {i for _, _, ids in _tx_data.RULES for i in ids if i.startswith("TX-")} - {"TX-R-83"} <= known


def test_every_rule_of_section_12_2_has_a_predicate_and_an_id():
    rows = re.findall(r"^\| (TX-R-\d\d) \|", SPEC, re.M)
    assert rows == [r[0] for r in _tx_data.RULES] and set(rows) == set(texas.PREDICATES)
    assert len(rows) == 33


def test_no_statute_text_is_written_into_the_template_or_the_engine():
    """stat_ names stay blanks until a texas.md anchor loads them; they are never optional."""
    text = TEMPLATE.read_text()
    optional = re.search(r"<!-- optional: (.*?) -->", text).group(1)
    assert "stat_" not in optional
    d = draft()
    assert {"stat_tx_homestead_warning", "stat_tx_rcla_notice"} <= set(d.unfilled_placeholders)
    for banned in ("NOTICE OF CANCELLATION", "Regulated by The Texas Department of Licensing"):
        assert banned not in d.markdown.replace("[[BLANK", "")


def test_a_homeowner_gets_all_four_regimes_and_their_blocks():
    d = draft(owner_married="yes")
    assert "homestead=on; residence=on; solicitation=on; rcla=on" in d.markdown
    for needle in ("Owner's right to rescind (homestead)", "Schedule D: Subcontractor and supplier list",
                   "disbursement statement", "construction account", "stat_tx_cancel_statement", "Harris County",
                   "These are two separate rights"):
        assert needle in d.markdown, needle
    assert "joins in this contract" in d.markdown


def test_a_landlord_has_no_homestead_and_no_residence_regime():
    d = draft(role="landlord")
    assert "homestead=off; residence=off" in d.markdown
    assert "stat_tx_homestead_warning" not in d.markdown and "Schedule D: Subcontractor" not in d.markdown
    assert "rescind" not in d.markdown.lower().replace("rescission", "")
    assert "Owner may cancel this transaction until midnight of the third business day" in d.markdown


def test_a_consumer_initiated_hvac_only_job_has_no_home_solicitation():
    d = draft(measures=("HVAC_HP",), consumer_initiated="yes")
    assert "solicitation=off" in d.markdown and "stat_tx_cancel_statement" not in d.markdown
    d2 = draft(measures=("HVAC_HP", "ENV_ATTIC"), consumer_initiated="yes")      # unlicensed envelope work: still on
    assert "solicitation=on" in d2.markdown


def test_trades_decide_which_tdlr_statements_appear():
    only_envelope = draft(measures=("ENV_ATTIC",))
    assert "trades=none" in only_envelope.markdown and "stat_tx_tdlr" not in only_envelope.markdown
    hvac = draft(measures=("HVAC_HP",))
    assert "stat_tx_tdlr_acr_statement" in hvac.markdown and "stat_tx_tdlr_electrical_statement" not in hvac.markdown


def test_the_cancellation_dates_are_computed_and_marked_check_before_signing():
    d = draft(contract_date="2026-12-01")       # a Tuesday
    assert "2026-12-04 (check before signing" in d.markdown          # third business day, Mon to Sat
    assert "2026-12-04" in d.markdown and "(check before signing: T5)" in d.markdown


def test_the_checklist_reports_blanks_and_procedural_steps_honestly():
    rules = by_rule(draft(owner_married="yes"))
    assert not rules["TX-R-83"][0].satisfied and "stat_tx_" in rules["TX-R-83"][0].note
    assert not rules["TX-R-04"][0].satisfied and "U-01" in rules["TX-R-04"][0].note
    assert not rules["TX-R-16"][0].satisfied and not rules["TX-R-18"][0].satisfied
    assert not rules["TX-R-20"][0].satisfied and "T6" in rules["TX-R-20"][0].note
    assert not rules["TX-R-17"][0].satisfied and not rules["TX-R-30"][0].satisfied      # blank statutory text
    for rid in ("TX-R-25", "TX-R-26", "TX-R-48", "TX-R-64", "TX-R-81", "TX-R-82"):
        assert all(c.satisfied for c in rules[rid]) or rid in ("TX-R-64",), rid


def test_regimes_that_are_off_are_not_applicable_not_failures():
    rules = by_rule(draft(role="landlord", measures=("ENV_ATTIC",)))
    for rid in ("TX-R-13", "TX-R-17", "TX-R-20", "TX-R-22"):
        assert rules[rid][0].satisfied and rules[rid][0].note.startswith("not applicable")


def test_the_payment_period_limit_is_read_from_the_clause():
    assert all(c.satisfied for c in by_rule(draft())["TX-R-42"])
    assert not all(c.satisfied for c in by_rule(draft(payment_due_days="75"))["TX-R-42"])


def test_homestead_with_the_marital_status_missing_fails_the_spouse_rule():
    assert not by_rule(draft())["TX-R-10"][0].satisfied
    assert "owner_married not given" in by_rule(draft())["TX-R-10"][0].note
    assert by_rule(draft(owner_married="no"))["TX-R-10"][0].satisfied


def test_every_check_carries_a_citation_from_texas_md():
    d = draft(owner_married="yes")
    assert len(d.statutory_checks) >= 55
    assert all(c.citation for c in d.statutory_checks if c.requirement_id.startswith("TX-"))

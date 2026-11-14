"""The legal door (workplan 3.3), wired to the real engine, template and checks.

These tests replace two that asserted the **stub's** behaviour - that
`list_templates` returned a hardcoded six and that `fill_template` round-tripped the
fixture. Keeping them would have pinned the echo in place, which is how the L0 stub
survived L1, L2 and L3 all landing.

What the door may and may not do, from `specs/legal.md` 1.1 and SPEC 15 step 7:

- a party name, licence number, party address or legal description has **no binding**
  and can only come from `DocumentRequest.fields`; the draft shows a visible blank
  otherwise, and lists it;
- `stat_` placeholders are filled only from verbatim statute text, and there is no
  loader for `specs/legal/*.md`, so today they are blanks and the `CA-R-*` predicates
  report them unsatisfied. **That is the designed behaviour**: SPEC 15 step 7 asks to
  show "the filled terms, the blanks, and the statutory checklist". Nobody pastes
  statute text in to make a check pass;
- a document type with no template file is **refused**, not faked.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.legal import api
from backend.legal.engine import engine
from backend.schema import DocumentDraft, DocumentRequest, RunResult, StatutoryCheck

EX = Path(__file__).resolve().parents[3] / "specs" / "examples"

#: The template these tests draft from. Which templates exist changes as L4 to L6 land,
#: so what is *offered* is asserted against the registry rather than a literal list - an
#: earlier version of this file said `list_templates("TX") == []` and went red the moment
#: L5 added the Texas residential contract.
ONLY_TEMPLATE = ("retrofit_contract_residential", "CA")


def _request(doc_type: str, state: str, fields: dict | None = None) -> DocumentRequest:
    return DocumentRequest(run_id="run_x", doc_type=doc_type, state=state,
                           measure_ids=["ENV_ATTIC"], fields=fields or {})


def _run(flavor: str = "house") -> RunResult:
    return RunResult.model_validate_json((EX / flavor / "run_result.json").read_text())


# ---------- what is offered ----------

def test_only_documents_with_a_template_are_offered():
    """The stub advertised six `DocType`s from a hardcoded tuple while one template file
    existed, so the agent could ask for `bid_package_rfp` and be handed the house
    fixture relabelled. What is offered now tracks the files on disk - asserted against
    the registry, so a template landing is offered without editing this test, and one
    that is not on disk can never be offered, which is the property that matters."""
    on_disk = set(api._registry())
    assert on_disk, "no templates loaded at all"
    for state in ("CA", "TX"):
        offered = api.list_templates(state)
        assert set(offered) == {t for t, s in on_disk if s == state}
        assert len(offered) == len(set(offered)), "a doc type listed twice"


def test_the_segment_decides_which_contract_is_offered():
    """A dwelling unit is a home improvement and uses document 1; an office is not
    (`california.md` 3.1). So a residential contract is never offered to a commercial
    property."""
    residential = api.list_templates("CA", "residential")
    assert "retrofit_contract_residential" in residential
    assert "retrofit_contract_residential" not in api.list_templates("CA", "commercial")


def test_nothing_is_offered_that_has_no_template_file():
    """The guard that keeps this true as L4 to L6 land: whatever is offered must be
    loadable. A name in a list with no file behind it is the stub's bug."""
    for state in ("CA", "TX"):
        for doc_type in api.list_templates(state):
            assert api._registry().get((doc_type, state)) is not None


def test_a_request_with_no_template_is_refused_rather_than_faked():
    for doc_type in ("cpace_package", "bid_package_rfp", "solar_installation_agreement"):
        with pytest.raises(LookupError) as caught:
            api.fill_template(_request(doc_type, "CA"), _run())
        assert doc_type in str(caught.value)


# ---------- what a draft is ----------

def test_a_draft_is_built_from_the_template_not_the_fixture():
    draft = api.fill_template(_request(*ONLY_TEMPLATE), _run())
    DocumentDraft.model_validate(json.loads(draft.model_dump_json()))

    fixture = json.loads((EX / "house" / "document_draft.json").read_text())
    assert draft.markdown != fixture["markdown"], "still the relabelled fixture"
    assert "California" in draft.disclaimer, "the notice names the state"
    assert draft.doc_type == "retrofit_contract_residential" and draft.state == "CA"


def test_the_blanks_are_visible_and_listed():
    """A blank is the honest output for a party name: the engine has no binding for one,
    and inventing it is the single thing a drafting tool must never do."""
    draft = api.fill_template(_request(*ONLY_TEMPLATE), _run())
    assert draft.unfilled_placeholders, "a draft with no fields filled nothing in"
    assert any(n.startswith("stat_") for n in draft.unfilled_placeholders), \
        "statute text has no loader, so those must appear as blanks"
    for name in draft.unfilled_placeholders:
        assert f"[[BLANK: {name}" in draft.markdown, f"{name} is listed but not visible"


def test_a_supplied_field_is_used_and_stops_being_a_blank():
    plain = api.fill_template(_request(*ONLY_TEMPLATE), _run())
    name = next(n for n in plain.unfilled_placeholders if not n.startswith("stat_"))

    filled = api.fill_template(_request(*ONLY_TEMPLATE, fields={name: "Acme Retrofit LLC"}),
                               _run())
    assert name not in filled.unfilled_placeholders
    assert "Acme Retrofit LLC" in filled.markdown
    assert f"[[BLANK: {name}" not in filled.markdown


def test_the_draft_is_deterministic():
    """The same request twice gives the same document; a demo that re-drafts must not
    produce a different contract."""
    a = api.fill_template(_request(*ONLY_TEMPLATE), _run())
    b = api.fill_template(_request(*ONLY_TEMPLATE), _run())
    assert a.markdown == b.markdown and a.unfilled_placeholders == b.unfilled_placeholders


# ---------- what the checks are ----------

def test_checks_run_the_predicates_rather_than_echoing_the_draft():
    """`check_document` was `return list(draft.statutory_checks)`, so it reported whatever
    the fixture happened to carry - including on a draft that had never been checked."""
    draft = api.fill_template(_request(*ONLY_TEMPLATE), _run())
    emptied = draft.model_copy(update={"statutory_checks": []})

    checks = api.check_document(emptied)
    assert len(checks) >= 30, f"the CA-R-* predicates did not run ({len(checks)} checks)"
    assert all(isinstance(c, StatutoryCheck) for c in checks)
    assert any(not c.satisfied for c in checks), \
        "unfilled statutory text must fail honestly, not be reported as satisfied"


def test_an_unchecked_document_type_returns_nothing_rather_than_a_pass():
    """L7 adds predicates for the other documents. Until then `[]` means "not checked",
    and it must not be presented as "no problems found"."""
    draft = api.fill_template(_request(*ONLY_TEMPLATE), _run())
    other = draft.model_copy(update={"doc_type": "energy_savings_guarantee"})
    assert api.check_document(other) == []


def test_the_notice_is_on_every_draft():
    draft = api.fill_template(_request(*ONLY_TEMPLATE), _run())
    assert "NOT LEGAL ADVICE" in draft.disclaimer
    assert engine.DISCLAIMER.split("{")[0] in draft.disclaimer


# ---------- the door's own contract ----------

def test_the_registry_is_read_once():
    import time

    api._registry()
    t0 = time.time()
    api._registry()
    assert time.time() - t0 < 0.005, "the template directory is re-read on every call"


def test_the_run_the_document_belongs_to_is_carried_through():
    """The draft's id ties it to the run, so a document in the UI can be traced back to
    the analysis it was drafted from."""
    draft = api.fill_template(_request(*ONLY_TEMPLATE), _run())
    assert "run_x" in draft.doc_id

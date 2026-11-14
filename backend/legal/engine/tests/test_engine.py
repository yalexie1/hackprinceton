import json
from pathlib import Path

import pytest

from backend.legal.engine import (DISCLAIMER, fill_template, list_templates, load_template,
                                  load_templates, placeholders_in)
from backend.schema import DocumentRequest, PropertyBundle, RunResult

EX = Path(__file__).resolve().parents[4] / "specs" / "examples" / "house"
RUN = RunResult.model_validate_json((EX / "run_result.json").read_text())
BUNDLE = PropertyBundle.model_validate_json((EX / "property_bundle.json").read_text())

TEMPLATE = load_template(
    "<!-- doc: retrofit_contract_residential / CA / template v0.1 -->\n"
    "<!-- optional: salesperson_block -->\n"
    "Work at {{property_address}}, {{property_city}}. {{salesperson_block}}\n"
    "Owner: {{owner_names}}. Licence {{contractor_license_number}}.\n")


def request(**fields):
    return DocumentRequest(run_id=RUN.run_id, doc_type="retrofit_contract_residential",
                           state="CA", measure_ids=[], fields=fields)


def fill(req, **kw):
    return fill_template(req, RUN, BUNDLE, TEMPLATE, **kw)


def test_bound_placeholder_filled_from_run():
    d = fill(request())
    assert RUN.property.address in d.markdown and RUN.property.city in d.markdown
    assert "property_address" not in d.unfilled_placeholders


def test_unbound_placeholder_is_visible_blank_and_listed():
    d = fill(request())
    assert d.unfilled_placeholders == ["owner_names", "contractor_license_number"]
    assert "[[BLANK: owner_names, value required]]" in d.markdown
    assert "salesperson_block" not in d.unfilled_placeholders    # optional and absent


def test_request_field_wins_over_derived():
    d = fill(request(property_city="Elsewhere", owner_names="A. Owner"))
    assert f"Work at {RUN.property.address}, Elsewhere." in d.markdown
    assert "A. Owner" in d.markdown and "owner_names" not in d.unfilled_placeholders


def test_no_party_name_invented():
    costar_owner = BUNDLE.costar.owner_name if BUNDLE.costar and hasattr(BUNDLE.costar, "owner_name") else None
    d = fill(request())
    assert "[[BLANK: owner_names" in d.markdown
    if costar_owner:
        assert costar_owner not in d.markdown


def test_notice_always_present_top_and_bottom():
    d = fill(request())
    notice = DISCLAIMER.format(state_name="California")
    assert d.disclaimer == notice
    assert d.markdown.startswith("> " + notice) and d.markdown.rstrip().endswith(notice)


def test_stat_placeholder_blank_or_verbatim():
    t = load_template("<!-- doc: retrofit_contract_residential / CA / template v0.1 -->\n{{stat_ca_x}}\n")
    d = fill_template(request(), RUN, BUNDLE, t)
    assert "[[BLANK: stat_ca_x, insert verbatim statutory text]]" in d.markdown
    d2 = fill_template(request(), RUN, BUNDLE, t, statutory={"stat_ca_x": "WORDS"})
    assert "WORDS" in d2.markdown and d2.unfilled_placeholders == []


def test_deterministic_and_validates():
    a, b = fill(request(owner_names="X")), fill(request(owner_names="X"))
    assert a == b
    from backend.schema import DocumentDraft
    DocumentDraft.model_validate(json.loads(a.model_dump_json()))


def test_mismatch_and_bad_header_rejected():
    with pytest.raises(ValueError):
        fill_template(request(), RUN, BUNDLE, load_template(
            "<!-- doc: retrofit_contract_residential / TX / template v0.1 -->\nx"))
    with pytest.raises(ValueError):
        load_template("no header")


def test_registry_and_list_templates(tmp_path):
    (tmp_path / "a.md").write_text(TEMPLATE.body)
    reg = load_templates(tmp_path)
    assert list_templates(reg, "CA", "residential") == ["retrofit_contract_residential"]
    assert list_templates(reg, "TX") == []
    assert placeholders_in(TEMPLATE.body)[0] == "property_address"

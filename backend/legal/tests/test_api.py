import json
from pathlib import Path

import pytest

from backend.legal import api
from backend.schema import DocumentDraft, DocumentRequest, RunResult, StatutoryCheck

EX = Path(__file__).resolve().parents[3] / "specs" / "examples"


def _load(flavor, name):
    return (EX / flavor / name).read_text()


def test_list_templates():
    assert "cpace_package" not in api.list_templates("TX", "residential")
    assert "cpace_package" in api.list_templates("CA", "commercial")


@pytest.mark.parametrize("flavor", ["house", "office"])
def test_fill_and_check(flavor):
    req = DocumentRequest.model_validate_json(_load(flavor, "document_request.json"))
    run = RunResult.model_validate_json(_load(flavor, "run_result.json"))
    draft = api.fill_template(req, run)
    DocumentDraft.model_validate(json.loads(draft.model_dump_json()))
    assert draft.doc_type == req.doc_type and draft.state == req.state
    checks = api.check_document(draft)
    assert checks and all(isinstance(c, StatutoryCheck) for c in checks)
    assert api.fill_template(req, run) == draft

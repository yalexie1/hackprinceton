import asyncio
import json
from pathlib import Path

import pytest

from backend.agent import api
from backend.schema import DocumentDraft, DocumentRequest, RunEvent, RunRequest, RunResult

EX = Path(__file__).resolve().parents[3] / "specs" / "examples"


@pytest.mark.parametrize("flavor", ["house", "office"])
def test_start_stream_get(flavor):
    req = RunRequest.model_validate_json((EX / flavor / "run_request.json").read_text())
    run_id = api.start_run(req)

    async def collect():
        return [e async for e in api.stream_events(run_id)]

    events = asyncio.run(collect())
    expected = json.loads((EX / flavor / "run_events.json").read_text())
    assert [e.model_dump(mode="json") for e in events] == [RunEvent.model_validate(e).model_dump(mode="json") for e in expected]
    assert events[-1].type == "done"
    result = api.get_run(run_id)
    RunResult.model_validate(result.model_dump(mode="json"))
    assert result.run_id == run_id and result.request.sid == req.sid


def test_unknown_run_raises():
    with pytest.raises(KeyError):
        api.get_run("nope")


def test_answer_update_and_documents():
    req = RunRequest.model_validate_json((EX / "house" / "run_request.json").read_text())
    run_id = api.start_run(req)
    api.answer(run_id, "q1", "yes")
    api.update_run(run_id, budget_usd=1234.0, overrides={"occupancy.count": 5.0})
    assert api.get_run(run_id).request.budget_usd == 1234.0
    dreq = DocumentRequest.model_validate_json((EX / "house" / "document_request.json").read_text())
    dreq.run_id = run_id
    draft = api.draft_document(dreq)
    DocumentDraft.model_validate(draft.model_dump(mode="json"))
    assert api.get_document(run_id, draft.doc_id) == draft
    with pytest.raises(KeyError):
        api.get_document(run_id, "missing")

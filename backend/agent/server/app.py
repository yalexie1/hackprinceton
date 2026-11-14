"""FastAPI app for SPEC 10. G7 skeleton: every route answers from the G0 run door
(which replays fixtures) and from specs/examples/search_results.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.agent import api
from backend.schema import (SCHEMA_VERSION, DocumentDraft, DocumentRequest, PropertySummary,
                            RunRequest, RunResult)

_SEARCH = Path(__file__).resolve().parents[3] / "specs" / "examples" / "search_results.json"

_CODES = {400: "bad_request", 404: "not_found", 422: "invalid_request"}


class AnswerBody(BaseModel):
    question_id: str
    value: Union[float, str, bool, None] = None


class PatchBody(BaseModel):
    budget_usd: Optional[float] = None
    overrides: Optional[dict[str, Union[float, str, bool]]] = None


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def _summaries() -> list[PropertySummary]:
    return [PropertySummary.model_validate(p) for p in json.loads(_SEARCH.read_text())]


def create_app() -> FastAPI:
    app = FastAPI(title="Energy consultant API")

    def envelope(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return envelope(exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return envelope(exc.status_code, _CODES.get(exc.status_code, "error"), str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        return envelope(422, "invalid_request", "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))

    def run_of(run_id: str) -> RunResult:
        try:
            return api.get_run(run_id)
        except KeyError:
            raise ApiError(404, "run_not_found", f"unknown run_id: {run_id}")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "schema_version": SCHEMA_VERSION}

    @app.get("/api/properties/search", response_model=list[PropertySummary])
    def search(q: str = "", segment: Optional[str] = None, use_type: Optional[str] = None,
               lat: Optional[float] = None, lon: Optional[float] = None,
               radius_m: Optional[float] = None, limit: int = 20):
        needle = q.lower()
        hits = [p for p in _summaries()
                if (not needle or needle in f"{p.name} {p.address}".lower())
                and (segment is None or p.segment == segment)
                and (use_type is None or p.use_type == use_type)]
        return hits[:max(limit, 0)]

    @app.get("/api/properties/{sid}", response_model=PropertySummary)
    def property_by_sid(sid: str):
        for p in _summaries():
            if p.sid == sid:
                return p
        raise ApiError(404, "property_not_found", f"unknown sid: {sid}")

    @app.post("/api/runs")
    def create_run(request: RunRequest):
        return {"run_id": api.start_run(request)}

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str):
        run_of(run_id)

        async def sse():
            async for event in api.stream_events(run_id):
                yield f"data: {event.model_dump_json()}\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    @app.get("/api/runs/{run_id}", response_model=RunResult)
    def get_run(run_id: str):
        return run_of(run_id)

    @app.post("/api/runs/{run_id}/answers")
    def post_answer(run_id: str, body: AnswerBody):
        run_of(run_id)
        api.answer(run_id, body.question_id, body.value)
        return {"ok": True}

    @app.patch("/api/runs/{run_id}")
    def patch_run(run_id: str, body: PatchBody):
        run_of(run_id)
        api.update_run(run_id, body.budget_usd, body.overrides)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/documents", response_model=DocumentDraft)
    def create_document(run_id: str, request: DocumentRequest):
        run_of(run_id)
        if request.run_id != run_id:
            raise ApiError(400, "run_id_mismatch", "body run_id differs from the path")
        return api.draft_document(request)

    @app.get("/api/runs/{run_id}/documents/{doc_id}", response_model=DocumentDraft)
    def get_document(run_id: str, doc_id: str):
        run_of(run_id)
        try:
            return api.get_document(run_id, doc_id)
        except KeyError:
            raise ApiError(404, "document_not_found", f"unknown doc_id: {doc_id}")

    @app.get("/api/assets/{path:path}")
    def get_asset(path: str):
        # No assets exist before the Data lane's get_asset door is live.
        raise ApiError(404, "asset_not_found", f"no asset at {path}")

    return app

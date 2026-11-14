"""FastAPI app for SPEC 10. Run and document routes answer from the run door
(backend/agent/api.py); search, property and asset routes from the data door."""
from __future__ import annotations

import mimetypes
from typing import Literal, Optional, Union

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.agent import api
from backend.agent.roof import PropertyPreview, RoofView
from backend.agent.runtime.replan import PatchError
from backend.data_layer import api as data
from backend.schema import (SCHEMA_VERSION, DocType, DocumentDraft, DocumentRequest, PropertySummary,
                            RunRequest, RunResult, Segment, UseType)

_CODES = {400: "bad_request", 404: "not_found", 409: "conflict", 422: "invalid_request"}


class AnswerBody(BaseModel):
    question_id: str
    value: Union[float, str, bool, None] = None


class PatchBody(BaseModel):
    budget_usd: Optional[float] = Field(default=None, ge=0)
    overrides: Optional[dict[str, Union[float, str, bool]]] = None


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


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

    @app.get("/api/templates", response_model=list[DocType])
    def templates(state: Optional[Literal["CA", "TX"]] = None, segment: Optional[Segment] = None):
        """The document types that can actually be drafted (read-only; the legal door's `list_templates`).
        A client offers only these; a request for anything else is a 404 template_not_available."""
        from backend.legal import api as legal
        return legal.list_templates(state, segment)

    @app.get("/api/properties/search", response_model=list[PropertySummary])
    def search(q: Optional[str] = None, segment: Optional[Segment] = None,
               use_type: Optional[UseType] = None, lat: Optional[float] = None,
               lon: Optional[float] = None, radius_m: Optional[float] = None,
               limit: int = 20):
        return data.search_properties(q=q, segment=segment, use_type=use_type, lat=lat,
                                      lon=lon, radius_m=radius_m, limit=limit)

    @app.get("/api/properties/{sid}", response_model=PropertySummary)
    def property_by_sid(sid: str):
        try:
            return data.get_property_summary(sid)
        except LookupError:
            raise ApiError(404, "property_not_found", f"unknown sid: {sid}")

    @app.get("/api/properties/{sid}/preview", response_model=PropertyPreview)
    def property_preview(sid: str):
        try:
            data.get_property_summary(sid)
        except LookupError:
            raise ApiError(404, "property_not_found", f"unknown sid: {sid}")
        return api.get_preview(sid)

    @app.post("/api/runs")
    def create_run(request: RunRequest):
        from backend.agent.live import LiveDataUnavailable
        try:
            return {"run_id": api.start_run(request)}
        except LiveDataUnavailable as err:        # loud and early: never a quiet fall back to the example
            raise ApiError(503, "live_data_unavailable", str(err))

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
        run = run_of(run_id)
        if run.status != "waiting_for_user":
            raise ApiError(409, "run_not_waiting", f"run {run_id} is {run.status}, not waiting")
        question = next((q for q in run.questions if q.id == body.question_id), None)
        if question is None:
            raise ApiError(404, "question_not_found", f"unknown question_id: {body.question_id}")
        if body.value not in [c.value for c in question.choices]:   # None = "I don't know"
            raise ApiError(422, "invalid_answer", f"{body.value!r} is not a choice of {question.id}")
        # The run door resumes the paused graph with Command(resume={"value": value}); the
        # server never builds that itself (a bare None resume breaks langgraph).
        try:
            api.answer(run_id, body.question_id, body.value)
        except LookupError as err:          # the run closed, or the question was already answered, meanwhile
            raise ApiError(409, "run_not_waiting", str(err))
        return {"ok": True}

    @app.patch("/api/runs/{run_id}")
    def patch_run(run_id: str, body: PatchBody):
        run_of(run_id)
        try:
            api.update_run(run_id, body.budget_usd, body.overrides)
        except PatchError as err:
            raise ApiError(err.status, err.code, err.message)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/documents", response_model=DocumentDraft)
    def create_document(run_id: str, request: DocumentRequest):
        run = run_of(run_id)
        if request.run_id != run_id:
            raise ApiError(400, "run_id_mismatch", "body run_id differs from the path")
        if run.status != "done":
            raise ApiError(409, "run_not_done", f"run {run_id} is {run.status}; documents need a finished run")
        from backend.legal import api as legal
        if (request.doc_type in legal.list_templates(request.state, None)
                and request.doc_type not in legal.list_templates(request.state, run.property.segment)):
            # a legal document for the wrong kind of building must not be draftable, whatever the UI offers
            raise ApiError(422, "template_not_for_segment",
                           f"{request.doc_type} is not for a {run.property.segment} property")
        try:
            return api.draft_document(request)
        except LookupError as err:
            # No template for this document type and state. A 404 and not a 500: the
            # legal door refuses rather than relabelling another document, and
            # `list_templates` is how a client learns what it may ask for.
            raise ApiError(404, "template_not_available", str(err))

    @app.get("/api/runs/{run_id}/documents/{doc_id}", response_model=DocumentDraft)
    def get_document(run_id: str, doc_id: str):
        run_of(run_id)
        try:
            return api.get_document(run_id, doc_id)
        except KeyError:
            raise ApiError(404, "document_not_found", f"unknown doc_id: {doc_id}")

    @app.get("/api/runs/{run_id}/roof", response_model=RoofView)
    def get_roof(run_id: str):
        run_of(run_id)
        try:
            return api.get_roof(run_id)
        except KeyError as err:
            raise ApiError(404, "roof_not_available", str(err).strip("'\""))

    @app.get("/api/assets/{path:path}")
    def get_asset(path: str):
        # A path outside the cache and a missing file are both "no such asset" (404).
        try:
            body = data.get_asset(path)
        except (ValueError, FileNotFoundError):
            raise ApiError(404, "asset_not_found", f"no asset at {path}")
        return Response(body, media_type=mimetypes.guess_type(path)[0] or "application/octet-stream")

    return app

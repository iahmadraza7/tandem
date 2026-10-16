"""Tandem HTTP app: web app routes, live events, Vapi webhook, MCP server, static frontend."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import log_filters, playbooks, service
from app.agents import caller
from app.config import settings
from app.mcp_server import mcp
from app.session import store

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

# The Vapi webhook URL carries ?token=; mask it in the access log
log_filters.install()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Tandem", lifespan=lifespan)


# ---- request bodies ---------------------------------------------------------
class NewRequest(BaseModel):
    text: str
    playbook: str | None = None


class Clarify(BaseModel):
    answers: dict[str, Any]


class Select(BaseModel):
    place_id: str


class Consent(BaseModel):
    fields: dict[str, dict[str, Any]]
    limits: dict[str, Any] = {}


class Answer(BaseModel):
    card_id: str
    choice: str


class CallBack(BaseModel):
    answer: str


def _get(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Unknown session")
    return session


# ---- web app routes -----------------------------------------------------------
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "llm": bool(settings.anthropic_api_key),
        "vapi": bool(settings.vapi_api_key and settings.vapi_phone_number_id),
        "places": bool(settings.google_places_api_key),
        "calcom": bool(settings.calcom_username and settings.calcom_event_slug),
        "playbooks": list(playbooks.all_playbooks()),
    }


@app.post("/api/sessions")
async def create_session(body: NewRequest) -> dict[str, Any]:
    session = await service.new_request(body.text, body.playbook)
    return session.public()


@app.post("/api/sessions/{session_id}/clarify")
async def clarify(session_id: str, body: Clarify) -> dict[str, Any]:
    session = _get(session_id)
    await service.clarify(session, body.answers)
    return session.public()


@app.get("/api/sessions/{session_id}/state")
async def state(session_id: str) -> dict[str, Any]:
    """Polling fallback if the live event stream is cut by a proxy."""
    return _get(session_id).public()


@app.get("/api/sessions/{session_id}/events", response_class=EventSourceResponse)
async def events(session_id: str, request: Request):
    session = _get(session_id)
    queue = session.subscribe()
    try:
        yield ServerSentEvent(event="snapshot", data=session.public())
        while True:
            if await request.is_disconnected():
                break
            try:
                item = await asyncio.wait_for(queue.get(), timeout=15)
                yield ServerSentEvent(event=item["event"], data=item)
            except asyncio.TimeoutError:
                yield ServerSentEvent(comment="keep-alive")
    finally:
        session.unsubscribe(queue)


@app.post("/api/sessions/{session_id}/select")
async def select(session_id: str, body: Select) -> dict[str, Any]:
    try:
        return service.select_place(_get(session_id), body.place_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/sessions/{session_id}/consent")
async def consent(session_id: str, body: Consent) -> dict[str, Any]:
    session = _get(session_id)
    if session.selected_place is None:
        raise HTTPException(400, "Choose a place first")
    service.approve_consent(session, body.fields, body.limits)
    return {"ok": True}


@app.post("/api/sessions/{session_id}/answer")
async def answer(session_id: str, body: Answer) -> dict[str, Any]:
    return {"accepted": service.answer(_get(session_id), body.card_id, body.choice)}


@app.post("/api/sessions/{session_id}/callback")
async def call_back(session_id: str, body: CallBack) -> dict[str, Any]:
    try:
        service.call_back(_get(session_id), body.answer)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.get("/api/sessions/{session_id}/calendar.ics")
async def calendar(session_id: str) -> Response:
    session = _get(session_id)
    if session.ics is None:
        raise HTTPException(404, "No confirmed booking")
    return Response(session.ics, media_type="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=tandem-booking.ics"})


@app.get("/api/dev/latest")
def latest_session() -> dict[str, Any]:
    """Simulator helper: newest session waiting on a simulated call."""
    if not settings.simulate_calls:
        raise HTTPException(404, "Simulation is off")
    calling = [s for s in store.sessions.values() if (s.call or {}).get("status") == "simulated"]
    if not calling:
        raise HTTPException(404, "No simulated call waiting")
    newest = max(calling, key=lambda s: s.created_at)
    return {"session_id": newest.id, "call_id": newest.call["vapi_call_id"], "playbook": newest.playbook}


# ---- Vapi webhook -------------------------------------------------------------
def _args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}


@app.post("/vapi/webhook")
async def vapi_webhook(request: Request) -> JSONResponse:
    if settings.webhook_token and request.query_params.get("token") != settings.webhook_token:
        raise HTTPException(401, "Bad token")
    body = await request.json()
    message = body.get("message", body)
    kind = message.get("type")
    call_id = (message.get("call") or {}).get("id")
    session = store.by_call(call_id)

    if kind == "tool-calls":
        results = []
        for item in message.get("toolCallList", []):
            fn = item.get("function") or {}
            if session is None:
                results.append({"toolCallId": item.get("id"), "error": "unknown call"})
                continue
            result = await caller.handle_tool_call(session, fn.get("name", ""), _args(fn.get("arguments")))
            results.append({"toolCallId": item.get("id"), "result": result})
        return JSONResponse({"results": results})

    if session is not None:
        if kind == "status-update":
            caller.handle_status(session, message.get("status", "unknown"))
        elif kind == "end-of-call-report":
            caller.handle_end_of_call(session, message)
        elif kind == "transcript" and message.get("transcriptType", "final") == "final":
            caller.handle_transcript(session, message.get("role", ""), message.get("transcript", ""))
    return JSONResponse({"ok": True})


# ---- MCP and frontend ---------------------------------------------------------
# DNS rebinding protection is on by default for 127.0.0.1; behind the cloud URL we
# allow our own host. Clients connect to <PUBLIC_BASE_URL>/mcp/
from urllib.parse import urlparse  # noqa: E402

from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

_public_host = urlparse(settings.public_base_url).netloc
_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[h for h in {_public_host, "localhost:8000", "127.0.0.1:8000", "testserver"} if h],
    allowed_origins=[settings.public_base_url, "http://localhost:8000"],
)
app.mount("/mcp", mcp.streamable_http_app(streamable_http_path="/", transport_security=_security))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

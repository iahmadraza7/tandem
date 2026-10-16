"""MCP server exposing Tandem's tools (mcp 2.x: FastMCP was renamed MCPServer).

Mounted at /mcp by app.main. Claude Desktop connects to https://<public url>/mcp as a
custom connector. The human checkpoints still apply: consent and live decisions are
answered by the user, through these tools or the web app.
"""
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from app import playbooks, service
from app.agents.concierge import template_values
from app.session import store

mcp = MCPServer(
    "Tandem",
    instructions=(
        "Tandem books with businesses by phone or booking API. Always show the user the shortlist, "
        "the consent card and every decision card, and only pass on the user's own answers."
    ),
)


def _session(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise ValueError("Unknown session id")
    return session


@mcp.tool()
async def start_request(text: str, playbook: str | None = None) -> dict[str, Any]:
    """Start a booking request, e.g. 'dentist near Gulberg Lahore next week for a cleaning'.
    playbook is optional: clinic, hotel or restaurant."""
    session = await service.new_request(text, playbook)
    return {"session_id": session.id, "status": session.status, "request": session.request, "places": session.places}


@mcp.tool()
async def clarify_request(session_id: str, where: str | None = None, when: str | None = None,
                          what: str | None = None, party_size: int | None = None) -> dict[str, Any]:
    """Fill in missing details of a request."""
    session = _session(session_id)
    missing = await service.clarify(session, {"where": where, "when": when, "what": what, "party_size": party_size})
    return {"missing": missing, "places": session.places}


@mcp.tool()
async def choose_place(session_id: str, place_id: str) -> dict[str, Any]:
    """Checkpoint 1: the user picks a place. Returns the consent card to show the user."""
    return service.select_place(_session(session_id), place_id)


@mcp.tool()
async def approve_consent(session_id: str, share_keys: list[str], window_start: str | None = None,
                    window_end: str | None = None, budget_cap: float | None = None,
                    confirm_slots: bool = True) -> str:
    """Checkpoint 2: the user approves which consent fields may be shared and sets limits, then the call
    or online booking starts. Times are ISO date and time, e.g. 2026-10-20T09:00.
    confirm_slots (default true): ask the user before confirming any time, even one inside the window."""
    session = _session(session_id)
    if session.selected_place is None:
        raise ValueError("Choose a place first")
    rows = {r["key"]: r for r in playbooks.consent_template(session.playbook, template_values(session))}
    fields = {k: {"value": r["value"], "share": k in share_keys} for k, r in rows.items()}
    limits = {"window_start": window_start, "window_end": window_end, "budget_cap": budget_cap,
              "tolerance_minutes": 0, "deposit_allowed": False, "confirm_slots": confirm_slots}
    service.approve_consent(session, fields, limits)
    return "started"


@mcp.tool()
async def get_status(session_id: str) -> dict[str, Any]:
    """Current status, open decision cards and outcome."""
    snap = _session(session_id).public()
    return {k: snap[k] for k in ("status", "channel", "cards", "outcome", "pending_offer", "timeline")}


@mcp.tool()
async def answer_card(session_id: str, card_id: str, choice: str) -> bool:
    """Checkpoint 3: pass on the user's answer to an open decision card."""
    return service.answer(_session(session_id), card_id, choice)

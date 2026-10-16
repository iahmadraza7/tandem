"""Use cases shared by the HTTP routes (web app) and the MCP server (Claude Desktop)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app import playbooks
from app.agents import caller, concierge, scout, web_booker
from app.agents.concierge import template_values
from app.session import Session, store

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()


def spawn(session: Session, coro, label: str) -> None:
    """Run agent work in the background and surface failures on the timeline."""

    async def runner():
        try:
            await coro
        except Exception as exc:
            # Real error in the server log only; the UI gets plain words
            logger.exception("%s failed", label)
            message = str(exc) if isinstance(exc, ValueError) else "Something went wrong. Details are in the server log."
            session.log("System", f"{label} stopped: {message}")
            session.emit("error", {"where": label, "message": message})

    task = asyncio.create_task(runner())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def new_request(text: str, playbook: str | None = None) -> Session:
    session = store.create()
    missing = await concierge.understand(session, text, playbook)
    if missing:
        session.status = "clarifying"
        session.emit("clarify", {"missing": missing, "request": session.request})
    else:
        await scout.find(session)
    return session


async def clarify(session: Session, answers: dict[str, Any]) -> list[str]:
    missing = concierge.apply_clarification(session, answers)
    if missing:
        session.emit("clarify", {"missing": missing, "request": session.request})
    else:
        await scout.find(session)
    return missing


def select_place(session: Session, place_id: str) -> dict[str, Any]:
    place = next((p for p in session.places if p.get("id") == place_id), None)
    if place is None:
        raise KeyError("Unknown place")
    if place.get("channel") == "none":
        raise ValueError("This place has no phone number or booking system")
    session.selected_place = place
    session.channel = place["channel"]
    session.status = "consenting"
    session.log("Concierge", f"You chose {place['name']} ({'phone call' if session.channel == 'phone' else 'online booking'})")
    consent = {
        "fields": playbooks.consent_template(session.playbook, template_values(session)),
        "limits": playbooks.get(session.playbook).get("default_limits", {}),
    }
    session.emit("consent.request", consent)
    return consent


def approve_consent(session: Session, fields: dict[str, dict[str, Any]], limits: dict[str, Any]) -> None:
    session.consent = {"fields": fields, "limits": limits}
    shared = [k for k, v in fields.items() if v.get("share")]
    session.log("Guardian", f"Consent set: may share {', '.join(shared) or 'nothing'}")
    if session.channel == "phone":
        spawn(session, caller.start_call(session), "Caller")
    elif session.channel == "web":
        spawn(session, web_booker.run(session), "Web Booker")


def answer(session: Session, card_id: str, choice: str) -> bool:
    accepted = session.answer_card(card_id, choice)
    if accepted:
        session.log("You", f"Answered: {choice if not choice.startswith('share:') else 'shared the detail'}")
    return accepted


def call_back(session: Session, user_answer: str) -> None:
    if not session.pending_offer:
        raise ValueError("Nothing to call back about")
    session.pending_offer["user_answer"] = user_answer
    session.outcome = None
    session.log("Concierge", f"Calling back with your answer: {user_answer}")
    spawn(session, caller.start_call(session), "Caller (call back)")

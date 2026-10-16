"""Concierge: understands the request, picks the playbook, asks for what is missing.

Uses Claude Sonnet when ANTHROPIC_API_KEY is set; falls back to keyword rules so the
app still runs offline during development.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app import playbooks
from app.config import settings
from app.session import Session
from app.tools import llm

logger = logging.getLogger(__name__)

REQUIRED = ("what", "where", "when")

SYSTEM = """You are the Concierge of Tandem, an assistant that books with businesses for the user.
Extract the booking request. Playbooks: clinic, hotel, restaurant.
Return JSON with keys: playbook (one of clinic, hotel, restaurant, or null), what (the service or request),
where (city or area, or null), when (natural language time preference, or null),
party_size (integer or null), wants_booking (true if the user wants a booking, false if they only want options).
Do not invent values the user did not give."""


def _heuristic(text: str) -> dict[str, Any]:
    lowered = text.lower()
    where = None
    match = re.search(r"\b(?:in|near|around)\s+([A-Za-z][\w\s,]{1,40})", text)
    if match:
        where = re.split(r"\b(?:today|tonight|tomorrow|next|this|on|at|for|by)\b", match.group(1))[0].strip(" .,")
    party = re.search(r"\b(\d{1,2})\s*(?:people|persons|guests|pax)\b", lowered)
    when = None
    for word in ("today", "tonight", "tomorrow", "next week", "this week", "weekend", "monday", "tuesday",
                 "wednesday", "thursday", "friday", "saturday", "sunday"):
        if word in lowered:
            when = word
            break
    return {
        "playbook": playbooks.guess(text),
        "what": text.strip(),
        "where": where,
        "when": when,
        "party_size": int(party.group(1)) if party else None,
        "wants_booking": "only options" not in lowered and "just show" not in lowered,
    }


async def understand(session: Session, text: str, playbook_hint: str | None = None) -> list[str]:
    """Fill session.request and session.playbook. Returns the list of missing fields."""
    session.log("Concierge", "Reading your request")
    try:
        parsed = await llm.complete_json(settings.model_concierge, SYSTEM, text)
    except llm.LLMNotConfigured:
        parsed = _heuristic(text)
    except Exception as exc:  # model or network error: degrade, do not crash
        logger.warning("Concierge model call failed: %r", exc)
        session.log("Concierge", "Model unavailable, using simple rules")
        parsed = _heuristic(text)

    playbook = playbook_hint or parsed.get("playbook") or playbooks.guess(text)
    session.playbook = playbook
    session.request = {**session.request, **{k: v for k, v in parsed.items() if v not in (None, "")}}
    session.request.setdefault("text", text)
    missing = [key for key in REQUIRED if not session.request.get(key)]
    if not playbook:
        missing.insert(0, "playbook")
    if playbook:
        session.log("Concierge", f"Using the {playbooks.get(playbook)['display']} playbook")
    return missing


def apply_clarification(session: Session, answers: dict[str, Any]) -> list[str]:
    for key, value in answers.items():
        if value not in (None, ""):
            if key == "playbook":
                session.playbook = value
            else:
                session.request[key] = value
    missing = [key for key in REQUIRED if not session.request.get(key)]
    if not session.playbook:
        missing.insert(0, "playbook")
    return missing


def template_values(session: Session) -> dict[str, Any]:
    req = session.request
    return {
        "user_name": settings.user_name,
        "what": req.get("what", ""),
        "where": req.get("where", ""),
        "when": req.get("when", ""),
        "party_size": req.get("party_size", ""),
    }

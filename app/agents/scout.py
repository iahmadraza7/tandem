"""Scout: finds places, ranks them, and picks a channel per place (phone, web, none)."""
from __future__ import annotations

import logging
import math
from typing import Any

from app import playbooks
from app.agents.concierge import template_values
from app.session import Session
from app.tools import places as places_tool

logger = logging.getLogger(__name__)


def channel_for(place: dict[str, Any]) -> str:
    if (place.get("booking") or {}).get("type") == "calcom":
        return "web"
    if place.get("phone"):
        return "phone"
    return "none"


def _score(place: dict[str, Any]) -> float:
    rating = place.get("rating") or 0
    reviews = place.get("reviews") or 0
    return rating * 2 + math.log10(reviews + 1)


async def find(session: Session) -> list[dict[str, Any]]:
    session.status = "searching"
    book = playbooks.get(session.playbook)
    query = playbooks.fill(book["search_query"], template_values(session))
    session.log("Scout", f"Searching: {query}")
    results: list[dict[str, Any]] = []
    try:
        results = await places_tool.search_places(query)
    except Exception as exc:
        logger.warning("Live Places search failed: %r", exc)
        session.log("Scout", "Live search unavailable, showing demo businesses")
    if not results:
        results = places_tool.seed_places(session.playbook)
        session.log("Scout", "Using the demo list of businesses")
    for place in results:
        place["channel"] = channel_for(place)
    results.sort(key=_score, reverse=True)
    # Reachable places first, unreachable ones last
    results.sort(key=lambda p: p["channel"] == "none")
    session.places = results[:5]
    session.status = "choosing"
    session.log("Scout", f"Found {len(session.places)} options, ranked by rating and number of reviews")
    session.emit("shortlist", {"places": session.places})
    return session.places

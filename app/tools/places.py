"""Place search: Google Places API (New) Text Search, with a seeded list as fallback.

Fields used here (rating, phone, website, opening hours) put requests in the Enterprise
SKU: 1,000 free requests a month per Google's pricing page (checked 16 Oct 2026).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.rating",
        "places.userRatingCount",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.currentOpeningHours.openNow",
    ]
)
SEED_FILE = Path(__file__).resolve().parents[2] / "data" / "seed_places.json"
# Used for seeded demo businesses in simulate mode when DEMO_FRONT_DESK_NUMBER is empty; never dialled
SIMULATED_FRONT_DESK_NUMBER = "+10000000000"


def seed_places(playbook: str) -> list[dict[str, Any]]:
    data = json.loads(SEED_FILE.read_text())
    places = []
    for place in data.get(playbook, []):
        place = dict(place)
        if place.get("phone") == "{DEMO_FRONT_DESK_NUMBER}":
            place["phone"] = settings.demo_front_desk_number or (
                SIMULATED_FRONT_DESK_NUMBER if settings.simulate_calls else None)
        place["source"] = "seed"
        places.append(place)
    return places


async def search_places(query: str) -> list[dict[str, Any]]:
    if not settings.google_places_api_key:
        return []
    headers = {
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": FIELD_MASK,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(SEARCH_URL, headers=headers, json={"textQuery": query, "pageSize": 8})
        response.raise_for_status()
    results = []
    for item in response.json().get("places", []):
        results.append(
            {
                "id": item.get("id"),
                "name": (item.get("displayName") or {}).get("text"),
                "address": item.get("formattedAddress"),
                "rating": item.get("rating"),
                "reviews": item.get("userRatingCount"),
                "phone": item.get("internationalPhoneNumber"),
                "website": item.get("websiteUri"),
                "open_now": (item.get("currentOpeningHours") or {}).get("openNow"),
                "booking": None,
                "source": "places",
            }
        )
    return results

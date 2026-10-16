"""Cal.com API v2 client for the web channel.

Cal.com's terms (section 4.3(d)) ban automated access other than the documented API,
so the Web Booker never drives the booking page with a browser.
Headers and versions from cal.com/docs/api-reference/v2 (checked 16 Oct 2026).
NOT YET TESTED LIVE.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings

SLOTS_VERSION = "2024-09-04"
BOOKINGS_VERSION = "2026-02-25"


class CalcomNotConfigured(RuntimeError):
    pass


def _check() -> None:
    if not (settings.calcom_username and settings.calcom_event_slug):
        raise CalcomNotConfigured("CALCOM_USERNAME and CALCOM_EVENT_SLUG must be set")


def _headers(version: str) -> dict[str, str]:
    headers = {"cal-api-version": version, "Content-Type": "application/json"}
    if settings.calcom_api_key:
        headers["Authorization"] = f"Bearer {settings.calcom_api_key}"
    return headers


async def get_slots(start_iso: str, end_iso: str, timezone: str) -> list[str]:
    _check()
    params = {
        "eventTypeSlug": settings.calcom_event_slug,
        "username": settings.calcom_username,
        "start": start_iso,
        "end": end_iso,
        "timeZone": timezone,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{settings.calcom_base_url}/slots", params=params, headers=_headers(SLOTS_VERSION))
        response.raise_for_status()
    data = response.json().get("data", {})
    slots: list[str] = []
    for day in sorted(data):  # data is keyed by date
        for slot in data[day]:
            slots.append(slot.get("start") if isinstance(slot, dict) else str(slot))
    return slots


async def create_booking(start_iso: str, name: str, email: str, timezone: str) -> dict[str, Any]:
    _check()
    body = {
        "start": start_iso,
        "eventTypeSlug": settings.calcom_event_slug,
        "username": settings.calcom_username,
        "attendee": {"name": name, "email": email, "timeZone": timezone},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{settings.calcom_base_url}/bookings", json=body, headers=_headers(BOOKINGS_VERSION))
        response.raise_for_status()
        return response.json()

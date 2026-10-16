"""Thin Vapi REST client. Field names follow docs.vapi.ai and the API spec (checked 16 Oct 2026).

NOT YET TESTED LIVE: run one real call before relying on the exact payload shapes.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class VapiNotConfigured(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.vapi_api_key:
        raise VapiNotConfigured("VAPI_API_KEY is not set")
    return {"Authorization": f"Bearer {settings.vapi_api_key}", "Content-Type": "application/json"}


async def create_call(assistant: dict[str, Any], customer_number: str) -> dict[str, Any]:
    """POST /call with a transient assistant and the imported Twilio number."""
    if not settings.vapi_phone_number_id:
        raise VapiNotConfigured("VAPI_PHONE_NUMBER_ID is not set")
    body = {
        "phoneNumberId": settings.vapi_phone_number_id,
        "customer": {"number": customer_number},
        "assistant": assistant,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(f"{settings.vapi_base_url}/call", headers=_headers(), json=body)
        response.raise_for_status()
        return response.json()


async def control(control_url: str, payload: dict[str, Any]) -> None:
    """Live call control: {"type":"say",...}, {"type":"add-message",...}, {"type":"end-call"}."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(control_url, headers=_headers(), json=payload)
        response.raise_for_status()

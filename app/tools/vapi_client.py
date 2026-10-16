"""Thin Vapi REST client. Field names follow docs.vapi.ai and the API spec (checked 16 Oct 2026).

create_call: tested on a live call 17 Oct. control / end_call: not yet run on a live call.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

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


class ControlError(RuntimeError):
    """Live control failed. The message never contains the control URL (whoever has it controls the call)."""


async def control(control_url: str, payload: dict[str, Any]) -> None:
    """Live call control: {"type":"say",...}, {"type":"add-message",...}, {"type":"end-call"}.

    docs.vapi.ai: with monitorPlan.controlAuthenticationEnabled the control URL requires
    "Authorization: Bearer <vapi-public-api-key>". Without VAPI_PUBLIC_API_KEY we try the private key (unverified).
    """
    host = urlparse(control_url).hostname or ""
    if not host.endswith(".vapi.ai"):
        raise ControlError("control URL is not a vapi.ai host")
    key = settings.vapi_public_api_key or settings.vapi_api_key
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(control_url, headers=headers, json=payload)
    if response.is_error:  # not raise_for_status(): its message contains the URL
        raise ControlError(f"control request failed with HTTP {response.status_code}")


async def end_call(control_url: str) -> None:
    await control(control_url, {"type": "end-call"})

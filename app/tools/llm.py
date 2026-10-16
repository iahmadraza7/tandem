"""Single entry point for Claude calls. All agents call the model through here."""
from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings

_client = None


class LLMNotConfigured(RuntimeError):
    pass


def _get_client():
    global _client
    if not settings.anthropic_api_key:
        raise LLMNotConfigured("ANTHROPIC_API_KEY is not set")
    if _client is None:
        from anthropic import AsyncAnthropic

        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def complete_text(model: str, system: str, user: str, max_tokens: int = 600) -> str:
    client = _get_client()
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")


async def complete_json(model: str, system: str, user: str, max_tokens: int = 600) -> dict[str, Any]:
    text = await complete_text(model, system + "\nReply with one JSON object only.", user, max_tokens)
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"Model did not return JSON: {text[:200]}")
    return json.loads(match.group(0))

"""Guardian: decides whether the agent may act alone or must ask the human.

Rules run first and are pure Python. The model is never asked to decide what the user
consented to. Three possible actions:
  allow     the offer is inside the user's limits, or the field was consented
  ask_user  open a decision card and wait for the user
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class Decision:
    action: str  # allow | ask_user
    reason: str
    value: str | None = None  # consented value to share, or the accepted offer


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=None)
    except ValueError:
        return None


def _parse_amount(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)", str(value))
    return float(match.group(1).replace(",", "")) if match else None


def _norm_field(field: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (field or "").lower()).strip("_")


def approved_fields(consent: dict[str, Any]) -> dict[str, str]:
    """Only the fields the user ticked, with the values they approved."""
    return {
        _norm_field(key): str(entry.get("value", ""))
        for key, entry in (consent.get("fields") or {}).items()
        if entry.get("share")
    }


def evaluate(
    consent: dict[str, Any],
    kind: str,
    offered_value: Any = None,
    field: str | None = None,
) -> Decision:
    limits = consent.get("limits") or {}
    kind = (kind or "other").lower()

    if kind == "payment":
        return Decision("ask_user", "Payments always go to the user; the agent never takes or relays payment.")

    if kind == "data":
        approved = approved_fields(consent)
        key = _norm_field(field)
        if key and key in approved and approved[key]:
            return Decision("allow", f"'{key}' is on the consent card.", approved[key])
        return Decision("ask_user", f"'{field or 'this detail'}' is not on your consent card.")

    if kind == "slot":
        slot = _parse_dt(offered_value)
        start, end = _parse_dt(limits.get("window_start")), _parse_dt(limits.get("window_end"))
        if slot is None:
            return Decision("ask_user", "The offered time could not be read as a full date and time.")
        if start is None or end is None:
            return Decision("ask_user", "No time window was set, so every time goes to the user.")
        tolerance = timedelta(minutes=int(limits.get("tolerance_minutes") or 0))
        if start - tolerance <= slot <= end + tolerance:
            return Decision("allow", "The time is inside your window.", slot.isoformat(timespec="minutes"))
        return Decision("ask_user", "The time is outside your window.")

    if kind == "price":
        amount, cap = _parse_amount(offered_value), _parse_amount(limits.get("budget_cap"))
        if amount is None:
            return Decision("ask_user", "The price could not be read.")
        if cap is None:
            return Decision("ask_user", "No budget cap was set, so every price goes to the user.")
        if amount <= cap:
            return Decision("allow", "The price is within your budget cap.", str(offered_value))
        return Decision("ask_user", "The price is above your budget cap.")

    return Decision("ask_user", "This needs your decision.")

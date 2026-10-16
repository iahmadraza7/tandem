"""Verifier: turns the end of a call or booking into exactly one outcome.

Only a Confirmed outcome with an exact date and time produces a calendar file.
"""
from __future__ import annotations

from typing import Any

from app.agents.guardian import _parse_dt
from app.config import settings
from app.session import Session
from app.tools.calendar_ics import build_ics

STATUSES = ("confirmed", "tentative", "callback_needed", "failed")

_ALIASES = {
    "confirmed": "confirmed",
    "booked": "confirmed",
    "tentative": "tentative",
    "held": "tentative",
    "hold": "tentative",
    "callback": "callback_needed",
    "callback_needed": "callback_needed",
    "call_back": "callback_needed",
    "failed": "failed",
    "no_answer": "failed",
    "busy": "failed",
}


def classify(report: dict[str, Any]) -> dict[str, Any]:
    raw = str(report.get("status", "")).strip().lower().replace(" ", "_")
    status = _ALIASES.get(raw, "failed")
    date_time = _parse_dt(report.get("date_time"))
    read_back = bool(report.get("read_back_confirmed"))
    reason = report.get("notes") or ""

    if status == "confirmed" and not read_back:
        status, reason = "tentative", "The front desk did not confirm the read back."
    if status == "confirmed" and date_time is None:
        status, reason = "tentative", "No exact date and time was captured."

    return {
        "status": status,
        "date_time": date_time.isoformat(timespec="minutes") if date_time else None,
        "details": report.get("details") or {},
        "hold_expires": report.get("hold_expires"),
        "reason": reason,
    }


def apply(session: Session, report: dict[str, Any], source: str) -> dict[str, Any]:
    """Classify, store on the session, emit, and write the calendar file if Confirmed."""
    outcome = classify(report)
    outcome["source"] = source  # phone | web
    session.outcome = outcome
    session.status = "done"
    place = session.selected_place or {}
    label = outcome["status"].replace("_", " ").capitalize()
    session.log("Verifier", f"Outcome: {label}" + (f" ({outcome['reason']})" if outcome["reason"] else ""))
    if outcome["status"] == "confirmed" and outcome["date_time"]:
        session.ics = build_ics(
            title=f"{place.get('name', 'Booking')}",
            start_iso=outcome["date_time"],
            minutes=60,
            location=place.get("address") or "",
            timezone=settings.timezone,
        )
        session.log("Verifier", "Calendar file ready")
    session.emit("outcome", outcome)
    return outcome

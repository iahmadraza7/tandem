"""Web Booker: books through a business's official booking API (Cal.com v2 in the demo).

Human checkpoints: pick a slot on a card, then approve a review card before the booking
request is sent. No browser automation (Cal.com terms, section 4.3(d)).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.agents import verifier
from app.config import settings
from app.session import Session
from app.tools import calcom

logger = logging.getLogger(__name__)

SLOT_CARD_SECONDS = 120  # web flow is not holding a phone line, so the user gets longer


def _label(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo(settings.timezone))
        return dt.strftime("%a %d %b, %I:%M %p")
    except ValueError:
        return iso


async def run(session: Session) -> None:
    session.status = "booking"
    session.log("Web Booker", "Reading open slots from the booking system")
    now = datetime.now(ZoneInfo(settings.timezone))
    try:
        slots = await calcom.get_slots(now.isoformat(), (now + timedelta(days=7)).isoformat(), settings.timezone)
    except Exception as exc:
        logger.warning("Cal.com slots failed: %r", exc)
        session.log("Web Booker", "Could not read open slots from the booking system")
        verifier.apply(session, {"status": "failed", "read_back_confirmed": False,
                                 "notes": "Booking system unavailable"}, "web")
        return
    if not slots:
        verifier.apply(session, {"status": "failed", "read_back_confirmed": False, "notes": "No open slots"}, "web")
        return

    offered = slots[:3]
    labels = [_label(s) for s in offered]
    card = session.open_card("slot", "Which time should I book?", labels + ["None of these"],
                             deadline_seconds=SLOT_CARD_SECONDS, meta={"slots": offered})
    choice = await session.wait_for_card(card, SLOT_CARD_SECONDS)
    if choice is None or choice not in labels:
        verifier.apply(session, {"status": "callback_needed", "read_back_confirmed": False,
                                 "notes": "No slot chosen"}, "web")
        return
    start = offered[labels.index(choice)]

    name = (session.consent.get("fields", {}).get("name") or {}).get("value") or settings.user_name
    email = settings.calcom_attendee_email or "demo@example.com"
    review = session.open_card(
        "review",
        f"Book {choice} at {(session.selected_place or {}).get('name')} for {name}?",
        ["Book it", "Cancel"],
        deadline_seconds=SLOT_CARD_SECONDS,
        meta={"start": start, "name": name, "email": email},
    )
    decision = await session.wait_for_card(review, SLOT_CARD_SECONDS)
    if decision != "Book it":
        verifier.apply(session, {"status": "callback_needed", "read_back_confirmed": False,
                                 "notes": "Booking not approved"}, "web")
        return

    session.log("Web Booker", "Sending the booking request")
    try:
        result = await calcom.create_booking(start, name, email, settings.timezone)
    except Exception as exc:
        logger.warning("Cal.com booking failed: %r", exc)
        session.log("Web Booker", "The booking request did not go through")
        verifier.apply(session, {"status": "failed", "read_back_confirmed": False, "notes": "Booking request failed"}, "web")
        return
    booking = result.get("data") or {}
    local_start = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(ZoneInfo(settings.timezone))
    verifier.apply(
        session,
        {
            "status": "confirmed" if booking else "tentative",
            "date_time": local_start.replace(tzinfo=None).isoformat(timespec="minutes"),
            "read_back_confirmed": bool(booking),  # the API's confirmation stands in for the read back
            "details": {"booking_uid": booking.get("uid")},
        },
        "web",
    )

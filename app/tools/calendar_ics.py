"""Calendar file for a Confirmed booking (no OAuth needed)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event


def build_ics(title: str, start_iso: str, minutes: int, location: str, timezone: str) -> bytes:
    tz = ZoneInfo(timezone)
    start = datetime.fromisoformat(start_iso)
    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)
    cal = Calendar()
    cal.add("prodid", "-//Tandem//Agentika 2.0//EN")
    cal.add("version", "2.0")
    event = Event()
    event.add("summary", title)
    event.add("dtstart", start)
    event.add("dtend", start + timedelta(minutes=minutes))
    event.add("dtstamp", datetime.now(tz))
    event.add("uid", f"{uuid.uuid4()}@tandem")
    event.add("location", location)
    cal.add_component(event)
    return cal.to_ical()

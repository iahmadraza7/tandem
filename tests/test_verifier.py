from app.agents import verifier
from app.session import Session


def test_confirmed_needs_read_back():
    out = verifier.classify({"status": "confirmed", "date_time": "2026-10-20T15:00", "read_back_confirmed": False})
    assert out["status"] == "tentative"


def test_confirmed_needs_exact_time():
    out = verifier.classify({"status": "confirmed", "read_back_confirmed": True})
    assert out["status"] == "tentative"


def test_confirmed_with_read_back():
    out = verifier.classify({"status": "confirmed", "date_time": "2026-10-20T15:00", "read_back_confirmed": True})
    assert out["status"] == "confirmed" and out["date_time"] == "2026-10-20T15:00"


def test_unknown_status_is_failed():
    assert verifier.classify({"status": "maybe"})["status"] == "failed"


def test_apply_writes_calendar_only_when_confirmed():
    s = Session(id="t1")
    s.selected_place = {"name": "Demo Clinic", "address": "Demo"}
    verifier.apply(s, {"status": "tentative", "read_back_confirmed": False}, "phone")
    assert s.ics is None
    verifier.apply(s, {"status": "confirmed", "date_time": "2026-10-20T15:00", "read_back_confirmed": True}, "phone")
    assert s.ics is not None and b"BEGIN:VCALENDAR" in s.ics

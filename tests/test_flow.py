"""End to end flow without Vapi: simulates Vapi's webhook calls against the real app."""
import asyncio

import httpx
import pytest

from app.config import settings
from app.main import app
from app.session import store


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def isolate_from_env(monkeypatch):
    # Tests must not depend on .env: no webhook token, no live APIs, seed list with a phone channel
    monkeypatch.setattr(settings, "webhook_token", None)
    monkeypatch.setattr(settings, "demo_front_desk_number", "+10000000000")
    monkeypatch.setattr(settings, "simulate_calls", True)
    for key in ("anthropic_api_key", "google_places_api_key", "vapi_api_key", "calcom_api_key"):
        monkeypatch.setattr(settings, key, None)


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


async def _setup_phone_session(client):
    r = await client.post("/api/sessions", json={"text": "dentist cleaning in Gulberg Lahore next week", "playbook": "clinic"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "choosing"
    phone_place = next(p for p in data["places"] if p["channel"] == "phone")
    r = await client.post(f"/api/sessions/{data['id']}/select", json={"place_id": phone_place["id"]})
    assert r.status_code == 200
    session = store.get(data["id"])
    session.consent = {
        "fields": {"name": {"value": "Ahmad", "share": True}},
        "limits": {"window_start": "2026-10-20T09:00", "window_end": "2026-10-20T12:00"},
    }
    store.link_call("call-test-" + session.id, session.id)
    return session, "call-test-" + session.id


def _tool_call(call_id, name, args, tool_id="tc1"):
    return {"message": {"type": "tool-calls", "call": {"id": call_id},
                        "toolCallList": [{"id": tool_id, "function": {"name": name, "arguments": args}}]}}


@pytest.mark.anyio
async def test_ask_user_waits_for_human_answer():
    async with _client() as client:
        session, call_id = await _setup_phone_session(client)
        request = asyncio.create_task(client.post("/vapi/webhook", json=_tool_call(
            call_id, "ask_user", {"question": "Tuesday 3 PM instead?", "kind": "slot", "offered_value": "2026-10-20T15:00"})))
        for _ in range(50):
            await asyncio.sleep(0.02)
            if session.cards:
                break
        card = next(iter(session.cards.values()))
        r = await client.post(f"/api/sessions/{session.id}/answer", json={"card_id": card.id, "choice": "Accept"})
        assert r.json()["accepted"] is True
        result = (await request).json()["results"][0]["result"]
        assert result == "user chose: Accept"
        # second answer to the same card is rejected (first tap wins)
        r = await client.post(f"/api/sessions/{session.id}/answer", json={"card_id": card.id, "choice": "Decline"})
        assert r.json()["accepted"] is False


@pytest.mark.anyio
async def test_preferred_time_still_asks_the_user_by_default():
    async with _client() as client:
        session, call_id = await _setup_phone_session(client)  # limits have no confirm_slots: on by default
        request = asyncio.create_task(client.post("/vapi/webhook", json=_tool_call(call_id, "ask_user", {
            "question": "They can do your preferred time, Tuesday 10 AM. Book it?", "kind": "slot",
            "offered_value": "2026-10-20T10:00", "options": ["Accept", "Decline"]})))
        for _ in range(100):
            await asyncio.sleep(0.02)
            if session.cards:
                break
        card = next(iter(session.cards.values()))
        assert card.kind == "slot" and card.meta["reason"] == "Your preferred time is available."
        await client.post(f"/api/sessions/{session.id}/answer", json={"card_id": card.id, "choice": "Accept"})
        assert (await request).json()["results"][0]["result"] == "user chose: Accept"


@pytest.mark.anyio
async def test_guardian_allows_slot_inside_window_without_card_when_confirm_is_off():
    async with _client() as client:
        session, call_id = await _setup_phone_session(client)
        session.consent["limits"]["confirm_slots"] = False
        r = await client.post("/vapi/webhook", json=_tool_call(
            call_id, "ask_user", {"question": "10 AM?", "kind": "slot", "offered_value": "2026-10-20T10:00"}))
        assert r.json()["results"][0]["result"].startswith("allowed by the user's limits")
        assert not session.cards


@pytest.mark.anyio
async def test_no_answer_on_a_time_asks_for_a_hold_and_offers_followup(monkeypatch):
    monkeypatch.setattr(settings, "card_deadline_seconds", 0.2)
    async with _client() as client:
        session, call_id = await _setup_phone_session(client)
        r = await client.post("/vapi/webhook", json=_tool_call(call_id, "ask_user", {
            "question": "They offer Tuesday 3 PM. Accept?", "kind": "slot", "offered_value": "2026-10-20T15:00"}))
        result = r.json()["results"][0]["result"]
        assert result.startswith("no_answer") and "hold the offer" in result
        assert next(iter(session.cards.values())).state == "expired"
        assert session.pending_offer is not None and session.pending_offer["offered_value"] == "2026-10-20T15:00"


@pytest.mark.anyio
async def test_no_answer_on_a_personal_detail_does_not_share_and_saves_no_offer(monkeypatch):
    monkeypatch.setattr(settings, "card_deadline_seconds", 0.2)
    async with _client() as client:
        session, call_id = await _setup_phone_session(client)
        r = await client.post("/vapi/webhook", json=_tool_call(
            call_id, "ask_user", {"question": "Date of birth?", "kind": "data", "field": "date_of_birth"}))
        result = r.json()["results"][0]["result"]
        assert result.startswith("no_answer") and "Do not share date_of_birth" in result
        assert "in person" in result and "hold" not in result
        assert next(iter(session.cards.values())).state == "expired"
        assert session.pending_offer is None  # nothing to call back about


@pytest.mark.anyio
async def test_report_outcome_confirmed_creates_calendar_file():
    async with _client() as client:
        session, call_id = await _setup_phone_session(client)
        r = await client.post("/vapi/webhook", json=_tool_call(call_id, "report_outcome", {
            "status": "confirmed", "date_time": "2026-10-20T15:00", "read_back_confirmed": True}))
        assert r.json()["results"][0]["result"] == "ok"
        r = await client.get(f"/api/sessions/{session.id}/calendar.ics")
        assert r.status_code == 200 and "BEGIN:VCALENDAR" in r.text


@pytest.mark.anyio
async def test_missing_details_ask_for_clarification():
    async with _client() as client:
        r = await client.post("/api/sessions", json={"text": "I want the best curry"})
        data = r.json()
        assert data["status"] == "clarifying"
        r = await client.post(f"/api/sessions/{data['id']}/clarify", json={"answers": {"where": "Lahore", "when": "tonight"}})
        assert r.json()["status"] == "choosing"
        assert r.json()["playbook"] == "restaurant"

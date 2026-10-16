"""Caller: endCall tool on the assistant, prompt rules for times, and the server end-call fallback."""
import asyncio

import pytest

from app.agents import caller
from app.config import settings
from app.session import Session
from app.tools import vapi_client

CONTROL_URL = "https://phone-call-websocket.aws-us-west-2-backend-production1.vapi.ai/abc123/control"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _session(confirm_slots=None, status="in-progress", control_url=CONTROL_URL):
    limits = {"window_start": "2026-10-19T09:00", "window_end": "2026-10-19T12:00"}
    if confirm_slots is not None:
        limits["confirm_slots"] = confirm_slots
    s = Session(id="s1", playbook="clinic", request={"what": "cleaning", "where": "Gulberg", "when": "Monday"},
                consent={"fields": {"name": {"value": "Ahmad", "share": True}}, "limits": limits})
    s.call = {"vapi_call_id": "call-1", "control_url": control_url, "status": status}
    return s


def test_assistant_has_end_call_tool_with_blocking_goodbye(monkeypatch):
    monkeypatch.setattr(settings, "webhook_token", None)
    tools = caller.build_assistant(_session())["model"]["tools"]
    end = [t for t in tools if t["type"] == "endCall"]
    assert len(end) == 1
    assert end[0]["messages"] == [{"type": "request-start", "content": caller.GOODBYE, "blocking": True}]


def test_prompt_asks_preferred_time_first_and_every_time_goes_to_ask_user():
    prompt = caller.system_prompt(_session())
    assert "First ask for" in prompt and "Monday 19 October 2026 at 09:00" in prompt
    assert "For EVERY time they offer, preferred or alternative, call ask_user" in prompt
    assert 'unless ask_user returned exactly "user chose: Accept"' in prompt
    assert "call the endCall tool" in prompt


def test_prompt_with_confirm_off_also_accepts_guardian_allowed_times():
    prompt = caller.system_prompt(_session(confirm_slots=False))
    assert "allowed by the user's limits: accept <that time>" in prompt


@pytest.mark.anyio
@pytest.mark.parametrize("status, control_url, replaced, expected", [
    ("in-progress", CONTROL_URL, False, [CONTROL_URL]),  # agent did not hang up: the server ends the call
    ("ended", CONTROL_URL, False, []),                  # already ended
    ("in-progress", None, False, []),                   # simulated call: no control URL
    ("in-progress", CONTROL_URL, True, []),             # a call back replaced this call
])
async def test_end_call_fallback(monkeypatch, status, control_url, replaced, expected):
    ended: list[str] = []

    async def fake_end_call(url):
        ended.append(url)

    monkeypatch.setattr(settings, "end_call_grace_seconds", 0.05)
    monkeypatch.setattr(vapi_client, "end_call", fake_end_call)
    session = _session(status=status, control_url=control_url)
    result = await caller.handle_tool_call(session, "report_outcome",
                                           {"status": "confirmed", "date_time": "2026-10-19T10:00",
                                            "read_back_confirmed": True})
    assert result == "ok"
    if replaced:
        session.call = {"vapi_call_id": "call-2", "control_url": CONTROL_URL, "status": "in-progress"}
    await asyncio.sleep(0.15)
    assert ended == expected
    logged = any("still open after the outcome" in e["text"] for e in session.timeline)
    assert logged == bool(expected)


@pytest.mark.anyio
async def test_control_refuses_non_vapi_host():
    with pytest.raises(vapi_client.ControlError):
        await vapi_client.end_call("https://evil.example.com/abc/control")

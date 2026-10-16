"""Scout: a failed live search shows plain words in the UI and logs the real error server side."""
import logging

import httpx
import pytest

from app.agents import scout
from app.config import settings
from app.session import Session
from app.tools import places as places_tool


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_live_search_failure_has_no_exception_name_in_timeline(monkeypatch, caplog):
    async def broken_search(query):
        request = httpx.Request("POST", "https://places.googleapis.com/v1/places:searchText")
        raise httpx.HTTPStatusError("403 Forbidden", request=request, response=httpx.Response(403, request=request))

    monkeypatch.setattr(places_tool, "search_places", broken_search)
    monkeypatch.setattr(settings, "demo_front_desk_number", "+10000000000")
    session = Session(id="s1", playbook="clinic", request={"what": "cleaning", "where": "Gulberg", "when": "next week"})

    with caplog.at_level(logging.WARNING, logger="app.agents.scout"):
        places = await scout.find(session)

    texts = [entry["text"] for entry in session.timeline]
    assert "Live search unavailable, showing demo businesses" in texts
    assert not any("Error" in t or "Exception" in t for t in texts)
    assert "HTTPStatusError" in caplog.text  # the real error stays in the server log
    assert places and places[0]["source"] == "seed"

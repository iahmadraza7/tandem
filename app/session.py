"""Session record and live event bus. Everything lives in memory and is gone on restart.

This file is a shared contract (see docs/CONTRACTS.md). Do not rename fields without
telling the other person.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

CARD_STATES = ("open", "answered", "expired", "closed")


@dataclass
class Card:
    id: str
    kind: str  # slot | price | data | payment | review | followup | other
    question: str
    options: list[str]
    state: str = "open"
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    answer: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    future: asyncio.Future | None = field(default=None, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "question": self.question,
            "options": self.options,
            "state": self.state,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "answer": self.answer,
            "meta": self.meta,
        }


@dataclass
class Session:
    id: str
    status: str = "new"  # new | clarifying | searching | choosing | consenting | calling | booking | done
    playbook: str | None = None
    request: dict[str, Any] = field(default_factory=dict)
    places: list[dict[str, Any]] = field(default_factory=list)
    selected_place: dict[str, Any] | None = None
    channel: str | None = None  # phone | web
    consent: dict[str, Any] = field(default_factory=lambda: {"fields": {}, "limits": {}})
    cards: dict[str, Card] = field(default_factory=dict)
    call: dict[str, Any] = field(default_factory=dict)  # vapi_call_id, control_url, status
    outcome: dict[str, Any] | None = None
    pending_offer: dict[str, Any] | None = None  # offer left open when the user did not answer in time
    timeline: list[dict[str, Any]] = field(default_factory=list)
    captions: list[dict[str, Any]] = field(default_factory=list)
    ics: bytes | None = field(default=None, repr=False)
    created_at: float = field(default_factory=time.time)
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)

    # ---- events -------------------------------------------------------------
    def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        payload = {"event": event, "session_id": self.id, "at": time.time(), "data": data or {}}
        for queue in list(self._subscribers):
            queue.put_nowait(payload)

    def log(self, agent: str, text: str) -> None:
        entry = {"agent": agent, "text": text, "at": time.time()}
        self.timeline.append(entry)
        self.emit("agent.step", entry)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    # ---- decision cards ------------------------------------------------------
    def open_card(
        self,
        kind: str,
        question: str,
        options: list[str],
        deadline_seconds: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Card:
        card = Card(
            id=uuid.uuid4().hex[:10],
            kind=kind,
            question=question,
            options=options,
            expires_at=(time.time() + deadline_seconds) if deadline_seconds else None,
            meta=meta or {},
        )
        try:
            card.future = asyncio.get_running_loop().create_future()
        except RuntimeError:  # no loop (unit tests of pure logic)
            card.future = None
        self.cards[card.id] = card
        self.emit("card.open", card.public())
        return card

    def answer_card(self, card_id: str, choice: str) -> bool:
        """First answer wins. Returns False if the card is not open any more."""
        card = self.cards.get(card_id)
        if card is None or card.state != "open":
            return False
        card.state = "answered"
        card.answer = choice
        if card.future is not None and not card.future.done():
            card.future.set_result(choice)
        self.emit("card.closed", card.public())
        return True

    def expire_card(self, card_id: str) -> None:
        card = self.cards.get(card_id)
        if card is None or card.state != "open":
            return
        card.state = "expired"
        if card.future is not None and not card.future.done():
            card.future.cancel()
        self.emit("card.closed", card.public())

    async def wait_for_card(self, card: Card, timeout: float) -> str | None:
        """Wait for the user's answer; None means no answer before the deadline."""
        if card.future is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(card.future), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.expire_card(card.id)
            return None

    # ---- snapshot ------------------------------------------------------------
    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "playbook": self.playbook,
            "request": self.request,
            "places": self.places,
            "selected_place": self.selected_place,
            "channel": self.channel,
            "consent": self.consent,
            "cards": [c.public() for c in self.cards.values()],
            "call": {k: v for k, v in self.call.items() if k != "control_url"},
            "outcome": self.outcome,
            "pending_offer": self.pending_offer,
            "timeline": self.timeline,
            "captions": self.captions[-20:],
            "has_calendar_file": self.ics is not None,
        }


class Store:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.by_call_id: dict[str, str] = {}

    def create(self) -> Session:
        session = Session(id=uuid.uuid4().hex[:12])
        self.sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    def link_call(self, call_id: str, session_id: str) -> None:
        self.by_call_id[call_id] = session_id

    def by_call(self, call_id: str | None) -> Session | None:
        if not call_id:
            return None
        session_id = self.by_call_id.get(call_id)
        return self.sessions.get(session_id) if session_id else None


store = Store()

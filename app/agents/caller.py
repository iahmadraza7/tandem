"""Caller: runs the live phone call through Vapi and handles its tool calls.

Flow per tool call from Vapi:
  ask_user        -> Guardian decides allow or ask_user -> decision card -> wait -> answer string
  report_outcome  -> Verifier -> one outcome -> calendar file if Confirmed
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app import playbooks
from app.agents import guardian, verifier
from app.config import settings
from app.session import Session, store
from app.tools import vapi_client

ASK_USER_TOOL = {
    "name": "ask_user",
    "description": (
        "Use for ANY offer or question you cannot answer from your instructions: a different time, a price, "
        "a deposit or card request, a personal detail you were not given, or anything else that commits the user. "
        "Never accept or share such things on your own."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "Short question for the user, e.g. 'They offer Tuesday 3 PM instead. Accept?'"},
            "options": {"type": "array", "items": {"type": "string"}, "description": "2 or 3 short answer options"},
            "kind": {"type": "string", "enum": ["slot", "price", "data", "payment", "other"]},
            "offered_value": {"type": "string", "description": "For slot: full ISO date and time like 2026-10-20T15:00. For price: the amount with currency."},
            "field": {"type": "string", "description": "For data: which detail they asked for, e.g. date_of_birth"},
        },
        "required": ["question", "kind"],
    },
}

REPORT_OUTCOME_TOOL = {
    "name": "report_outcome",
    "description": "Call exactly once before the call ends to report how the booking ended.",
    "parameters": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["confirmed", "tentative", "callback_needed", "failed"]},
            "date_time": {"type": "string", "description": "Full ISO date and time of the booking, e.g. 2026-10-20T15:00"},
            "read_back_confirmed": {"type": "boolean", "description": "True only if the front desk said yes to your read back"},
            "hold_expires": {"type": "string", "description": "If they hold a slot, until when"},
            "details": {"type": "object", "description": "Other confirmation fields, e.g. room type, rate, party size"},
            "notes": {"type": "string"},
        },
        "required": ["status", "read_back_confirmed"],
    },
}


def _now_local() -> datetime:
    return datetime.now(ZoneInfo(settings.timezone))


def system_prompt(session: Session) -> str:
    book = playbooks.get(session.playbook)
    values = {"user_name": settings.user_name, **{k: v for k, v in session.request.items() if isinstance(v, (str, int))}}
    approved = guardian.approved_fields(session.consent)
    limits = session.consent.get("limits") or {}
    shared = "\n".join(f"- {k}: {v}" for k, v in approved.items()) or "- (nothing beyond the user's first name)"
    followup = ""
    if session.pending_offer and session.pending_offer.get("user_answer"):
        offer = session.pending_offer
        followup = (
            "\nTHIS IS A CALL BACK. Earlier on a call, the business offered: "
            f"{offer.get('question')} (value: {offer.get('offered_value')}). The user has now answered: "
            f"{offer['user_answer']}. Say you are calling back about that and act on the user's answer.\n"
        )
    return f"""You are Tandem, an AI assistant phoning a business on behalf of {settings.user_name}.
Goal: {playbooks.fill(book['goal'], values)}
Request details: when = {session.request.get('when')}, where = {session.request.get('where')}, party size = {session.request.get('party_size')}.
Today is {_now_local():%A %d %B %Y, %H:%M} ({settings.timezone}).
{followup}
You may share ONLY these details:
{shared}
User limits: time window {limits.get('window_start')} to {limits.get('window_end')}, budget cap {limits.get('budget_cap')}.

Rules:
1. You already said you are an AI assistant calling for {settings.user_name}. If asked again, say so honestly.
2. Any offer or question that is not covered above (a different time, a price, a deposit or card, a personal detail
   not listed, anything that commits the user) goes to the ask_user tool. Never accept or share it yourself.
   Always give slot offers as a full ISO date and time.
3. Never give or ask for payment card or bank details. If they need payment, call ask_user with kind payment.
4. If ask_user returns no_answer: do not accept. Ask them to hold the offer for 15 minutes for {settings.user_name}.
   If they agree, report_outcome with status tentative and hold_expires; if not, status callback_needed. Then end politely.
5. Before ending, read back the confirmation fields ({', '.join(book['confirmation_fields'])}) with the full date,
   e.g. "So that's Tuesday, October 20 at 3 PM, correct?" Only if they say yes set read_back_confirmed true.
6. Call report_outcome exactly once, then thank them and end the call.
7. Keep every sentence short and natural. One question at a time."""


def build_assistant(session: Session) -> dict[str, Any]:
    book = playbooks.get(session.playbook)
    server_url = f"{settings.public_base_url}/vapi/webhook"
    if settings.webhook_token:
        server_url += f"?token={settings.webhook_token}"
    server = {"url": server_url, "timeoutSeconds": settings.vapi_tool_timeout_seconds}
    ask_tool = {
        "type": "function",
        "function": ASK_USER_TOOL,
        "server": server,
        "messages": [
            {"type": "request-start", "content": f"One moment please, let me check with {settings.user_name}."},
            {"type": "request-response-delayed", "content": "Thanks for waiting, just a moment.", "timingMilliseconds": 8000},
            {"type": "request-response-delayed", "content": f"{settings.user_name} is just checking, almost there.", "timingMilliseconds": 16000},
        ],
    }
    report_tool = {"type": "function", "function": REPORT_OUTCOME_TOOL, "server": server}
    opening = playbooks.fill(book["opening_line"], {"user_name": settings.user_name})
    if session.pending_offer and session.pending_offer.get("user_answer"):
        opening = f"Hi, I'm an AI assistant calling back on behalf of {settings.user_name} about the offer you made earlier."
    return {
        "name": "Tandem Caller",
        "firstMessage": opening,
        "model": {
            "provider": settings.vapi_model_provider,
            "model": settings.vapi_model,
            "messages": [{"role": "system", "content": system_prompt(session)}],
            "tools": [ask_tool, report_tool],
        },
        "server": server,
        "serverMessages": ["tool-calls", "status-update", "end-of-call-report", 'transcript[transcriptType="final"]'],
        "artifactPlan": {"recordingEnabled": False, "transcriptPlan": {"enabled": False}},
        "monitorPlan": {"controlEnabled": True, "controlAuthenticationEnabled": True},
        "maxDurationSeconds": 300,
    }


async def start_call(session: Session) -> dict[str, Any]:
    place = session.selected_place or {}
    number = place.get("phone")
    if not number:
        raise ValueError("The selected place has no phone number")
    session.status = "calling"
    session.log("Caller", f"Calling {place.get('name')}")
    if settings.simulate_calls:
        call_id = f"sim-{session.id}"
        session.call = {"vapi_call_id": call_id, "control_url": None, "status": "simulated"}
        store.link_call(call_id, session.id)
        session.log("Caller", "Simulated call: run scripts/simulate_call.py to play the front desk")
        session.emit("call.status", {"status": "simulated"})
        return session.call
    created = await vapi_client.create_call(build_assistant(session), number)
    call_id = created.get("id")
    session.call = {
        "vapi_call_id": call_id,
        "control_url": (created.get("monitor") or {}).get("controlUrl"),
        "status": created.get("status", "queued"),
    }
    if call_id:
        store.link_call(call_id, session.id)
    session.emit("call.status", {"status": session.call["status"]})
    return session.call


# ---- tool calls from Vapi ---------------------------------------------------

def _default_options(kind: str) -> list[str]:
    return {
        "slot": ["Accept", "Decline"],
        "price": ["Accept", "Decline"],
        "payment": ["I'll pay at the venue", "Decline"],
        "data": ["Don't share"],
    }.get(kind, ["Yes", "No"])


async def handle_ask_user(session: Session, args: dict[str, Any]) -> str:
    kind = args.get("kind", "other")
    decision = guardian.evaluate(session.consent, kind, args.get("offered_value"), args.get("field"))
    if decision.action == "allow":
        session.log("Guardian", f"Allowed without asking: {decision.reason}")
        if kind == "data":
            return f"allowed: you may share {args.get('field')}: {decision.value}"
        return f"allowed by the user's limits: accept {decision.value}"

    session.log("Guardian", f"Asking you: {decision.reason}")
    options = args.get("options") or _default_options(kind)
    if kind == "payment" and "Decline" not in options:
        options = _default_options("payment")
    card = session.open_card(
        kind=kind,
        question=args.get("question", "The business needs your decision."),
        options=options,
        deadline_seconds=settings.card_deadline_seconds,
        meta={"reason": decision.reason, "offered_value": args.get("offered_value"), "field": args.get("field"),
              "input": kind == "data"},
    )
    answer = await session.wait_for_card(card, timeout=settings.card_deadline_seconds)
    if answer is None:
        session.pending_offer = {
            "question": card.question, "kind": kind, "offered_value": args.get("offered_value"),
            "options": card.options, "user_answer": None,
        }
        session.log("Caller", "No answer in time; asking the business to hold the offer")
        session.emit("followup.available", session.pending_offer)
        return (
            "no_answer: the user did not answer in time. Do not accept on their behalf. Ask the business to hold "
            f"the offer for 15 minutes for {settings.user_name}; report tentative with hold_expires if they agree, "
            "otherwise callback_needed, then end politely."
        )
    if kind == "data":
        if answer.startswith("share:"):
            return f"user allows sharing {args.get('field')}: {answer[len('share:'):].strip()}"
        return f"user declined: do not share {args.get('field')}; say {settings.user_name} can provide it in person."
    if kind == "payment":
        return f"user chose: {answer}. Never take payment details; say {settings.user_name} will pay directly."
    return f"user chose: {answer}"


async def handle_tool_call(session: Session, name: str, args: dict[str, Any]) -> str:
    if name == "ask_user":
        return await handle_ask_user(session, args)
    if name == "report_outcome":
        verifier.apply(session, args, source="phone")
        return "ok"
    return f"unknown tool {name}"


def handle_status(session: Session, status: str) -> None:
    session.call["status"] = status
    session.emit("call.status", {"status": status})
    session.log("Caller", f"Call {status}")


def handle_end_of_call(session: Session, report: dict[str, Any]) -> None:
    session.call["status"] = "ended"
    session.emit("call.status", {"status": "ended", "reason": report.get("endedReason")})
    if session.outcome is None:
        verifier.apply(session, {"status": "failed", "read_back_confirmed": False,
                                 "notes": f"Call ended without an outcome ({report.get('endedReason')})"}, "phone")


def handle_transcript(session: Session, role: str, text: str) -> None:
    caption = {"speaker": "Front desk" if role == "user" else "Tandem", "text": text}
    session.captions.append(caption)  # in memory only, never written anywhere
    session.emit("caption", caption)

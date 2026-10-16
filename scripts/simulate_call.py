"""Play the front desk without a phone call: sends the same webhooks Vapi would.

Usage (server running with SIMULATE_CALLS=1):
    python scripts/simulate_call.py                 # clinic script, waits for your taps in the web app
    python scripts/simulate_call.py --scenario ignore   # you ignore the card: tests the hold and call back path
    python scripts/simulate_call.py --base http://localhost:8000
    python scripts/simulate_call.py --token <value>     # override WEBHOOK_TOKEN from .env

Each ask_user call blocks until you answer the card in the browser (or it times out),
exactly like a live call. The webhook token is read from .env and never printed.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Query params for /vapi/webhook only: {"token": ...} when a token is set
WEBHOOK_PARAMS: dict[str, str] = {}


def next_weekday(weekday: int, hour: int) -> str:
    today = datetime.now()
    days = (weekday - today.weekday()) % 7 or 7
    return (today + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat(timespec="minutes")


def send(client: httpx.Client, base: str, call_id: str, message: dict) -> dict:
    message = {**message, "call": {"id": call_id}}
    r = client.post(f"{base}/vapi/webhook", params=WEBHOOK_PARAMS, json={"message": message}, timeout=60)
    # Not raise_for_status(): its message contains the URL, and the URL contains the token
    if r.status_code == 401:
        raise SystemExit("Webhook refused the token (401). Check WEBHOOK_TOKEN in .env or pass --token.")
    if r.is_error:
        raise SystemExit(f"Webhook error {r.status_code}: {r.text[:200]}")
    return r.json()


def say(client, base, call_id, role, text):
    print(f"{'FRONT DESK' if role == 'user' else 'TANDEM':>10}: {text}")
    send(client, base, call_id, {"type": "transcript", "role": role, "transcriptType": "final", "transcript": text})
    time.sleep(1.2)


def tool(client, base, call_id, name, args):
    print(f"{'TOOL':>10}: {name} {args}")
    result = send(client, base, call_id, {"type": "tool-calls", "toolCallList": [
        {"id": f"tc-{time.time_ns()}", "function": {"name": name, "arguments": args}}]})
    answer = result["results"][0].get("result")
    print(f"{'RESULT':>10}: {answer}")
    return answer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--scenario", choices=["happy", "ignore"], default="happy")
    parser.add_argument("--token", default=os.getenv("WEBHOOK_TOKEN"),
                        help="webhook token (default: WEBHOOK_TOKEN from .env)")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    if args.token:
        WEBHOOK_PARAMS["token"] = args.token
    print(f"Webhook token: {'set' if args.token else 'not set'}")

    with httpx.Client() as client:
        print("Waiting for a simulated call (approve the consent card in the web app)...")
        while True:
            r = client.get(f"{base}/api/dev/latest")
            if r.status_code == 200:
                info = r.json()
                break
            time.sleep(1)
        call_id = info["call_id"]
        tuesday_3pm = next_weekday(1, 15)

        send(client, base, call_id, {"type": "status-update", "status": "ringing"})
        time.sleep(1)
        send(client, base, call_id, {"type": "status-update", "status": "in-progress"})
        say(client, base, call_id, "assistant", "Hi, I'm an AI assistant calling on behalf of Ahmad to book an appointment. Do you have a moment?")
        say(client, base, call_id, "user", "Sure. Mornings are full next week. I can do Tuesday at 3 PM.")
        slot = tool(client, base, call_id, "ask_user", {
            "question": "They offer Tuesday 3 PM instead. Accept?", "kind": "slot",
            "offered_value": tuesday_3pm, "options": ["Accept", "Decline"]})

        if slot.startswith("no_answer"):
            say(client, base, call_id, "assistant", "Could you hold Tuesday 3 PM for 15 minutes for Ahmad?")
            say(client, base, call_id, "user", "Sure, I'll hold it until half past.")
            tool(client, base, call_id, "report_outcome", {
                "status": "tentative", "read_back_confirmed": False, "hold_expires": "15 minutes", "date_time": tuesday_3pm})
        else:
            say(client, base, call_id, "user", "Great. Can I also get his date of birth for the file?")
            dob = tool(client, base, call_id, "ask_user", {
                "question": "They ask for your date of birth. It is not on your consent card. Share it?",
                "kind": "data", "field": "date_of_birth"})
            if "declined" in dob or dob.startswith("no_answer"):
                say(client, base, call_id, "assistant", "I'm not able to share that, Ahmad can provide it at the visit.")
            else:
                say(client, base, call_id, "assistant", "Sure, I have that for you.")
            say(client, base, call_id, "assistant", "So that's Tuesday at 3 PM for Ahmad, correct?")
            say(client, base, call_id, "user", "Yes, that's booked.")
            tool(client, base, call_id, "report_outcome", {
                "status": "confirmed", "date_time": tuesday_3pm, "read_back_confirmed": True})
        say(client, base, call_id, "assistant", "Thank you, goodbye.")
        send(client, base, call_id, {"type": "end-of-call-report", "endedReason": "assistant-ended-call"})
        print("Done.")


if __name__ == "__main__":
    main()

# Contracts

Shared by Ahmad and Daniyal. Change only together, in the same commit as the code.

## Session record (app/session.py)

| Field | Type | Meaning |
| --- | --- | --- |
| id | str | Session id |
| status | str | new, clarifying, searching, choosing, consenting, calling, booking, done |
| playbook | str | clinic, hotel, restaurant |
| request | dict | text, what, where, when, party_size, wants_booking |
| places | list | Scout shortlist (max 5): id, name, address, rating, reviews, phone, website, open_now, booking, channel, source |
| selected_place | dict | Checkpoint 1 |
| channel | str | phone or web |
| consent | dict | fields: {key: {value, share}}, limits: {window_start, window_end, tolerance_minutes, budget_cap, deposit_allowed, confirm_slots} |
| cards | dict | card_id to Card |
| call | dict | vapi_call_id, control_url (never sent to the browser), status |
| outcome | dict | status, date_time, details, hold_expires, reason, source |
| pending_offer | dict | Offer left open when the user did not answer; user_answer set on call back |
| timeline | list | {agent, text, at} |
| captions | list | {speaker, text}, last 20 shown, memory only |

Card: id, kind (slot, price, data, payment, review, followup, other), question, options, state (open, answered,
expired, closed), created_at, expires_at, answer, meta (reason, offered_value, field, input).
Rule: the first answer wins; answers to a card that is not open are rejected.

## HTTP routes (app/main.py)

| Method and path | Body | Returns |
| --- | --- | --- |
| GET /health | | which integrations are configured |
| POST /api/sessions | {text, playbook?} | session snapshot |
| POST /api/sessions/{id}/clarify | {answers: {where, when, what, playbook}} | session snapshot |
| GET /api/sessions/{id}/state | | session snapshot (polling fallback) |
| GET /api/sessions/{id}/events | | server sent events |
| POST /api/sessions/{id}/select | {place_id} | consent template {fields: [{key, label, value, share}], limits} |
| POST /api/sessions/{id}/consent | {fields: {key: {value, share}}, limits} | {ok}; starts the call or web booking |
| POST /api/sessions/{id}/answer | {card_id, choice} | {accepted}; data cards send "share:<value>" to share |
| POST /api/sessions/{id}/callback | {answer} | {ok}; calls back about pending_offer |
| GET /api/sessions/{id}/calendar.ics | | calendar file, confirmed only |
| GET /api/dev/latest | | simulator helper, only with SIMULATE_CALLS=1 |
| POST /vapi/webhook?token= | Vapi server message | tool results or {ok} |
| /mcp/ | MCP streamable HTTP | MCP tools |

## Live events (server sent events)

Every event: {event, session_id, at, data}. Event names:

| Event | data |
| --- | --- |
| snapshot | full session snapshot (first event on connect) |
| agent.step | {agent, text, at} |
| clarify | {missing: [..], request} |
| shortlist | {places} |
| consent.request | {fields, limits} |
| call.status | {status} |
| card.open | Card |
| card.closed | Card (answered or expired) |
| caption | {speaker, text} |
| followup.available | pending_offer |
| outcome | outcome |
| error | {where, message} |

## Vapi tools (server tools on POST /vapi/webhook)

Limits: confirm_slots (bool, default true; a missing key counts as true): every offered time goes to the user as a
slot card, even inside the window (reason "Your preferred time is available."). Only false lets the Guardian accept a
time inside the window alone.

ask_user(question, options[], kind: slot|price|data|payment|other, offered_value, field) returns one of:
- `allowed by the user's limits: accept <value>`
- `allowed: you may share <field>: <value>`
- `user chose: <option>`
- `user allows sharing <field>: <value>` / `user declined: do not share <field> ...`
- `no_answer: ...` (after CARD_DEADLINE_SECONDS; the agent asks the business to hold the offer)

report_outcome(status, date_time, read_back_confirmed, hold_expires, details, notes) returns `ok`.

endCall: Vapi built-in tool ({"type": "endCall"} in model.tools). Its blocking request-start message says
"Thank you for your help. Goodbye." before the call ends. The prompt calls it right after report_outcome.
Server fallback: END_CALL_GRACE_SECONDS (10) after report_outcome, if the same call is still active, the server POSTs
{"type": "end-call"} to the monitor controlUrl (Bearer VAPI_PUBLIC_API_KEY).

Vapi waiting lines on ask_user: request-start, then request-response-delayed at 8 s and 16 s.

## MCP tools (app/mcp_server.py)

start_request, clarify_request, choose_place, approve_consent, get_status, answer_card.

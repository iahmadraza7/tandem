# Tandem

Human in the loop calling agent for the Agentika 2.0 hackathon (theme: human in the loop).
The agent phones a business (or books through its booking API) for the user, and hands every
committing decision back to the user live, mid call, as a decision card.

Team: Ahmad Raza (agents, call, MCP) and Daniyal (web app, web channel, deploy).
Deadline: submission 17 Oct 2026, 12:45 PM Pakistan time. Feature freeze 10:30 AM.

Read these before changing anything in their area:
- docs/CONTRACTS.md: session record, routes, live events, Vapi tools. Shared by both people.
- docs/DECISIONS.md: verified API facts and why we chose them. Do not re-guess APIs; check here first.
- docs/TASKS.md: what is done, what is next, who owns it. Update it when you finish a task.

## Hard rules (the product depends on these)
- Nothing is persisted: no database, no files written at runtime, no transcript or recording storage.
  Session state lives in memory (app/session.py) and is lost on restart. Live captions stay in memory only.
- Secrets only from environment variables (.env). Never hard code, log or commit a key or token.
- The agent never shares a field that is not ticked on the consent card and never accepts a time, price,
  deposit or anything committing outside the user's limits. All such checks go through app/agents/guardian.py.
  Guardian rules are pure Python; do not move consent decisions into a prompt.
- Payments are never taken, read out or relayed by the agent. A payment request is always a decision card.
- Every call or web booking ends in exactly one outcome: confirmed, tentative, callback_needed, failed
  (app/agents/verifier.py). Only confirmed with an exact date and time writes the calendar file.
- The agent always discloses it is an AI at the start of a call.
- Web channel uses Cal.com API v2 only. Never automate a booking web page with a browser
  (Cal.com terms section 4.3(d) ban automated access other than the documented API).

## Architecture (six agents, one FastAPI service)
- app/agents/concierge.py: understands the request, picks the playbook (clinic, hotel, restaurant), asks for missing details. Claude Sonnet, keyword fallback offline.
- app/agents/scout.py: finds places (Google Places, seed list fallback), ranks, picks channel: phone, web, none.
- app/agents/caller.py: builds the Vapi assistant, starts calls, handles Vapi tool calls `ask_user` and `report_outcome`.
- app/agents/web_booker.py: Cal.com slots, slot card, review card, booking.
- app/agents/guardian.py: allow or ask_user for data, slot, price, payment.
- app/agents/verifier.py: outcome classification and calendar file.
- app/service.py: use cases shared by HTTP routes (app/main.py) and the MCP server (app/mcp_server.py).
- app/session.py: Session, Card, event bus. Cards: first answer wins; expired cards ignore answers.
- app/playbooks/*.yaml: one file per niche. Adding a niche = adding a YAML file.
- web/: single page (index.html, app.js, styles.css). Live events by server sent events, 1 s polling fallback.
- scripts/simulate_call.py: plays the front desk by sending the webhooks Vapi would send. Use it instead of real calls.

## Commands
- Setup: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cp .env.example .env
- Run: uvicorn app.main:app --reload --port 8000   then open http://localhost:8000
- Simulated call: set SIMULATE_CALLS=1 in .env, start a booking in the browser, then python scripts/simulate_call.py
  (add --scenario ignore to test the no answer path)
- Tests: pytest -q   (must pass before every commit)
- MCP endpoint: <PUBLIC_BASE_URL>/mcp/  (trailing slash; /mcp redirects)

## Gotchas already hit
- FastAPI routes that touch sessions, cards or spawn agent work must be `async def`. A sync route runs in a
  thread pool with no event loop: asyncio.create_task fails and card futures break.
- mcp 2.x removed FastMCP. Use `from mcp.server import MCPServer`. The app lifespan must run
  `mcp.session_manager.run()` (already in app/main.py).
- FastAPI has built in server sent events: `from fastapi.sse import EventSourceResponse, ServerSentEvent`.
- Vapi tool replies must be HTTP 200 with {"results":[{"toolCallId": ..., "result": "<string>"}]}.
- Anything that posts to /vapi/webhook must send ?token=<WEBHOOK_TOKEN> when it is set, or it gets 401
  (Vapi server URL, scripts/simulate_call.py). Tests set settings.webhook_token to None instead. Never print the token.
- CARD_DEADLINE_SECONDS must stay below VAPI_TOOL_TIMEOUT_SECONDS (22 < 25), so we answer before Vapi times out.
- Vapi payload shapes in app/agents/caller.py and app/tools/vapi_client.py follow the docs but are NOT yet tested
  on a live call. Same for app/tools/calcom.py and app/tools/places.py. Mark a module tested in docs/TASKS.md
  only after a live run.

## How to work
- One module per prompt. Plan first, then code, then tests, then run pytest.
- Keep changes inside your own modules (ownership in docs/TASKS.md); change a contract only after telling the other person
  and updating docs/CONTRACTS.md in the same commit.
- Short sentences in user facing text. No emoji in the UI.
- Do not add dependencies without a reason written in docs/DECISIONS.md.

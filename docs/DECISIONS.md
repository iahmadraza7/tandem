# Decisions and verified facts

Checked against official docs on 16 Oct 2026. If something here turns out wrong on a live run, fix it here first.

## Decisions

| Decision | Why |
| --- | --- |
| Plain Python FastAPI, no n8n | Full control of timeouts, retries and error states (technical execution is 25 of 100 points); fewer cloud credits |
| Six small agents, one service | Each agent one job; judges see orchestration on the timeline; two people can work in parallel |
| Guardian rules in Python, model only for unclear cases | Consent must be enforced, not suggested to a model |
| Cal.com API v2 for the web channel, no browser automation | Cal.com terms section 4.3(d) ban automated access other than the documented API; API is also more reliable |
| Calendar as an .ics file | No OAuth setup; works on every calendar app |
| Vapi for the call, existing Twilio number imported | Fastest path to a reliable live call; team already owns the number |
| No free Gemini | Google says free tier content may be used to improve products and read by human reviewers |
| Nothing persisted | Privacy promise; simpler build |
| Simulator for development | Real calls cost Twilio minutes; the simulator exercises the same webhook code |
| Playwright (Python) for browser tests, dev only (requirements-dev.txt) | The stage flow (sticky cards, polling, stale session banner, phone width) can only be checked in a real browser. Python keeps it in pytest. Not in requirements.txt or the Docker image; skipped unless RUN_E2E=1 so normal pytest stays fast and free |
| Webhook token stays in the query string (?token=) for now; the access log masks it (app/log_filters.py) | Known to work with any server URL. Moving it to a header needs the Vapi docs checked first (custom headers on the server URL); until then the filter keeps it out of logs |

## Verified facts

### Anthropic
- Model IDs: `claude-sonnet-5-5` ($2 / $10 per million tokens in/out), `claude-haiku-5-5` (from $0.10 / $0.50). platform.claude.com/docs/en/about-claude/models/overview
- Python SDK `anthropic` 1.15.0.

### Vapi (docs.vapi.ai)
- Outbound call: POST https://api.vapi.ai/call with {phoneNumberId, customer: {number}, assistant | assistantId}. Bearer API key.
- Tool calls arrive as message.type "tool-calls" with toolCallList [{id, function: {name, arguments}}].
  Reply HTTP 200 {"results":[{"toolCallId", "result": "<string>"}]}; use "error" instead of "result" on failure.
- Tool timeout `server.timeoutSeconds`: default 20, min 1, max 300.
- Waiting messages: request-start, request-response-delayed (timingMilliseconds 100 to 120000), request-complete, request-failed.
- Live control: create call response has monitor.controlUrl; POST {"type":"say","content":...}, {"type":"add-message",...},
  {"type":"end-call"}, transfer. Control auth is OFF by default: set monitorPlan.controlAuthenticationEnabled true.
- Server messages: transcript is not sent by default; add "transcript" or transcript[transcriptType="final"] to serverMessages.
- No storage: artifactPlan.recordingEnabled false, artifactPlan.transcriptPlan.enabled false.
- Anthropic models listed in docs: claude-sonnet-5, claude-sonnet-4-6, claude-haiku-4-5-20251001 and others.
  `claude-haiku-5-5` appears in the API spec but not the docs page: TEST IT. No Sonnet 5.5 in Vapi.
  Fallback: provider custom-llm with an OpenAI compatible URL.
- maxDurationSeconds default 600. Pay as you go: 4 concurrent calls.
- Pricing: $0.05/min platform; Deepgram about $0.0095/min; ElevenLabs about $0.015 to $0.024/min; browser test calls
  have no telephony charge. Signup credit $10 (docs) or $5 (marketing page): check the dashboard.
- Importing a Twilio number replaces its voice webhook with Vapi's. Pass SMS off to keep messaging untouched.
- transferCall tool exists; destinations [{type: number, number, message}].

### Twilio
- A number attached to an Elastic SIP Trunk ignores its voice webhook: remove it from the trunk before importing to Vapi
  (Console: Elastic SIP Trunking, Manage, Trunks, <trunk>, Numbers, trash icon).
- Trial accounts block Stream and similar media verbs and call only verified numbers: upgrade before testing Vapi.
- Geo permissions: Voice, Settings, Geo permissions, tick Pakistan, Save (Owner or Admin role).
- Pakistan mobile $0.18/min, landline $0.155/min. US local number $1.15/month.

### Google Places API (New) Text Search
- POST https://places.googleapis.com/v1/places:searchText, headers X-Goog-Api-Key, X-Goog-FieldMask (required).
- rating, userRatingCount, phone, websiteUri, opening hours = Enterprise SKU: 1,000 free per month, then $35 per 1,000.
- Billing account required.

### Cal.com
- Free plan: 1 user, unlimited event types. Booking page cal.com/<username>/<slug>.
- API v2: GET /v2/slots (header cal-api-version 2024-09-04; eventTypeSlug + username, start, end, timeZone).
  POST /v2/bookings (header cal-api-version 2026-02-25; start in UTC ISO, eventTypeSlug + username, attendee {name, email, timeZone}).
  Authorization optional on create booking. Base URL https://api.cal.com/v2 seen only in an example: confirm.

### Libraries
- fastapi 0.143.2 with built in server sent events (fastapi.sse).
- mcp 2.3.0: MCPServer (FastMCP removed); streamable HTTP; mount with lifespan session_manager.run().
- icalendar 7.3.0.
- playwright 1.64.0 (dev only): browser binary installed with `python -m playwright install chromium`.

### Alternate Clouds (docs.alternatefutures.ai)
- CLI `acc` (npm i -g @alternatefutures/acc). Safest deploy: own Docker image, `--kind docker --image <img>:<fixed tag> --port 8000`.
  Moving tags like latest are refused; GHCR images must be public.
- Env vars: acc services env set <svc> KEY VALUE. Logs: acc services logs <id> --tail N.
- Public HTTPS URL https://<slug>-app.alternatefutures.ai. No custom domains yet.
- Billing hourly; a deploy needs at least 1 hour of balance and $1. Prices only via `acc regions`.
- Server sent events through their proxy: not documented. The web app falls back to polling.

## Still unverified (test on day 1)
- Vapi accepts claude-haiku-5-5 on a live call.
- Exact Vapi payload for tools inside a transient assistant (model.tools with server and messages).
- Vapi behaviour when the line is silent while a tool waits.
- Cal.com free plan API key; booking without a key.
- Alternate Clouds keeps an event stream open.

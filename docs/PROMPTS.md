# Claude Code prompts

Open the repo folder in Claude Code. CLAUDE.md loads automatically. Paste one prompt at a time; read the plan before
letting it write code.

## 0. Kickoff (both, once)
```
Read CLAUDE.md, docs/CONTRACTS.md, docs/DECISIONS.md and docs/TASKS.md. Then:
1. Create the venv, install requirements, copy .env.example to .env (leave keys empty), run pytest -q and report.
2. Start the server with SIMULATE_CALLS=1, open http://localhost:8000 in my browser, and tell me the exact steps to
   run one simulated clinic booking with scripts/simulate_call.py.
3. Summarise in 10 lines what is built, what is not tested live, and what my next 3 tasks are according to
   docs/TASKS.md. I am <Ahmad|Daniyal>.
Do not change any code in this step.
```

## Ahmad: first live call (Stage 1)
```
My .env now has VAPI_API_KEY, VAPI_PHONE_NUMBER_ID, ANTHROPIC_API_KEY, PUBLIC_BASE_URL (tunnel URL),
WEBHOOK_TOKEN and DEMO_FRONT_DESK_NUMBER, and SIMULATE_CALLS=0.
Goal: one real outbound call through Vapi using app/agents/caller.py build_assistant().
1. Write scripts/check_vapi.py that prints the assistant JSON caller.build_assistant() would send for a clinic session
   and validates it against Vapi's current API docs (docs.vapi.ai, CreateCallDTO, model.tools, server, messages,
   artifactPlan, monitorPlan). List any field names that do not match and fix them in caller.py.
2. Run one real call. If Vapi rejects the payload, read the error, fix the payload, and update docs/DECISIONS.md.
3. If claude-haiku-5-5 is rejected by Vapi, switch VAPI_MODEL to a model Vapi lists and note it in DECISIONS.md.
Keep the Guardian and Verifier untouched. Run pytest after every change.
```

## Ahmad: tune the Caller prompt
```
Here are notes from 3 real test calls: <paste what went wrong>.
Improve system_prompt() in app/agents/caller.py so that the agent: keeps sentences short, always reads back the
full date, always calls ask_user before accepting anything new, asks for a 15 minute hold on no_answer, and calls
report_outcome exactly once. Do not move any consent logic into the prompt. Show me a diff first.
```

## Ahmad: MCP with Claude Desktop
```
The app is deployed at <cloud URL>. Check that <cloud URL>/mcp/ answers MCP initialize and tools/list
(transport security allowed_hosts must include the cloud host). Then give me the exact steps to add it in
Claude Desktop as a custom connector, and a test prompt that runs a full clinic booking through the MCP tools.
```

## Daniyal: web app polish
```
Improve web/ for a stage demo on a projector and a phone screen, without changing any route or event name
(docs/CONTRACTS.md). Requirements: decision cards large and impossible to miss, with the countdown bar; agent timeline
readable from the back of a room; channel badges clear; outcome screen shows status, full date and the calendar link.
Keep it plain HTML, CSS and JavaScript. Test it with a simulated call and show me screenshots.
```

## Daniyal: Places live search
```
GOOGLE_PLACES_API_KEY is set. Test app/tools/places.py search_places() on 3 queries. Confirm the field mask works
with Places API (New) Text Search and the response mapping is right. Keep the seed list as fallback when the key is
missing or a request fails. Add a test that mocks the HTTP call.
```

## Daniyal: Web Booker on Cal.com
```
CALCOM_USERNAME, CALCOM_EVENT_SLUG and CALCOM_ATTENDEE_EMAIL are set (CALCOM_API_KEY if available).
Test app/tools/calcom.py get_slots() and create_booking() against the real event type. Fix headers, versions or
response parsing using Cal.com API v2 docs. Never use a browser to book. Then run the online clinic flow in the
web app end to end and confirm the booking appears in the Cal.com dashboard.
```

## Daniyal: deploy to Alternate Clouds
```
Build the Docker image from the Dockerfile, push it to GitHub Container Registry as public with a fixed tag
(not latest), and give me the exact acc CLI commands to deploy it on Alternate Clouds with port 8000 and all .env
values as secrets (never print secret values). After deploy, check /health and that
/api/sessions/{id}/events stays open for 60 seconds; if it does not, tell me and we rely on the polling fallback.
```

## Any time: before a commit
```
Run pytest -q. Review my staged diff against the hard rules in CLAUDE.md (no persistence, no secrets, Guardian
owns consent decisions, one outcome per call, payments never handled). List any violation. Then update
docs/TASKS.md for what I finished.
```

# Tasks

Legend: [x] done and tested, [~] written but not tested live, [ ] to do. Update this file when you finish something.

## Already in the scaffold (16 Oct, tested locally with the simulator, 20 tests passing)
- [x] Session record, cards (first answer wins, expiry), event bus
- [x] Playbooks: clinic, hotel, restaurant (YAML)
- [x] Guardian rules: data, slot window with tolerance, price cap, payment always to user (10 tests)
- [x] Verifier: four outcomes, read back required, calendar file only on confirmed (5 tests)
- [x] Concierge with keyword fallback; clarify flow for missing details
- [x] Scout with seed list and channel choice
- [x] Fresh clone works with an empty DEMO_FRONT_DESK_NUMBER (Ahmad, 16 Oct): flow tests set their own number;
  in simulate mode the seeded businesses get +10000000000 (never dialled). 20 tests pass with the variable unset.
- [x] WEBHOOK_TOKEN (Ahmad, 16 Oct): flow tests clear the token and all live API keys, so they pass with a full .env
  and make no network calls; simulate_call.py sends ?token= from .env or --token (checked: wrong token gets a 401 message).
- [x] Vapi webhook handler: ask_user waits for the card, no_answer path, report_outcome, status, transcript, end of call
- [x] Live events (server sent events) and polling fallback route
- [x] Web app: request, clarify, shortlist, consent card with limits, live call, captions, decision cards with countdown, follow up, outcome, calendar link
- [x] MCP server at /mcp/ with 6 tools (initialize and tools/list checked)
- [x] Simulator: happy path and ignore path, end to end
- [~] Caller: Vapi assistant config and POST /call (not tested on a live call)
- [~] Concierge with Claude Sonnet. 16 Oct: claude-sonnet-5-5 answers and parses on 3 of the 10 example requests
  (curry: restaurant, asks where and when; dentist: clinic, "dental cleaning"; hotel: hotel, party 2, late check in kept)
- [~] Places API search (needs key)
- [~] Web Booker with Cal.com API v2 (needs account)
- [~] Dockerfile (not built yet)

## Frontend, 17 Oct (Ahmad). [~] = passed in simulate mode only (browser e2e on port 8011), not on a live call
- [~] Consent window defaults to the next weekday 09:00 to 12:00; Latest before Earliest shows an error and blocks Approve
- [~] Server restart: 404 on the session stops polling and shows "This session ended..." with a reset button
- [~] While calling or booking, /state is polled every 2 s next to the event stream; each card rendered once by id,
  switched to answered or expired from state (cards arrive even if a tunnel buffers the stream). Not yet tried through a real tunnel
- [~] No exception names on the timeline (Scout, Concierge, Web Booker, background task errors); real errors in the server log
- [~] Decision card: large, sticky at the top, kind label, big equal option buttons, countdown, chime, "Decision needed" tab title
- [~] Outcome panel: large status, full date, calendar link only when confirmed, hold details and Call back for an open offer
- [~] Projector sizes (timeline 16 px) and phone width 390 px without horizontal scroll
- Won't do: open an existing session from a second device by link (decided 17 Oct). Anyone with the link could
  answer cards; not needed for the demo. e2e scenario e stays skipped.

## Stage 0: setup (exit: one browser test call and one real call work)
Ahmad
- [ ] Twilio: check for the Trial banner; upgrade if present
- [ ] Twilio: remove the number from the "testing" SIP trunk
- [ ] Twilio: geo permissions, tick Pakistan; permission check on Daniyal's number
- [ ] Vapi: account, check credit, import the Twilio number (SMS off), copy the phone number ID to .env
- [ ] Vapi: one dashboard test call with model anthropic / claude-haiku-5-5
Daniyal
- [ ] Repo on GitHub from this folder; both clone it
- [ ] Cal.com account, event type "Dental cleaning, 30 min"; try creating an API key
- [ ] Google Cloud project, Places API (New), billing, key (optional, seed list works without)
- [ ] Alternate Clouds: acc CLI, deploy this image once, check /health and that /api/sessions/{id}/events stays open
- [ ] Local tunnel (for example cloudflared) for Vapi webhooks during development

## Stage 1: P0 live phone path (exit: demo clinic booking on a real call, with the Guardian block)
- [x] Ahmad: real call through Vapi (17 Oct: phone rang, agent talked, booking confirmed)
- [~] Ahmad: end the call after report_outcome: endCall tool with a goodbye, server end-call fallback after 10 s.
  Assistant JSON validated on the Vapi API (create and delete, no call); needs VAPI_PUBLIC_API_KEY; not yet live
- [~] Ahmad: "Ask me before confirming any time" (confirm_slots, default on): preferred time asked first, every
  offered time goes to a card. Guardian, flow and browser tests pass in simulate mode; not yet live
- [ ] Ahmad: tune the Caller prompt on 5 real calls (read back, holding, hold request on no_answer)
- [ ] Ahmad: Concierge on Claude Sonnet; verify JSON parsing on 10 example requests
- [~] Daniyal: polish the web app for the stage (big cards, readable timeline, phone width). Done by Ahmad 17 Oct;
  passed in simulate mode only (see "Frontend, 17 Oct" below). Daniyal: review on the real screen and projector
- [ ] Daniyal: Places live search behind the seed list

## Stage 2: deploy (exit: same run from the cloud URL)
- [ ] Daniyal: build and push image with a fixed tag, deploy with acc, set env secrets
- [ ] Ahmad: PUBLIC_BASE_URL and WEBHOOK_TOKEN set; Vapi webhooks reach the cloud

## Stage 3: P1 (exit: demo script steps 6 and 7 work)
- [ ] Daniyal: Web Booker against the real Cal.com event type
- [ ] Ahmad: Claude Desktop custom connector to <cloud URL>/mcp/, full booking through MCP
- [ ] Ahmad: hotel and restaurant playbooks checked on a call each

## Stage 4: P2 (only if everything above is green)
- [ ] Take over button: transfer the call to the user's phone through the control URL
- [ ] Trust receipt screen: what was shared, what you decided, outcome
- [ ] Late answer: say the answer through the control URL instead of a call back, if the call is still live

## Stage 5: freeze (10:30 AM day 2)
- [ ] Backup screen recording of the full demo
- [ ] Two timed rehearsals with room audio
- [ ] Submission description and README final

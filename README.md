# Tandem

Human in the loop calling agent. Tandem phones a business (or books through its booking API) for you, and the
moment the business asks something only you can decide, you get a one tap card while the call is still live.

Built for Agentika 2.0 (theme: human in the loop) by Ahmad Raza and Daniyal.

## Run locally
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # SIMULATE_CALLS=1 works with no keys at all
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000, ask for "Dentist near Gulberg Lahore for a cleaning next week", pick the Phone clinic,
approve the consent card, then in a second terminal:
```bash
python scripts/simulate_call.py              # or --scenario ignore
```
Answer the cards in the browser as they appear.

Tests: `pytest -q`

## Real calls
Set SIMULATE_CALLS=0 and fill VAPI_API_KEY, VAPI_PHONE_NUMBER_ID, ANTHROPIC_API_KEY, DEMO_FRONT_DESK_NUMBER,
PUBLIC_BASE_URL (public URL Vapi can reach) and WEBHOOK_TOKEN in .env.

## How it works
Six agents in one FastAPI service: Concierge (request and playbook), Scout (places and channel), Caller (Vapi call),
Web Booker (Cal.com API v2), Guardian (consent and limits), Verifier (one outcome, calendar file). Three playbooks in
app/playbooks: clinic, hotel, restaurant. MCP server at /mcp/ for Claude Desktop.

Docs: docs/PRODUCT.md, docs/CONTRACTS.md, docs/DECISIONS.md, docs/TASKS.md, docs/DEMO.md, docs/TESTING.md,
docs/PROMPTS.md.

## Privacy
No recordings, no transcripts, no database. The agent discloses it is an AI and shares only what you approve.

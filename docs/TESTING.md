# Testing

Automated: `pytest -q` (Guardian, Verifier, end to end webhook flow, Scout, log filter). Must pass before every commit.
It makes no network calls and does not depend on .env.

Simulated call: SIMULATE_CALLS=1, start a booking in the browser, run `python scripts/simulate_call.py`
(or `--scenario ignore`).

## Browser end to end (simulate mode)

    pip install -r requirements-dev.txt && python -m playwright install chromium   # once
    RUN_E2E=1 pytest -q tests/e2e

The test starts its own server on port 8011 (port must be free) with SIMULATE_CALLS=1 and every external key
cleared, so nothing real is called, and stops it at the end. scripts/simulate_call.py plays the front desk.
Card deadline is 8 s in this run. Screenshots go to /tmp/tandem-shots/ (not the repo). Takes about a minute.

Passed in simulate mode, 17 Oct (not live):
- [x] a) Happy: clinic, phone place, approve, Accept the time card, Don't share the date of birth, Confirmed,
  full date, calendar file downloads
- [x] a2) Preferred time offered (simulate_call.py --scenario preferred): card "Your preferred time is available.",
  Accept, Confirmed. The consent box "Ask me before confirming any time" is ticked by default
- [x] b) Ignore: no tap, card expires, Tentative, "Hold: 15 minutes", no calendar link, Call back with an answer
- [x] c) Server restart: stale session banner in view, polling stops, reset button (mid call and on the shortlist)
- [x] d) Phone 390x844: no horizontal scroll, card buttons fully on screen, Confirmed
- [ ] e) Two browsers on one session, first tap wins: skipped on purpose, no session link (see DECISIONS.md)
  (first tap wins is covered at the API level in tests/test_flow.py)

Live scenarios (tick when run on a real call or the real Cal.com event):

Phone
- [ ] Preferred time (box ticked): agent asks for it first, card "Your preferred time is available.", Accept, Confirmed
- [ ] After report_outcome: one goodbye, call hangs up by itself; if not, the server ends it within 10 s
- [ ] Slot inside limits with the box unticked: Guardian accepts alone, read back, Confirmed, calendar file
- [ ] Slot outside limits: card, Accept, Confirmed
- [ ] Date of birth asked: Guardian card, Don't share, agent says it cannot share
- [ ] Date of birth card ignored: agent does not share it, says Ahmad can give it in person, no open offer on screen
- [ ] Card ignored: holding lines at 8 s and 16 s, hold request, Tentative; open offer, call back, Confirmed
- [ ] Front desk refuses to hold: Callback needed, no calendar file
- [ ] "We'll call you back": Tentative, no calendar file
- [ ] No answer or busy: Failed, next option offered
- [ ] Card or deposit requested: payment card, no payment details given
- [ ] "Next Tuesday": read back uses the full date, correct day
- [ ] Hotel: price above cap raises a card

Web
- [ ] Slot card, review card, booking visible in Cal.com
- [ ] Review rejected: nothing booked

System
- [ ] Tap as a card expires: card ends in one state
- [ ] Laptop and phone open: first tap wins
- [ ] Claude Desktop runs a booking through /mcp/
- [ ] Full demo on the cloud URL under 3 minutes

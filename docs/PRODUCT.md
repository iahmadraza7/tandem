# Product

## One line
Tandem is an AI calling agent that books with businesses for you and pulls you into the call the moment a
decision is yours to make.

## Submission description
Tandem is a human in the loop voice agent for businesses that still run on phone calls. One engine, three
playbooks (clinics, hotels, restaurants). It finds options, calls in real time or books through an official booking
API, hands every committing decision to the user mid call as a one tap card, and confirms the booking with a read
back before adding it to the calendar.

## Problem
Booking a dentist, a hotel special request or a group dinner still means a phone call, and a call is never one
question: the slot is full, the front desk offers something else, asks for details or a deposit. Autonomous calling
agents either freeze or guess. Google's Ask for Me gathers prices and availability but does not book with you in the
call; Pine AI runs calls without continuous human involvement.

## Our answer: keep the human in the call
Three checkpoints in every playbook:
1. You pick the place (agent ranks by rating and reviews, never claims "best").
2. Consent card: exactly what the agent may say, plus your limits (time window, flex minutes, budget cap).
3. Live decision cards during the call for anything outside the plan. Inside your limits the Guardian decides alone
   (adjustable autonomy); outside them it asks you.

If you do not answer in time the agent never guesses: it asks the business to hold the slot, ends politely, and calls
back when you decide.

## Six agents
Concierge, Scout, Caller, Web Booker, Guardian, Verifier. See CLAUDE.md for files.

## Scope for the hackathon
In: three playbooks, English, one call at a time, phone channel, Cal.com API web channel, new bookings, payments
handed to the user. Out: other languages, IVR menus, rescheduling, parallel calls, booking sites without an API.

## Privacy
Nothing stored: no recordings, no transcripts, no database. Vapi recording and transcript storage switched off.
The agent discloses it is an AI and shares only consented fields. We make no compliance certification claims.

## Judge questions
- Google already does this. It gathers information; it does not finish the booking with you in the call.
- Why not fully autonomous? A different time, a higher rate, a deposit or a personal detail is a commitment.
- What if I do not answer? Hold request, polite end, call back. Never a guess.
- How do you know it is booked? Read back of the exact date and time; confirmed only after the front desk says yes.
- Is it legal to call with AI? Every call discloses AI and nothing is recorded; we make no jurisdiction claims.
- How does it make money? Consumer subscription or per booking fee, then employers and insurers (hypotheses).
- Where is MCP? Tandem's tools are an MCP server; Claude Desktop can run the same flow.
- Why three niches? The hard part is identical; a niche is a YAML playbook.

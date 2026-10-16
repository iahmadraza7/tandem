// Tandem web app: one page, live events, and polling as a safety net.
// Every state change goes through renderAll(snapshot), so events and polling cannot disagree.
const $ = (sel) => document.querySelector(sel);

const LIVE_STATUSES = new Set(["calling", "booking"]);
const KIND_LABEL = { slot: "Time", price: "Price", data: "Personal detail", payment: "Payment", review: "Review", followup: "Follow up", other: "Decision" };
const OUTCOME_LABEL = { confirmed: "Confirmed", tentative: "Tentative", callback_needed: "Callback needed", failed: "Failed" };
const CALL_LABEL = { simulated: "Simulated call. Run the front desk script.", queued: "Dialling", ringing: "Ringing", "in-progress": "On the call", forwarding: "Transferring", ended: "Call ended" };

let sessionId = null;
let source = null;
let streamFailed = false; // event stream cut by a proxy: poll every second instead
let pollTimer = null;
let pollEvery = 0;
let refreshing = false;
let lastStatus = null;
let clarifyKey = null;
let outcomeKey = null;
let captions = [];
const cardEls = new Map(); // card id -> element; each card is rendered once
const timelineKeys = new Set();

class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new HttpError(res.status, (await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

// Session routes answer 404 only when the server no longer has the session (nothing is persisted).
async function sessionApi(path, body) {
  try {
    return await api(`/api/sessions/${sessionId}${path}`, body);
  } catch (err) {
    if (err.status === 404) sessionEnded();
    throw err;
  }
}

function show(id, on = true) { $(id).classList.toggle("hidden", !on); }
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
const pad = (n) => String(n).padStart(2, "0");

// "2026-10-20T15:00" -> "Tuesday, 20 October 2026, 3:00 PM". Anything that is not a date is shown as is.
function longDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(String(value ?? ""))) return String(value ?? "");
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const weekday = d.toLocaleDateString("en-GB", { weekday: "long" });
  const month = d.toLocaleDateString("en-GB", { month: "long" });
  const hour = d.getHours() % 12 || 12;
  return `${weekday}, ${d.getDate()} ${month} ${d.getFullYear()}, ${hour}:${pad(d.getMinutes())} ${d.getHours() >= 12 ? "PM" : "AM"}`;
}

// ---- health -------------------------------------------------------------------
api("/health").then((h) => {
  const item = (k, label) => (h[k] ? `<b>${label}</b>` : `<i>${label} off</i>`);
  $("#health").innerHTML = [item("llm", "Claude"), item("vapi", "Phone"), item("places", "Places"), item("calcom", "Cal.com")].join(" · ");
}).catch(() => {});

// ---- live events and polling ----------------------------------------------------
function connect(id) {
  sessionId = id;
  streamFailed = false;
  if (source) source.close();
  source = new EventSource(`/api/sessions/${id}/events`);
  source.addEventListener("snapshot", (e) => renderAll(JSON.parse(e.data)));
  const handlers = {
    "agent.step": (d) => addStep(d),
    "clarify": (d) => renderClarify(d.missing),
    "shortlist": (d) => renderPlaces(d.places),
    "consent.request": (d) => renderConsent(d),
    "call.status": (d) => { renderCallStatus(d.status); refresh(); },
    "card.open": (d) => renderCard(d),
    "card.closed": (d) => closeCard(d),
    "caption": (d) => addCaption(d),
    "followup.available": () => refresh(),
    "outcome": () => refresh(),
    "error": (d) => showNotice(d.message),
  };
  for (const [name, fn] of Object.entries(handlers)) {
    source.addEventListener(name, (e) => fn(JSON.parse(e.data).data));
  }
  source.onerror = () => {
    // A proxy cut the stream, or the server restarted. Polling finds out which (404 = session gone).
    if (source) source.close();
    source = null;
    streamFailed = true;
    schedulePolling();
    refresh();
  };
}

// Poll every 2 s while a call or booking runs (cards must arrive even if a tunnel buffers the stream),
// every 1 s if the stream failed, otherwise not at all.
function schedulePolling() {
  const every = !sessionId ? 0 : streamFailed ? 1000 : LIVE_STATUSES.has(lastStatus) ? 2000 : 0;
  if (every === pollEvery) return;
  clearInterval(pollTimer);
  pollTimer = every ? setInterval(refresh, every) : null;
  pollEvery = every;
}

async function refresh() {
  if (!sessionId || refreshing) return;
  refreshing = true;
  const id = sessionId;
  try {
    const s = await sessionApi("/state");
    if (id === sessionId) renderAll(s);
  } catch (_) {
    // Network error while the server restarts: try again on the next tick.
  } finally {
    refreshing = false;
  }
}

function sessionEnded() {
  if (source) source.close();
  source = null;
  sessionId = null;
  schedulePolling();
  $("#cards").innerHTML = "";
  updateAlerts();
  show("#stale");
}
$("#stale-reset").addEventListener("click", () => location.assign("/"));

function renderAll(s) {
  lastStatus = s.status;
  s.timeline.forEach(addStep);
  if (s.status === "clarifying") renderClarify(missingFrom(s)); else show("#clarify-form", false);
  if (s.places?.length) renderPlaces(s.places, s.selected_place?.id);
  if (s.call?.status || LIVE_STATUSES.has(s.status) || s.cards.length) {
    show("#step-live");
    $("#live-title").textContent = s.channel === "web" ? "Online booking" : "Live call";
  }
  if (s.call?.status) renderCallStatus(s.call.status);
  renderCaptions(s.captions || []);
  s.cards.forEach((c) => (c.state === "open" ? renderCard(c) : closeCard(c)));
  renderOutcome(s);
  schedulePolling();
}
function missingFrom(s) { return ["what", "where", "when"].filter((k) => !s.request?.[k]); }

function resetSession() {
  if (source) source.close();
  source = null;
  sessionId = null;
  lastStatus = clarifyKey = outcomeKey = null;
  schedulePolling();
  timelineKeys.clear();
  cardEls.clear();
  captions = [];
  for (const id of ["#timeline", "#cards", "#captions", "#decisions", "#outcome", "#followup", "#places"]) $(id).innerHTML = "";
  for (const id of ["#step-shortlist", "#step-consent", "#step-live", "#step-outcome", "#clarify-form", "#notice", "#decisions-title", "#followup", "#stale"]) show(id, false);
  updateAlerts();
}

// ---- timeline -----------------------------------------------------------------------
function addStep(d) {
  const key = `${d.at}|${d.agent}|${d.text}`;
  if (timelineKeys.has(key)) return; // already shown by the stream or an earlier poll
  timelineKeys.add(key);
  const li = document.createElement("li");
  li.className = String(d.agent).replace(/\s+/g, "-");
  li.dataset.at = d.at;
  li.innerHTML = `<div class="agent">${esc(d.agent)}</div><div>${esc(d.text)}</div>`;
  const list = $("#timeline");
  const older = [...list.children].find((x) => Number(x.dataset.at) < d.at); // newest first
  list.insertBefore(li, older || null);
}

// ---- step 1: request ------------------------------------------------------------------
$("#request-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#request-text").value.trim();
  if (!text) return;
  const playbook = document.querySelector("input[name=playbook]:checked").value || null;
  resetSession();
  const s = await api("/api/sessions", { text, playbook });
  connect(s.id);
  renderAll(s);
});

function renderClarify(missing) {
  const form = $("#clarify-form");
  const key = missing.join(",");
  if (key === clarifyKey && !form.classList.contains("hidden")) return; // keep what the user is typing
  clarifyKey = key;
  const labels = { playbook: "Clinic, hotel or restaurant?", what: "What exactly?", where: "Where (city or area)?", when: "When?" };
  form.innerHTML = missing.map((k) => `<input name="${k}" placeholder="${labels[k] || k}">`).join("") + `<button>Continue</button>`;
  show("#clarify-form");
  form.onsubmit = async (e) => {
    e.preventDefault();
    const answers = Object.fromEntries(new FormData(form).entries());
    show("#clarify-form", false);
    clarifyKey = null;
    renderAll(await sessionApi("/clarify", { answers }));
  };
}

// ---- step 2: shortlist ------------------------------------------------------------------
function renderPlaces(places, selectedId) {
  show("#step-shortlist");
  const label = { phone: "Phone", web: "Online", none: "Unreachable" };
  $("#places").innerHTML = places.map((p) => `
    <div class="place${p.id === selectedId ? " chosen" : ""}">
      <div><div><b>${esc(p.name)}</b><span class="badge ${p.channel}">${label[p.channel]}</span></div>
      <div class="meta">${p.rating ?? "?"}★ · ${p.reviews ?? 0} reviews · ${esc(p.address || "")}</div></div>
      <button class="ghost" data-id="${esc(p.id)}" ${p.channel === "none" || selectedId ? "disabled" : ""}>${p.id === selectedId ? "Chosen" : "Choose"}</button>
    </div>`).join("");
  $("#places").querySelectorAll("button").forEach((b) => b.addEventListener("click", async () => {
    renderConsent(await sessionApi("/select", { place_id: b.dataset.id }));
  }));
}

// ---- step 3: consent ------------------------------------------------------------------------
// Default window: the next weekday, 09:00 to 12:00 local time.
function defaultWindow() {
  const d = new Date();
  do { d.setDate(d.getDate() + 1); } while (d.getDay() === 0 || d.getDay() === 6);
  const day = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  return { start: `${day}T09:00`, end: `${day}T12:00` };
}

function renderConsent(consent) {
  show("#step-consent");
  $("#consent-fieldset").disabled = false;
  $("#consent-fields").innerHTML = consent.fields.map((f) => `
    <div class="field">
      <input type="checkbox" id="share_${esc(f.key)}" name="share_${esc(f.key)}" ${f.share ? "checked" : ""}>
      <label for="share_${esc(f.key)}">${esc(f.label)}</label>
      <input name="value_${esc(f.key)}" value="${esc(f.value)}" aria-label="${esc(f.label)}">
    </div>`).join("");
  const form = $("#consent-form").elements;
  const limits = consent.limits || {};
  const fallback = defaultWindow();
  form.window_start.value = String(limits.window_start || "").slice(0, 16) || fallback.start;
  form.window_end.value = String(limits.window_end || "").slice(0, 16) || fallback.end;
  form.tolerance_minutes.value = limits.tolerance_minutes ?? 0;
  form.budget_cap.value = limits.budget_cap ?? "";
  validateLimits();
}

function validateLimits() {
  const form = $("#consent-form").elements;
  const start = form.window_start.value;
  const end = form.window_end.value;
  const bad = Boolean(start && end && end < start); // same "YYYY-MM-DDTHH:MM" format, so text order is time order
  $("#limits-error").textContent = bad ? "Latest time is before earliest time. Change one of them to continue." : "";
  show("#limits-error", bad);
  $("#consent-submit").disabled = bad;
  return !bad;
}
for (const name of ["window_start", "window_end"]) {
  for (const type of ["input", "change"]) $("#consent-form").elements[name].addEventListener(type, validateLimits);
}

$("#consent-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!validateLimits()) return;
  const form = new FormData(e.target);
  const fields = {};
  for (const [k, v] of form.entries()) {
    if (k.startsWith("value_")) {
      const key = k.slice(6);
      fields[key] = { value: v, share: form.get(`share_${key}`) === "on" };
    }
  }
  const num = (n) => (form.get(n) ? Number(form.get(n)) : null);
  const limits = {
    window_start: form.get("window_start") || null,
    window_end: form.get("window_end") || null,
    tolerance_minutes: num("tolerance_minutes") || 0,
    budget_cap: num("budget_cap"),
    deposit_allowed: false,
  };
  $("#consent-fieldset").disabled = true;
  try {
    await sessionApi("/consent", { fields, limits });
  } catch (err) {
    if (err.status !== 404) { $("#consent-fieldset").disabled = false; showNotice(err.message); }
    return;
  }
  show("#step-live");
  lastStatus = "calling"; // the call or booking starts now; poll until the outcome arrives
  schedulePolling();
});

// ---- step 4: live ------------------------------------------------------------------------------
function renderCallStatus(status) {
  show("#step-live");
  $("#call-status").textContent = CALL_LABEL[status] || `Call: ${status}`;
}
function showNotice(message) {
  $("#notice").textContent = message;
  show("#notice", Boolean(message));
}

function captionEl(c) {
  const div = document.createElement("div");
  div.className = "caption";
  div.innerHTML = `<b>${esc(c.speaker)}</b>${esc(c.text)}`;
  return div;
}
function addCaption(c) {
  const last = captions[captions.length - 1];
  if (last && last.speaker === c.speaker && last.text === c.text) return; // already shown by a poll
  captions.push(c);
  $("#captions").append(captionEl(c));
  $("#captions").scrollTop = $("#captions").scrollHeight;
}
// The snapshot has the last 20 captions; replace ours only if they differ.
function renderCaptions(list) {
  const tail = list.length ? captions.slice(-list.length) : [];
  if (JSON.stringify(tail) === JSON.stringify(list)) return;
  captions = list.slice();
  $("#captions").replaceChildren(...captions.map(captionEl));
  $("#captions").scrollTop = $("#captions").scrollHeight;
}

// ---- decision cards (checkpoint 3) ---------------------------------------------------------------
function cardHtml(card, open) {
  const input = open && card.meta?.input ? `<input class="share-input" placeholder="Type the value to share">` : "";
  // All options look the same: the page must not nudge the user towards the committing choice
  const shareBtn = open && card.meta?.input ? `<button class="opt" data-share="1">Share it</button>` : "";
  const options = open ? card.options.map((o) => `<button class="opt" data-choice="${esc(o)}">${esc(o)}</button>`).join("") : "";
  return `
    <div class="kind">${esc(KIND_LABEL[card.kind] || "Decision")}<span>Your decision</span></div>
    <div class="q">${esc(card.question)}</div>
    ${card.meta?.reason ? `<div class="why">${esc(card.meta.reason)}</div>` : ""}
    ${input}
    ${options || shareBtn ? `<div class="opts">${shareBtn}${options}</div>` : ""}
    ${open && card.expires_at ? `<div class="countdown"><div class="bar"><i></i></div><span class="left"></span></div>` : ""}
    <div class="result hidden" role="status"></div>`;
}

function renderCard(card) {
  if (cardEls.has(card.id)) return;
  const el = document.createElement("div");
  el.className = `card open kind-${card.kind}`;
  el.dataset.cardId = card.id;
  el.innerHTML = cardHtml(card, true);
  $("#cards").prepend(el);
  cardEls.set(card.id, el);
  el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => answerCard(card, el, b)));
  if (card.expires_at) startCountdown(el, card);
  chime();
  updateAlerts();
}

async function answerCard(card, el, button) {
  const choice = button.dataset.share ? `share:${el.querySelector(".share-input").value}` : button.dataset.choice;
  el.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  try {
    const res = await sessionApi("/answer", { card_id: card.id, choice });
    if (!res.accepted) setResult(el, "Too late. This decision was already closed.");
  } catch (err) {
    if (err.status !== 404) {
      el.querySelectorAll("button").forEach((b) => { b.disabled = false; });
      setResult(el, "That did not go through. Try again.");
    }
  }
}

function startCountdown(el, card) {
  const total = (card.expires_at - card.created_at) * 1000;
  const bar = el.querySelector(".bar i");
  const left = el.querySelector(".left");
  const tick = () => {
    if (!el.classList.contains("open")) return clearInterval(timer);
    const ms = Math.max(0, card.expires_at * 1000 - Date.now());
    bar.style.width = `${total > 0 ? (ms / total) * 100 : 0}%`;
    left.textContent = ms > 0 ? `${Math.ceil(ms / 1000)} s left` : "Time is up";
    if (ms <= 0) clearInterval(timer);
  };
  const timer = setInterval(tick, 250);
  tick();
}

function setResult(el, text) {
  const result = el.querySelector(".result");
  result.textContent = text;
  result.classList.remove("hidden");
}

function closedText(card) {
  if (card.state === "answered") {
    return String(card.answer || "").startsWith("share:") ? "You shared the detail." : `You chose: ${card.answer}`;
  }
  return card.state === "expired" ? "No answer in time." : "Closed.";
}

// Switch the same element to answered or expired, keep it in view briefly, then file it under "Your decisions".
function closeCard(card) {
  let el = cardEls.get(card.id);
  if (el && !el.classList.contains("open")) return;
  if (!el) { // opened and closed between two polls: record it without the sticky step
    el = document.createElement("div");
    el.dataset.cardId = card.id;
    cardEls.set(card.id, el);
    el.className = `card kind-${card.kind} ${card.state}`;
    el.innerHTML = cardHtml(card, false);
    setResult(el, closedText(card));
    fileDecision(el);
    return;
  }
  el.classList.remove("open");
  el.classList.add(card.state);
  el.querySelectorAll(".opts, .share-input, .countdown").forEach((n) => n.remove());
  setResult(el, closedText(card));
  updateAlerts();
  setTimeout(() => fileDecision(el), 2500);
}

function fileDecision(el) {
  if (!sessionId || el.parentElement?.id === "decisions") return;
  const li = document.createElement("li");
  li.append(el);
  $("#decisions").prepend(li);
  show("#decisions-title");
}

// ---- attention: chime and tab title ---------------------------------------------------------------
// Browsers allow sound only after a user gesture, so the audio context starts on the first click.
let audioCtx = null;
document.addEventListener("click", () => {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    else if (audioCtx.state === "suspended") audioCtx.resume();
  } catch (_) {}
}, { capture: true });

function chime() {
  if (!audioCtx) return;
  try {
    const t = audioCtx.currentTime;
    [880, 1320].forEach((freq, i) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      const at = t + i * 0.15;
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.25, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.35);
      osc.connect(gain).connect(audioCtx.destination);
      osc.start(at);
      osc.stop(at + 0.4);
    });
  } catch (_) {}
}

let titleTimer = null;
function updateAlerts() {
  const open = document.querySelector("#cards .card.open") !== null;
  if (open && !titleTimer) {
    let on = true;
    document.title = "Decision needed";
    titleTimer = setInterval(() => { on = !on; document.title = on ? "Decision needed" : "Tandem"; }, 900);
  } else if (!open && titleTimer) {
    clearInterval(titleTimer);
    titleTimer = null;
    document.title = "Tandem";
  }
}

// ---- step 5: outcome ------------------------------------------------------------------------------------
function renderOutcome(s) {
  const o = s.outcome;
  const offer = s.pending_offer && !s.pending_offer.user_answer ? s.pending_offer : null;
  const key = JSON.stringify([o, s.has_calendar_file, offer]);
  if (key === outcomeKey) return; // unchanged: keep the user's choice in the follow up box
  outcomeKey = key;
  if (!o) {
    show("#step-outcome", false);
    renderFollowup(null);
    return;
  }
  show("#step-outcome");
  const when = o.date_time ? longDate(o.date_time) : "";
  const link = o.status === "confirmed" && s.has_calendar_file
    ? `<a class="button" id="calendar-link" href="/api/sessions/${esc(sessionId)}/calendar.ics" download>Add to calendar</a>` : "";
  $("#outcome").innerHTML = `
    <div class="outcome ${esc(o.status)}">
      <div class="status">${esc(OUTCOME_LABEL[o.status] || o.status)}</div>
      ${when ? `<div class="when">${esc(when)}</div>` : ""}
      ${o.reason ? `<div class="reason">${esc(o.reason)}</div>` : ""}
      ${o.hold_expires ? `<div class="hold">Hold: ${esc(o.hold_expires)}</div>` : ""}
    </div>
    ${link ? `<p class="actions">${link}</p>` : ""}`;
  renderFollowup(offer);
}

function renderFollowup(offer) {
  const box = $("#followup");
  if (!offer) { box.innerHTML = ""; show("#followup", false); return; }
  const offered = offer.offered_value ? longDate(offer.offered_value) : "";
  box.innerHTML = `
    <div class="offer-title">Open offer</div>
    <div class="offer-q">${esc(offer.question)}</div>
    ${offered ? `<div>Offered: ${esc(offered)}</div>` : ""}
    <div class="opts">${(offer.options || []).map((o) => `<button class="ghost" aria-pressed="false" data-choice="${esc(o)}">${esc(o)}</button>`).join("")}</div>
    <button id="callback-btn" disabled>Call back</button>
    <div class="hint">Pick your answer. Tandem calls them back with it.</div>`;
  show("#followup");
  let choice = null;
  box.querySelectorAll(".opts button").forEach((b) => b.addEventListener("click", () => {
    choice = b.dataset.choice;
    box.querySelectorAll(".opts button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    $("#callback-btn").disabled = false;
  }));
  $("#callback-btn").addEventListener("click", async () => {
    if (!choice) return;
    $("#callback-btn").disabled = true;
    try {
      await sessionApi("/callback", { answer: choice });
    } catch (err) {
      if (err.status !== 404) { $("#callback-btn").disabled = false; showNotice(err.message); }
      return;
    }
    lastStatus = "calling";
    schedulePolling();
    refresh();
  });
}

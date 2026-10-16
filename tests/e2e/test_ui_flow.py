"""Browser end to end tests (Playwright) against a local server on port 8011 in forced simulate mode.

Skipped unless RUN_E2E=1, so the normal `pytest -q` stays fast and needs no browser.
    pip install -r requirements-dev.txt && python -m playwright install chromium
    RUN_E2E=1 pytest -q tests/e2e

The test starts and stops its own server (scenario c restarts it), with every external key cleared,
so nothing real is called. scripts/simulate_call.py plays the front desk. Screenshots: /tmp/tandem-shots/
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

if os.getenv("RUN_E2E") != "1":
    pytest.skip("browser tests run only with RUN_E2E=1", allow_module_level=True)

import httpx  # noqa: E402
from playwright.sync_api import Page, expect, sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PORT = 8011
BASE = f"http://localhost:{PORT}"
SHOTS = Path("/tmp/tandem-shots")
CARD_DEADLINE = 8  # seconds; short so the ignore path is quick

# Forced simulate mode, every external integration off. Values set here win over .env (load_dotenv does not override).
SERVER_ENV = {
    "SIMULATE_CALLS": "1",
    "VAPI_API_KEY": "",
    "VAPI_PHONE_NUMBER_ID": "",
    "ANTHROPIC_API_KEY": "",
    "GOOGLE_PLACES_API_KEY": "",
    "CALCOM_API_KEY": "",
    "CALCOM_USERNAME": "",
    "CALCOM_EVENT_SLUG": "",
    "CARD_DEADLINE_SECONDS": str(CARD_DEADLINE),
}

expect.set_options(timeout=30_000)


class Server:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.log = tempfile.NamedTemporaryFile(prefix="tandem-e2e-", suffix=".log", delete=False)

    def start(self) -> None:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                pytest.fail(f"Port {PORT} is already in use; stop that process first")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--timeout-graceful-shutdown", "2"],
            cwd=ROOT, env={**os.environ, **SERVER_ENV}, stdout=self.log, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                health = httpx.get(f"{BASE}/health", timeout=1).json()
                assert not (health["llm"] or health["vapi"] or health["places"] or health["calcom"]), health
                return
            except (httpx.HTTPError, ValueError):
                time.sleep(0.2)
        pytest.fail(f"Server did not start; log: {self.log.name}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc = None

    def restart(self) -> None:
        self.stop()
        self.start()


@pytest.fixture(scope="module")
def server():
    SHOTS.mkdir(parents=True, exist_ok=True)
    srv = Server()
    srv.start()
    yield srv
    srv.stop()


@pytest.fixture(scope="module")
def browser(server):
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    p = context.new_page()
    p.set_default_timeout(30_000)
    yield p
    context.close()


def front_desk(scenario: str) -> subprocess.Popen:
    """scripts/simulate_call.py plays the front desk; it waits for the newest simulated call."""
    return subprocess.Popen([sys.executable, "scripts/simulate_call.py", "--base", BASE, "--scenario", scenario],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def finish(proc: subprocess.Popen) -> str:
    out, _ = proc.communicate(timeout=90)
    assert proc.returncode == 0, out
    return out


def start_clinic_call(page: Page) -> None:
    """Request, choose the phone clinic (Checkpoint 1), approve the default consent (Checkpoint 2)."""
    page.goto(BASE)
    page.locator("input[name=playbook][value=clinic]").check()
    page.locator("#request-text").fill("dentist in Gulberg Lahore next week for a cleaning")
    page.get_by_role("button", name="Find").click()
    phone_place = page.locator(".place", has=page.locator(".badge.phone"))
    phone_place.get_by_role("button", name="Choose").click()
    expect(page.locator("#step-consent")).to_be_visible()
    # Default window: next weekday 09:00 to 12:00 (bug A1)
    start = page.locator("input[name=window_start]").input_value()
    end = page.locator("input[name=window_end]").input_value()
    assert start.endswith("T09:00") and end.endswith("T12:00") and start[:10] == end[:10], (start, end)
    page.get_by_role("button", name="Approve and start").click()
    expect(page.locator("#call-status")).to_contain_text("Simulated call")


def open_card(page: Page, question: str):
    card = page.locator("#cards .card.open", has_text=question)
    expect(card).to_be_visible()
    return card


def no_horizontal_scroll(page: Page) -> None:
    widths = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    assert widths[0] <= widths[1], f"horizontal scroll: content {widths[0]}px, viewport {widths[1]}px"


# ---- a) happy path ---------------------------------------------------------------
def test_a_happy_confirmed_with_calendar_link(page: Page):
    start_clinic_call(page)
    desk = front_desk("happy")

    slot = open_card(page, "Tuesday 3 PM")
    expect(slot).to_be_in_viewport()  # sticky at the top although the page scrolled to the consent form
    expect(slot.locator(".kind")).to_contain_text("Time")
    expect(slot.locator(".countdown .left")).to_contain_text("s left")
    page.wait_for_function("() => document.title === 'Decision needed'")
    page.screenshot(path=str(SHOTS / "a-happy-1-slot-card.png"))
    slot.get_by_role("button", name="Accept").click()

    dob = open_card(page, "date of birth")
    expect(dob.locator(".kind")).to_contain_text("Personal detail")
    page.screenshot(path=str(SHOTS / "a-happy-2-data-card.png"))
    dob.get_by_role("button", name="Don't share").click()

    expect(page.locator("#outcome .status")).to_have_text("Confirmed")
    expect(page.locator("#outcome .when")).to_have_text(re.compile(r"^Tuesday, \d{1,2} [A-Z][a-z]+ \d{4}, 3:00 PM$"))
    link = page.locator("#calendar-link")
    expect(link).to_be_visible()
    ics = page.request.get(BASE + link.get_attribute("href"))
    assert ics.ok and "BEGIN:VCALENDAR" in ics.text()
    expect(page.locator("#decisions .card")).to_have_count(2)
    expect(page.locator("#decisions")).to_contain_text("You chose: Accept")
    page.wait_for_function("() => document.title === 'Tandem'")
    page.screenshot(path=str(SHOTS / "a-happy-3-confirmed.png"), full_page=True)
    finish(desk)


# ---- b) card ignored -------------------------------------------------------------------
def test_b_ignore_tentative_with_hold_and_call_back(page: Page):
    start_clinic_call(page)
    desk = front_desk("ignore")

    open_card(page, "Tuesday 3 PM")
    page.screenshot(path=str(SHOTS / "b-ignore-1-card-open.png"))
    # No tap: the card expires after the deadline, the agent asks for a hold
    expect(page.locator("#outcome .status")).to_have_text("Tentative", timeout=(CARD_DEADLINE + 30) * 1000)
    expect(page.locator("#outcome .hold")).to_have_text("Hold: 15 minutes")
    expect(page.locator("#calendar-link")).to_have_count(0)
    expect(page.locator("#decisions")).to_contain_text("No answer in time.")
    callback = page.get_by_role("button", name="Call back")
    expect(callback).to_be_visible()
    expect(callback).to_be_disabled()  # the user picks an answer first
    page.screenshot(path=str(SHOTS / "b-ignore-2-tentative.png"), full_page=True)
    finish(desk)

    page.locator("#followup").get_by_role("button", name="Accept").click()
    expect(callback).to_be_enabled()
    callback.click()
    expect(page.locator("#step-outcome")).to_be_hidden()
    expect(page.locator("#timeline")).to_contain_text("Calling back with your answer: Accept")


# ---- d) phone viewport ------------------------------------------------------------------
def test_d_phone_390_no_horizontal_scroll(browser):
    context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3,
                                  is_mobile=True, has_touch=True)
    page = context.new_page()
    try:
        page.goto(BASE)
        no_horizontal_scroll(page)
        start_clinic_call(page)
        no_horizontal_scroll(page)
        desk = front_desk("happy")

        slot = open_card(page, "Tuesday 3 PM")
        no_horizontal_scroll(page)
        for name in ("Accept", "Decline"):
            button = slot.get_by_role("button", name=name)
            expect(button).to_be_visible()
            box = button.bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390 and box["y"] + box["height"] <= 844, (name, box)
        page.screenshot(path=str(SHOTS / "d-phone-1-card.png"))
        slot.get_by_role("button", name="Accept").click()
        open_card(page, "date of birth").get_by_role("button", name="Don't share").click()

        expect(page.locator("#outcome .status")).to_have_text("Confirmed")
        no_horizontal_scroll(page)
        page.screenshot(path=str(SHOTS / "d-phone-2-confirmed.png"), full_page=True)
        finish(desk)
    finally:
        context.close()


# ---- c) server restart -------------------------------------------------------------------
@pytest.mark.parametrize("stage", ["calling", "choosing"])
def test_c_restart_shows_stale_session_banner(page: Page, server: Server, stage: str):
    """calling: the page polls /state; choosing: only the event stream is open."""
    if stage == "calling":
        start_clinic_call(page)
    else:
        page.goto(BASE)
        page.locator("input[name=playbook][value=clinic]").check()
        page.locator("#request-text").fill("dentist in Gulberg Lahore next week for a cleaning")
        page.get_by_role("button", name="Find").click()
        expect(page.locator("#step-shortlist")).to_be_visible()

    server.restart()

    banner = page.locator("#stale")
    expect(banner).to_be_in_viewport()  # not just rendered: the page may be scrolled down
    expect(banner).to_contain_text("This session ended because the server restarted. Start a new request.")
    page.screenshot(path=str(SHOTS / f"c-restart-{stage}.png"))

    # Polling stops once the session is known to be gone
    state_calls: list[str] = []
    page.on("request", lambda r: state_calls.append(r.url) if r.url.endswith("/state") else None)
    page.wait_for_timeout(3000)
    assert state_calls == [], state_calls

    banner.get_by_role("button", name="Start a new request").click()
    expect(banner).to_be_hidden()
    expect(page.locator("#step-shortlist")).to_be_hidden()
    expect(page.locator("#request-text")).to_have_value("")


# ---- e) two devices, first tap wins ---------------------------------------------------
def test_e_two_contexts_first_tap_wins():
    pytest.skip("The page cannot open an existing session (no session link or id in the URL), "
                "so a second browser cannot join the same session. First tap wins is covered at the API "
                "level in tests/test_flow.py.")

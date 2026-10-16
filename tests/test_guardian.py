from app.agents import guardian

CONSENT = {
    "fields": {
        "name": {"value": "Ahmad", "share": True},
        "reason": {"value": "cleaning", "share": True},
        "callback_number": {"value": "+920000000", "share": False},
    },
    "limits": {
        "window_start": "2026-10-20T09:00",
        "window_end": "2026-10-20T12:00",
        "tolerance_minutes": 30,
        "budget_cap": 50,
    },
}


def test_consented_field_is_allowed_with_value():
    d = guardian.evaluate(CONSENT, "data", field="Name")
    assert d.action == "allow" and d.value == "Ahmad"


def test_unconsented_field_goes_to_user():
    assert guardian.evaluate(CONSENT, "data", field="date of birth").action == "ask_user"


def test_unticked_field_goes_to_user():
    assert guardian.evaluate(CONSENT, "data", field="callback_number").action == "ask_user"


def _with_limits(**changes):
    return {**CONSENT, "limits": {**CONSENT["limits"], **changes}}


AUTO = _with_limits(confirm_slots=False)  # "Ask me before confirming any time" switched off


def test_confirm_slots_on_by_default_asks_even_inside_window():
    # CONSENT has no confirm_slots key: missing means on
    d = guardian.evaluate(CONSENT, "slot", "2026-10-20T10:30")
    assert d.action == "ask_user" and d.reason == "Your preferred time is available."


def test_confirm_slots_true_asks_inside_window_and_within_tolerance():
    on = _with_limits(confirm_slots=True)
    assert guardian.evaluate(on, "slot", "2026-10-20T10:30").reason == "Your preferred time is available."
    near = guardian.evaluate(on, "slot", "2026-10-20T12:20")
    assert near.action == "ask_user" and "within 30 minutes" in near.reason


def test_confirm_slots_false_keeps_auto_accept_inside_window():
    d = guardian.evaluate(AUTO, "slot", "2026-10-20T10:30")
    assert d.action == "allow" and d.value == "2026-10-20T10:30"


def test_confirm_slots_false_allows_within_tolerance():
    assert guardian.evaluate(AUTO, "slot", "2026-10-20T12:20").action == "allow"


def test_confirm_slots_string_false_and_null():
    assert guardian.evaluate(_with_limits(confirm_slots="false"), "slot", "2026-10-20T10:30").action == "allow"
    assert guardian.evaluate(_with_limits(confirm_slots=None), "slot", "2026-10-20T10:30").action == "ask_user"


def test_slot_outside_window_goes_to_user_either_way():
    for consent in (CONSENT, AUTO):
        d = guardian.evaluate(consent, "slot", "2026-10-20T15:00")
        assert d.action == "ask_user" and d.reason == "The time is outside your window."


def test_unreadable_slot_goes_to_user():
    assert guardian.evaluate(CONSENT, "slot", "Tuesday afternoon").action == "ask_user"


def test_price_under_cap_is_allowed_and_over_cap_asks():
    assert guardian.evaluate(CONSENT, "price", "$45").action == "allow"
    assert guardian.evaluate(CONSENT, "price", "USD 80").action == "ask_user"


def test_payment_always_goes_to_user():
    assert guardian.evaluate(CONSENT, "payment", "1000").action == "ask_user"


def test_no_limits_means_ask():
    empty = {"fields": {}, "limits": {}}
    assert guardian.evaluate(empty, "slot", "2026-10-20T10:00").action == "ask_user"
    assert guardian.evaluate(empty, "price", "10").action == "ask_user"

"""All settings come from environment variables (.env in development)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


class Settings:
    # Who the agent is calling for (shown in the opening line and on cards)
    user_name: str = _env("USER_NAME", "Ahmad")
    timezone: str = _env("TIMEZONE", "Asia/Karachi")

    # Public URL of this service (cloud URL or local tunnel). Vapi posts webhooks here.
    public_base_url: str = (_env("PUBLIC_BASE_URL", "http://localhost:8000") or "").rstrip("/")
    # Shared secret appended to the Vapi webhook URL as ?token=...
    webhook_token: str | None = _env("WEBHOOK_TOKEN")

    # Anthropic models (IDs verified on platform.claude.com, 16 Oct 2026)
    anthropic_api_key: str | None = _env("ANTHROPIC_API_KEY")
    model_concierge: str = _env("MODEL_CONCIERGE", "claude-sonnet-5-5")
    model_fast: str = _env("MODEL_FAST", "claude-haiku-5-5")

    # Vapi
    vapi_api_key: str | None = _env("VAPI_API_KEY")
    vapi_phone_number_id: str | None = _env("VAPI_PHONE_NUMBER_ID")
    vapi_base_url: str = _env("VAPI_BASE_URL", "https://api.vapi.ai")
    # Model used inside Vapi for the Caller. claude-haiku-5-5 is in Vapi's API spec but
    # not yet on its docs page: test it; fall back to a model Vapi lists if it fails.
    vapi_model_provider: str = _env("VAPI_MODEL_PROVIDER", "anthropic")
    vapi_model: str = _env("VAPI_MODEL", "claude-haiku-5-5")
    vapi_tool_timeout_seconds: int = int(_env("VAPI_TOOL_TIMEOUT_SECONDS", "25"))
    # Public key (Dashboard > API keys > Public). The live control URL requires it as a Bearer token
    # because monitorPlan.controlAuthenticationEnabled is true.
    vapi_public_api_key: str | None = _env("VAPI_PUBLIC_API_KEY")
    # Server fallback: seconds after report_outcome before the server ends a call that is still open
    end_call_grace_seconds: float = float(_env("END_CALL_GRACE_SECONDS", "10"))

    # How long a decision card waits before the agent is told "no_answer".
    # Must stay below vapi_tool_timeout_seconds.
    card_deadline_seconds: float = float(_env("CARD_DEADLINE_SECONDS", "22"))

    # Development: no real phone call; scripts/simulate_call.py plays the front desk
    simulate_calls: bool = (_env("SIMULATE_CALLS", "0") or "0") == "1"

    # Demo: the seeded "business" phone number (Daniyal's phone, E.164 format)
    demo_front_desk_number: str | None = _env("DEMO_FRONT_DESK_NUMBER")

    # Google Places API (New)
    google_places_api_key: str | None = _env("GOOGLE_PLACES_API_KEY")

    # Cal.com API v2 (web channel)
    calcom_base_url: str = _env("CALCOM_BASE_URL", "https://api.cal.com/v2")
    calcom_api_key: str | None = _env("CALCOM_API_KEY")
    calcom_username: str | None = _env("CALCOM_USERNAME")
    calcom_event_slug: str | None = _env("CALCOM_EVENT_SLUG")
    calcom_attendee_email: str | None = _env("CALCOM_ATTENDEE_EMAIL")


settings = Settings()

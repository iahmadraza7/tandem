"""The access log masks ?token= and keeps the rest of the line."""
import logging

from app import log_filters

ACCESS_FORMAT = '%s - "%s %s HTTP/%s" %d'  # what uvicorn logs on "uvicorn.access"


def _access_line(path: str) -> str:
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, ACCESS_FORMAT,
                               ("127.0.0.1:5000", "POST", path, "1.1", 200), None)
    assert log_filters.RedactTokenFilter().filter(record) is True
    return record.getMessage()


def test_token_value_is_masked_and_rest_of_line_kept():
    line = _access_line("/vapi/webhook?token=s3cret-value")
    assert "s3cret-value" not in line
    assert line == '127.0.0.1:5000 - "POST /vapi/webhook?token=*** HTTP/1.1" 200'


def test_token_masked_among_other_params():
    line = _access_line("/vapi/webhook?a=1&token=s3cret&b=2")
    assert "s3cret" not in line
    assert "?a=1&token=***&b=2" in line


def test_lines_without_token_unchanged():
    assert _access_line("/api/sessions/abc/state?x=1") == '127.0.0.1:5000 - "POST /api/sessions/abc/state?x=1 HTTP/1.1" 200'
    # A parameter that only ends in "token" is not the webhook token
    assert "access_token=keep" in _access_line("/x?access_token=keep")


def test_vapi_control_url_is_masked():
    text = log_filters.redact('HTTP Request: POST https://phone-call-websocket.aws-us-west-2-backend-production1.vapi.ai/'
                              '7420f27a-30fd-4f49-a995-5549ae7cc00d/control "HTTP/1.1 200 OK"')
    assert "7420f27a" not in text and "vapi.ai/***/control" in text


def test_installed_once_on_uvicorn_access_logger():
    import app.main  # noqa: F401  installs the filter on import

    log_filters.install()
    filters = [f for f in logging.getLogger("uvicorn.access").filters if isinstance(f, log_filters.RedactTokenFilter)]
    assert len(filters) == 1

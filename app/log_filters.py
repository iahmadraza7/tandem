"""Log filters: keep secrets out of the logs.

Vapi posts to /vapi/webhook?token=<WEBHOOK_TOKEN>, and uvicorn logs the full path with its query string.
httpx logs the Vapi live control URL when we end a call. The filter masks both and keeps the rest of the line.
"""
from __future__ import annotations

import logging
import re

TOKEN_PARAM = re.compile(r"([?&]token=)[^&\s\"]*", re.IGNORECASE)
# Vapi live control URL (https://<host>.vapi.ai/<call id>/control): whoever has it can control the call
CONTROL_URL = re.compile(r"(https://[\w.-]*vapi\.ai/)[^\s/\"']+(/control)")
LOGGERS = ("uvicorn.access", "httpx")  # httpx logs every outgoing request URL at INFO


def redact(text: str) -> str:
    return CONTROL_URL.sub(r"\1***\2", TOKEN_PARAM.sub(r"\1***", text))


class RedactTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn passes the path as an argument, not inside msg, so both are masked
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True


def install() -> None:
    """Attach the filter to the uvicorn access logger and the httpx logger once."""
    for name in LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactTokenFilter) for f in logger.filters):
            logger.addFilter(RedactTokenFilter())

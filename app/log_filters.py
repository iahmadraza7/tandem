"""Log filters: keep secrets out of the uvicorn access log.

Vapi posts to /vapi/webhook?token=<WEBHOOK_TOKEN>, and uvicorn logs the full path with its query string.
The filter masks the token value and keeps the rest of the line for debugging.
"""
from __future__ import annotations

import logging
import re

TOKEN_PARAM = re.compile(r"([?&]token=)[^&\s\"]*", re.IGNORECASE)


def redact(text: str) -> str:
    return TOKEN_PARAM.sub(r"\1***", text)


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
    """Attach the filter to the uvicorn access logger once."""
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactTokenFilter) for f in logger.filters):
        logger.addFilter(RedactTokenFilter())

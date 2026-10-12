from __future__ import annotations

import logging
import sys
from typing import Any

SENSITIVE_KEYS = frozenset({
    "api_key", "apikey", "secret", "password", "token", "authorization",
    "cookie", "cv_text", "raw_text", "email", "phone",
})


class SanitizingFilter(logging.Filter):
    """Prevent sensitive data from appearing in logs."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.msg = self._sanitize(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact_if_sensitive(k, v) for k, v in record.args.items()}
        return True

    def _sanitize(self, msg: Any) -> Any:
        if isinstance(msg, str):
            for key in SENSITIVE_KEYS:
                if key.lower() in msg.lower():
                    return "[REDACTED LOG - sensitive key found in message]"
        return msg

    def _redact_if_sensitive(self, key: str, value: Any) -> Any:
        if any(s in key.lower() for s in SENSITIVE_KEYS):
            return "[REDACTED]"
        return value


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging for the application."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SanitizingFilter())
        root.addHandler(handler)

    # Suppress noisy third-party loggers
    for name in ("httpx", "httpcore", "urllib3", "google", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"opportunity_radar.{name}")

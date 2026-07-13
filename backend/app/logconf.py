"""Logging house standard — structlog to JSON on stdout, one event per line.

Call setup("<service>") ONCE at boot (main.py); everywhere else use structlog.get_logger(). Never
print(), never the stdlib logging module directly — the shimpz-stdcheck gate BLOCKs both. Per-request
trace_id is bound in app/middleware.py and rides every line automatically (contextvars). LOG_FORMAT=console
gives human output in dev (default json); LOG_LEVEL sets the level (default INFO)."""

import logging
import os

import structlog


def setup(service: str) -> None:
    # Fail-fast: an invalid LOG_LEVEL must surface LOUDLY, never silently coerce to INFO (a masked
    # misconfiguration is exactly the fallback the house rules forbid).
    _lvl = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, _lvl, None)
    if not isinstance(level, int):
        raise ValueError(
            "invalid LOG_LEVEL=%r (use DEBUG/INFO/WARNING/ERROR/CRITICAL)" % _lvl
        )
    shared = [
        structlog.contextvars.merge_contextvars,  # inject per-request binds (trace_id, ...)
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.dict_tracebacks,  # full exception -> structured JSON, never a bare string
    ]
    if os.getenv("LOG_FORMAT", "json") == "console":
        processors = [*shared, structlog.dev.ConsoleRenderer()]
    else:
        processors = [
            *shared,
            structlog.processors.EventRenamer("msg"),
            structlog.processors.JSONRenderer(),
        ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),  # stdout; the platform collector ships it
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service)

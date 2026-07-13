"""Pure ASGI middleware: bind a per-request trace_id into structlog contextvars so every log line of the
request (across nested calls) carries it. Reuses an inbound X-Request-ID (propagated by a caller) or mints
one, and echoes it back so a browser / calling service can follow the same request end-to-end.

The inbound header is ATTACKER-CONTROLLED, so it is never trusted raw: it flows into a response header (a
control byte would crash the ASGI send / enable header injection) and into contextvars + every log line (an
oversized value would bloat them). _clean() decodes safely (latin-1 never raises on bad bytes), keeps only a
conservative token charset, and caps the length — an empty/oversized/hostile id is replaced with a fresh one."""

import re
from uuid import uuid4

import structlog

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _clean(raw: bytes) -> str:
    tid = _UNSAFE.sub("", raw.decode("latin-1"))[
        :200
    ]  # strip non-token chars (drops CTLs/unicode), cap 200
    return tid or uuid4().hex  # empty after cleaning → mint a safe one


class TraceIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        trace_id = _clean(headers.get(b"x-request-id", b""))
        # Bind WITHOUT reset: each request runs in its own contextvars copy (can't leak across requests),
        # and the id must stay visible to the exception handler in the outer error middleware.
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers") or [])
                message["headers"].append(
                    (b"x-request-id", trace_id.encode("ascii"))
                )  # token-only → safe
            await send(message)

        await self.app(scope, receive, send_with_id)

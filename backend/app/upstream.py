"""Bounded one-hop JSON transport to trusted internal services."""

from __future__ import annotations

import functools
import http.client
import json
from urllib.parse import urlparse

import structlog

from app.concurrency import BoundedThreadPoolExecutor, run_bounded

log = structlog.get_logger()


def call(
    base: str,
    method: str,
    path: str,
    payload: dict | None = None,
    extra: dict | None = None,
) -> tuple[int, dict]:
    """Proxy one trusted internal hop with a closed generic failure."""
    parsed = urlparse(base)
    headers: dict[str, str] = dict(extra or {})
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=180)
    try:
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, (json.loads(raw) if raw else {})
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("proxy_unreachable", base=base, path=path, error=str(exc))
        return 502, {"detail": "the Space is unreachable"}
    finally:
        connection.close()


async def call_bounded(
    executor: BoundedThreadPoolExecutor,
    *args,
    **kwargs,
) -> tuple[int, dict]:
    """Run one internal JSON hop through the caller's bounded executor."""
    return await run_bounded(executor, functools.partial(call, *args, **kwargs))

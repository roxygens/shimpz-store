"""Bounded blocking relay between the Team driver NDJSON stream and asyncio."""

from __future__ import annotations

import asyncio
import concurrent.futures
import http.client
import json as jsonlib
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlparse

import structlog

from app import config
from app.chat.events import parsed_stream_event as _parsed_stream_event
from app.chat.events import public_chat_error_event as _public_chat_error_event
from app.chat.events import upstream_error_event as _upstream_error_event
from app.chat.events import validated_terminal_event as _validated_terminal_event
from app.config import (
    MAX_UPSTREAM_STREAM_BYTES,
    MAX_UPSTREAM_STREAM_LINE_BYTES,
    STREAM_QUEUE_PUT_TIMEOUT,
    TERMINAL_CONTRACT_ERROR,
)
from app.upstream import CONTROL_PLANE_TIMEOUT_SECONDS
from app.upstream import call as _call

log = structlog.get_logger()


def _stream_queue_put(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, item: dict | None) -> bool:
    """Thread→event-loop handoff with a hard queue bound and real producer backpressure."""
    pending = None
    try:
        pending = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
        pending.result(timeout=STREAM_QUEUE_PUT_TIMEOUT)
    except TimeoutError, concurrent.futures.CancelledError, RuntimeError:
        if pending is not None:
            pending.cancel()
        return False
    return True


class _StreamLimitError(ValueError):
    """The team-driver stream exceeded a bounded relay contract."""


class _StreamProtocolError(ValueError):
    """The team-driver stream violated its typed NDJSON contract."""


def _bounded_upstream_lines(resp: http.client.HTTPResponse):
    buf = b""
    received = 0
    while chunk := resp.read1(4096):
        received += len(chunk)
        if received > MAX_UPSTREAM_STREAM_BYTES:
            raise _StreamLimitError("brain stream exceeded its total output limit")
        buf += chunk
        if len(buf) > MAX_UPSTREAM_STREAM_LINE_BYTES and b"\n" not in buf:
            raise _StreamLimitError("brain stream line exceeded its size limit")
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if len(line) > MAX_UPSTREAM_STREAM_LINE_BYTES:
                raise _StreamLimitError("brain stream line exceeded its size limit")
            yield line
    if len(buf) > MAX_UPSTREAM_STREAM_LINE_BYTES:
        raise _StreamLimitError("brain stream line exceeded its size limit")
    if buf:
        yield buf


def _relay_upstream_events(
    resp: http.client.HTTPResponse,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    expected_team_id: str,
) -> None:
    """Release exactly one validated terminal event after the controller closes its response."""
    terminal_event = None
    try:
        for line in _bounded_upstream_lines(resp):
            if not line.strip():
                continue
            event = _parsed_stream_event(line, expected_team_id)
            if event is None:
                raise _StreamProtocolError
            if terminal_event is not None:
                raise _StreamProtocolError
            terminal_event = event
    except _StreamLimitError, _StreamProtocolError:
        _stream_queue_put(
            queue,
            loop,
            {
                "type": "error",
                "status": 502,
                "detail": TERMINAL_CONTRACT_ERROR,
                "_relay_abort": True,
            },
        )
        return
    if terminal_event is None:
        _stream_queue_put(
            queue,
            loop,
            {
                "type": "error",
                "status": 502,
                "detail": TERMINAL_CONTRACT_ERROR,
                "_relay_abort": True,
            },
        )
    else:
        _stream_queue_put(queue, loop, terminal_event)


@dataclass(frozen=True)
class _StreamRelay:
    team_id: str
    text: str
    headers: dict
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop
    started: asyncio.Event
    files: tuple[str, ...] = ()
    assistant_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ChallengeRelay:
    team_id: str
    kind: str
    body: dict
    headers: dict
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop
    started: asyncio.Event


def _stream_lines(relay: _StreamRelay) -> None:
    """BLOCKING (run in a thread): relay the driver's NDJSON into a bounded asyncio queue."""
    parsed = urlparse(config.TEAMDRIVER_URL)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=200)
    try:
        payload: dict[str, object] = {
            "message": relay.text,
            "files": list(relay.files),
            "assistant_ids": list(relay.assistant_ids),
        }
        body = jsonlib.dumps(payload, ensure_ascii=False).encode()
        conn.request(
            "POST",
            f"/v1/teams/{relay.team_id}/chat/stream",
            body,
            {**relay.headers, "Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        relay.loop.call_soon_threadsafe(relay.started.set)
        if not 200 <= resp.status < 300:
            _stream_queue_put(
                relay.queue,
                relay.loop,
                _upstream_error_event(resp.status),
            )
            return
        _relay_upstream_events(resp, relay.queue, relay.loop, relay.team_id)
    except (OSError, http.client.HTTPException) as exc:
        log.warning("chat_stream_failed", team_id=relay.team_id, error=type(exc).__name__)
        _stream_queue_put(
            relay.queue,
            relay.loop,
            {
                "type": "error",
                "status": 502,
                "detail": "team-driver stream failed",
                "_relay_abort": True,
            },
        )
    finally:
        relay.loop.call_soon_threadsafe(relay.started.set)
        conn.close()
        _stream_queue_put(relay.queue, relay.loop, None)


def _challenge_response_event(status: int, data: object, team_id: str) -> dict:
    projected = None
    if isinstance(data, dict) and status in {
        HTTPStatus.OK,
        HTTPStatus.PRECONDITION_REQUIRED,
    }:
        challenge_status = data.get("status")
        if challenge_status in {"input-required", "approval-required"}:
            projected = {"type": challenge_status, **data}
        elif status == HTTPStatus.OK:
            projected = {"type": "done", **data}
    terminal = _validated_terminal_event(projected, team_id)
    if terminal is not None:
        return terminal
    if 400 <= status <= 599:
        return _public_chat_error_event(status)
    return {
        "type": "error",
        "status": 502,
        "detail": TERMINAL_CONTRACT_ERROR,
        "_relay_abort": True,
    }


def _relay_challenge(relay: _ChallengeRelay) -> None:
    relay.loop.call_soon_threadsafe(relay.started.set)
    try:
        status, data = _call(
            config.TEAMDRIVER_URL,
            "POST",
            f"/v1/teams/{relay.team_id}/chat/{relay.kind}",
            relay.body,
            relay.headers,
            timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
        )
        _stream_queue_put(
            relay.queue,
            relay.loop,
            _challenge_response_event(status, data, relay.team_id),
        )
    finally:
        _stream_queue_put(relay.queue, relay.loop, None)

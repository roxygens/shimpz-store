import asyncio
import contextlib
import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import WebSocket

from app import config
from app.chat.relay import _relay_upstream_events
from app.chat import ws as main
from tests.chat_relay_fixture import real_stream_driver as _real_stream_driver

TEST_TEAM_ID = "test_team"


def _done(
    reply: str = "hello",
    *,
    team_id: str = TEST_TEAM_ID,
    team_name: str = "Marketing",
) -> dict:
    return {
        "type": "done",
        "team_id": team_id,
        "team_name": team_name,
        "reply": reply,
    }


def _websocket(text: str) -> tuple[WebSocket, list[dict]]:
    incoming = iter(
        (
            {"type": "websocket.connect"},
            {"type": "websocket.receive", "text": text},
        )
    )

    async def receive() -> dict:
        return next(incoming)

    sent = []

    async def send(message: dict) -> None:
        sent.append(message)

    return WebSocket({"type": "websocket", "path": "/"}, receive, send), sent


@contextlib.contextmanager
def _real_upstream(body: bytes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    worker.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", "/stream")
        yield connection.getresponse()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def _relay(body: bytes, team_id: str = TEST_TEAM_ID) -> list[dict]:
    async def scenario() -> list[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with _real_upstream(body) as response:
            await asyncio.to_thread(_relay_upstream_events, response, queue, loop, team_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        return events

    return asyncio.run(scenario())


@contextlib.contextmanager
def _real_delayed_upstream(first: bytes, rest: bytes):
    first_flushed = threading.Event()
    release_rest = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body_size = len(first) + len(rest)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(body_size))
            self.end_headers()
            self.wfile.write(first)
            self.wfile.flush()
            first_flushed.set()
            if release_rest.wait(timeout=5):
                self.wfile.write(rest)
                self.wfile.flush()

        def log_message(self, *_args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    worker.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", "/stream")
        yield connection.getresponse(), first_flushed, release_rest
    finally:
        release_rest.set()
        connection.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_upstream_relay_releases_nothing_before_one_complete_terminal_event():
    async def scenario() -> None:
        queue: asyncio.Queue = asyncio.Queue(maxsize=4)
        loop = asyncio.get_running_loop()
        first = b'{"type":"done","team_id":"test_team",'
        rest = b'"team_name":"Marketing","reply":"first"}\n'
        with _real_delayed_upstream(first, rest) as (
            response,
            first_flushed,
            release_rest,
        ):
            relay = asyncio.create_task(
                asyncio.to_thread(
                    _relay_upstream_events,
                    response,
                    queue,
                    loop,
                    TEST_TEAM_ID,
                )
            )
            assert await asyncio.to_thread(first_flushed.wait, 1)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(queue.get(), timeout=0.05)
            assert not relay.done()
            release_rest.set()
            await asyncio.wait_for(relay, timeout=2)
            assert await asyncio.wait_for(queue.get(), timeout=1) == _done("first")

    asyncio.run(scenario())


def test_stream_transport_preserves_utf8_prompt_and_reply_bytes():
    async def scenario() -> None:
        reply = "Olá, Capitão 🦐"
        encoded_reply = (
            json.dumps(
                _done(reply, team_id="team_utf8"),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        queue: asyncio.Queue = asyncio.Queue(maxsize=4)
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        prompt = "ação e camarão 🦐"
        opaque_file = "a" * 32
        with _real_stream_driver(encoded_reply) as requests:
            await asyncio.to_thread(
                main._stream_lines,
                main._StreamRelay(
                    "team_utf8",
                    prompt,
                    {},
                    queue,
                    loop,
                    started,
                    (opaque_file,),
                    ("shimpz-cloudflare",),
                ),
            )
        assert started.is_set()
        assert len(requests) == 1
        assert json.loads(requests[0]) == {
            "message": prompt,
            "files": [opaque_file],
            "assistant_ids": ["shimpz-cloudflare"],
        }
        assert prompt.encode() in requests[0]
        assert b"\\u" not in requests[0]
        assert await queue.get() == _done(reply, team_id="team_utf8")
        assert await queue.get() is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "terminal",
    [
        pytest.param(
            {
                "type": "error",
                "status": 504,
                "detail": "the brain did not answer within 170s",
            },
            id="rc-124-timeout",
        ),
        pytest.param(
            {"type": "error", "status": 500, "detail": "brain error (rc=23)"},
            id="nonzero-rc",
        ),
        pytest.param(
            {
                "type": "error",
                "status": 502,
                "detail": "brain stream ended without a completion event",
            },
            id="missing-completion",
        ),
    ],
)
def test_driver_terminal_failures_reach_websocket_as_errors(terminal: dict):
    async def scenario() -> None:
        websocket, sent = _websocket("{}")
        await websocket.accept()
        started = asyncio.Event()
        response = json.dumps(terminal, separators=(",", ":")).encode() + b"\n"
        with _real_stream_driver(response) as requests:
            await main._ws_run_turn(
                websocket,
                "team-terminal",
                {},
                {"message": "hello", "files": [], "assistant_ids": []},
                started,
            )
        events = [json.loads(message["text"]) for message in sent if message["type"] == "websocket.send"]
        assert started.is_set()
        assert len(requests) == 1
        expected_detail = (
            "chat service timed out" if terminal["status"] == 504 else "chat service is temporarily unavailable"
        )
        assert events == [
            {
                "type": "error",
                "status": terminal["status"],
                "detail": expected_detail,
            }
        ]
        assert all(event.get("type") == "error" for event in events)
        assert not any(event.get("type") == "done" for event in events)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (409, {"error": "team already has an active chat turn"}),
        (429, {"detail": "chat rate limit exceeded"}),
    ],
)
def test_real_upstream_non_2xx_reaches_websocket_redacted(status: int, payload: dict):
    async def scenario() -> None:
        websocket, sent = _websocket("{}")
        await websocket.accept()
        started = asyncio.Event()
        body = json.dumps(payload, separators=(",", ":")).encode()
        with _real_stream_driver(body, status=status) as requests:
            await main._ws_run_turn(
                websocket,
                "team-upstream-error",
                {},
                {"message": "hello", "files": [], "assistant_ids": []},
                started,
            )
        events = [json.loads(message["text"]) for message in sent if message["type"] == "websocket.send"]
        assert started.is_set()
        assert len(requests) == 1
        assert events == [
            {
                "type": "error",
                "status": status,
                "detail": ("chat service is busy; try again shortly" if status == 429 else "chat request was rejected"),
            }
        ]

    asyncio.run(scenario())


def test_upstream_relay_is_bounded_and_fails_closed_on_protocol_errors():
    success = json.dumps(_done(), separators=(",", ":")).encode()
    assert _relay(success) == [_done()]

    protocol_error = {
        "type": "error",
        "status": 502,
        "detail": "team-driver stream violated the terminal event contract",
        "_relay_abort": True,
    }
    legacy_then_terminal = b'{"type":"text","text":"partial"}\n' + json.dumps(_done()).encode() + b"\n"
    assert _relay(legacy_then_terminal) == [protocol_error]

    malformed = b"not-json\n" + json.dumps(_done()).encode() + b"\n"
    assert _relay(malformed) == [protocol_error]

    extra_after_terminal = json.dumps(_done()).encode() + b'\n{"type":"stopped"}\n'
    assert _relay(extra_after_terminal) == [protocol_error]

    mismatched_team = json.dumps(_done(team_id="another_team")).encode() + b"\n"
    assert _relay(mismatched_team) == [protocol_error]

    assert _relay(b"") == [protocol_error]

    oversized = b"x" * (config.MAX_UPSTREAM_STREAM_LINE_BYTES + 1)
    assert _relay(oversized) == [protocol_error]

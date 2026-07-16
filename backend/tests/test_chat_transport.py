import asyncio
import concurrent.futures
import contextlib
import http.client
import json
import re
import secrets
import tempfile
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest
from app import main
from app.main import (
    ACCOUNT_COOKIE,
    MAX_UPSTREAM_STREAM_LINE_BYTES,
    MAX_WS_FRAME_BYTES,
    WS_ALLOWED_ORIGINS,
    ClientPayloadError,
    WebSocketPayloadError,
    _canonical_origin,
    _parsed_stream_event,
    _read_bounded_json,
    _relay_upstream_events,
    _stream_queue_put,
    _upstream_error_event,
    _ws_dispatch,
    _ws_receive_bounded_json,
    app,
)
from fastapi import Request, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def _websocket_disconnect_code(client: TestClient, origin: str | None) -> int:
    headers = {"origin": origin} if origin is not None else {}
    with (
        pytest.raises(WebSocketDisconnect) as raised,
        client.websocket_connect("/api/capsules/test-capsule/ws", headers=headers),
    ):
        pass
    return raised.value.code


def _origin_variants(origin: str) -> tuple[str, str, str]:
    parsed = urlparse(origin)
    explicit_port = f":{parsed.port}" if parsed.port is not None else ""
    subdomain = f"{parsed.scheme}://chat.{parsed.hostname}{explicit_port}"
    suffix_trick = f"{parsed.scheme}://{parsed.hostname}.evil.example{explicit_port}"
    alternate_port = 444 if parsed.port == 443 else 443
    port_trick = f"{parsed.scheme}://{parsed.hostname}:{alternate_port}"
    return subdomain, suffix_trick, port_trick


def test_websocket_origin_is_exact_and_checked_before_authentication():
    assert WS_ALLOWED_ORIGINS
    allowed = next(iter(WS_ALLOWED_ORIGINS))
    denied = (None, "null", *_origin_variants(allowed))

    with TestClient(app) as client:
        for origin in denied:
            assert _websocket_disconnect_code(client, origin) == 4403
        # An exact first-party Origin advances to the cookie check; no account service call is made
        # because this handshake deliberately has no account cookie.
        assert _websocket_disconnect_code(client, allowed) == 4401


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("null", None),
        ("https://shimpz.com", "https://shimpz.com"),
        ("HTTPS://SHIMPZ.COM", "https://shimpz.com"),
        ("https://shimpz.com:443", "https://shimpz.com:443"),
        ("https://shimpz.com/", None),
        ("https://shimpz.com.evil.example", "https://shimpz.com.evil.example"),
        ("https://user@shimpz.com", None),
        ("https://shimpz.com?next=evil", None),
        ("https://shimpz.com:bad", None),
    ],
)
def test_canonical_origin(value: str | None, expected: str | None):
    assert _canonical_origin(value) == expected


def _request(body: bytes, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    delivered = False

    async def receive() -> dict:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "headers": headers or []}, receive)


def test_bounded_json_rejects_declared_and_streamed_oversize_bodies():
    async def scenario() -> None:
        with pytest.raises(ClientPayloadError) as declared:
            await _read_bounded_json(_request(b"{}", [(b"content-length", b"9")]), 8)
        assert declared.value.status == 413

        with pytest.raises(ClientPayloadError) as streamed:
            await _read_bounded_json(_request(b'{"x":123}'), 8)
        assert streamed.value.status == 413

    asyncio.run(scenario())


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


def test_websocket_frame_limit_is_enforced_before_json_parsing():
    async def scenario() -> None:
        websocket, _ = _websocket("x" * (MAX_WS_FRAME_BYTES + 1))
        await websocket.accept()
        with pytest.raises(WebSocketPayloadError) as raised:
            await _ws_receive_bounded_json(websocket)
        assert raised.value.status == 413
        assert raised.value.close_code == 1009

    asyncio.run(scenario())


def test_websocket_allows_only_one_local_turn_task():
    async def scenario() -> None:
        websocket, sent = _websocket("{}")
        await websocket.accept()
        blocker = asyncio.Event()
        active_turn = asyncio.create_task(blocker.wait())
        state = {"seen": set(), "turns": {active_turn}}
        try:
            await _ws_dispatch(
                websocket,
                "test-capsule",
                {},
                {"type": "chat", "message": "second"},
                state,
            )
        finally:
            active_turn.cancel()
            await asyncio.gather(active_turn, return_exceptions=True)

        assert len(state["turns"]) == 1
        assert json.loads(sent[-1]["text"]) == {
            "type": "error",
            "status": 409,
            "detail": "capsule already has an active chat turn",
        }

    asyncio.run(scenario())


def test_websocket_returns_typed_429_when_global_turn_queue_is_full():
    async def scenario() -> None:
        capacity = main._TURN_ADMISSION.active_limit + main._TURN_ADMISSION.queue_limit
        leases = [main._TURN_ADMISSION.reserve() for _ in range(capacity)]
        assert all(lease is not None for lease in leases)
        assert main._TURN_ADMISSION.reserve() is None
        websocket, sent = _websocket("{}")
        await websocket.accept()
        try:
            await _ws_dispatch(
                websocket,
                "test-capsule",
                {},
                {"type": "chat", "message": "beyond the bound"},
                {"seen": set(), "turns": set()},
            )
            assert json.loads(sent[-1]["text"]) == {
                "type": "error",
                "status": 429,
                "detail": "chat relay capacity reached",
            }
        finally:
            for lease in reversed(leases):
                assert lease is not None
                lease.release()
        assert main._TURN_ADMISSION.snapshot() == (0, 0)

    asyncio.run(scenario())


def test_stream_queue_applies_backpressure_without_dropping_events():
    async def scenario() -> None:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        await queue.put({"type": "text", "text": "first"})
        loop = asyncio.get_running_loop()
        producer = asyncio.create_task(
            asyncio.to_thread(
                _stream_queue_put,
                queue,
                loop,
                {"type": "text", "text": "second"},
            )
        )

        assert (await queue.get())["text"] == "first"
        assert await asyncio.wait_for(producer, timeout=1) is True
        assert (await queue.get())["text"] == "second"

    asyncio.run(scenario())


def test_global_turn_admission_has_an_exact_fifo_queue_bound():
    async def scenario() -> None:
        admission = main._TurnAdmission(active_limit=1, queue_limit=1)
        active = admission.reserve()
        queued = admission.reserve()
        rejected = admission.reserve()
        assert active is not None and queued is not None
        assert rejected is None
        assert admission.snapshot() == (1, 1)

        entered = asyncio.Event()

        async def wait_for_slot() -> None:
            async with queued:
                entered.set()

        waiter = asyncio.create_task(wait_for_slot())
        await asyncio.sleep(0)
        assert not entered.is_set()
        active.release()
        await asyncio.wait_for(entered.wait(), timeout=1)
        await waiter
        assert admission.snapshot() == (0, 0)

        active = admission.reserve()
        queued = admission.reserve()
        assert active is not None and queued is not None
        cancelled = asyncio.create_task(queued.__aenter__())
        await asyncio.sleep(0)
        cancelled.cancel()
        await asyncio.gather(cancelled, return_exceptions=True)
        assert admission.snapshot() == (1, 0)
        active.release()
        assert admission.snapshot() == (0, 0)

    asyncio.run(scenario())


def test_queued_turn_stop_removes_its_fifo_lease_before_it_can_run():
    async def scenario() -> None:
        admission = main._TurnAdmission(active_limit=1, queue_limit=1)
        occupied = admission.reserve()
        assert occupied is not None
        previous = main._TURN_ADMISSION
        main._TURN_ADMISSION = admission
        websocket, sent = _websocket("{}")
        await websocket.accept()
        state = {"seen": set(), "turns": set()}
        try:
            await _ws_dispatch(
                websocket,
                "cap-queued",
                {},
                {"type": "chat", "message": "must never execute"},
                state,
            )
            await asyncio.sleep(0)
            assert admission.snapshot() == (1, 1)

            await _ws_dispatch(websocket, "cap-queued", {}, {"type": "stop"}, state)
            assert admission.snapshot() == (1, 0)
            assert not state["turns"]
            assert json.loads(sent[-1]["text"]) == {
                "type": "stopped",
                "status": 200,
                "requested": True,
                "queued": True,
            }

            occupied.release()
            await asyncio.sleep(0)
            assert admission.snapshot() == (0, 0)
            assert not state["turns"]
        finally:
            occupied.release()
            for turn in list(state["turns"]):
                turn.cancel()
            await asyncio.gather(*state["turns"], return_exceptions=True)
            main._TURN_ADMISSION = previous

    asyncio.run(scenario())


def test_websocket_connection_admission_bounds_global_account_and_capsule_counts():
    admission = main._WsConnectionAdmission(global_limit=3, account_limit=2, capsule_limit=1)
    account_a_one = admission.reserve("account-a", "cap-1")
    assert account_a_one is not None
    assert admission.reserve("account-a", "cap-1") is None
    account_a_two = admission.reserve("account-a", "cap-2")
    assert account_a_two is not None
    assert admission.reserve("account-a", "cap-3") is None
    account_b_one = admission.reserve("account-b", "cap-1")
    assert account_b_one is not None
    assert admission.reserve("account-b", "cap-2") is None
    assert admission.snapshot() == (
        3,
        {"account-a": 2, "account-b": 1},
        {
            ("account-a", "cap-1"): 1,
            ("account-a", "cap-2"): 1,
            ("account-b", "cap-1"): 1,
        },
    )

    account_a_one.release()
    replacement = admission.reserve("account-b", "cap-2")
    assert replacement is not None
    account_a_two.release()
    account_b_one.release()
    replacement.release()
    replacement.release()
    assert admission.snapshot() == (0, {}, {})


def test_stream_executor_rejects_instead_of_growing_an_internal_work_queue():
    release = threading.Event()
    started = threading.Event()
    executor = main._BoundedThreadPoolExecutor(
        max_workers=1,
        max_outstanding=1,
        thread_name_prefix="bounded-proof",
    )

    def occupy() -> None:
        started.set()
        release.wait(timeout=5)

    first = executor.submit(occupy)
    try:
        assert started.wait(timeout=1)
        with pytest.raises(main._ExecutorSaturatedError):
            executor.submit(lambda: None)
    finally:
        release.set()
        first.result(timeout=2)
        executor.shutdown(wait=True)


def test_bounded_executor_counts_running_and_queued_work_then_recovers():
    release = threading.Event()
    started = threading.Event()
    executor = main._BoundedThreadPoolExecutor(
        max_workers=1,
        max_outstanding=2,
        thread_name_prefix="bounded-queue-proof",
    )

    def occupy() -> None:
        started.set()
        release.wait(timeout=5)

    running = executor.submit(occupy)
    queued = executor.submit(lambda: "queued")
    try:
        assert started.wait(timeout=1)
        with pytest.raises(main._ExecutorSaturatedError):
            executor.submit(lambda: "overflow")
        assert queued.cancel()
        assert executor.submit(lambda: "replacement").cancel()
    finally:
        release.set()
        running.result(timeout=2)
        executor.shutdown(wait=True)


def test_public_auth_json_is_bounded_before_any_upstream_hop():
    oversized = json.dumps({"padding": "x" * (main.MAX_AUTH_BODY_BYTES + 1)})
    with TestClient(app) as client:
        responses = [
            client.post(path, content=oversized, headers={"Content-Type": "application/json"})
            for path in ("/api/signup", "/api/login")
        ]
    assert [response.status_code for response in responses] == [413, 413]


def test_retired_public_marketplace_routes_are_absent():
    registered_paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/accounts/v1/verify" not in registered_paths
    assert "/api/apps/{app_id}/reviews" not in registered_paths

    with TestClient(app) as client:
        responses = (
            client.post("/api/accounts/v1/verify", json={"token": "unused"}),
            client.post("/api/apps/dormant/reviews", json={"rating": 5, "body": "unused"}),
        )

    # The GET-only static catch-all makes unknown POST paths method-not-allowed; neither path has an
    # API handler or can execute retired marketplace behavior.
    assert [response.status_code for response in responses] == [405, 405]


def test_upstream_errors_and_unterminated_final_lines_remain_typed():
    raw = json.dumps({"error": "already chatting"}).encode()
    assert _upstream_error_event(409, raw) == {
        "type": "error",
        "status": 409,
        "detail": "already chatting",
    }
    assert _parsed_stream_event(b'{"type":"error","status":502}') == {
        "type": "error",
        "status": 502,
    }


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
    worker = threading.Thread(target=server.serve_forever, daemon=True)
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


def _relay(body: bytes) -> list[dict]:
    async def scenario() -> list[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with _real_upstream(body) as response:
            await asyncio.to_thread(_relay_upstream_events, response, queue, loop)
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
    worker = threading.Thread(target=server.serve_forever, daemon=True)
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


def test_upstream_relay_emits_first_event_before_response_eof():
    async def scenario() -> None:
        queue: asyncio.Queue = asyncio.Queue(maxsize=4)
        loop = asyncio.get_running_loop()
        first = b'{"type":"text","text":"first"}\n'
        rest = b'{"type":"done","reply":"first"}\n'
        with _real_delayed_upstream(first, rest) as (
            response,
            first_flushed,
            release_rest,
        ):
            relay = asyncio.create_task(asyncio.to_thread(_relay_upstream_events, response, queue, loop))
            assert await asyncio.to_thread(first_flushed.wait, 1)
            assert await asyncio.wait_for(queue.get(), timeout=1) == {
                "type": "text",
                "text": "first",
            }
            assert not relay.done()
            release_rest.set()
            await asyncio.wait_for(relay, timeout=2)
            assert await asyncio.wait_for(queue.get(), timeout=1) == {
                "type": "done",
                "reply": "first",
            }

    asyncio.run(scenario())


@contextlib.contextmanager
def _real_stream_driver(response_body: bytes, *, status: int = 200):
    requests: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            requests.append(self.rfile.read(length))
            self.send_response(status)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, *_args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    previous = main.CAPSULEDRIVER_URL
    main.CAPSULEDRIVER_URL = f"http://127.0.0.1:{server.server_port}"
    try:
        yield requests
    finally:
        main.CAPSULEDRIVER_URL = previous
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_stream_transport_preserves_utf8_prompt_and_reply_bytes():
    async def scenario() -> None:
        reply = "Olá, Capitão 🦐"
        encoded_reply = (
            json.dumps(
                {"type": "done", "reply": reply},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        queue: asyncio.Queue = asyncio.Queue(maxsize=4)
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        prompt = "ação e camarão 🦐"
        with _real_stream_driver(encoded_reply) as requests:
            await asyncio.to_thread(
                main._stream_lines,
                main._StreamRelay("cap-utf8", prompt, {}, queue, loop, started),
            )
        assert started.is_set()
        assert len(requests) == 1
        assert json.loads(requests[0]) == {"message": prompt}
        assert prompt.encode() in requests[0]
        assert b"\\u" not in requests[0]
        assert await queue.get() == {"type": "done", "reply": reply}
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
            await main._ws_run_turn(websocket, "cap-terminal", {}, "hello", started)
        events = [json.loads(message["text"]) for message in sent if message["type"] == "websocket.send"]
        assert started.is_set()
        assert len(requests) == 1
        assert events == [terminal]
        assert all(event.get("type") == "error" for event in events)
        assert not any(event.get("type") == "done" for event in events)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (409, {"error": "capsule already has an active chat turn"}),
        (429, {"detail": "chat rate limit exceeded"}),
    ],
)
def test_real_upstream_non_2xx_reaches_websocket_unchanged(status: int, payload: dict):
    async def scenario() -> None:
        websocket, sent = _websocket("{}")
        await websocket.accept()
        started = asyncio.Event()
        body = json.dumps(payload, separators=(",", ":")).encode()
        with _real_stream_driver(body, status=status) as requests:
            await main._ws_run_turn(websocket, "cap-upstream-error", {}, "hello", started)
        events = [json.loads(message["text"]) for message in sent if message["type"] == "websocket.send"]
        assert started.is_set()
        assert len(requests) == 1
        assert events == [
            {
                "type": "error",
                "status": status,
                "detail": payload.get("detail") or payload["error"],
            }
        ]

    asyncio.run(scenario())


def test_upstream_relay_is_bounded_and_fails_closed_on_protocol_errors():
    success = b'{"type":"text","text":"hello"}\n{"type":"done","reply":"hello"}'
    assert _relay(success) == [
        {"type": "text", "text": "hello"},
        {"type": "done", "reply": "hello"},
    ]

    malformed = b'{"type":"text","text":"partial"}\nnot-json\n{"type":"done"}\n'
    assert _relay(malformed) == [
        {"type": "text", "text": "partial"},
        {
            "type": "error",
            "status": 502,
            "detail": "brain stream contained malformed JSONL",
            "_relay_abort": True,
        },
    ]

    extra_after_terminal = b'{"type":"done"}\n{"type":"text","text":"late"}\n'
    assert _relay(extra_after_terminal) == [
        {
            "type": "error",
            "status": 502,
            "detail": "brain stream emitted data after its terminal event",
            "_relay_abort": True,
        }
    ]

    oversized = b"x" * (MAX_UPSTREAM_STREAM_LINE_BYTES + 1)
    assert _relay(oversized) == [
        {
            "type": "error",
            "status": 502,
            "detail": "brain stream line exceeded its size limit",
            "_relay_abort": True,
        }
    ]


def test_stream_workers_cannot_starve_the_default_control_pool():
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        release_default = threading.Event()
        default_started = asyncio.Event()

        def occupy_only_default_thread() -> None:
            loop.call_soon_threadsafe(default_started.set)
            release_default.wait(timeout=5)

        default_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        loop.set_default_executor(default_executor)
        occupied = loop.run_in_executor(None, occupy_only_default_thread)
        await asyncio.wait_for(default_started.wait(), timeout=1)

        reply = b'{"type":"done","reply":"reserved"}\n'
        queue: asyncio.Queue = asyncio.Queue(maxsize=4)
        started = asyncio.Event()
        try:
            with _real_stream_driver(reply):
                worker = loop.run_in_executor(
                    main._STREAM_EXECUTOR,
                    main._stream_lines,
                    main._StreamRelay("cap-pool", "hello", {}, queue, loop, started),
                )
                await asyncio.wait_for(started.wait(), timeout=1)
                await asyncio.wait_for(worker, timeout=2)
            assert await queue.get() == {"type": "done", "reply": "reserved"}
            assert await queue.get() is None
            assert not occupied.done()
        finally:
            release_default.set()
            await occupied

    asyncio.run(scenario())


@contextlib.contextmanager
def _real_relay_abort_driver(on_stop: Callable[[], None] | None = None):
    calls: list[str] = []
    unterminated = b'{"type":"text","text":"partial"}\n'

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            calls.append(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            if self.path.endswith("/chat/stop"):
                if on_stop is not None:
                    on_stop()
                body = b'{"requested":true,"accepted":true}'
                content_type = "application/json"
            else:
                body = unterminated
                content_type = "application/x-ndjson"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    previous = main.CAPSULEDRIVER_URL
    main.CAPSULEDRIVER_URL = f"http://127.0.0.1:{server.server_port}"
    try:
        yield calls
    finally:
        main.CAPSULEDRIVER_URL = previous
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_local_relay_eof_stops_provider_before_browser_error():
    async def scenario() -> None:
        websocket, sent = _websocket("{}")
        await websocket.accept()
        started = asyncio.Event()
        with _real_relay_abort_driver() as calls:
            await main._ws_run_turn(websocket, "cap-abort", {}, "hello", started)
        events = [json.loads(message["text"]) for message in sent if message["type"] == "websocket.send"]
        assert events == [
            {"type": "text", "text": "partial"},
            {
                "type": "error",
                "status": 502,
                "detail": "brain stream ended without a terminal event",
            },
        ]
        assert calls == [
            "/v1/capsules/cap-abort/chat/stream",
            "/v1/capsules/cap-abort/chat/stop",
        ]

    asyncio.run(scenario())


def test_browser_disconnect_requests_provider_stop_exactly_once():
    async def scenario() -> None:
        incoming = iter(({"type": "websocket.connect"},))

        async def receive() -> dict:
            return next(incoming)

        async def send(message: dict) -> None:
            if message["type"] == "websocket.send":
                raise WebSocketDisconnect()

        websocket = WebSocket({"type": "websocket", "path": "/"}, receive, send)
        await websocket.accept()
        queue: asyncio.Queue = asyncio.Queue()
        queue.put_nowait({"type": "text", "text": "partial"})
        stopped = threading.Event()

        with _real_relay_abort_driver(stopped.set) as calls:
            worker = asyncio.create_task(asyncio.to_thread(stopped.wait))
            try:
                turn = main._WsTurn(
                    websocket,
                    "cap-disconnect",
                    {},
                    "hello",
                    asyncio.Event(),
                    asyncio.Event(),
                )
                with pytest.raises(WebSocketDisconnect):
                    await main._deliver_turn(turn, queue, worker)
            finally:
                stopped.set()
                await worker

        assert calls == ["/v1/capsules/cap-disconnect/chat/stop"]

    asyncio.run(scenario())


class _BrainControlHandler(BaseHTTPRequestHandler):
    calls: list[tuple[str, str, dict]]
    state: dict[str, int]
    finalize_token: str

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self.calls.append(("GET", self.path, {}))
        if self.path == "/v1/capsules":
            self._json(
                200,
                {
                    "capsules": [
                        {"id": "cap-codex", "brain": "codex"},
                        {"id": "cap-claude", "brain": "claude-code"},
                    ]
                },
            )
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.calls.append(("POST", self.path, body))
        if self.path == "/v1/verify":
            self._json(200, {"account_id": "account-1", "username": "captain"})
        elif self.path == "/v1/brains/revoke-begin":
            self.state["begin_count"] += 1
            self._json(
                200,
                {
                    "provider": body.get("provider"),
                    "status": "revoking",
                    "generation": 7,
                    "already_absent": False,
                    "already_revoking": self.state["begin_count"] > 1,
                },
            )
        elif self.path == "/v1/capsules/cap-codex/brain/deconfigure":
            status = 500 if self.state["revoke_failures"] else 200
            self.state["revoke_failures"] = max(0, self.state["revoke_failures"] - 1)
            self._json(
                status,
                {"configured": False} if status == 200 else {"error": "failed"},
            )
        elif self.path == "/v1/internal/brains/revoke-finalize":
            if self.headers.get("Authorization") != f"Bearer {self.finalize_token}":
                self._json(403, {"error": "invalid or missing credentials"})
                return
            if body.get("generation") != 7:
                self._json(409, {"detail": "generation mismatch"})
            else:
                self._json(200, {"deleted": True, "generation": 7})
        elif self.path == "/v1/capsules/cap-codex/brain/login/cancel":
            self._json(200, {"provider": "codex", "mode": "device_code", "cancelled": True})
        elif self.path.startswith("/v1/capsules/") and self.path.endswith("/create"):
            self._json(201, {"created": True, **body})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, *_args) -> None:
        pass


@contextlib.contextmanager
def _brain_control_plane(*, revoke_status: int = 200, finalize_token_available: bool = True):
    calls: list[tuple[str, str, dict]] = []
    finalize_token = secrets.token_hex(32)
    handler = type(
        "_ScopedBrainControlHandler",
        (_BrainControlHandler,),
        {
            "calls": calls,
            "state": {
                "begin_count": 0,
                "revoke_failures": 1 if revoke_status != 200 else 0,
            },
            "finalize_token": finalize_token,
        },
    )

    with tempfile.TemporaryDirectory() as temporary:
        token_path = Path(temporary) / "brain-finalize-token"
        if finalize_token_available:
            token_path.write_text(finalize_token)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        previous = (
            main.ACCOUNTS_URL,
            main.CAPSULEDRIVER_URL,
            main.BRAIN_FINALIZE_TOKEN_FILE,
        )
        main.ACCOUNTS_URL = main.CAPSULEDRIVER_URL = base
        main.BRAIN_FINALIZE_TOKEN_FILE = token_path
        try:
            yield calls
        finally:
            (
                main.ACCOUNTS_URL,
                main.CAPSULEDRIVER_URL,
                main.BRAIN_FINALIZE_TOKEN_FILE,
            ) = previous
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


def test_brain_delete_revokes_every_matching_capsule_before_deleting_ciphertext():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.delete("/api/brains/codex")
    assert response.status_code == 200
    begin = (
        "POST",
        "/v1/brains/revoke-begin",
        {"token": "valid-token", "provider": "codex"},
    )
    inventory = ("GET", "/v1/capsules", {})
    deconfigure = ("POST", "/v1/capsules/cap-codex/brain/deconfigure", {})
    finalize = (
        "POST",
        "/v1/internal/brains/revoke-finalize",
        {"token": "valid-token", "provider": "codex", "generation": 7},
    )
    assert begin in calls
    assert deconfigure in calls
    assert not any(call[1] == "/v1/capsules/cap-claude/brain/deconfigure" for call in calls)
    assert calls.index(begin) < calls.index(inventory) < calls.index(deconfigure) < calls.index(finalize)


def test_capsule_create_forwards_the_account_scoped_model_to_the_real_control_plane():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.post(
            "/api/capsules",
            json={"name": "Astra", "brain": "codex", "model": "gpt-5.2-codex"},
        )
    assert response.status_code == 201
    creates = [
        call
        for call in calls
        if call[0] == "POST" and call[1].startswith("/v1/capsules/") and call[1].endswith("/create")
    ]
    assert creates == [
        (
            "POST",
            f"/v1/capsules/{main._cid_for('account-1', 'Astra')}/create",
            {"name": "Astra", "brain": "codex", "model": "gpt-5.2-codex"},
        )
    ]


def test_codex_device_login_cancel_is_forwarded_as_a_post():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.post("/api/capsules/cap-codex/brain/login/cancel")
    assert response.status_code == 200
    assert response.json() == {
        "provider": "codex",
        "mode": "device_code",
        "cancelled": True,
    }
    assert ("POST", "/v1/capsules/cap-codex/brain/login/cancel", {}) in calls


def test_capsule_ids_bind_the_complete_account_and_normalized_name():
    first = main._cid_for("account-prefix-one", "A very long shared capsule name alpha")
    same = main._cid_for("account-prefix-one", "A very long shared capsule name alpha")
    other_account = main._cid_for("account-prefix-two", "A very long shared capsule name alpha")
    other_tail = main._cid_for("account-prefix-one", "A very long shared capsule name omega")

    assert first == same
    assert first != other_account
    assert first != other_tail
    assert len(first) <= 40
    assert re.fullmatch(r"[a-z0-9_]+", first)
    assert main._cid_for("account-prefix-one", "!!!") == ""


def test_capsule_create_and_install_reject_bodies_before_control_plane_forwarding():
    create_body = json.dumps(
        {
            "name": "Astra",
            "padding": "x" * main.MAX_CAPSULE_CREATE_BODY_BYTES,
        }
    ).encode()
    install_body = json.dumps(
        {
            "app": "notification-center",
            "padding": "x" * main.MAX_CAPSULE_INSTALL_BODY_BYTES,
        }
    ).encode()
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        create = client.post(
            "/api/capsules",
            content=create_body,
            headers={"Content-Type": "application/json"},
        )
        install = client.post(
            "/api/capsules/cap_codex/install",
            content=install_body,
            headers={"Content-Type": "application/json", "Origin": "https://shimpz.com"},
        )
    assert create.status_code == 413
    assert install.status_code == 413
    forwarded_mutations = [
        path for method, path, _body in calls if method == "POST" and path.endswith(("/create", "/apps"))
    ]
    assert forwarded_mutations == []


def test_brain_delete_keeps_ciphertext_when_any_runtime_revoke_fails():
    with _brain_control_plane(revoke_status=500) as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.delete("/api/brains/codex")
    assert response.status_code == 502
    assert not any(call[1] == "/v1/internal/brains/revoke-finalize" for call in calls)


def test_brain_delete_fails_closed_without_the_finalizer_bearer_after_purge():
    with (
        _brain_control_plane(finalize_token_available=False) as calls,
        TestClient(app) as client,
    ):
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.delete("/api/brains/codex")
    assert response.status_code == 502
    assert response.json() == {"detail": "Brain credential finalization is unavailable"}
    assert any(call[1].endswith("/brain/deconfigure") for call in calls)
    assert not any(call[1] == "/v1/internal/brains/revoke-finalize" for call in calls)


def test_brain_delete_retry_resumes_the_same_revoking_generation():
    with _brain_control_plane(revoke_status=500) as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        first = client.delete("/api/brains/codex")
        second = client.delete("/api/brains/codex")
    assert first.status_code == 502
    assert second.status_code == 200
    begins = [call for call in calls if call[1] == "/v1/brains/revoke-begin"]
    finalizes = [call for call in calls if call[1] == "/v1/internal/brains/revoke-finalize"]
    assert len(begins) == 2
    assert finalizes == [
        (
            "POST",
            "/v1/internal/brains/revoke-finalize",
            {"token": "valid-token", "provider": "codex", "generation": 7},
        )
    ]

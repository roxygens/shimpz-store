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
from fastapi import Request, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import main
from app.main import (
    ACCOUNT_COOKIE,
    CHAT_WS_SUBPROTOCOL,
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
    _validated_terminal_event,
    _ws_dispatch,
    _ws_receive_bounded_json,
    app,
)

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


def _input_challenge(
    *, team_id: str = TEST_TEAM_ID, challenge_id: str = "a" * 32
) -> dict:
    return {
        "type": "input-required",
        "status": "input-required",
        "team_id": team_id,
        "turn_id": challenge_id,
        "challenge_id": challenge_id,
        "request": {
            "type": "choice",
            "title": "Choose zone",
            "summary": "Choose the target zone.",
            "docs": None,
            "options": ["example.com", "example.net"],
        },
    }


def _approval_challenge(
    *, team_id: str = TEST_TEAM_ID, challenge_id: str = "b" * 32
) -> dict:
    return {
        "type": "approval-required",
        "status": "approval-required",
        "team_id": team_id,
        "turn_id": challenge_id,
        "challenge_id": challenge_id,
        "requirements": [
            {
                "assistant_id": "shimpz-cloudflare",
                "assistant_name": "Shimpz Cloudflare",
                "power_id": "list-zones",
                "title": "Publish zones",
                "summary": "Publish the current zones?",
                "docs": None,
                "approval": "once",
            }
        ],
    }


def _websocket_disconnect_code(
    client: TestClient,
    origin: str | None,
    subprotocols: tuple[str, ...] = (CHAT_WS_SUBPROTOCOL,),
) -> int:
    headers = {"origin": origin} if origin is not None else {}
    with (
        pytest.raises(WebSocketDisconnect) as raised,
        client.websocket_connect(
            "/api/teams/test_team/chat/ws",
            headers=headers,
            subprotocols=list(subprotocols),
        ),
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


def test_websocket_requires_and_negotiates_the_v2_chat_subprotocol(monkeypatch):
    allowed = next(iter(WS_ALLOWED_ORIGINS))
    with TestClient(app) as client:
        assert _websocket_disconnect_code(client, allowed, ()) == 4406
        assert _websocket_disconnect_code(client, allowed, ("shimpz.chat.v1",)) == 4406

    async def verified(_ws: WebSocket) -> tuple[str, str]:
        return "account-token", "account-one"

    monkeypatch.setattr(main, "_ws_verify", verified)
    with (
        TestClient(app) as client,
        client.websocket_connect(
            "/api/teams/test_team/chat/ws",
            headers={"origin": allowed},
            subprotocols=[CHAT_WS_SUBPROTOCOL],
        ) as websocket,
    ):
        assert websocket.accepted_subprotocol == CHAT_WS_SUBPROTOCOL


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


def test_chat_turn_requires_an_explicit_bounded_assistant_scope():
    assert main._chat_turn_payload(
        {
            "message": "  hello  ",
            "files": ["a" * 32],
            "assistant_ids": ["shimpz-cloudflare"],
        }
    ) == {
        "message": "hello",
        "files": ["a" * 32],
        "assistant_ids": ["shimpz-cloudflare"],
    }
    assert main._chat_turn_payload(
        {"message": "brain only", "files": [], "assistant_ids": []}
    ) == {
        "message": "brain only",
        "files": [],
        "assistant_ids": [],
    }

    invalid = (
        {"message": "implicit scope", "files": []},
        {"message": "duplicate", "files": [], "assistant_ids": ["one", "one"]},
        {"message": "invalid", "files": [], "assistant_ids": ["../escape"]},
        {
            "message": "too many",
            "files": [],
            "assistant_ids": [f"assistant-{index}" for index in range(17)],
        },
    )
    for payload in invalid:
        with pytest.raises(ClientPayloadError) as raised:
            main._chat_turn_payload(payload)
        assert raised.value.status == 400


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


def test_websocket_rejects_binary_frames_even_when_they_contain_valid_json(monkeypatch):
    async def verified(_ws: WebSocket) -> tuple[str, str]:
        return "account-token", "account-one"

    monkeypatch.setattr(main, "_ws_verify", verified)
    allowed = next(iter(WS_ALLOWED_ORIGINS))
    with (
        TestClient(app) as client,
        client.websocket_connect(
            "/api/teams/test_team/chat/ws",
            headers={"origin": allowed},
            subprotocols=[CHAT_WS_SUBPROTOCOL],
        ) as websocket,
    ):
        websocket.send_bytes(b'{"type":"stop"}')
        assert websocket.receive_json() == {
            "type": "error",
            "status": 415,
            "detail": "WebSocket frame must be text JSON",
        }
        with pytest.raises(WebSocketDisconnect) as raised:
            websocket.receive_json()
        assert raised.value.code == 1003


@pytest.mark.parametrize("frame", ("not-json", "[]", '{"type":"stop","type":"chat"}'))
def test_websocket_rejects_ambiguous_or_non_object_json_frames(frame: str):
    async def scenario() -> None:
        websocket, _ = _websocket(frame)
        await websocket.accept()
        with pytest.raises(WebSocketPayloadError) as raised:
            await _ws_receive_bounded_json(websocket)
        assert raised.value.status == 400
        assert raised.value.close_code == 1007

    asyncio.run(scenario())


def test_websocket_allows_only_one_local_turn_task():
    async def scenario() -> None:
        websocket, sent = _websocket("{}")
        await websocket.accept()
        blocker = asyncio.Event()
        active_turn = asyncio.create_task(blocker.wait())
        state = {"turns": {active_turn}}
        try:
            await _ws_dispatch(
                websocket,
                "test-team",
                {},
                {"type": "chat", "message": "second", "files": [], "assistant_ids": []},
                state,
            )
        finally:
            active_turn.cancel()
            await asyncio.gather(active_turn, return_exceptions=True)

        assert len(state["turns"]) == 1
        assert json.loads(sent[-1]["text"]) == {
            "type": "error",
            "status": 409,
            "detail": "team already has an active chat turn",
        }

    asyncio.run(scenario())


def test_websocket_rejects_retired_answer_frames():
    async def scenario() -> None:
        websocket, sent = _websocket("{}")
        await websocket.accept()
        await _ws_dispatch(
            websocket,
            "test-team",
            {},
            {"type": "answer", "rid": "legacy", "answer": "yes"},
            {"turns": set()},
        )
        assert json.loads(sent[-1]["text"]) == {
            "type": "error",
            "status": 400,
            "detail": "unsupported chat frame",
        }

    asyncio.run(scenario())


def test_websocket_relays_a_bound_input_submission_to_the_hosted_controller(
    monkeypatch,
):
    challenge_id = "a" * 32
    calls: list[tuple] = []

    def completed_call(base, method, path, payload, headers):
        calls.append((base, method, path, payload, headers))
        return 200, {
            "team_id": TEST_TEAM_ID,
            "team_name": "Marketing",
            "reply": "Completed.",
        }

    monkeypatch.setattr(main, "_call", completed_call)

    async def scenario() -> None:
        websocket, sent = _websocket("{}")
        await websocket.accept()
        state = {
            "turns": set(),
            "starts": {},
            "dispatches": {},
            "leases": {},
            "deliveries": {},
            "stop_requested": False,
            "pending_challenge_id": challenge_id,
            "pending_challenge_type": "input",
        }
        await _ws_dispatch(
            websocket,
            TEST_TEAM_ID,
            {"X-Shimpz-Account": "account-token"},
            {
                "type": "input-submit",
                "challenge_id": challenge_id,
                "answer": "example.com",
            },
            state,
        )
        await asyncio.gather(*tuple(state["turns"]))
        await asyncio.sleep(0)
        events = [
            json.loads(message["text"])
            for message in sent
            if message["type"] == "websocket.send"
        ]
        assert events == [
            {
                "type": "done",
                "team_id": TEST_TEAM_ID,
                "team_name": "Marketing",
                "reply": "Completed.",
            }
        ]
        assert state["pending_challenge_id"] is None
        assert state["pending_challenge_type"] is None

    asyncio.run(scenario())
    assert calls == [
        (
            main.TEAMDRIVER_URL,
            "POST",
            f"/v1/teams/{TEST_TEAM_ID}/chat/input",
            {"challenge_id": challenge_id, "answer": "example.com"},
            {"X-Shimpz-Account": "account-token"},
        )
    ]


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
                "test-team",
                {},
                {
                    "type": "chat",
                    "message": "beyond the bound",
                    "files": [],
                    "assistant_ids": [],
                },
                {"turns": set()},
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
        first = {"type": "stopped"}
        second = {"type": "error", "status": 502, "detail": "failed"}
        await queue.put(first)
        loop = asyncio.get_running_loop()
        producer = asyncio.create_task(
            asyncio.to_thread(
                _stream_queue_put,
                queue,
                loop,
                second,
            )
        )

        assert await queue.get() == first
        assert await asyncio.wait_for(producer, timeout=1) is True
        assert await queue.get() == second

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
        state = {"turns": set()}
        try:
            await _ws_dispatch(
                websocket,
                "team-queued",
                {},
                {
                    "type": "chat",
                    "message": "must never execute",
                    "files": [],
                    "assistant_ids": [],
                },
                state,
            )
            await asyncio.sleep(0)
            assert admission.snapshot() == (1, 1)

            await _ws_dispatch(websocket, "team-queued", {}, {"type": "stop"}, state)
            await _ws_dispatch(websocket, "team-queued", {}, {"type": "stop"}, state)
            assert admission.snapshot() == (1, 0)
            assert not state["turns"]
            events = [
                json.loads(message["text"])
                for message in sent
                if message["type"] == "websocket.send"
            ]
            assert events == [{"type": "stopped"}]

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


def test_duplicate_stop_then_disconnect_requests_provider_stop_once(monkeypatch):
    async def scenario() -> None:
        calls = []

        async def stop(team_id: str, headers: dict) -> tuple[int, dict]:
            calls.append((team_id, headers))
            return 200, {"requested": True}

        class RunningLease:
            @staticmethod
            def cancel_if_queued() -> bool:
                return False

        monkeypatch.setattr(main, "_driver_stop", stop)
        websocket, _ = _websocket("{}")
        await websocket.accept()
        started = asyncio.Event()
        dispatched = asyncio.Event()
        started.set()
        dispatched.set()
        delivery = main._RelayDelivery()
        turn = main._WsTurn(
            websocket,
            "team-stop-once",
            {"X-Shimpz-Account": "token"},
            "hello",
            started,
            dispatched,
            delivery=delivery,
        )
        queue: asyncio.Queue = asyncio.Queue()
        worker = asyncio.get_running_loop().create_future()
        active = asyncio.create_task(main._deliver_turn(turn, queue, worker))
        await asyncio.sleep(0)
        state = {
            "turns": {active},
            "starts": {active: started},
            "dispatches": {active: dispatched},
            "leases": {active: RunningLease()},
            "deliveries": {active: delivery},
            "stop_requested": False,
        }

        await main._ws_stop_turn(websocket, turn.team_id, turn.headers, state)
        await main._ws_stop_turn(websocket, turn.team_id, turn.headers, state)
        active.cancel()  # The endpoint cancels the relay after a browser disconnect.
        worker.set_result(None)
        await asyncio.gather(active, return_exceptions=True)

        assert calls == [("team-stop-once", {"X-Shimpz-Account": "token"})]
        assert delivery.stop_attempted

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "event",
    [
        {"type": "text", "text": "legacy"},
        _done("invalid Team identity", team_name=" Marketing "),
    ],
)
def test_final_websocket_gate_converts_invalid_events(event: dict, monkeypatch):
    async def scenario() -> None:
        stops = []

        async def stop(team_id: str, headers: dict) -> tuple[int, dict]:
            stops.append((team_id, headers))
            return 200, {"requested": True}

        monkeypatch.setattr(main, "_driver_stop", stop)
        websocket, sent = _websocket("{}")
        await websocket.accept()
        turn = main._WsTurn(
            websocket,
            "team_terminal_gate",
            {"X-Shimpz-Account": "token"},
            "hello",
            asyncio.Event(),
            asyncio.Event(),
        )
        delivery = main._RelayDelivery()
        await main._send_relay_event(turn, event, delivery)
        assert json.loads(sent[-1]["text"]) == {
            "type": "error",
            "status": 502,
            "detail": main.TERMINAL_CONTRACT_ERROR,
        }
        assert stops == [("team_terminal_gate", {"X-Shimpz-Account": "token"})]
        assert delivery.terminal_seen and delivery.aborted

    asyncio.run(scenario())


def test_websocket_connection_admission_bounds_global_account_and_team_counts():
    admission = main._WsConnectionAdmission(
        global_limit=3, account_limit=2, team_limit=1
    )
    account_a_one = admission.reserve("account-a", "team-1")
    assert account_a_one is not None
    assert admission.reserve("account-a", "team-1") is None
    account_a_two = admission.reserve("account-a", "team-2")
    assert account_a_two is not None
    assert admission.reserve("account-a", "team-3") is None
    account_b_one = admission.reserve("account-b", "team-1")
    assert account_b_one is not None
    assert admission.reserve("account-b", "team-2") is None
    assert admission.snapshot() == (
        3,
        {"account-a": 2, "account-b": 1},
        {
            ("account-a", "team-1"): 1,
            ("account-a", "team-2"): 1,
            ("account-b", "team-1"): 1,
        },
    )

    account_a_one.release()
    replacement = admission.reserve("account-b", "team-2")
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
            client.post(
                path, content=oversized, headers={"Content-Type": "application/json"}
            )
            for path in ("/api/signup", "/api/login")
        ]
    assert [response.status_code for response in responses] == [413, 413]


def test_signup_forwards_only_the_persisted_credentials(monkeypatch):
    forwarded = []

    async def bounded_call(*args, extra=None):
        executor, base, method, path, payload = args
        forwarded.append((executor, base, method, path, payload, extra))
        return 400, {"error": "rejected"}

    monkeypatch.setattr(main, "_bounded_call", bounded_call)
    with TestClient(app) as client:
        response = client.post(
            "/api/signup",
            json={
                "username": "captain",
                "password": "correct horse battery staple",
                "github": "ignored",
            },
        )

    assert response.status_code == 400
    assert len(forwarded) == 1
    _executor, base, method, path, payload, extra = forwarded[0]
    assert (base, method, path) == (main.ACCOUNTS_URL, "POST", "/v1/signup")
    assert payload == {
        "username": "captain",
        "password": "correct horse battery staple",
    }
    assert set(extra) == {"X-Forwarded-For"}


def test_retired_public_marketplace_routes_are_absent():
    registered_paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/accounts/v1/verify" not in registered_paths
    assert "/api/apps/{app_id}/reviews" not in registered_paths

    with TestClient(app) as client:
        responses = (
            client.post("/api/accounts/v1/verify", json={"token": "unused"}),
            client.post(
                "/api/apps/dormant/reviews", json={"rating": 5, "body": "unused"}
            ),
        )

    # The GET-only static catch-all makes unknown POST paths method-not-allowed; neither path has an
    # API handler or can execute retired marketplace behavior.
    assert [response.status_code for response in responses] == [405, 405]


def test_upstream_http_errors_and_unterminated_terminal_lines_are_redacted():
    leak_marker = "upstream-private-marker-7e9b"
    http_error = _upstream_error_event(409, json.dumps({"error": leak_marker}).encode())
    stream_error = _parsed_stream_event(
        json.dumps({"type": "error", "status": 502, "detail": leak_marker}).encode(),
        TEST_TEAM_ID,
    )
    assert http_error == {
        "type": "error",
        "status": 409,
        "detail": "chat request was rejected",
    }
    assert stream_error == {
        "type": "error",
        "status": 502,
        "detail": "chat service is temporarily unavailable",
    }
    assert leak_marker not in json.dumps([http_error, stream_error])


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (
            _done("complete", team_name="Marketing"),
            _done("complete", team_name="Marketing"),
        ),
        (_input_challenge(), _input_challenge()),
        (_approval_challenge(), _approval_challenge()),
        (
            {"type": "error", "status": 504, "detail": "provider timed out"},
            {"type": "error", "status": 504, "detail": "chat service timed out"},
        ),
        ({"type": "stopped"}, {"type": "stopped"}),
    ],
)
def test_terminal_event_contract_accepts_only_exact_bounded_schemas(
    event: dict, expected: dict
):
    assert _validated_terminal_event(event, TEST_TEAM_ID) == expected


def test_terminal_event_contract_excludes_out_of_band_account_challenges():
    assert (
        _validated_terminal_event(
            {
                "type": "accounts-required",
                "status": "accounts-required",
                "team_id": TEST_TEAM_ID,
                "challenge_id": "a" * 32,
                "requirements": [],
            },
            TEST_TEAM_ID,
        )
        is None
    )


@pytest.mark.parametrize(
    "event",
    [
        {"type": "text", "text": "partial"},
        {"type": "tool", "label": "shell"},
        {"type": "ask", "text": "approve?"},
        {"type": "answered", "answered": True},
        _input_challenge(team_id="another_team"),
        {
            **_input_challenge(),
            "request": {**_input_challenge()["request"], "type": "unknown"},
        },
        {**_approval_challenge(), "requirements": []},
        {
            **_approval_challenge(),
            "requirements": [
                {
                    **_approval_challenge()["requirements"][0],
                    "summary": "private\x00value",
                }
            ],
        },
        {**_done(), "extra": True},
        {"type": "done", "reply": "hello"},
        _done("hello", team_id="another_team"),
        _done("hello", team_name=" Marketing "),
        _done("hello", team_name="Marketing\x00"),
        _done("x" * (main.MAX_CHAT_REPLY_CHARS + 1)),
        {"type": "error", "status": True, "detail": "failed"},
        {"type": "error", "status": 200, "detail": "not an error"},
        {
            "type": "error",
            "status": 502,
            "detail": "x" * (main.MAX_CHAT_ERROR_DETAIL_CHARS + 1),
        },
        {"type": "stopped", "requested": True},
    ],
)
def test_terminal_event_contract_rejects_legacy_extra_and_unbounded_values(event: dict):
    assert _validated_terminal_event(event, TEST_TEAM_ID) is None


def test_terminal_event_parser_rejects_duplicate_fields():
    assert (
        _parsed_stream_event(b'{"type":"stopped","type":"done"}', TEST_TEAM_ID) is None
    )


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
            await asyncio.to_thread(
                _relay_upstream_events, response, queue, loop, team_id
            )
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
    worker = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    worker.start()
    previous = main.TEAMDRIVER_URL
    main.TEAMDRIVER_URL = f"http://127.0.0.1:{server.server_port}"
    try:
        yield requests
    finally:
        main.TEAMDRIVER_URL = previous
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


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
        events = [
            json.loads(message["text"])
            for message in sent
            if message["type"] == "websocket.send"
        ]
        assert started.is_set()
        assert len(requests) == 1
        expected_detail = (
            "chat service timed out"
            if terminal["status"] == 504
            else "chat service is temporarily unavailable"
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
        events = [
            json.loads(message["text"])
            for message in sent
            if message["type"] == "websocket.send"
        ]
        assert started.is_set()
        assert len(requests) == 1
        assert events == [
            {
                "type": "error",
                "status": status,
                "detail": (
                    "chat service is busy; try again shortly"
                    if status == 429
                    else "chat request was rejected"
                ),
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
    legacy_then_terminal = (
        b'{"type":"text","text":"partial"}\n' + json.dumps(_done()).encode() + b"\n"
    )
    assert _relay(legacy_then_terminal) == [protocol_error]

    malformed = b"not-json\n" + json.dumps(_done()).encode() + b"\n"
    assert _relay(malformed) == [protocol_error]

    extra_after_terminal = json.dumps(_done()).encode() + b'\n{"type":"stopped"}\n'
    assert _relay(extra_after_terminal) == [protocol_error]

    mismatched_team = json.dumps(_done(team_id="another_team")).encode() + b"\n"
    assert _relay(mismatched_team) == [protocol_error]

    assert _relay(b"") == [protocol_error]

    oversized = b"x" * (MAX_UPSTREAM_STREAM_LINE_BYTES + 1)
    assert _relay(oversized) == [protocol_error]


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

        reply = (
            json.dumps(
                _done("reserved", team_id="team_pool"),
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        queue: asyncio.Queue = asyncio.Queue(maxsize=4)
        started = asyncio.Event()
        try:
            with _real_stream_driver(reply):
                worker = loop.run_in_executor(
                    main._STREAM_EXECUTOR,
                    main._stream_lines,
                    main._StreamRelay("team_pool", "hello", {}, queue, loop, started),
                )
                await asyncio.wait_for(started.wait(), timeout=1)
                await asyncio.wait_for(worker, timeout=2)
            assert await queue.get() == _done("reserved", team_id="team_pool")
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
    worker = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    worker.start()
    previous = main.TEAMDRIVER_URL
    main.TEAMDRIVER_URL = f"http://127.0.0.1:{server.server_port}"
    try:
        yield calls
    finally:
        main.TEAMDRIVER_URL = previous
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_local_relay_eof_stops_provider_before_browser_error():
    async def scenario() -> None:
        websocket, sent = _websocket("{}")
        await websocket.accept()
        started = asyncio.Event()
        with _real_relay_abort_driver() as calls:
            await main._ws_run_turn(
                websocket,
                "team-abort",
                {},
                {"message": "hello", "files": [], "assistant_ids": []},
                started,
            )
        events = [
            json.loads(message["text"])
            for message in sent
            if message["type"] == "websocket.send"
        ]
        assert events == [
            {
                "type": "error",
                "status": 502,
                "detail": "chat service is temporarily unavailable",
            },
        ]
        assert calls == [
            "/v1/teams/team-abort/chat/stream",
            "/v1/teams/team-abort/chat/stop",
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
        queue.put_nowait(_done("complete", team_id="team_disconnect"))
        stopped = threading.Event()

        with _real_relay_abort_driver(stopped.set) as calls:
            worker = asyncio.create_task(asyncio.to_thread(stopped.wait))
            try:
                turn = main._WsTurn(
                    websocket,
                    "team_disconnect",
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

        assert calls == ["/v1/teams/team_disconnect/chat/stop"]

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
        if self.path == "/v1/teams/team-openai/inference":
            self._json(200, {"provider": "openai", "model": "gpt-5.5"})
            return
        self._json(404, {"error": "not found"})

    def do_PUT(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.calls.append(("PUT", self.path, body))
        if self.path == "/v1/teams/team-openai/inference":
            self._json(200, {"team_id": "team-openai", **body})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.calls.append(("POST", self.path, body))
        if self.path == "/v1/verify":
            self._json(200, {"account_id": "account-1", "username": "captain"})
        elif self.path == "/v1/brains/upsert":
            self._json(
                200,
                {
                    "provider": body.get("provider"),
                    "auth_type": body.get("auth_type"),
                    "status": "configured",
                },
            )
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
        elif self.path == "/v1/internal/brains/revoke-finalize":
            if self.headers.get("Authorization") != f"Bearer {self.finalize_token}":
                self._json(403, {"error": "invalid or missing credentials"})
                return
            if body.get("generation") != 7:
                self._json(409, {"detail": "generation mismatch"})
            else:
                self._json(200, {"deleted": True, "generation": 7})
        elif self.path.startswith("/v1/teams/") and self.path.endswith("/create"):
            self._json(201, {"created": True, **body})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, *_args) -> None:
        pass


@contextlib.contextmanager
def _brain_control_plane(*, finalize_token_available: bool = True):
    calls: list[tuple[str, str, dict]] = []
    finalize_token = secrets.token_hex(32)
    handler = type(
        "_ScopedBrainControlHandler",
        (_BrainControlHandler,),
        {
            "calls": calls,
            "state": {
                "begin_count": 0,
            },
            "finalize_token": finalize_token,
        },
    )

    with tempfile.TemporaryDirectory() as temporary:
        token_path = Path(temporary) / "brain-finalize-token"
        if finalize_token_available:
            token_path.write_text(finalize_token)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        worker = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        previous = (
            main.ACCOUNTS_URL,
            main.TEAMDRIVER_URL,
            main.BRAIN_FINALIZE_TOKEN_FILE,
        )
        main.ACCOUNTS_URL = main.TEAMDRIVER_URL = base
        main.BRAIN_FINALIZE_TOKEN_FILE = token_path
        try:
            yield calls
        finally:
            (
                main.ACCOUNTS_URL,
                main.TEAMDRIVER_URL,
                main.BRAIN_FINALIZE_TOKEN_FILE,
            ) = previous
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


def test_provider_key_delete_revokes_generation_without_touching_teams():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.delete("/api/brains/openai")
    assert response.status_code == 200
    begin = (
        "POST",
        "/v1/brains/revoke-begin",
        {"token": "valid-token", "provider": "openai"},
    )
    finalize = (
        "POST",
        "/v1/internal/brains/revoke-finalize",
        {"token": "valid-token", "provider": "openai", "generation": 7},
    )
    assert begin in calls
    assert finalize in calls
    assert calls.index(begin) < calls.index(finalize)
    assert not any(call[1].startswith("/v1/teams/") for call in calls)


def test_model_credentials_accept_only_generic_provider_api_keys():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        valid = client.post(
            "/api/brains/anthropic",
            json={"auth_type": "api_key", "secret": "secret-key"},
        )
        oauth = client.post(
            "/api/brains/anthropic",
            json={"auth_type": "oauth", "secret": "oauth-token"},
        )
        legacy = client.post(
            "/api/brains/codex",
            json={"auth_type": "api_key", "secret": "secret-key"},
        )

    assert valid.status_code == 200
    assert valid.json() == {
        "provider": "anthropic",
        "auth_type": "api_key",
        "status": "configured",
    }
    assert oauth.status_code == legacy.status_code == 400
    assert [call for call in calls if call[1] == "/v1/brains/upsert"] == [
        (
            "POST",
            "/v1/brains/upsert",
            {
                "token": "valid-token",
                "provider": "anthropic",
                "auth_type": "api_key",
                "secret": "secret-key",
            },
        )
    ]


def test_team_create_forwards_the_account_scoped_model_to_the_real_control_plane():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.post(
            "/api/teams",
            json={"team_name": "Astra", "provider": "openai", "model": "gpt-5.5"},
        )
        legacy = client.post(
            "/api/teams",
            json={
                "team_name": "Legacy",
                "provider": "openai",
                "model": "gpt-5.5",
                "brain": "codex",
            },
        )
    assert response.status_code == 201
    assert legacy.status_code == 400
    creates = [
        call
        for call in calls
        if call[0] == "POST"
        and call[1].startswith("/v1/teams/")
        and call[1].endswith("/create")
    ]
    assert creates == [
        (
            "POST",
            f"/v1/teams/{main._team_id_for('account-1', 'Astra')}/create",
            {"team_name": "Astra", "provider": "openai", "model": "gpt-5.5"},
        )
    ]


def test_team_inference_is_read_and_updated_without_recreating_team():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        current = client.get("/api/teams/team-openai/inference")
        updated = client.put(
            "/api/teams/team-openai/inference",
            json={"provider": "anthropic", "model": "claude-sonnet-5"},
        )
        retired_login = client.post("/api/teams/team-openai/brain/login/start")

    assert current.status_code == updated.status_code == 200
    assert current.json() == {"provider": "openai", "model": "gpt-5.5"}
    assert updated.json() == {
        "team_id": "team-openai",
        "provider": "anthropic",
        "model": "claude-sonnet-5",
    }
    assert retired_login.status_code in {404, 405}
    assert ("GET", "/v1/teams/team-openai/inference", {}) in calls
    assert (
        "PUT",
        "/v1/teams/team-openai/inference",
        {"provider": "anthropic", "model": "claude-sonnet-5"},
    ) in calls
    assert not any(call[1].endswith("/create") for call in calls)


def test_team_models_must_match_the_closed_provider_catalog_before_forwarding():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        create = client.post(
            "/api/teams",
            json={"team_name": "Unknown", "provider": "openai", "model": "gpt-unknown"},
        )
        switch = client.put(
            "/api/teams/team-openai/inference",
            json={"provider": "anthropic", "model": "gpt-5.5"},
        )

    assert create.status_code == switch.status_code == 400
    assert (
        create.json() == switch.json() == {"detail": "unsupported model for provider"}
    )
    assert not any(
        path.endswith("/create") or (method == "PUT" and path.endswith("/inference"))
        for method, path, _body in calls
    )


def test_team_ids_bind_the_complete_account_and_normalized_name():
    first = main._team_id_for(
        "account-prefix-one", "A very long shared team name alpha"
    )
    same = main._team_id_for("account-prefix-one", "A very long shared team name alpha")
    other_account = main._team_id_for(
        "account-prefix-two", "A very long shared team name alpha"
    )
    other_tail = main._team_id_for(
        "account-prefix-one", "A very long shared team name omega"
    )

    assert first == same
    assert first != other_account
    assert first != other_tail
    assert len(first) <= 40
    assert re.fullmatch(r"[a-z0-9_]+", first)
    assert main._team_id_for("account-prefix-one", "!!!") == ""


def test_team_create_and_install_reject_bodies_before_control_plane_forwarding():
    create_body = json.dumps(
        {
            "team_name": "Astra",
            "padding": "x" * main.MAX_TEAM_CREATE_BODY_BYTES,
        }
    ).encode()
    install_body = json.dumps(
        {
            "app": "notification-center",
            "padding": "x" * main.MAX_TEAM_INSTALL_BODY_BYTES,
        }
    ).encode()
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        create = client.post(
            "/api/teams",
            content=create_body,
            headers={"Content-Type": "application/json"},
        )
        install = client.post(
            "/api/teams/team_openai/install",
            content=install_body,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://shimpz.com",
            },
        )
    assert create.status_code == 413
    assert install.status_code == 413
    forwarded_mutations = [
        path
        for method, path, _body in calls
        if method == "POST" and path.endswith(("/create", "/apps"))
    ]
    assert forwarded_mutations == []


def test_provider_key_delete_fails_closed_without_the_finalizer_bearer():
    with (
        _brain_control_plane(finalize_token_available=False) as calls,
        TestClient(app) as client,
    ):
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.delete("/api/brains/openai")
    assert response.status_code == 502
    assert response.json() == {"detail": "Brain credential finalization is unavailable"}
    assert not any(call[1] == "/v1/internal/brains/revoke-finalize" for call in calls)

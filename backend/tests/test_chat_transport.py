import asyncio
import json
import threading
from urllib.parse import urlparse

import pytest
from fastapi import Request, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import authn, config
from app.chat import events as chat_events
from app.chat import relay as chat_relay
from app.chat import ws as main
from app.chat.events import WebSocketPayloadError
from app.chat.events import parsed_stream_event as _parsed_stream_event
from app.chat.events import upstream_error_event as _upstream_error_event
from app.chat.events import validated_terminal_event as _validated_terminal_event
from app.chat.events import ws_receive_bounded_json as _ws_receive_bounded_json
from app.chat.relay import _stream_queue_put
from app.chat.ws import _ws_dispatch
from app.config import CHAT_WS_SUBPROTOCOL, WS_ALLOWED_ORIGINS
from app.config import canonical_origin as _canonical_origin
from app.main import app
from app.payloads import ClientPayloadError, read_bounded_json

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


def _input_challenge(*, team_id: str = TEST_TEAM_ID, challenge_id: str = "a" * 32) -> dict:
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


def _approval_challenge(*, team_id: str = TEST_TEAM_ID, challenge_id: str = "b" * 32) -> dict:
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
            await read_bounded_json(_request(b"{}", [(b"content-length", b"9")]), 8)
        assert declared.value.status == 413

        with pytest.raises(ClientPayloadError) as streamed:
            await read_bounded_json(_request(b'{"x":123}'), 8)
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
    assert main._chat_turn_payload({"message": "brain only", "files": [], "assistant_ids": []}) == {
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
        websocket, _ = _websocket("x" * (config.MAX_WS_FRAME_BYTES + 1))
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

    monkeypatch.setattr(chat_relay, "_call", completed_call)

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
        events = [json.loads(message["text"]) for message in sent if message["type"] == "websocket.send"]
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
            config.TEAMDRIVER_URL,
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
            events = [json.loads(message["text"]) for message in sent if message["type"] == "websocket.send"]
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
    admission = main._WsConnectionAdmission(global_limit=3, account_limit=2, team_limit=1)
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
    oversized = json.dumps({"padding": "x" * (config.MAX_AUTH_BODY_BYTES + 1)})
    with TestClient(app) as client:
        responses = [
            client.post(path, content=oversized, headers={"Content-Type": "application/json"})
            for path in ("/api/signup", "/api/login")
        ]
    assert [response.status_code for response in responses] == [413, 413]


def test_signup_forwards_only_the_persisted_credentials(monkeypatch):
    forwarded = []

    async def bounded_call(*args, extra=None):
        forwarded.append((*args, extra))
        return 400, {"error": "rejected"}

    monkeypatch.setattr("app.routers.account._bounded_call", bounded_call)
    with TestClient(app) as client:
        response = client.post(
            "/api/signup",
            json={"username": "captain", "password": "correct horse battery staple", "github": "ignored"},
        )

    assert response.status_code == 400
    assert response.headers["cache-control"] == "private, no-store"
    assert len(forwarded) == 1
    base, method, path, payload, extra = forwarded[0]
    assert (base, method, path) == (authn.ACCOUNTS_URL, "POST", "/v1/signup")
    assert payload == {"username": "captain", "password": "correct horse battery staple"}
    assert set(extra) == {"X-Forwarded-For"}


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


def test_upstream_http_errors_and_unterminated_terminal_lines_are_redacted():
    leak_marker = "upstream-private-marker-7e9b"
    http_error = _upstream_error_event(409)
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


def test_public_chat_errors_delegate_status_clamping_to_the_shared_contract(monkeypatch):
    clamped: list[object] = []
    monkeypatch.setattr(
        chat_events.chat_ws_common,
        "safe_status",
        lambda value: clamped.append(value) or 504,
    )

    assert chat_events.public_chat_error_event(True) == {
        "type": "error",
        "status": 504,
        "detail": "chat service timed out",
    }
    assert clamped == [True]


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
def test_terminal_event_contract_accepts_only_exact_bounded_schemas(event: dict, expected: dict):
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
        _done("x" * (config.MAX_CHAT_REPLY_CHARS + 1)),
        {"type": "error", "status": True, "detail": "failed"},
        {"type": "error", "status": 200, "detail": "not an error"},
        {"type": "error", "status": 502, "detail": "x" * (config.MAX_CHAT_ERROR_DETAIL_CHARS + 1)},
        {"type": "stopped", "requested": True},
    ],
)
def test_terminal_event_contract_rejects_legacy_extra_and_unbounded_values(event: dict):
    assert _validated_terminal_event(event, TEST_TEAM_ID) is None


def test_terminal_event_parser_rejects_duplicate_fields():
    assert _parsed_stream_event(b'{"type":"stopped","type":"done"}', TEST_TEAM_ID) is None

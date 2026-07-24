"""Authenticated shimpz.chat.v3 WebSocket admission, dispatch, and delivery."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import config
from app.authn import EXECUTOR as _AUTH_EXECUTOR
from app.chat.events import CHALLENGE_ID_RE as _CHALLENGE_ID_RE
from app.chat.events import WebSocketPayloadError
from app.chat.events import chat_turn_payload as _chat_turn_payload
from app.chat.events import upstream_error_event as _upstream_error_event
from app.chat.events import validated_terminal_event as _validated_terminal_event
from app.chat.events import ws_receive_bounded_json as _ws_receive_bounded_json
from app.chat.relay import _ChallengeRelay, _relay_challenge, _stream_lines, _StreamRelay
from app.concurrency import BoundedThreadPoolExecutor as _BoundedThreadPoolExecutor
from app.concurrency import ExecutorSaturatedError as _ExecutorSaturatedError
from app.concurrency import TurnAdmission as _TurnAdmission
from app.concurrency import TurnLease as _TurnLease
from app.concurrency import WsConnectionAdmission as _WsConnectionAdmission
from app.config import (
    ACCOUNT_COOKIE,
    CHAT_WS_SUBPROTOCOL,
    STOP_QUEUE_MAX,
    STOP_WORKER_THREADS,
    STREAM_QUEUE_MAX_EVENTS,
    STREAM_TURN_QUEUE_MAX,
    STREAM_WORKER_THREADS,
    TERMINAL_CONTRACT_ERROR,
    WS_ACCOUNT_CONNECTION_LIMIT,
    WS_ALLOWED_ORIGINS,
    WS_GLOBAL_CONNECTION_LIMIT,
    WS_TEAM_CONNECTION_LIMIT,
)
from app.payloads import ClientPayloadError
from app.upstream import call as _call
from app.upstream import call_bounded as _bounded_call

log = structlog.get_logger()

_STREAM_EXECUTOR = _BoundedThreadPoolExecutor(
    max_workers=STREAM_WORKER_THREADS,
    max_outstanding=STREAM_WORKER_THREADS,
    thread_name_prefix="shimpz-stream",
)
_TURN_ADMISSION = _TurnAdmission(STREAM_WORKER_THREADS, STREAM_TURN_QUEUE_MAX)
_STOP_EXECUTOR = _BoundedThreadPoolExecutor(
    max_workers=STOP_WORKER_THREADS,
    max_outstanding=STOP_WORKER_THREADS + STOP_QUEUE_MAX,
    thread_name_prefix="shimpz-stop",
)
_WS_CONNECTION_ADMISSION = _WsConnectionAdmission(
    WS_GLOBAL_CONNECTION_LIMIT,
    WS_ACCOUNT_CONNECTION_LIMIT,
    WS_TEAM_CONNECTION_LIMIT,
)


async def _ws_verify(ws: WebSocket) -> tuple[str, str]:
    token = ws.cookies.get(ACCOUNT_COOKIE, "")
    if not token:
        return "", ""
    status, data = await _bounded_call(
        _AUTH_EXECUTOR,
        config.ACCOUNTS_URL,
        "POST",
        "/v1/verify",
        {"token": token},
    )
    account_id = data.get("account_id") if status == 200 else None
    return (token, str(account_id)) if account_id else ("", "")


@dataclass
class _RelayDelivery:
    terminal_seen: bool = False
    aborted: bool = False
    stop_attempted: bool = False


async def _stop_delivery_once(
    team_id: str,
    hdr: dict,
    delivery: _RelayDelivery,
) -> tuple[int, dict] | None:
    """Request provider cancellation at most once for one admitted relay."""
    if delivery.stop_attempted:
        return None
    delivery.stop_attempted = True
    return await _driver_stop(team_id, hdr)


async def _send_relay_event(
    turn: _WsTurn,
    event: dict,
    delivery: _RelayDelivery,
) -> None:
    projected = dict(event)
    relay_abort = bool(projected.pop("_relay_abort", False))
    terminal = _validated_terminal_event(projected, turn.team_id)
    if terminal is None:
        terminal = {"type": "error", "status": 502, "detail": TERMINAL_CONTRACT_ERROR}
        relay_abort = True
    if relay_abort:
        if not delivery.aborted:
            await _stop_delivery_once(turn.team_id, turn.headers, delivery)
        delivery.aborted = True
    if turn.state is not None and terminal["type"] in {
        "input-required",
        "approval-required",
    }:
        turn.state["pending_challenge_id"] = terminal["challenge_id"]
        turn.state["pending_challenge_type"] = terminal["type"].removesuffix("-required")
    elif turn.state is not None and terminal["type"] in {"done", "stopped"}:
        turn.state["pending_challenge_id"] = None
        turn.state["pending_challenge_type"] = None
    delivery.terminal_seen = True
    await turn.ws.send_json(terminal)


async def _driver_stop(team_id: str, hdr: dict) -> tuple[int, dict]:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            _STOP_EXECUTOR,
            _call,
            config.TEAMDRIVER_URL,
            "POST",
            f"/v1/teams/{team_id}/chat/stop",
            None,
            hdr,
        )
    except _ExecutorSaturatedError:
        return 429, {"detail": "chat stop capacity reached"}


@dataclass(frozen=True)
class _WsTurn:
    ws: WebSocket
    team_id: str
    headers: dict
    text: str
    started: asyncio.Event
    dispatched: asyncio.Event
    files: tuple[str, ...] = ()
    assistant_ids: tuple[str, ...] = ()
    delivery: _RelayDelivery = field(default_factory=_RelayDelivery)
    state: dict | None = None


@dataclass(frozen=True)
class _WsContext:
    ws: WebSocket
    team_id: str
    headers: dict
    state: dict


def _relay_capacity_event() -> dict:
    return {
        "type": "error",
        "status": 429,
        "detail": "chat relay capacity reached",
    }


async def _deliver_turn(turn: _WsTurn, queue: asyncio.Queue, worker: asyncio.Future) -> None:
    delivery = turn.delivery
    try:
        while True:
            pending = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait({pending, worker}, return_when=asyncio.FIRST_COMPLETED)
            if pending not in done:
                pending.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pending
                while not queue.empty():
                    evt = queue.get_nowait()
                    if evt is not None:
                        await _send_relay_event(turn, evt, delivery)
                break
            evt = pending.result()
            if evt is None:
                break
            await _send_relay_event(turn, evt, delivery)
        if not delivery.terminal_seen:
            await _stop_delivery_once(turn.team_id, turn.headers, delivery)
            await turn.ws.send_json(
                {
                    "type": "error",
                    "status": 502,
                    "detail": "team-driver relay ended before a terminal event",
                }
            )
    except WebSocketDisconnect, OSError, RuntimeError, asyncio.CancelledError:
        await _stop_delivery_once(turn.team_id, turn.headers, delivery)
        raise
    finally:
        if not delivery.terminal_seen and not worker.done():
            await _stop_delivery_once(turn.team_id, turn.headers, delivery)
        with contextlib.suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(asyncio.shield(worker), timeout=15)


async def _ws_run_admitted_turn(turn: _WsTurn, lease: _TurnLease) -> None:
    async with lease:
        queue: asyncio.Queue = asyncio.Queue(maxsize=STREAM_QUEUE_MAX_EVENTS)
        loop = asyncio.get_running_loop()
        try:
            worker = loop.run_in_executor(
                _STREAM_EXECUTOR,
                _stream_lines,
                _StreamRelay(
                    turn.team_id,
                    turn.text,
                    turn.headers,
                    queue,
                    loop,
                    turn.started,
                    turn.files,
                    turn.assistant_ids,
                ),
            )
            turn.dispatched.set()
        except _ExecutorSaturatedError:
            turn.started.set()
            await turn.ws.send_json(_relay_capacity_event())
            return
        await _deliver_turn(turn, queue, worker)


async def _ws_run_admitted_challenge(
    turn: _WsTurn,
    lease: _TurnLease,
    kind: str,
    body: dict,
) -> None:
    async with lease:
        queue: asyncio.Queue = asyncio.Queue(maxsize=STREAM_QUEUE_MAX_EVENTS)
        loop = asyncio.get_running_loop()
        try:
            worker = loop.run_in_executor(
                _STREAM_EXECUTOR,
                _relay_challenge,
                _ChallengeRelay(
                    turn.team_id,
                    kind,
                    body,
                    turn.headers,
                    queue,
                    loop,
                    turn.started,
                ),
            )
            turn.dispatched.set()
        except _ExecutorSaturatedError:
            turn.started.set()
            await turn.ws.send_json(_relay_capacity_event())
            return
        await _deliver_turn(turn, queue, worker)


async def _ws_run_turn(
    ws: WebSocket,
    team_id: str,
    hdr: dict,
    payload: dict[str, object],
    started: asyncio.Event,
) -> None:
    """Relay one terminal controller event for a live turn."""
    admitted = _TURN_ADMISSION.reserve()
    if admitted is None:
        started.set()
        await ws.send_json(_relay_capacity_event())
        return
    dispatched = asyncio.Event()
    await _ws_run_admitted_turn(
        _WsTurn(
            ws=ws,
            team_id=team_id,
            headers=hdr,
            text=payload["message"],
            started=started,
            dispatched=dispatched,
            files=tuple(payload["files"]),
            assistant_ids=tuple(payload["assistant_ids"]),
        ),
        admitted,
    )


def _start_ws_turn(
    context: _WsContext,
    msg: dict,
    lease: _TurnLease,
) -> tuple[asyncio.Task, asyncio.Event, asyncio.Event, _RelayDelivery]:
    started = asyncio.Event()
    dispatched = asyncio.Event()
    delivery = _RelayDelivery()
    turn = asyncio.create_task(
        _ws_run_admitted_turn(
            _WsTurn(
                ws=context.ws,
                team_id=context.team_id,
                headers=context.headers,
                text=msg["message"],
                started=started,
                dispatched=dispatched,
                files=tuple(msg["files"]),
                assistant_ids=tuple(msg["assistant_ids"]),
                delivery=delivery,
                state=context.state,
            ),
            lease,
        )
    )
    return turn, started, dispatched, delivery


def _start_ws_challenge(
    context: _WsContext,
    kind: str,
    body: dict,
    lease: _TurnLease,
) -> tuple[asyncio.Task, asyncio.Event, asyncio.Event, _RelayDelivery]:
    started = asyncio.Event()
    dispatched = asyncio.Event()
    delivery = _RelayDelivery()
    turn = asyncio.create_task(
        _ws_run_admitted_challenge(
            _WsTurn(
                ws=context.ws,
                team_id=context.team_id,
                headers=context.headers,
                text="",
                started=started,
                dispatched=dispatched,
                delivery=delivery,
                state=context.state,
            ),
            lease,
            kind,
            body,
        )
    )
    return turn, started, dispatched, delivery


async def _ws_stop_turn(ws: WebSocket, team_id: str, hdr: dict, state: dict) -> None:
    if state.get("stop_requested", False):
        return
    turns = state["turns"]
    active = next((turn for turn in turns if not turn.done()), None)
    if active is None:
        if state.get("pending_challenge_id") is not None:
            state["stop_requested"] = True
            status, data = await _driver_stop(team_id, hdr)
            if status == 200 and data.get("requested"):
                state["pending_challenge_id"] = None
                state["pending_challenge_type"] = None
                await ws.send_json({"type": "stopped"})
            else:
                await ws.send_json(_upstream_error_event(status if status != 200 else 409))
            return
        await ws.send_json({"type": "error", "status": 409, "detail": "no active chat turn"})
        return
    state["stop_requested"] = True
    lease = state["leases"][active]
    delivery = state["deliveries"][active]
    dispatched = state["dispatches"][active]
    started = state["starts"][active]
    queued = lease.cancel_if_queued()
    if queued or not dispatched.is_set():
        active.cancel()
        await asyncio.gather(active, return_exceptions=True)
        await ws.send_json({"type": "stopped"})
        return
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(started.wait(), timeout=10)
    result = await _stop_delivery_once(team_id, hdr, delivery)
    if result is None:
        return
    status, data = result
    if status != 200 or not data.get("requested"):
        error_status = status if status != 200 else 409
        await ws.send_json(_upstream_error_event(error_status))


def _track_ws_turn(
    state: dict,
    tracked: tuple[asyncio.Task, asyncio.Event, asyncio.Event, _RelayDelivery],
    lease: _TurnLease,
) -> None:
    turn, started, dispatched, delivery = tracked
    turns = state["turns"]
    starts = state.setdefault("starts", {})
    dispatches = state.setdefault("dispatches", {})
    leases = state.setdefault("leases", {})
    deliveries = state.setdefault("deliveries", {})
    state["stop_requested"] = False
    turns.add(turn)
    starts[turn] = started
    dispatches[turn] = dispatched
    leases[turn] = lease
    deliveries[turn] = delivery

    def turn_done(completed: asyncio.Task) -> None:
        lease.release()
        turns.discard(completed)
        starts.pop(completed, None)
        dispatches.pop(completed, None)
        leases.pop(completed, None)
        deliveries.pop(completed, None)

    turn.add_done_callback(turn_done)


async def _ws_dispatch_challenge(
    ws: WebSocket,
    team_id: str,
    hdr: dict,
    msg: dict,
    state: dict,
) -> None:
    kind = "input" if msg.get("type") == "input-submit" else "approval"
    expected_fields = {"type", "challenge_id", "answer"} if kind == "input" else {"type", "challenge_id", "approved"}
    challenge_id = msg.get("challenge_id")
    valid_answer = kind == "input" or msg.get("approved") is True
    if (
        set(msg) != expected_fields
        or not isinstance(challenge_id, str)
        or _CHALLENGE_ID_RE.fullmatch(challenge_id) is None
        or not valid_answer
    ):
        await ws.send_json({"type": "error", "status": 400, "detail": f"invalid {kind} submission"})
        return
    state["turns"].difference_update({turn for turn in state["turns"] if turn.done()})
    if state["turns"]:
        await ws.send_json(
            {
                "type": "error",
                "status": 409,
                "detail": "a chat operation is already active",
            }
        )
        return
    if state.get("pending_challenge_type") != kind or state.get("pending_challenge_id") != challenge_id:
        await ws.send_json(
            {
                "type": "error",
                "status": 409,
                "detail": f"no matching {kind} challenge is pending",
            }
        )
        return
    lease = _TURN_ADMISSION.reserve()
    if lease is None:
        await ws.send_json(_relay_capacity_event())
        return
    body = {key: value for key, value in msg.items() if key != "type"}
    try:
        tracked = _start_ws_challenge(_WsContext(ws, team_id, hdr, state), kind, body, lease)
    except BaseException:
        lease.release()
        raise
    _track_ws_turn(state, tracked, lease)


async def _ws_dispatch(ws: WebSocket, team_id: str, hdr: dict, msg: dict, state: dict) -> None:
    turns = state["turns"]
    if msg.get("type") == "chat":
        try:
            if set(msg) != {"type", "message", "files", "assistant_ids"}:
                raise ClientPayloadError(
                    400,
                    "chat frame must contain only type, message, files, and assistant_ids",
                )
            turn_payload = _chat_turn_payload({key: value for key, value in msg.items() if key != "type"})
        except ClientPayloadError as exc:
            await ws.send_json({"type": "error", "status": exc.status, "detail": exc.detail})
            return
        msg = {"type": "chat", **turn_payload}
        turns.difference_update({turn for turn in turns if turn.done()})
        if turns:
            await ws.send_json(
                {
                    "type": "error",
                    "status": 409,
                    "detail": "team already has an active chat turn",
                }
            )
            return
        lease = _TURN_ADMISSION.reserve()
        if lease is None:
            await ws.send_json(
                {
                    "type": "error",
                    "status": 429,
                    "detail": "chat relay capacity reached",
                }
            )
            return
        # The background task keeps the socket responsive to Stop. The set is capped at one;
        # the controller independently enforces the same invariant across sockets.
        try:
            tracked = _start_ws_turn(_WsContext(ws, team_id, hdr, state), msg, lease)
        except BaseException:
            lease.release()
            raise
        _track_ws_turn(state, tracked, lease)
    elif msg.get("type") in {"input-submit", "approval-submit"}:
        await _ws_dispatch_challenge(ws, team_id, hdr, msg, state)
    elif msg.get("type") == "stop" and set(msg) == {"type"}:
        await _ws_stop_turn(ws, team_id, hdr, state)
    else:
        await ws.send_json({"type": "error", "status": 400, "detail": "unsupported chat frame"})


async def _ws_validate_opening(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if not config.origin_allowed(origin, WS_ALLOWED_ORIGINS):
        log.warning("ws_origin_denied", origin=origin or "<missing>")
        await ws.close(code=4403)
        return False
    if tuple(ws.scope.get("subprotocols", ())) != (CHAT_WS_SUBPROTOCOL,):
        log.warning("ws_subprotocol_denied")
        await ws.close(code=4406)
        return False
    return True


router = APIRouter()


@router.websocket("/api/teams/{team_id}/chat/ws")
async def team_chat_ws(ws: WebSocket, team_id: str) -> None:
    if not await _ws_validate_opening(ws):
        return
    try:
        token, account_id = await _ws_verify(ws)
    except _ExecutorSaturatedError:
        await ws.close(code=4429)
        return
    if not token:
        await ws.close(code=4401)
        return
    connection = _WS_CONNECTION_ADMISSION.reserve(account_id, team_id)
    if connection is None:
        await ws.send(
            {
                "type": "websocket.http.response.start",
                "status": 429,
                "headers": [
                    (b"retry-after", b"1"),
                    (b"x-shimpz-rejection", b"websocket-capacity"),
                ],
            }
        )
        await ws.send(
            {
                "type": "websocket.http.response.body",
                "body": b"",
                "more_body": False,
            }
        )
        return
    try:
        await ws.accept(subprotocol=CHAT_WS_SUBPROTOCOL)
        hdr = {"X-Shimpz-Account": token}
        state: dict = {
            "turns": set(),
            "starts": {},
            "dispatches": {},
            "leases": {},
            "deliveries": {},
            "stop_requested": False,
            "pending_challenge_id": None,
            "pending_challenge_type": None,
        }
        try:
            while True:
                try:
                    message = await _ws_receive_bounded_json(ws)
                except WebSocketPayloadError as exc:
                    await ws.send_json(
                        {
                            "type": "error",
                            "status": exc.status,
                            "detail": exc.detail,
                        }
                    )
                    await ws.close(code=exc.close_code)
                    return
                await _ws_dispatch(ws, team_id, hdr, message, state)
        except WebSocketDisconnect:
            return
        finally:
            turns = list(state["turns"])
            for turn in turns:
                turn.cancel()
            await asyncio.gather(*turns, return_exceptions=True)
    finally:
        connection.release()

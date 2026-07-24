import asyncio
import concurrent.futures
import contextlib
import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app import config
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
    previous = config.TEAMDRIVER_URL
    config.TEAMDRIVER_URL = f"http://127.0.0.1:{server.server_port}"
    try:
        yield calls
    finally:
        config.TEAMDRIVER_URL = previous
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
        events = [json.loads(message["text"]) for message in sent if message["type"] == "websocket.send"]
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

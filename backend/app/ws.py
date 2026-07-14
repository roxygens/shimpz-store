"""WebSocket gateway — this project's realtime push worker (its OWN supervised process).

The standard for backend→frontend data flow is the WebSocket, not HTTP polling: anything that
publishes to this project's bus topic (app/events.py notify()) is fanned out live to every browser
connected at /ws. Deploy it SEPARATELY from the API, on its own port:

    shimpz-app deploy shimpz-store-ws <ws-port> -- uv run uvicorn app.ws:app --host 0.0.0.0 --port <ws-port>

and publish it with the fullstack form `shimpz-publish <fqdn> <web> public <api> <ws-port>` — the
frontend connects to the RELATIVE /ws (src/lib/ws.ts), same code in dev (vite proxy) and live (Caddy).
"""

import asyncio
import contextlib
from contextlib import asynccontextmanager

import shimpzbus
import structlog
from aiokafka.errors import KafkaError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.logconf import setup

setup("shimpz-store-ws")
log = structlog.get_logger()

TOPIC = "shimpz_store.events"
clients: set[WebSocket] = set()


async def _fanout(event: dict) -> None:
    dead = []
    for ws in list(clients):  # snapshot: connects/disconnects mutate the set between awaits
        try:
            await ws.send_json(event)
        except WebSocketDisconnect, RuntimeError, ConnectionError, OSError:
            dead.append(ws)  # a dying socket must never stop the fan-out to the others
    for ws in dead:
        clients.discard(ws)
    if dead:
        log.info("ws_clients_dropped", count=len(dead))


async def _pump() -> None:
    # One live bus tail per gateway process. Broker errors PROPAGATE out of shimpzbus.stream (fail-fast);
    # this loop logs them LOUDLY and reconnects with a delay — a gateway silently serving no data
    # would be the invisible degrade the house rules forbid.
    while True:
        try:
            async for event in shimpzbus.stream(TOPIC):
                await _fanout(event)
        except asyncio.CancelledError:
            raise  # shutdown — never swallow cancellation
        except KafkaError, OSError, RuntimeError, ValueError:
            log.exception("ws_pump_error", topic=TOPIC)
            await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # No self-registration here: this process runs in its OWN container where the service registry
    # is mounted READ-ONLY — registration is the DEPLOY's job (shimpz-app runs app/register.py on the
    # brain after the health gate passes).
    task = asyncio.create_task(_pump())
    log.info("ws_gateway_up", topic=TOPIC)
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="shimpz-store-ws", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    # the deploy smoke gate needs an HTTP answer; client count makes `curl /health` a live gauge
    return {"status": "ok", "clients": len(clients)}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    clients.add(ws)
    log.info("ws_connected", clients=len(clients))
    try:
        while True:
            await ws.receive_text()  # inbound frames are keepalives; server→client is the data path
    except WebSocketDisconnect:
        log.info("ws_disconnected", clients=len(clients) - 1)
    finally:
        clients.discard(ws)

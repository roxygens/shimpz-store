"""Publish realtime events to this project's bus topic — the frontend receives them over /ws.

Call notify() after a meaningful state change (a row created, a job finished, progress). The ws
gateway (app/ws.py) tails the topic and pushes every event to connected browsers (src/lib/ws.ts).
publish() is delivery-confirmed and RAISES if the broker doesn't ack — surface that (503), never
swallow it.
"""

import shimpzbus
import structlog

TOPIC = "shimpz_store.events"
log = structlog.get_logger()


def notify(kind: str, **data) -> None:
    shimpzbus.publish(TOPIC, {"kind": kind, **data})
    log.debug("event_published", kind=kind)

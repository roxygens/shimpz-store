"""Closed browser-visible chat event validation."""

from __future__ import annotations

import re

from fastapi import WebSocket, WebSocketDisconnect

from app import chat_ws_common, team_driver_contract
from app.config import (
    MAX_CHAT_ASSISTANTS,
    MAX_CHAT_ERROR_DETAIL_CHARS,
    MAX_CHAT_FILES,
    MAX_CHAT_MESSAGE_CHARS,
    MAX_CHAT_REPLY_CHARS,
    MAX_WS_FRAME_BYTES,
)
from app.payloads import ClientPayloadError

CHALLENGE_ID_RE = chat_ws_common.CHALLENGE_ID_RE
HUMAN_REQUEST_TYPES = frozenset({"str", "int", "float", "bool", "choice", "choices"})


def canonical_chat_reply(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_CHAT_REPLY_CHARS
        or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value) is not None
    ):
        return None
    return value


def chat_turn_payload(payload: dict) -> dict[str, object]:
    """Project one browser turn onto the controller's closed Team chat contract."""
    if set(payload) != {"message", "files", "assistant_ids"}:
        raise ClientPayloadError(400, "body must contain only message, files, and assistant_ids")
    message = payload["message"]
    if not isinstance(message, str):
        raise ClientPayloadError(400, "message must be a string")
    message = message.strip()
    if not message:
        raise ClientPayloadError(400, "message must be non-empty")
    if len(message) > MAX_CHAT_MESSAGE_CHARS:
        raise ClientPayloadError(400, f"message too long (> {MAX_CHAT_MESSAGE_CHARS} chars)")
    files = payload["files"]
    if not isinstance(files, list) or len(files) > MAX_CHAT_FILES:
        raise ClientPayloadError(400, f"files must contain at most {MAX_CHAT_FILES} opaque ids")
    opaque_ids = [team_driver_contract.canonical_file_id(file_id) for file_id in files]
    if any(file_id is None for file_id in opaque_ids) or len(opaque_ids) != len(set(opaque_ids)):
        raise ClientPayloadError(400, "files must contain unique opaque ids")
    assistant_ids = payload["assistant_ids"]
    if not isinstance(assistant_ids, list) or len(assistant_ids) > MAX_CHAT_ASSISTANTS:
        raise ClientPayloadError(
            400,
            f"assistant_ids must contain at most {MAX_CHAT_ASSISTANTS} Assistant ids",
        )
    canonical_ids = [team_driver_contract.canonical_assistant_id(value) for value in assistant_ids]
    if any(value is None for value in canonical_ids) or len(canonical_ids) != len(set(canonical_ids)):
        raise ClientPayloadError(400, "assistant_ids must contain unique canonical Assistant ids")
    return {"message": message, "files": opaque_ids, "assistant_ids": canonical_ids}


WebSocketPayloadError = chat_ws_common.FrameError


async def ws_receive_bounded_json(ws: WebSocket) -> dict:
    message = await ws.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    return chat_ws_common.decode_bounded_json_frame(
        message,
        MAX_WS_FRAME_BYTES,
        invalid_json_detail="WebSocket frame must be valid JSON",
    )


def _validated_done_event(value: dict, expected_team_id: str) -> dict | None:
    if set(value) != {"type", "team_id", "team_name", "reply"}:
        return None
    team_id = team_driver_contract.canonical_team_id(value["team_id"])
    reply = canonical_chat_reply(value["reply"])
    team_name = team_driver_contract.canonical_team_name(value["team_name"])
    if team_id is None or team_id != expected_team_id or reply is None or team_name is None:
        return None
    return {
        "type": "done",
        "team_id": team_id,
        "team_name": team_name,
        "reply": reply,
    }


def public_chat_error_event(status: int) -> dict:
    safe_status = chat_ws_common.safe_status(status)
    if safe_status == 429:
        detail = "chat service is busy; try again shortly"
    elif safe_status == 504:
        detail = "chat service timed out"
    elif safe_status < 500:
        detail = "chat request was rejected"
    else:
        detail = "chat service is temporarily unavailable"
    return {"type": "error", "status": safe_status, "detail": detail}


def _validated_error_event(value: dict) -> dict | None:
    if set(value) != {"type", "status", "detail"}:
        return None
    status = value["status"]
    detail = value["detail"]
    if (
        isinstance(status, bool)
        or not isinstance(status, int)
        or not 400 <= status <= 599
        or not isinstance(detail, str)
        or not detail
        or detail != detail.strip()
        or len(detail) > MAX_CHAT_ERROR_DETAIL_CHARS
        or re.search(r"[\x00-\x1f\x7f]", detail) is not None
    ):
        return None
    return public_chat_error_event(status)


def _bounded_public_text(value: object, maximum: int, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or re.search(r"[\x00-\x1f\x7f]", value) is not None
    ):
        return None
    return value


def _validated_input_challenge(value: dict, expected_team_id: str) -> dict | None:
    if set(value) != {
        "type",
        "status",
        "team_id",
        "turn_id",
        "challenge_id",
        "request",
    }:
        return None
    challenge_id = value["challenge_id"]
    request = value["request"]
    team_id = team_driver_contract.canonical_team_id(value["team_id"])
    if (
        value["type"] != "input-required"
        or value["status"] != "input-required"
        or team_id != expected_team_id
        or not chat_ws_common.valid_challenge_id(challenge_id)
        or value["turn_id"] != challenge_id
        or not isinstance(request, dict)
        or set(request) != {"type", "title", "summary", "docs", "options"}
    ):
        return None
    request_type = request["type"]
    title = _bounded_public_text(request["title"], 80)
    summary = _bounded_public_text(request["summary"], 240)
    docs = _bounded_public_text(request["docs"], 2048, optional=True)
    options = request["options"]
    if (
        not isinstance(request_type, str)
        or request_type not in HUMAN_REQUEST_TYPES
        or title is None
        or summary is None
        or (request["docs"] is not None and docs is None)
        or not isinstance(options, list)
        or len(options) > 64
        or any(_bounded_public_text(option, 200) is None for option in options)
        or len(options) != len(set(options))
        or (request_type in {"choice", "choices"}) != bool(options)
    ):
        return None
    return {
        "type": "input-required",
        "status": "input-required",
        "team_id": team_id,
        "turn_id": challenge_id,
        "challenge_id": challenge_id,
        "request": {
            "type": request_type,
            "title": title,
            "summary": summary,
            "docs": docs,
            "options": list(options),
        },
    }


def _validated_approval_challenge(value: dict, expected_team_id: str) -> dict | None:
    if set(value) != {
        "type",
        "status",
        "team_id",
        "turn_id",
        "challenge_id",
        "requirements",
    }:
        return None
    challenge_id = value["challenge_id"]
    requirements = value["requirements"]
    team_id = team_driver_contract.canonical_team_id(value["team_id"])
    if (
        value["type"] != "approval-required"
        or value["status"] != "approval-required"
        or team_id != expected_team_id
        or not chat_ws_common.valid_challenge_id(challenge_id)
        or value["turn_id"] != challenge_id
        or not isinstance(requirements, list)
        or len(requirements) != 1
        or not isinstance(requirements[0], dict)
    ):
        return None
    requirement = requirements[0]
    if set(requirement) != {
        "assistant_id",
        "assistant_name",
        "power_id",
        "title",
        "summary",
        "docs",
        "approval",
    }:
        return None
    assistant_id = team_driver_contract.canonical_assistant_id(requirement["assistant_id"])
    power_id = team_driver_contract.canonical_assistant_id(requirement["power_id"])
    assistant_name = _bounded_public_text(requirement["assistant_name"], 80)
    title = _bounded_public_text(requirement["title"], 80)
    summary = _bounded_public_text(requirement["summary"], 240)
    docs = _bounded_public_text(requirement["docs"], 2048, optional=True)
    if (
        assistant_id is None
        or power_id is None
        or assistant_name is None
        or title is None
        or summary is None
        or (requirement["docs"] is not None and docs is None)
        or not isinstance(requirement["approval"], str)
        or requirement["approval"] not in {"always", "once"}
    ):
        return None
    return {
        "type": "approval-required",
        "status": "approval-required",
        "team_id": team_id,
        "turn_id": challenge_id,
        "challenge_id": challenge_id,
        "requirements": [
            {
                "assistant_id": assistant_id,
                "assistant_name": assistant_name,
                "power_id": power_id,
                "title": title,
                "summary": summary,
                "docs": docs,
                "approval": requirement["approval"],
            }
        ],
    }


def validated_terminal_event(value: object, expected_team_id: str) -> dict | None:
    """Project an untrusted controller value onto the only browser-visible chat events."""
    if not isinstance(value, dict):
        return None
    event_type = value.get("type")
    terminal = None
    if event_type == "done":
        terminal = _validated_done_event(value, expected_team_id)
    elif event_type == "error":
        terminal = _validated_error_event(value)
    elif event_type == "input-required":
        terminal = _validated_input_challenge(value, expected_team_id)
    elif event_type == "approval-required":
        terminal = _validated_approval_challenge(value, expected_team_id)
    elif event_type == "stopped" and set(value) == {"type"}:
        terminal = {"type": "stopped"}
    return terminal


def parsed_stream_event(line: bytes, expected_team_id: str) -> dict | None:
    if not line.strip():
        return None
    try:
        event = chat_ws_common.decode_bounded_json_frame(
            {"type": "websocket.receive", "text": line.decode()},
            len(line),
        )
    except chat_ws_common.FrameError, UnicodeDecodeError:
        return None
    return validated_terminal_event(event, expected_team_id)


def upstream_error_event(status: int) -> dict:
    return public_chat_error_event(status)

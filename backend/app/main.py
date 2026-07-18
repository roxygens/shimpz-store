"""Serve the Shimpz public console and account-authenticated control surface.

One FastAPI process serves the prerendered SvelteKit build and `/api`: signup/login, Capsule selection,
and installed-App management. It holds no driver/admin credential; it forwards the user's account token
to the socket-holding `capsule-driver`, which enforces ownership. Its one narrow service capability can
only finalize an exact already-revoking model credential generation. It is reached over the
Space's internal networks (accounts_net + capsuledriver_net) and uses stdlib http.client for proxy hops.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import contextlib
import functools
import hashlib
import http.client
import json as jsonlib
import os
import re
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import structlog
from fastapi import FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from app.logconf import setup
from app.middleware import TraceIdMiddleware

setup("shimpz-store")
log = structlog.get_logger()

BUILD = Path(os.environ.get("SHIMPZ_STORE_BUILD", "/app/build"))
ACCOUNTS_URL = os.environ.get("SHIMPZ_ACCOUNTS_URL", "http://accounts:7079")
CAPSULEDRIVER_URL = os.environ.get("SHIMPZ_CAPSULEDRIVER_URL", "http://capsule-driver:7077")
BRAIN_FINALIZE_TOKEN_FILE = Path(
    os.environ.get(
        "SHIMPZ_ACCOUNTS_BRAIN_FINALIZE_TOKEN_FILE",
        "/run/shimpz-accounts-brain-finalize/token",
    )
)
ACCOUNT_COOKIE = "shimpz_account"
COOKIE_MAX_AGE = 7 * 24 * 3600
MAX_CHAT_BODY_BYTES = max(1024, int(os.environ.get("SHIMPZ_STORE_MAX_CHAT_BODY_BYTES", str(128 * 1024))))
MAX_CAPSULE_CREATE_BODY_BYTES = max(
    1024,
    int(os.environ.get("SHIMPZ_STORE_MAX_CAPSULE_CREATE_BODY_BYTES", str(16 * 1024))),
)
MAX_INFERENCE_BODY_BYTES = max(
    1024,
    int(os.environ.get("SHIMPZ_STORE_MAX_INFERENCE_BODY_BYTES", str(4 * 1024))),
)
MAX_CAPSULE_INSTALL_BODY_BYTES = max(
    1024,
    int(os.environ.get("SHIMPZ_STORE_MAX_CAPSULE_INSTALL_BODY_BYTES", str(4 * 1024))),
)
MAX_AUTH_BODY_BYTES = max(1024, int(os.environ.get("SHIMPZ_STORE_MAX_AUTH_BODY_BYTES", str(16 * 1024))))
MAX_WS_FRAME_BYTES = max(1024, int(os.environ.get("SHIMPZ_STORE_MAX_WS_FRAME_BYTES", str(128 * 1024))))
STREAM_QUEUE_MAX_EVENTS = max(1, int(os.environ.get("SHIMPZ_STORE_STREAM_QUEUE_MAX_EVENTS", "32")))
STREAM_QUEUE_PUT_TIMEOUT = max(1.0, float(os.environ.get("SHIMPZ_STORE_STREAM_QUEUE_PUT_TIMEOUT", "10")))
STREAM_WORKER_THREADS = max(1, int(os.environ.get("SHIMPZ_STORE_STREAM_WORKER_THREADS", "32")))
STREAM_TURN_QUEUE_MAX = max(0, int(os.environ.get("SHIMPZ_STORE_STREAM_TURN_QUEUE_MAX", "32")))
CONTROL_WORKER_THREADS = max(1, int(os.environ.get("SHIMPZ_STORE_CONTROL_WORKER_THREADS", "8")))
CONTROL_QUEUE_MAX = max(0, int(os.environ.get("SHIMPZ_STORE_CONTROL_QUEUE_MAX", "8")))
AUTH_WORKER_THREADS = max(1, int(os.environ.get("SHIMPZ_STORE_AUTH_WORKER_THREADS", "8")))
AUTH_QUEUE_MAX = max(0, int(os.environ.get("SHIMPZ_STORE_AUTH_QUEUE_MAX", "8")))
STOP_WORKER_THREADS = max(1, int(os.environ.get("SHIMPZ_STORE_STOP_WORKER_THREADS", "4")))
STOP_QUEUE_MAX = max(0, int(os.environ.get("SHIMPZ_STORE_STOP_QUEUE_MAX", "4")))
WS_GLOBAL_CONNECTION_LIMIT = max(1, int(os.environ.get("SHIMPZ_STORE_WS_GLOBAL_CONNECTION_LIMIT", "64")))
WS_ACCOUNT_CONNECTION_LIMIT = max(1, int(os.environ.get("SHIMPZ_STORE_WS_ACCOUNT_CONNECTION_LIMIT", "4")))
WS_CAPSULE_CONNECTION_LIMIT = max(1, int(os.environ.get("SHIMPZ_STORE_WS_CAPSULE_CONNECTION_LIMIT", "2")))
MAX_UPSTREAM_ERROR_BYTES = 64 * 1024
MAX_UPSTREAM_STREAM_LINE_BYTES = 256 * 1024
MAX_UPSTREAM_STREAM_BYTES = 2 * 1024 * 1024
HTML_CACHE_CONTROL = "no-cache, max-age=0, must-revalidate"
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


class _ExecutorSaturatedError(RuntimeError):
    """A bounded executor rejected work instead of growing its private queue."""


class _BoundedThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    """ThreadPoolExecutor with a hard cap on running plus queued futures."""

    def __init__(self, *, max_workers: int, max_outstanding: int, thread_name_prefix: str) -> None:
        if max_outstanding < max_workers:
            raise ValueError("max_outstanding must cover every worker")
        self._permits = threading.BoundedSemaphore(max_outstanding)
        super().__init__(max_workers=max_workers, thread_name_prefix=thread_name_prefix)

    def submit(self, fn, /, *args, **kwargs):
        if not self._permits.acquire(blocking=False):
            raise _ExecutorSaturatedError("blocking worker admission is full")
        try:
            future = super().submit(fn, *args, **kwargs)
        except BaseException:
            self._permits.release()
            raise
        future.add_done_callback(lambda _completed: self._permits.release())
        return future


class _TurnAdmission:
    """Process-global FIFO turn semaphore with an exact finite waiter bound."""

    def __init__(self, active_limit: int, queue_limit: int) -> None:
        if active_limit < 1 or queue_limit < 0:
            raise ValueError("turn admission limits are invalid")
        self.active_limit = active_limit
        self.queue_limit = queue_limit
        self._guard = threading.Lock()
        self._active = 0
        self._waiting: deque[_TurnLease] = deque()

    def reserve(self) -> _TurnLease | None:
        loop = asyncio.get_running_loop()
        with self._guard:
            if self._active < self.active_limit:
                self._active += 1
                return _TurnLease(self, loop, active=True)
            if len(self._waiting) >= self.queue_limit:
                return None
            lease = _TurnLease(self, loop, active=False)
            self._waiting.append(lease)
            return lease

    def snapshot(self) -> tuple[int, int]:
        with self._guard:
            return self._active, len(self._waiting)

    def _release(self, lease: _TurnLease) -> None:
        promote = None
        with self._guard:
            if lease._state == "released":
                return
            if lease._state == "queued":
                lease._state = "released"
                with contextlib.suppress(ValueError):
                    self._waiting.remove(lease)
                return
            lease._state = "released"
            while self._waiting:
                candidate = self._waiting.popleft()
                if candidate._state == "queued":
                    candidate._state = "active"
                    promote = candidate
                    break
            if promote is None:
                self._active -= 1
        if promote is not None:
            try:
                promote._loop.call_soon_threadsafe(promote._grant)
            except RuntimeError:
                promote.release()


class _TurnLease:
    def __init__(
        self,
        admission: _TurnAdmission,
        loop: asyncio.AbstractEventLoop,
        *,
        active: bool,
    ) -> None:
        self._admission = admission
        self._loop = loop
        self._ready = loop.create_future()
        self._state = "active" if active else "queued"
        if active:
            self._ready.set_result(None)

    def _grant(self) -> None:
        if not self._ready.done():
            self._ready.set_result(None)

    async def __aenter__(self) -> _TurnLease:
        try:
            await self._ready
        except BaseException:
            self.release()
            raise
        return self

    async def __aexit__(self, *_exc) -> None:
        self.release()

    def release(self) -> None:
        self._admission._release(self)

    def cancel_if_queued(self) -> bool:
        """Atomically remove a waiting turn so it can never be promoted later."""
        with self._admission._guard:
            if self._state != "queued":
                return False
            self._state = "released"
            with contextlib.suppress(ValueError):
                self._admission._waiting.remove(self)
            return True


class _WsConnectionAdmission:
    """Hard process/account/Capsule bounds for sockets and their one ask poller."""

    def __init__(self, global_limit: int, account_limit: int, capsule_limit: int) -> None:
        if min(global_limit, account_limit, capsule_limit) < 1:
            raise ValueError("WebSocket connection limits must be positive")
        self.global_limit = global_limit
        self.account_limit = account_limit
        self.capsule_limit = capsule_limit
        self._guard = threading.Lock()
        self._global = 0
        self._accounts: dict[str, int] = {}
        self._capsules: dict[tuple[str, str], int] = {}

    def reserve(self, account_id: str, cid: str) -> _WsConnectionLease | None:
        capsule_key = (account_id, cid)
        with self._guard:
            if (
                self._global >= self.global_limit
                or self._accounts.get(account_id, 0) >= self.account_limit
                or self._capsules.get(capsule_key, 0) >= self.capsule_limit
            ):
                return None
            self._global += 1
            self._accounts[account_id] = self._accounts.get(account_id, 0) + 1
            self._capsules[capsule_key] = self._capsules.get(capsule_key, 0) + 1
        return _WsConnectionLease(self, account_id, capsule_key)

    def snapshot(self) -> tuple[int, dict[str, int], dict[tuple[str, str], int]]:
        with self._guard:
            return self._global, dict(self._accounts), dict(self._capsules)

    def _release(self, lease: _WsConnectionLease) -> None:
        with self._guard:
            if lease._released:
                return
            lease._released = True
            self._global -= 1
            account_count = self._accounts[lease._account_id] - 1
            capsule_count = self._capsules[lease._capsule_key] - 1
            if account_count:
                self._accounts[lease._account_id] = account_count
            else:
                del self._accounts[lease._account_id]
            if capsule_count:
                self._capsules[lease._capsule_key] = capsule_count
            else:
                del self._capsules[lease._capsule_key]


class _WsConnectionLease:
    def __init__(
        self,
        admission: _WsConnectionAdmission,
        account_id: str,
        capsule_key: tuple[str, str],
    ) -> None:
        self._admission = admission
        self._account_id = account_id
        self._capsule_key = capsule_key
        self._released = False

    def release(self) -> None:
        self._admission._release(self)


_STREAM_EXECUTOR = _BoundedThreadPoolExecutor(
    max_workers=STREAM_WORKER_THREADS,
    max_outstanding=STREAM_WORKER_THREADS,
    thread_name_prefix="shimpz-stream",
)
_TURN_ADMISSION = _TurnAdmission(STREAM_WORKER_THREADS, STREAM_TURN_QUEUE_MAX)
_CONTROL_EXECUTOR = _BoundedThreadPoolExecutor(
    max_workers=CONTROL_WORKER_THREADS,
    max_outstanding=CONTROL_WORKER_THREADS + CONTROL_QUEUE_MAX,
    thread_name_prefix="shimpz-control",
)
_AUTH_EXECUTOR = _BoundedThreadPoolExecutor(
    max_workers=AUTH_WORKER_THREADS,
    max_outstanding=AUTH_WORKER_THREADS + AUTH_QUEUE_MAX,
    thread_name_prefix="shimpz-auth",
)
_STOP_EXECUTOR = _BoundedThreadPoolExecutor(
    max_workers=STOP_WORKER_THREADS,
    max_outstanding=STOP_WORKER_THREADS + STOP_QUEUE_MAX,
    thread_name_prefix="shimpz-stop",
)
_WS_CONNECTION_ADMISSION = _WsConnectionAdmission(
    WS_GLOBAL_CONNECTION_LIMIT,
    WS_ACCOUNT_CONNECTION_LIMIT,
    WS_CAPSULE_CONNECTION_LIMIT,
)


def _canonical_origin(value: str | None) -> str | None:
    """Canonical exact WebSocket origin, preserving an explicitly supplied port."""
    if not value or value == "null":
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return None
    try:
        _ = parsed.port
    except ValueError:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


WS_ALLOWED_ORIGINS = frozenset(
    origin
    for raw in os.environ.get("SHIMPZ_WS_ALLOWED_ORIGINS", "https://shimpz.com").split(",")
    if (origin := _canonical_origin(raw.strip())) is not None
)
ASSISTANT_MUTATION_ALLOWED_ORIGINS = WS_ALLOWED_ORIGINS
CAPSULE_ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")
ASSISTANT_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
CAPSULE_FILE_ID_RE = re.compile(r"^[a-f0-9]{32}$")
CAPSULE_FILE_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
MODEL_CATALOG = {
    "openai": frozenset({"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5"}),
    "anthropic": frozenset({"claude-fable-5", "claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5-20251001"}),
}
RELEASED_CLOUD_ASSISTANTS = frozenset({"hello-pulse"})
PRIVATE_NO_STORE_HEADERS = {"Cache-Control": "private, no-store"}
MAX_CHAT_MESSAGE_CHARS = 16_000
MAX_CHAT_FILES = 8
MAX_CAPSULE_FILES = 256
MAX_CHAT_REPLY_CHARS = 60_000
MAX_CHAT_ERROR_DETAIL_CHARS = 800
TERMINAL_CONTRACT_ERROR = "capsule-driver stream violated the terminal event contract"


def _ws_origin_allowed(origin: str | None) -> bool:
    canonical = _canonical_origin(origin)
    return canonical is not None and canonical in WS_ALLOWED_ORIGINS


def _assistant_mutation_origin_allowed(origin: str | None) -> bool:
    canonical = _canonical_origin(origin)
    return canonical is not None and canonical in ASSISTANT_MUTATION_ALLOWED_ORIGINS


def _private_json(content: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content, status_code=status_code, headers=PRIVATE_NO_STORE_HEADERS)


def _canonical_capsule_id(value: object) -> str | None:
    return value if isinstance(value, str) and CAPSULE_ID_RE.fullmatch(value) is not None else None


def _canonical_assistant_id(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 80 or ASSISTANT_ID_RE.fullmatch(value) is None:
        return None
    return value


def _canonical_team_name(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 80
        or value.strip() != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return None
    return value


def _canonical_capsule_file_id(value: object) -> str | None:
    return value if isinstance(value, str) and CAPSULE_FILE_ID_RE.fullmatch(value) is not None else None


def _canonical_chat_reply(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_CHAT_REPLY_CHARS
        or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value) is not None
    ):
        return None
    return value


def _validated_chat_response(value: object, capsule_id: str) -> dict | None:
    """Expose only the controller-authenticated Team identity and natural reply."""
    if not isinstance(value, dict) or set(value) != {"capsule", "team", "reply"}:
        return None
    capsule = _canonical_capsule_id(value["capsule"])
    team = _canonical_team_name(value["team"])
    reply = _canonical_chat_reply(value["reply"])
    if capsule != capsule_id or team is None or reply is None:
        return None
    return {"capsule": capsule, "team": team, "reply": reply}


def _chat_turn_payload(payload: dict) -> dict[str, object]:
    """Project one browser turn onto the controller's closed Team chat contract."""
    if set(payload) not in ({"message"}, {"message", "files"}):
        raise ClientPayloadError(400, "body must contain message and optional files")
    message = payload["message"]
    if not isinstance(message, str):
        raise ClientPayloadError(400, "message must be a string")
    message = message.strip()
    if not message:
        raise ClientPayloadError(400, "message must be non-empty")
    if len(message) > MAX_CHAT_MESSAGE_CHARS:
        raise ClientPayloadError(400, f"message too long (> {MAX_CHAT_MESSAGE_CHARS} chars)")
    files = payload.get("files", [])
    if not isinstance(files, list) or len(files) > MAX_CHAT_FILES:
        raise ClientPayloadError(400, f"files must contain at most {MAX_CHAT_FILES} opaque ids")
    opaque_ids = [_canonical_capsule_file_id(file_id) for file_id in files]
    if any(file_id is None for file_id in opaque_ids) or len(opaque_ids) != len(set(opaque_ids)):
        raise ClientPayloadError(400, "files must contain unique opaque ids")
    turn: dict[str, object] = {"message": message}
    if opaque_ids:
        turn["files"] = opaque_ids
    return turn


def _capsule_create_payload(payload: dict, account_id: str) -> tuple[str, dict[str, str]]:
    if set(payload) != {"name", "provider", "model"}:
        raise ClientPayloadError(400, "Capsule requires name, provider, and model")
    name = str(payload.get("name", "")).strip()
    provider = _brain_provider(payload.get("provider"))
    model = _brain_model(provider, payload.get("model")) if provider is not None else None
    cid = _cid_for(account_id, name)
    if not name or not cid.strip("_"):
        raise ClientPayloadError(400, "bad capsule name")
    if provider is None:
        raise ClientPayloadError(400, "unsupported model provider")
    if model is None:
        raise ClientPayloadError(400, "unsupported model for provider")
    return cid, {"name": name, "provider": provider, "model": model}


def _public_file_metadata(value: object) -> dict | None:
    """Copy only opaque, non-path file metadata from the trusted controller response."""
    if not isinstance(value, dict):
        return None
    file_id = _canonical_capsule_file_id(value.get("id"))
    name = value.get("name")
    media_type = value.get("media_type")
    size = value.get("size")
    sha256 = value.get("sha256")
    if (
        file_id is None
        or not isinstance(name, str)
        or not name
        or name.strip() != name
        or len(name.encode()) > 255
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
        or not isinstance(media_type, str)
        or not media_type
        or len(media_type) > 127
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
        or not isinstance(sha256, str)
        or CAPSULE_FILE_SHA256_RE.fullmatch(sha256) is None
    ):
        return None
    metadata = {
        "id": file_id,
        "name": name,
        "media_type": media_type,
        "size": size,
        "sha256": sha256,
    }
    if "created_at" in value:
        created_at = value["created_at"]
        if isinstance(created_at, bool) or not isinstance(created_at, int) or created_at < 0:
            return None
        metadata["created_at"] = created_at
    return metadata


def _public_storage_usage(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    usage = {}
    for key in ("used_bytes", "limit_bytes", "remaining_bytes"):
        amount = value.get(key)
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            return None
        usage[key] = amount
    over_quota = usage["used_bytes"] >= usage["limit_bytes"] and usage["remaining_bytes"] == 0
    within_quota = usage["used_bytes"] + usage["remaining_bytes"] == usage["limit_bytes"]
    if not (over_quota or within_quota):
        return None
    return usage


def _public_file_upload(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    metadata = _public_file_metadata(value.get("file"))
    usage = _public_storage_usage(value.get("file"))
    return {"file": metadata, **usage} if metadata is not None and usage is not None else None


def _public_file_inventory(value: object) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        return None
    values = value["files"]
    if len(values) > MAX_CAPSULE_FILES:
        return None
    files = [_public_file_metadata(item) for item in values]
    if any(item is None for item in files):
        return None
    opaque_ids = [item["id"] for item in files if item is not None]
    usage = _public_storage_usage(value)
    if usage is None or len(opaque_ids) != len(set(opaque_ids)):
        return None
    return {"files": files, **usage}


def _public_file_deletion(value: object, expected_id: str) -> dict | None:
    if not isinstance(value, dict) or value.get("id") != expected_id or value.get("deleted") is not True:
        return None
    usage = _public_storage_usage(value)
    return {"id": expected_id, "deleted": True, **usage} if usage is not None else None


def _released_assistant_inventory(data: object) -> list[str] | None:
    if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
        return None
    installed: list[str] = []
    for item in data["apps"]:
        if not isinstance(item, dict):
            return None
        assistant = item.get("app")
        if assistant in RELEASED_CLOUD_ASSISTANTS:
            if assistant in installed:
                return None
            installed.append(assistant)
    return installed


app = FastAPI(title="shimpz-store", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TraceIdMiddleware)


class ClientPayloadError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def _run_bounded(executor: _BoundedThreadPoolExecutor, fn, /, *args):
    """Run one blocking hop only when its finite worker/queue budget admits it."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, fn, *args)


async def _bounded_call(
    executor: _BoundedThreadPoolExecutor,
    *args,
    **kwargs,
) -> tuple[int, dict]:
    return await _run_bounded(executor, functools.partial(_call, *args, **kwargs))


async def _read_bounded_json(request: Request, max_bytes: int) -> dict:
    """Read one JSON object without ever buffering more than `max_bytes`."""
    raw_length = request.headers.get("content-length")
    if raw_length:
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ClientPayloadError(400, "invalid Content-Length") from exc
        if length < 0:
            raise ClientPayloadError(400, "invalid Content-Length")
        if length > max_bytes:
            raise ClientPayloadError(413, f"request body too large (max {max_bytes} bytes)")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > max_bytes:
            raise ClientPayloadError(413, f"request body too large (max {max_bytes} bytes)")
        body.extend(chunk)
    try:
        payload = jsonlib.loads(body or b"{}")
    except jsonlib.JSONDecodeError as exc:
        raise ClientPayloadError(400, f"invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClientPayloadError(400, "JSON body must be an object")
    return payload


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Fail-loud: full structured trace in the logs, generic 500 to the caller. Never swallow.
    log.exception("unhandled_exception", path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.exception_handler(_ExecutorSaturatedError)
async def executor_saturated(request: Request, exc: _ExecutorSaturatedError) -> JSONResponse:
    log.warning("store_capacity_rejected", path=request.url.path)
    return JSONResponse(
        status_code=429,
        content={"detail": "Store upstream capacity reached"},
        headers={"Retry-After": "1"},
    )


# ── proxy helpers (user tokens, plus one narrow Brain-finalizer capability) ────
def _call(
    base: str,
    method: str,
    path: str,
    payload: dict | None = None,
    extra: dict | None = None,
) -> tuple[int, dict]:
    """Proxy one hop.

    The `extra` headers carry the user's account token (X-Shimpz-Account, verified by the receiving
    driver), the client IP (X-Forwarded-For, keyed by the accounts rate-limiter), or the file-backed
    Brain-finalizer bearer on its one internal call.
    """
    parsed = urlparse(base)
    headers: dict[str, str] = dict(extra or {})
    body = None
    if payload is not None:
        body = jsonlib.dumps(payload)
        headers["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=180)
    try:
        conn.request(method, path, body, headers)
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, (jsonlib.loads(raw) if raw else {})
    except (OSError, jsonlib.JSONDecodeError) as exc:
        log.warning("proxy_unreachable", base=base, path=path, error=str(exc))
        return 502, {"detail": "the Space is unreachable"}
    finally:
        conn.close()


def _set_cookie(resp: JSONResponse, token: str) -> None:
    resp.set_cookie(
        ACCOUNT_COOKIE,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=True,
        path="/",
    )


def _authed_account(request: Request) -> tuple[str, str, str]:
    """(token, account_id, username) for a valid cookie, else ('', '', ''). Verified against accounts."""
    token = request.cookies.get(ACCOUNT_COOKIE, "")
    if not token:
        return "", "", ""
    status, data = _call(ACCOUNTS_URL, "POST", "/v1/verify", {"token": token})
    if status == 200 and data.get("account_id"):
        return token, data["account_id"], data.get("username", "")
    return "", "", ""


async def _authed_account_bounded(request: Request) -> tuple[str, str, str]:
    return await _run_bounded(_AUTH_EXECUTOR, _authed_account, request)


def _client_ip(request: Request) -> str:
    """The end user's IP as best we can know it — Cloudflare's header when fronted, else the socket peer."""
    return request.headers.get("cf-connecting-ip", "") or (request.client.host if request.client else "")


def _cid_for(account_id: str, name: str) -> str:
    """Derive a collision-resistant, Docker/PG-safe ID from the complete account/name pair.

    The old eight-character account prefix had only 32 bits of collision space. Public signup makes
    an accidental or deliberately searched collision a cross-account denial-of-service risk. Keep a
    short readable suffix, but bind the complete normalized name and account ID into a 96-bit digest.
    """
    normalized = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    if not normalized:
        return ""
    digest = hashlib.sha256(f"{account_id}\0{normalized}".encode()).hexdigest()[:24]
    return f"{digest}_{normalized[:15]}".rstrip("_")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ── account auth (proxied to the `accounts` identity service) ──────────────────
@app.post("/api/signup")
async def signup(request: Request) -> JSONResponse:
    try:
        payload = await _read_bounded_json(request, MAX_AUTH_BODY_BYTES)
    except ClientPayloadError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)
    status, data = await _bounded_call(
        _AUTH_EXECUTOR,
        ACCOUNTS_URL,
        "POST",
        "/v1/signup",
        {"username": payload.get("username"), "password": payload.get("password")},
        extra={"X-Forwarded-For": _client_ip(request)},
    )
    body = {"account_id": data.get("account_id"), "username": data.get("username")} if status == 200 else data
    resp = JSONResponse(body, status_code=status)
    if status == 200 and data.get("token"):
        _set_cookie(resp, data["token"])
        log.info("signup", username=data.get("username"))
    return resp


@app.post("/api/login")
async def login(request: Request) -> JSONResponse:
    try:
        payload = await _read_bounded_json(request, MAX_AUTH_BODY_BYTES)
    except ClientPayloadError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)
    status, data = await _bounded_call(
        _AUTH_EXECUTOR,
        ACCOUNTS_URL,
        "POST",
        "/v1/login",
        {"username": payload.get("username"), "password": payload.get("password")},
        extra={"X-Forwarded-For": _client_ip(request)},
    )
    body = {"account_id": data.get("account_id"), "username": data.get("username")} if status == 200 else data
    resp = JSONResponse(body, status_code=status)
    if status == 200 and data.get("token"):
        _set_cookie(resp, data["token"])
    return resp


@app.post("/api/logout")
def logout() -> JSONResponse:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(ACCOUNT_COOKIE, path="/")
    return resp


@app.get("/api/me")
async def me(request: Request) -> JSONResponse:
    _, account_id, username = await _authed_account_bounded(request)
    return JSONResponse(
        {
            "authenticated": bool(account_id),
            "account_id": account_id or None,
            "username": username or None,
        }
    )


# ── Account model credentials (one encrypted-at-rest API key per provider) ────
BRAIN_PROVIDERS = frozenset(MODEL_CATALOG)
MAX_BRAIN_CREDENTIAL_BODY_BYTES = 72 * 1024


def _brain_provider(value: str) -> str | None:
    provider = str(value or "").strip().lower()
    return provider if provider in BRAIN_PROVIDERS else None


def _brain_model(provider: str, value: object) -> str | None:
    model = str(value or "").strip()
    return model if model in MODEL_CATALOG[provider] else None


@app.get("/api/brains")
async def brains_list(request: Request) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _AUTH_EXECUTOR,
        ACCOUNTS_URL,
        "POST",
        "/v1/brains/list",
        {"token": token},
        extra={"X-Forwarded-For": _client_ip(request)},
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/brains/{provider}")
async def brain_upsert(request: Request, provider: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    provider_value = _brain_provider(provider)
    if provider_value is None:
        return JSONResponse({"detail": "unsupported Brain provider"}, status_code=400)
    try:
        payload = await _read_bounded_json(
            request,
            MAX_BRAIN_CREDENTIAL_BODY_BYTES,
        )
    except ClientPayloadError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)
    if set(payload) != {"auth_type", "secret"}:
        return JSONResponse({"detail": "credential requires auth_type and secret"}, status_code=400)
    auth_type = str(payload.get("auth_type") or "").strip().lower()
    secret = payload.get("secret")
    if auth_type != "api_key" or not isinstance(secret, str):
        return JSONResponse({"detail": "invalid Brain credential"}, status_code=400)
    status, data = await _bounded_call(
        _AUTH_EXECUTOR,
        ACCOUNTS_URL,
        "POST",
        "/v1/brains/upsert",
        {
            "token": token,
            "provider": provider_value,
            "auth_type": auth_type,
            "secret": secret,
        },
        {"X-Forwarded-For": _client_ip(request)},
    )
    log.info("brain_upsert", provider=provider_value, status=status)
    return JSONResponse(data, status_code=status)


@app.delete("/api/brains/{provider}")
async def brain_delete(request: Request, provider: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    provider_value = _brain_provider(provider)
    if provider_value is None:
        return JSONResponse({"detail": "unsupported Brain provider"}, status_code=400)
    return await _run_bounded(
        _CONTROL_EXECUTOR,
        _delete_brain_for_token,
        token,
        provider_value,
        _client_ip(request),
    )


def _revocation_state(begin_data: dict) -> tuple[bool, int | None]:
    already_absent = begin_data.get("already_absent") is True
    generation = begin_data.get("generation")
    if not already_absent and (not isinstance(generation, int) or isinstance(generation, bool) or generation < 1):
        raise ValueError("credential revocation returned invalid state")
    return already_absent, generation


def _delete_brain_for_token(token: str, provider: str, forwarded_for: str) -> JSONResponse:
    begin_status, begin_data = _call(
        ACCOUNTS_URL,
        "POST",
        "/v1/brains/revoke-begin",
        {"token": token, "provider": provider},
        extra={"X-Forwarded-For": forwarded_for},
    )
    if begin_status != 200 or not isinstance(begin_data, dict):
        return JSONResponse(begin_data, status_code=begin_status)
    try:
        already_absent, generation = _revocation_state(begin_data)
    except ValueError as exc:
        return JSONResponse(
            {"detail": str(exc)},
            status_code=502,
        )
    if already_absent:
        log.info("brain_delete", provider=provider, status=200, already_absent=True)
        return JSONResponse(
            {
                "provider": provider,
                "generation": generation,
                "deleted": False,
                "already_absent": True,
            }
        )
    try:
        finalize_token = BRAIN_FINALIZE_TOKEN_FILE.read_text().strip()
    except OSError:
        finalize_token = ""
    if not finalize_token:
        log.warning("brain_finalize_unavailable", provider=provider)
        return JSONResponse(
            {"detail": "Brain credential finalization is unavailable"},
            status_code=502,
        )
    status, data = _call(
        ACCOUNTS_URL,
        "POST",
        "/v1/internal/brains/revoke-finalize",
        {"token": token, "provider": provider, "generation": generation},
        extra={
            "Authorization": f"Bearer {finalize_token}",
            "X-Forwarded-For": forwarded_for,
        },
    )
    log.info("brain_delete", provider=provider, status=status)
    return JSONResponse(data, status_code=status)


# ── Capsules (forward the user's token; capsule-driver is the enforcer) ────────
@app.get("/api/capsules")
async def capsules_list(request: Request) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "GET",
        "/v1/capsules",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/capsules")
async def capsules_create(request: Request) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    try:
        payload = await _read_bounded_json(request, MAX_CAPSULE_CREATE_BODY_BYTES)
        cid, create_payload = _capsule_create_payload(payload, account_id)
    except ClientPayloadError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "POST",
        f"/v1/capsules/{cid}/create",
        create_payload,
        {"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.delete("/api/capsules/{cid}")
async def capsules_destroy(request: Request, cid: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "DELETE",
        f"/v1/capsules/{cid}",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/capsules/{cid}/install")
async def capsule_install(request: Request, cid: str) -> JSONResponse:
    """Install one trusted internal-registry App into an owned Capsule.

    The Store forwards the account token and App ID; capsule-driver enforces ownership, resolves the
    immutable artifact, and applies the Capsule isolation policy. This operational endpoint has no
    dependency on the unrendered APPS inventory or any public product route.
    """
    token, account_id, _ = await _authed_account_bounded(request)
    if not token:
        return _private_json({"detail": "not authenticated"}, 401)
    try:
        if not _assistant_mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        if request.headers.get("content-type", "").strip().lower() != "application/json":
            raise ClientPayloadError(415, "Content-Type must be application/json")
        capsule_id = _canonical_capsule_id(cid)
        if capsule_id is None:
            raise ClientPayloadError(400, "bad capsule id")
        payload = await _read_bounded_json(request, MAX_CAPSULE_INSTALL_BODY_BYTES)
        if set(payload) != {"app"}:
            raise ClientPayloadError(400, "body must contain only app")
        app_id = _canonical_assistant_id(payload["app"])
        if app_id is None:
            raise ClientPayloadError(400, "bad app id")
    except ClientPayloadError as exc:
        return _private_json({"detail": exc.detail}, exc.status)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "POST",
        f"/v1/capsules/{capsule_id}/apps",
        {"app": app_id},
        {"X-Shimpz-Account": token},
    )
    log.info(
        "app_install",
        account=account_id,
        capsule=capsule_id,
        app=app_id,
        status=status,
        installed=data.get("installed"),
    )
    return _private_json(data, status)


@app.get("/api/capsules/{cid}/apps")
async def capsule_apps(request: Request, cid: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "GET",
        f"/v1/capsules/{cid}/apps",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.delete("/api/capsules/{cid}/apps/{app_id}")
async def capsule_uninstall(request: Request, cid: str, app_id: str) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "DELETE",
        f"/v1/capsules/{cid}/apps/{app_id}",
        extra={"X-Shimpz-Account": token},
    )
    log.info("app_uninstall", account=account_id, capsule=cid, app=app_id, status=status)
    return JSONResponse(data, status_code=status)


# ── Assistant Store cloud lifecycle (closed adapter over the legacy Capsule App plane) ──────────
@app.get("/api/capsules/{cid}/assistants")
async def cloud_assistants_list(request: Request, cid: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return _private_json({"detail": "not authenticated"}, 401)
    capsule_id = _canonical_capsule_id(cid)
    if capsule_id is None:
        return _private_json({"detail": "bad capsule id"}, 400)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "GET",
        f"/v1/capsules/{capsule_id}/apps",
        extra={"X-Shimpz-Account": token},
    )
    if status != 200:
        return _private_json(data, status)
    installed = _released_assistant_inventory(data)
    if installed is None:
        log.warning("assistant_inventory_invalid", capsule=capsule_id)
        return _private_json({"detail": "invalid Assistant inventory"}, 502)
    return _private_json({"installed": installed})


@app.post("/api/capsules/{cid}/assistants")
async def cloud_assistant_install(request: Request, cid: str) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    if not token:
        return _private_json({"detail": "not authenticated"}, 401)
    try:
        if not _assistant_mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        if request.headers.get("content-type", "").strip().lower() != "application/json":
            raise ClientPayloadError(415, "Content-Type must be application/json")
        capsule_id = _canonical_capsule_id(cid)
        if capsule_id is None:
            raise ClientPayloadError(400, "bad capsule id")
        payload = await _read_bounded_json(request, MAX_CAPSULE_INSTALL_BODY_BYTES)
        if set(payload) != {"assistant"}:
            raise ClientPayloadError(400, "body must contain only assistant")
        assistant = _canonical_assistant_id(payload["assistant"])
        if assistant not in RELEASED_CLOUD_ASSISTANTS:
            raise ClientPayloadError(404, "Assistant is not released")
    except ClientPayloadError as exc:
        return _private_json({"detail": exc.detail}, exc.status)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "POST",
        f"/v1/capsules/{capsule_id}/apps",
        {"app": assistant},
        {"X-Shimpz-Account": token},
    )
    log.info(
        "assistant_install",
        account=account_id,
        capsule=capsule_id,
        assistant=assistant,
        status=status,
    )
    if not 200 <= status < 300:
        return _private_json(data, status)
    return _private_json({"assistant": assistant, "accepted": True})


@app.delete("/api/capsules/{cid}/assistants/{assistant}")
async def cloud_assistant_uninstall(request: Request, cid: str, assistant: str) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    if not token:
        return _private_json({"detail": "not authenticated"}, 401)
    try:
        if not _assistant_mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        capsule_id = _canonical_capsule_id(cid)
        assistant_id = _canonical_assistant_id(assistant)
        if capsule_id is None:
            raise ClientPayloadError(400, "bad capsule id")
        if assistant_id is None:
            raise ClientPayloadError(400, "bad Assistant id")
        if assistant_id not in RELEASED_CLOUD_ASSISTANTS:
            raise ClientPayloadError(404, "Assistant is not released")
    except ClientPayloadError as exc:
        return _private_json({"detail": exc.detail}, exc.status)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "DELETE",
        f"/v1/capsules/{capsule_id}/apps/{assistant_id}",
        extra={"X-Shimpz-Account": token},
    )
    log.info(
        "assistant_uninstall",
        account=account_id,
        capsule=capsule_id,
        assistant=assistant_id,
        status=status,
    )
    if not 200 <= status < 300:
        return _private_json(data, status)
    return _private_json({"assistant": assistant_id, "accepted": True})


# ── the Captain's chat (ADR-0004): forwarded to the capsule-driver's named exec ops ──────────────
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # well under Cloudflare's 100 MB proxied-body cap; big files → R2 later


@app.get("/api/capsules/{cid}/inference")
async def capsule_inference(request: Request, cid: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "GET",
        f"/v1/capsules/{cid}/inference",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.put("/api/capsules/{cid}/inference")
async def capsule_inference_configure(request: Request, cid: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    try:
        payload = await _read_bounded_json(request, MAX_INFERENCE_BODY_BYTES)
    except ClientPayloadError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)
    if set(payload) != {"provider", "model"}:
        return JSONResponse({"detail": "inference requires provider and model"}, status_code=400)
    provider = _brain_provider(payload.get("provider"))
    model = _brain_model(provider, payload.get("model")) if provider is not None else None
    if provider is None:
        return JSONResponse({"detail": "unsupported model provider"}, status_code=400)
    if model is None:
        return JSONResponse({"detail": "unsupported model for provider"}, status_code=400)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "PUT",
        f"/v1/capsules/{cid}/inference",
        {"provider": provider, "model": model},
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/capsules/{cid}/chat")
async def capsule_chat(request: Request, cid: str) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    try:
        payload = await _read_bounded_json(request, MAX_CHAT_BODY_BYTES)
        body = _chat_turn_payload(payload)
    except ClientPayloadError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "POST",
        f"/v1/capsules/{cid}/chat",
        body,
        {"X-Shimpz-Account": token},
    )
    log.info(
        "chat",
        account=account_id,
        capsule=cid,
        status=status,
        chars=len(body["message"]),
    )
    if 200 <= status < 300:
        projected = _validated_chat_response(data, cid)
        if projected is None:
            return _private_json({"detail": TERMINAL_CONTRACT_ERROR}, 502)
        return _private_json(projected, status)
    detail = data.get("detail") or data.get("error")
    if (
        not isinstance(detail, str)
        or not detail
        or detail != detail.strip()
        or len(detail) > MAX_CHAT_ERROR_DETAIL_CHARS
        or re.search(r"[\x00-\x1f\x7f]", detail) is not None
    ):
        detail = "chat request failed"
    return _private_json({"detail": detail}, status)


@app.get("/api/capsules/{cid}/files")
async def capsule_files(request: Request, cid: str) -> JSONResponse:
    """List opaque file metadata; file bytes and host paths remain controller-private."""
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return _private_json({"detail": "not authenticated"}, 401)
    capsule_id = _canonical_capsule_id(cid)
    if capsule_id is None:
        return _private_json({"detail": "bad capsule id"}, 400)
    status, body = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "GET",
        f"/v1/capsules/{capsule_id}/files",
        extra={"X-Shimpz-Account": token},
    )
    if status != 200:
        return _private_json(body, status)
    inventory = _public_file_inventory(body)
    if inventory is None:
        log.warning("capsule_file_inventory_invalid", capsule=capsule_id)
        return _private_json({"detail": "invalid Capsule storage inventory"}, 502)
    return _private_json(inventory)


@app.post("/api/capsules/{cid}/files")
async def capsule_file_upload(request: Request, cid: str, file: UploadFile) -> JSONResponse:
    """Upload one opaque Capsule object without granting a Brain or Assistant filesystem access."""
    token, account_id, _ = await _authed_account_bounded(request)
    try:
        if not token:
            raise ClientPayloadError(401, "not authenticated")
        if not _assistant_mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        capsule_id = _canonical_capsule_id(cid)
        if capsule_id is None:
            raise ClientPayloadError(400, "bad capsule id")
    except ClientPayloadError as exc:
        return _private_json({"detail": exc.detail}, exc.status)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return _private_json(
            {"detail": f"file too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)"},
            413,
        )
    payload = {
        "filename": file.filename or "upload.bin",
        "media_type": file.content_type or "application/octet-stream",
        "content_b64": base64.b64encode(data).decode(),
    }
    status, body = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "POST",
        f"/v1/capsules/{capsule_id}/files",
        payload,
        extra={"X-Shimpz-Account": token},
    )
    log.info("capsule_file_upload", account=account_id, capsule=capsule_id, bytes=len(data), status=status)
    if status != 200:
        return _private_json(body, status)
    uploaded = _public_file_upload(body)
    if uploaded is None:
        log.warning("capsule_file_upload_invalid", capsule=capsule_id)
        return _private_json({"detail": "invalid Capsule storage response"}, 502)
    return _private_json(uploaded)


@app.delete("/api/capsules/{cid}/files/{file_id}")
async def capsule_file_delete(request: Request, cid: str, file_id: str) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    try:
        if not token:
            raise ClientPayloadError(401, "not authenticated")
        if not _assistant_mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        capsule_id = _canonical_capsule_id(cid)
        opaque_id = _canonical_capsule_file_id(file_id)
        if capsule_id is None:
            raise ClientPayloadError(400, "bad capsule id")
        if opaque_id is None:
            raise ClientPayloadError(404, "file not found")
    except ClientPayloadError as exc:
        return _private_json({"detail": exc.detail}, exc.status)
    status, body = await _bounded_call(
        _CONTROL_EXECUTOR,
        CAPSULEDRIVER_URL,
        "DELETE",
        f"/v1/capsules/{capsule_id}/files/{opaque_id}",
        extra={"X-Shimpz-Account": token},
    )
    log.info(
        "capsule_file_delete",
        account=account_id,
        capsule=capsule_id,
        file_id=opaque_id,
        status=status,
    )
    if status != 200:
        return _private_json(body, status)
    deleted = _public_file_deletion(body, opaque_id)
    if deleted is None:
        log.warning("capsule_file_delete_invalid", capsule=capsule_id, file_id=opaque_id)
        return _private_json({"detail": "invalid Capsule storage response"}, 502)
    return _private_json(deleted)


# ── the Captain's LIVE bridge: one closed terminal event per WebSocket turn ─────


class WebSocketPayloadError(Exception):
    def __init__(self, status: int, detail: str, close_code: int) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.close_code = close_code


async def _ws_receive_bounded_json(ws: WebSocket) -> dict:
    message = await ws.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    raw = message.get("text")
    if raw is None:
        data = message.get("bytes") or b""
        if len(data) > MAX_WS_FRAME_BYTES:
            raise WebSocketPayloadError(413, "WebSocket frame too large", 1009)
        try:
            raw = data.decode()
        except UnicodeDecodeError as exc:
            raise WebSocketPayloadError(400, "WebSocket frame must be UTF-8 JSON", 1007) from exc
    elif len(raw.encode()) > MAX_WS_FRAME_BYTES:
        raise WebSocketPayloadError(413, "WebSocket frame too large", 1009)
    try:
        payload = jsonlib.loads(raw)
    except jsonlib.JSONDecodeError as exc:
        raise WebSocketPayloadError(400, "WebSocket frame must be valid JSON", 1007) from exc
    if not isinstance(payload, dict):
        raise WebSocketPayloadError(400, "WebSocket JSON must be an object", 1007)
    return payload


async def _ws_verify(ws: WebSocket) -> tuple[str, str]:
    token = ws.cookies.get(ACCOUNT_COOKIE, "")
    if not token:
        return "", ""
    status, data = await _bounded_call(_AUTH_EXECUTOR, ACCOUNTS_URL, "POST", "/v1/verify", {"token": token})
    account_id = data.get("account_id") if status == 200 else None
    return (token, str(account_id)) if account_id else ("", "")


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


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def _validated_done_event(value: dict) -> dict | None:
    if set(value) != {"type", "reply", "team"}:
        return None
    reply = _canonical_chat_reply(value["reply"])
    team = _canonical_team_name(value["team"])
    if reply is None or team is None:
        return None
    return {"type": "done", "reply": reply, "team": team}


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
    return {"type": "error", "status": status, "detail": detail}


def _validated_terminal_event(value: object) -> dict | None:
    """Project an untrusted controller value onto the only browser-visible chat events."""
    if not isinstance(value, dict):
        return None
    if value.get("type") == "done":
        return _validated_done_event(value)
    if value.get("type") == "error":
        return _validated_error_event(value)
    if value.get("type") == "stopped" and set(value) == {"type"}:
        return {"type": "stopped"}
    return None


def _parsed_stream_event(line: bytes) -> dict | None:
    if not line.strip():
        return None
    try:
        event = jsonlib.loads(line, object_pairs_hook=_unique_json_object)
    except jsonlib.JSONDecodeError, UnicodeDecodeError, ValueError:
        return None
    return _validated_terminal_event(event)


def _upstream_error_event(status: int, raw: bytes) -> dict:
    safe_status = status if isinstance(status, int) and not isinstance(status, bool) and 400 <= status <= 599 else 502
    detail = f"capsule-driver returned HTTP {safe_status}"
    with contextlib.suppress(jsonlib.JSONDecodeError, UnicodeDecodeError):
        payload = jsonlib.loads(raw)
        if isinstance(payload, dict):
            candidate = payload.get("detail") or payload.get("error")
            if isinstance(candidate, str):
                candidate = re.sub(r"[\x00-\x1f\x7f]", " ", candidate).strip()
                if candidate:
                    detail = candidate[:MAX_CHAT_ERROR_DETAIL_CHARS]
    return {"type": "error", "status": safe_status, "detail": detail}


class _StreamLimitError(ValueError):
    """The capsule-driver stream exceeded a bounded relay contract."""


class _StreamProtocolError(ValueError):
    """The capsule-driver stream violated its typed NDJSON contract."""


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
) -> None:
    """Release exactly one validated terminal event after the controller closes its response."""
    terminal_event = None
    try:
        for line in _bounded_upstream_lines(resp):
            if not line.strip():
                continue
            event = _parsed_stream_event(line)
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
    cid: str
    text: str
    headers: dict
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop
    started: asyncio.Event
    files: tuple[str, ...] = ()


@dataclass
class _RelayDelivery:
    terminal_seen: bool = False
    aborted: bool = False
    stop_attempted: bool = False


async def _stop_delivery_once(
    cid: str,
    hdr: dict,
    delivery: _RelayDelivery,
) -> None:
    """Request provider cancellation at most once for one admitted relay."""
    if delivery.stop_attempted:
        return
    delivery.stop_attempted = True
    await _driver_stop(cid, hdr)


async def _send_relay_event(
    turn: _WsTurn,
    event: dict,
    delivery: _RelayDelivery,
) -> None:
    projected = dict(event)
    relay_abort = bool(projected.pop("_relay_abort", False))
    terminal = _validated_terminal_event(projected)
    if terminal is None:
        terminal = {"type": "error", "status": 502, "detail": TERMINAL_CONTRACT_ERROR}
        relay_abort = True
    if relay_abort:
        if not delivery.aborted:
            await _stop_delivery_once(turn.cid, turn.headers, delivery)
        delivery.aborted = True
    delivery.terminal_seen = True
    await turn.ws.send_json(terminal)


def _stream_lines(relay: _StreamRelay) -> None:
    """BLOCKING (run in a thread): relay the driver's NDJSON into a bounded asyncio queue."""
    parsed = urlparse(CAPSULEDRIVER_URL)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=200)
    try:
        payload: dict[str, object] = {"message": relay.text}
        if relay.files:
            payload["files"] = list(relay.files)
        body = jsonlib.dumps(payload, ensure_ascii=False).encode()
        conn.request(
            "POST",
            f"/v1/capsules/{relay.cid}/chat/stream",
            body,
            {**relay.headers, "Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        relay.loop.call_soon_threadsafe(relay.started.set)
        if not 200 <= resp.status < 300:
            _stream_queue_put(
                relay.queue,
                relay.loop,
                _upstream_error_event(resp.status, resp.read(MAX_UPSTREAM_ERROR_BYTES + 1)),
            )
            return
        _relay_upstream_events(resp, relay.queue, relay.loop)
    except (OSError, http.client.HTTPException) as exc:
        log.warning("chat_stream_failed", capsule=relay.cid, error=type(exc).__name__)
        _stream_queue_put(
            relay.queue,
            relay.loop,
            {
                "type": "error",
                "status": 502,
                "detail": "capsule-driver stream failed",
                "_relay_abort": True,
            },
        )
    finally:
        relay.loop.call_soon_threadsafe(relay.started.set)
        conn.close()
        _stream_queue_put(relay.queue, relay.loop, None)


async def _driver_stop(cid: str, hdr: dict) -> tuple[int, dict]:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            _STOP_EXECUTOR,
            _call,
            CAPSULEDRIVER_URL,
            "POST",
            f"/v1/capsules/{cid}/chat/stop",
            None,
            hdr,
        )
    except _ExecutorSaturatedError:
        return 429, {"detail": "chat stop capacity reached"}


@dataclass(frozen=True)
class _WsTurn:
    ws: WebSocket
    cid: str
    headers: dict
    text: str
    started: asyncio.Event
    dispatched: asyncio.Event
    files: tuple[str, ...] = ()


def _relay_capacity_event() -> dict:
    return {
        "type": "error",
        "status": 429,
        "detail": "chat relay capacity reached",
    }


async def _deliver_turn(turn: _WsTurn, queue: asyncio.Queue, worker: asyncio.Future) -> None:
    delivery = _RelayDelivery()
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
            await _stop_delivery_once(turn.cid, turn.headers, delivery)
            await turn.ws.send_json(
                {
                    "type": "error",
                    "status": 502,
                    "detail": "capsule-driver relay ended before a terminal event",
                }
            )
    except WebSocketDisconnect, OSError, RuntimeError, asyncio.CancelledError:
        await _stop_delivery_once(turn.cid, turn.headers, delivery)
        raise
    finally:
        if not delivery.terminal_seen and not worker.done():
            await _stop_delivery_once(turn.cid, turn.headers, delivery)
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
                    turn.cid,
                    turn.text,
                    turn.headers,
                    queue,
                    loop,
                    turn.started,
                    turn.files,
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
    cid: str,
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
            cid=cid,
            headers=hdr,
            text=payload["message"],
            started=started,
            dispatched=dispatched,
            files=tuple(payload.get("files", [])),
        ),
        admitted,
    )


def _start_ws_turn(
    ws: WebSocket,
    cid: str,
    hdr: dict,
    msg: dict,
    lease: _TurnLease,
) -> tuple[asyncio.Task, asyncio.Event, asyncio.Event]:
    started = asyncio.Event()
    dispatched = asyncio.Event()
    turn = asyncio.create_task(
        _ws_run_admitted_turn(
            _WsTurn(
                ws=ws,
                cid=cid,
                headers=hdr,
                text=msg["message"],
                started=started,
                dispatched=dispatched,
                files=tuple(msg.get("files", [])),
            ),
            lease,
        )
    )
    return turn, started, dispatched


async def _ws_stop_turn(ws: WebSocket, cid: str, hdr: dict, state: dict) -> None:
    turns = state["turns"]
    active = next((turn for turn in turns if not turn.done()), None)
    if active is None:
        await ws.send_json({"type": "error", "status": 409, "detail": "no active chat turn"})
        return
    lease = state["leases"][active]
    queued = lease.cancel_if_queued()
    if queued or not state["dispatches"][active].is_set():
        active.cancel()
        await asyncio.gather(active, return_exceptions=True)
        await ws.send_json({"type": "stopped"})
        return
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(state["starts"][active].wait(), timeout=10)
    status, data = await _driver_stop(cid, hdr)
    if status != 200 or not data.get("requested"):
        error_status = status if status != 200 else 409
        detail = data.get("detail") or data.get("error")
        if not isinstance(detail, str):
            detail = "chat turn could not be stopped"
        await ws.send_json(
            _upstream_error_event(
                error_status,
                jsonlib.dumps({"detail": detail}, ensure_ascii=False).encode(),
            )
        )


async def _ws_dispatch(ws: WebSocket, cid: str, hdr: dict, msg: dict, state: dict) -> None:
    turns = state["turns"]
    starts = state.setdefault("starts", {})
    dispatches = state.setdefault("dispatches", {})
    leases = state.setdefault("leases", {})
    if msg.get("type") == "chat":
        try:
            if set(msg) not in (
                {"type", "message"},
                {"type", "message", "files"},
            ):
                raise ClientPayloadError(
                    400,
                    "chat frame must contain type, message, and optional files",
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
                    "detail": "capsule already has an active chat turn",
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
            turn, started, dispatched = _start_ws_turn(ws, cid, hdr, msg, lease)
        except BaseException:
            lease.release()
            raise
        turns.add(turn)
        starts[turn] = started
        dispatches[turn] = dispatched
        leases[turn] = lease

        def turn_done(completed: asyncio.Task) -> None:
            lease.release()
            turns.discard(completed)
            starts.pop(completed, None)
            dispatches.pop(completed, None)
            leases.pop(completed, None)

        turn.add_done_callback(turn_done)
    elif msg.get("type") == "stop" and set(msg) == {"type"}:
        await _ws_stop_turn(ws, cid, hdr, state)
    else:
        await ws.send_json({"type": "error", "status": 400, "detail": "unsupported chat frame"})


@app.websocket("/api/capsules/{cid}/ws")
async def capsule_ws(ws: WebSocket, cid: str) -> None:
    origin = ws.headers.get("origin")
    if not _ws_origin_allowed(origin):
        log.warning("ws_origin_denied", origin=origin or "<missing>")
        await ws.close(code=4403)
        return
    try:
        token, account_id = await _ws_verify(ws)
    except _ExecutorSaturatedError:
        await ws.close(code=4429)
        return
    if not token:
        await ws.close(code=4401)
        return
    connection = _WS_CONNECTION_ADMISSION.reserve(account_id, cid)
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
        await ws.accept()
        hdr = {"X-Shimpz-Account": token}
        state: dict = {
            "turns": set(),
            "starts": {},
            "dispatches": {},
            "leases": {},
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
                await _ws_dispatch(ws, cid, hdr, message, state)
        except WebSocketDisconnect:
            return
        finally:
            turns = list(state["turns"])
            for turn in turns:
                turn.cancel()
            await asyncio.gather(*turns, return_exceptions=True)
    finally:
        connection.release()


# ── static: serve the prerendered SvelteKit build (adapter-static writes <route>.html + assets) ──
def _resolve(rel: str) -> Path | None:
    rel = rel.strip("/")
    if ".." in rel.split("/"):  # no traversal out of BUILD
        return None
    for cand in (BUILD / rel, BUILD / f"{rel}.html", BUILD / rel / "index.html"):
        if cand.is_file():
            return cand
    return None


def _static_cache_control(path: str, hit: Path) -> str:
    """Revalidate navigations while retaining SvelteKit's content-addressed asset cache."""
    rel = path.strip("/")
    if hit.suffix.lower() not in {".html", ".htm"} and rel.startswith("_app/immutable/"):
        return IMMUTABLE_CACHE_CONTROL
    return HTML_CACHE_CONTROL


@app.get("/{path:path}")
def static_files(path: str) -> Response:
    hit = _resolve(path)
    if hit:
        return FileResponse(hit, headers={"Cache-Control": _static_cache_control(path, hit)})
    return PlainTextResponse(
        "not found",
        status_code=404,
        headers={"Cache-Control": HTML_CACHE_CONTROL},
    )

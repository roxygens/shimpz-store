"""Serve the Shimpz public console and account-authenticated control surface.

One FastAPI process serves the prerendered SvelteKit build and `/api`: signup/login, Team selection,
and installed-App management. It holds no driver/admin credential; it forwards the user's account token
to the socket-holding `team-driver`, which enforces ownership. Its one narrow service capability can
only finalize an exact already-revoking model credential generation. It is reached over the
Space's internal networks (accounts_net + teamdriver_net) and uses stdlib http.client for proxy hops.
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
import re
from dataclasses import dataclass, field
from http import HTTPStatus
from urllib.parse import urlparse

import structlog
from fastapi import FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app import team_driver_contract
from app.authn import (
    EXECUTOR as _AUTH_EXECUTOR,
)
from app.authn import (
    authed_account_bounded as _authed_account_bounded,
)
from app.authn import (
    client_ip as _client_ip,
)
from app.concurrency import (
    BoundedThreadPoolExecutor as _BoundedThreadPoolExecutor,
)
from app.concurrency import (
    ExecutorSaturatedError as _ExecutorSaturatedError,
)
from app.concurrency import (
    TurnAdmission as _TurnAdmission,
)
from app.concurrency import (
    TurnLease as _TurnLease,
)
from app.concurrency import (
    WsConnectionAdmission as _WsConnectionAdmission,
)
from app.config import (
    ACCOUNT_COOKIE,
    ACCOUNTS_URL,
    ASSISTANT_MUTATION_ALLOWED_ORIGINS,
    BRAIN_FINALIZE_TOKEN_FILE,
    CHAT_WS_SUBPROTOCOL,
    MAX_CHAT_ASSISTANTS,
    MAX_CHAT_ERROR_DETAIL_CHARS,
    MAX_CHAT_FILES,
    MAX_CHAT_MESSAGE_CHARS,
    MAX_CHAT_REPLY_CHARS,
    MAX_INFERENCE_BODY_BYTES,
    MAX_TEAM_CREATE_BODY_BYTES,
    MAX_TEAM_INSTALL_BODY_BYTES,
    MAX_UPSTREAM_STREAM_BYTES,
    MAX_UPSTREAM_STREAM_LINE_BYTES,
    MAX_WS_FRAME_BYTES,
    PRIVATE_NO_STORE_HEADERS,
    RELEASED_CLOUD_ASSISTANTS,
    STOP_QUEUE_MAX,
    STOP_WORKER_THREADS,
    STREAM_QUEUE_MAX_EVENTS,
    STREAM_QUEUE_PUT_TIMEOUT,
    STREAM_TURN_QUEUE_MAX,
    STREAM_WORKER_THREADS,
    TEAMDRIVER_URL,
    TERMINAL_CONTRACT_ERROR,
    WS_ACCOUNT_CONNECTION_LIMIT,
    WS_ALLOWED_ORIGINS,
    WS_GLOBAL_CONNECTION_LIMIT,
    WS_TEAM_CONNECTION_LIMIT,
)
from app.config import (
    canonical_origin as _canonical_origin,
)
from app.control import EXECUTOR as _CONTROL_EXECUTOR
from app.inference import model as _brain_model
from app.inference import provider as _brain_provider
from app.logconf import setup
from app.middleware import TraceIdMiddleware
from app.payloads import (
    ClientPayloadError,
)
from app.payloads import (
    read_bounded_json as _read_bounded_json,
)
from app.payloads import (
    unique_json_object as _unique_json_object,
)
from app.projections import (
    public_file_deletion as _public_file_deletion,
)
from app.projections import (
    public_file_inventory as _public_file_inventory,
)
from app.projections import (
    public_file_upload as _public_file_upload,
)
from app.projections import (
    released_assistant_inventory as _released_assistant_inventory,
)
from app.projections import (
    released_running_assistant_inventory as _released_running_assistant_inventory,
)
from app.routers import account, oauth, public, static
from app.upstream import call as _call

setup("shimpz-store")
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


_CHALLENGE_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
_HUMAN_REQUEST_TYPES = frozenset({"str", "int", "float", "bool", "choice", "choices"})


def _ws_origin_allowed(origin: str | None) -> bool:
    canonical = _canonical_origin(origin)
    return canonical is not None and canonical in WS_ALLOWED_ORIGINS


def _assistant_mutation_origin_allowed(origin: str | None) -> bool:
    canonical = _canonical_origin(origin)
    return canonical is not None and canonical in ASSISTANT_MUTATION_ALLOWED_ORIGINS


def _private_json(content: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content, status_code=status_code, headers=PRIVATE_NO_STORE_HEADERS)


_canonical_team_id = team_driver_contract.canonical_team_id
_canonical_assistant_id = team_driver_contract.canonical_assistant_id
_canonical_team_name = team_driver_contract.canonical_team_name
_canonical_team_file_id = team_driver_contract.canonical_file_id


def _canonical_chat_reply(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_CHAT_REPLY_CHARS
        or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value) is not None
    ):
        return None
    return value


def _chat_turn_payload(payload: dict) -> dict[str, object]:
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
    opaque_ids = [_canonical_team_file_id(file_id) for file_id in files]
    if any(file_id is None for file_id in opaque_ids) or len(opaque_ids) != len(set(opaque_ids)):
        raise ClientPayloadError(400, "files must contain unique opaque ids")
    assistant_ids = payload["assistant_ids"]
    if not isinstance(assistant_ids, list) or len(assistant_ids) > MAX_CHAT_ASSISTANTS:
        raise ClientPayloadError(
            400,
            f"assistant_ids must contain at most {MAX_CHAT_ASSISTANTS} Assistant ids",
        )
    canonical_assistant_ids = [_canonical_assistant_id(assistant_id) for assistant_id in assistant_ids]
    if any(assistant_id is None for assistant_id in canonical_assistant_ids) or len(canonical_assistant_ids) != len(
        set(canonical_assistant_ids)
    ):
        raise ClientPayloadError(400, "assistant_ids must contain unique canonical Assistant ids")
    return {
        "message": message,
        "files": opaque_ids,
        "assistant_ids": canonical_assistant_ids,
    }


def _team_create_payload(payload: dict, account_id: str) -> tuple[str, dict[str, str]]:
    if set(payload) != {"team_name", "provider", "model"}:
        raise ClientPayloadError(400, "Team requires team_name, provider, and model")
    team_name = str(payload.get("team_name", "")).strip()
    provider = _brain_provider(payload.get("provider"))
    model = _brain_model(provider, payload.get("model")) if provider is not None else None
    team_id = _team_id_for(account_id, team_name)
    if not team_name or not team_id.strip("_"):
        raise ClientPayloadError(400, "bad team name")
    if provider is None:
        raise ClientPayloadError(400, "unsupported model provider")
    if model is None:
        raise ClientPayloadError(400, "unsupported model for provider")
    return team_id, {"team_name": team_name, "provider": provider, "model": model}


_public_storage_usage = team_driver_contract.project_storage_usage


app = FastAPI(title="shimpz-store", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TraceIdMiddleware)


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


def _team_id_for(account_id: str, team_name: str) -> str:
    """Derive a collision-resistant, Docker/PG-safe ID from the complete account/Team-name pair.

    The old eight-character account prefix had only 32 bits of collision space. Public signup makes
    an accidental or deliberately searched collision a cross-account denial-of-service risk. Keep a
    short readable suffix, but bind the complete normalized name and account ID into a 96-bit digest.
    """
    normalized = re.sub(r"[^a-z0-9_]+", "_", team_name.lower()).strip("_")
    if not normalized:
        return ""
    digest = hashlib.sha256(f"{account_id}\0{normalized}".encode()).hexdigest()[:24]
    return f"{digest}_{normalized[:15]}".rstrip("_")


# ── Account model credentials (one encrypted-at-rest API key per provider) ────
MAX_BRAIN_CREDENTIAL_BODY_BYTES = 72 * 1024


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


# ── Teams (forward the user's token; team-driver is the enforcer) ────────
@app.get("/api/teams")
async def teams_list(request: Request) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "GET",
        "/v1/teams",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/teams")
async def teams_create(request: Request) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    try:
        payload = await _read_bounded_json(request, MAX_TEAM_CREATE_BODY_BYTES)
        team_id, create_payload = _team_create_payload(payload, account_id)
    except ClientPayloadError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "POST",
        f"/v1/teams/{team_id}/create",
        create_payload,
        {"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.delete("/api/teams/{team_id}")
async def teams_destroy(request: Request, team_id: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "DELETE",
        f"/v1/teams/{team_id}",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/teams/{team_id}/install")
async def team_install(request: Request, team_id: str) -> JSONResponse:
    """Install one trusted internal-registry App into an owned Team.

    The Store forwards the account token and App ID; team-driver enforces ownership, resolves the
    immutable artifact, and applies the Team isolation policy. This operational endpoint has no
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
        team_id = _canonical_team_id(team_id)
        if team_id is None:
            raise ClientPayloadError(400, "bad team id")
        payload = await _read_bounded_json(request, MAX_TEAM_INSTALL_BODY_BYTES)
        if set(payload) != {"app"}:
            raise ClientPayloadError(400, "body must contain only app")
        app_id = _canonical_assistant_id(payload["app"])
        if app_id is None:
            raise ClientPayloadError(400, "bad app id")
    except ClientPayloadError as exc:
        return _private_json({"detail": exc.detail}, exc.status)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "POST",
        f"/v1/teams/{team_id}/apps",
        {"app": app_id},
        {"X-Shimpz-Account": token},
    )
    log.info(
        "app_install",
        account=account_id,
        team_id=team_id,
        app=app_id,
        status=status,
        installed=data.get("installed"),
    )
    return _private_json(data, status)


@app.get("/api/teams/{team_id}/apps")
async def team_apps(request: Request, team_id: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "GET",
        f"/v1/teams/{team_id}/apps",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.delete("/api/teams/{team_id}/apps/{app_id}")
async def team_uninstall(request: Request, team_id: str, app_id: str) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "DELETE",
        f"/v1/teams/{team_id}/apps/{app_id}",
        extra={"X-Shimpz-Account": token},
    )
    log.info("app_uninstall", account=account_id, team_id=team_id, app=app_id, status=status)
    return JSONResponse(data, status_code=status)


# ── Assistant Store cloud lifecycle (closed adapter over the Team App plane) ─────────────────
@app.get("/api/teams/{team_id}/assistants")
async def cloud_assistants_list(request: Request, team_id: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return _private_json({"detail": "not authenticated"}, 401)
    team_id = _canonical_team_id(team_id)
    if team_id is None:
        return _private_json({"detail": "bad team id"}, 400)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "GET",
        f"/v1/teams/{team_id}/apps",
        extra={"X-Shimpz-Account": token},
    )
    if status != 200:
        return _private_json(data, status)
    installed = _released_assistant_inventory(data)
    if installed is None:
        log.warning("assistant_inventory_invalid", team_id=team_id)
        return _private_json({"detail": "invalid Assistant inventory"}, 502)
    return _private_json({"installed": installed})


@app.get("/api/teams/{team_id}/chat/assistants")
async def team_chat_assistants(request: Request, team_id: str) -> JSONResponse:
    """Return the verified default Assistant scope without exposing runtime metadata."""
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return _private_json({"detail": "not authenticated"}, 401)
    team_id = _canonical_team_id(team_id)
    if team_id is None:
        return _private_json({"detail": "bad team id"}, 400)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "GET",
        f"/v1/teams/{team_id}/apps",
        extra={"X-Shimpz-Account": token},
    )
    if status != 200:
        return _private_json(data, status)
    assistant_ids = _released_running_assistant_inventory(data)
    if assistant_ids is None:
        log.warning("chat_assistant_inventory_invalid", team_id=team_id)
        return _private_json({"detail": "invalid chat Assistant inventory"}, 502)
    return _private_json({"assistant_ids": assistant_ids})


@app.post("/api/teams/{team_id}/assistants")
async def cloud_assistant_install(request: Request, team_id: str) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    if not token:
        return _private_json({"detail": "not authenticated"}, 401)
    try:
        if not _assistant_mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        if request.headers.get("content-type", "").strip().lower() != "application/json":
            raise ClientPayloadError(415, "Content-Type must be application/json")
        team_id = _canonical_team_id(team_id)
        if team_id is None:
            raise ClientPayloadError(400, "bad team id")
        payload = await _read_bounded_json(request, MAX_TEAM_INSTALL_BODY_BYTES)
        if set(payload) != {"assistant"}:
            raise ClientPayloadError(400, "body must contain only assistant")
        assistant = _canonical_assistant_id(payload["assistant"])
        if assistant not in RELEASED_CLOUD_ASSISTANTS:
            raise ClientPayloadError(404, "Assistant is not released")
    except ClientPayloadError as exc:
        return _private_json({"detail": exc.detail}, exc.status)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "POST",
        f"/v1/teams/{team_id}/apps",
        {"app": assistant},
        {"X-Shimpz-Account": token},
    )
    log.info(
        "assistant_install",
        account=account_id,
        team_id=team_id,
        assistant=assistant,
        status=status,
    )
    if not 200 <= status < 300:
        return _private_json(data, status)
    return _private_json({"assistant": assistant, "accepted": True})


@app.delete("/api/teams/{team_id}/assistants/{assistant}")
async def cloud_assistant_uninstall(request: Request, team_id: str, assistant: str) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    if not token:
        return _private_json({"detail": "not authenticated"}, 401)
    try:
        if not _assistant_mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        team_id = _canonical_team_id(team_id)
        assistant_id = _canonical_assistant_id(assistant)
        if team_id is None:
            raise ClientPayloadError(400, "bad team id")
        if assistant_id is None:
            raise ClientPayloadError(400, "bad Assistant id")
        if assistant_id not in RELEASED_CLOUD_ASSISTANTS:
            raise ClientPayloadError(404, "Assistant is not released")
    except ClientPayloadError as exc:
        return _private_json({"detail": exc.detail}, exc.status)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "DELETE",
        f"/v1/teams/{team_id}/apps/{assistant_id}",
        extra={"X-Shimpz-Account": token},
    )
    log.info(
        "assistant_uninstall",
        account=account_id,
        team_id=team_id,
        assistant=assistant_id,
        status=status,
    )
    if not 200 <= status < 300:
        return _private_json(data, status)
    return _private_json({"assistant": assistant_id, "accepted": True})


# ── the Captain's chat (ADR-0004): forwarded to the team-driver's named exec ops ──────────────
MAX_UPLOAD_BYTES = team_driver_contract.MAX_FILE_UPLOAD_BYTES  # Below Cloudflare's 100 MB proxied-body limit.


@app.get("/api/teams/{team_id}/inference")
async def team_inference(request: Request, team_id: str) -> JSONResponse:
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "GET",
        f"/v1/teams/{team_id}/inference",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.put("/api/teams/{team_id}/inference")
async def team_inference_configure(request: Request, team_id: str) -> JSONResponse:
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
        TEAMDRIVER_URL,
        "PUT",
        f"/v1/teams/{team_id}/inference",
        {"provider": provider, "model": model},
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.get("/api/teams/{team_id}/files")
async def team_files(request: Request, team_id: str) -> JSONResponse:
    """List opaque file metadata; file bytes and host paths remain controller-private."""
    token, _, _ = await _authed_account_bounded(request)
    if not token:
        return _private_json({"detail": "not authenticated"}, 401)
    team_id = _canonical_team_id(team_id)
    if team_id is None:
        return _private_json({"detail": "bad team id"}, 400)
    status, body = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "GET",
        f"/v1/teams/{team_id}/files",
        extra={"X-Shimpz-Account": token},
    )
    if status != 200:
        return _private_json(body, status)
    inventory = _public_file_inventory(body, team_id)
    if inventory is None:
        log.warning("team_file_inventory_invalid", team_id=team_id)
        return _private_json({"detail": "invalid Team storage inventory"}, 502)
    return _private_json(inventory)


@app.post("/api/teams/{team_id}/files")
async def team_file_upload(request: Request, team_id: str, file: UploadFile) -> JSONResponse:
    """Upload one opaque Team object without granting a Brain or Assistant filesystem access."""
    token, account_id, _ = await _authed_account_bounded(request)
    try:
        if not token:
            raise ClientPayloadError(401, "not authenticated")
        if not _assistant_mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        team_id = _canonical_team_id(team_id)
        if team_id is None:
            raise ClientPayloadError(400, "bad team id")
    except ClientPayloadError as exc:
        return _private_json({"detail": exc.detail}, exc.status)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return _private_json(
            {"detail": f"file too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)"},
            413,
        )
    filename = team_driver_contract.canonical_filename(file.filename or "upload.bin")
    media_type = team_driver_contract.canonical_media_type(file.content_type)
    if filename is None or media_type is None:
        return _private_json({"detail": "invalid file metadata"}, 400)
    payload = {
        "filename": filename,
        "media_type": media_type,
        "content_b64": base64.b64encode(data).decode(),
    }
    status, body = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "POST",
        f"/v1/teams/{team_id}/files",
        payload,
        extra={"X-Shimpz-Account": token},
    )
    log.info(
        "team_file_upload",
        account=account_id,
        team_id=team_id,
        bytes=len(data),
        status=status,
    )
    if status != 200:
        return _private_json(body, status)
    uploaded = _public_file_upload(body, team_id)
    if uploaded is None:
        log.warning("team_file_upload_invalid", team_id=team_id)
        return _private_json({"detail": "invalid Team storage response"}, 502)
    return _private_json(uploaded)


@app.delete("/api/teams/{team_id}/files/{file_id}")
async def team_file_delete(request: Request, team_id: str, file_id: str) -> JSONResponse:
    token, account_id, _ = await _authed_account_bounded(request)
    try:
        if not token:
            raise ClientPayloadError(401, "not authenticated")
        if not _assistant_mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        team_id = _canonical_team_id(team_id)
        opaque_id = _canonical_team_file_id(file_id)
        if team_id is None:
            raise ClientPayloadError(400, "bad team id")
        if opaque_id is None:
            raise ClientPayloadError(404, "file not found")
    except ClientPayloadError as exc:
        return _private_json({"detail": exc.detail}, exc.status)
    status, body = await _bounded_call(
        _CONTROL_EXECUTOR,
        TEAMDRIVER_URL,
        "DELETE",
        f"/v1/teams/{team_id}/files/{opaque_id}",
        extra={"X-Shimpz-Account": token},
    )
    log.info(
        "team_file_delete",
        account=account_id,
        team_id=team_id,
        file_id=opaque_id,
        status=status,
    )
    if status != 200:
        return _private_json(body, status)
    deleted = _public_file_deletion(body, team_id, opaque_id)
    if deleted is None:
        log.warning("team_file_delete_invalid", team_id=team_id, file_id=opaque_id)
        return _private_json({"detail": "invalid Team storage response"}, 502)
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
        raise WebSocketPayloadError(415, "WebSocket frame must be text JSON", 1003)
    if len(raw.encode()) > MAX_WS_FRAME_BYTES:
        raise WebSocketPayloadError(413, "WebSocket frame too large", 1009)
    try:
        payload = jsonlib.loads(raw, object_pairs_hook=_unique_json_object)
    except (jsonlib.JSONDecodeError, ValueError) as exc:
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


def _validated_done_event(value: dict, expected_team_id: str) -> dict | None:
    if set(value) != {"type", "team_id", "team_name", "reply"}:
        return None
    team_id = _canonical_team_id(value["team_id"])
    reply = _canonical_chat_reply(value["reply"])
    team_name = _canonical_team_name(value["team_name"])
    if team_id is None or team_id != expected_team_id or reply is None or team_name is None:
        return None
    return {
        "type": "done",
        "team_id": team_id,
        "team_name": team_name,
        "reply": reply,
    }


def _public_chat_error_event(status: int) -> dict:
    safe_status = status if isinstance(status, int) and not isinstance(status, bool) and 400 <= status <= 599 else 502
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
    return _public_chat_error_event(status)


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
    team_id = _canonical_team_id(value["team_id"])
    if (
        value["type"] != "input-required"
        or value["status"] != "input-required"
        or team_id != expected_team_id
        or not isinstance(challenge_id, str)
        or _CHALLENGE_ID_RE.fullmatch(challenge_id) is None
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
        or request_type not in _HUMAN_REQUEST_TYPES
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
    team_id = _canonical_team_id(value["team_id"])
    if (
        value["type"] != "approval-required"
        or value["status"] != "approval-required"
        or team_id != expected_team_id
        or not isinstance(challenge_id, str)
        or _CHALLENGE_ID_RE.fullmatch(challenge_id) is None
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
    assistant_id = _canonical_assistant_id(requirement["assistant_id"])
    power_id = _canonical_assistant_id(requirement["power_id"])
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


def _validated_terminal_event(value: object, expected_team_id: str) -> dict | None:
    """Project an untrusted controller value onto the only browser-visible chat events."""
    if not isinstance(value, dict):
        return None
    # Store accounts are connected through the OAuth routes before chat; accounts-required is
    # intentionally not a browser-visible terminal event.
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


def _parsed_stream_event(line: bytes, expected_team_id: str) -> dict | None:
    if not line.strip():
        return None
    try:
        event = jsonlib.loads(line, object_pairs_hook=_unique_json_object)
    except jsonlib.JSONDecodeError, UnicodeDecodeError, ValueError:
        return None
    return _validated_terminal_event(event, expected_team_id)


def _upstream_error_event(status: int) -> dict:
    return _public_chat_error_event(status)


class _StreamLimitError(ValueError):
    """The team-driver stream exceeded a bounded relay contract."""


class _StreamProtocolError(ValueError):
    """The team-driver stream violated its typed NDJSON contract."""


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
    expected_team_id: str,
) -> None:
    """Release exactly one validated terminal event after the controller closes its response."""
    terminal_event = None
    try:
        for line in _bounded_upstream_lines(resp):
            if not line.strip():
                continue
            event = _parsed_stream_event(line, expected_team_id)
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
    team_id: str
    text: str
    headers: dict
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop
    started: asyncio.Event
    files: tuple[str, ...] = ()
    assistant_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ChallengeRelay:
    team_id: str
    kind: str
    body: dict
    headers: dict
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop
    started: asyncio.Event


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


def _stream_lines(relay: _StreamRelay) -> None:
    """BLOCKING (run in a thread): relay the driver's NDJSON into a bounded asyncio queue."""
    parsed = urlparse(TEAMDRIVER_URL)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=200)
    try:
        payload: dict[str, object] = {
            "message": relay.text,
            "files": list(relay.files),
            "assistant_ids": list(relay.assistant_ids),
        }
        body = jsonlib.dumps(payload, ensure_ascii=False).encode()
        conn.request(
            "POST",
            f"/v1/teams/{relay.team_id}/chat/stream",
            body,
            {**relay.headers, "Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        relay.loop.call_soon_threadsafe(relay.started.set)
        if not 200 <= resp.status < 300:
            _stream_queue_put(
                relay.queue,
                relay.loop,
                _upstream_error_event(resp.status),
            )
            return
        _relay_upstream_events(resp, relay.queue, relay.loop, relay.team_id)
    except (OSError, http.client.HTTPException) as exc:
        log.warning("chat_stream_failed", team_id=relay.team_id, error=type(exc).__name__)
        _stream_queue_put(
            relay.queue,
            relay.loop,
            {
                "type": "error",
                "status": 502,
                "detail": "team-driver stream failed",
                "_relay_abort": True,
            },
        )
    finally:
        relay.loop.call_soon_threadsafe(relay.started.set)
        conn.close()
        _stream_queue_put(relay.queue, relay.loop, None)


def _challenge_response_event(status: int, data: object, team_id: str) -> dict:
    projected = None
    if isinstance(data, dict) and status in {
        HTTPStatus.OK,
        HTTPStatus.PRECONDITION_REQUIRED,
    }:
        challenge_status = data.get("status")
        if challenge_status in {"input-required", "approval-required"}:
            projected = {"type": challenge_status, **data}
        elif status == HTTPStatus.OK:
            projected = {"type": "done", **data}
    terminal = _validated_terminal_event(projected, team_id)
    if terminal is not None:
        return terminal
    if 400 <= status <= 599:
        return _public_chat_error_event(status)
    return {
        "type": "error",
        "status": 502,
        "detail": TERMINAL_CONTRACT_ERROR,
        "_relay_abort": True,
    }


def _relay_challenge(relay: _ChallengeRelay) -> None:
    relay.loop.call_soon_threadsafe(relay.started.set)
    try:
        status, data = _call(
            TEAMDRIVER_URL,
            "POST",
            f"/v1/teams/{relay.team_id}/chat/{relay.kind}",
            relay.body,
            relay.headers,
        )
        _stream_queue_put(
            relay.queue,
            relay.loop,
            _challenge_response_event(status, data, relay.team_id),
        )
    finally:
        _stream_queue_put(relay.queue, relay.loop, None)


async def _driver_stop(team_id: str, hdr: dict) -> tuple[int, dict]:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            _STOP_EXECUTOR,
            _call,
            TEAMDRIVER_URL,
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
    if not _ws_origin_allowed(origin):
        log.warning("ws_origin_denied", origin=origin or "<missing>")
        await ws.close(code=4403)
        return False
    if tuple(ws.scope.get("subprotocols", ())) != (CHAT_WS_SUBPROTOCOL,):
        log.warning("ws_subprotocol_denied")
        await ws.close(code=4406)
        return False
    return True


@app.websocket("/api/teams/{team_id}/chat/ws")
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


app.include_router(account.router)
app.include_router(oauth.router)
app.include_router(public.router)
app.include_router(static.router)

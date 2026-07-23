"""Released cloud Assistant lifecycle routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import authn, config, team_driver_contract
from app.access import mutation_origin_allowed, private_json
from app.config import MAX_TEAM_INSTALL_BODY_BYTES, RELEASED_CLOUD_ASSISTANTS
from app.control import EXECUTOR as CONTROL_EXECUTOR
from app.payloads import ClientPayloadError, read_bounded_json
from app.projections import released_assistant_inventory, released_running_assistant_inventory
from app.upstream import call_bounded

log = structlog.get_logger()
router = APIRouter()


async def _assistant_inventory(
    request: Request,
    team_id: str,
    projector,
    response_key: str,
    invalid_detail: str,
    invalid_event: str,
) -> JSONResponse:
    token, _, _ = await authn.authed_account_bounded(request)
    if not token:
        return private_json({"detail": "not authenticated"}, 401)
    team_id = team_driver_contract.canonical_team_id(team_id)
    if team_id is None:
        return private_json({"detail": "bad team id"}, 400)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "GET",
        f"/v1/teams/{team_id}/apps",
        extra={"X-Shimpz-Account": token},
    )
    if status != 200:
        return private_json(data, status)
    projected = projector(data)
    if projected is None:
        log.warning(invalid_event, team_id=team_id)
        return private_json({"detail": invalid_detail}, 502)
    return private_json({response_key: projected})


@router.get("/api/teams/{team_id}/assistants")
async def cloud_assistants_list(request: Request, team_id: str) -> JSONResponse:
    return await _assistant_inventory(
        request,
        team_id,
        released_assistant_inventory,
        "installed",
        "invalid Assistant inventory",
        "assistant_inventory_invalid",
    )


@router.get("/api/teams/{team_id}/chat/assistants")
async def team_chat_assistants(request: Request, team_id: str) -> JSONResponse:
    """Return the verified default Assistant scope without exposing runtime metadata."""
    return await _assistant_inventory(
        request,
        team_id,
        released_running_assistant_inventory,
        "assistant_ids",
        "invalid chat Assistant inventory",
        "chat_assistant_inventory_invalid",
    )


@router.post("/api/teams/{team_id}/assistants")
async def cloud_assistant_install(request: Request, team_id: str) -> JSONResponse:
    token, account_id, _ = await authn.authed_account_bounded(request)
    if not token:
        return private_json({"detail": "not authenticated"}, 401)
    try:
        if not mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        if request.headers.get("content-type", "").strip().lower() != "application/json":
            raise ClientPayloadError(415, "Content-Type must be application/json")
        team_id = team_driver_contract.canonical_team_id(team_id)
        if team_id is None:
            raise ClientPayloadError(400, "bad team id")
        payload = await read_bounded_json(request, MAX_TEAM_INSTALL_BODY_BYTES)
        if set(payload) != {"assistant"}:
            raise ClientPayloadError(400, "body must contain only assistant")
        assistant = team_driver_contract.canonical_assistant_id(payload["assistant"])
        if assistant not in RELEASED_CLOUD_ASSISTANTS:
            raise ClientPayloadError(404, "Assistant is not released")
    except ClientPayloadError as exc:
        return private_json({"detail": exc.detail}, exc.status)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
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
        return private_json(data, status)
    return private_json({"assistant": assistant, "accepted": True})


@router.delete("/api/teams/{team_id}/assistants/{assistant}")
async def cloud_assistant_uninstall(request: Request, team_id: str, assistant: str) -> JSONResponse:
    token, account_id, _ = await authn.authed_account_bounded(request)
    if not token:
        return private_json({"detail": "not authenticated"}, 401)
    try:
        if not mutation_origin_allowed(request.headers.get("origin")):
            raise ClientPayloadError(403, "forbidden origin")
        team_id = team_driver_contract.canonical_team_id(team_id)
        assistant_id = team_driver_contract.canonical_assistant_id(assistant)
        if team_id is None:
            raise ClientPayloadError(400, "bad team id")
        if assistant_id is None:
            raise ClientPayloadError(400, "bad Assistant id")
        if assistant_id not in RELEASED_CLOUD_ASSISTANTS:
            raise ClientPayloadError(404, "Assistant is not released")
    except ClientPayloadError as exc:
        return private_json({"detail": exc.detail}, exc.status)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
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
        return private_json(data, status)
    return private_json({"assistant": assistant_id, "accepted": True})

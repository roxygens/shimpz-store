"""Released cloud Assistant lifecycle routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import authn, config, team_driver_contract
from app.access import private_json
from app.config import RELEASED_CLOUD_ASSISTANTS
from app.control import EXECUTOR as CONTROL_EXECUTOR
from app.projections import released_assistant_inventory, released_running_assistant_inventory
from app.routers import app_lifecycle
from app.upstream import CONTROL_PLANE_TIMEOUT_SECONDS, call_bounded

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
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
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
    result = await app_lifecycle.install(
        request,
        team_id,
        "assistant",
        released=RELEASED_CLOUD_ASSISTANTS,
    )
    log.info(
        "assistant_install",
        account=result.account_id,
        team_id=result.team_id,
        assistant=result.app_id,
        status=result.status,
    )
    if not 200 <= result.status < 300:
        return private_json(result.data, result.status)
    return private_json({"assistant": result.app_id, "accepted": True})


@router.delete("/api/teams/{team_id}/assistants/{assistant}")
async def cloud_assistant_uninstall(request: Request, team_id: str, assistant: str) -> JSONResponse:
    result = await app_lifecycle.uninstall(
        request,
        team_id,
        assistant,
        released=RELEASED_CLOUD_ASSISTANTS,
    )
    log.info(
        "assistant_uninstall",
        account=result.account_id,
        team_id=result.team_id,
        assistant=result.app_id,
        status=result.status,
    )
    if not 200 <= result.status < 300:
        return private_json(result.data, result.status)
    return private_json({"assistant": result.app_id, "accepted": True})

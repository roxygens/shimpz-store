"""Legacy Team App control routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import authn, config
from app.access import private_json
from app.control import EXECUTOR as CONTROL_EXECUTOR
from app.routers import app_lifecycle
from app.upstream import CONTROL_PLANE_TIMEOUT_SECONDS, call_bounded

log = structlog.get_logger()
router = APIRouter()


@router.post("/api/teams/{team_id}/install")
async def team_install(request: Request, team_id: str) -> JSONResponse:
    """Install one trusted internal-registry App into an owned Team."""
    result = await app_lifecycle.install(request, team_id, "app")
    log.info(
        "app_install",
        account=result.account_id,
        team_id=result.team_id,
        app=result.app_id,
        status=result.status,
        installed=result.data.get("installed"),
    )
    return private_json(result.data, result.status)


@router.get("/api/teams/{team_id}/apps")
async def team_apps(request: Request, team_id: str) -> JSONResponse:
    token, _, _ = await authn.authed_account_bounded(request)
    if not token:
        return private_json({"detail": "not authenticated"}, 401)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "GET",
        f"/v1/teams/{team_id}/apps",
        extra={"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    return private_json(data, status)


@router.delete("/api/teams/{team_id}/apps/{app_id}")
async def team_uninstall(request: Request, team_id: str, app_id: str) -> JSONResponse:
    result = await app_lifecycle.uninstall(request, team_id, app_id)
    log.info(
        "app_uninstall",
        account=result.account_id,
        team_id=result.team_id,
        app=result.app_id,
        status=result.status,
    )
    return private_json(result.data, result.status)

"""Legacy Team App control routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import authn, config, team_driver_contract
from app.access import mutation_origin_allowed, private_json
from app.config import MAX_TEAM_INSTALL_BODY_BYTES
from app.control import EXECUTOR as CONTROL_EXECUTOR
from app.payloads import ClientPayloadError, read_bounded_json
from app.upstream import call_bounded

log = structlog.get_logger()
router = APIRouter()


@router.post("/api/teams/{team_id}/install")
async def team_install(request: Request, team_id: str) -> JSONResponse:
    """Install one trusted internal-registry App into an owned Team."""
    token, account_id, _ = await authn.authed_account_bounded(request)
    if not token:
        return private_json({"detail": "not authenticated"}, 401)
    if not mutation_origin_allowed(request.headers.get("origin")):
        raise ClientPayloadError(403, "forbidden origin")
    if request.headers.get("content-type", "").strip().lower() != "application/json":
        raise ClientPayloadError(415, "Content-Type must be application/json")
    team_id = team_driver_contract.canonical_team_id(team_id)
    if team_id is None:
        raise ClientPayloadError(400, "bad team id")
    payload = await read_bounded_json(request, MAX_TEAM_INSTALL_BODY_BYTES)
    if set(payload) != {"app"}:
        raise ClientPayloadError(400, "body must contain only app")
    app_id = team_driver_contract.canonical_assistant_id(payload["app"])
    if app_id is None:
        raise ClientPayloadError(400, "bad app id")
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
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
    return private_json(data, status)


@router.get("/api/teams/{team_id}/apps")
async def team_apps(request: Request, team_id: str) -> JSONResponse:
    token, _, _ = await authn.authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "GET",
        f"/v1/teams/{team_id}/apps",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@router.delete("/api/teams/{team_id}/apps/{app_id}")
async def team_uninstall(request: Request, team_id: str, app_id: str) -> JSONResponse:
    token, account_id, _ = await authn.authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "DELETE",
        f"/v1/teams/{team_id}/apps/{app_id}",
        extra={"X-Shimpz-Account": token},
    )
    log.info("app_uninstall", account=account_id, team_id=team_id, app=app_id, status=status)
    return JSONResponse(data, status_code=status)

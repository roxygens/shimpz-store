"""Core Team identity and lifecycle routes."""

from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import authn, config
from app.config import MAX_TEAM_CREATE_BODY_BYTES
from app.control import EXECUTOR as CONTROL_EXECUTOR
from app.inference import model as canonical_model
from app.inference import provider as canonical_provider
from app.payloads import ClientPayloadError, read_bounded_json
from app.upstream import CONTROL_PLANE_TIMEOUT_SECONDS, call_bounded

router = APIRouter()


def team_id_for(account_id: str, team_name: str) -> str:
    """Derive a collision-resistant, Docker/PG-safe ID from the complete identity pair."""
    normalized = re.sub(r"[^a-z0-9_]+", "_", team_name.lower()).strip("_")
    if not normalized:
        return ""
    digest = hashlib.sha256(f"{account_id}\0{normalized}".encode()).hexdigest()[:24]
    return f"{digest}_{normalized[:15]}".rstrip("_")


def _create_payload(payload: dict, account_id: str) -> tuple[str, dict[str, str]]:
    if set(payload) != {"team_name", "provider", "model"}:
        raise ClientPayloadError(400, "Team requires team_name, provider, and model")
    team_name = str(payload.get("team_name", "")).strip()
    provider = canonical_provider(payload.get("provider"))
    model = canonical_model(provider, payload.get("model")) if provider is not None else None
    team_id = team_id_for(account_id, team_name)
    if not team_name or not team_id.strip("_"):
        raise ClientPayloadError(400, "bad team name")
    if provider is None:
        raise ClientPayloadError(400, "unsupported model provider")
    if model is None:
        raise ClientPayloadError(400, "unsupported model for provider")
    return team_id, {"team_name": team_name, "provider": provider, "model": model}


@router.get("/api/teams")
async def teams_list(request: Request) -> JSONResponse:
    token, _, _ = await authn.authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "GET",
        "/v1/teams",
        extra={"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    return JSONResponse(data, status_code=status)


@router.post("/api/teams")
async def teams_create(request: Request) -> JSONResponse:
    token, account_id, _ = await authn.authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    payload = await read_bounded_json(request, MAX_TEAM_CREATE_BODY_BYTES)
    team_id, create_payload = _create_payload(payload, account_id)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "POST",
        f"/v1/teams/{team_id}/create",
        create_payload,
        {"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    return JSONResponse(data, status_code=status)


@router.delete("/api/teams/{team_id}")
async def teams_destroy(request: Request, team_id: str) -> JSONResponse:
    token, _, _ = await authn.authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "DELETE",
        f"/v1/teams/{team_id}",
        extra={"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    return JSONResponse(data, status_code=status)

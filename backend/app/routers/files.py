"""Opaque Team file routes."""

from __future__ import annotations

import base64

import structlog
from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import JSONResponse

from app import authn, config, team_driver_contract
from app.access import mutation_origin_allowed, private_json
from app.control import EXECUTOR as CONTROL_EXECUTOR
from app.payloads import ClientPayloadError
from app.projections import public_file_deletion, public_file_inventory, public_file_upload
from app.upstream import CONTROL_PLANE_TIMEOUT_SECONDS, call_bounded

log = structlog.get_logger()
router = APIRouter()

MAX_UPLOAD_BYTES = team_driver_contract.MAX_FILE_UPLOAD_BYTES


@router.get("/api/teams/{team_id}/files")
async def team_files(request: Request, team_id: str) -> JSONResponse:
    """List opaque file metadata; file bytes and host paths remain controller-private."""
    token, _, _ = await authn.authed_account_bounded(request)
    if not token:
        return private_json({"detail": "not authenticated"}, 401)
    team_id = team_driver_contract.canonical_team_id(team_id)
    if team_id is None:
        return private_json({"detail": "bad team id"}, 400)
    status, body = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "GET",
        f"/v1/teams/{team_id}/files",
        extra={"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    if status != 200:
        return private_json(body, status)
    inventory = public_file_inventory(body, team_id)
    if inventory is None:
        log.warning("team_file_inventory_invalid", team_id=team_id)
        return private_json({"detail": "invalid Team storage inventory"}, 502)
    return private_json(inventory)


@router.post("/api/teams/{team_id}/files")
async def team_file_upload(request: Request, team_id: str, file: UploadFile) -> JSONResponse:
    """Upload one opaque Team object without granting a Brain or Assistant filesystem access."""
    token, account_id, _ = await authn.authed_account_bounded(request)
    if not token:
        raise ClientPayloadError(401, "not authenticated")
    if not mutation_origin_allowed(request.headers.get("origin")):
        raise ClientPayloadError(403, "forbidden origin")
    team_id = team_driver_contract.canonical_team_id(team_id)
    if team_id is None:
        raise ClientPayloadError(400, "bad team id")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return private_json(
            {"detail": f"file too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)"},
            413,
        )
    filename = team_driver_contract.canonical_filename(file.filename or "upload.bin")
    media_type = team_driver_contract.canonical_media_type(file.content_type)
    if filename is None or media_type is None:
        return private_json({"detail": "invalid file metadata"}, 400)
    payload = {
        "filename": filename,
        "media_type": media_type,
        "content_b64": base64.b64encode(data).decode(),
    }
    status, body = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "POST",
        f"/v1/teams/{team_id}/files",
        payload,
        extra={"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    log.info(
        "team_file_upload",
        account=account_id,
        team_id=team_id,
        bytes=len(data),
        status=status,
    )
    if status != 200:
        return private_json(body, status)
    uploaded = public_file_upload(body, team_id)
    if uploaded is None:
        log.warning("team_file_upload_invalid", team_id=team_id)
        return private_json({"detail": "invalid Team storage response"}, 502)
    return private_json(uploaded)


@router.delete("/api/teams/{team_id}/files/{file_id}")
async def team_file_delete(request: Request, team_id: str, file_id: str) -> JSONResponse:
    token, account_id, _ = await authn.authed_account_bounded(request)
    if not token:
        raise ClientPayloadError(401, "not authenticated")
    if not mutation_origin_allowed(request.headers.get("origin")):
        raise ClientPayloadError(403, "forbidden origin")
    team_id = team_driver_contract.canonical_team_id(team_id)
    opaque_id = team_driver_contract.canonical_file_id(file_id)
    if team_id is None:
        raise ClientPayloadError(400, "bad team id")
    if opaque_id is None:
        raise ClientPayloadError(404, "file not found")
    status, body = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "DELETE",
        f"/v1/teams/{team_id}/files/{opaque_id}",
        extra={"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    log.info(
        "team_file_delete",
        account=account_id,
        team_id=team_id,
        file_id=opaque_id,
        status=status,
    )
    if status != 200:
        return private_json(body, status)
    deleted = public_file_deletion(body, team_id, opaque_id)
    if deleted is None:
        log.warning("team_file_delete_invalid", team_id=team_id, file_id=opaque_id)
        return private_json({"detail": "invalid Team storage response"}, 502)
    return private_json(deleted)

"""Shared authenticated Team App mutation boundary."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app import authn, config, team_driver_contract
from app.access import mutation_origin_allowed
from app.config import MAX_TEAM_INSTALL_BODY_BYTES
from app.control import EXECUTOR as CONTROL_EXECUTOR
from app.payloads import ClientPayloadError, read_bounded_json
from app.upstream import CONTROL_PLANE_TIMEOUT_SECONDS, call_bounded


@dataclass(frozen=True, slots=True)
class AppMutation:
    account_id: str
    team_id: str
    app_id: str
    status: int
    data: dict


def _canonical_ids(team_id: str, app_id: object, released: frozenset[str] | None) -> tuple[str, str]:
    canonical_team = team_driver_contract.canonical_team_id(team_id)
    canonical_app = team_driver_contract.canonical_assistant_id(app_id)
    if canonical_team is None:
        raise ClientPayloadError(400, "bad team id")
    if canonical_app is None:
        raise ClientPayloadError(400, "bad app id")
    if released is not None and canonical_app not in released:
        raise ClientPayloadError(404, "Assistant is not released")
    return canonical_team, canonical_app


async def install(
    request: Request,
    team_id: str,
    body_key: str,
    *,
    released: frozenset[str] | None = None,
) -> AppMutation:
    token, account_id, _ = await authn.authed_account_bounded(request)
    if not token:
        raise ClientPayloadError(401, "not authenticated")
    if not mutation_origin_allowed(request.headers.get("origin")):
        raise ClientPayloadError(403, "forbidden origin")
    if request.headers.get("content-type", "").strip().lower() != "application/json":
        raise ClientPayloadError(415, "Content-Type must be application/json")
    payload = await read_bounded_json(request, MAX_TEAM_INSTALL_BODY_BYTES)
    if set(payload) != {body_key}:
        raise ClientPayloadError(400, f"body must contain only {body_key}")
    canonical_team, app_id = _canonical_ids(team_id, payload[body_key], released)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "POST",
        f"/v1/teams/{canonical_team}/apps",
        {"app": app_id},
        {"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    return AppMutation(account_id, canonical_team, app_id, status, data)


async def uninstall(
    request: Request,
    team_id: str,
    app_id: str,
    *,
    released: frozenset[str] | None = None,
) -> AppMutation:
    token, account_id, _ = await authn.authed_account_bounded(request)
    if not token:
        raise ClientPayloadError(401, "not authenticated")
    if not mutation_origin_allowed(request.headers.get("origin")):
        raise ClientPayloadError(403, "forbidden origin")
    canonical_team, canonical_app = _canonical_ids(team_id, app_id, released)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "DELETE",
        f"/v1/teams/{canonical_team}/apps/{canonical_app}",
        extra={"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    return AppMutation(account_id, canonical_team, canonical_app, status, data)

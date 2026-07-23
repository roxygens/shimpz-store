"""Public account authentication routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import authn
from app.config import ACCOUNT_COOKIE, MAX_AUTH_BODY_BYTES
from app.payloads import ClientPayloadError, read_bounded_json
from app.upstream import call_bounded

log = structlog.get_logger()
router = APIRouter()


async def _bounded_call(*args, **kwargs) -> tuple[int, dict]:
    return await call_bounded(authn.EXECUTOR, *args, **kwargs)


async def _credential_route(request: Request, path: str) -> JSONResponse:
    try:
        payload = await read_bounded_json(request, MAX_AUTH_BODY_BYTES)
    except ClientPayloadError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)
    status, data = await _bounded_call(
        authn.ACCOUNTS_URL,
        "POST",
        path,
        {"username": payload.get("username"), "password": payload.get("password")},
        extra={"X-Forwarded-For": authn.client_ip(request)},
    )
    body = {"account_id": data.get("account_id"), "username": data.get("username")} if status == 200 else data
    response = JSONResponse(body, status_code=status)
    if status == 200 and data.get("token"):
        authn.set_cookie(response, data["token"])
        if path == "/v1/signup":
            log.info("signup", username=data.get("username"))
    return response


@router.post("/api/signup")
async def signup(request: Request) -> JSONResponse:
    return await _credential_route(request, "/v1/signup")


@router.post("/api/login")
async def login(request: Request) -> JSONResponse:
    return await _credential_route(request, "/v1/login")


@router.post("/api/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(ACCOUNT_COOKIE, path="/")
    return response


@router.get("/api/me")
async def me(request: Request) -> JSONResponse:
    _, account_id, username = await authn.authed_account_bounded(request)
    return JSONResponse(
        {
            "authenticated": bool(account_id),
            "account_id": account_id or None,
            "username": username or None,
        }
    )

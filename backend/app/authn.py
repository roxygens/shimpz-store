"""Bounded account-session verification shared by Store routers."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.concurrency import BoundedThreadPoolExecutor
from app.concurrency import run_bounded as run_with_executor
from app.config import (
    ACCOUNT_COOKIE,
    ACCOUNTS_URL,
    AUTH_QUEUE_MAX,
    AUTH_WORKER_THREADS,
    COOKIE_MAX_AGE,
)
from app.upstream import VERIFY_TIMEOUT_SECONDS, call

EXECUTOR = BoundedThreadPoolExecutor(
    max_workers=AUTH_WORKER_THREADS,
    max_outstanding=AUTH_WORKER_THREADS + AUTH_QUEUE_MAX,
    thread_name_prefix="shimpz-auth",
)


async def run_bounded(fn, /, *args):
    return await run_with_executor(EXECUTOR, fn, *args)


def set_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        ACCOUNT_COOKIE,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=True,
        path="/",
    )


def authed_account(request: Request) -> tuple[str, str, str]:
    """Return the verified token/account/username tuple, or three empty strings."""
    token = request.cookies.get(ACCOUNT_COOKIE, "")
    if not token:
        return "", "", ""
    status, data = call(
        ACCOUNTS_URL,
        "POST",
        "/v1/verify",
        {"token": token},
        timeout=VERIFY_TIMEOUT_SECONDS,
    )
    if status == 200 and data.get("account_id"):
        return token, data["account_id"], data.get("username", "")
    return "", "", ""


async def authed_account_bounded(request: Request) -> tuple[str, str, str]:
    return await run_bounded(authed_account, request)


def client_ip(request: Request) -> str:
    """Return Cloudflare's client IP when present, otherwise the socket peer."""
    return request.headers.get("cf-connecting-ip", "") or (request.client.host if request.client else "")

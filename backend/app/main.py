"""Serve the Shimpz public console and account-authenticated control surface."""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.access import private_json
from app.chat import ws as chat_ws
from app.concurrency import ExecutorSaturatedError as _ExecutorSaturatedError
from app.config import ACCOUNT_COOKIE as ACCOUNT_COOKIE
from app.logconf import setup
from app.middleware import TraceIdMiddleware
from app.payloads import ClientPayloadError
from app.routers import account, apps, assistants, brains, files, inference, oauth, public, static, teams

setup("shimpz-store")
log = structlog.get_logger()

app = FastAPI(title="shimpz-store", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TraceIdMiddleware)


@app.exception_handler(ClientPayloadError)
async def client_payload_error(_request: Request, exc: ClientPayloadError) -> JSONResponse:
    return private_json({"detail": exc.detail}, exc.status)


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


app.include_router(account.router)
app.include_router(apps.router)
app.include_router(assistants.router)
app.include_router(brains.router)
app.include_router(files.router)
app.include_router(inference.router)
app.include_router(oauth.router)
app.include_router(public.router)
app.include_router(teams.router)
app.include_router(chat_ws.router)
app.include_router(static.router)

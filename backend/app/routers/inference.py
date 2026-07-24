"""Team model-selection routes."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import authn, config
from app.config import MAX_INFERENCE_BODY_BYTES
from app.control import EXECUTOR as CONTROL_EXECUTOR
from app.inference import model as canonical_model
from app.inference import provider as canonical_provider
from app.payloads import read_bounded_json
from app.upstream import CONTROL_PLANE_TIMEOUT_SECONDS, call_bounded

router = APIRouter()


@router.get("/api/teams/{team_id}/inference")
async def team_inference(request: Request, team_id: str) -> JSONResponse:
    token, _, _ = await authn.authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "GET",
        f"/v1/teams/{team_id}/inference",
        extra={"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    return JSONResponse(data, status_code=status)


@router.put("/api/teams/{team_id}/inference")
async def team_inference_configure(request: Request, team_id: str) -> JSONResponse:
    token, _, _ = await authn.authed_account_bounded(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    payload = await read_bounded_json(request, MAX_INFERENCE_BODY_BYTES)
    if set(payload) != {"provider", "model"}:
        return JSONResponse({"detail": "inference requires provider and model"}, status_code=400)
    provider = canonical_provider(payload.get("provider"))
    model = canonical_model(provider, payload.get("model")) if provider is not None else None
    if provider is None:
        return JSONResponse({"detail": "unsupported model provider"}, status_code=400)
    if model is None:
        return JSONResponse({"detail": "unsupported model for provider"}, status_code=400)
    status, data = await call_bounded(
        CONTROL_EXECUTOR,
        config.TEAMDRIVER_URL,
        "PUT",
        f"/v1/teams/{team_id}/inference",
        {"provider": provider, "model": model},
        extra={"X-Shimpz-Account": token},
        timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
    )
    return JSONResponse(data, status_code=status)

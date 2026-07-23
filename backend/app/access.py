"""Browser mutation and private-response policy for authenticated Store routes."""

from fastapi.responses import JSONResponse

from app.config import (
    ASSISTANT_MUTATION_ALLOWED_ORIGINS,
    PRIVATE_NO_STORE_HEADERS,
    canonical_origin,
)


def mutation_origin_allowed(origin: str | None) -> bool:
    canonical = canonical_origin(origin)
    return canonical is not None and canonical in ASSISTANT_MUTATION_ALLOWED_ORIGINS


def private_json(content: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content, status_code=status_code, headers=PRIVATE_NO_STORE_HEADERS)

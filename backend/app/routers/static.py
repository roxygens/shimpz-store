"""Prerendered SvelteKit files registered after every API and WebSocket route."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, PlainTextResponse, Response

from app.config import BUILD, HTML_CACHE_CONTROL, IMMUTABLE_CACHE_CONTROL

router = APIRouter()


def resolve(rel: str) -> Path | None:
    rel = rel.strip("/")
    if ".." in rel.split("/"):
        return None
    for candidate in (BUILD / rel, BUILD / f"{rel}.html", BUILD / rel / "index.html"):
        if candidate.is_file():
            return candidate
    return None


def cache_control(path: str, hit: Path) -> str:
    """Revalidate navigations while retaining SvelteKit's content-addressed asset cache."""
    rel = path.strip("/")
    if hit.suffix.lower() not in {".html", ".htm"} and rel.startswith("_app/immutable/"):
        return IMMUTABLE_CACHE_CONTROL
    return HTML_CACHE_CONTROL


@router.get("/{path:path}")
def static_files(path: str) -> Response:
    hit = resolve(path)
    if hit:
        return FileResponse(hit, headers={"Cache-Control": cache_control(path, hit)})
    return PlainTextResponse(
        "not found",
        status_code=404,
        headers={"Cache-Control": HTML_CACHE_CONTROL},
    )

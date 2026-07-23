"""Closed model-catalog validation shared by Store control-surface routers."""

from __future__ import annotations

from app.config import MODEL_CATALOG

PROVIDERS = frozenset(MODEL_CATALOG)


def provider(value: object) -> str | None:
    canonical = str(value or "").strip().lower()
    return canonical if canonical in PROVIDERS else None


def model(provider_name: str, value: object) -> str | None:
    canonical = str(value or "").strip()
    return canonical if canonical in MODEL_CATALOG[provider_name] else None

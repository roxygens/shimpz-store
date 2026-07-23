"""Closed browser-safe projections for Store controller responses."""

from __future__ import annotations

from app import team_driver_contract
from app.config import MAX_CHAT_ASSISTANTS, RELEASED_CLOUD_ASSISTANTS


def public_file_metadata(value: object) -> dict | None:
    """Copy only opaque, non-path file metadata from the trusted controller response."""
    return team_driver_contract.project_file_metadata(value, include_usage=False)


def public_file_upload(value: object, expected_team_id: str) -> dict | None:
    return team_driver_contract.project_storage_response(
        value,
        kind="upload",
        expected_team_id=expected_team_id,
        include_team_id=False,
    )


def public_file_inventory(value: object, expected_team_id: str) -> dict | None:
    return team_driver_contract.project_storage_response(
        value,
        kind="list",
        expected_team_id=expected_team_id,
        include_team_id=False,
    )


def public_file_deletion(value: object, expected_team_id: str, expected_id: str) -> dict | None:
    return team_driver_contract.project_storage_response(
        value,
        kind="delete",
        expected_team_id=expected_team_id,
        expected_file_id=expected_id,
        include_team_id=False,
    )


def released_assistant_inventory(data: object) -> list[str] | None:
    if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
        return None
    installed: list[str] = []
    for item in data["apps"]:
        if not isinstance(item, dict):
            return None
        assistant = item.get("app")
        if assistant in RELEASED_CLOUD_ASSISTANTS:
            if assistant in installed:
                return None
            installed.append(assistant)
    return installed


def released_running_assistant_inventory(data: object) -> list[str] | None:
    """Project only verified, runnable Assistants onto the browser chat scope."""
    if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
        return None
    running: list[str] = []
    seen: set[str] = set()
    for item in data["apps"]:
        if not isinstance(item, dict):
            return None
        assistant = item.get("app")
        if assistant not in RELEASED_CLOUD_ASSISTANTS:
            continue
        if assistant in seen:
            return None
        seen.add(assistant)
        status = item.get("status")
        if not isinstance(status, str):
            return None
        if status != "running":
            continue
        if len(running) >= MAX_CHAT_ASSISTANTS:
            return None
        running.append(assistant)
    return running

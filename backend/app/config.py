"""Environment-derived Store limits, endpoints, and public protocol constants."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from app import team_driver_contract

BUILD = Path(os.environ.get("SHIMPZ_STORE_BUILD", "/app/build"))
ACCOUNTS_URL = os.environ.get("SHIMPZ_ACCOUNTS_URL", "http://accounts:7079")
TEAMDRIVER_URL = os.environ.get("SHIMPZ_TEAMDRIVER_URL", "http://team-driver:7077")
BRAIN_FINALIZE_TOKEN_FILE = Path(
    os.environ.get(
        "SHIMPZ_ACCOUNTS_BRAIN_FINALIZE_TOKEN_FILE",
        "/run/shimpz-accounts-brain-finalize/token",
    )
)
ACCOUNT_COOKIE = "shimpz_account"
COOKIE_MAX_AGE = 7 * 24 * 3600
MAX_TEAM_CREATE_BODY_BYTES = max(
    1024,
    int(os.environ.get("SHIMPZ_STORE_MAX_TEAM_CREATE_BODY_BYTES", str(16 * 1024))),
)
MAX_INFERENCE_BODY_BYTES = max(
    1024,
    int(os.environ.get("SHIMPZ_STORE_MAX_INFERENCE_BODY_BYTES", str(4 * 1024))),
)
MAX_TEAM_INSTALL_BODY_BYTES = max(
    1024,
    int(os.environ.get("SHIMPZ_STORE_MAX_TEAM_INSTALL_BODY_BYTES", str(4 * 1024))),
)
MAX_AUTH_BODY_BYTES = max(1024, int(os.environ.get("SHIMPZ_STORE_MAX_AUTH_BODY_BYTES", str(16 * 1024))))
MAX_OAUTH_BODY_BYTES = 32 * 1024
MAX_WS_FRAME_BYTES = max(1024, int(os.environ.get("SHIMPZ_STORE_MAX_WS_FRAME_BYTES", str(128 * 1024))))
STREAM_QUEUE_MAX_EVENTS = max(1, int(os.environ.get("SHIMPZ_STORE_STREAM_QUEUE_MAX_EVENTS", "32")))
STREAM_QUEUE_PUT_TIMEOUT = max(1.0, float(os.environ.get("SHIMPZ_STORE_STREAM_QUEUE_PUT_TIMEOUT", "10")))
STREAM_WORKER_THREADS = max(1, int(os.environ.get("SHIMPZ_STORE_STREAM_WORKER_THREADS", "32")))
STREAM_TURN_QUEUE_MAX = max(0, int(os.environ.get("SHIMPZ_STORE_STREAM_TURN_QUEUE_MAX", "32")))
CONTROL_WORKER_THREADS = max(1, int(os.environ.get("SHIMPZ_STORE_CONTROL_WORKER_THREADS", "8")))
CONTROL_QUEUE_MAX = max(0, int(os.environ.get("SHIMPZ_STORE_CONTROL_QUEUE_MAX", "8")))
AUTH_WORKER_THREADS = max(1, int(os.environ.get("SHIMPZ_STORE_AUTH_WORKER_THREADS", "8")))
AUTH_QUEUE_MAX = max(0, int(os.environ.get("SHIMPZ_STORE_AUTH_QUEUE_MAX", "8")))
STOP_WORKER_THREADS = max(1, int(os.environ.get("SHIMPZ_STORE_STOP_WORKER_THREADS", "4")))
STOP_QUEUE_MAX = max(0, int(os.environ.get("SHIMPZ_STORE_STOP_QUEUE_MAX", "4")))
OAUTH_WORKER_THREADS = max(1, int(os.environ.get("SHIMPZ_STORE_OAUTH_WORKER_THREADS", "8")))
OAUTH_QUEUE_MAX = max(0, int(os.environ.get("SHIMPZ_STORE_OAUTH_QUEUE_MAX", "8")))
WS_GLOBAL_CONNECTION_LIMIT = max(1, int(os.environ.get("SHIMPZ_STORE_WS_GLOBAL_CONNECTION_LIMIT", "64")))
WS_ACCOUNT_CONNECTION_LIMIT = max(1, int(os.environ.get("SHIMPZ_STORE_WS_ACCOUNT_CONNECTION_LIMIT", "4")))
WS_TEAM_CONNECTION_LIMIT = max(1, int(os.environ.get("SHIMPZ_STORE_WS_TEAM_CONNECTION_LIMIT", "2")))
MAX_UPSTREAM_STREAM_LINE_BYTES = 256 * 1024
MAX_UPSTREAM_STREAM_BYTES = 2 * 1024 * 1024
HTML_CACHE_CONTROL = "no-cache, max-age=0, must-revalidate"
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


def canonical_origin(value: str | None) -> str | None:
    """Canonical exact WebSocket origin, preserving an explicitly supplied port."""
    if not value or value == "null":
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return None
    try:
        _ = parsed.port
    except ValueError:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def origin_allowed(value: str | None, allowed_origins: frozenset[str]) -> bool:
    canonical = canonical_origin(value)
    return canonical is not None and canonical in allowed_origins


WS_ALLOWED_ORIGINS = frozenset(
    origin
    for raw in os.environ.get("SHIMPZ_WS_ALLOWED_ORIGINS", "https://shimpz.com").split(",")
    if (origin := canonical_origin(raw.strip())) is not None
)
ASSISTANT_MUTATION_ALLOWED_ORIGINS = WS_ALLOWED_ORIGINS
MODEL_CATALOG = {
    provider["id"]: frozenset(model["id"] for model in provider["models"])
    for provider in json.loads(Path(__file__).with_name("model_catalog.json").read_text(encoding="utf-8"))["providers"]
}
RELEASED_CLOUD_ASSISTANTS = frozenset({"shimpz-cloudflare"})
PRIVATE_NO_STORE_HEADERS = {"Cache-Control": "private, no-store"}
MAX_CHAT_MESSAGE_CHARS = team_driver_contract.MAX_CHAT_MESSAGE_CHARS
MAX_CHAT_FILES = team_driver_contract.MAX_CHAT_FILES
MAX_CHAT_ASSISTANTS = team_driver_contract.MAX_CHAT_ASSISTANTS
MAX_CHAT_REPLY_CHARS = 60_000
MAX_CHAT_ERROR_DETAIL_CHARS = 800
TERMINAL_CONTRACT_ERROR = "team-driver stream violated the terminal event contract"
CHAT_WS_SUBPROTOCOL = "shimpz.chat.v3"

"""Shimpz storefront serve — one FastAPI process serves the prerendered SvelteKit build (best SEO) AND
the account-authenticated control surface (/api): the shimpz.com loop = signup/login → my Capsules →
create/select → install. It holds NO privileged secret: it PROXIES auth to the `accounts` service and
FORWARDS the user's account token to the socket-holding `capsule-driver`, which is the sole enforcer
(it verifies the token + scopes every op to the account's own Capsules). Reached over the Space's
internal nets (accounts_net + capsuledriver_net). Stdlib http.client for the proxy hops."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import http.client
import json as jsonlib
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import structlog
from fastapi import FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from app import reviews
from app.logconf import setup

setup("shimpz-store")
log = structlog.get_logger()

BUILD = Path(os.environ.get("SHIMPZ_STORE_BUILD", "/app/build"))
ACCOUNTS_URL = os.environ.get("SHIMPZ_ACCOUNTS_URL", "http://accounts:7079")
CAPSULEDRIVER_URL = os.environ.get(
    "SHIMPZ_CAPSULEDRIVER_URL", "http://capsule-driver:7077"
)
ACCOUNT_COOKIE = "shimpz_account"
COOKIE_MAX_AGE = 7 * 24 * 3600

app = FastAPI(title="shimpz-store", docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Fail-loud: full structured trace in the logs, generic 500 to the caller. Never swallow.
    log.exception("unhandled_exception", path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


# ── proxy helpers (the store forwards; it holds no privileged secret) ──────────
def _call(
    base: str,
    method: str,
    path: str,
    payload: dict | None = None,
    extra: dict | None = None,
) -> tuple[int, dict]:
    """One proxied hop. `extra` headers carry the user's account token (X-Shimpz-Account, verified by
    the receiving driver) or the client IP (X-Forwarded-For, keyed by the accounts rate-limiter)."""
    parsed = urlparse(base)
    headers: dict[str, str] = dict(extra or {})
    body = None
    if payload is not None:
        body = jsonlib.dumps(payload)
        headers["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=180)
    try:
        conn.request(method, path, body, headers)
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, (jsonlib.loads(raw) if raw else {})
    except (OSError, jsonlib.JSONDecodeError) as exc:
        log.warning("proxy_unreachable", base=base, path=path, error=str(exc))
        return 502, {"detail": "the Space is unreachable"}
    finally:
        conn.close()


def _set_cookie(resp: JSONResponse, token: str) -> None:
    resp.set_cookie(
        ACCOUNT_COOKIE,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=True,
        path="/",
    )


def _authed_account(request: Request) -> tuple[str, str, str]:
    """(token, account_id, username) for a valid cookie, else ('', '', ''). Verified against accounts."""
    token = request.cookies.get(ACCOUNT_COOKIE, "")
    if not token:
        return "", "", ""
    status, data = _call(ACCOUNTS_URL, "POST", "/v1/verify", {"token": token})
    if status == 200 and data.get("account_id"):
        return token, data["account_id"], data.get("username", "")
    return "", "", ""


def _installed_anywhere(token: str, app_id: str) -> bool:
    """True iff the account has this Shimpz installed in ANY Capsule it owns — the review honesty gate.

    Asks the capsule-driver with the user's own forwarded token, so the answer is owner-scoped by the
    same enforcer as every other capsule op; the store still holds no privileged secret.
    """
    status, data = _call(
        CAPSULEDRIVER_URL, "GET", "/v1/capsules", extra={"X-Shimpz-Account": token}
    )
    if status != 200:
        return False
    for capsule in data.get("capsules", []):
        status, apps = _call(
            CAPSULEDRIVER_URL,
            "GET",
            f"/v1/capsules/{capsule['id']}/apps",
            extra={"X-Shimpz-Account": token},
        )
        if status == 200 and any(a.get("app") == app_id for a in apps.get("apps", [])):
            return True
    return False


def _client_ip(request: Request) -> str:
    """The end user's IP as best we can know it — Cloudflare's header when fronted, else the socket peer."""
    return request.headers.get("cf-connecting-ip", "") or (
        request.client.host if request.client else ""
    )


def _cid_for(account_id: str, name: str) -> str:
    """A globally-unique, Docker/PG-safe capsule id from (account, name) — so two accounts can both name
    a Capsule 'workspace' without colliding. The display name is kept separately (the capsule.owner/name)."""
    slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")[:28]
    return f"{account_id[:8]}_{slug}".strip("_")[:40]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ── account auth (proxied to the `accounts` identity service) ──────────────────
@app.post("/api/signup")
def signup(request: Request, payload: dict) -> JSONResponse:
    status, data = _call(
        ACCOUNTS_URL,
        "POST",
        "/v1/signup",
        {"username": payload.get("username"), "password": payload.get("password")},
        extra={"X-Forwarded-For": _client_ip(request)},
    )
    body = (
        {"account_id": data.get("account_id"), "username": data.get("username")}
        if status == 200
        else data
    )
    resp = JSONResponse(body, status_code=status)
    if status == 200 and data.get("token"):
        _set_cookie(resp, data["token"])
        log.info("signup", username=data.get("username"))
    return resp


@app.post("/api/login")
def login(request: Request, payload: dict) -> JSONResponse:
    status, data = _call(
        ACCOUNTS_URL,
        "POST",
        "/v1/login",
        {"username": payload.get("username"), "password": payload.get("password")},
        extra={"X-Forwarded-For": _client_ip(request)},
    )
    body = (
        {"account_id": data.get("account_id"), "username": data.get("username")}
        if status == 200
        else data
    )
    resp = JSONResponse(body, status_code=status)
    if status == 200 and data.get("token"):
        _set_cookie(resp, data["token"])
    return resp


@app.post("/api/logout")
def logout() -> JSONResponse:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(ACCOUNT_COOKIE, path="/")
    return resp


@app.get("/api/me")
def me(request: Request) -> JSONResponse:
    _, account_id, username = _authed_account(request)
    return JSONResponse(
        {
            "authenticated": bool(account_id),
            "account_id": account_id or None,
            "username": username or None,
        }
    )


# ── Capsules (forward the user's token; capsule-driver is the enforcer) ────────
@app.get("/api/capsules")
def capsules_list(request: Request) -> JSONResponse:
    token, _, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = _call(
        CAPSULEDRIVER_URL, "GET", "/v1/capsules", extra={"X-Shimpz-Account": token}
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/capsules")
def capsules_create(request: Request, payload: dict) -> JSONResponse:
    token, account_id, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    name = str((payload or {}).get("name", "")).strip()
    brain = str((payload or {}).get("brain", "") or "claude-code").strip()
    cid = _cid_for(account_id, name)
    if not name or not cid.strip("_"):
        return JSONResponse({"detail": "bad capsule name"}, status_code=400)
    status, data = _call(
        CAPSULEDRIVER_URL,
        "POST",
        f"/v1/capsules/{cid}/create",
        {
            "name": name,
            "brain": brain,
        },  # the driver's BRAINS registry validates it (unknown → 400)
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.delete("/api/capsules/{cid}")
def capsules_destroy(request: Request, cid: str) -> JSONResponse:
    token, _, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = _call(
        CAPSULEDRIVER_URL,
        "DELETE",
        f"/v1/capsules/{cid}",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/capsules/{cid}/install")
def capsule_install(request: Request, cid: str, payload: dict) -> JSONResponse:
    """P4 marketplace install: gate AND deploy. The forwarded account token is verified and ownership
    enforced by the capsule-driver, which resolves the app id against its own trusted registry and
    deploys the pinned image into the Capsule's isolated environment (own network, own scoped DB).
    The store still holds no privileged secret — it forwards, the socket-holding driver enforces."""
    token, account_id, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    app_id = str((payload or {}).get("app", "")).strip()
    if not app_id.replace("-", "").isalnum():
        return JSONResponse({"detail": "bad app id"}, status_code=400)
    status, data = _call(
        CAPSULEDRIVER_URL,
        "POST",
        f"/v1/capsules/{cid}/apps",
        {"app": app_id},
        extra={"X-Shimpz-Account": token},
    )
    log.info(
        "app_install",
        account=account_id,
        capsule=cid,
        app=app_id,
        status=status,
        installed=data.get("installed"),
    )
    return JSONResponse(data, status_code=status)


@app.get("/api/capsules/{cid}/apps")
def capsule_apps(request: Request, cid: str) -> JSONResponse:
    token, _, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = _call(
        CAPSULEDRIVER_URL,
        "GET",
        f"/v1/capsules/{cid}/apps",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.delete("/api/capsules/{cid}/apps/{app_id}")
def capsule_uninstall(request: Request, cid: str, app_id: str) -> JSONResponse:
    token, account_id, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = _call(
        CAPSULEDRIVER_URL,
        "DELETE",
        f"/v1/capsules/{cid}/apps/{app_id}",
        extra={"X-Shimpz-Account": token},
    )
    log.info(
        "app_uninstall", account=account_id, capsule=cid, app=app_id, status=status
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/accounts/v1/verify")
def accounts_verify(payload: dict) -> JSONResponse:
    """The SELF-HOST PHONE-HOME surface: a self-hosted Space's capsule-driver points its
    SHIMPZ_ACCOUNTS_URL at https://shimpz.com/api/accounts and verifies marketplace-install tokens
    here — its accounts client appends /v1/verify to that base, landing exactly on this route (the
    same internal verify shimpz.com's own Space uses, exposed as a public passthrough). Discloses
    nothing but token validity → account_id (tokens are 256-bit-HMAC-signed)."""
    status, data = _call(
        ACCOUNTS_URL, "POST", "/v1/verify", {"token": (payload or {}).get("token")}
    )
    return JSONResponse(data, status_code=status)


# ── the Captain's chat (ADR-0004): forwarded to the capsule-driver's named exec ops ──────────────
MAX_UPLOAD_BYTES = (
    25 * 1024 * 1024
)  # well under Cloudflare's 100 MB proxied-body cap; big files → R2 later


@app.get("/api/capsules/{cid}/brain")
def capsule_brain(request: Request, cid: str) -> JSONResponse:
    token, _, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = _call(
        CAPSULEDRIVER_URL,
        "GET",
        f"/v1/capsules/{cid}/brain",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/capsules/{cid}/brain/login/start")
@app.get("/api/capsules/{cid}/brain/login/url")
@app.post("/api/capsules/{cid}/brain/login/code")
@app.get("/api/capsules/{cid}/brain/login/status")
def capsule_brain_login(
    request: Request, cid: str, payload: dict | None = None
) -> JSONResponse:
    """The per-Capsule Claude-subscription OAuth bridge (the admin panel's exact flow, Captain-facing):
    start → poll url → the Captain authorizes in the browser and pastes the code → status flips.
    Pure forward — the capsule-driver execs the FIXED `shimpz-login` inside the Captain's own Capsule."""
    token, _, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    step = request.url.path.rsplit("/", 1)[-1]
    method = "POST" if step in ("start", "code") else "GET"
    body = {"code": (payload or {}).get("code")} if step == "code" else None
    status, data = _call(
        CAPSULEDRIVER_URL,
        method,
        f"/v1/capsules/{cid}/brain/login/{step}",
        body,
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/capsules/{cid}/chat")
def capsule_chat(request: Request, cid: str, payload: dict) -> JSONResponse:
    token, account_id, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    message = str((payload or {}).get("message", ""))
    status, data = _call(
        CAPSULEDRIVER_URL,
        "POST",
        f"/v1/capsules/{cid}/chat",
        {"message": message},
        extra={"X-Shimpz-Account": token},
    )
    log.info("chat", account=account_id, capsule=cid, status=status, chars=len(message))
    return JSONResponse(data, status_code=status)


@app.get("/api/capsules/{cid}/chat/asks")
def capsule_chat_asks(request: Request, cid: str) -> JSONResponse:
    token, _, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    status, data = _call(
        CAPSULEDRIVER_URL,
        "GET",
        f"/v1/capsules/{cid}/chat/asks",
        extra={"X-Shimpz-Account": token},
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/capsules/{cid}/chat/answer")
def capsule_chat_answer(request: Request, cid: str, payload: dict) -> JSONResponse:
    token, account_id, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    body = {"rid": (payload or {}).get("rid"), "answer": (payload or {}).get("answer")}
    status, data = _call(
        CAPSULEDRIVER_URL,
        "POST",
        f"/v1/capsules/{cid}/chat/answer",
        body,
        extra={"X-Shimpz-Account": token},
    )
    log.info(
        "chat_answer",
        account=account_id,
        capsule=cid,
        status=status,
        answered=data.get("answered"),
    )
    return JSONResponse(data, status_code=status)


@app.post("/api/capsules/{cid}/files")
async def capsule_file(request: Request, cid: str, file: UploadFile) -> JSONResponse:
    """Upload one file to the Capsule's workspace inbox (the chat references it by path)."""
    token, account_id, _ = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return JSONResponse(
            {"detail": f"file too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)"},
            status_code=413,
        )
    payload = {
        "filename": file.filename or "upload.bin",
        "content_b64": base64.b64encode(data).decode(),
    }
    status, body = _call(
        CAPSULEDRIVER_URL,
        "POST",
        f"/v1/capsules/{cid}/files",
        payload,
        extra={"X-Shimpz-Account": token},
    )
    log.info(
        "inbox_file", account=account_id, capsule=cid, bytes=len(data), status=status
    )
    return JSONResponse(body, status_code=status)


# ── the Captain's LIVE bridge: WebSocket chat (push, not poll) ───────────────────
# One socket per open chat: the Captain's messages go down it, the brain's replies AND the brain's
# own mid-turn QUESTIONS (shimpz-ask → the capsule's ipc dir) come back up as pushes. Inter-container
# hops stay HTTP (cheap, internal); the browser never polls.
WS_ASK_POLL_SECONDS = 1.0


async def _ws_verify(ws: WebSocket) -> str:
    token = ws.cookies.get(ACCOUNT_COOKIE, "")
    if not token:
        return ""
    status, data = await asyncio.to_thread(
        _call, ACCOUNTS_URL, "POST", "/v1/verify", {"token": token}
    )
    return token if status == 200 and data.get("account_id") else ""


async def _ws_push_asks(ws: WebSocket, cid: str, hdr: dict, seen: set[str]) -> None:
    """Push the brain's pending shimpz-ask questions the moment they appear; hang up on 404."""
    while True:
        status, data = await asyncio.to_thread(
            _call, CAPSULEDRIVER_URL, "GET", f"/v1/capsules/{cid}/chat/asks", None, hdr
        )
        if status == 404:  # not the Captain's capsule (the driver's owner-scoping)
            await ws.send_json(
                {"type": "error", "status": 404, "detail": "capsule not found"}
            )
            await ws.close(code=4404)
            return
        if status == 200:
            for ask in data.get("asks", []):
                rid = str(ask.get("rid", ""))
                if rid and rid not in seen:
                    seen.add(rid)
                    await ws.send_json({"type": "ask", **ask})
        await asyncio.sleep(WS_ASK_POLL_SECONDS)


def _stream_lines(
    cid: str,
    text: str,
    hdr: dict,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """BLOCKING (run in a thread): read the driver's chunked NDJSON chat stream, push each event onto
    an asyncio queue the WS coroutine drains. A sentinel None marks end-of-stream."""
    parsed = urlparse(CAPSULEDRIVER_URL)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=200)
    try:
        body = jsonlib.dumps({"message": text})
        conn.request(
            "POST",
            f"/v1/capsules/{cid}/chat/stream",
            body,
            {**hdr, "Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        buf = b""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    with contextlib.suppress(jsonlib.JSONDecodeError):
                        loop.call_soon_threadsafe(queue.put_nowait, jsonlib.loads(line))
    except OSError as exc:
        loop.call_soon_threadsafe(
            queue.put_nowait, {"type": "error", "detail": f"stream failed: {exc}"}
        )
    finally:
        conn.close()
        loop.call_soon_threadsafe(queue.put_nowait, None)


async def _ws_run_turn(ws: WebSocket, cid: str, hdr: dict, text: str) -> None:
    """Relay a LIVE streaming turn: text/tool/done/error events pushed as the brain produces them."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    worker = asyncio.create_task(
        asyncio.to_thread(_stream_lines, cid, text, hdr, queue, loop)
    )
    try:
        while True:
            evt = await queue.get()
            if evt is None:
                break
            await ws.send_json(evt)
    finally:
        worker.cancel()


async def _ws_dispatch(
    ws: WebSocket, cid: str, hdr: dict, msg: dict, state: dict
) -> None:
    seen, turns = state["seen"], state["turns"]
    if msg.get("type") == "chat":
        # a background task, NOT awaited inline: the brain may shimpz-ask mid-turn and that
        # question must reach the Captain while this very turn is still streaming
        turn = asyncio.create_task(
            _ws_run_turn(ws, cid, hdr, str(msg.get("message", "")))
        )
        turns.add(turn)
        turn.add_done_callback(turns.discard)
    elif msg.get("type") == "stop":
        await asyncio.to_thread(
            _call, CAPSULEDRIVER_URL, "POST", f"/v1/capsules/{cid}/chat/stop", None, hdr
        )
        await ws.send_json({"type": "stopped"})
    elif msg.get("type") == "answer":
        status, data = await asyncio.to_thread(
            _call,
            CAPSULEDRIVER_URL,
            "POST",
            f"/v1/capsules/{cid}/chat/answer",
            {"rid": msg.get("rid"), "answer": msg.get("answer")},
            hdr,
        )
        seen.discard(str(msg.get("rid", "")))
        await ws.send_json({"type": "answered", "status": status, **data})


@app.websocket("/api/capsules/{cid}/ws")
async def capsule_ws(ws: WebSocket, cid: str) -> None:
    token = await _ws_verify(ws)
    if not token:
        await ws.close(code=4401)
        return
    await ws.accept()
    hdr = {"X-Shimpz-Account": token}
    state: dict = {"seen": set(), "turns": set()}
    pusher = asyncio.create_task(_ws_push_asks(ws, cid, hdr, state["seen"]))
    try:
        while True:
            await _ws_dispatch(ws, cid, hdr, await ws.receive_json(), state)
    except WebSocketDisconnect:
        pass
    finally:
        pusher.cancel()
        for turn in state["turns"]:
            turn.cancel()


# ── reviews (stars + comments from Captains who actually run the Shimpz) ───────
@app.get("/api/apps/{app_id}/reviews")
def reviews_get(app_id: str) -> JSONResponse:
    try:
        return JSONResponse(reviews.for_app(app_id))
    except reviews.ReviewError as exc:
        return JSONResponse({"detail": exc.message}, status_code=exc.code)


@app.post("/api/apps/{app_id}/reviews")
def reviews_post(request: Request, app_id: str, payload: dict) -> JSONResponse:
    """Upsert the caller's review. The HONESTY GATE: only an account with this Shimpz installed in a
    Capsule it owns may rate it (checked against the capsule-driver with the caller's own token) —
    the marketplace never shows a rating from someone who never ran the thing."""
    token, account_id, username = _authed_account(request)
    if not token:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    try:
        aid = reviews.validate_app_id(app_id)
        if not _installed_anywhere(token, aid):
            return JSONResponse(
                {"detail": "install this Shimpz in your Capsule to review it"},
                status_code=403,
            )
        reviews.upsert(
            aid,
            account_id,
            username or account_id[:8],
            (payload or {}).get("stars"),
            (payload or {}).get("comment"),
        )
        log.info(
            "review", account=account_id, app=aid, stars=(payload or {}).get("stars")
        )
        return JSONResponse(reviews.for_app(aid))
    except reviews.ReviewError as exc:
        return JSONResponse({"detail": exc.message}, status_code=exc.code)


# ── the install one-liner (ADR-0005): `curl -fsSL https://install.shimpz.com | sh` ──────────────
INSTALL_SH = Path(os.environ.get("SHIMPZ_INSTALL_SH", "/app/install.sh"))
INSTALL_HOST = "install.shimpz.com"


def _install_script() -> Response:
    if INSTALL_SH.is_file():
        return PlainTextResponse(
            INSTALL_SH.read_text(encoding="utf-8"), media_type="text/x-shellscript"
        )
    return PlainTextResponse(
        "# installer unavailable\n", status_code=503, media_type="text/plain"
    )


@app.get("/install.sh")
def install_sh() -> Response:
    return _install_script()


# ── static: serve the prerendered SvelteKit build (adapter-static writes <route>.html + assets) ──
def _resolve(rel: str) -> Path | None:
    rel = rel.strip("/")
    if ".." in rel.split("/"):  # no traversal out of BUILD
        return None
    for cand in (BUILD / rel, BUILD / f"{rel}.html", BUILD / rel / "index.html"):
        if cand.is_file():
            return cand
    return None


@app.get("/{path:path}")
def static_files(path: str, request: Request) -> Response:
    # install.shimpz.com serves the installer at its ROOT — `curl install.shimpz.com | sh`, like
    # the big open-source projects (the same script is also at shimpz.com/install.sh).
    host = (request.headers.get("host", "") or "").split(":")[0].lower()
    if host == INSTALL_HOST and path in ("", "install.sh"):
        return _install_script()
    hit = _resolve(path)
    if hit:
        return FileResponse(hit)
    # unknown path → the prerendered root (a redirect to /en); 404 status so bots don't index junk
    root = BUILD / "index.html"
    if root.is_file():
        return FileResponse(root, status_code=404)
    return PlainTextResponse("not found", status_code=404)

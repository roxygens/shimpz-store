import contextlib
import json
import re
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from app import authn, config, main, upstream
from app.config import ACCOUNT_COOKIE
from app.main import app


def test_verify_timeout_uses_fast_budget_and_surfaces_502(monkeypatch):
    observed: dict[str, object] = {}

    class TimedOutConnection:
        def __init__(self, hostname, port, *, timeout):
            observed.update(hostname=hostname, port=port, timeout=timeout)

        def request(self, *_args) -> None:
            raise TimeoutError

        def close(self) -> None:
            observed["closed"] = True

    monkeypatch.setattr(upstream.http.client, "HTTPConnection", TimedOutConnection)

    status, body = upstream.call(
        "http://accounts:8080",
        "POST",
        "/v1/verify",
        {"token": "opaque"},
        timeout=upstream.VERIFY_TIMEOUT_SECONDS,
    )

    assert (status, body) == (502, {"detail": "the Space is unreachable"})
    assert observed == {
        "hostname": "accounts",
        "port": 8080,
        "timeout": 5,
        "closed": True,
    }


class _BrainControlHandler(BaseHTTPRequestHandler):
    calls: list[tuple[str, str, dict]]
    state: dict[str, int]
    finalize_token: str

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self.calls.append(("GET", self.path, {}))
        if self.path == "/v1/teams/team-openai/inference":
            self._json(200, {"provider": "openai", "model": "gpt-5.5"})
            return
        self._json(404, {"error": "not found"})

    def do_PUT(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.calls.append(("PUT", self.path, body))
        if self.path == "/v1/teams/team-openai/inference":
            self._json(200, {"team_id": "team-openai", **body})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.calls.append(("POST", self.path, body))
        if self.path == "/v1/verify":
            self._json(200, {"account_id": "account-1", "username": "captain"})
        elif self.path == "/v1/brains/upsert":
            self._json(
                200,
                {
                    "provider": body.get("provider"),
                    "auth_type": body.get("auth_type"),
                    "status": "configured",
                },
            )
        elif self.path == "/v1/brains/revoke-begin":
            self.state["begin_count"] += 1
            self._json(
                200,
                {
                    "provider": body.get("provider"),
                    "status": "revoking",
                    "generation": 7,
                    "already_absent": False,
                    "already_revoking": self.state["begin_count"] > 1,
                },
            )
        elif self.path == "/v1/internal/brains/revoke-finalize":
            if self.headers.get("Authorization") != f"Bearer {self.finalize_token}":
                self._json(403, {"error": "invalid or missing credentials"})
                return
            if body.get("generation") != 7:
                self._json(409, {"detail": "generation mismatch"})
            else:
                self._json(200, {"deleted": True, "generation": 7})
        elif self.path.startswith("/v1/teams/") and self.path.endswith("/create"):
            self._json(201, {"created": True, **body})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, *_args) -> None:
        pass


@contextlib.contextmanager
def _brain_control_plane(*, finalize_token_available: bool = True):
    calls: list[tuple[str, str, dict]] = []
    finalize_token = secrets.token_hex(32)
    handler = type(
        "_ScopedBrainControlHandler",
        (_BrainControlHandler,),
        {
            "calls": calls,
            "state": {"begin_count": 0},
            "finalize_token": finalize_token,
        },
    )

    with tempfile.TemporaryDirectory() as temporary:
        token_path = Path(temporary) / "brain-finalize-token"
        if finalize_token_available:
            token_path.write_text(finalize_token)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        worker = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        previous = (
            config.ACCOUNTS_URL,
            config.TEAMDRIVER_URL,
            config.BRAIN_FINALIZE_TOKEN_FILE,
        )
        authn.ACCOUNTS_URL = config.ACCOUNTS_URL = config.TEAMDRIVER_URL = base
        config.BRAIN_FINALIZE_TOKEN_FILE = token_path
        try:
            yield calls
        finally:
            (
                config.ACCOUNTS_URL,
                config.TEAMDRIVER_URL,
                config.BRAIN_FINALIZE_TOKEN_FILE,
            ) = previous
            authn.ACCOUNTS_URL = config.ACCOUNTS_URL
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


def test_provider_key_delete_revokes_generation_without_touching_teams():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.delete("/api/brains/openai")
    begin = ("POST", "/v1/brains/revoke-begin", {"token": "valid-token", "provider": "openai"})
    finalize = (
        "POST",
        "/v1/internal/brains/revoke-finalize",
        {"token": "valid-token", "provider": "openai", "generation": 7},
    )
    assert response.status_code == 200
    assert begin in calls and finalize in calls
    assert calls.index(begin) < calls.index(finalize)
    assert not any(call[1].startswith("/v1/teams/") for call in calls)


def test_model_credentials_accept_only_generic_provider_api_keys():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        valid = client.post("/api/brains/anthropic", json={"auth_type": "api_key", "secret": "secret-key"})
        oauth = client.post("/api/brains/anthropic", json={"auth_type": "oauth", "secret": "oauth-token"})
        legacy = client.post("/api/brains/codex", json={"auth_type": "api_key", "secret": "secret-key"})

    assert valid.status_code == 200
    assert valid.json() == {"provider": "anthropic", "auth_type": "api_key", "status": "configured"}
    assert oauth.status_code == legacy.status_code == 400
    assert [call for call in calls if call[1] == "/v1/brains/upsert"] == [
        (
            "POST",
            "/v1/brains/upsert",
            {
                "token": "valid-token",
                "provider": "anthropic",
                "auth_type": "api_key",
                "secret": "secret-key",
            },
        )
    ]


def test_team_create_forwards_the_account_scoped_model_to_the_real_control_plane():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.post(
            "/api/teams",
            json={"team_name": "Astra", "provider": "openai", "model": "gpt-5.5"},
        )
        legacy = client.post(
            "/api/teams",
            json={"team_name": "Legacy", "provider": "openai", "model": "gpt-5.5", "brain": "codex"},
        )
    assert response.status_code == 201
    assert legacy.status_code == 400
    assert [
        call for call in calls if call[0] == "POST" and call[1].startswith("/v1/teams/") and call[1].endswith("/create")
    ] == [
        (
            "POST",
            f"/v1/teams/{main.teams.team_id_for('account-1', 'Astra')}/create",
            {"team_name": "Astra", "provider": "openai", "model": "gpt-5.5"},
        )
    ]


def test_team_inference_is_read_and_updated_without_recreating_team():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        current = client.get("/api/teams/team-openai/inference")
        updated = client.put(
            "/api/teams/team-openai/inference",
            json={"provider": "anthropic", "model": "claude-sonnet-5"},
        )
        retired_login = client.post("/api/teams/team-openai/brain/login/start")

    assert current.status_code == updated.status_code == 200
    assert current.json() == {"provider": "openai", "model": "gpt-5.5"}
    assert updated.json() == {
        "team_id": "team-openai",
        "provider": "anthropic",
        "model": "claude-sonnet-5",
    }
    assert retired_login.status_code in {404, 405}
    assert ("GET", "/v1/teams/team-openai/inference", {}) in calls
    assert (
        "PUT",
        "/v1/teams/team-openai/inference",
        {"provider": "anthropic", "model": "claude-sonnet-5"},
    ) in calls
    assert not any(call[1].endswith("/create") for call in calls)


def test_team_models_must_match_the_closed_provider_catalog_before_forwarding():
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        create = client.post(
            "/api/teams",
            json={"team_name": "Unknown", "provider": "openai", "model": "gpt-unknown"},
        )
        switch = client.put(
            "/api/teams/team-openai/inference",
            json={"provider": "anthropic", "model": "gpt-5.5"},
        )

    assert create.status_code == switch.status_code == 400
    assert create.json() == switch.json() == {"detail": "unsupported model for provider"}
    assert not any(
        path.endswith("/create") or (method == "PUT" and path.endswith("/inference")) for method, path, _body in calls
    )


def test_team_ids_bind_the_complete_account_and_normalized_name():
    first = main.teams.team_id_for("account-prefix-one", "A very long shared team name alpha")
    same = main.teams.team_id_for("account-prefix-one", "A very long shared team name alpha")
    other_account = main.teams.team_id_for("account-prefix-two", "A very long shared team name alpha")
    other_tail = main.teams.team_id_for("account-prefix-one", "A very long shared team name omega")

    assert first == same
    assert first != other_account
    assert first != other_tail
    assert len(first) <= 40
    assert re.fullmatch(r"[a-z0-9_]+", first)
    assert main.teams.team_id_for("account-prefix-one", "!!!") == ""


def test_control_mutations_reject_oversize_bodies_before_control_plane_forwarding():
    create_body = json.dumps({"team_name": "Astra", "padding": "x" * config.MAX_TEAM_CREATE_BODY_BYTES}).encode()
    install_body = json.dumps(
        {"app": "notification-center", "padding": "x" * config.MAX_TEAM_INSTALL_BODY_BYTES}
    ).encode()
    inference_body = json.dumps(
        {"provider": "openai", "model": "gpt-5.5", "padding": "x" * config.MAX_INFERENCE_BODY_BYTES}
    ).encode()
    credential_body = json.dumps(
        {"auth_type": "api_key", "secret": "x" * main.brains.MAX_CREDENTIAL_BODY_BYTES}
    ).encode()
    with _brain_control_plane() as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        create = client.post("/api/teams", content=create_body, headers={"Content-Type": "application/json"})
        install = client.post(
            "/api/teams/team_openai/install",
            content=install_body,
            headers={"Content-Type": "application/json", "Origin": "https://shimpz.com"},
        )
        inference = client.put(
            "/api/teams/team_openai/inference",
            content=inference_body,
            headers={"Content-Type": "application/json"},
        )
        credential = client.post(
            "/api/brains/openai",
            content=credential_body,
            headers={"Content-Type": "application/json"},
        )
    assert create.status_code == install.status_code == inference.status_code == credential.status_code == 413
    for private_response in (inference, credential):
        assert private_response.headers["cache-control"] == "private, no-store"
    assert [path for method, path, _body in calls if method == "POST" and path.endswith(("/create", "/apps"))] == []
    assert not any(
        path == "/v1/brains/upsert" or (method == "PUT" and path.endswith("/inference"))
        for method, path, _body in calls
    )


def test_provider_key_delete_fails_closed_without_the_finalizer_bearer():
    with _brain_control_plane(finalize_token_available=False) as calls, TestClient(app) as client:
        client.cookies.set(ACCOUNT_COOKIE, "valid-token")
        response = client.delete("/api/brains/openai")
    assert response.status_code == 502
    assert response.json() == {"detail": "Brain credential finalization is unavailable"}
    assert not any(call[1] == "/v1/internal/brains/revoke-finalize" for call in calls)

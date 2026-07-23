import contextlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

from fastapi.testclient import TestClient

from app import authn, main


class _AssistantControlHandler(BaseHTTPRequestHandler):
    calls: list[tuple[str, str, dict, str]]
    app_status = 200
    apps: ClassVar[list[dict[str, object]]] = [
        {
            "app": "shimpz-cloudflare",
            "status": "running",
            "container": "private-name",
        },
        {"app": "notification-center", "status": "running"},
    ]

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        self.calls.append(("GET", self.path, {}, self.headers.get("X-Shimpz-Account", "")))
        if self.path == "/v1/teams/team_one/apps":
            self._json(
                self.app_status,
                {
                    "team_id": "team_one",
                    "apps": self.apps,
                }
                if self.app_status == 200
                else {"detail": "driver unavailable"},
            )
            return
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:
        body = self._body()
        token = self.headers.get("X-Shimpz-Account", "")
        self.calls.append(("POST", self.path, body, token))
        if self.path == "/v1/verify":
            if body.get("token") == "valid-token":
                self._json(200, {"account_id": "account-1", "username": "captain"})
            else:
                self._json(401, {"detail": "invalid token"})
            return
        if self.path == "/v1/teams/team_one/apps":
            self._json(
                self.app_status,
                {"installed": True} if self.app_status == 200 else {"detail": "blocked"},
            )
            return
        self._json(404, {"detail": "not found"})

    def do_DELETE(self) -> None:
        self.calls.append(("DELETE", self.path, {}, self.headers.get("X-Shimpz-Account", "")))
        if self.path.startswith("/v1/teams/team_one/apps/"):
            self._json(
                self.app_status,
                {"uninstalled": True} if self.app_status == 200 else {"detail": "blocked"},
            )
            return
        self._json(404, {"detail": "not found"})

    def log_message(self, *_args) -> None:
        pass


@contextlib.contextmanager
def _assistant_control_plane(*, app_status: int = 200, apps: list[dict] | None = None):
    calls: list[tuple[str, str, dict, str]] = []
    handler = type(
        "_ScopedAssistantControlHandler",
        (_AssistantControlHandler,),
        {
            "calls": calls,
            "app_status": app_status,
            "apps": _AssistantControlHandler.apps if apps is None else apps,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    worker.start()
    previous = authn.ACCOUNTS_URL, main.TEAMDRIVER_URL
    authn.ACCOUNTS_URL = main.TEAMDRIVER_URL = f"http://127.0.0.1:{server.server_port}"
    try:
        yield calls
    finally:
        authn.ACCOUNTS_URL, main.TEAMDRIVER_URL = previous
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def _authenticate(client: TestClient) -> None:
    client.cookies.set(main.ACCOUNT_COOKIE, "valid-token")


def _mutation_headers() -> dict[str, str]:
    return {"Origin": "https://shimpz.com", "Content-Type": "application/json"}


def _assert_private(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"


def test_cloud_assistant_lifecycle_requires_authentication_before_upstream():
    with _assistant_control_plane() as calls, TestClient(main.app) as client:
        responses = (
            client.get("/api/teams/team_one/assistants"),
            client.get("/api/teams/team_one/chat/assistants"),
            client.post(
                "/api/teams/team_one/assistants",
                content=b'{"assistant":"shimpz-cloudflare"}',
                headers=_mutation_headers(),
            ),
            client.delete(
                "/api/teams/team_one/assistants/shimpz-cloudflare",
                headers={"Origin": "https://shimpz.com"},
            ),
        )
    assert [response.status_code for response in responses] == [401, 401, 401, 401]
    assert calls == []
    for response in responses:
        assert response.json() == {"detail": "not authenticated"}
        _assert_private(response)


def test_cloud_assistant_inventory_projects_only_released_ids_without_private_runtime_data():
    with _assistant_control_plane() as calls, TestClient(main.app) as client:
        _authenticate(client)
        response = client.get("/api/teams/team_one/assistants")
    assert response.status_code == 200
    assert response.json() == {"installed": ["shimpz-cloudflare"]}
    _assert_private(response)
    assert ("GET", "/v1/teams/team_one/apps", {}, "valid-token") in calls


def test_cloud_chat_scope_projects_only_released_running_assistants():
    with _assistant_control_plane() as calls, TestClient(main.app) as client:
        _authenticate(client)
        response = client.get("/api/teams/team_one/chat/assistants")
    assert response.status_code == 200
    assert response.json() == {"assistant_ids": ["shimpz-cloudflare"]}
    _assert_private(response)
    assert ("GET", "/v1/teams/team_one/apps", {}, "valid-token") in calls


def test_cloud_chat_scope_is_brain_only_when_the_released_assistant_is_not_running():
    apps = [
        {"app": "shimpz-cloudflare", "status": "stopped"},
        {"app": "notification-center", "status": "running"},
    ]
    with _assistant_control_plane(apps=apps), TestClient(main.app) as client:
        _authenticate(client)
        response = client.get("/api/teams/team_one/chat/assistants")
    assert response.status_code == 200
    assert response.json() == {"assistant_ids": []}
    _assert_private(response)


def test_cloud_chat_scope_fails_closed_on_ambiguous_running_inventory():
    apps = [
        {"app": "shimpz-cloudflare", "status": "running"},
        {"app": "shimpz-cloudflare", "status": "running"},
    ]
    with _assistant_control_plane(apps=apps), TestClient(main.app) as client:
        _authenticate(client)
        response = client.get("/api/teams/team_one/chat/assistants")
    assert response.status_code == 502
    assert response.json() == {"detail": "invalid chat Assistant inventory"}
    _assert_private(response)


def test_cloud_assistant_install_rejects_origin_content_type_shape_and_unreleased_ids_before_driver():
    cases = (
        ("/api/teams/team_one/assistants", {}, b'{"assistant":"shimpz-cloudflare"}', 403),
        (
            "/api/teams/team_one/assistants",
            {"Origin": "https://store.shimpz.com", "Content-Type": "application/json"},
            b'{"assistant":"shimpz-cloudflare"}',
            403,
        ),
        (
            "/api/teams/team_one/assistants",
            {"Origin": "https://shimpz.com", "Content-Type": "text/plain"},
            b'{"assistant":"shimpz-cloudflare"}',
            415,
        ),
        (
            "/api/teams/team_one/assistants",
            _mutation_headers(),
            b'{"assistant":"shimpz-cloudflare","image":"attacker/image"}',
            400,
        ),
        (
            "/api/teams/team_one/assistants",
            _mutation_headers(),
            b'{"assistant":"unknown-assistant"}',
            404,
        ),
        (
            "/api/teams/TEAM_ONE/assistants",
            _mutation_headers(),
            b'{"assistant":"shimpz-cloudflare"}',
            400,
        ),
    )
    with _assistant_control_plane() as calls, TestClient(main.app) as client:
        _authenticate(client)
        responses = [client.post(path, content=body, headers=headers) for path, headers, body, _ in cases]
    assert [response.status_code for response in responses] == [case[3] for case in cases]
    assert not any(path.endswith("/apps") for _method, path, _body, _token in calls)
    for response in responses:
        _assert_private(response)


def test_legacy_app_install_cannot_bypass_origin_json_or_exact_body_contract():
    cases = (
        ({"Content-Type": "text/plain"}, b'{"app":"shimpz-cloudflare"}', 403),
        (
            {"Origin": "https://store.shimpz.com", "Content-Type": "text/plain"},
            b'{"app":"shimpz-cloudflare"}',
            403,
        ),
        (
            {"Origin": "https://shimpz.com", "Content-Type": "text/plain"},
            b'{"app":"shimpz-cloudflare"}',
            415,
        ),
        (
            _mutation_headers(),
            b'{"app":"shimpz-cloudflare","image":"attacker/image"}',
            400,
        ),
    )
    with _assistant_control_plane() as calls, TestClient(main.app) as client:
        _authenticate(client)
        responses = [
            client.post("/api/teams/team_one/install", content=body, headers=headers)
            for headers, body, _status in cases
        ]
    assert [response.status_code for response in responses] == [case[2] for case in cases]
    assert not any(path.endswith("/apps") for _method, path, _body, _token in calls)
    for response in responses:
        _assert_private(response)


def test_cloud_assistant_delete_rejects_untrusted_origins_and_nonreleased_ids_before_driver():
    cases = (
        ("/api/teams/team_one/assistants/shimpz-cloudflare", {}, 403),
        (
            "/api/teams/team_one/assistants/shimpz-cloudflare",
            {"Origin": "https://shimpz.com.evil.example"},
            403,
        ),
        (
            "/api/teams/team_one/assistants/retired-assistant",
            {"Origin": "https://shimpz.com"},
            404,
        ),
        (
            "/api/teams/TEAM_ONE/assistants/shimpz-cloudflare",
            {"Origin": "https://shimpz.com"},
            400,
        ),
    )
    with _assistant_control_plane() as calls, TestClient(main.app) as client:
        _authenticate(client)
        responses = [client.delete(path, headers=headers) for path, headers, _status in cases]
    assert [response.status_code for response in responses] == [case[2] for case in cases]
    assert not any(method == "DELETE" for method, _path, _body, _token in calls)
    for response in responses:
        _assert_private(response)


def test_cloud_assistant_mutations_translate_only_identity_and_refreshable_acceptance():
    with _assistant_control_plane() as calls, TestClient(main.app) as client:
        _authenticate(client)
        installed = client.post(
            "/api/teams/team_one/assistants",
            content=b'{"assistant":"shimpz-cloudflare"}',
            headers=_mutation_headers(),
        )
        removed = client.delete(
            "/api/teams/team_one/assistants/shimpz-cloudflare",
            headers={"Origin": "https://shimpz.com"},
        )
        retired_removed = client.delete(
            "/api/teams/team_one/assistants/retired-assistant",
            headers={"Origin": "https://shimpz.com"},
        )
    assert installed.status_code == removed.status_code == 200
    assert retired_removed.status_code == 404
    assert installed.json() == {"assistant": "shimpz-cloudflare", "accepted": True}
    assert removed.json() == {"assistant": "shimpz-cloudflare", "accepted": True}
    for response in (installed, removed, retired_removed):
        _assert_private(response)
    assert (
        "POST",
        "/v1/teams/team_one/apps",
        {"app": "shimpz-cloudflare"},
        "valid-token",
    ) in calls
    assert (
        "DELETE",
        "/v1/teams/team_one/apps/shimpz-cloudflare",
        {},
        "valid-token",
    ) in calls
    assert not any(path.endswith("/retired-assistant") for _method, path, _body, _token in calls)


def test_cloud_assistant_upstream_failures_remain_private_and_typed():
    with _assistant_control_plane(app_status=503), TestClient(main.app) as client:
        _authenticate(client)
        inventory = client.get("/api/teams/team_one/assistants")
        install = client.post(
            "/api/teams/team_one/assistants",
            content=b'{"assistant":"shimpz-cloudflare"}',
            headers=_mutation_headers(),
        )
        uninstall = client.delete(
            "/api/teams/team_one/assistants/shimpz-cloudflare",
            headers={"Origin": "https://shimpz.com"},
        )
    assert [response.status_code for response in (inventory, install, uninstall)] == [
        503,
        503,
        503,
    ]
    for response in (inventory, install, uninstall):
        _assert_private(response)

import base64
import contextlib
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

from app import main
from fastapi.testclient import TestClient

FILE_ID = "a" * 32
FILE_SHA256 = hashlib.sha256(b"hello").hexdigest()
USAGE = {"used_bytes": 5, "limit_bytes": 100 * 1024 * 1024, "remaining_bytes": 100 * 1024 * 1024 - 5}


class _ControlPlaneHandler(BaseHTTPRequestHandler):
    calls: ClassVar[list[tuple[str, str, dict]]] = []

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
        self.calls.append(("GET", self.path, {}))
        if self.path == "/v1/teams/team_one/files":
            self._json(
                200,
                {
                    "team_id": "team_one",
                    "files": [
                        {
                            "id": FILE_ID,
                            "name": "note.txt",
                            "media_type": "text/plain",
                            "size": 5,
                            "sha256": FILE_SHA256,
                            "created_at": 1_700_000_000,
                            "path": "/controller/private/storage",
                        }
                    ],
                    **USAGE,
                    "controller_private": "ignored",
                },
            )
            return
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:
        body = self._body()
        self.calls.append(("POST", self.path, body))
        if self.path == "/v1/verify":
            self._json(200, {"account_id": "account-one", "username": "captain"})
        elif self.path == "/v1/teams/team_one/files":
            self._json(
                200,
                {
                    "team_id": "team_one",
                    "file": {
                        "id": FILE_ID,
                        "name": body["filename"],
                        "media_type": body["media_type"],
                        "size": 5,
                        "sha256": FILE_SHA256,
                        "path": "/controller/private/storage",
                        **USAGE,
                    },
                    "trace_id": "controller-private",
                },
            )
        else:
            self._json(404, {"detail": "not found"})

    def do_DELETE(self) -> None:
        self.calls.append(("DELETE", self.path, {}))
        if self.path == f"/v1/teams/team_one/files/{FILE_ID}":
            self._json(200, {"team_id": "team_one", "id": FILE_ID, "deleted": True, **USAGE})
        else:
            self._json(404, {"detail": "not found"})

    def log_message(self, *_args) -> None:
        pass


@contextlib.contextmanager
def _control_plane():
    calls: list[tuple[str, str, dict]] = []
    _ControlPlaneHandler.calls = calls

    server = ThreadingHTTPServer(("127.0.0.1", 0), _ControlPlaneHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    previous_accounts = main.ACCOUNTS_URL
    previous_driver = main.TEAMDRIVER_URL
    main.ACCOUNTS_URL = base
    main.TEAMDRIVER_URL = base
    try:
        yield calls
    finally:
        main.ACCOUNTS_URL = previous_accounts
        main.TEAMDRIVER_URL = previous_driver
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def _authenticated_client() -> TestClient:
    client = TestClient(main.app)
    client.cookies.set(main.ACCOUNT_COOKIE, "valid-token")
    return client


def test_public_http_chat_endpoint_is_absent():
    with _control_plane() as calls, _authenticated_client() as client:
        response = client.post(
            "/api/teams/team_one/chat",
            json={"message": "say hello", "files": [FILE_ID]},
        )

    assert response.status_code == 405
    routes = {getattr(route, "path", None) for route in main.app.routes}
    assert "/api/teams/{team_id}/chat" not in routes
    assert "/api/teams/{team_id}/ws" not in routes
    assert "/api/teams/{team_id}/chat/ws" in routes
    assert not any(path.endswith("/chat") for _method, path, _body in calls)


def test_team_files_are_opaque_typed_and_deletable_without_paths():
    origin = next(iter(main.ASSISTANT_MUTATION_ALLOWED_ORIGINS))
    with _control_plane() as calls, _authenticated_client() as client:
        listed = client.get("/api/teams/team_one/files")
        uploaded = client.post(
            "/api/teams/team_one/files",
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers={"Origin": origin},
        )
        deleted = client.delete(
            f"/api/teams/team_one/files/{FILE_ID}",
            headers={"Origin": origin},
        )

    assert listed.status_code == uploaded.status_code == deleted.status_code == 200
    assert listed.json() == {
        "files": [
            {
                "id": FILE_ID,
                "name": "note.txt",
                "media_type": "text/plain",
                "size": 5,
                "sha256": FILE_SHA256,
                "created_at": 1_700_000_000,
            }
        ],
        **USAGE,
    }
    assert uploaded.json() == {
        "file": {
            "id": FILE_ID,
            "name": "note.txt",
            "media_type": "text/plain",
            "size": 5,
            "sha256": FILE_SHA256,
        },
        **USAGE,
    }
    assert deleted.json() == {"id": FILE_ID, "deleted": True, **USAGE}
    assert all("path" not in json.dumps(response.json()) for response in (listed, uploaded, deleted))

    upload_call = next(call for call in calls if call[:2] == ("POST", "/v1/teams/team_one/files"))
    assert upload_call[2] == {
        "filename": "note.txt",
        "media_type": "text/plain",
        "content_b64": base64.b64encode(b"hello").decode(),
    }
    assert ("GET", "/v1/teams/team_one/files", {}) in calls
    assert ("DELETE", f"/v1/teams/team_one/files/{FILE_ID}", {}) in calls


def test_team_file_mutations_reject_untrusted_origins_and_ids_before_the_driver():
    with _control_plane() as calls, _authenticated_client() as client:
        upload = client.post(
            "/api/teams/team_one/files",
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers={"Origin": "https://evil.example"},
        )
        deletion = client.delete(
            "/api/teams/team_one/files/not-an-opaque-id",
            headers={"Origin": next(iter(main.ASSISTANT_MUTATION_ALLOWED_ORIGINS))},
        )

    assert upload.status_code == 403
    assert deletion.status_code == 404
    assert not any(path.endswith("/files") or "/files/" in path for _method, path, _body in calls)


def test_storage_projection_keeps_cleanup_visible_after_a_future_plan_downgrade():
    assert main._public_storage_usage({"used_bytes": 8, "limit_bytes": 4, "remaining_bytes": 0}) == {
        "used_bytes": 8,
        "limit_bytes": 4,
        "remaining_bytes": 0,
    }
    assert main._public_storage_usage({"used_bytes": 8, "limit_bytes": 4, "remaining_bytes": 1}) is None

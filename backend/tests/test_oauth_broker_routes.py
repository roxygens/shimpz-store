from __future__ import annotations

from contextlib import contextmanager
from unittest import mock

from app import main
from app.oauth_broker import SCOPES
from fastapi.testclient import TestClient


class _Broker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def start(self, **values) -> str:
        self.calls.append(("start", values))
        return "https://dash.cloudflare.com/oauth2/auth?validated=1"

    def callback(self, **values) -> str:
        self.calls.append(("callback", values))
        return "http://127.0.0.1:7777/api/oauth/cloudflare/callback?state=" + "s" * 43 + "&claim=" + "a" * 64

    def claim(self, **values) -> dict[str, object]:
        self.calls.append(("claim", values))
        return {
            "access_token": "access-token-private-123456",
            "refresh_token": "refresh-token-private-123456",
            "expires_in": 3600,
            "scopes": list(SCOPES),
            "broker_lease": "lease-private-123456",
        }

    def refresh(self, **values) -> dict[str, object]:
        self.calls.append(("refresh", values))
        return {
            "access_token": "refreshed-access-token-private-123456",
            "refresh_token": "refreshed-refresh-token-private-123456",
            "expires_in": 3600,
            "scopes": list(SCOPES),
            "broker_lease": "refreshed-lease-private-123456",
        }

    def revoke(self, **values) -> None:
        self.calls.append(("revoke", values))


@contextmanager
def _broker():
    broker = _Broker()
    with mock.patch.object(main, "_OAUTH_BROKER", broker):
        yield broker


def test_browser_start_and_callback_redirect_without_oauth_tokens() -> None:
    with _broker() as broker, TestClient(main.app) as client:
        start = client.get(
            "/api/oauth/cloudflare/start",
            params={
                "state": "s" * 43,
                "code_challenge": "c" * 43,
                "scope": " ".join(SCOPES),
                "callback": "loopback",
            },
            follow_redirects=False,
        )
        callback = client.get(
            "/api/oauth/cloudflare/callback",
            params={"state": "b" * 43, "code": "authorization-code-private-123456"},
            follow_redirects=False,
        )

    assert start.status_code == 303
    assert start.headers["location"].startswith("https://dash.cloudflare.com/oauth2/auth?")
    assert callback.status_code == 303
    assert callback.headers["location"].startswith("http://127.0.0.1:7777/api/oauth/cloudflare/callback?")
    assert "access-token" not in callback.headers["location"]
    assert "refresh-token" not in callback.headers["location"]
    assert start.headers["cache-control"] == "private, no-store"
    assert callback.headers["referrer-policy"] == "no-referrer"
    assert [call[0] for call in broker.calls] == ["start", "callback"]
    assert broker.calls[0][1]["callback_mode"] == "loopback"


def test_server_only_claim_refresh_and_revoke_are_exact_and_no_store() -> None:
    with _broker() as broker, TestClient(main.app) as client:
        claim = client.post(
            "/api/oauth/cloudflare/claim",
            json={"claim": "a" * 64, "state": "s" * 43, "code_verifier": "v" * 43},
        )
        refresh = client.post(
            "/api/oauth/cloudflare/refresh",
            json={
                "refresh_token": "refresh-token-private-123456",
                "broker_lease": "lease-private-123456",
                "scopes": list(SCOPES),
            },
        )
        revoke = client.post(
            "/api/oauth/cloudflare/revoke",
            json={
                "token": "access-token-private-123456",
                "broker_lease": "lease-private-123456",
            },
        )

    assert claim.status_code == refresh.status_code == revoke.status_code == 200
    assert claim.headers["cache-control"] == "private, no-store"
    assert set(claim.json()) == {
        "access_token",
        "refresh_token",
        "expires_in",
        "scopes",
        "broker_lease",
    }
    assert revoke.json() == {"revoked": True}
    assert [call[0] for call in broker.calls] == ["claim", "refresh", "revoke"]


def test_token_routes_reject_browser_origin_duplicate_and_extra_fields() -> None:
    with _broker() as broker, TestClient(main.app) as client:
        browser = client.post(
            "/api/oauth/cloudflare/claim",
            headers={"Origin": "https://evil.example"},
            json={"claim": "a" * 64, "state": "s" * 43, "code_verifier": "v" * 43},
        )
        duplicate = client.post(
            "/api/oauth/cloudflare/claim",
            headers={"Content-Type": "application/json"},
            content=b'{"claim":"first","claim":"second","state":"'
            + b"s" * 43
            + b'","code_verifier":"'
            + b"v" * 43
            + b'"}',
        )
        extra = client.post(
            "/api/oauth/cloudflare/revoke",
            json={
                "token": "private-token-123456",
                "broker_lease": "private-lease-123456",
                "extra": True,
            },
        )

    assert browser.status_code == 403
    assert duplicate.status_code == 400
    assert extra.status_code == 400
    assert broker.calls == []

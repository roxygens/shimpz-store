from __future__ import annotations

import json
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from app.oauth_broker import (
    HOSTED_ADMIN_CALLBACK,
    HOSTED_CALLBACK,
    LOCAL_CALLBACK,
    SCOPES,
    BrokerLeaseSigner,
    BrokerResponse,
    NeuronOAuthClient,
    OAuthBroker,
    OAuthBrokerError,
    OAuthTokens,
    _pkce_challenge,
)


class _Transport:
    def __init__(self, responses: list[BrokerResponse]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    def request(self, **request) -> BrokerResponse:
        self.requests.append(request)
        return self.responses.pop(0)


class _Neuron:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def authorization(self, *, state: str, code_challenge: str) -> str:
        self.calls.append(("authorization", (state, code_challenge)))
        return "https://dash.cloudflare.com/oauth2/auth"

    def exchange(self, *, code: str, verifier: str) -> OAuthTokens:
        self.calls.append(("exchange", (code, verifier)))
        return OAuthTokens("access-token-private-123456", "refresh-token-private-123456", 3600)

    def refresh(self, *, refresh_token: str) -> OAuthTokens:
        self.calls.append(("refresh", refresh_token))
        return OAuthTokens("rotated-access-private-123456", "rotated-refresh-private-123456", 3600)

    def revoke(self, *, token: str) -> None:
        self.calls.append(("revoke", token))


def _secret(path: Path, value: bytes) -> Path:
    path.write_bytes(value)
    path.chmod(0o400)
    return path


def test_neuron_client_sends_access_service_identity_and_validates_fixed_authorization() -> None:
    state = "a" * 43
    challenge = "b" * 43
    authorization_url = "https://dash.cloudflare.com/oauth2/auth?" + urlencode(
        {
            "response_type": "code",
            "client_id": "cloudflare-client-id-123456",
            "redirect_uri": HOSTED_CALLBACK,
            "scope": " ".join(SCOPES),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    transport = _Transport(
        [
            BrokerResponse(
                200,
                "application/json",
                json.dumps({"authorization_url": authorization_url}).encode(),
            )
        ]
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        client = NeuronOAuthClient(
            transport,
            client_id_path=_secret(root / "id", ("c" * 32 + ".access").encode()),
            client_secret_path=_secret(root / "secret", b"service-token-private-material-123456"),
        )
        assert client.authorization(state=state, code_challenge=challenge) == authorization_url

    request = transport.requests[0]
    assert request["url"] == "https://neuron.shimpz.com/api/internal/oauth/cloudflare/authorization"
    assert request["headers"]["CF-Access-Client-Id"] == "c" * 32 + ".access"
    assert "CF-Access-Client-Secret" in request["headers"]
    assert "client_secret" not in request["body"].decode()


def test_broker_keeps_tokens_out_of_browser_and_claims_once_with_local_pkce() -> None:
    neuron = _Neuron()
    signer = BrokerLeaseSigner(b"k" * 32, clock=lambda: 1_800_000_000)
    broker = OAuthBroker(neuron, signer, clock=lambda: 100.0)
    local_verifier = "v" * 43
    local_state = "s" * 43

    authorization_url = broker.start(
        local_state=local_state,
        local_code_challenge=_pkce_challenge(local_verifier),
        callback_mode="loopback",
        scopes=list(SCOPES),
    )
    assert authorization_url == "https://dash.cloudflare.com/oauth2/auth"
    broker_state = neuron.calls[0][1][0]
    callback = broker.callback(state=broker_state, code="authorization-code-private-123456")
    parsed = urlsplit(callback)
    query = parse_qs(parsed.query, strict_parsing=True)
    assert callback.startswith(LOCAL_CALLBACK + "?")
    assert set(query) == {"state", "claim"}
    assert "access-token" not in callback
    assert "refresh-token" not in callback

    payload = broker.claim(claim=query["claim"][0], state=local_state, code_verifier=local_verifier)
    assert set(payload) == {
        "access_token",
        "refresh_token",
        "expires_in",
        "scopes",
        "broker_lease",
    }
    with pytest.raises(OAuthBrokerError):
        broker.claim(claim=query["claim"][0], state=local_state, code_verifier=local_verifier)

    refreshed = broker.refresh(
        refresh_token=payload["refresh_token"],
        lease=payload["broker_lease"],
        scopes=list(SCOPES),
    )
    broker.revoke(token=refreshed["access_token"], lease=refreshed["broker_lease"])
    assert [call[0] for call in neuron.calls] == [
        "authorization",
        "exchange",
        "refresh",
        "revoke",
    ]


def test_broker_returns_only_the_named_hosted_admin_callback() -> None:
    neuron = _Neuron()
    broker = OAuthBroker(neuron, BrokerLeaseSigner(b"k" * 32), clock=lambda: 100.0)
    broker.start(
        local_state="s" * 43,
        local_code_challenge="c" * 43,
        callback_mode="hosted",
        scopes=list(SCOPES),
    )
    state = neuron.calls[0][1][0]

    callback = broker.callback(state=state, code="authorization-code-private-123456")

    assert callback.startswith(HOSTED_ADMIN_CALLBACK + "?")
    with pytest.raises(OAuthBrokerError):
        broker.start(
            local_state="s" * 43,
            local_code_challenge="c" * 43,
            callback_mode="https://evil.example",
            scopes=list(SCOPES),
        )


def test_broker_rejects_wrong_pkce_tampered_lease_and_expired_state() -> None:
    neuron = _Neuron()
    now = [100.0]
    broker = OAuthBroker(
        neuron,
        BrokerLeaseSigner(b"k" * 32, clock=lambda: now[0]),
        clock=lambda: now[0],
    )
    verifier = "v" * 43
    broker.start(
        local_state="s" * 43,
        local_code_challenge=_pkce_challenge(verifier),
        callback_mode="loopback",
        scopes=list(SCOPES),
    )
    state = neuron.calls[0][1][0]
    callback = broker.callback(state=state, code="authorization-code-private-123456")
    claim = parse_qs(urlsplit(callback).query)["claim"][0]
    with pytest.raises(OAuthBrokerError):
        broker.claim(claim=claim, state="s" * 43, code_verifier="x" * 43)
    payload = broker.claim(claim=claim, state="s" * 43, code_verifier=verifier)
    with pytest.raises(OAuthBrokerError):
        broker.refresh(
            refresh_token=payload["refresh_token"],
            lease=str(payload["broker_lease"])[:-1] + "x",
            scopes=list(SCOPES),
        )

    broker.start(
        local_state="t" * 43,
        local_code_challenge=_pkce_challenge(verifier),
        callback_mode="loopback",
        scopes=list(SCOPES),
    )
    expired_state = neuron.calls[-1][1][0]
    now[0] += 301
    with pytest.raises(OAuthBrokerError):
        broker.callback(state=expired_state, code="authorization-code-private-123456")

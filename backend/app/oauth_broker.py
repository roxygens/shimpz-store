"""Short-lived hosted Cloudflare OAuth broker for self-hosted local Spaces."""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import stat
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit

NEURON_ORIGIN = "https://neuron.shimpz.com"
LOCAL_CALLBACK = "http://127.0.0.1:7777/api/oauth/cloudflare/callback"
CANARY_CALLBACK = "https://local.shimpz.com/api/oauth/cloudflare/callback"
CALLBACKS = {"loopback": LOCAL_CALLBACK, "canary": CANARY_CALLBACK}
HOSTED_CALLBACK = "https://shimpz.com/api/oauth/cloudflare/callback"
SCOPES = ("dns.read", "offline_access", "zone.read")
AUTHORIZATION_TTL_SECONDS = 300
GRANT_TTL_SECONDS = 90
LEASE_TTL_SECONDS = 366 * 24 * 60 * 60
CAPACITY = 4096
MAX_RESPONSE_BYTES = 32 * 1024
MAX_TOKEN_BYTES = 16 * 1024
HTTP_TIMEOUT_SECONDS = 10
ACCESS_CLIENT_ID_PATH = Path(
    os.environ.get("SHIMPZ_NEURON_ACCESS_CLIENT_ID_FILE", "/run/secrets/neuron_access_client_id")
)
ACCESS_CLIENT_SECRET_PATH = Path(
    os.environ.get(
        "SHIMPZ_NEURON_ACCESS_CLIENT_SECRET_FILE",
        "/run/secrets/neuron_access_client_secret",
    )
)
LEASE_KEY_PATH = Path(os.environ.get("SHIMPZ_OAUTH_BROKER_LEASE_KEY_FILE", "/run/secrets/oauth_broker_lease_key"))
_BINDING = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_CLAIM = re.compile(r"[0-9a-f]{64}\Z")
_SERVICE_CLIENT_ID = re.compile(r"[A-Za-z0-9_-]{16,128}\.access\Z")
_LEASE = re.compile(r"l1\.(\d{10})\.([A-Za-z0-9_-]{43})\.([A-Za-z0-9_-]{43})\.([A-Za-z0-9_-]{43})\Z")


class OAuthBrokerError(RuntimeError):
    """A hosted OAuth operation failed without reflecting private values."""


@dataclass(frozen=True, slots=True, repr=False)
class OAuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class _PendingAuthorization:
    local_state: str
    local_code_challenge: str
    callback_mode: str
    broker_verifier: str
    expires_at: float


@dataclass(frozen=True, slots=True, repr=False)
class _PendingGrant:
    local_state: str
    local_code_challenge: str
    tokens: OAuthTokens
    expires_at: float


@dataclass(frozen=True, slots=True)
class BrokerResponse:
    status: int
    content_type: str
    body: bytes


class BrokerTransport(Protocol):
    def request(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> BrokerResponse: ...


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _binding(value: object, label: str = "binding") -> str:
    if not isinstance(value, str) or _BINDING.fullmatch(value) is None:
        raise OAuthBrokerError(f"OAuth {label} is invalid")
    return value


def _callback_mode(value: object) -> str:
    if not isinstance(value, str) or value not in CALLBACKS:
        raise OAuthBrokerError("OAuth callback mode is invalid")
    return value


def _code(value: object, *, label: str, minimum: int = 16, maximum: int = 4096) -> str:
    if not isinstance(value, str):
        raise OAuthBrokerError(f"OAuth {label} is invalid")
    try:
        encoded = value.encode("ascii")
    except UnicodeError as exc:
        raise OAuthBrokerError(f"OAuth {label} is invalid") from exc
    if not minimum <= len(encoded) <= maximum or any(byte <= 32 or byte >= 127 for byte in encoded):
        raise OAuthBrokerError(f"OAuth {label} is invalid")
    return value


def _scopes(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or tuple(sorted(value)) != SCOPES or len(value) != len(set(value)):
        raise OAuthBrokerError("OAuth scopes are invalid")
    return SCOPES


def _pkce_challenge(verifier: str) -> str:
    return _base64url(hashlib.sha256(verifier.encode("ascii")).digest())


def _read_secret(path: Path, *, maximum: int, modes: frozenset[int]) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) not in modes
            or not 1 <= metadata.st_size <= maximum
        ):
            raise OAuthBrokerError("OAuth broker secret failed its file contract")
        payload = bytearray()
        while len(payload) <= maximum:
            chunk = os.read(descriptor, min(4096, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) != metadata.st_size:
            raise OAuthBrokerError("OAuth broker secret failed its file contract")
        return bytes(payload)
    except OSError as exc:
        raise OAuthBrokerError("OAuth broker secret is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


class FixedNeuronTransport:
    """Reach only the Access-protected Neuron OAuth operation API."""

    def request(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> BrokerResponse:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "neuron.shimpz.com"
            or parsed.port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/api/internal/oauth/cloudflare/")
        ):
            raise OAuthBrokerError("Neuron OAuth endpoint is invalid")
        connection = http.client.HTTPSConnection(parsed.hostname, timeout=HTTP_TIMEOUT_SECONDS)
        try:
            connection.request("POST", parsed.path, body=body, headers=dict(headers))
            response = connection.getresponse()
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise OAuthBrokerError("Neuron OAuth response is invalid")
            return BrokerResponse(response.status, response.getheader("Content-Type", ""), payload)
        except OAuthBrokerError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise OAuthBrokerError("Neuron OAuth service is unavailable") from exc
        finally:
            connection.close()


class NeuronOAuthClient:
    """Use one Access service token without ever receiving the OAuth Client Secret."""

    def __init__(
        self,
        transport: BrokerTransport | None = None,
        *,
        client_id_path: Path = ACCESS_CLIENT_ID_PATH,
        client_secret_path: Path = ACCESS_CLIENT_SECRET_PATH,
    ) -> None:
        self._transport = transport or FixedNeuronTransport()
        self._client_id_path = client_id_path
        self._client_secret_path = client_secret_path

    def _access_headers(self) -> dict[str, str]:
        try:
            client_id = _read_secret(
                self._client_id_path,
                maximum=256,
                modes=frozenset({0o400, 0o440, 0o444, 0o600, 0o640}),
            ).decode("ascii")
            client_secret = _read_secret(
                self._client_secret_path,
                maximum=1024,
                modes=frozenset({0o400, 0o440, 0o444, 0o600, 0o640}),
            ).decode("ascii")
        except UnicodeError as exc:
            raise OAuthBrokerError("Neuron Access service credential is invalid") from exc
        if _SERVICE_CLIENT_ID.fullmatch(client_id) is None:
            raise OAuthBrokerError("Neuron Access service credential is invalid")
        _code(client_secret, label="service credential", minimum=32, maximum=1024)
        return {
            "CF-Access-Client-Id": client_id,
            "CF-Access-Client-Secret": client_secret,
        }

    @staticmethod
    def _object(response: BrokerResponse) -> dict[str, object]:
        if response.status != 200 or response.content_type.lower().split(";", 1)[0].strip() != "application/json":
            raise OAuthBrokerError("Neuron OAuth operation failed")

        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise OAuthBrokerError("Neuron OAuth response is invalid")
                result[key] = value
            return result

        try:
            value = json.loads(response.body, object_pairs_hook=unique)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OAuthBrokerError("Neuron OAuth response is invalid") from exc
        if not isinstance(value, dict):
            raise OAuthBrokerError("Neuron OAuth response is invalid")
        return value

    def _call(self, operation: str, payload: dict[str, object]) -> dict[str, object]:
        if operation not in {"authorization", "exchange", "refresh", "revoke"}:
            raise OAuthBrokerError("Neuron OAuth operation is invalid")
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        headers = {
            **self._access_headers(),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "User-Agent": "shimpz-oauth-broker/1",
        }
        return self._object(
            self._transport.request(
                url=f"{NEURON_ORIGIN}/api/internal/oauth/cloudflare/{operation}",
                headers=headers,
                body=body,
            )
        )

    def authorization(self, *, state: str, code_challenge: str) -> str:
        value = self._call(
            "authorization",
            {"state": state, "code_challenge": code_challenge, "scopes": list(SCOPES)},
        )
        if set(value) != {"authorization_url"}:
            raise OAuthBrokerError("Neuron OAuth response is invalid")
        url = value.get("authorization_url")
        if not isinstance(url, str) or len(url) > 4096:
            raise OAuthBrokerError("Neuron OAuth response is invalid")
        parsed = urlsplit(url)
        try:
            query = parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=7,
            )
        except ValueError as exc:
            raise OAuthBrokerError("Neuron OAuth response is invalid") from exc
        fields = dict(query)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "dash.cloudflare.com"
            or parsed.port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/oauth2/auth"
            or parsed.fragment
            or len(query) != 7
            or len(fields) != 7
            or fields.get("response_type") != "code"
            or fields.get("redirect_uri") != HOSTED_CALLBACK
            or fields.get("state") != state
            or fields.get("code_challenge") != code_challenge
            or fields.get("code_challenge_method") != "S256"
            or fields.get("scope") != " ".join(SCOPES)
            or not _code(fields.get("client_id"), label="client id", minimum=8, maximum=256)
        ):
            raise OAuthBrokerError("Neuron OAuth response is invalid")
        return url

    @staticmethod
    def _tokens(value: dict[str, object]) -> OAuthTokens:
        if set(value) != {"access_token", "refresh_token", "scopes", "expires_in"}:
            raise OAuthBrokerError("Neuron OAuth response is invalid")
        _scopes(value.get("scopes"))
        expires = value.get("expires_in")
        if type(expires) is not int or not 30 <= expires <= 31_536_000:
            raise OAuthBrokerError("Neuron OAuth response is invalid")
        return OAuthTokens(
            _code(
                value.get("access_token"),
                label="token",
                minimum=16,
                maximum=MAX_TOKEN_BYTES,
            ),
            _code(
                value.get("refresh_token"),
                label="token",
                minimum=16,
                maximum=MAX_TOKEN_BYTES,
            ),
            expires,
        )

    def exchange(self, *, code: str, verifier: str) -> OAuthTokens:
        return self._tokens(
            self._call(
                "exchange",
                {"code": code, "code_verifier": verifier, "scopes": list(SCOPES)},
            )
        )

    def refresh(self, *, refresh_token: str) -> OAuthTokens:
        return self._tokens(
            self._call(
                "refresh",
                {"refresh_token": refresh_token, "scopes": list(SCOPES)},
            )
        )

    def revoke(self, *, token: str) -> None:
        if self._call("revoke", {"token": token}) != {"revoked": True}:
            raise OAuthBrokerError("Neuron OAuth response is invalid")


class BrokerLeaseSigner:
    """Issue a bounded proof that tokens came from one successful broker claim."""

    def __init__(
        self,
        key: bytes | None = None,
        *,
        key_path: Path = LEASE_KEY_PATH,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._provided_key = key
        self._key_path = key_path
        self._clock = clock

    def _key(self) -> bytes:
        key = self._provided_key or _read_secret(
            self._key_path,
            maximum=32,
            modes=frozenset({0o400, 0o440, 0o444, 0o600, 0o640}),
        )
        if len(key) != 32:
            raise OAuthBrokerError("OAuth broker lease key is unavailable")
        return key

    @staticmethod
    def _digest(token: str) -> str:
        return _base64url(hashlib.sha256(token.encode("ascii")).digest())

    def issue(self, tokens: OAuthTokens) -> str:
        expires = int(self._clock()) + LEASE_TTL_SECONDS
        payload = f"l1.{expires}.{self._digest(tokens.access_token)}.{self._digest(tokens.refresh_token)}"
        signature = _base64url(hmac.new(self._key(), payload.encode("ascii"), hashlib.sha256).digest())
        return f"{payload}.{signature}"

    def verify(self, lease: object, token: str) -> None:
        if not isinstance(lease, str):
            raise OAuthBrokerError("OAuth broker lease is invalid")
        match = _LEASE.fullmatch(lease)
        if match is None:
            raise OAuthBrokerError("OAuth broker lease is invalid")
        expires, access_digest, refresh_digest, supplied = match.groups()
        payload = lease.rsplit(".", 1)[0]
        expected = _base64url(hmac.new(self._key(), payload.encode("ascii"), hashlib.sha256).digest())
        digest = self._digest(token)
        if (
            int(expires) <= int(self._clock())
            or not hmac.compare_digest(expected, supplied)
            or not any(hmac.compare_digest(digest, allowed) for allowed in (access_digest, refresh_digest))
        ):
            raise OAuthBrokerError("OAuth broker lease is invalid")


class OAuthBroker:
    """Bind one hosted provider exchange to one local PKCE verifier and one-use claim."""

    def __init__(
        self,
        neuron: NeuronOAuthClient | None = None,
        signer: BrokerLeaseSigner | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._neuron = neuron or NeuronOAuthClient()
        self._signer = signer or BrokerLeaseSigner()
        self._clock = clock
        self._authorizations: dict[str, _PendingAuthorization] = {}
        self._grants: dict[str, _PendingGrant] = {}
        self._grant_reservations = 0
        self._lock = threading.Lock()

    def _expire(self, now: float) -> None:
        for key in tuple(key for key, value in self._authorizations.items() if value.expires_at <= now):
            self._authorizations.pop(key, None)
        for key in tuple(key for key, value in self._grants.items() if value.expires_at <= now):
            self._grants.pop(key, None)

    @staticmethod
    def _random_binding() -> str:
        return secrets.token_urlsafe(32)

    def start(
        self,
        *,
        local_state: object,
        local_code_challenge: object,
        callback_mode: object,
        scopes: object,
    ) -> str:
        state = _binding(local_state, "state")
        challenge = _binding(local_code_challenge, "challenge")
        callback = _callback_mode(callback_mode)
        _scopes(scopes)
        now = self._clock()
        broker_state = self._random_binding()
        verifier = self._random_binding()
        with self._lock:
            self._expire(now)
            if len(self._authorizations) >= CAPACITY:
                raise OAuthBrokerError("OAuth broker capacity is unavailable")
            while broker_state in self._authorizations:
                broker_state = self._random_binding()
            self._authorizations[broker_state] = _PendingAuthorization(
                state,
                challenge,
                callback,
                verifier,
                now + AUTHORIZATION_TTL_SECONDS,
            )
        try:
            return self._neuron.authorization(
                state=broker_state,
                code_challenge=_pkce_challenge(verifier),
            )
        except OAuthBrokerError:
            with self._lock:
                self._authorizations.pop(broker_state, None)
            raise

    def callback(self, *, state: object, code: object) -> str:
        broker_state = _binding(state, "state")
        authorization_code = _code(code, label="code")
        now = self._clock()
        with self._lock:
            self._expire(now)
            if len(self._grants) + self._grant_reservations >= CAPACITY:
                raise OAuthBrokerError("OAuth broker capacity is unavailable")
            pending = self._authorizations.pop(broker_state, None)
            if pending is not None:
                self._grant_reservations += 1
        if pending is None:
            raise OAuthBrokerError("OAuth authorization is unavailable")
        try:
            tokens = self._neuron.exchange(code=authorization_code, verifier=pending.broker_verifier)
        except BaseException:
            with self._lock:
                self._grant_reservations -= 1
            raise
        claim = secrets.token_hex(32)
        with self._lock:
            self._expire(now)
            self._grant_reservations -= 1
            while claim in self._grants:
                claim = secrets.token_hex(32)
            self._grants[claim] = _PendingGrant(
                pending.local_state,
                pending.local_code_challenge,
                tokens,
                now + GRANT_TTL_SECONDS,
            )
        return CALLBACKS[pending.callback_mode] + "?" + urlencode({"state": pending.local_state, "claim": claim})

    def claim(self, *, claim: object, state: object, code_verifier: object) -> dict[str, object]:
        if not isinstance(claim, str) or _CLAIM.fullmatch(claim) is None:
            raise OAuthBrokerError("OAuth grant is unavailable")
        local_state = _binding(state, "state")
        verifier = _code(code_verifier, label="verifier", minimum=43, maximum=128)
        now = self._clock()
        with self._lock:
            self._expire(now)
            pending = self._grants.get(claim)
            if (
                pending is None
                or not hmac.compare_digest(pending.local_state, local_state)
                or not hmac.compare_digest(pending.local_code_challenge, _pkce_challenge(verifier))
            ):
                raise OAuthBrokerError("OAuth grant is unavailable")
            self._grants.pop(claim, None)
        return self._token_payload(pending.tokens)

    def _token_payload(self, tokens: OAuthTokens) -> dict[str, object]:
        return {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_in": tokens.expires_in,
            "scopes": list(SCOPES),
            "broker_lease": self._signer.issue(tokens),
        }

    def refresh(self, *, refresh_token: object, lease: object, scopes: object) -> dict[str, object]:
        _scopes(scopes)
        token = _code(refresh_token, label="token", minimum=16, maximum=MAX_TOKEN_BYTES)
        self._signer.verify(lease, token)
        return self._token_payload(self._neuron.refresh(refresh_token=token))

    def revoke(self, *, token: object, lease: object) -> None:
        value = _code(token, label="token", minimum=16, maximum=MAX_TOKEN_BYTES)
        self._signer.verify(lease, value)
        self._neuron.revoke(token=value)

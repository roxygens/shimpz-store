"""Canonical, metadata-only Assistant release feed.

The public Store feed is deliberately not an installation authority. It carries
only bounded notification copy; executable images and installation commands remain
outside this contract. The canonical body and ETag are built once while the process
imports this module, so invalid release data fails startup and every request is
allocation-light.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime

ASSISTANT_RELEASE_CACHE_CONTROL = "public, max-age=60, s-maxage=300, stale-while-revalidate=86400"
MAX_RELEASES = 256
MAX_ASSISTANT_ID_CHARS = 80
MAX_HEADLINE_BYTES = 160
MAX_CHANGELOG_BYTES = 32 * 1024
MAX_FEED_BYTES = 512 * 1024
MAX_SEQUENCE = (1 << 63) - 1

_RELEASE_FIELDS = frozenset({"assistant_id", "sequence", "headline", "changelog", "published_at"})
_ASSISTANT_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_PUBLISHED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_EXECUTABLE_REFERENCE_RE = re.compile(
    r"(?:sha256:[0-9a-f]{64}|\bdocker\s+(?:pull|run|compose)\b|"
    r"\b(?:curl|wget)\b[^\r\n|]{0,512}\|\s*(?:ba)?sh\b)",
    re.IGNORECASE,
)
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

# This binding is intentionally private: it lets repository checks prove that
# notification copy was reviewed with the exact Assistant source while keeping
# executable identity out of the public feed.
_CANONICAL_RELEASE_SOURCE_COMMITS = {
    "shimpz-assistant": "c46f83c45418a832052fededafcab616ce37579c",
    "shimpz-cloudflare": "095fca97b78132d6f6f3271ecbc4547e16edee73",
}

_SHIMPZ_CLOUDFLARE_0_1_5_CHANGELOG = """# Changelog

## 0.1.5 - 2026-07-21

- Reassemble bounded chunked Cloudflare responses before strict JSON validation.

## 0.1.4 - 2026-07-21

- Request uncompressed Cloudflare API responses so the strict response contract can validate zone and DNS results.

## 0.1.3 - 2026-07-21

- Make the Python 3.14 Ruff format and security contract self-contained for isolated builds.

## 0.1.2 - 2026-07-21

- Synchronize frozen release metadata and enforce the canonical Ruff contract.

## 0.1.1 - 2026-07-21

- Align the immutable Genesis and Help package root with the controller's standard Assistant contract.

## 0.1.0 - 2026-07-21

- Add OAuth-backed, read-only Cloudflare zone listing.
- Add bounded DNS record listing for an exact zone.
"""

_SHIMPZ_CLOUDFLARE_0_1_4_CHANGELOG = """# Changelog

## 0.1.4 - 2026-07-21

- Request uncompressed Cloudflare API responses so the strict response contract can validate zone and DNS results.

## 0.1.3 - 2026-07-21

- Make the Python 3.14 Ruff format and security contract self-contained for isolated builds.

## 0.1.2 - 2026-07-21

- Synchronize frozen release metadata and enforce the canonical Ruff contract.

## 0.1.1 - 2026-07-21

- Align the immutable Genesis and Help package root with the controller's standard Assistant contract.

## 0.1.0 - 2026-07-21

- Add OAuth-backed, read-only Cloudflare zone listing.
- Add bounded DNS record listing for an exact zone.
"""

_SHIMPZ_CLOUDFLARE_0_1_3_CHANGELOG = """# Changelog

## 0.1.3 - 2026-07-21

- Make the Python 3.14 Ruff format and security contract self-contained for isolated builds.

## 0.1.2 - 2026-07-21

- Synchronize frozen release metadata and enforce the canonical Ruff contract.

## 0.1.1 - 2026-07-21

- Align the immutable Genesis and Help package root with the controller's standard Assistant contract.

## 0.1.0 - 2026-07-21

- Add OAuth-backed, read-only Cloudflare zone listing.
- Add bounded DNS record listing for an exact zone.
"""

_SHIMPZ_ASSISTANT_0_6_0_CHANGELOG = """# Changelog

## 0.6.0

- Updated repository and image-source metadata for the TheShimpz organization.
- Renamed provider authorization from Connections to Accounts throughout the Assistant contract.
- Added three just-in-time Mux BYOK Secrets with exact per-Power references.
- Added bounded direct-upload list, test-create, and cancel Powers against only `api.mux.com`.
- Added network-free Mux webhook verification with raw-body HMAC-SHA256, constant-time comparison, and freshness checks.
- Kept all credentials out of source, schemas, logs, Help, Genesis, and Power outputs.

## 0.5.0

- Enabled the reviewed controller-owned X OAuth 2.0 Authorization Code flow with S256 PKCE.
- Added the Admin consent handoff that pauses the first Power needing X and resumes it after authorization.
- Released the four typed X Powers behind the exact `api.x.com` egress boundary without collecting \
developer credentials or tokens.
- Kept OAuth consent separate from the explicit approval required for every publish or delete action.

## 0.4.0

- Declared one controller-owned X OAuth Account shared only by the four referencing Powers.
- Added the fixed-host OAuth bearer runtime without accepting refresh tokens or developer credentials.
- Kept Store publication blocked until the controller PKCE broker is available.

## 0.3.0

- Removed developer credentials and access tokens from Assistant secrets.
- Locked X Powers until the Admin and controller can broker user-authorized OAuth 2.0 with S256 PKCE.

## 0.2.1

- Delegated X's weighted Post-length and normalization rules to X while retaining a strict local byte bound.

## 0.2.0

- Replaced the weather demonstration with real, typed X profile and Post Powers.
- Added isolated declarations for one Bearer Token and four OAuth 1.0a credentials.
- Restricted all outbound requests to `api.x.com` and made every Post write require explicit approval.
- Added strict runtime, RPC, redaction, redirect, timeout, and response-boundary validation for the X integration.
- Made the release source pass the repository-wide no-inline-suppression security gate without exceptions.
- Bound the private RPC adapter to the fixed Assistant package root inside its hardened image.
- Aligned the Python source with the repository formatting gate.

## 0.1.2

- Shows that the Assistant can provide forecasts for up to 16 days in the English in-Admin help.

## 0.1.1

- Identifies outbound Open-Meteo requests with the exact Assistant patch version.

## 0.1.0

- Added three typed Open-Meteo Powers for location search, current weather, and daily forecasts.
- Added localized in-Admin help and a bounded Genesis playbook for the Team Brain.
"""

# Append releases in increasing sequence order for each Assistant. This source is
# intentionally code reviewed alongside the Store instead of being downloaded from
# another service at runtime.
_CANONICAL_RELEASES = (
    {
        "assistant_id": "shimpz-assistant",
        "sequence": 1,
        "headline": "Shimpz Assistant is ready",
        "changelog": (
            "# Changelog\n\n"
            "## 0.1.0\n\n"
            "- Added three typed Open-Meteo Powers for location search, current "
            "weather, and daily forecasts.\n"
            "- Added localized in-Admin help and a bounded Genesis playbook for "
            "the Team Brain.\n"
        ),
        "published_at": "2026-07-19T00:00:00Z",
    },
    {
        "assistant_id": "shimpz-assistant",
        "sequence": 2,
        "headline": "Shimpz Assistant 0.1.1 is available",
        "changelog": (
            "# Changelog\n\n"
            "## 0.1.1\n\n"
            "- Identifies outbound Open-Meteo requests with the exact Assistant "
            "patch version.\n\n"
            "## 0.1.0\n\n"
            "- Added three typed Open-Meteo Powers for location search, current "
            "weather, and daily forecasts.\n"
            "- Added localized in-Admin help and a bounded Genesis playbook for "
            "the Team Brain.\n"
        ),
        "published_at": "2026-07-19T20:22:42Z",
    },
    {
        "assistant_id": "shimpz-assistant",
        "sequence": 3,
        "headline": "Shimpz Assistant 0.1.2 is available",
        "changelog": (
            "# Changelog\n\n"
            "## 0.1.2\n\n"
            "- Shows that the Assistant can provide forecasts for up to 16 days "
            "in the English in-Admin help.\n\n"
            "## 0.1.1\n\n"
            "- Identifies outbound Open-Meteo requests with the exact Assistant "
            "patch version.\n\n"
            "## 0.1.0\n\n"
            "- Added three typed Open-Meteo Powers for location search, current "
            "weather, and daily forecasts.\n"
            "- Added localized in-Admin help and a bounded Genesis playbook for "
            "the Team Brain.\n"
        ),
        "published_at": "2026-07-19T23:37:30Z",
    },
    {
        "assistant_id": "shimpz-assistant",
        "sequence": 4,
        "headline": "Shimpz Assistant 0.2.0 is available",
        "changelog": (
            "# Changelog\n\n"
            "## 0.2.0\n\n"
            "- Replaced the weather demonstration with real, typed X profile and "
            "Post Powers.\n"
            "- Added isolated declarations for one Bearer Token and four OAuth "
            "1.0a credentials.\n"
            "- Restricted all outbound requests to `api.x.com` and made every "
            "Post write require explicit approval.\n"
            "- Added strict runtime, RPC, redaction, redirect, timeout, and "
            "response-boundary validation for the "
            "X integration.\n"
            "- Made the release source pass the repository-wide "
            "no-inline-suppression security gate without "
            "exceptions.\n"
            "- Bound the private RPC adapter to the fixed Assistant package root "
            "inside its hardened image.\n"
            "- Aligned the Python source with the repository formatting gate.\n\n"
            "## 0.1.2\n\n"
            "- Shows that the Assistant can provide forecasts for up to 16 days "
            "in the English in-Admin help.\n\n"
            "## 0.1.1\n\n"
            "- Identifies outbound Open-Meteo requests with the exact Assistant "
            "patch version.\n\n"
            "## 0.1.0\n\n"
            "- Added three typed Open-Meteo Powers for location search, current "
            "weather, and daily forecasts.\n"
            "- Added localized in-Admin help and a bounded Genesis playbook for "
            "the Team Brain.\n"
        ),
        "published_at": "2026-07-20T05:10:32Z",
    },
    {
        "assistant_id": "shimpz-assistant",
        "sequence": 5,
        "headline": "Shimpz Assistant 0.5.0 connects to X safely",
        "changelog": (
            "# Changelog\n\n"
            "## 0.5.0\n\n"
            "- Enabled the reviewed controller-owned X OAuth 2.0 Authorization "
            "Code flow with S256 PKCE.\n"
            "- Added the Admin consent handoff that pauses the first Power "
            "needing X and resumes it after authorization.\n"
            "- Released the four typed X Powers behind the exact `api.x.com` "
            "egress boundary without collecting developer credentials or "
            "tokens.\n"
            "- Kept OAuth consent separate from the explicit approval required "
            "for every publish or delete action.\n\n"
            "## 0.4.0\n\n"
            "- Declared one controller-owned X OAuth Account shared only by "
            "the four referencing Powers.\n"
            "- Added the fixed-host OAuth bearer runtime without accepting "
            "refresh tokens or developer credentials.\n"
            "- Kept Store publication blocked until the controller PKCE broker "
            "is available.\n\n"
            "## 0.3.0\n\n"
            "- Removed developer credentials and access tokens from Assistant "
            "secrets.\n"
            "- Locked X Powers until the Admin and controller can broker "
            "user-authorized OAuth 2.0 with S256 PKCE.\n\n"
            "## 0.2.1\n\n"
            "- Delegated X's weighted Post-length and normalization rules to X "
            "while retaining a strict local byte bound.\n\n"
            "## 0.2.0\n\n"
            "- Replaced the weather demonstration with real, typed X profile and "
            "Post Powers.\n"
            "- Added isolated declarations for one Bearer Token and four OAuth "
            "1.0a credentials.\n"
            "- Restricted all outbound requests to `api.x.com` and made every "
            "Post write require explicit approval.\n"
            "- Added strict runtime, RPC, redaction, redirect, timeout, and "
            "response-boundary validation for the X integration.\n"
            "- Made the release source pass the repository-wide "
            "no-inline-suppression security gate without exceptions.\n"
            "- Bound the private RPC adapter to the fixed Assistant package root "
            "inside its hardened image.\n"
            "- Aligned the Python source with the repository formatting gate.\n\n"
            "## 0.1.2\n\n"
            "- Shows that the Assistant can provide forecasts for up to 16 days "
            "in the English in-Admin help.\n\n"
            "## 0.1.1\n\n"
            "- Identifies outbound Open-Meteo requests with the exact Assistant "
            "patch version.\n\n"
            "## 0.1.0\n\n"
            "- Added three typed Open-Meteo Powers for location search, current "
            "weather, and daily forecasts.\n"
            "- Added localized in-Admin help and a bounded Genesis playbook for "
            "the Team Brain.\n"
        ),
        "published_at": "2026-07-20T09:24:45Z",
    },
    {
        "assistant_id": "shimpz-assistant",
        "sequence": 6,
        "headline": "Shimpz Assistant 0.6.0 adds Accounts and Mux BYOK",
        "changelog": _SHIMPZ_ASSISTANT_0_6_0_CHANGELOG,
        "published_at": "2026-07-20T15:00:00Z",
    },
    {
        "assistant_id": "shimpz-cloudflare",
        "sequence": 1,
        "headline": "Shimpz Cloudflare 0.1.3 is ready",
        "changelog": _SHIMPZ_CLOUDFLARE_0_1_3_CHANGELOG,
        "published_at": "2026-07-21T05:43:00Z",
    },
    {
        "assistant_id": "shimpz-cloudflare",
        "sequence": 2,
        "headline": "Shimpz Cloudflare 0.1.4 fixes strict provider transport",
        "changelog": _SHIMPZ_CLOUDFLARE_0_1_4_CHANGELOG,
        "published_at": "2026-07-22T01:09:04Z",
    },
    {
        "assistant_id": "shimpz-cloudflare",
        "sequence": 3,
        "headline": "Shimpz Cloudflare 0.1.5 supports bounded chunked responses",
        "changelog": _SHIMPZ_CLOUDFLARE_0_1_5_CHANGELOG,
        "published_at": "2026-07-22T01:35:00Z",
    },
)


def _valid_text(value: object, *, max_bytes: int, multiline: bool) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > max_bytes:
        return False
    allowed_controls = {"\n", "\t"} if multiline else set()
    return not any(
        (ord(character) < 32 and character not in allowed_controls) or ord(character) == 127 for character in value
    )


def _validated_published_at(value: object, position: int) -> str:
    if not isinstance(value, str) or _PUBLISHED_AT_RE.fullmatch(value) is None:
        raise ValueError(f"Assistant release {position} has an invalid published_at")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"Assistant release {position} has an invalid published_at") from exc
    return value


def _validated_release(raw: object, position: int, previous_sequence: dict[str, int]) -> dict[str, object]:
    if not isinstance(raw, dict) or set(raw) != _RELEASE_FIELDS:
        raise ValueError(f"Assistant release {position} has an invalid field set")

    assistant_id = raw["assistant_id"]
    sequence = raw["sequence"]
    headline = raw["headline"]
    changelog = raw["changelog"]
    if (
        not isinstance(assistant_id, str)
        or len(assistant_id) > MAX_ASSISTANT_ID_CHARS
        or _ASSISTANT_ID_RE.fullmatch(assistant_id) is None
    ):
        raise ValueError(f"Assistant release {position} has an invalid assistant_id")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or not 1 <= sequence <= MAX_SEQUENCE:
        raise ValueError(f"Assistant release {position} has an invalid sequence")
    if sequence <= previous_sequence.get(assistant_id, 0):
        raise ValueError(f"Assistant {assistant_id} release sequence is not increasing")
    if not _valid_text(headline, max_bytes=MAX_HEADLINE_BYTES, multiline=False):
        raise ValueError(f"Assistant release {position} has an invalid headline")
    if not _valid_text(changelog, max_bytes=MAX_CHANGELOG_BYTES, multiline=True):
        raise ValueError(f"Assistant release {position} has an invalid changelog")
    if any(_EXECUTABLE_REFERENCE_RE.search(value) is not None for value in (headline, changelog)):
        raise ValueError(f"Assistant release {position} contains executable installation metadata")

    previous_sequence[assistant_id] = sequence
    return {
        "assistant_id": assistant_id,
        "sequence": sequence,
        "headline": headline,
        "changelog": changelog,
        "published_at": _validated_published_at(raw["published_at"], position),
    }


def _validate_release_records(source: object) -> tuple[dict[str, object], ...]:
    """Return a closed, copied release sequence or reject the complete feed."""
    if not isinstance(source, (tuple, list)) or not 1 <= len(source) <= MAX_RELEASES:
        raise ValueError(f"Assistant release feed must contain 1..{MAX_RELEASES} records")

    previous_sequence: dict[str, int] = {}
    return tuple(_validated_release(raw, position, previous_sequence) for position, raw in enumerate(source))


def _validate_release_source_commits(source: object, releases: object) -> None:
    """Reject an invalid or incomplete private release-source binding."""
    if not isinstance(source, dict) or not isinstance(releases, (tuple, list)):
        raise ValueError("Assistant release source binding is invalid")
    assistant_ids = {release.get("assistant_id") for release in releases if isinstance(release, dict)}
    if set(source) != assistant_ids or any(
        not isinstance(commit, str) or _GIT_COMMIT_RE.fullmatch(commit) is None for commit in source.values()
    ):
        raise ValueError("Assistant release source binding is incomplete or invalid")


def _build_feed(source: object) -> tuple[bytes, str]:
    releases = _validate_release_records(source)
    body = json.dumps(
        {"schema_version": 1, "releases": releases},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(body) > MAX_FEED_BYTES:
        raise ValueError(f"Assistant release feed exceeds {MAX_FEED_BYTES} bytes")
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    return body, etag


def if_none_match_matches(value: str | None, etag: str) -> bool:
    """Weakly match one bounded If-None-Match header for a safe GET."""
    if value is None or len(value) > 4096:
        return False
    for candidate in value.split(","):
        candidate = candidate.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:].strip()
        if candidate == etag:
            return True
    return False


_validate_release_source_commits(_CANONICAL_RELEASE_SOURCE_COMMITS, _CANONICAL_RELEASES)
ASSISTANT_RELEASE_FEED_BODY, ASSISTANT_RELEASE_FEED_ETAG = _build_feed(_CANONICAL_RELEASES)

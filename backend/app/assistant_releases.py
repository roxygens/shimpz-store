"""Canonical, metadata-only Assistant release feed.

The public Store feed is deliberately not an installation authority. It carries
only bounded notification copy; executable images and installation commands remain
outside this contract. The canonical body and ETag are built once while the process
imports this module, while repository tests validate the reviewed literals.
"""

from __future__ import annotations

import hashlib
import json

ASSISTANT_RELEASE_CACHE_CONTROL = "public, max-age=60, s-maxage=300, stale-while-revalidate=86400"

# This binding is intentionally private: it lets repository checks prove that
# notification copy was reviewed with the exact Assistant source while keeping
# executable identity out of the public feed.
_CANONICAL_RELEASE_SOURCE_COMMITS = {
    "shimpz-cloudflare": "2fd76d18ae421286444f3e005fa81edcacfc6055",
}

_SHIMPZ_CLOUDFLARE_CHANGELOG_ENTRIES = (
    """## 0.2.1 - 2026-07-23

- Generate the reviewed Power contract from source during the image build and keep the generated file read-only.
- Remove unverifiable SDK provenance metadata from the Assistant package.""",
    """## 0.2.0 - 2026-07-23

- Author both read-only Powers with `@power`, `field`, typed SDK output contracts, and `ctx.accounts`.
- Replace the persistent Assistant server and proxy RPC with the one-shot Shimpz SDK runner.
- Bind image builds to the reviewed SDK source tree carried by the umbrella repository.""",
    """## 0.1.5 - 2026-07-21

- Reassemble bounded chunked Cloudflare responses before strict JSON validation.""",
    """## 0.1.4 - 2026-07-21

- Request uncompressed Cloudflare API responses so the strict response contract can validate zone and DNS results.""",
    """## 0.1.3 - 2026-07-21

- Make the Python 3.14 Ruff format and security contract self-contained for isolated builds.""",
    """## 0.1.2 - 2026-07-21

- Synchronize frozen release metadata and enforce the canonical Ruff contract.""",
    """## 0.1.1 - 2026-07-21

- Align the immutable Genesis and Help package root with the controller's standard Assistant contract.""",
    """## 0.1.0 - 2026-07-21

- Add OAuth-backed, read-only Cloudflare zone listing.
- Add bounded DNS record listing for an exact zone.""",
)


def _cumulative_changelog(first_entry: int) -> str:
    return "# Changelog\n\n" + "\n\n".join(_SHIMPZ_CLOUDFLARE_CHANGELOG_ENTRIES[first_entry:]) + "\n"


# Append releases in increasing sequence order for each Assistant. This source is
# intentionally code reviewed alongside the Store instead of being downloaded from
# another service at runtime.
_CANONICAL_RELEASES = (
    {
        "assistant_id": "shimpz-cloudflare",
        "sequence": 1,
        "headline": "Shimpz Cloudflare 0.1.3 is ready",
        "changelog": _cumulative_changelog(4),
        "published_at": "2026-07-21T05:43:00Z",
    },
    {
        "assistant_id": "shimpz-cloudflare",
        "sequence": 2,
        "headline": "Shimpz Cloudflare 0.1.4 fixes strict provider transport",
        "changelog": _cumulative_changelog(3),
        "published_at": "2026-07-22T01:09:04Z",
    },
    {
        "assistant_id": "shimpz-cloudflare",
        "sequence": 3,
        "headline": "Shimpz Cloudflare 0.1.5 supports bounded chunked responses",
        "changelog": _cumulative_changelog(2),
        "published_at": "2026-07-22T01:35:00Z",
    },
    {
        "assistant_id": "shimpz-cloudflare",
        "sequence": 4,
        "headline": "Shimpz Cloudflare 0.2.0 now runs on the Shimpz SDK",
        "changelog": _cumulative_changelog(1),
        "published_at": "2026-07-23T09:40:00Z",
    },
    {
        "assistant_id": "shimpz-cloudflare",
        "sequence": 5,
        "headline": "Shimpz Cloudflare 0.2.1 generates its reviewed contract",
        "changelog": _cumulative_changelog(0),
        "published_at": "2026-07-23T16:50:54Z",
    },
)


def _build_feed(releases: tuple[dict[str, object], ...]) -> tuple[bytes, str]:
    body = json.dumps(
        {"schema_version": 1, "releases": releases},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
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


ASSISTANT_RELEASE_FEED_BODY, ASSISTANT_RELEASE_FEED_ETAG = _build_feed(_CANONICAL_RELEASES)

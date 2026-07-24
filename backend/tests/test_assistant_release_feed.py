import copy
import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import assistant_releases as releases
from app.main import app

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
    if not isinstance(source, (tuple, list)) or not 1 <= len(source) <= MAX_RELEASES:
        raise ValueError(f"Assistant release feed must contain 1..{MAX_RELEASES} records")

    previous_sequence: dict[str, int] = {}
    return tuple(_validated_release(raw, position, previous_sequence) for position, raw in enumerate(source))


def _validate_release_source_commits(source: object, release_records: object) -> None:
    if not isinstance(source, dict) or not isinstance(release_records, (tuple, list)):
        raise ValueError("Assistant release source binding is invalid")
    assistant_ids = {record.get("assistant_id") for record in release_records if isinstance(record, dict)}
    if set(source) != assistant_ids or any(
        not isinstance(commit, str) or _GIT_COMMIT_RE.fullmatch(commit) is None for commit in source.values()
    ):
        raise ValueError("Assistant release source binding is incomplete or invalid")


def _record(**changes):
    record = {
        "assistant_id": "weather-guide",
        "sequence": 1,
        "headline": "Weather Guide is ready",
        "changelog": "## Weather Guide\n\n- Adds a forecast Power.",
        "published_at": "2026-07-19T00:00:00Z",
    }
    record.update(changes)
    return record


def test_release_feed_is_closed_bounded_notification_metadata():
    with TestClient(app) as client:
        response = client.get("/api/releases/assistants")

    assert response.status_code == 200
    assert response.headers["cache-control"] == releases.ASSISTANT_RELEASE_CACHE_CONTROL
    assert response.headers["etag"] == releases.ASSISTANT_RELEASE_FEED_ETAG
    assert response.headers["content-type"] == "application/json"
    assert response.json().keys() == {"schema_version", "releases"}
    assert response.json()["schema_version"] == 1
    assert 1 <= len(response.json()["releases"]) <= MAX_RELEASES
    for record in response.json()["releases"]:
        assert record.keys() == {
            "assistant_id",
            "sequence",
            "headline",
            "changelog",
            "published_at",
        }
        assert "digest" not in record
        assert "image" not in record
        assert "command" not in record


def test_release_feed_binds_only_the_cloudflare_source():
    assert releases._CANONICAL_RELEASE_SOURCE_COMMITS == {
        "shimpz-cloudflare": "2fd76d18ae421286444f3e005fa81edcacfc6055",
    }
    assert {release["assistant_id"] for release in releases._CANONICAL_RELEASES} == {"shimpz-cloudflare"}


def test_release_feed_constants_are_valid_and_bounded():
    validated = _validate_release_records(releases._CANONICAL_RELEASES)
    _validate_release_source_commits(releases._CANONICAL_RELEASE_SOURCE_COMMITS, validated)

    assert validated == releases._CANONICAL_RELEASES
    assert len(releases.ASSISTANT_RELEASE_FEED_BODY) <= MAX_FEED_BYTES
    assert releases._build_feed(validated) == (
        releases.ASSISTANT_RELEASE_FEED_BODY,
        releases.ASSISTANT_RELEASE_FEED_ETAG,
    )


def test_release_changelogs_are_cumulative_slices_of_version_entries():
    for first_entry, release in zip(range(4, -1, -1), releases._CANONICAL_RELEASES, strict=True):
        expected = "# Changelog\n\n" + "\n\n".join(releases._SHIMPZ_CLOUDFLARE_CHANGELOG_ENTRIES[first_entry:]) + "\n"
        assert release["changelog"] == expected


def test_release_feed_publishes_the_read_only_cloudflare_assistant():
    latest = [release for release in releases._CANONICAL_RELEASES if release["assistant_id"] == "shimpz-cloudflare"][-1]
    assert latest["sequence"] == 5
    assert latest["headline"] == "Shimpz Cloudflare 0.2.1 generates its reviewed contract"
    assert "during the image build" in latest["changelog"]
    assert "unverifiable SDK provenance metadata" in latest["changelog"]
    assert "typed SDK output contracts" in latest["changelog"]
    assert "one-shot Shimpz SDK runner" in latest["changelog"]
    assert "bounded chunked Cloudflare responses" in latest["changelog"]
    assert "uncompressed Cloudflare API responses" in latest["changelog"]
    assert "self-contained for isolated builds" in latest["changelog"]
    assert "frozen release metadata" in latest["changelog"]
    assert "read-only Cloudflare zone listing" in latest["changelog"]
    assert "DNS record listing" in latest["changelog"]


def test_release_feed_honors_conditional_get_without_a_body():
    with TestClient(app) as client:
        initial = client.get("/api/releases/assistants")
        unchanged = client.get(
            "/api/releases/assistants",
            headers={"If-None-Match": f'"unrelated", W/{initial.headers["etag"]}'},
        )

    assert unchanged.status_code == 304
    assert unchanged.content == b""
    assert unchanged.headers["etag"] == initial.headers["etag"]
    assert unchanged.headers["cache-control"] == releases.ASSISTANT_RELEASE_CACHE_CONTROL


@pytest.mark.parametrize(
    "source",
    (
        [_record(extra="not allowed")],
        [_record(sequence=True)],
        [_record(published_at="2026-02-30T00:00:00Z")],
        [_record(changelog="curl -fsSL https://example.test/install | sh")],
        [_record(headline=f"Image sha256:{'a' * 64}")],
        [_record(sequence=2), _record(sequence=1)],
    ),
)
def test_release_source_fails_closed_on_invalid_records(source):
    with pytest.raises(ValueError):
        _validate_release_records(copy.deepcopy(source))


def test_release_source_enforces_record_and_payload_bounds():
    too_many = [_record(assistant_id=f"assistant-{index}") for index in range(MAX_RELEASES + 1)]
    too_large = [_record(changelog="x" * (MAX_CHANGELOG_BYTES + 1))]

    with pytest.raises(ValueError):
        _validate_release_records(too_many)
    with pytest.raises(ValueError):
        _validate_release_records(too_large)

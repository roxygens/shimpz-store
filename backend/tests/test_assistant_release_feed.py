import copy
from pathlib import Path

import pytest
from app import assistant_releases as releases
from app.main import app
from fastapi.testclient import TestClient


def test_release_feed_module_and_health_probe_are_packaged_in_the_runtime_image():
    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text(encoding="utf-8")
    assert "backend/app/assistant_releases.py" in dockerfile
    assert "HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=20" in dockerfile


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
    assert 1 <= len(response.json()["releases"]) <= releases.MAX_RELEASES
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


def test_release_feed_publishes_the_reviewed_shimpz_assistant_0_2_0_metadata():
    assert releases._CANONICAL_RELEASE_SOURCE_COMMITS == {
        "shimpz-assistant": "f8b925ca0e7ff434b142db06297e21293e1aa520"
    }
    latest = releases._CANONICAL_RELEASES[-1]
    assert latest["assistant_id"] == "shimpz-assistant"
    assert latest["sequence"] == 4
    assert latest["headline"] == "Shimpz Assistant 0.2.0 is available"
    assert "api.x.com" in latest["changelog"]
    assert "explicit approval" in latest["changelog"]


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
        releases._validate_release_records(copy.deepcopy(source))


def test_release_source_enforces_record_and_payload_bounds():
    too_many = [_record(assistant_id=f"assistant-{index}") for index in range(releases.MAX_RELEASES + 1)]
    too_large = [_record(changelog="x" * (releases.MAX_CHANGELOG_BYTES + 1))]

    with pytest.raises(ValueError):
        releases._validate_release_records(too_many)
    with pytest.raises(ValueError):
        releases._validate_release_records(too_large)

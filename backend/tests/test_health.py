from app.main import app
from fastapi.testclient import TestClient


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_only_the_assistant_embed_allows_loopback_admin_framing():
    with TestClient(app) as client:
        normal = client.get("/api/health")
        assert normal.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in normal.headers["content-security-policy"]
        assert "x-robots-tag" not in normal.headers

        for locale in ("en", "pt"):
            embedded = client.get(f"/{locale}/assistants/embed")
            policy = embedded.headers["content-security-policy"]
            assert "x-frame-options" not in embedded.headers
            assert (
                "frame-ancestors http://127.0.0.1:* http://localhost:* http://[::1]:*"
                in policy
            )
            assert (
                "https:" not in policy.split("frame-ancestors", 1)[1].split(";", 1)[0]
            )
            assert embedded.headers["x-robots-tag"] == "noindex, nofollow"

        lookalike = client.get("/en/assistants/embed/anything")
        assert lookalike.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in lookalike.headers["content-security-policy"]

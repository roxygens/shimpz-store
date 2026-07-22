from pathlib import Path

from fastapi.testclient import TestClient

from app import main as store


def _write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_html_navigation_always_revalidates(monkeypatch, tmp_path):
    _write(tmp_path, "index.html", "home")
    _write(tmp_path, "en/assistants/embed.html", "embedded-store")
    _write(tmp_path, "_app/immutable/chunks/never-cache.html", "html")
    monkeypatch.setattr(store, "BUILD", tmp_path)

    with TestClient(store.app) as client:
        for url in (
            "/",
            "/en/assistants/embed?admin-frame=new-release",
            "/_app/immutable/chunks/never-cache.html",
        ):
            response = client.get(url)
            assert response.status_code == 200
            assert response.headers["cache-control"] == store.HTML_CACHE_CONTROL
            assert "immutable" not in response.headers["cache-control"]


def test_sveltekit_immutable_assets_keep_long_content_addressed_cache(monkeypatch, tmp_path):
    _write(tmp_path, "_app/immutable/chunks/AssistantStore.BfzPtRCS.js", "export default true")
    monkeypatch.setattr(store, "BUILD", tmp_path)

    with TestClient(store.app) as client:
        response = client.get("/_app/immutable/chunks/AssistantStore.BfzPtRCS.js?release=1")

    assert response.status_code == 200
    assert response.headers["cache-control"] == store.IMMUTABLE_CACHE_CONTROL
    assert response.text == "export default true"


def test_mutable_assets_and_missing_navigation_do_not_heuristically_cache(monkeypatch, tmp_path):
    _write(tmp_path, "brand/shimpz.svg", "<svg></svg>")
    _write(tmp_path, "_app/immutable-lookalike/chunk.js", "mutable")
    monkeypatch.setattr(store, "BUILD", tmp_path)

    with TestClient(store.app) as client:
        mutable = client.get("/brand/shimpz.svg")
        lookalike = client.get("/_app/immutable-lookalike/chunk.js")
        missing = client.get("/en/not-published-yet")

    assert mutable.status_code == 200
    assert mutable.headers["cache-control"] == store.HTML_CACHE_CONTROL
    assert lookalike.status_code == 200
    assert lookalike.headers["cache-control"] == store.HTML_CACHE_CONTROL
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == store.HTML_CACHE_CONTROL

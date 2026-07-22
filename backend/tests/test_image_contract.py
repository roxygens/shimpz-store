"""Static delivery contracts for the Store production image."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UV_IMAGE = "ghcr.io/astral-sh/uv:0.11.25@sha256:1e3808aa9023d0980e7c15b1fa7c1ac16ff35925780cf5c459858b2d693f01a9"


def test_static_runtime_packages_the_release_broker_and_health_probe():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "backend/app/assistant_releases.py" in dockerfile
    assert "backend/app/oauth_broker.py" in dockerfile
    assert "HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=20" in dockerfile


def test_static_runtime_copies_only_builder_resolved_dependencies():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.split(" AS serve\n", 1)[1]

    assert f"FROM {UV_IMAGE} AS uv" in dockerfile
    assert "COPY --from=uv /uv /usr/local/bin/uv" in dockerfile
    assert "COPY --from=dependencies /opt/venv /opt/venv" in runtime
    assert "uv-install.sh" not in dockerfile
    assert "apt-get" not in runtime
    assert "curl" not in runtime
    assert "/usr/local/bin/uv" not in runtime


def test_static_build_context_excludes_dependencies_caches_and_secrets():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert {
        ".git",
        ".env",
        ".env.*",
        "**/.env",
        "**/.env.*",
        ".pnpm-store",
        ".venv",
        "backend/.venv",
        "frontend/.pnpm-store",
        "frontend/.svelte-kit",
        "frontend/build",
        "frontend/node_modules",
    } <= set(dockerignore)

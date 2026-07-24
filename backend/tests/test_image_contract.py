"""Static delivery contracts for the Store production image."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UV_IMAGE = "ghcr.io/astral-sh/uv:0.11.25@sha256:1e3808aa9023d0980e7c15b1fa7c1ac16ff35925780cf5c459858b2d693f01a9"


def _runtime_import_closure() -> set[str]:
    source = ROOT / "backend" / "app"
    pending = [Path("main.py")]
    modules = {Path("__init__.py")}
    while pending:
        module = pending.pop()
        if module in modules:
            continue
        modules.add(module)
        tree = ast.parse((source / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if node.module == "app":
                for alias in node.names:
                    child = Path(f"{alias.name}.py")
                    if (source / child).is_file():
                        pending.append(child)
                continue
            if not node.module.startswith("app."):
                continue
            imported = Path(*node.module.removeprefix("app.").split("."))
            module_file = imported.with_suffix(".py")
            if (source / module_file).is_file():
                pending.append(module_file)
            package_init = imported / "__init__.py"
            if (source / package_init).is_file():
                pending.append(package_init)
                for alias in node.names:
                    child = imported / f"{alias.name}.py"
                    if (source / child).is_file():
                        pending.append(child)
    return {f"backend/app/{module}" for module in modules if len(module.parts) == 1}


def test_static_runtime_packages_the_exact_application_import_closure():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.split(" AS serve\n", 1)[1]
    logical_runtime = re.sub(r"\\\n\s*", " ", runtime)
    packaged = set(re.findall(r"\bbackend/app/(?:__init__|[a-z][a-z0-9_]*)[.]py\b", logical_runtime))

    assert packaged == _runtime_import_closure()
    assert (
        "COPY backend/app/chat/__init__.py backend/app/chat/events.py "
        "backend/app/chat/relay.py backend/app/chat/ws.py ./app/chat/"
    ) in dockerfile


def test_static_runtime_has_a_bounded_health_probe():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=20" in dockerfile


def test_static_runtime_copies_only_builder_resolved_dependencies():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.split(" AS serve\n", 1)[1]

    assert f"FROM {UV_IMAGE} AS uv" in dockerfile
    assert "COPY --from=uv /uv /usr/local/bin/uv" in dockerfile
    assert "COPY backend/pyproject.toml backend/uv.lock ./" in dockerfile
    assert "uv sync --frozen --no-install-project --no-dev --python 3.14" in dockerfile
    assert "requirements.lock" not in dockerfile
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

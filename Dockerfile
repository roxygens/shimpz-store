# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
# Shimpz storefront — multi-stage: node prerenders the SvelteKit app (static HTML, best SEO), python
# serves the build + the tiny /api. Follows the shimpz-new fullstack shape (frontend/ + backend/).

# ── stage 1: obtain the exact uv binary without retaining an installer toolchain ─────────────────
FROM ghcr.io/astral-sh/uv:0.11.25@sha256:1e3808aa9023d0980e7c15b1fa7c1ac16ff35925780cf5c459858b2d693f01a9 AS uv
ARG SOURCE_DATE_EPOCH=0

# ── stage 2: build the prerendered frontend ─────────────────────────────────────────────────────
FROM node:24-slim@sha256:b31e7a42fdf8b8aa5f5ed477c72d694301273f1069c5a2f71d53c6482e99a2fc AS web
ARG SOURCE_DATE_EPOCH=0
WORKDIR /w
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/.npmrc ./
RUN corepack enable \
 && corepack prepare pnpm@11.9.0 --activate \
 && pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm test \
 && pnpm run build \
 && find /w/build -depth -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} + \
 && rm -rf /root/.cache/node /root/.local/share/pnpm /root/.npm
# adapter-static writes the prerendered site to /w/build

# ── stage 3: resolve target-platform Python dependencies ─────────────────────────────────────────
FROM python:3.14-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1 AS dependencies
ARG SOURCE_DATE_EPOCH=0
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY backend/requirements.lock ./requirements.lock
RUN uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python --no-cache-dir --require-hashes --requirements requirements.lock \
 && rm -rf /root/.cache/uv /root/.cache/pip

# ── stage 4: minimal runtime ─────────────────────────────────────────────────────────────────────
FROM python:3.14-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1 AS serve
ARG SOURCE_DATE_EPOCH=0
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY backend/app/__init__.py backend/app/assistant_releases.py backend/app/logconf.py backend/app/main.py \
     backend/app/middleware.py backend/app/oauth_broker.py ./app/
COPY --from=web /w/build ./build
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SHIMPZ_STORE_BUILD=/app/build
EXPOSE 3200
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=20 \
  CMD ["python3", "-c", "import socket; socket.create_connection(('127.0.0.1', 3200), 2).close()"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3200"]

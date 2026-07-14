# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
# Shimpz storefront — multi-stage: node prerenders the SvelteKit app (static HTML, best SEO), python
# serves the build + the tiny /api. Follows the shimpz-new fullstack shape (frontend/ + backend/).

# ── stage 1: build the prerendered frontend ─────────────────────────────────────────────────────
FROM node:24-slim@sha256:b31e7a42fdf8b8aa5f5ed477c72d694301273f1069c5a2f71d53c6482e99a2fc AS web
ARG SOURCE_DATE_EPOCH=0
WORKDIR /w
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/.npmrc ./
RUN corepack enable \
 && corepack prepare pnpm@11.9.0 --activate \
 && pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build \
 && find /w/build -depth -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} + \
 && rm -rf /root/.cache/node /root/.local/share/pnpm /root/.npm
# adapter-static writes the prerendered site to /w/build

# ── stage 2: serve ──────────────────────────────────────────────────────────────────────────────
FROM python:3.14-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1 AS serve
ARG SOURCE_DATE_EPOCH=0

ARG DEBIAN_SNAPSHOT=20260623T000000Z
RUN set -eux; \
    . /etc/os-release; \
    archive_keyring="$(find /usr/share/keyrings -maxdepth 1 -type f -name 'debian-archive-keyring.*' -print -quit)"; \
    test -n "$archive_keyring"; \
    rm -f /etc/apt/sources.list; \
    find /etc/apt/sources.list.d -maxdepth 1 -type f -delete; \
    printf '%s\n' \
        "deb [signed-by=${archive_keyring}] https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} ${VERSION_CODENAME} main" \
        "deb [signed-by=${archive_keyring}] https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} ${VERSION_CODENAME}-updates main" \
        "deb [signed-by=${archive_keyring}] https://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT} ${VERSION_CODENAME}-security main" \
        > /etc/apt/sources.list.d/debian-snapshot.list; \
    printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99shimpz-snapshot; \
    test "$(grep -Fc "https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}" /etc/apt/sources.list.d/debian-snapshot.list)" -eq 2; \
    test "$(grep -Fc "https://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}" /etc/apt/sources.list.d/debian-snapshot.list)" -eq 1

ARG UV_VERSION=0.11.25
ARG UV_INSTALL_SHA256=ca2de1bca2913ba30ce88658b6d90a663c627ecac378803aa58084a9adb35a46

WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" -o /tmp/uv-install.sh \
 && echo "${UV_INSTALL_SHA256}  /tmp/uv-install.sh" | sha256sum -c - \
 && env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh /tmp/uv-install.sh \
 && rm -f /tmp/uv-install.sh \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /var/lib/apt/periodic/* /var/cache/apt/* /var/cache/fontconfig/* \
        /var/cache/ldconfig/aux-cache /var/cache/man/* /var/log/apt/* \
        /var/log/alternatives.log /var/log/dpkg.log /root/.cache/uv
COPY backend/requirements.lock ./requirements.lock
RUN uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python --no-cache-dir --require-hashes --requirements requirements.lock \
 && rm -rf /root/.cache/uv /root/.cache/pip
COPY backend/app/__init__.py backend/app/logconf.py backend/app/main.py backend/app/middleware.py ./app/
COPY --from=web /w/build ./build
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SHIMPZ_STORE_BUILD=/app/build
EXPOSE 3200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3200"]

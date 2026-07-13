# Shimpz storefront — multi-stage: node prerenders the SvelteKit app (static HTML, best SEO), python
# serves the build + the tiny /api. Follows the shimpz-new fullstack shape (frontend/ + backend/),
# collapsed into one image for the standalone deploy.

# ── stage 1: build the prerendered frontend ─────────────────────────────────────────────────────
FROM node:24-slim AS web
WORKDIR /w
COPY frontend/ ./
RUN corepack enable \
 && corepack prepare pnpm@11.9.0 --activate \
 && pnpm install --no-frozen-lockfile \
 && pnpm run build
# adapter-static writes the prerendered site to /w/build

# ── stage 2: serve ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS serve
WORKDIR /app
RUN pip install --no-cache-dir "fastapi" "uvicorn[standard]" "structlog" "python-multipart"
COPY backend/vendor/shimpzbus /tmp/shimpzbus
RUN pip install --no-cache-dir /tmp/shimpzbus && rm -rf /tmp/shimpzbus
COPY backend/app/__init__.py backend/app/logconf.py backend/app/main.py backend/app/reviews.py ./app/
# The install.sh served at install.shimpz.com (mirror of sdk/install/install.sh — the SDK is the source of truth)
COPY backend/install.sh ./install.sh
COPY --from=web /w/build ./build
ENV SHIMPZ_STORE_BUILD=/app/build
EXPOSE 3200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3200"]

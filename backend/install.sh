#!/bin/sh
# Shimpz — standalone Capsule installer.  curl -fsSL https://install.shimpz.com | sh
#
# Runs a single-owner Shimpz Capsule on YOUR machine via Docker: the admin panel (first-config,
# Claude-subscription login, create your Capsule) on the magic default port :7777. Builds from the
# PUBLIC source repos — no registry, no account, no secret required (ADR-0005). Add `-s -- --dev` to
# also set up the SDK for building Shimpz apps/drivers against your live local Capsule.
#
# POSIX sh, idempotent, safe to re-run. Honours: SHIMPZ_HOME (default ~/.shimpz),
# SHIMPZ_PORT (default 7777), SHIMPZ_REF (git ref, default main).
set -eu

SHIMPZ_HOME="${SHIMPZ_HOME:-$HOME/.shimpz}"
SHIMPZ_PORT="${SHIMPZ_PORT:-7777}"
SHIMPZ_REF="${SHIMPZ_REF:-main}"
GH="https://github.com/roxygens"
DEV=0
for arg in "$@"; do
    [ "$arg" = "--dev" ] && DEV=1
done

# ── pretty output ────────────────────────────────────────────────────────────
if [ -t 1 ]; then C='\033[36m'; B='\033[1m'; D='\033[2m'; R='\033[31m'; Z='\033[0m'; else C=''; B=''; D=''; R=''; Z=''; fi
say()  { printf "%b\n" "${C}▸${Z} $*"; }
ok()   { printf "%b\n" "${C}✓${Z} $*"; }
die()  { printf "%b\n" "${R}✗ $*${Z}" >&2; exit 1; }

banner() {
    printf "%b\n" "${C}${B}"
    printf '   ▟▛ SHIMPZ  ·  standalone Capsule\n'
    printf "%b\n" "${D}   a better way to create and sell your AI solutions${Z}\n"
}

# ── preflight ────────────────────────────────────────────────────────────────
need() { command -v "$1" >/dev/null 2>&1 || die "missing '$1' — $2"; }
banner
say "Checking prerequisites…"
need git "install git and re-run"
need docker "install Docker Desktop (mac) or Docker Engine (linux): https://docs.docker.com/get-docker/"
if ! docker compose version >/dev/null 2>&1; then
    die "'docker compose' (v2) not found — update Docker Desktop, or install the compose plugin"
fi
docker info >/dev/null 2>&1 || die "the Docker daemon isn't running — start Docker and re-run"
case "$(uname -s)" in
    Linux|Darwin) ok "$(uname -s) + Docker ready" ;;
    *) die "unsupported OS '$(uname -s)' — Linux or macOS only (Windows: use WSL2)" ;;
esac

# ── fetch the public source (build-from-source: no registry needed) ──────────
mkdir -p "$SHIMPZ_HOME"
fetch() {  # fetch <repo> — clone or fast-forward a public roxygens repo at $SHIMPZ_REF
    dir="$SHIMPZ_HOME/$1"
    if [ -d "$dir/.git" ]; then
        say "Updating $1…"
        git -C "$dir" fetch --depth 1 origin "$SHIMPZ_REF" -q && git -C "$dir" checkout -q FETCH_HEAD
    else
        say "Cloning $1…"
        git clone --depth 1 -b "$SHIMPZ_REF" -q "$GH/$1" "$dir"
    fi
}
# The Capsule's own image + the socket-holding lifecycle driver + the admin panel + shared datastore
# driver. All PUBLIC. (pay/accounts — the SaaS moat — is deliberately NOT part of a single-owner box.)
for repo in shimpz-brain shimpz-drivers shimpz-admin shimpz-sdk; do fetch "$repo"; done
[ "$DEV" = 1 ] && fetch shimpz-store

cp "$SHIMPZ_HOME/shimpz-sdk/install/docker-compose.capsule.yml" "$SHIMPZ_HOME/docker-compose.yml"

# ── first-run config: mint the local Postgres password once, never rotate ────
ENV="$SHIMPZ_HOME/.env"
if [ ! -f "$ENV" ]; then
    say "Generating local config (.env)…"
    PW="$(docker run --rm busybox sh -c 'head -c18 /dev/urandom | base64 | tr -d "/+=" | head -c24')"
    {
        printf 'SHIMPZ_HOME=%s\n' "$SHIMPZ_HOME"
        printf 'SHIMPZ_PORT=%s\n' "$SHIMPZ_PORT"
        printf 'POSTGRES_PASSWORD=%s\n' "$PW"
        printf 'SHIMPZ_MODEL=claude-sonnet-5\n'
    } > "$ENV"
    chmod 600 "$ENV"
    ok "Config written to $ENV"
else
    ok "Reusing existing config ($ENV)"
fi

# ── build + boot ─────────────────────────────────────────────────────────────
say "Building the Capsule (first run compiles from source — a few minutes)…"
( cd "$SHIMPZ_HOME" && docker compose --env-file .env up -d --build ) || die "compose up failed (see the log above)"

# ── wait for the panel to answer ─────────────────────────────────────────────
say "Waiting for the admin panel on :$SHIMPZ_PORT…"
i=0
while [ "$i" -lt 60 ]; do
    if curl -fsS "http://127.0.0.1:$SHIMPZ_PORT/api/session" >/dev/null 2>&1; then break; fi
    i=$((i + 1)); sleep 2
done
[ "$i" -lt 60 ] || die "the panel didn't come up in time — check: cd $SHIMPZ_HOME && docker compose logs"

printf '\n'
ok "${B}Your Shimpz Capsule is running.${Z}"
printf "%b\n" "   ${B}Open  →  http://localhost:$SHIMPZ_PORT${Z}"
printf "%b\n" "   ${D}1. set your admin password   2. log the brain in (Claude)   3. create your Capsule${Z}"
if [ "$DEV" = 1 ]; then
    printf "%b\n" "   ${C}dev:${Z} the SDK is at ${B}$SHIMPZ_HOME/shimpz-sdk${Z} — see sdk/docs/build-a-shimpz-app.md"
fi
printf "%b\n" "   ${D}manage:  cd $SHIMPZ_HOME && docker compose {logs,down,up -d}${Z}\n"

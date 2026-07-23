# Shimpz Store

Shimpz Store is the public, account-authenticated Shimpz web application. A SvelteKit frontend and
FastAPI backend serve signup/login, OAuth model credentials, Team creation and teardown, Assistant
release discovery and installation, hosted App inventory, provider/model selection, Team files, and
the strict `shimpz.chat.v3` WebSocket surface.

The Store is an unprivileged gateway, not a controller. It has no Docker socket, provider admin key, or
Team-driver bearer. It forwards the authenticated account token to the internal accounts and Team
controller services, which enforce account/Team ownership and perform privileged work. Its one
file-backed service capability can only finalize an exact model-credential generation already being
revoked by accounts.

## Security boundary

- Session cookies are secure, HTTP-only, same-site, and verified against accounts before protected work.
- Team IDs bind the complete account ID and normalized Team name with a collision-resistant digest.
- OAuth uses PKCE and an audited broker; provider credentials never enter URLs, browser-readable state,
  logs, or controller chat frames.
- Chat accepts only bounded message, opaque file IDs, and selected installed Assistant IDs. Hosted v2
  exposes terminal reply/error/stop events and no local secret, account, or approval challenge flow.
- Static files resolve beneath the built application root; unknown API paths do not fall through to the
  SPA, and private JSON responses are non-cacheable.

The production image runs non-root with a read-only filesystem, fixed dependency locks, and only the
compiled frontend plus explicitly copied backend modules. Backend and frontend contracts live under
their respective `tests/` directories; built-browser behavior is exercised from the umbrella repository.

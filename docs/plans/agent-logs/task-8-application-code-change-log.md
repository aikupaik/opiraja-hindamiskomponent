# Task 8 Application-Code Change Log

Date: 2026-07-31

## Project changes

- Added required `ALLOWED_HOSTS` configuration. It must be a non-empty list of
  exact host values; blank entries and wildcard entries are rejected.
- Configured FastAPI's `TrustedHostMiddleware` from that setting.
- Recorded the phase-1 values in `.env.example` and Compose:
  `193.40.157.124` for the VM public IPv4 and `127.0.0.1` for direct API
  health checks.
- Added boundary tests for the VM IP, direct health-check host, arbitrary host
  rejection, trusted proxy scheme/client metadata, and spoofed proxy headers
  from an untrusted peer.
- Reviewed the admin production bundle for active `http://` resource URLs. No
  browser-loaded HTTP resource URL was found; the matches are XML namespace
  literals emitted by React DOM, not resource URLs.

## Validation

- Backend pytest: `94 passed, 1 skipped`.
- Backend Pyright: `0 errors, 0 warnings, 0 informations`.
- Admin Vitest: `11 passed`.
- Admin Oxlint: passed.
- Admin production build: passed.
- `docker compose config --quiet`: passed.

No deployment, firewall, Nginx, certificate, or service state was changed by
Task 8.

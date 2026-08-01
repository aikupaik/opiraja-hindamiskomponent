# Phase 2 — Restricted HTTPS Stabilization and Hardening Change Log

This log records the repository implementation work for the Phase 2 plan. It
does not record bearer tokens, cookies, request bodies, rendered environment
values, private keys, or sensitive query strings.

## Step 1 — Add edge rate and connection limits

### Implementation notes

- Updated `deploy/nginx/opiraja.conf` with shared-memory zones keyed by
  `$binary_remote_addr` for general API requests, the exact admin-session
  endpoint, and admin experiment SSE connections.
- Applied `10r/s` with `burst=20 nodelay` only to the general `/api/`
  location, and `5r/m` with `burst=5 nodelay` to the exact
  `/api/v1/admin/session` location.
- Applied a two-connection limit only to the admin experiment SSE location;
  established SSE streams remain outside request-rate limiting.
- Configured `429` statuses, warning-level limiter logging, a small
  `rate_limited` JSON envelope, and query-free limiter status fields in the
  host access log.
- Hid upstream `X-Request-ID` and made the host-generated request ID the sole
  response header on the public redirect and TLS server responses.
- Enabled `limit_req_dry_run on` and `limit_conn_dry_run on` for the initial
  observation deployment. The reviewed enforcement deployment remains a
  separate operational action.

### Validation and deployment status

- The repository host-Nginx fragment passed a privileged syntax check through
  a temporary full-configuration wrapper.
- The live VM site was not installed or reloaded; the repository change is
  ready for the planned dry-run deployment and controlled observation.

## Step 2 — Remove unsafe or duplicate request logging

### Implementation notes

- Changed `admin/nginx.conf` to log the request method, query-free `$uri`,
  protocol, status, byte count, request ID, and timing fields separately.
- Removed `$request`, referrer, user-agent, and other fields that could expose
  sensitive query values from the inner Nginx access log.
- Added `--no-access-log` to the Uvicorn command in `backend/Dockerfile`; the
  FastAPI structured completion event remains the application request log.
- Retained diagnostic-event redaction and expanded regression coverage for
  authorization, cookies, `Set-Cookie`, configured secrets, uploaded content,
  and sensitive query values.

### Validation and deployment status

- The Python 3.14 container reports Pyright clean and `95 passed, 1 skipped`.
- The modified inner Nginx configuration passes `nginx -t` in the production
  `nginx:1.28.3-alpine3.23` image.
- No VM configuration was installed or reloaded for this step.

## Step 3 — Retain remote URL ingestion with bounded hardening

### Implementation notes

- Kept authenticated administrator remote URL ingestion enabled without adding
  a feature flag.
- Restricted remote destinations to HTTP/HTTPS ports 80 and 443, while
  preserving the existing scheme, credential, DNS-address, redirect, size,
  timeout, content-type, PDF-page, and extracted-text checks.
- Added regression coverage for IPv4 and IPv6 loopback/private/link-local
  destinations, the `169.254.169.254` cloud metadata address, public redirects
  to private or metadata destinations, URL credentials, non-standard ports,
  excessive redirects, oversized responses, and timeouts.

### Validation and deployment status

- The Python 3.14 container reports Pyright clean and `106 passed, 1 skipped`.
- Remote URL ingestion remains a bounded authenticated feature; no VM
  configuration was installed or reloaded.
- The DNS-rebinding race between validation and the HTTP client's later
  connection lookup remains an accepted residual risk for this phase. Disabling
  URL ingestion or implementing DNS-pinned fetching with preserved TLS hostname
  verification remains an explicit public-launch blocker.

## Step 4 — Add a manual operations runbook and evidence log

### Implementation notes

- Added [the Phase 2 operations runbook](../active/phase-2-restricted-https-stabilization-hardening-runbook.md)
  covering preconditions, sanitized baseline collection, dry-run and
  enforcement deployment, controlled limiter/SSE probes, monitoring cadence,
  patching, Compose deployment, certificate replacement, service recovery, and
  network-first rollback.
- Added a sanitized evidence-record template with placeholders for commits,
  checksums, versions, status counts, health results, limiter observations,
  certificate windows, and recovery outcomes.
- Explicitly documented the prohibition on recording bearer tokens, cookies,
  request bodies, uploaded content, private keys, rendered environment values,
  or sensitive query strings.

### Validation and deployment status

- Documentation links and Markdown structure were reviewed locally.
- No VM, service, firewall, certificate, or application state was changed for
  this documentation step.

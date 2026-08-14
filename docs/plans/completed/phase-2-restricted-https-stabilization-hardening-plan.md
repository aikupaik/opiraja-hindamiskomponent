# Phase 2 — Restricted HTTPS Stabilization and Hardening

## Summary

Harden the existing allowlisted HTTPS deployment without changing its network
topology or opening Internet-wide access.

Labels identify ownership:

- **[CODE]** Repository configuration, application, tests, or documentation.
- **[VM]** Commands or configuration applied on the deployment VM.
- **[MANUAL]** Operator action requiring credentials, an external client, or an
  operational decision.

Phase 1 is locally operational, but its external acceptance remains incomplete.
Confirm the OpenStack rules and approved/non-approved client behavior before
treating the Phase 2 deployment as accepted.

## Implementation Changes

### 1. Add edge rate and connection limits

- **[CODE]** Update `deploy/nginx/opiraja.conf` using the standard Nginx
  [`limit_req`](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html)
  and
  [`limit_conn`](https://nginx.org/en/docs/http/ngx_http_limit_conn_module.html)
  modules:
  - Define an API zone keyed by `$binary_remote_addr`, sized `1m`, at `10r/s`.
  - Apply it only inside the general `/api/` location with
    `burst=20 nodelay`.
  - Define a separate `1m` zone for exact `/api/v1/admin/session` requests at
    `5r/m`, with `burst=5 nodelay`.
  - Define a `1m` connection zone keyed by `$binary_remote_addr`.
  - Apply `limit_conn ... 2` only to the admin experiment SSE location.
  - Do not apply `limit_req` at server scope or inside the SSE location; an
    established stream must remain open and unthrottled.
  - Return `429` for both request-rate and connection-limit rejection.
  - Return a small JSON error envelope with code `rate_limited` for
    edge-generated `429` responses.
  - Set rate/connection limit logging to `warn`.
- **[CODE]** Extend the host access log with `$limit_req_status` and
  `$limit_conn_status`. Preserve query-free request logging.
- **[CODE]** Make host Nginx own the public `X-Request-ID` response header:
  - Hide the upstream copy.
  - Add the host-generated ID to successful and edge-generated error responses.
  - Verify that responses contain exactly one request-ID header.
- **[CODE]** Commit the first deployment with `limit_req_dry_run on` and
  `limit_conn_dry_run on`. After observation and controlled tests, commit or
  install the reviewed enforcement configuration with dry-run disabled.

### 2. Remove unsafe or duplicate request logging

- **[CODE]** Change `admin/nginx.conf` from logging `$request` to separate
  method, `$uri`, and protocol fields. Remove referrer and other fields that
  could carry sensitive query values. Retain status, byte count, request ID,
  and timing.
- **[CODE]** Disable Uvicorn's default access log in `backend/Dockerfile`; the
  FastAPI structured completion log already records method, path without query,
  status, outcome, timing, and dependency measurements.
- **[CODE]** Retain diagnostic-event redaction and add regression coverage
  confirming authorization, cookies, configured secrets, uploaded content, and
  sensitive query values are absent from emitted logs.

### 3. Retain remote URL ingestion with bounded hardening

- **[CODE]** Keep remote URL ingestion enabled for authenticated
  administrators, as requested. Do not add a feature flag in this phase.
- **[CODE]** Retain the existing scheme, credential, DNS-address, redirect,
  size, timeout, content-type, PDF-page, and extracted-text checks. Additionally
  restrict remote destinations to HTTP/HTTPS ports 80 and 443.
- **[CODE]** Add tests covering:
  - IPv4 and IPv6 loopback/private/link-local destinations.
  - Cloud metadata addresses such as `169.254.169.254`.
  - A public URL redirecting to a private or metadata destination.
  - URL credentials and non-80/443 ports.
  - Excess redirects, oversized responses, and timeouts.
- **[MANUAL]** Record the accepted residual risk: DNS validation and the HTTP
  client's later connection lookup still leave a DNS-rebinding race. Trusted
  admin authentication reduces who can exercise the feature but does not
  eliminate SSRF if credentials are compromised.
- **[MANUAL]** Make “disable URL ingestion or implement DNS-pinned fetching
  with preserved TLS hostname verification” an explicit public-launch blocker.
  JWT authorization alone does not close this risk.

### 4. Add a manual operations runbook and evidence log

- **[CODE]** Add a Phase 2 runbook covering baseline collection, monitoring
  commands, rate-limit testing, patching, deployment, certificate replacement,
  recovery, and rollback. Add a sanitized Phase 2 agent/change log; never
  record rendered `.env` values, bearer tokens, cookies, bodies, private keys,
  or sensitive query strings.
- **[CODE]** Document this review cadence:
  - Daily for the first seven days after enforcement.
  - Weekly after stabilization.
  - Immediately before and after package, Nginx, certificate, or Compose
    changes.

## VM Deployment and Operations

### 1. Close the outstanding Phase 1 external gate

- **[MANUAL]** Inspect security groups attached to the exact
  OpenStack/Neutron VM port. Confirm TCP 80/443 are limited to
  `172.20.0.0/16` and `193.40.0.0/16`, SSH retains its approved restrictions,
  and no `0.0.0.0/0` or `::/0` ingress exists.
- **[MANUAL]** From an approved client, verify HTTPS access, the exact-path
  HTTP `308`, and the recorded certificate fingerprint.
- **[MANUAL]** From an independent non-approved source, verify denial on 80,
  443, 8080, and 8000. Do not weaken rules to conduct the test.

### 2. Baseline and protect secrets

- **[VM]** Record sanitized pre-change evidence: release commit,
  Ubuntu/kernel/Nginx/Docker/Compose versions, package sources, listeners,
  UFW/nftables state, Compose health, container restart counts, Docker networks,
  disk/inode use, Docker disk use, time synchronization, certificate metadata,
  and `nginx -V`.
- **[VM]** Confirm the host Nginx includes the request/connection-limit modules
  and supports dry-run directives. If not, update through the configured
  supported package source before installing the Phase 2 site.
- **[VM]** Verify `.env` is owned by the deployment user and has mode `0600`.
  Confirm it is absent from images and Git.
- **[MANUAL]** Rotate `ADMIN_ACCESS_KEY`, since it may previously have crossed
  plaintext HTTP. Close existing admin tabs, update the VM `.env` without
  printing the value, recreate the API, and unlock only after confirming the
  HTTPS certificate fingerprint. Rotate any other credential only if the
  inventory shows it was exposed or transported over HTTP.
- **[VM]** Verify application containers have no `/var/run/docker.sock` mount.
  Inspect socket ownership/mode and Docker-group membership.
- **[MANUAL]** Confirm every Docker-group member still requires root-equivalent
  Docker access; remove only accounts explicitly approved for removal.

### 3. Patch the host and images

- **[MANUAL]** Schedule a restricted-access maintenance window and confirm
  console/recovery access.
- **[VM]** Back up active Nginx configuration under the privileged VM backup
  area, excluding copies to Git or operator laptops.
- **[VM]** Refresh package metadata and review pending updates before applying
  them:
  - If Docker is installed as Ubuntu `docker.io`, update it through Ubuntu.
  - If Docker CE is installed from Docker's repository, update Docker Engine,
    CLI, containerd, Buildx, and Compose plugin through that already-configured
    repository.
  - Update Ubuntu security packages, Nginx, OpenSSL, and their dependencies.
  - Do not migrate package repositories as part of this phase.
- **[MANUAL]** Reboot during the maintenance window when
  `/var/run/reboot-required` exists.
- **[VM]** After patching or reboot, verify UFW, Nginx, Docker, Compose
  services, loopback publication, readiness, listeners, and TLS versions before
  continuing.
- **[VM]** Build the reviewed application commit with
  `docker compose build --pull`, so pinned base-image tags resolve to their
  current patched digest, then recreate services and wait for healthy status.

### 4. Deploy rate limits in two stages

- **[VM]** Install the dry-run host configuration, execute `sudo nginx -t`,
  and perform a graceful reload. Do not restart Nginx when a reload is
  sufficient.
- **[MANUAL]** From an approved client, run controlled probes:
  - Send more than 30 rapid requests to a harmless `/api/` probe path.
  - Send more than five rapid requests to `/api/v1/admin/session`.
  - Open three concurrent authenticated SSE connections from one client IP.
  - In dry-run mode, requests should continue, while access logs identify
    dry-run excesses.
  - Complete a normal admin workflow and one full simulation to check for
    false positives.
- **[MANUAL]** Review at least one normal operating day of dry-run logs. Confirm
  the chosen limits do not reject ordinary administrative use.
- **[VM]** Disable dry-run, validate with `nginx -t`, and gracefully reload.
- **[MANUAL]** Repeat the probes. Confirm:
  - General API traffic allows the configured rate/burst and then returns
    controlled `429`.
  - The session endpoint enforces its stricter rate.
  - Two SSE streams remain incremental; the third receives `429`.
  - Established SSE streams are not interrupted by request-rate limiting.
  - Ordinary UI/API/upload behavior and the existing `413` boundary remain
    functional.

## Monitoring and Recovery Rehearsals

### Manual monitoring checklist

- **[VM]** Review host Nginx access/error logs for totals and `413`, `429`, and
  5xx counts, including limiter status. In this low-volume phase, investigate
  every unexpected 5xx or 429 rather than relying only on percentage
  thresholds.
- **[VM]** Check `docker compose ps` and container restart counts. Investigate
  any readiness failure or restart-count increase.
- **[VM]** Check API readiness through loopback and R health from within its
  Compose context.
- **[VM]** Check filesystem/inode use and Docker/log consumption. Investigate
  at 80% use and treat 90% as urgent.
- **[VM]** Verify the normal Nginx logrotate policy covers both Opiraja logs.
  Add a VM-local logrotate rule only if the package rule does not cover them.
- **[VM]** Check certificate validity and fail the checklist if fewer than 30
  days remain.
- **[MANUAL]** Create operator-owned reminders 30, 14, and 7 days before the
  post-rehearsal certificate expiry.

### Rehearsals

- **[VM + MANUAL] Certificate replacement:** Generate a new 90-day IP-SAN
  certificate beside the live files, verify key/certificate pairing and
  permissions, back up the current live pair in the privileged VM area, install
  the replacement at the stable paths, run `nginx -t`, reload, and independently
  compare the new fingerprint from an approved client. Restore the previous
  pair if validation fails.
- **[VM] Failure recovery:** Restart R, then API, then web separately. Confirm
  readiness becomes unavailable where expected and recovers without changing
  networks, firewall rules, or TLS configuration.
- **[VM] Compose update:** Deploy the reviewed Phase 2 commit with
  `docker compose config`, build, recreate, health verification, and HTTPS
  smoke tests.
- **[VM + MANUAL] Rollback:** First reconfirm OpenStack and UFW restrictions.
  Roll back only to the recorded known-good Phase 1 HTTPS commit and Nginx
  backup, validate/reload, and verify listeners and HTTPS. Then redeploy Phase
  2. Never roll back to public plaintext HTTP or a Compose revision publishing
  port 80 directly.

## Test Plan and Acceptance

- **[CODE]** Backend with `backend/.venv`: run the complete pytest suite and
  `python -m pyright`; both must pass without ignores or configuration
  weakening.
- **[CODE]** Admin: run `npm test`, `npm run lint`, and `npm run build`.
- **[CODE]** Run the R `testthat` suite because the integrated deployment is
  rebuilt and recovery is rehearsed, even though R code is unchanged.
- **[CODE/VM]** Validate `docker compose config`, both Nginx configurations,
  loopback-only port publication, API-to-R connectivity, and recovery after
  recreation.
- **[MANUAL]** Repeat the Phase 1 browser, upload, SSE, forwarded-header,
  mixed-content, certificate, and approved/non-approved source checks after
  enforcement.
- **[MANUAL]** Phase 2 is accepted only when:
  - External Phase 1 checks are recorded.
  - Dry-run and enforced limiter tests pass.
  - Normal workflows show no false-positive throttling.
  - Logs are sanitized.
  - Secrets and Docker access are reviewed.
  - Patch/reboot recovery succeeds.
  - Certificate, Compose, service-failure, and network-first rollback
    rehearsals succeed.
  - The residual DNS-rebinding risk is recorded as a hard public-launch
    blocker.

## Public Interface and Assumptions

- Public API success schemas and persistence remain unchanged.
- Nginx may now return HTTP `429` with a stable `rate_limited` JSON envelope.
- Remote URL ingestion remains available to authenticated administrators; URLs
  using ports other than 80/443 become invalid.
- Monitoring is a manual runbook with documented cadence; no external
  monitoring platform or systemd timer is added.
- Host Nginx remains the only TLS terminator, IPv6 public HTTPS remains
  disabled, and access remains limited to approved CIDRs.
- Phase 3 JWT work and Phase 4 domain/public-certificate work remain separate.
- `ATA_kst/`, `TP_kst`, and the unused `frontend/` application remain
  untouched.
- Preserve the existing user-owned plan-file move visible in the working tree.

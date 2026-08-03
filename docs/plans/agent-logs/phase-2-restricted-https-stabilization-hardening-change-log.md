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

## VM deployment and operations — Step 2 baseline and secret protection

### Read-only VM baseline

Collected on `2026-08-03T10:03:31Z` before any Phase 2 installation or
reload. No service, firewall, certificate, container, package, or secret was
changed, and no secret value was read or recorded.

| Evidence item | Sanitized result |
| --- | --- |
| Release | `d6424d39c80e4cfb28f29d1767640436e124f11a`; working tree clean at collection |
| Host/runtime | Ubuntu 24.04.4 LTS; kernel 6.8.0-136; Nginx 1.24.0; Docker Engine 29.6.2; Compose 5.3.1 |
| Package provenance | Nginx from Ubuntu updates/security; Docker CE, CLI, containerd, and Compose plugin from Docker's configured Ubuntu repository |
| Pending patch observation | Docker CE and CLI 29.7.1 are available; this is for the scheduled package-patching step, not installed during baseline |
| Nginx capability | Stock Ubuntu Nginx reports the standard HTTP build; the Phase 2 template had already passed its privileged full-configuration syntax check. `nginx -t` remains successful on the current site |
| Network/service state | UFW default-deny inbound with the approved source CIDRs only; IPv4 80/443 owned by Nginx; web publication loopback-only on 127.0.0.1:8080; no host 8000 listener; all three Compose services healthy |
| Storage | Root filesystem 30% used, root inodes 4% used; Docker has 36.62 GB build cache, 22.07 GB reclaimable |
| Time/certificate | NTP synchronized; certificate CN/SAN is `193.40.157.124`, recorded SHA-256 fingerprint matches Phase 1 evidence, expiry `2026-10-29T13:43:59Z` (more than 30 days remaining) |
| Compose/image secret check | `.env` is Git-ignored and not tracked; no `.env` file was found in the exported filesystem of the API, R, or web application container; no application container mounts `/var/run/docker.sock` |
| Docker socket/access | Socket is owned by `root:docker` with mode `0660`; the Docker group has one non-root member, requiring operator confirmation that this root-equivalent access remains necessary |
| Log rotation | The Ubuntu Nginx rule covers `/var/log/nginx/*.log` daily, retaining 14 compressed rotations, which includes the Opiraja host logs |
| Reboot state | `/var/run/reboot-required` is absent |

### Findings and required manual actions

- **Blocker — `.env` mode:** the deployment `.env` is owned by the deployment
  user but has mode `0664`, not the required `0600`. Correct its mode through
  the approved privileged deployment process before any Phase 2 installation.
- **Required rotation:** the operator must rotate `ADMIN_ACCESS_KEY` before
  Phase 2 deployment because it may have crossed plaintext HTTP previously.
  Close existing admin tabs, update the VM `.env` without printing the value,
  recreate the API, and use the credential only after the HTTPS certificate
  fingerprint has been reconfirmed.
- **Required decision:** the operator must confirm that the sole non-root
  Docker-group member still requires root-equivalent Docker access. No account
  was changed by this review.
- **Known planned drift:** the active host site checksum differs from the
  reviewed Phase 2 template checksum, as expected before the dry-run
  installation. This is the recorded source of the Phase 1 request-ID finding.

Result: **VM baseline completed; secret/access gate not yet complete**. Do not
install the Phase 2 host configuration until the `.env` permission and the
manual credential/access decisions above are completed and recorded.

### Manual-action completion record

On `2026-08-03T10:09:20Z`, the deployment `.env` mode was rechecked without
reading its contents and is now `0600`, owned by the deployment user. The
operator reported that `ADMIN_ACCESS_KEY` was rotated; no key material was
read, displayed, or recorded. The required API recreation after that rotation
must be confirmed before authenticated acceptance testing.

The operator confirmed that `ubuntu` is the designated deployment operator
and requires Docker-group access for approved Compose deployment and
operations. Privileged inspection confirmed Docker's configured socket is
`root:docker` mode `0660` and `ubuntu` remains the sole non-root Docker-group
member. The current agent shell was created before that supplementary group
membership was effective and cannot access Docker; begin a new SSH/login
session before running non-privileged Docker or Compose commands.

Result: `.env` permission and Docker-access decision are complete. Credential
rotation is operator-reported, but API recreation remains a required
verification before proceeding to authenticated checks or the Phase 2
deployment.

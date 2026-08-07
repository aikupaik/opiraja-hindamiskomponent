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

The operator subsequently confirmed that the recreated API is healthy. The
secret/access gate is therefore complete, subject to the later authenticated
acceptance checks using the rotated credential.

## JWT rollout prerequisites — 2026-08-07

During the approved maintenance window, the deployment VM was prepared for
the reviewed JWT application commit `3b12860b25459d8e70d0eff326b5d6b13b89425c`.
No application container was rebuilt or recreated in this step.

- Upgraded Docker Buildx from `0.36.0` to `0.36.1` and Docker Compose from
  `5.3.1` to `5.4.0`, using Docker's already configured Ubuntu repository.
  The package manager reported a newer installed kernel; a reboot is now
  required, but was deliberately deferred rather than combined with this
  JWT-edge preparation change.
- Backed up the prior root-owned host site to
  `/var/backups/nginx/opiraja-jwt-20260807/opiraja.conf.before`. Its SHA-256
  checksum was `3fe748c6d11dc212fa31226abb55fc802096c459dbdea579949a7f0a7977dfbc`.
- Installed the reviewed `deploy/nginx/opiraja.conf` at the normal live site
  path and completed a successful `nginx -t` followed by a graceful reload.
  The active and enabled configuration checksum is now
  `5e7bff2b4fe5cc85d05b1036cbd864b4a95d4cde43a8c580074000bb9925bb10`.
- The installed edge now has the exact JWT controls: the `admin/login` limit,
  shared issuance limits for test creation and player-token issuance, and the
  player start/answer limit. Both dry-run directives remain enabled.
- Post-change checks passed at `2026-08-07T08:55:32Z`: Compose configuration
  was structurally valid; all existing services remained healthy; loopback web
  health and API readiness returned `200`; the HTTPS root returned `200`; and
  only host IPv4 `80`/`443` plus loopback `8080` listened. The new login path
  returned `404`, as expected while the pre-JWT API image is still running.

Result: **JWT host and package prerequisites are complete.** The next approved
deployment step is `docker compose build --pull` followed by `docker compose
up -d --remove-orphans`, health verification, and signed OR-to-player and
admin-login acceptance. Keep both limiter dry-run directives enabled during
that rollout. Perform the endpoint-specific threshold probes, shared-IP player
burst, normal workflow observation, and one-day sanitized log review before
considering limiter enforcement. Schedule the deferred kernel reboot in a
separate approved maintenance window and re-run the standard host/Compose/TLS
checks afterward.

The deployment operator will perform that reboot manually as the final
pre-rollout maintenance action. Do not reboot the VM from a deployment-agent
session before the operator explicitly confirms it.

The operator completed the reboot on 2026-08-07. Post-reboot verification
found kernel `6.8.0-137-generic`, no reboot-required marker, active and
syntactically valid Nginx, healthy Compose services, successful loopback web
health and API-readiness checks, and only host IPv4 `80`/`443` plus loopback
`8080` listening. The JWT application rollout may proceed.

## VM deployment and operations — Step 3 patching and Step 4 dry-run install

### Maintenance execution record

Performed during the operator-confirmed maintenance window with OpenStack
console recovery access available.

- Backed up the active site to the root-only directory
  `/var/backups/nginx/opiraja-phase-2-20260803/`; the backup and pre-change
  active-site SHA-256 checksums match.
- Refreshed APT metadata and reviewed the pending set. Only Docker Engine,
  Docker CLI, and Docker rootless extras were pending, from Docker's already
  configured Ubuntu repository. Upgraded each from 29.6.2 to 29.7.1; no
  Ubuntu, Nginx, OpenSSL, kernel, or Compose-plugin update was pending.
- The package manager reported that no reboot was required. Docker's refresh
  briefly restarted containers; all recovered healthy.
- Rebuilt the reviewed R, API, and web images with `docker compose build
  --pull`. The web build and its inner Nginx syntax test passed. Recreated
  Compose services with `docker compose up -d --remove-orphans`; R, API, and
  web all became healthy.
- Post-patch checks at `2026-08-03T10:28:56Z` passed: Compose configuration
  was structurally valid; UFW and listener restrictions were unchanged;
  loopback web health and API readiness both returned 200; TLS 1.2 and 1.3
  negotiated successfully; `/var/run/reboot-required` remained absent.

### Phase 2 Nginx dry-run deployment

At `2026-08-03T10:30:41Z`, installed the reviewed host site with
`limit_req_dry_run on` and `limit_conn_dry_run on`, checksum
`87f2df8288ccd24b74f7d439f4631d0e2bfb11562c743372cd0d3d05df13d2c1`.
`nginx -t` passed and Nginx was gracefully reloaded.

Post-reload VM checks passed: Nginx is active; all three Compose services are
healthy; only host IPv4 80/443 and loopback 8080 are published; loopback web
health and API readiness return 200; and the HTTPS SPA response contains one
copy of each canonical security header plus one host-generated
`X-Request-ID`. HSTS remains absent.

Result: **dry-run deployment passed its VM checks**. The next required work is
approved-client external revalidation and controlled dry-run API/session/SSE
probes, followed by at least one normal operating day of sanitized limiter-log
observation. Do not disable dry-run before those results are recorded.

### Approved-client revalidation

During 2026-08-03 13:31–13:33 EEST, the approved VPN client confirmed the
public HTTPS/header and forged-forwarded-header checks pass, including exactly
one host-generated `X-Request-ID`, and confirmed the SPA is clean in a browser
profile with extensions disabled. Sanitized host evidence for the same window
contains six `200` responses, all with a generated request ID.

One host-Nginx warning recorded buffering of a normal proxied response to a
temporary file. It caused no failed response and does not apply to the exact
SSE location, which retains disabled buffering. Include it in the required
normal-operation log observation; it is not a dry-run limiter event.

Result: **approved-client smoke revalidation passed**. Authenticated normal
workflow, upload, SSE, and controlled dry-run limiter probes remain required.

### Dry-run observation deferral

On 2026-08-03, the operator deferred the credentialed normal-workflow,
upload-boundary, complete-SSE, and controlled API/session/SSE limiter probes
to a later testing session. The one-normal-operating-day dry-run observation
begins with the installed dry-run configuration and must include those results
before it is concluded.

Enforcement remains explicitly blocked: do not disable `limit_req_dry_run` or
`limit_conn_dry_run`, and do not claim Phase 2 acceptance, until the deferred
tests and sanitized one-day limiter-log review are recorded.

### Controlled dry-run request-rate probes

From the approved VPN client on 2026-08-03:

- A sequential 35-request harmless `/api/` probe at approximately
  13:46–13:47 EEST returned 35 `404` responses. Sanitized host evidence
  recorded all 35 as `limit_req_status=PASSED`; this did not exceed the 10/s
  general API rate and is a baseline result, not an excess-limit result.
- An eight-request authenticated admin-session probe at approximately
  13:49–13:50 EEST returned eight `200` responses. Sanitized host evidence
  recorded six `PASSED` and two `REJECTED_DRY_RUN` limiter statuses, with two
  matching session-limit warning events and no other error events. This
  confirms the strict session limiter observes excess traffic without rejecting
  it in dry-run mode.

Result: **admin-session dry-run excess probe passed**. Repeat the harmless
general `/api/` probe concurrently to produce and record general API
`REJECTED_DRY_RUN` evidence. The SSE connection-limit probe and normal-workflow
observation remain outstanding.

The concurrent harmless general-API probe was repeated at approximately
13:55 EEST with 60 requests. The client received 60 `404` responses; sanitized
host evidence recorded 21 `PASSED` and 39 `REJECTED_DRY_RUN` statuses, with 39
matching general-API limiter warnings and no other error events. This confirms
the general API rate limiter observes excess traffic without rejecting it in
dry-run mode.

Result: **general API dry-run excess probe passed**. The SSE connection-limit
probe, normal authenticated workflow/upload/SSE observation, and one-day
sanitized log review remain outstanding before enforcement.

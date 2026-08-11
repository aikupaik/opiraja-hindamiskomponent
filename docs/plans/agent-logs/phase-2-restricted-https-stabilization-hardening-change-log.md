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

## Phase 2 blocker assessment and live-VM preflight — 2026-08-09

This entry records a read-only assessment and privileged VM preflight performed
from the deployment VM. No Nginx, Compose, package, firewall, certificate, or
application state was changed. No rendered environment value, credential,
token, cookie, request body, uploaded content, private key, client address, or
raw log line was displayed or recorded.

### Live preflight evidence

- Repository HEAD was `7acb18733c1e946cf318b4d801d58b82456a2281`; the working
  tree was clean.
- The repository host-site file, enabled host-site file, and active host-site
  file all had SHA-256
  `5e7bff2b4fe5cc85d05b1036cbd864b4a95d4cde43a8c580074000bb9925bb10`.
- The active site retains `limit_req_dry_run on` and `limit_conn_dry_run on`.
  Host Nginx syntax validation passed and the Nginx service was active.
- The live strict administrative limiter is now the JWT
  `/api/v1/admin/login` location at `5r/m` with `burst=5`, rather than the
  original Phase 2 `/api/v1/admin/session` location. The general API,
  experiment-SSE connection, shared issuance, and player request limiter zones
  are also present. A change-control record must explicitly treat the login
  endpoint as the successor to the originally planned session endpoint before
  the dry-run results are used for enforcement approval.
- All Compose services were healthy. Loopback web health and API readiness both
  returned `200`; the HTTPS root returned `200`; and a deliberately invalid
  admin-login request returned `401`, confirming the JWT API deployment is
  live without recording the submitted value.
- Listener inspection found host IPv4 `80` and `443`, loopback
  `127.0.0.1:8080`, SSH, and local resolver listeners only; host port `8000`
  was not published. No reboot-required marker was present.

### Sanitized initial observation findings

The immediately preceding 24-hour host access-log window contained 10
requests: eight `200`, one `308`, and one `401`. It contained six
`limit_req_status=PASSED`, four requests without a request-limit status, and no
connection-limit excess. This is not sufficient to satisfy the required normal
operating-day observation, particularly because the API and R containers had
been recreated shortly before the preflight.

The same window had no error-level Nginx entries and no rate- or
connection-limit warnings. It had one warning at `2026/08/09T14:52:50` that a
proxied response was buffered to a temporary file. This is one warning, not an
upstream failure plus a separate buffering event: the word "upstream" caused
the first aggregate to count it in both categories. It is unrelated to rate
limiting and is not a timeout, connection failure, premature close, or `5xx`.
The dedicated SSE location retains disabled proxy buffering. Include the
warning in the normal-operation review and investigate only if it recurs or
affects temporary-disk use or SSE behavior.

### Seven remaining steps to finish the Phase 2 blocker

1. Record the change-control decision that `/api/v1/admin/login` supersedes
   the planned strict `/api/v1/admin/session` limiter probe, and confirm the
   live checksum/dry-run state again immediately before testing.
2. From one approved VPN client, perform the controlled dry-run general-API
   and admin-login excess probes. Record only response-status totals and
   `REJECTED_DRY_RUN`/`PASSED` counts; the old session endpoint is not a valid
   test of the strict JWT login zone.
3. During a real authenticated admin simulation, open three concurrent
   experiment SSE streams from the same client IP. Confirm two remain
   incremental, the third is logged as a connection-limit dry-run excess, and
   no established stream is interrupted.
4. Test all additional currently deployed JWT request-limit zones before
   enforcement: the shared test-creation/player-token issuance zone and the
   player start/answer zone, including the intended shared-IP player burst.
5. Complete a normal authenticated admin workflow, valid upload, over-limit
   upload (`413`), and full signed OR-to-player simulation. Then review at
   least one normal operating day of sanitized host/container logs; investigate
   every unexpected `429` or `5xx`, false positive, or recurring buffering
   warning before enforcement.
6. Create and deploy a reviewed, version-controlled enforcement revision with
   both dry-run directives disabled. Run `nginx -t` and perform a graceful
   reload, then repeat all limiter probes. Excesses must now receive the
   documented `429` `rate_limited` response while normal UI, API, upload, and
   SSE flows continue working.
7. Complete and record the remaining acceptance evidence: post-enforcement
   Phase 1 approved/non-approved-source, certificate, browser, forwarding,
   upload, and SSE checks; certificate-replacement, Compose-update,
   per-service-recovery, and network-first rollback rehearsals; current-commit
   backend/admin/R/Compose/Nginx validation; and the first seven daily
   enforcement reviews. Retain the DNS-rebinding risk as a public-launch
   blocker.

### Controlled dry-run general API and JWT-login probes — 2026-08-09

The operator ran the approved-client probe procedure from a VPN-connected PC.
The client reported only UTC boundaries; host Nginx logs were correlated using
the corresponding local timestamps. No credential, client address, raw request
line, header, body, or response body was displayed or recorded.

- General API probe: `2026-08-09T12:12:33Z`. A concurrent harmless 60-request
  request to a non-existent `/api/` path produced 60 `404` responses. Sanitized
  host access evidence recorded 21 `limit_req_status=PASSED` and 39
  `limit_req_status=REJECTED_DRY_RUN`; the host error log recorded 39 matching
  request-limit warnings.
- Strict JWT login probe: `2026-08-09T12:12:57Z`. Eight concurrent POSTs to
  `/api/v1/admin/login` with a deliberately invalid non-secret test value
  produced eight `401` responses. Sanitized host access evidence recorded six
  `limit_req_status=PASSED` and two `limit_req_status=REJECTED_DRY_RUN`; the
  host error log recorded two matching request-limit warnings.

Result: **both request-rate dry-run excess probes passed on the live JWT
deployment.** Requests were observed as excess but were not edge-rejected,
which is the expected dry-run behavior. For Phase 2 enforcement evidence, the
strict JWT `/api/v1/admin/login` limiter is the documented successor to the
original `/api/v1/admin/session` probe; the session endpoint was not used
because it no longer has the exact strict limiter. The remaining dry-run work
is the authenticated three-connection SSE probe, the additional active JWT
limiter-zone probes, normal workflow/upload/simulation observation, and the
sanitized normal-operating-day review.


### Controlled SSE connection-limit dry-run probe — 2026-08-09

The operator ran a fresh authenticated UI simulation from the approved
VPN-connected PC. The UI experiment terminal continued receiving diagnostic
events, providing the first SSE connection. Two additional same-client
connections were opened with local `curl` processes that discarded all event
content and intentionally ended after 35 seconds.

- Probe window: `2026-08-09T12:44:51Z` to `2026-08-09T12:45:27Z`.
- Each manual stream established HTTP `200`; each intentionally timed out with
  curl exit status `28` after the configured 35-second maximum duration. This
  is expected for an otherwise unbounded SSE response and is not an application
  or proxy failure.
- Sanitized host access evidence recorded two completed manual SSE requests:
  one `limit_conn_status=PASSED` and one
  `limit_conn_status=REJECTED_DRY_RUN`. The host error log recorded one matching
  connection-limit warning. The browser UI stream remained incremental during
  the overlap.

Result: **SSE connection-limit dry-run probe passed.** Three concurrent,
authenticated streams from one approved client IP were established; two streams
remained usable and the third was observed as excess without edge rejection.
The general-API, JWT-login, and SSE dry-run limiter probes are now complete.
Remaining work before enforcement is the additional active JWT limiter-zone
testing, normal authenticated workflow/upload/simulation observation, and the
sanitized normal-operating-day review.

### Controlled JWT issuance and player-limit dry-run probes — 2026-08-09

The operator ran both probes from the approved VPN client. Each request was
intentionally unauthenticated and targeted a harmless non-existent resource or
an endpoint that cannot mutate state without authorization. All client-visible
responses were `401`; no response bodies, client address, bearer token, or raw
request line was recorded.

- Shared issuance-zone probe: `2026-08-09T12:50:13Z`. Twelve concurrent
  requests to test creation and twelve concurrent requests to player-token
  issuance produced 24 `401` responses. Sanitized host evidence recorded four
  create requests and seven player-token requests as `PASSED`, with eight
  create and five player-token requests as `REJECTED_DRY_RUN`. The host error
  log recorded matching warning counts. The combined 13 dry-run excesses prove
  the two endpoint locations consume the same issuance zone.
- Shared player-zone probe: `2026-08-09T12:51:39Z` to
  `2026-08-09T12:51:40Z`. Eighty start and 80 answer requests produced 160
  `401` responses. Sanitized host evidence recorded all 80 start requests as
  `PASSED`, then 26 answer requests as `PASSED` and 54 as
  `REJECTED_DRY_RUN`, with 54 matching request-limit warnings. This confirms
  the start and answer locations consume the same player zone and that its
  excesses are observed without rejection in dry-run mode.

Result: **all additional active JWT request-limit dry-run probes passed.** The
general API, JWT login, SSE connection, shared issuance, and shared player
zones have each produced the required dry-run excess evidence. Remaining work
before enforcement is a normal authenticated administrative workflow, valid and
over-limit upload checks, a complete simulation, and at least one normal
operating day of sanitized log observation without false-positive throttling.

### Live source-upload limit confirmation — 2026-08-09

A read-only command run in the live API container printed only the effective
numeric `ADMIN_SOURCE_MAX_BYTES` setting: `10000000` bytes. No rendered
environment values or secrets were displayed. The reviewed and active host
Nginx configuration retains `client_max_body_size 11m`, equivalent to
11,534,336 bytes. The normal-workflow upload validation must therefore
distinguish the application `413` above 10,000,000 bytes from the edge-Nginx
`413` above 11 MiB.

### Normal authenticated workflow and upload-boundary checks — 2026-08-09

The operator completed a normal authenticated administrative workflow from the
approved VPN client between `2026-08-09T13:09:26Z` and
`2026-08-09T13:14:35Z`. A valid source upload succeeded, the 10,000,001-byte
application-limit upload and 11,600,000-byte edge-limit upload each returned
`413`, and a test simulation ran to completion without a reported error.

Sanitized host correlation for the local 16:09–16:15 window recorded one
successful source-material creation (`201`), four normal source-material reads
(`200`), two source-material `413` responses, two test-creation responses
(`201`), and nine player responses (`200`). All normal OR/player requests had
`limit_req_status=PASSED`; there were no request- or connection-limit warnings.

The two upload rejections were correctly distinguished without recording any
source content: one `413` had upstream status `413`, confirming the
application's 10,000,000-byte limit; one had no upstream status and produced
the expected Nginx `client intended to send too large body` error-level event,
confirming the 11 MiB edge boundary. No unexpected Nginx error-level entry was
present.

Result: **normal workflow, valid upload, application-limit `413`, edge-limit
`413`, and complete simulation checks passed.** Begin the separate one-normal-
operating-day dry-run observation after this workflow. During that interval,
use the restricted application normally and record only sanitized traffic,
limiter, error, health, storage, and certificate findings; do not run further
artificial burst probes.

### One-normal-operating-day dry-run observation — 2026-08-09 to 2026-08-11

The operator reported no user-visible issue during the restricted dry-run
observation from `2026-08-09T13:17:56Z` through
`2026-08-11T05:32:47Z`, a duration of 40 hours, 14 minutes, and 51 seconds.
No artificial burst probe was run during the recorded window.

Sanitized host access evidence for the corresponding local-time window
recorded 214 requests: 185 `200`, six `201`, two `202`, six `304`, six `308`,
five `401`, and four `413`. It recorded 177
`limit_req_status=PASSED` values and no `REJECTED_DRY_RUN` request or
connection result; 37 requests and 212 connections did not traverse a
request/connection-limited location, while the two completed SSE connections
were `limit_conn_status=PASSED`.

The host error log recorded no request- or connection-limit warning, upstream
timeout, premature upstream close, upstream connection failure, no-live-
upstream condition, or error-level event. Ten ordinary-response buffering
warnings recurred: four API responses, five static-asset responses, and one
player-SPA response. The exact SSE location was not represented in those
warnings and remains configured with proxy buffering disabled. This is a
documented non-limiter observation; investigate if the warning frequency or
temporary-disk use grows.

Current post-observation checks passed: Nginx syntax validation and service
status were healthy; all four Compose services were healthy with restart count
zero; listeners remained limited to host IPv4 80/443 plus loopback 8080 and
the approved SSH/resolver listeners; root disk use was 30%, inode use 4%, and
Docker build cache was 37.89 GB with 20.22 GB reclaimable. NTP remained
synchronized, no reboot marker was present, and the IP-SAN certificate expires
on `2026-10-29T13:43:59Z`, more than 30 days after this review.

Follow-up required before marking this observation completely clean: all four
window `413` responses were source-material requests with upstream status
`413`, meaning they were application-limit rejections rather than host-edge
rejections. The operator must confirm they were intentional expected
over-limit upload attempts; otherwise investigate the affected normal upload
workflow before enforcement.

### Observation `413` disposition — 2026-08-11

The operator confirmed that the four application-side source-material `413`
responses were expected. They resulted from intentionally attempting to upload
a PDF with 111 pages while the deployment configuration sets the maximum PDF
page count to 100. The file was below both the 10,000,000-byte application
source-size limit and the 11 MiB host-Nginx request-body limit.

Result: **the four observation-window `413` responses are expected configured
PDF-page-limit rejections, not upload-size failures or limiter false positives.**
The 40-hour normal-operating-day dry-run observation is accepted. The dry-run
gate is complete; retain both dry-run directives until the reviewed enforcement
revision is deliberately deployed.

### Phase 2 limiter-enforcement deployment — 2026-08-11

After review of the completed dry-run gate, the enforcement revision was
created as Git commit `61670c0` (`Enable Nginx rate-limit enforcement`). It
changes only the two reviewed host-Nginx directives from dry-run `on` to `off`:
`limit_req_dry_run` and `limit_conn_dry_run`. Existing zones, rates, bursts,
the edge `429` handler, and SSE settings were not changed. The pre-enforcement
active site configuration was copied to the privileged VM backup area before
installation.

The reviewed repository file was installed through the root-owned active-site
path. `nginx -t` passed and Nginx was gracefully reloaded. The repository and
active-site SHA-256 checksums both equal
`bee6c7b2bb1fdbc26baa72e7ccc3f789071da90547782f79adfdcf12b8269ae5`.
Read-only verification confirmed both dry-run directives are `off`, the Nginx
service is active, and all four Compose services are healthy. Nginx continues
to listen on host IPv4 ports 80 and 443.

Result: **Step 6 deployment items 1–4 passed.** The immediate post-enforcement
limiter and normal-workflow acceptance probes remain required before the
enforcement step can be accepted.

### Post-enforcement request-limiter evidence and edge-header correction — 2026-08-11

The first approved-client enforcement burst confirmed that the general API
zone returned 21 `404` and 39 `429` responses, and the strict JWT-login zone
returned six `401` and two `429` responses. That established that dry-run was
disabled and excess requests were actively rejected. The initial response
inspection also identified a configuration defect: edge-generated `429`
responses lacked the required host-generated `X-Request-ID` header. The
client-side body-inspection helper had a shell-quoting error, so its initial
body result was not used as evidence.

The defect was corrected in Git commit `d590d84` (`Preserve edge headers on
rate limits`). The named rate-limit handler now explicitly includes the
public-edge headers, because Nginx does not inherit server-level `add_header`
directives into a location that defines its own header. The preceding active
site was backed up in the privileged VM backup area, the reviewed file was
installed, `nginx -t` passed, and Nginx was gracefully reloaded. The repository
and active-site SHA-256 checksums both equal
`cb10f4c7d316e3c707432d9892f071755945728d94220811bab58f516b14264c`.
All four Compose services remained healthy.

The corrected approved-client retry produced 21 `404` and 39 `429` responses
for the general API burst, and six `401` and two `429` responses for the JWT
login burst. Its sanitized inspection of one edge `429` confirmed the exact
`rate_limited` JSON envelope, exactly one `X-Request-ID` header, and
`Cache-Control: no-store`. Sanitized host evidence for the corresponding
local-time review window recorded 21 `404`, six `401`, and 41 `429` responses;
27 `limit_req_status=PASSED` and 41 `limit_req_status=REJECTED`; 41 matching
request-limit warnings; no connection-limit warning; and no error-level Nginx
entry.

Result: **general API and strict JWT-login post-enforcement acceptance passed.**
The shared issuance/player request-limit probes, authenticated three-stream
SSE connection-limit probe, and normal-workflow acceptance check remain.

### Post-enforcement shared JWT-zone evidence — 2026-08-11

The approved VPN client ran harmless unauthenticated probes against the two
shared request-limit zones. The issuance-zone probe at
`2026-08-11T05:57:35Z` produced 11 `401` and 13 `429` responses across test
creation and player-token issuance. The shared-player-zone probe at
`2026-08-11T05:58:07Z` produced 124 `401` and 36 `429` responses across player
start and answer requests. No valid resource identifier or credential was used
or recorded.

Sanitized host evidence for the corresponding local-time window recorded 135
`401` and 49 `429` responses: 135 `limit_req_status=PASSED`, 49
`limit_req_status=REJECTED`, and 49 matching request-limit warnings. There was
no connection-limit warning and no error-level Nginx entry.

Result: **the shared issuance and shared player request-limit zones enforce
correctly after dry-run disablement.** The authenticated three-stream SSE
connection-limit probe and normal-workflow acceptance check remain.

### Post-enforcement three-stream SSE connection-limit probe — 2026-08-11

From one approved VPN client, the operator held the admin UI diagnostics
stream open for a live simulation and ran two additional authenticated SSE
connections from that same client IP. No JWT, response body, diagnostic event
payload, request ID, client address, or query value was recorded.

- Probe window: `2026-08-11T07:27:41Z` to `2026-08-11T07:28:41Z`.
- The browser stream remained incremental. The accepted additional curl stream
  returned `200`, increased from 36 to 54 SSE data frames after a UI action,
  and reached 87 frames before its intentional 60-second curl timeout (exit
  status `28`).
- The third stream returned `429`, contained no SSE data frame, had the exact
  `rate_limited` envelope, and contained exactly one `X-Request-ID` header.
- Sanitized host correlation, extended only to allow completed SSE requests to
  be written to the access log, recorded two `200` responses with
  `limit_conn_status=PASSED` and one `429` with
  `limit_conn_status=REJECTED`. The error log had one matching
  connection-limit warning, no request-limit warning, and no error-level
  entry.

Result: **the enforced three-stream SSE probe passed.** Two concurrent streams
remained incremental; the third was edge-rejected without interrupting either
established stream.

### Post-enforcement normal authenticated workflow and upload check — 2026-08-11

The operator reported completing a normal authenticated administrative
workflow after enforcement. One valid source upload succeeded, and two
deliberately over-limit source uploads were rejected as intended. No
client-visible rate- or connection-limit false positive was reported. This
entry records the operator-supplied outcome only; a later final acceptance
review must retain the corresponding sanitized status/log correlation without
recording source content or credentials.

Result: **post-enforcement normal workflow and upload-boundary behavior passed
on the operator report.**

### OpenStack exact-port security-group re-confirmation — 2026-08-11

The operator confirmed the OpenStack/Neutron security groups attached to the
exact VM port continue to match the Phase 1 required policy: TCP 80 and 443
are restricted to `172.20.0.0/16` and `193.40.0.0/16`, SSH retains its approved
restrictions, and neither `0.0.0.0/0` nor `::/0` ingress is present. No cloud
network rule was changed for this confirmation.

Result: **the OpenStack security-group portion of the external Phase 1 gate is
reconfirmed.** The approved-client repeat checks and the independent
non-approved-source denial check remain separate acceptance evidence.

### Post-enforcement independent non-approved-source denial check — 2026-08-11

From an independent non-approved source with the VPN disconnected, the
operator tested the public VM IP without changing any OpenStack, firewall, or
host configuration. No client identifier, response body, credential, or query
value was recorded.

- Probe window: `2026-08-11T08:01:17Z` to `2026-08-11T08:01:37Z`.
- TCP ports 80, 443, 8080, and 8000 each produced no HTTP response and were
  classified as denied by the client-side probe.

Result: **the post-enforcement independent non-approved-source denial check
passed for all four required ports.**

### Post-enforcement approved-client external revalidation — 2026-08-11

From an approved VPN client, the operator repeated the external browser, TLS,
redirect, and forwarded-header checks without using credentials. No response
body, request ID, certificate fingerprint, query value, or client identifier
was recorded.

- Probe window: `2026-08-11T08:05:20Z` to `2026-08-11T08:05:22Z`.
- The exact-path HTTP check returned `308` and preserved its path and query.
  The HTTPS root returned `200` with one CSP header, `Referrer-Policy:
  no-referrer`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  no HSTS header, and exactly one `X-Request-ID` header.
- The served certificate metadata matched both the expected IP subject/SAN and
  the recorded fingerprint. The clean browser check passed with no reported
  mixed-content, CORS, asset-load, or CSP error.
- A request containing forged forwarding and request-ID headers returned a
  replacement `X-Request-ID`; the established host edge configuration replaces
  all supplied forwarding metadata with the public-edge values.
- Sanitized host correlation recorded three related requests: two `200`, one
  `308`, and a generated request ID on each; the host error log had no entry
  or error-level event in the window.

Result: **the post-enforcement approved-client external revalidation passed.**

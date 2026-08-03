# Task 9 Deployment Check Log

Date: 2026-07-31

## Scope

Read-only verification of the Task 9 deployment sequence and Task 10
acceptance criteria. No application, Compose, firewall, Nginx, certificate,
container, or service state was changed during these checks.

## Confirmed results

- All three Compose services are running and healthy.
- The web service publishes only `127.0.0.1:8080->8080`; API and R expose
  `8000/tcp` only as container metadata.
- The host has no listener on port 8000.
- The live Docker networks match the deployment configuration:
  - `edge`: `172.30.0.0/24`
  - `compute`: `172.18.0.0/16`, internal
- Host Nginx is enabled and active, and the complete configuration passes
  `nginx -t`.
- Host Nginx owns IPv4 ports 80 and 443. No IPv6 80/443 listener is present.
- The container health endpoint and API readiness endpoint return `200` over
  the loopback publication.
- Requests to the exact VM IP on HTTP return `308` and preserve the complete
  path and query string in the HTTPS location.
- HTTPS serves the SPA successfully with the configured CSP, referrer,
  frame-protection, and content-type headers. HSTS is absent as required for
  this temporary self-signed phase.
- Public access to `/nginx-health`, `/health/*`, `/docs`, `/redoc`,
  `/openapi.json`, `/internal/*`, `/test/*`, and R documentation paths returns
  `404`.
- Unknown HTTP and HTTPS hosts are rejected by the host Nginx catch-all.
- TLS 1.2 and TLS 1.3 negotiate successfully. TLS 1.0 and TLS 1.1 are
  rejected.
- The served certificate matches the VM certificate:
  - Subject: `CN=193.40.157.124`
  - SAN: `IP:193.40.157.124`
  - SHA-256 fingerprint:
    `73:EA:4F:30:DB:F4:23:41:4A:FA:85:52:E6:B8:5F:48:36:C9:F4:DD:48:A1:81:6C:D9:F6:C3:2A:76:20:CB:21`
  - Valid until: `2026-10-29 13:43:59 UTC`
- UFW is active with default-deny incoming and the recorded approved CIDR
  rules for SSH, HTTP, and HTTPS.
- The repository worktree remained clean after the checks.

## Not verified from this environment

- End-to-end access from an approved external client and rejection from a
  non-approved external source.
- Current OpenStack security-group rules on the exact VM port.
- Full external API, upload-limit, SSE-streaming, forged-forwarded-header,
  and production log-content acceptance tests.

These require testing from the relevant external clients or operational
environment and should be completed before declaring the phase fully accepted.

## Follow-up observations from the initial check

- The initial HTTPS check found duplicate CSP and related security headers,
  because both the host and container Nginx layers added them. Action 1 below
  consolidates ownership at the public host layer while retaining the inner
  container headers for direct diagnostics.
- The initial global host Nginx configuration listed TLS 1.0 and TLS 1.1,
  while the active application server already restricted the endpoint to TLS
  1.2 and 1.3. Action 2 below now aligns the global baseline as well.

## Required follow-up actions

### 1. Consolidate duplicate security headers

Status: completed on 2026-07-31.

This is a deployment-proxy configuration cleanup, not an application-code
change. The public HTTPS response currently receives the same CSP,
`Referrer-Policy`, `X-Content-Type-Options`, and `X-Frame-Options` headers from
both host Nginx and the container Nginx.

Recommended change:

- Update the version-controlled [host Nginx template](../../../deploy/nginx/opiraja.conf)
  so the public proxy hides those four upstream response headers before the
  host layer adds its canonical values.
- Keep the container headers in `admin/nginx.conf` so direct loopback/container
  diagnostics retain the existing protections.
- Install the revised host site on the VM, run `sudo nginx -t`, and perform a
  graceful Nginx reload.
- Verify that each public response contains one effective copy of each header.

This does not require a backend or React code change, Compose change, image
rebuild, or container recreation.

### 2. Remove obsolete TLS versions from the global host Nginx baseline

Status: completed on 2026-07-31.

This is an actual-VM Nginx configuration hardening change. The active Opiraja
server already rejects TLS 1.0 and TLS 1.1, so this is not blocking the current
endpoint, but the package-wide setting should not permit obsolete protocols for
any future TLS server.

Required operational change:

- Change the global `/etc/nginx/nginx.conf` `ssl_protocols` setting from
  `TLSv1 TLSv1.1 TLSv1.2 TLSv1.3` to `TLSv1.2 TLSv1.3`, using the VM's normal
  configuration-management or privileged deployment process.
- Run `sudo nginx -t` and gracefully reload Nginx.
- Recheck TLS 1.2/1.3 success and TLS 1.0/1.1 rejection.

No application-code, Compose, Docker image, or certificate change is needed.
The repository should record this as a VM baseline/runbook requirement because
the global package configuration is not owned by the application repository.

### 3. Complete external acceptance checks

Status: outstanding; this remains the final manual/external validation gate.

These observations do not currently identify a required code or configuration
change. They identify checks that remain outstanding:

- From an approved client, verify HTTP/HTTPS access and compare the served
  certificate fingerprint with the recorded VM fingerprint.
- From a non-approved source, verify that HTTP/HTTPS access is denied.
- Confirm the OpenStack security-group rules on the exact VM port.
- Exercise normal API calls, a valid upload, an oversized upload, a complete
  SSE simulation, forged `X-Forwarded-*`/request-ID headers, and production
  logging behavior.

Apply further code, deployment, firewall, or VM changes only if one of these
tests fails. The current evidence does not justify changing application code,
Compose networking, certificate material, or UFW rules.

## Follow-up execution record

### Action 1: security-header consolidation

Updated the version-controlled [`deploy/nginx/opiraja.conf`](../../../deploy/nginx/opiraja.conf)
with `proxy_hide_header` directives for `Content-Security-Policy`,
`Referrer-Policy`, `X-Content-Type-Options`, and `X-Frame-Options`. The
container configuration in `admin/nginx.conf` was intentionally left
unchanged, so direct loopback/container diagnostics retain their existing
headers.

Before installing the site, the previous VM copy was backed up under
`/var/backups/nginx/opiraja-task9-20260731/opiraja.conf.pre-header-cleanup`
by the privileged deployment process. The revised site was installed at
`/etc/nginx/sites-available/opiraja.conf`, passed `sudo nginx -t`, and was
gracefully reloaded.

The post-reload local HTTPS check returned exactly one effective copy of each
canonical header on the SPA response:

- `Content-Security-Policy`
- `Referrer-Policy: no-referrer`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`

### Action 2: global TLS baseline hardening

The live `/etc/nginx/nginx.conf` setting was changed from
`TLSv1 TLSv1.1 TLSv1.2 TLSv1.3` to `TLSv1.2 TLSv1.3`. The previous global file
was backed up under
`/var/backups/nginx/opiraja-task9-20260731/nginx.conf.pre-tls-baseline`.
The complete configuration passed `sudo nginx -t` and Nginx was gracefully
reloaded.

Post-reload local protocol checks confirmed TLS 1.2 and TLS 1.3 negotiation.
TLS 1.0 and TLS 1.1 failed with `no protocols available`. The self-signed
certificate verification warning in the successful checks is expected for
this phase. The global baseline remains VM/package configuration rather than
a repository-owned file; this log is the repository record of the operational
change.

## Action 3: detailed external acceptance procedure

Action 3 is a validation gate, not an instruction to change the application.
It should be completed after actions 1 and 2, with the results recorded in
this log or the deployment change record. Do not record bearer tokens,
cookies, uploaded content, request bodies, query values containing secrets, or
private-key material.

### Preparation and ownership

An operator must provide or identify the following before testing:

1. An approved client on a network whose source CIDR is explicitly allowed by
   both the OpenStack security group and Ubuntu firewall. A browser is useful
   for the certificate-warning and SPA checks; a shell on the same client is
   useful for repeatable HTTP/TLS checks.
2. A genuinely non-approved source network for the denial test. The VM itself
   and a loopback request are not valid substitutes for an independent
   source. If no such source is available, the denial result must remain
   unverified rather than being inferred from local tests.
3. Access to the OpenStack project or its approved operational CLI, plus the
   exact VM port identity, so the security-group rules can be inspected rather
   than inferred from the guest. This may require a cloud administrator.
4. A non-production test account or otherwise approved test credential for a
   normal API call, a valid upload, and a complete admin-experiment SSE run.
   The credential should be entered only on the expected HTTPS endpoint after
   the certificate fingerprint has been checked.

An agent can prepare commands, scripts, test payloads, and an evidence table;
inspect repository configuration; run checks from an already-authorized
client when that client is actually available; interpret failures; and update
the log with sanitized results. An agent cannot create the independent
network vantage, approve a browser certificate warning on behalf of an
operator, obtain missing OpenStack permissions, or safely invent the API
credentials and test data required for authenticated application flows.

### 1. Verify the cloud and host ingress policy

From the OpenStack control plane, inspect the security groups attached to the
exact VM port and record the rule identifiers or an equivalent sanitized
export. Confirm that TCP 80 and 443 allow only the approved VPN and test
CIDRs, TCP 22 retains its existing administration restrictions, and ports
8080, 8000, Docker API ports, and unrelated services have no unintended
ingress. Confirm that neither `0.0.0.0/0` nor `::/0` was added for this phase.

On the VM, an operator or agent with the required access should record the
effective UFW/nftables policy and listeners after the external tests. The
expected result is host Nginx on IPv4 80/443, loopback-only web publication
on 127.0.0.1:8080, and no host listener on 8000. IPv6 80/443 must remain
closed unless it is deliberately included in every policy and certificate
decision; this plan does not include it.

### 2. Test from an approved client

Use the public IPv4 address, not a loopback address or an internal container
name.

- Request an HTTP URL containing both a non-root path and query string. Confirm
  a `308` redirect to the identical path and query under
  `https://193.40.157.124`.
- Use `openssl s_client -connect 193.40.157.124:443 -showcerts` or an
  equivalent client to capture the served certificate. Confirm the SAN is
  `IP:193.40.157.124` and compare the SHA-256 fingerprint out-of-band with
  the recorded value:
  `73:EA:4F:30:DB:F4:23:41:4A:FA:85:52:E6:B8:5F:48:36:C9:F4:DD:48:A1:81:6C:D9:F6:C3:2A:76:20:CB:21`.
  The browser should show the expected self-signed/untrusted warning and no
  name-mismatch warning. Certificate acceptance is an operator decision.
- Open the SPA and check browser developer tools for mixed-content, CORS, or
  failed asset errors. Confirm the response has one copy of each canonical
  security header and no HSTS header.
- Make a normal authenticated API request and confirm any externally visible
  generated URL or redirect uses the public HTTPS origin.
- Upload a representative valid file below the configured body/source limits;
  then submit a deliberately oversized test file and confirm a controlled
  `413` without exposing stack traces or internal service details.
- Run one complete admin-experiment simulation and observe the SSE stream
  incrementally until its normal completion. Record that it does not stop
  early because of buffering or the upstream read timeout.
- Send deliberately forged `X-Forwarded-For`, `X-Forwarded-Proto`,
  `X-Real-IP`, and `X-Request-ID` request headers. Use the application's
  observable behavior and sanitized server logs to confirm the public edge
  replaces these values with the actual client IP, `https`, and a host-created
  request ID. Do not use real credentials in diagnostic header values.
- Inspect the relevant host, container, API, and application logs for request
  IDs, status, and latency/upstream timing. Confirm that authorization values,
  cookies, forwarded secrets, request bodies, uploaded content, and sensitive
  query values are not logged. If a logging format includes a full request
  line, treat query-string exposure as a finding rather than assuming it is
  safe.

### 3. Test from a non-approved source

From the independent source, attempt both HTTP and HTTPS to the public IP.
The expected result is denial at the cloud or host-firewall boundary (often a
timeout or connection refusal; an application response is not success). Also
test direct ports 8080 and 8000 if the source can reach them. Do not weaken a
rule temporarily just to make this test easier. Record the source network,
timestamp, destination, and observed result without recording unrelated
client identifiers.

### 4. Decide whether remediation is needed

If all checks pass, record the approved and denied source CIDRs, security
group evidence, certificate comparison, protocol results, application-flow
results, and sanitized log review; then mark the HTTPS phase accepted subject
to the planned certificate-expiry reminder. If a check fails, classify it
first as OpenStack ingress, Ubuntu firewall, host Nginx, container proxy,
application, certificate, or observability behavior. Preserve the evidence and
apply only the smallest reviewed change in the corresponding layer. Do not
change Compose networking, certificate material, firewall rules, or application
code merely because an external check is still outstanding.

### Action 3 execution evidence

#### Step 1 — VM host ingress policy

Checked on 2026-08-03 12:37:32+03:00 with read-only `ufw`, `nftables`, and
TCP-listener inspection. No VM configuration or service state was changed.

- UFW is active with `deny (incoming)`, `allow (outgoing)`, and `deny
  (routed)` defaults. Its only IPv4 inbound allow rules are TCP 22, 80, and
  443 from `172.20.0.0/16` and `193.40.0.0/16`.
- The effective nftables input policy is `drop`; its UFW user-input chain
  contains the same six source/port rules. The IPv6 input policy is also
  `drop`, and it has no IPv6 user allow rules for HTTP or HTTPS.
- Host Nginx is listening on `0.0.0.0:80` and `0.0.0.0:443`. No listener is
  bound to `[::]:80` or `[::]:443`.
- Docker's web publication is bound only to `127.0.0.1:8080`; nftables also
  drops TCP 8080 packets addressed to `127.0.0.1` when they do not arrive on
  loopback. There is no host TCP listener on port 8000 and no Docker API TCP
  listener.
- Other observed host TCP listeners are the approved SSH service on 22 and
  local system DNS on loopback port 53. Neither is an unintended public web
  publication.

Result: **passed** for the VM portion of Step 1. This does not replace the
separate OpenStack security-group evidence already inspected by the operator,
nor the approved/non-approved external-client tests in Steps 2 and 3.

#### Step 2 — approved external client (partial)

Tested from an approved VPN client on 2026-08-03. No credentials, cookies,
request bodies, uploaded content, or sensitive query values were recorded.

- HTTP `GET /acceptance-check?source=vpn` returned `308` and redirected to
  the identical path and query on `https://193.40.157.124`.
- The served TLS certificate had the expected IP SAN and the recorded
  SHA-256 fingerprint.
- HTTPS `GET /` returned `200` and exactly one copy of each canonical
  browser-security header: CSP, `Referrer-Policy`,
  `X-Content-Type-Options`, and `X-Frame-Options`. HSTS was absent as
  required for the self-signed phase.
- Finding — the public HTTPS response did **not** include `X-Request-ID`.
  Read-only VM inspection confirmed that the installed
  `/etc/nginx/sites-enabled/opiraja.conf` is behind the repository template:
  it lacks the public `add_header X-Request-ID $request_id always` directive
  and the related upstream-header hiding/rate-limit configuration. The
  repository template contains those directives. Classify this as **host
  Nginx deployment drift**; do not mark forwarded-header/request-ID
  acceptance passed until the reviewed site configuration is installed,
  tested, reloaded, and retested.
- Browser developer tools reported CSP blocks for inline scripts attributed to
  `utils.js` and `node.js`, while the SPA document and its same-origin assets
  loaded successfully. The version-controlled SPA entry document contains no
  inline script, so the source of these messages is not yet established. A
  clean browser profile/private window with extensions disabled must be used
  to determine whether they are browser/extension injection or an application
  finding.

Result: **partially passed; remediation required before Step 2 acceptance**.
The authenticated API, upload-boundary, SSE, forwarded-metadata/log, and
clean-browser checks remain outstanding.

#### Step 3 — non-approved external source

Tested on 2026-08-03 12:55:51+03:00 from a home ISP with the VPN disconnected.
The source was independently confirmed unable to reach the VPN/SSH access
path. No client IP address or other identifying client detail was recorded.

| Destination TCP port | Result |
| --- | --- |
| 80 | Connection timeout after approximately five seconds (`curl` exit 28) |
| 443 | Connection timeout after approximately five seconds (`curl` exit 28) |
| 8080 | Connection timeout after approximately five seconds (`curl` exit 28) |
| 8000 | Connection timeout after approximately five seconds (`curl` exit 28) |

Result: **passed**. The absence of an HTTP/application response on all four
ports is the expected ingress-boundary denial. No cloud or host firewall rule
was weakened for this test.

### Action 3 current status

Step 1 (VM and operator-reported OpenStack review) and Step 3 pass. Step 2 is
not accepted: the installed host Nginx configuration is behind the reviewed
repository template, and its required authenticated API, upload, SSE,
forwarded-metadata/log, and clean-browser checks remain outstanding. Do not
lock Phase 1 until that finding is remediated and Step 2 is completed.

### Step 2 revalidation after Phase 2 dry-run Nginx deployment

From the approved VPN client during 2026-08-03 13:31–13:33 EEST, the operator
confirmed that the public HTTPS/header check, forged-forwarded-header check,
and clean-browser-profile SPA check passed. In particular, the response used
one host-generated `X-Request-ID` rather than the supplied forged value, and
the clean browser reported no application mixed-content, CORS, asset-load, or
CSP errors.

Sanitized host evidence for the same window recorded six requests, all `200`,
with a generated request ID on every response. The active host configuration
sets the forwarding fields from `$remote_addr`/`https` and hides upstream
`X-Request-ID`, consistent with the observed result. One Nginx warning
recorded normal-response proxy buffering to a temporary file; it did not cause
a failed response and is not the SSE location, where buffering remains
disabled. Retain it for the planned dry-run monitoring review.

Result: the Nginx deployment-drift, forged-metadata/request-ID, and
clean-browser findings are resolved. The authenticated API, upload-boundary,
SSE, and log-sanitization portions of Step 2 remain outstanding.

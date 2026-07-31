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

## Follow-up observations

- HTTPS responses currently contain duplicate CSP and related security headers,
  because both the host and container Nginx layers add them. The values are
  consistent, so this did not block the checks, but header ownership should be
  consolidated later.
- The global host Nginx configuration still lists TLS 1.0 and TLS 1.1, while
  the active application server blocks explicitly restrict TLS to 1.2 and
  1.3. The active endpoint is correct; the global setting is a future
  configuration-drift hazard if another TLS server is added.

## Required follow-up actions

### 1. Consolidate duplicate security headers

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

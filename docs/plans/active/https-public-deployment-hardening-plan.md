# HTTPS and Public-Deployment Hardening Plan

## Summary

Use a layered deployment:

```text
Browser
  → OpenStack security group
  → Ubuntu firewall
  → Host Nginx :80/:443 (TLS and public controls)
  → 127.0.0.1:8080
  → Compose web Nginx
  → FastAPI:8000
  → R:8000
```

Only browser-to-host traffic needs HTTPS. FastAPI and R remain HTTP inside the
single VM's isolated Docker networks.

Roll out in two gates:

1. Deploy browser-trusted HTTPS while access remains VPN-only.
2. Open ports 80/443 publicly only after JWT/real authorization replaces the
   currently permissive OR/player authorization.

HTTPS alone is not approval for public launch.

## Implementation Changes

### Host Nginx and certificates

- Add a version-controlled host-Nginx template and deployment runbook, but keep
  certificates and keys outside Git and Docker.
- Require university IT to provide:
  - The final FQDN.
  - A publicly trusted certificate covering that FQDN, including the full chain
    and private key.
  - A documented renewal owner, automated handoff or notification process, and
    revocation process.
- Treat an internal university CA as insufficient for public launch unless its
  root is trusted by every intended browser.
- If IT delegates DNS automation instead, use automated
  [DNS-01 validation](https://letsencrypt.org/docs/challenge-types/) with
  narrowly scoped DNS credentials. Do not expose the VM publicly merely to use
  HTTP-01.
- Store key material under `/etc/nginx/tls/opiraja/`, owned by root; private key
  mode `0600`. Never place it in `.env`, a container image, or the repository.
- Configure host Nginx to:
  - Listen on TLS 443 for the exact university hostname.
  - Support TLS 1.2 and 1.3 using Nginx defaults unless university policy is
    stricter.
  - Redirect the exact hostname on port 80 to the same HTTPS URI with `308`.
  - Reject unknown `Host`/SNI values rather than redirecting them.
  - Proxy only to `http://127.0.0.1:8080`.
  - Replace client-supplied forwarding headers with trusted values: `Host`,
    `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto=https`, and request ID.
  - Preserve SSE behavior with buffering/cache disabled and the existing long
    read timeout.
  - Enforce the existing approximately 11 MiB body limit and bounded
    header/body/upstream timeouts.
  - Block public `/health/*`, `/docs`, `/redoc`, `/openapi.json`, `/internal/*`,
    and R documentation paths.
  - Add HSTS on HTTPS only, initially `max-age=86400`; increase to one year after
    a stable observation period. Do not enable `includeSubDomains` or preload.
  - Start public rate-limit defaults at 10 API requests/second/IP with burst 20,
    stricter admin-session limits, and at most two concurrent SSE
    connections/IP. Exempt an established SSE stream from request-rate limiting
    and monitor `429` responses.
- Validate renewed certificates with `nginx -t` and reload Nginx without
  rebuilding containers. Alert at 30, 14, and 7 days before expiry.

### Compose and admin

- Change `web` publication from `${HTTP_PORT:-80}:8080` to
  `127.0.0.1:8080:8080`; host Nginx exclusively owns public ports 80/443.
- Keep API and R port 8000 unpublished.
- Preserve current read-only filesystems, non-root users, dropped capabilities,
  `no-new-privileges`, PID limits, tmpfs mounts, and log rotation.
- Keep the SPA's relative `/api/...` URLs unchanged: they automatically become
  same-origin HTTPS and require no CORS configuration.
- Update inner `admin/nginx.conf` to preserve the trusted external scheme/client
  chain supplied by host Nginx instead of replacing `X-Forwarded-Proto` with its
  internal HTTP scheme.
- Retain the strict CSP and other browser headers. Do not store certificates in
  the admin image.
- Continue treating the `sessionStorage` admin bearer as transitional. Rotate
  `ADMIN_ACCESS_KEY` after leaving HTTP and again at public cutover.

### Backend

- Enable Uvicorn proxy-header processing with an explicit trusted Docker edge
  subnet via `FORWARDED_ALLOW_IPS`; never trust arbitrary Internet clients.
- Assign the Compose `edge` network an explicit non-conflicting subnet selected
  after checking VM, VPN, and Docker routes. Only `web` and `api` may join it.
- Add production `ALLOWED_HOSTS` configuration and Starlette trusted-host
  enforcement for the public FQDN plus internal health-check names/addresses.
- Keep HTTPS redirects at host Nginx, not FastAPI, preventing redirect loops
  over the internal HTTP hop.
- Keep `R_SERVICE_URL=http://r-service:8000` and the Supabase URL HTTPS.
- Keep same-origin behavior; do not add permissive CORS.
- Disable public FastAPI documentation and dependency-detailed readiness
  responses at the edge.
- Before public launch:
  - Replace permissive OR/player authorization with the planned authenticated
    policy; anonymous create/read/play operations must return `401` or `403`.
  - Disable remote-URL source ingestion by default or close its DNS-rebinding
    and metadata-service exposure. File upload can remain available.
  - Ensure JWT/cookie work, when implemented, uses `Secure`, `HttpOnly`, and an
    intentional `SameSite` policy.

### R service

- Make no HTTPS, contract, or application-code changes.
- Retain plaintext `http://r-service:8000` on the internal `compute` network.
- Retain `compute.internal: true`, internal HTTP health checks, and the absence
  of host port publication and credentials.
- Never proxy R routes or Plumber documentation through either Nginx layer.
- mTLS between FastAPI and R remains unnecessary while both run on one
  controlled Docker host.

## VM and OpenStack Operations

- Inspect `ip route`, `docker network ls/inspect`, `ss -lntup`, active
  UFW/nftables rules, IPv6 state, disk space, time synchronization, and all
  OpenStack ports/security groups before changing exposure.
- Phase 1 security groups and Ubuntu firewall:
  - Allow 80/443 only from VPN CIDRs.
  - Allow SSH only from VPN/administrative CIDRs.
  - Deny inbound 8000, Docker API ports, and every unrelated port.
- Phase 2, only after the authorization gate passes:
  - Allow TCP 80/443 from `0.0.0.0/0` and `::/0`.
  - Keep SSH VPN/admin-only and all internal ports closed.
  - Port 80 must serve redirects only.
- Verify rules on the exact Neutron port, because OpenStack security groups are
  attached to ports and are default-deny allowlists
  ([OpenStack security-group documentation](https://docs.openstack.org/nova/latest/user/security-groups.html)).
- Keep Ubuntu security updates enabled, Docker/Nginx patched, membership in the
  Docker group minimal, and `/var/run/docker.sock` inaccessible to application
  containers.
- Restrict `.env` to the deployment owner with mode `0600`; rotate
  Supabase/admin credentials if they may have traversed or been exposed through
  the old HTTP deployment.
- Keep access logs free of authorization headers, cookies, uploaded bodies, and
  secrets. Monitor Nginx error/429/5xx rates, certificate expiry, container
  restarts, disk use, and API/R readiness.

## Test and Cutover Plan

- Run existing module checks:
  - Admin: `npm test`, `npm run lint`, `npm run build`.
  - Backend using `backend/.venv`: tests and `python -m pyright`.
  - R: existing `testthat` suite.
  - Validate both Nginx configurations with `nginx -t`.
- Compose/network acceptance:
  - `docker compose config` succeeds.
  - Only `127.0.0.1:8080` is published by Compose.
  - Neither API nor R is reachable on VM port 8000.
  - API can still reach R internally and readiness recovers after R restarts.
- HTTPS acceptance:
  - Certificate hostname, chain, and expiry validate in normal browsers and
    `openssl s_client`.
  - TLS 1.2/1.3 work; obsolete TLS versions fail.
  - HTTP redirects to the identical HTTPS URI.
  - Unknown Host/SNI values are rejected.
  - UI and API have no mixed-content or CORS errors.
  - Forged client `X-Forwarded-*` headers cannot override the proxy-generated
    values.
  - HSTS and existing CSP/referrer/frame/content-type headers appear on HTTPS
    responses.
  - Admin uploads respect the body limit; excessive requests receive controlled
    `413`/`429` responses.
  - SSE events remain incremental through both Nginx layers for a complete
    simulation.
  - Logs contain no bearer, Supabase, certificate-key, or uploaded-content
    values.
- Public-launch gate:
  - Anonymous OR/player/admin operations are denied.
  - Remote URL ingestion is disabled or hardened.
  - External scanning finds only 80 and 443; port 80 only redirects.
  - SSH remains unreachable outside approved administration networks.
  - Certificate renewal/reload has been successfully rehearsed.
- Roll back by restoring VPN-only security-group rules first, then the previous
  host-Nginx and Compose configurations. Do not roll back to public HTTP.

## Assumptions

- Host Nginx is the selected TLS terminator.
- The eventual service is public, but it remains VPN-only until authorization
  and certificate prerequisites pass.
- University certificate/DNS ownership is currently unknown; browser-trusted
  HTTPS and a renewal process are mandatory blockers, not implementation
  details to improvise.
- JWT design is outside this plan, but successful authorization tests are a
  hard prerequisite for public exposure.
- `TP_kst`, `ATA_kst`, and the unused `frontend/` application remain untouched.

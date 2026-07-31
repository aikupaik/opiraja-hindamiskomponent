# HTTPS and Public-Deployment Hardening Plan

## Summary

Keep TLS termination on host Nginx and deploy in four deliberately separate
phases:

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

1. Introduce HTTPS by VM IP with a self-signed certificate while access remains
   limited to VPN and approved administration CIDRs.
2. Stabilize the proxy, application, logging, and operational controls over
   HTTPS.
3. Implement and verify JWT-based authorization before any Internet-wide
   access. JWT design is tracked separately.
4. Obtain a domain and browser-trusted certificate, migrate from the IP
   endpoint, and only then consider opening ports 80/443 publicly.

Only browser-to-host traffic needs HTTPS. FastAPI and R remain HTTP inside the
single VM's isolated Docker networks. A self-signed certificate encrypts
traffic but does not authenticate the VM to browsers by default; the expected
browser warning is acceptable only for the restricted first phase.

HTTPS alone, whether self-signed or publicly trusted, is not approval for
public launch.

## Phase 0: Baseline and Prepare the Deployment Boundary

- Inspect the VM's routes, Docker networks, listeners, firewall rules, IPv6
  state, disk space, time synchronization, OpenStack ports, and attached
  security groups before changing exposure.
- Select an unused, explicit Docker subnet for the Compose `edge` network after
  comparing it with VM, VPN, OpenStack, and existing Docker routes.
- Add a version-controlled host-Nginx configuration under `deploy/nginx/` and a
  deployment runbook. Keep all certificates, private keys, rendered secrets,
  and VM-specific backup files outside Git and Docker images.
- Change the Compose `web` publication from `${HTTP_PORT:-80}:8080` to
  `127.0.0.1:8080:8080`. Host Nginx must be the only process accepting traffic
  on public ports 80/443.
- Keep API and R port 8000 unpublished. Preserve the internal `compute`
  network, read-only filesystems, non-root users, dropped capabilities,
  `no-new-privileges`, PID limits, tmpfs mounts, and log rotation.
- Establish a rollback path that first restores VPN-only network rules and then
  restores the prior Nginx/Compose configuration. Never roll back to public
  plaintext HTTP.

## Phase 1: Restricted Self-Signed HTTPS by VM IP

The detailed implementation tasks and commands for this phase are in
[`self-signed-https-implementation-plan.md`](self-signed-https-implementation-plan.md).

### Certificate and host Nginx tasks

- Generate a short-lived self-signed server certificate on the VM. Its Subject
  Alternative Name must contain the VM's public IPv4 address as an `IP` entry;
  a Common Name alone is not sufficient for modern clients.
- Store the certificate and key under `/etc/nginx/tls/opiraja/`, owned by root.
  Use mode `0600` for the private key. Never place the key in `.env`, Compose,
  an image layer, or the repository.
- Configure host Nginx to:
  - Listen on ports 80 and 443 for the VM IP.
  - Use TLS 1.2 and 1.3 with the generated certificate and key.
  - Redirect the exact VM-IP host on port 80 to the identical HTTPS URI with
    `308`; reject other `Host` values.
  - Proxy only to `http://127.0.0.1:8080`.
  - Replace client-supplied forwarding headers with trusted values for `Host`,
    `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, and request ID.
  - Preserve SSE with buffering/cache disabled and the existing long read
    timeout.
  - Enforce the existing approximately 11 MiB body limit and bounded
    header/body/upstream timeouts.
  - Block public `/nginx-health`, `/health/*`, `/docs`, `/redoc`,
    `/openapi.json`, `/internal/*`, and R documentation paths.
- Do not enable HSTS in the self-signed/IP phase. It does not remove certificate
  warnings and complicates a deliberately temporary trust arrangement. Retain
  the existing CSP, referrer, frame, and content-type protections.
- Validate every Nginx change with `nginx -t` before a graceful reload. Record
  the certificate expiry and replace it before expiry; there is no ACME renewal
  for this temporary certificate.

### Project and application tasks

- Update `admin/nginx.conf` to preserve the external HTTPS scheme and trusted
  client chain supplied by host Nginx instead of replacing
  `X-Forwarded-Proto` with the inner HTTP scheme.
- Keep SPA requests relative (`/api/...`). They automatically become
  same-origin HTTPS, so no CORS configuration or frontend TLS code is needed.
- Enable Uvicorn proxy-header processing only for the selected Compose `edge`
  subnet using `FORWARDED_ALLOW_IPS`; never use `*` in this deployment.
- Add production `ALLOWED_HOSTS` configuration and Starlette trusted-host
  enforcement. In this phase allow the VM IP plus the narrowly required
  internal health-check names/addresses.
- Keep HTTPS redirects at host Nginx, not FastAPI, to avoid redirect loops over
  the internal HTTP hop.
- Keep `R_SERVICE_URL=http://r-service:8000` and the Supabase URL HTTPS. The R
  service needs no TLS or application-code changes.
- Keep the `sessionStorage` admin bearer flow transitional. Rotate
  `ADMIN_ACCESS_KEY` when leaving plaintext HTTP and never test it over HTTP.

### Restricted-access gate

- Allow TCP 80/443 in both OpenStack and the Ubuntu firewall only from VPN and
  approved administration CIDRs. Keep SSH limited to its existing approved
  administration sources.
- Deny inbound port 8000, Docker API ports, and every unrelated port. Apply the
  security group to the exact Neutron port.
- Accept the browser warning only after independently comparing the certificate
  fingerprint with the value recorded on the VM. Prefer a dedicated test
  browser profile; never distribute the private key.
- Confirm UI/API HTTPS, redirects, host rejection, forwarding-header integrity,
  upload limits, SSE streaming, and absence of mixed-content/CORS errors before
  declaring the phase complete.

## Phase 2: Stabilize and Harden the Restricted HTTPS Deployment

- Monitor Nginx error, `413`, `429`, and 5xx rates; container restarts; disk
  use; API/R readiness; and certificate expiry.
- Start rate-limit testing at 10 API requests/second/IP with burst 20, stricter
  admin-session limits, and at most two concurrent SSE connections/IP. Do not
  request-rate-limit an established SSE stream.
- Disable remote-URL source ingestion by default or close its DNS-rebinding and
  metadata-service exposure before public launch. File upload may remain.
- Keep logs free of authorization headers, cookies, uploaded bodies, and
  secrets. Restrict the deployment `.env` to its owner with mode `0600` and
  rotate credentials that may have crossed the prior HTTP deployment.
- Patch Ubuntu, Docker, and Nginx; keep Docker-group membership minimal; and
  keep `/var/run/docker.sock` inaccessible to application containers.
- Rehearse certificate replacement, Nginx validation/reload, Compose update,
  failure recovery, and network-first rollback while the service remains
  restricted.

## Phase 3: JWT Authorization Prerequisite for Public Access

JWT design and implementation are outside this plan. Before any
Internet-wide firewall rule is introduced:

- Replace the permissive OR/player authorization with the planned authenticated
  policy. Anonymous create/read/play operations must return `401` or `403`.
- Protect all administrative and player workflows with intentional roles and
  resource ownership checks, not only route-level token presence.
- If cookies are used, require `Secure`, `HttpOnly`, and an intentional
  `SameSite` policy. Do not weaken same-origin protections with permissive CORS.
- Complete authorization tests for anonymous, expired, invalid, wrong-role,
  and cross-resource access.
- Treat a passed security review and those tests as a hard public-launch gate.

## Phase 4: Domain, Publicly Trusted Certificate, and Public Cutover

### Domain and certificate tasks

- Obtain the final FQDN and point its A/AAAA records only after confirming the
  intended IPv4/IPv6 exposure and rollback plan.
- Obtain a publicly trusted certificate covering that FQDN. University IT must
  either provide the certificate/full chain/private key and own renewal, or
  delegate narrowly scoped DNS automation for DNS-01 validation. Do not open
  the application publicly merely to satisfy HTTP-01.
- Document renewal, expiry alerting, automated handoff, reload, and revocation.
  Alert at 30, 14, and 7 days before expiry.
- Replace the self-signed certificate paths and IP `server_name` with the FQDN
  and trusted certificate chain. Add the FQDN to `ALLOWED_HOSTS`, remove the VM
  IP after the migration window, and reject direct-IP/unknown-host requests.
- Validate the full chain, hostname, expiry, TLS versions, redirects, and
  graceful reload without rebuilding containers.

### Public cutover tasks

- Repeat the full restricted acceptance suite through the FQDN before changing
  ingress rules.
- Only after the JWT gate and trusted-certificate gate both pass, allow TCP
  80/443 from `0.0.0.0/0` and, if deliberately supported, `::/0`. Keep SSH
  VPN/admin-only and all internal ports closed. Port 80 serves redirects only.
- Add HSTS on HTTPS only, starting with `max-age=86400`. Increase to one year
  after a stable observation period; do not enable `includeSubDomains` or
  preload without a separate domain-wide decision.
- Run an external scan and verify that only 80/443 are exposed, direct IP and
  unknown hosts are rejected, and SSH is unreachable outside approved sources.
- Remove the obsolete self-signed private key and certificate from the VM after
  the migration and rollback window, using a recoverable/approved operational
  process.

## Validation Matrix

### Repository and service checks

- Admin: `npm test`, `npm run lint`, and `npm run build`.
- Backend using `backend/.venv`: tests and `python -m pyright`.
- R: the existing `testthat` suite.
- Both Nginx configurations pass `nginx -t`.
- `docker compose config` succeeds, only `127.0.0.1:8080` is published, and API
  and R port 8000 are unreachable from the VM network.
- API reaches R internally and readiness recovers after service restarts.

### HTTPS and proxy checks

- The certificate identity, SAN, fingerprint, and expiry match the current
  phase: VM IP/self-signed in Phase 1; FQDN/trusted chain in Phase 4.
- TLS 1.2/1.3 work and obsolete TLS versions fail.
- HTTP redirects to the identical HTTPS URI and unknown `Host` values fail.
- Forged client `X-Forwarded-*` and request-ID headers cannot override values
  created by host Nginx.
- UI and API show no mixed-content or CORS failures. Security headers appear on
  HTTPS responses; HSTS appears only after the Phase 4 decision.
- Oversized uploads and excessive requests receive controlled `413`/`429`
  responses. SSE events remain incremental through both Nginx layers for a
  complete simulation.
- Logs contain no bearer token, Supabase secret, certificate key, cookie, or
  uploaded-content values.

### Public-launch gate

- Anonymous and unauthorized OR/player/admin operations are denied.
- Remote URL ingestion is disabled or hardened.
- A normal browser trusts the FQDN certificate without a warning.
- External scanning finds only 80/443; port 80 only redirects.
- SSH remains unreachable outside approved administration networks.
- Certificate renewal/replacement and Nginx reload have been rehearsed.

## Assumptions

- Host Nginx is the selected and only TLS terminator.
- Phase 1 uses the VM's stable public IPv4 address. IPv6 is not exposed until it
  is explicitly configured in the certificate, Nginx, OpenStack, and the host
  firewall.
- Self-signed HTTPS remains VPN/allowlist restricted and is a development step,
  not a public-launch certificate.
- JWT design is outside this plan, but successful authorization tests are a
  hard prerequisite for public exposure.
- `TP_kst`, `ATA_kst`, and the unused `frontend/` application remain untouched.

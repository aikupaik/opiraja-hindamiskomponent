# Self-Signed HTTPS Implementation Plan

## Purpose and Exit Condition

Implement the first HTTPS phase without waiting for a domain:

```text
Approved browser
  → https://<VM_PUBLIC_IPV4>
  → OpenStack security group
  → Ubuntu firewall
  → host Nginx :443 (self-signed TLS)
  → http://127.0.0.1:8080
  → Compose web Nginx
  → http://api:8000
  → http://r-service:8000
```

The phase is complete when approved clients can use the SPA and API over HTTPS
by VM IPv4 address, HTTP redirects to HTTPS, only host Nginx is publicly
reachable, proxy metadata is trustworthy, and SSE/uploads/health behavior still
works. Browser certificate warnings are expected because the certificate is
self-signed.

This phase must remain limited to VPN and approved source CIDRs. JWT is a
prerequisite for later Internet-wide access but is not implemented in this
plan. A domain and publicly trusted certificate are also deferred.

Current Nginx HTTPS syntax is documented in the
[NGINX HTTPS guide](https://nginx.org/en/docs/http/configuring_https_servers.html),
loopback-only port publication uses Compose's `HOST_IP:HOST_PORT:CONTAINER_PORT`
form, and Uvicorn must trust forwarded headers only from known proxies as
described in its
[proxy-header settings](https://www.uvicorn.org/settings/#http).

## Inputs to Record Before Implementation

- `<VM_PUBLIC_IPV4>`: the stable IPv4 address users will enter in the browser.
- `<VPN_CIDR>` and each approved administrator/test-client CIDR.
- `<EDGE_SUBNET>`: an unused private subnet for the Compose `edge` network.
- The exact OpenStack security groups attached to the VM.
- The deployment user, repository path on the VM, current release commit, and
  current rollback commit.
- Whether an existing host Nginx configuration owns ports 80/443.

Do not guess these values in committed files. Record the chosen values in the
deployment runbook and change record without recording secrets.

## Task 1: Audit and Back Up the VM

Run read-only checks before installing or reconfiguring anything:

```bash
ip -brief address
ip route
ss -lntup
docker network ls
docker compose ps
sudo ufw status verbose
sudo nft list ruleset
timedatectl status
df -h
sudo nginx -T
```

- Inspect each existing Docker network and confirm `<EDGE_SUBNET>` conflicts
  with none of the Docker, VM, VPN, or OpenStack routes.
- Confirm the Compose application is healthy over its current endpoint and
  capture `docker compose config` and `docker compose ps` output for comparison.
- Back up the active host-Nginx site configuration using the VM's normal
  configuration-management or privileged backup process. Do not copy TLS keys
  into the repository or an operator laptop.
- Confirm time synchronization. Incorrect time causes confusing certificate
  validity failures even for a self-signed certificate.
- If Nginx is not installed, install it and OpenSSL from the supported Ubuntu
  repositories, enable its systemd service, and keep it patched. Do not install
  Nginx in the Compose application for host TLS termination; the existing
  container Nginx remains the inner web proxy.

### Task 1 audit findings (2026-07-31)

- The guest interface is `ens3` with `192.168.42.72/24`; Floating IP address is `193.40.157.124`. 
  Related security groups: SSH-TALTECH (custom), WEB-TALTECH (custom), DEFAULT, PING, SSH.
  
  VPN CIDRs for SSH and WEB-TALTECH access:
  - 172.20.0.0/16
  - 193.40.0.0/16
- The route table contains the VM subnet plus Docker routes. Existing Docker
  subnets are `172.17.0.0/16` (default bridge), `172.18.0.0/16` (internal
  `compute`), and `172.19.0.0/16` (non-internal `edge`). A replacement edge
  subnet must be selected only after checking it against the unavailable
  OpenStack and VPN routes; no subnet was selected or committed by this audit.
- All three Compose services are running and healthy. The API and R service
  expose port 8000 only to their Docker networks. The web service currently
  publishes `0.0.0.0:80` and `[::]:80` from container port 8080, because
  `compose.yaml` still uses `${HTTP_PORT:-80}:8080`; this must be changed to
  the planned loopback-only `127.0.0.1:8080:8080` publication before host
  Nginx owns the public ports.
- The current local application responds successfully at `/` and
  `/health/ready`. `/nginx-health` returns 403 through the host-published
  path, although the container healthcheck reports healthy; verify the direct
  loopback endpoint after the publication change.
- Host Nginx is installed and its current configuration passes `nginx -t`,
  but the service is enabled and inactive. The stock default site is the only
  configuration shown by `nginx -T`; it has no TLS listener and retains
  `TLSv1`/`TLSv1.1` in the global `ssl_protocols` setting. The active port-80
  listener is the Compose web container, not host Nginx. No host port 443
  listener exists. No privileged backup of the current `/etc/nginx` site was
  created during this read-only audit; create one through the normal operational
  backup process before changing the host configuration.
- UFW is inactive. The visible nftables rules are Docker-managed rules with a
  default-drop IPv4 forwarding chain, but no explicit host ingress policy for
  the approved CIDRs is present in this audit. IPv4 port 80 and SSH are
  listening on all addresses; IPv6 port 80 and SSH are also listening, so the
  IPv6 policy must be addressed before exposure.
- System time is synchronized with NTP active. Disk space is healthy (`137G`
  available, 29% used).
- `docker compose config` succeeds and was inspected without copying its
  rendered output into this plan. Because it renders values from `.env`, its
  output contains deployment secrets and must not be committed or pasted into
  operator documentation.

The audit was read-only. No firewall, Nginx, certificate, Compose, or service
state was changed.

## Task 2: Restrict Network Access Before Enabling TLS

In the OpenStack security group attached to the exact VM port:

- Allow TCP 443 only from `<VPN_CIDR>` and approved test/administrator CIDRs.
- Allow TCP 80 from the same CIDRs only, for redirect testing.
- Keep TCP 22 limited to the existing administration CIDRs.
- Remove/deny ingress for ports 8080 and 8000, Docker daemon/API ports, and
  unrelated services.
- Do not add `0.0.0.0/0` or `::/0` rules in this phase.

Mirror the same policy in UFW/nftables on Ubuntu. Then verify rules from both an
approved and a non-approved source. OpenStack and host-firewall controls are
both required; one is not a substitute for the other.

Keep IPv6 closed unless it is deliberately included in every layer. This plan
uses an IPv4 certificate SAN and therefore does not authorize IPv6 exposure.

## Task 3: Generate and Protect the Self-Signed Certificate on the VM

Create the certificate on the VM so the private key never needs to be copied:

```bash
sudo install -d -o root -g root -m 0700 /etc/nginx/tls/opiraja
sudo openssl req -x509 -nodes -newkey rsa:3072 -sha256 -days 90 \
  -keyout /etc/nginx/tls/opiraja/self-signed.key \
  -out /etc/nginx/tls/opiraja/self-signed.crt \
  -subj "/CN=<VM_PUBLIC_IPV4>" \
  -addext "subjectAltName=IP:<VM_PUBLIC_IPV4>" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"
sudo chown root:root /etc/nginx/tls/opiraja/self-signed.key \
  /etc/nginx/tls/opiraja/self-signed.crt
sudo chmod 0600 /etc/nginx/tls/opiraja/self-signed.key
sudo chmod 0644 /etc/nginx/tls/opiraja/self-signed.crt
```

Replace the placeholder before running the command. The SAN must be an `IP`
entry, not `DNS:<VM_PUBLIC_IPV4>`. Use a short lifetime because this certificate
is transitional; record its expiry and owner rather than pretending it has an
automated public-CA renewal process.

Verify the generated artifact without printing the private key:

```bash
sudo openssl x509 -in /etc/nginx/tls/opiraja/self-signed.crt \
  -noout -subject -issuer -serial -fingerprint -sha256 -dates -ext subjectAltName
sudo openssl pkey -in /etc/nginx/tls/opiraja/self-signed.key -check -noout
```

- Store the SHA-256 fingerprint in the deployment change record and compare it
  out-of-band when accepting the browser warning.
- Never commit the certificate or key. The public certificate may be copied to
  a managed test client only if local trust is deliberately configured; the
  private key must stay on the VM.
- Alert well before the 90-day expiry. Replacement repeats generation,
  `nginx -t`, graceful reload, and fingerprint verification.

## Task 4: Add the Host-Nginx Deployment Configuration to the Project

Add `deploy/nginx/opiraja.conf` as a version-controlled template/runbook input.
It should contain these server roles:

1. An IPv4 port-80 server for `<VM_PUBLIC_IPV4>` that returns a `308` redirect
   to `https://<VM_PUBLIC_IPV4>$request_uri`.
2. A catch-all port-80 server that closes/rejects unknown `Host` values instead
   of redirecting them.
3. An IPv4 port-443 server for `<VM_PUBLIC_IPV4>` using:
   - `ssl_certificate /etc/nginx/tls/opiraja/self-signed.crt`;
   - `ssl_certificate_key /etc/nginx/tls/opiraja/self-signed.key`;
   - `ssl_protocols TLSv1.2 TLSv1.3`;
   - the host's supported secure Nginx defaults unless organizational policy is
     stricter.
4. A TLS catch-all behavior that uses the same temporary certificate only as
   needed to complete the TLS handshake and then rejects unknown HTTP `Host`
   values. Verify expected no-SNI/IP-client behavior before attempting
   `ssl_reject_handshake`.

The HTTPS application server must:

- `proxy_pass http://127.0.0.1:8080` and never proxy to an API/R container port.
- Use HTTP/1.1 and clear hop-by-hop `Connection` for normal HTTP/SSE proxying.
- replace, rather than append to, untrusted client headers at the public edge:

  ```nginx
  proxy_set_header Host              $host;
  proxy_set_header X-Real-IP         $remote_addr;
  proxy_set_header X-Forwarded-For   $remote_addr;
  proxy_set_header X-Forwarded-Proto https;
  proxy_set_header X-Forwarded-Host  $host;
  proxy_set_header X-Request-ID      $request_id;
  ```

- Disable `proxy_buffering` and `proxy_cache` for the existing admin experiment
  SSE route and retain a read timeout longer than a complete simulation.
- Retain the approximately 11 MiB request limit and bounded connection, header,
  body, send, and upstream timeouts.
- Return `404` for `/nginx-health`, `/health/*`, `/docs`, `/redoc`,
  `/openapi.json`, `/internal/*`, `/test/*`, and any R/Plumber documentation
  route before the general proxy location.
- Add `X-Content-Type-Options`, frame protection, referrer policy, and the
  existing CSP on all relevant responses. Do not add HSTS in this temporary
  self-signed/IP phase.
- Log request IDs, response status, latency, and upstream status without logging
  `Authorization`, cookies, query/body content, or forwarded secrets.

Keep reusable proxy settings in an included snippet if that makes drift between
normal API and SSE locations less likely. Render/install the template to the
VM's Nginx site directory using a privileged, reviewable deployment step; do
not make the repository writable by the Nginx user.

## Task 5: Change `compose.yaml`

Update the `web` publication:

```yaml
services:
  web:
    ports:
      - "127.0.0.1:8080:8080"
```

This is the only published Compose port. `expose: "8000"` on API/R is
container-network metadata and does not create a host port; confirm the final
model with `docker compose config`.

Give `edge` the preselected explicit, non-conflicting subnet and configure
Uvicorn to trust only that subnet:

```yaml
services:
  api:
    environment:
      R_SERVICE_URL: http://r-service:8000
      FORWARDED_ALLOW_IPS: <EDGE_SUBNET>

networks:
  edge:
    driver: bridge
    ipam:
      config:
        - subnet: <EDGE_SUBNET>
```

Replace `<EDGE_SUBNET>` with the audited CIDR before committing an actual
deployment configuration. Do not use `FORWARDED_ALLOW_IPS=*`. Only `web` and
`api` join `edge`; only `api` and `r-service` join the internal `compute`
network.

Do not mount `/etc/nginx/tls` into any service. Host Nginx terminates TLS, so
Compose needs no certificate volumes, secrets, environment variables, or 443
publication. Preserve all current container hardening, health checks,
dependency conditions, and log rotation.

## Task 6: Update the Container Nginx Configuration

In `admin/nginx.conf`, keep proxying to `http://api_backend`, but stop
overwriting the public scheme with the inner Nginx `$scheme` (`http`).

- Derive a bounded internal variable from the incoming
  `X-Forwarded-Proto`: pass `https` only when the host proxy supplied `https`,
  otherwise use `http` for direct internal health checks.
- Set API proxy headers consistently in the SSE, normal API, and health
  locations.
- Preserve the trusted chain from host Nginx. Because `web` is reachable only
  through host-loopback publication, the header source is the local host proxy;
  append only the inner proxy hop in a controlled way.
- Pass the host-generated `X-Request-ID`; do not restore a value supplied by the
  original Internet client.
- Keep the current SSE buffering/cache behavior, timeouts, body limit, SPA
  fallback, asset caching, blocked routes, and browser headers.

Add an Nginx configuration test to the image/build verification. TLS directives
and certificate files do not belong in `admin/nginx.conf` because this is the
inner HTTP proxy.

## Task 7: Review the Dockerfiles

### `admin/Dockerfile`

- Keep the current multi-stage build and unprivileged Nginx runtime on port
  8080.
- Do not expose 443, install certificate tooling, copy a certificate, or add a
  TLS volume expectation.
- Rebuild only because `admin/nginx.conf` changed.

### `backend/Dockerfile`

- Keep Uvicorn on HTTP port 8000.
- Make proxy-header handling explicit in the exec-form command with
  `--proxy-headers`; Uvicorn reads the trusted CIDR from
  `FORWARDED_ALLOW_IPS`. Pinning trust to the Compose edge subnet is the
  security control; enabling proxy parsing alone is insufficient.
- Do not add application certificate/key arguments or expose port 443.

### `R/Dockerfile`

- Make no change. R remains HTTP-only on the internal `compute` network and is
  never routed by host Nginx.

## Task 8: Make the Required Application-Code Changes

### FastAPI configuration and middleware

- Add an `ALLOWED_HOSTS` production setting and validate it as a non-empty,
  explicit list. Phase 1 values should contain `<VM_PUBLIC_IPV4>` and only the
  exact internal host names/addresses required by direct health checks (for
  example `127.0.0.1` and `api` if tests prove they are needed).
- Add Starlette `TrustedHostMiddleware` using that setting and add tests for the
  allowed VM IP, rejected arbitrary host, and required health-check hosts. See
  FastAPI's
  [TrustedHostMiddleware guidance](https://fastapi.tiangolo.com/advanced/middleware/#trustedhostmiddleware).
- Do not add `HTTPSRedirectMiddleware`. TLS ends at host Nginx, so the API's
  immediate connection remains HTTP; redirects belong at the public edge.
- Verify that a request through both proxies is observed as scheme `https` and
  has the original approved client IP after Uvicorn processes the trusted
  headers. Add tests for spoofed headers from an untrusted peer.
- Optionally make FastAPI's documentation URLs environment-controlled and
  disabled in the deployment. The host and inner Nginx blocks remain mandatory
  defense in depth.

### Admin SPA

- No HTTPS-specific React change is expected. Keep all API/EventSource URLs
  relative to the current origin; do not hard-code `http://<VM-IP>` or add
  permissive CORS.
- Search the built application for active `http://` resource URLs and correct
  any browser-loaded mixed content. Development-only Vite proxy targets do not
  affect the production bundle.
- Continue using the admin bearer only as a transitional restricted-phase
  mechanism. Rotate `ADMIN_ACCESS_KEY` before the HTTPS test and enter it only
  after the browser is on the expected HTTPS endpoint/fingerprint.

### R service

- No code change. Keep `R_SERVICE_URL=http://r-service:8000`; internal HTTP is
  intentional on the isolated single-host network.

## Task 9: Deploy in a Safe Order

1. Apply the restricted OpenStack and Ubuntu firewall rules.
2. Generate and inspect the certificate; record its fingerprint and expiry.
3. Commit/review the project changes and run all repository checks.
4. On the VM, check out the reviewed commit and protect `.env` with mode `0600`.
5. Run `docker compose config` and confirm the loopback-only publication and
   selected network subnet.
6. Build/recreate the Compose services and wait for healthy status.
7. From the VM, verify `http://127.0.0.1:8080/nginx-health` and confirm that
   ports 8000 are not host-published.
8. Install/enable the rendered host-Nginx site, run `sudo nginx -t`, and only
   then gracefully reload Nginx.
9. Test TLS from an approved client and compare the observed SHA-256 certificate
   fingerprint with the VM record before proceeding through the warning.
10. Recheck listeners, security-group rules, UFW/nftables, and Compose port
    mappings after deployment.

Plan a brief maintenance window: the current Compose `web` service owns host
port 80 and must release it before host Nginx can own that port. Keep the gap
short and do not leave a second public HTTP listener in place after cutover.

## Task 10: Verification and Acceptance

### Repository checks

- Admin: `npm test`, `npm run lint`, `npm run build`.
- Backend, using `backend/.venv`: the test suite and `python -m pyright` with no
  errors.
- R: the existing `testthat` suite if R code or the integrated deployment was
  affected.
- `docker compose config` succeeds.
- Both the container Nginx and installed host Nginx pass `nginx -t`.

### VM and network checks

- `ss -lntup` shows host Nginx on 80/443 and no host listener on port 8000.
- Docker publishes only `127.0.0.1:8080->8080` for `web`.
- Approved clients reach 80/443; unapproved sources and direct ports 8080/8000
  do not.
- SSH remains reachable only from its approved administration network.
- Container health checks remain green and API-to-R traffic still works.

### Certificate and TLS checks

```bash
openssl s_client -connect <VM_PUBLIC_IPV4>:443 -showcerts
```

- The served certificate fingerprint matches the VM record and its SAN contains
  `IP:<VM_PUBLIC_IPV4>`.
- TLS 1.2 and 1.3 succeed; TLS 1.0/1.1 fail.
- A normal browser displays the expected self-signed/untrusted warning, not a
  separate name-mismatch warning. Do not use the absence of a warning as the
  Phase 1 success criterion.
- HTTP requests for the exact VM IP redirect to the identical HTTPS path/query;
  unknown host values are rejected.
- HSTS is absent in this phase.

### Application and proxy checks

- The SPA loads over HTTPS with no mixed-content or CORS errors.
- Normal API calls work and externally generated redirects, if any, use
  `https://<VM_PUBLIC_IPV4>` rather than an internal host or `http`.
- Forged inbound `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Real-IP`, and
  `X-Request-ID` cannot replace values created at host Nginx.
- Unknown `Host` receives rejection from Nginx or TrustedHostMiddleware.
- `/nginx-health`, `/health/*`, `/docs`, `/redoc`, `/openapi.json`,
  `/internal/*`, `/test/*`, and R documentation are unavailable from the
  browser.
- A valid upload below the configured body/source limits succeeds and an
  oversized upload gets a controlled `413`.
- SSE events arrive incrementally through both proxies for a complete
  simulation without a premature timeout.
- Logs contain request IDs and useful status/latency data but no bearer tokens,
  cookies, Supabase secrets, TLS private key data, or uploaded content.

## Rollback

1. Keep or restore the VPN/approved-CIDR security-group rules first. Network
   restriction is the first rollback control.
2. Disable the new host-Nginx site, restore the backed-up known-good site,
   validate with `nginx -t`, and gracefully reload.
3. Check out the prior application commit and recreate the previous Compose
   services only if the application changes caused the failure.
4. Recheck listeners and confirm no accidental public HTTP or port-8000
   exposure.
5. Preserve the failed certificate/config only in the privileged operational
   incident area if needed for diagnosis; never move the private key into Git.

If HTTPS is unhealthy, return to restricted/VPN-only service or no service. Do
not solve a TLS failure by exposing the application over public HTTP.

## Deferred Domain and Public-Access Work

The parent
[`https-public-deployment-hardening-plan.md`](https-public-deployment-hardening-plan.md)
tracks the later work:

- implement and verify JWT authorization;
- obtain the FQDN and DNS ownership;
- issue and automate a publicly trusted certificate and chain;
- replace the IP `server_name`, certificate, and `ALLOWED_HOSTS` values;
- reject direct-IP traffic after migration;
- enable HSTS gradually only after trusted HTTPS is stable; and
- open 80/443 Internet-wide only after both authorization and certificate gates
  pass.

The self-signed certificate must not be reused as the public-launch
certificate.

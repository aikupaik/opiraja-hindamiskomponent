# Public and VPN-Only Access Runbook

## Purpose

This runbook switches the deployed application between VPN/approved-CIDR-only
access and public IPv4 access. It also documents the one-time domain and
certificate cutover.

The supported ingress path is:

```text
Client
  -> OpenStack security group
  -> Ubuntu UFW
  -> host Nginx :80/:443
  -> 127.0.0.1:8080
  -> Compose web Nginx
       -> admin SPA at /
       -> player SPA at /test/
       -> FastAPI at /api/
```

Public API access means using `https://<deployment-host>/api/v1/...`. Never
publish FastAPI port 8000, the R service, port 8080, or the Docker API. The API
and both frontends intentionally share the host-Nginx HTTPS boundary.

This runbook does not authorize a public launch. Follow the security gates in
`docs/plans/active/https-public-deployment-hardening-plan.md`, including JWT,
trusted-certificate, remote-ingestion, and external-scan requirements.

## Current deployment boundary

- Host Nginx listens on IPv4 ports 80 and 443.
- Compose publishes the web container only as `127.0.0.1:8080:8080`.
- FastAPI and R use Docker-only port 8000 exposure.
- Host Nginx routes `/api/` to the web container, which proxies it to FastAPI.
- Host Nginx rejects unknown hosts and hides health, OpenAPI, internal, and R
  documentation endpoints.
- UFW and the OpenStack security group decide which source networks can reach
  host Nginx.
- SSH must remain restricted to its existing VPN/administration sources.

## Required values and files

Record these values before a change:

```text
DEPLOYMENT_HOST=<current IPv4 or final FQDN>
VM_FLOATING_IPV4=<OpenStack floating IPv4>
VPN_CIDRS=<approved source CIDRs>
```

Relevant files:

- `compose.yaml`: loopback publication, Docker networks, forwarded-proxy trust,
  and the deployment-provided `ALLOWED_HOSTS` value.
- VM `.env`: exact `ALLOWED_HOSTS` JSON array and `PLAYER_APP_URL`; this file
  contains secrets and must remain mode `0600` and outside Git.
- `deploy/nginx/opiraja.conf`: version-controlled host-Nginx source.
- `/etc/nginx/sites-available/opiraja.conf`: installed host-Nginx site.
- `/etc/nginx/sites-enabled/opiraja.conf`: symlink to the installed site.
- `/etc/nginx/tls/opiraja/`: VM-only certificate and private key material.

`ALLOWED_HOSTS` must contain exact hosts and no wildcard. For the IP phase:

```dotenv
ALLOWED_HOSTS=["193.40.157.124","127.0.0.1"]
PLAYER_APP_URL=https://193.40.157.124
```

For the final domain phase:

```dotenv
ALLOWED_HOSTS=["assessment.example.edu","127.0.0.1"]
PLAYER_APP_URL=https://assessment.example.edu
```

Replace `assessment.example.edu` with the approved FQDN. Keep the old IP in
`ALLOWED_HOSTS` only during an explicitly approved migration window and only if
host Nginx still accepts that IP host.

## Read-only preflight

Run from the repository root on the VM. Do not print `.env`, rendered Compose
environment, tokens, cookies, certificate keys, or request bodies.

```bash
git status --short
git rev-parse HEAD
docker compose config --quiet
docker compose ps
sudo nginx -t
systemctl is-active nginx
sudo ss -ltnp
sudo ufw status verbose
sudo ufw status numbered
ip -brief address
ip route
```

Confirm all of the following:

- Nginx owns IPv4 80/443.
- Only `127.0.0.1:8080` is published by Docker.
- There is no host listener on 8000.
- API, web, player, and R containers are healthy.
- UFW defaults to deny incoming and deny routed traffic.
- The existing VPN/administration rules are present.
- No public SSH rule exists.
- The exact OpenStack port and attached security groups are known.

## Temporary public-IP exercise

The current IP configuration needs no Compose or Nginx change. Its self-signed
certificate is suitable only for a short controlled exercise. Normal browsers
and service clients will not trust it unless the public certificate is added
to a test trust store.

### Open public HTTPS on the VM

Add a temporary IPv4 rule while retaining all existing CIDR-specific rules:

```bash
sudo ufw allow proto tcp from 0.0.0.0/0 to any port 443 comment 'TEMP public HTTPS'
```

Port 80 is optional for this exercise. Open it only to test the HTTP-to-HTTPS
redirect:

```bash
sudo ufw allow proto tcp from 0.0.0.0/0 to any port 80 comment 'TEMP public HTTP redirect'
```

Verify the effective rules before changing OpenStack:

```bash
sudo ufw status verbose
sudo ufw status numbered
sudo ss -ltnp
```

Do not disable UFW. Do not add public rules for SSH, 8080, 8000, or IPv6.

### Open public HTTPS in OpenStack

On the exact Neutron port attached to the VM, add IPv4 ingress from
`0.0.0.0/0` for TCP 443. Add TCP 80 only if the redirect is being tested.
Leave SSH and all internal ports restricted.

Stage UFW first and OpenStack last so the OpenStack rule is the start of the
public exposure window. Record the public rule identifiers and a removal
deadline without recording unrelated infrastructure details.

### Exercise the endpoint

From a source outside every approved CIDR:

```bash
curl --cacert /path/to/opiraja-public-certificate.crt \
  --output /dev/null --write-out 'ui=%{http_code}\n' \
  https://193.40.157.124/

curl --cacert /path/to/opiraja-public-certificate.crt \
  --output /dev/null --write-out 'api_without_token=%{http_code}\n' \
  https://193.40.157.124/api/v1/tests/00000000-0000-4000-8000-000000000001
```

Expected results are `200` for the admin SPA and `401` for an API request
without a Bearer JWT. Test `/test/<real-test-id>` only with a deliberately
created test. A valid external OR integration must send the JWT profile from
`docs/contracts/public-assessment-api.md`.

If port 80 was opened, verify an exact-host request receives `308` and preserves
the path and query. Confirm `/health/ready`, `/docs`, `/openapi.json`, and
internal/R paths remain `404` at the public edge. Confirm ports 8080 and 8000
remain unreachable externally.

Do not use production credentials merely to prove reachability. Do not put JWTs
on command lines, in URLs, or in the evidence log.

## Return to VPN/approved-CIDR-only access

Remove the public OpenStack rules first. This ends public exposure at the
outermost boundary. Then remove only the temporary UFW rules:

```bash
sudo ufw --force delete allow proto tcp from 0.0.0.0/0 to any port 443
sudo ufw --force delete allow proto tcp from 0.0.0.0/0 to any port 80
```

Skip the port-80 deletion if that rule was never added. If an exact-rule delete
does not match, inspect `sudo ufw status numbered` and delete only the verified
temporary rule by number. Rule numbers change after each deletion, so delete
the higher number first and re-list between deletions.

Verify the rollback:

```bash
sudo ufw status verbose
sudo ufw status numbered
sudo ss -ltnp
docker compose ps
```

From an approved VPN client, HTTPS must still work. From an independent
non-approved source, 80/443/8080/8000 must produce no application response.
The original VPN and administration rules must remain present.

Switching between these two network exposure modes does not require an Nginx
reload, a Compose restart, or a repository change.

## One-time Phase 4 domain cutover

Perform this while ingress is still VPN/approved-CIDR-only.

### Prepare DNS and trusted TLS

1. Point the final A record at the floating IPv4 only after confirming the
   rollback plan.
2. Do not publish an AAAA record. The current VM has no intended public IPv6
   path and host Nginx does not listen on IPv6 80/443.
3. Obtain the certificate and full chain through the approved university IT or
   DNS-01 process. Keep the private key on the VM and outside Git.
4. Document certificate renewal, handoff, expiry alerts, and revocation.

### Update the version-controlled host-Nginx site

In `deploy/nginx/opiraja.conf`:

1. Replace the exact IP `server_name` values with the final FQDN.
2. Change the port-80 redirect target to `https://<final-fqdn>$request_uri`.
3. Replace the self-signed certificate and key paths with the approved full
   chain and private-key paths.
4. Keep the default unknown-host HTTP and TLS rejection servers.
5. Keep all `/api/`, SSE, rate-limit, forwarding-header, hidden-path, upload,
   timeout, and security-header controls.
6. Add HSTS on HTTPS only with the initially approved `max-age=86400`; do not
   add `includeSubDomains` or `preload` without a separate decision.

Review the diff before installation. Back up the active VM site in the
privileged VM backup area, install the reviewed file, and validate before a
graceful reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
systemctl is-active nginx
```

### Update the API deployment identity

Update only the two non-secret identity values in the VM `.env` without
printing the file:

```dotenv
ALLOWED_HOSTS=["<final-fqdn>","127.0.0.1"]
PLAYER_APP_URL=https://<final-fqdn>
```

`compose.yaml` passes `ALLOWED_HOSTS` from this deployment environment instead
of embedding an IP. Validate and recreate the API container so both values
take effect:

```bash
docker compose config --quiet
docker compose up -d --no-deps --force-recreate api
docker compose ps
```

Do not use `docker compose config` without `--quiet` in operational evidence,
because rendered output can contain secrets. A rebuild is not required solely
for environment changes.

### Restricted acceptance before public cutover

Through the FQDN and from an approved client, verify:

- the full certificate chain, hostname, and expiry;
- TLS 1.2/1.3 and rejection of obsolete TLS versions;
- HTTP `308` redirect with path/query preservation;
- admin and player SPA assets with no mixed-content or CORS errors;
- authenticated OR and player API flows;
- anonymous, expired, invalid, wrong-role, and cross-resource denials;
- rate limiting, upload limits, and incremental SSE;
- unknown-host and direct-IP rejection;
- hidden health, documentation, internal, and R routes;
- one public-edge request ID and trusted forwarding metadata;
- no credentials, bodies, or sensitive queries in logs;
- no host listener on 8000 and only loopback publication on 8080.

Only after this suite and every Phase 4 gate pass should the public UFW and
OpenStack IPv4 rules be added. For the permanent public service, port 80 serves
redirects only and 443 serves the application. SSH remains VPN/admin-only.

## Domain-cutover rollback

Rollback is network-first:

1. Remove public OpenStack 80/443 rules.
2. Remove public UFW 80/443 rules while retaining approved-CIDR rules.
3. Confirm independent public denial and VPN access.
4. Restore the reviewed prior Nginx site or certificate only if required.
5. Run `sudo nginx -t` before any reload.
6. Restore the prior `.env` identity values and recreate only the API container
   if the application identity must be rolled back.

Never roll back to public plaintext HTTP, a wildcard `ALLOWED_HOSTS`,
`FORWARDED_ALLOW_IPS=*`, a public container port, or a disabled firewall.

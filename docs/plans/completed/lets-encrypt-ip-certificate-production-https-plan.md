# Production Let's Encrypt HTTPS for `193.40.157.124`

Status: completed on 2026-09-22. Deployment and acceptance evidence is in
`docs/plans/agent-logs/lets-encrypt-ip-certificate-production-https-change-log.md`.

## Summary

Replace the self-signed certificate with a Let's Encrypt short-lived IP
certificate while retaining `https://193.40.157.124/`.

Keep IPv4 TCP 80 and 443 permanently public. Port 80 serves only ACME HTTP-01
challenges and HTTPS redirects; port 443 serves the application. SSH, Grafana,
internal container ports, and IPv6 remain restricted.

Use Certbot 5.4 or newer with automated renewal, safe Nginx reloads, six-hour
local certificate checks, and a daily operator inspection runbook. No ACME
email or external alerting will be configured.

No application API, schema, or frontend behavior changes are required.

## Implementation Changes

### Nginx and repository

- Back up the enabled Nginx site and record its checksum.
- Update `deploy/nginx/opiraja.conf` so the exact-IP port-80 server:
  - serves `/.well-known/acme-challenge/` from `/var/lib/letsencrypt`;
  - uses `try_files` and never proxies challenge requests;
  - redirects all other paths to the same path and query on HTTPS.
- Keep unknown HTTP hosts returning `444`.
- After issuance, configure both TLS server blocks to use:
  - `/etc/letsencrypt/live/193.40.157.124/fullchain.pem`;
  - `/etc/letsencrypt/live/193.40.157.124/privkey.pem`.
- Preserve TLS 1.2/1.3, authentication, rate limits, forwarding-header
  replacement, hidden routes, upload limits, Grafana restrictions, and
  security headers.
- Do not enable HSTS for the IP endpoint.
- Add configuration tests for the ACME location, redirect behavior, and
  production certificate paths.
- Add deployment assets under `deploy/letsencrypt/`:
  - an Nginx validation and reload hook;
  - a parameterized certificate-health script;
  - systemd certificate-check service and timer templates.

### Permanent ingress

- Verify OpenStack IPv4 `0.0.0.0/0` ingress for TCP 443 and add TCP 80 if
  absent.
- Do not expose IPv6, SSH, 8080, 8000, 3000, Loki, or the Docker API.
- Add persistent interface-bound UFW rules on `ens3` before removing the
  temporary rules:
  - TCP 80: `public HTTP ACME and redirect`;
  - TCP 443: `public HTTPS`.
- Delete only the verified rules carrying the existing temporary comments.
- Retain CIDR-specific rules and UFW's default-deny incoming and routed
  policies.

### ACME enrollment and cutover

- Install `snapd` and the official classic Certbot snap; do not use Ubuntu's
  Certbot 2.9 package.
- Require Certbot 5.4 or newer.
- Create `/var/lib/letsencrypt/.well-known/acme-challenge/` as `root:root`,
  mode `0755`.
- Deploy the ACME-routing change while retaining the self-signed certificate.
- Validate Nginx and externally retrieve an exact-content probe through the
  floating IP.
- Request an isolated staging certificate:

  ```bash
  sudo certbot certonly --staging \
    --non-interactive --agree-tos --register-unsafely-without-email \
    --preferred-profile shortlived \
    --webroot --webroot-path /var/lib/letsencrypt \
    --ip-address 193.40.157.124 \
    --cert-name 193.40.157.124-staging
  ```

- Inspect the staging certificate without installing it.
- Repeat against production, omitting `--staging` and using certificate name
  `193.40.157.124`.
- Verify its IP SAN, trusted chain, issuer, serial, fingerprint, and
  approximately 160-hour validity.
- Switch Nginx to the production lineage, run `nginx -t`, and reload
  gracefully.
- Delete the staging lineage only after production acceptance.
- Retain the self-signed certificate and Nginx backup through at least one
  successful renewal.

### Renewal and local monitoring

- Install a root-owned Certbot deploy hook that reloads Nginx only after
  `nginx -t` succeeds.
- Verify and enable Certbot's renewal timer.
- Run `certbot renew --dry-run --run-deploy-hooks`.
- Enable a six-hour `opiraja-certificate-check.timer`.
- Fail the check and log to journald if:
  - validity remaining is below 72 hours;
  - the IP SAN is wrong;
  - the served certificate differs from the active lineage;
  - system trust or IP verification fails;
  - Nginx is inactive or invalid;
  - the Certbot renewal timer is absent or inactive.
- Document a daily operator inspection covering:
  - `systemctl --failed`;
  - certificate-check and Certbot timer status;
  - recent renewal journals;
  - certificate SAN, issuer, fingerprint, and expiry;
  - normally verified HTTPS;
  - Nginx and Compose health.
- Treat less than 72 hours remaining as an incident and less than 48 hours as
  urgent.
- State clearly that local checks produce no external notification; daily
  inspection is an operating requirement.

### Documentation reconciliation

After implementation and live acceptance, search the repository for references
to self-signed HTTPS, domain-required certificates, temporary public access,
old certificate paths and fingerprints, `curl -k`, and obsolete expiry
schedules.

- Update active plans, the public-access runbook, performance preflight and
  runbook, README guidance, and operational checklists to describe the trusted
  IP certificate and permanent IPv4 ingress.
- Replace 30/14/7-day certificate alert guidance with the short-lived renewal
  and 72/48-hour response policy where it describes the current deployment.
- Update examples to use normal certificate verification rather than
  self-signed exceptions.
- Mark historical completed plans and agent logs as superseded where necessary,
  but do not rewrite their historical execution evidence.
- Add a new change log containing the Certbot version, lineage, certificate
  metadata, UFW and OpenStack rule evidence, timer status, renewal test,
  deployment checksums, and rollback location.
- Finish with a repository-wide search confirming that no current document
  conflicts with the implemented state.

### Domain-ready follow-up

- Keep the IP and future domain certificates in separate Certbot lineages.
- Keep the HTTP-01 webroot permanently usable.
- Parameterize certificate-health tooling by expected host and certificate
  path.
- Document a zero-downtime domain transition:
  1. issue the domain certificate while the IP endpoint remains active;
  2. add parallel FQDN Nginx blocks;
  3. temporarily allow both identities in `ALLOWED_HOSTS`;
  4. update `PLAYER_APP_URL` and Grafana's external URL;
  5. validate authenticated flows through the domain;
  6. make the domain canonical and redirect the IP while retaining its valid
     certificate;
  7. retire the IP lineage after the migration window;
  8. enable HSTS only after the domain is stable.

## Test and Acceptance Plan

- Run the focused Nginx policy tests.
- Run `backend/.venv/bin/python -m pyright` with zero errors after modifying
  Python tests.
- Validate shell scripts with `sh -n` and systemd units with
  `systemd-analyze verify`.
- Require `nginx -t` before every reload.
- From an independent external client, verify:
  - exact-content ACME probe;
  - path- and query-preserving HTTP `308`;
  - trusted HTTPS without `--insecure` or browser warnings;
  - OpenSSL verification code `0` for `193.40.157.124`;
  - TLS 1.2/1.3 success and obsolete-protocol rejection;
  - clean admin and player browser loading.
- Re-run public security acceptance:
  - anonymous protected API access returns `401` or `403`;
  - invalid admin login returns `401`;
  - diagnostic and internal routes remain hidden;
  - Grafana remains CIDR-restricted;
  - unknown hosts are rejected;
  - forged forwarding headers are replaced;
  - only IPv4 80/443 are public.
- Confirm the live Nginx configuration matches the reviewed repository version.
- Require a successful renewal dry run and one later real renewal before
  removing rollback artifacts.
- Confirm no temporary UFW rules or conflicting current documentation remain.

## Assumptions and Rollback

- `193.40.157.124` remains assigned to this VM.
- Public IPv4 TCP 80 remains available for recurring HTTP-01 validation.
- Existing JWT authorization and public-edge protections remain unchanged.
- ACME registration uses no email and no external alerting.
- If issuance fails, retain the valid self-signed deployment while correcting
  reachability.
- If Nginx validation fails, do not reload.
- If renewal cannot be restored before expiry, remove public OpenStack and UFW
  access first and return to approved-CIDR-only self-signed HTTPS.
- Private keys, ACME account material, certificates, and rendered secrets
  remain outside Git and operator-facing logs.

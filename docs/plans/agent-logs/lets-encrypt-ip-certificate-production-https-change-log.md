# Let's Encrypt IP Certificate Production HTTPS Change Log

Deployment date: 2026-09-22

This log records sanitized implementation and acceptance evidence for the
trusted certificate at `https://193.40.157.124/`. It contains no private key,
ACME account material, credentials, rendered environment, cookies, tokens, or
request bodies.

## Repository implementation

- Added an exact-IP HTTP-01 location rooted at `/var/lib/letsencrypt`, with
  `try_files $uri =404` so missing challenges never reach the application.
- Kept the exact-IP path/query-preserving `308`; unknown HTTP hosts still
  receive `444`.
- Both TLS blocks now use the production lineage under
  `/etc/letsencrypt/live/193.40.157.124/`.
- TLS 1.2/1.3, rate and connection limits, forwarding-header replacement,
  hidden routes, upload/time limits, Grafana CIDR restrictions, and security
  headers were retained. HSTS remains absent.
- Added a validation-first Nginx deploy hook, parameterized certificate-health
  script, and six-hour systemd service/timer.
- Focused Nginx policy tests passed (`7 passed`), shell syntax checks passed,
  systemd units verified after installation, and Pyright reported zero errors.

## Ingress

The operator confirmed that the exact OpenStack VM port permits IPv4
`0.0.0.0/0` ingress for TCP 80 and 443 and has no other public ingress. No IPv6
public rule was added.

On the VM, permanent UFW rules were added before the two temporary rules were
removed:

- `80/tcp on ens3` from Anywhere, comment `public HTTP ACME and redirect`;
- `443/tcp on ens3` from Anywhere, comment `public HTTPS`.

The prior CIDR-specific SSH/HTTP/HTTPS rules remain. UFW is active with deny
incoming, allow outgoing, and deny routed defaults. Final listener inspection
showed Nginx only on IPv4 80/443, web on `127.0.0.1:8080`, Grafana on
`127.0.0.1:3000`, no host port 8000, and no IPv6 HTTP/HTTPS listener.

## Backup and deployment checksums

- Pre-change live site checksum:
  `637fb52be2a0f36702b026284e4231005309ce88ffd592cd3e364498900c9776`
- ACME-bootstrap site checksum (self-signed TLS retained):
  `3ccbf66e0c6d2852a7ba1c71d5a1721857debb6aba3c70f01ac6d67c82c4feeb`
- Final live and repository site checksum:
  `90fbfb1faca4c0a0b58b477f0a7ff2784fc99524af0f79e015498321942cafd5`
- Root-only rollback directory:
  `/var/backups/nginx/opiraja-letsencrypt-20260922/`
- Rollback files: `opiraja.conf.before` and `opiraja.conf.acme-bootstrap`.

The earlier self-signed certificate and key remain under
`/etc/nginx/tls/opiraja/` until one successful real renewal, as required by the
rollback policy.

## ACME enrollment and certificate

- Official classic Certbot snap version: `5.8.0`.
- The exact-content HTTP-01 probe was retrieved through an external network
  path before enrollment; the redirect probe preserved its path and query.
- A separate staging lineage was issued and inspected first. It was deleted
  only after production and browser acceptance.
- Active lineage: `193.40.157.124`.
- Key type: ECDSA.
- IP SAN: `193.40.157.124` (critical SAN extension).
- Issuer: `C=US, O=Let's Encrypt, CN=YE1`.
- Serial: `0652E9F6A60F33C112908F367CAE07BA6F6F`.
- SHA-256 fingerprint:
  `C0:01:41:36:56:3D:71:D5:97:59:70:8E:13:C1:3D:7F:4D:CC:FA:B6:FF:FE:BC:7E:A1:60:A1:20:88:C9:E2:63`.
- Validity: `2026-09-22 14:35:12 UTC` through
  `2026-09-29 06:35:11 UTC` (160 hours).
- System-chain and IP verification: `OK`.

Nginx passed `nginx -t` before the production lineage was installed and was
reloaded gracefully. The live and repository checksums match.

## Renewal and local monitoring

- `snap.certbot.renew.timer`: enabled and active.
- `opiraja-certificate-check.timer`: enabled and active, scheduled every six
  hours with a bounded randomized delay.
- Root-owned hook and health scripts are mode `0755`; systemd units are mode
  `0644`; the ACME challenge directory is `root:root` mode `0755`.
- The live certificate check passed the validity, IP SAN, system trust,
  served/lineage fingerprint, Nginx, and renewal-timer checks.
- `systemctl --failed` reported no failed units after deployment.
- A full `certbot renew --dry-run --run-deploy-hooks` succeeded for both the
  isolated staging and production renewal configurations, including the
  validation-first deploy hook.
- The hook was then adjusted only to suppress Nginx's success text on stderr;
  its validation/reload behavior was exercised directly and passed.
- A later production-only dry-run attempt reached the staging CA but received
  a transient `rateLimited: Service busy; retry later` response. It did not
  change the live certificate or service state and does not invalidate the
  earlier successful full simulation. Avoid repeated immediate retries; the
  daily inspection must confirm the next timer/dry-run result.

There is no email or external alerting. Daily operator inspection is mandatory.
Less than 72 hours remaining is an incident; less than 48 hours is urgent.

## Acceptance

- External normal certificate verification returned code `0`.
- Root and player shells returned `200` through trusted HTTPS.
- Anonymous protected API and invalid admin login returned `401`.
- Health, documentation, internal, R, and Plumber paths returned `404`.
- A missing ACME token returned a local `404` rather than reaching the app.
- Exact-IP HTTP returned `308` with path/query preservation.
- Unknown HTTP and HTTPS hosts were dropped without an application response.
- A forged request ID was replaced by a host-generated value; the reviewed
  configuration replaces all forwarding metadata at the same boundary.
- TLS 1.2 and TLS 1.3 succeeded with trusted IP verification; TLS 1.1 failed.
- The operator confirmed clean admin and player browser loading with no
  certificate warning, mixed-content, CORS, CSP, or asset errors.
- Nginx and all seven Compose services were healthy after cutover.
- Live configuration, firewall, listeners, systemd timers, lineage, and
  certificate metadata were rechecked at `2026-09-22T15:54:59Z`.
- A repository-wide current-document scan found no conflicting old certificate
  path/fingerprint, temporary-ingress, self-signed exception, or obsolete
  30/14/7-day alert guidance. Historical evidence is marked as superseded.

## Follow-up

- Retain the rollback artifacts through the first successful real renewal.
- Perform the daily inspection in `docs/public-vpn-access-runbook.md`; local
  health failures do not notify anyone externally.
- Keep any future domain certificate in a separate lineage and follow the
  documented parallel, zero-downtime transition.

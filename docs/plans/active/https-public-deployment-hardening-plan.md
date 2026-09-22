# HTTPS and Public-Deployment Hardening Status

## Current state

The earlier restricted self-signed phases are complete and retained in the
completed plans and historical agent logs. The production endpoint is now
`https://193.40.157.124/` with a browser-trusted, short-lived Let's Encrypt IP
certificate and enforced JWT authorization.

```text
Browser
  -> OpenStack IPv4 TCP 80/443
  -> interface-bound UFW rules on ens3
  -> host Nginx :80/:443
  -> 127.0.0.1:8080
  -> Compose web Nginx
  -> FastAPI and R on internal Docker networks
```

Operational details and rollback procedures are maintained in
[`docs/public-vpn-access-runbook.md`](../../public-vpn-access-runbook.md). The
certificate implementation and acceptance evidence is recorded in
[`lets-encrypt-ip-certificate-production-https-change-log.md`](../agent-logs/lets-encrypt-ip-certificate-production-https-change-log.md).

## Required production invariants

- OpenStack and UFW expose only IPv4 TCP 80/443 to `0.0.0.0/0`; SSH, Grafana,
  8080, 8000, 3000, Loki, the Docker API, and IPv6 remain restricted.
- Port 80 serves `/.well-known/acme-challenge/` from the local Certbot webroot
  and redirects every other exact-IP request to the same path/query on HTTPS.
- Port 443 uses `/etc/letsencrypt/live/193.40.157.124/fullchain.pem` and
  `privkey.pem`, supports TLS 1.2/1.3, and has no HSTS for the IP endpoint.
- Host Nginx replaces forwarding metadata, preserves rate/upload/timeout/SSE
  controls, hides internal routes, rejects unknown hosts, and restricts
  Grafana to the approved CIDRs.
- Certbot's timer remains enabled. Its deploy hook reloads Nginx only after a
  successful `nginx -t`.
- `opiraja-certificate-check.timer` runs every six hours. Less than 72 hours
  remaining is an incident; less than 48 hours is urgent.
- The local checks send no external notification, so the documented daily
  operator inspection remains mandatory.
- The prior self-signed certificate and Nginx backup remain available only
  through the first successful real renewal.

## Remaining public-launch gates

- Continue authorization regression testing for anonymous, expired, invalid,
  wrong-role, and cross-resource access.
- Keep remote URL ingestion's SSRF controls under review.
- Continue patching, log-sanitization, backup, capacity, recovery, and external
  exposure reviews. A trusted certificate alone is not authorization to weaken
  any application or network control.

## Future domain transition

A domain migration is optional and must preserve the trusted IP endpoint until
the new identity is accepted:

1. Issue the domain certificate into a separate Certbot lineage.
2. Add parallel FQDN Nginx blocks.
3. Temporarily allow both exact identities in `ALLOWED_HOSTS`.
4. Update `PLAYER_APP_URL` and Grafana's external URL.
5. Validate authenticated admin, OR, and player flows through the domain.
6. Make the domain canonical and redirect the IP while its valid certificate
   remains active.
7. Retire the IP lineage only after the migration window.
8. Enable HSTS only after the domain is stable and its policy is separately
   approved; never add `includeSubDomains` or `preload` implicitly.

Do not publish an AAAA record until IPv6 is intentionally configured through
the certificate, Nginx, OpenStack, UFW, monitoring, and acceptance layers.

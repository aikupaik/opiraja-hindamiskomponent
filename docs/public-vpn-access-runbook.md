# Public IPv4 and Trusted-Certificate Operations Runbook

## Purpose

The production endpoint is `https://193.40.157.124/`, using a browser-trusted,
short-lived Let's Encrypt IP certificate. IPv4 TCP 80 and 443 are permanently
public. Port 80 serves only HTTP-01 challenges and HTTPS redirects; port 443
serves the application. IPv6, SSH, Grafana, container ports, Loki, and the
Docker API remain restricted.

The supported path is:

```text
Client
  -> OpenStack security group
  -> UFW on ens3
  -> host Nginx :80/:443
  -> 127.0.0.1:8080
  -> Compose web Nginx
       -> admin SPA at /
       -> player SPA at /test/
       -> FastAPI at /api/
```

## Current deployment boundary

- OpenStack permits IPv4 `0.0.0.0/0` ingress only for TCP 80 and 443.
- UFW has interface-bound `ens3` rules named `public HTTP ACME and redirect`
  and `public HTTPS`, while retaining the approved CIDR-specific rules.
- UFW defaults remain deny incoming and deny routed traffic.
- Host Nginx is the only public HTTP/TLS listener and does not listen on IPv6.
- Compose publishes the web service only on `127.0.0.1:8080`; Grafana is
  loopback-only on `127.0.0.1:3000`; API, R, and Loki have no host publication.
- SSH remains restricted to its existing administration networks.
- Unknown HTTP hosts are dropped, and unknown TLS hosts are rejected after the
  handshake. HSTS is intentionally disabled for the IP endpoint.

The deployment identity remains:

```dotenv
ALLOWED_HOSTS=["193.40.157.124","127.0.0.1"]
PLAYER_APP_URL=https://193.40.157.124
```

Do not print the VM `.env`, rendered Compose environment, credentials, private
keys, bearer tokens, cookies, or request bodies in operational evidence.

## Files and services

- Repository Nginx source: `deploy/nginx/opiraja.conf`
- Live Nginx site: `/etc/nginx/sites-available/opiraja.conf`
- Production lineage: `/etc/letsencrypt/live/193.40.157.124/`
- Renewal configuration: `/etc/letsencrypt/renewal/193.40.157.124.conf`
- HTTP-01 webroot: `/var/lib/letsencrypt/.well-known/acme-challenge/`
- Deploy hook: `/etc/letsencrypt/renewal-hooks/deploy/opiraja-nginx`
- Certificate check: `/usr/local/sbin/opiraja-certificate-health`
- Renewal timer: `snap.certbot.renew.timer`
- Local monitoring timer: `opiraja-certificate-check.timer`

Keep the IP and any future domain certificate in separate Certbot lineages.
Never commit `/etc/letsencrypt`, the self-signed rollback key, or VM backups.

## Safe preflight

Run from the deployed repository root:

```bash
git status --short
git rev-parse HEAD
docker compose --profile observability config --quiet
docker compose --profile observability ps
sudo nginx -t
systemctl is-active nginx
sudo ss -ltnp
sudo ufw status verbose
sudo ufw status numbered
systemctl is-active snap.certbot.renew.timer
systemctl is-active opiraja-certificate-check.timer
systemctl list-timers snap.certbot.renew.timer \
  opiraja-certificate-check.timer --all --no-pager
```

Confirm Nginx owns IPv4 80/443, Docker publishes only the intended loopback
ports, no host port 8000 exists, all Compose services are healthy, no public
SSH rule exists, and no temporary UFW rule remains.

## Certificate and renewal inspection

Inspect only public certificate metadata:

```bash
sudo /snap/bin/certbot certificates
sudo openssl x509 \
  -in /etc/letsencrypt/live/193.40.157.124/cert.pem \
  -noout -issuer -serial -fingerprint -sha256 -dates -ext subjectAltName
sudo openssl verify -CApath /etc/ssl/certs \
  -untrusted /etc/letsencrypt/live/193.40.157.124/chain.pem \
  -verify_ip 193.40.157.124 \
  /etc/letsencrypt/live/193.40.157.124/cert.pem
```

The SAN must contain `IP Address:193.40.157.124`, chain verification must be
`OK`, and the issuer must be Let's Encrypt. Verify the served endpoint normally:

```bash
curl --fail --silent --show-error --output /dev/null \
  --write-out 'status=%{http_code} verify=%{ssl_verify_result}\n' \
  https://193.40.157.124/
```

Expected output is `status=200 verify=0`. Do not use `--insecure`, `-k`, a
custom CA file, or a k6 certificate-verification exception for this endpoint.

To exercise renewal after a relevant Certbot, Nginx, hook, or firewall change:

```bash
sudo /snap/bin/certbot renew --dry-run --run-deploy-hooks
sudo nginx -t
systemctl is-active nginx
```

The deploy hook captures `nginx -t` output, aborts on invalid configuration,
and reloads Nginx only after validation succeeds.

## Daily operator inspection

Local checks do not send email, pages, or any other external notification.
The following inspection is therefore required every day:

```bash
systemctl --failed
systemctl status opiraja-certificate-check.timer \
  snap.certbot.renew.timer --no-pager
systemctl list-timers opiraja-certificate-check.timer \
  snap.certbot.renew.timer --all --no-pager
sudo journalctl -u opiraja-certificate-check.service \
  -u snap.certbot.renew.service --since '2 days ago' --no-pager
sudo openssl x509 \
  -in /etc/letsencrypt/live/193.40.157.124/cert.pem \
  -noout -issuer -fingerprint -sha256 -dates -ext subjectAltName
curl --fail --silent --show-error --output /dev/null \
  --write-out 'status=%{http_code} verify=%{ssl_verify_result}\n' \
  https://193.40.157.124/
sudo nginx -t
systemctl is-active nginx
docker compose --profile observability ps
```

The six-hour local check fails and logs to journald when less than 72 hours
remain, the IP SAN is wrong, system trust or IP verification fails, the served
leaf differs from the lineage, Nginx is inactive/invalid, or the Certbot timer
is absent/inactive.

- Less than 72 hours remaining is an incident: investigate renewal and HTTP-01
  reachability immediately.
- Less than 48 hours remaining is urgent: restore renewal promptly or begin
  the network-first rollback below.

Retain the self-signed certificate and the pre-cutover Nginx backup until at
least one real automatic renewal has completed successfully.

## HTTP-01 and public-edge checks

The exact-IP port-80 server must keep the webroot usable permanently. A safe
probe is:

```bash
probe_name="operator-probe-$(date -u +%Y%m%dT%H%M%SZ)"
printf '%s\n' "$probe_name" | sudo tee \
  "/var/lib/letsencrypt/.well-known/acme-challenge/$probe_name" >/dev/null
curl --fail --silent --show-error \
  "http://193.40.157.124/.well-known/acme-challenge/$probe_name"
sudo rm -f "/var/lib/letsencrypt/.well-known/acme-challenge/$probe_name"
```

The response must exactly equal the probe name. A missing token must return a
local `404` and must never be proxied to the application. Other HTTP paths must
return `308` to the same path and query on HTTPS.

Regular acceptance also confirms anonymous protected API access returns
`401`/`403`, invalid admin login returns `401`, internal/diagnostic paths stay
`404`, Grafana remains limited to `172.20.0.0/16` and `193.40.0.0/16`, forged
forwarding headers are replaced, TLS 1.2/1.3 work, and obsolete TLS fails.

## Network-first emergency rollback

If trusted renewal cannot be restored safely before expiry:

1. Remove public IPv4 TCP 80/443 from the exact OpenStack port first.
2. Remove only the two interface-bound UFW rules carrying the comments
   `public HTTP ACME and redirect` and `public HTTPS`; retain approved CIDRs.
3. Confirm independent public denial and approved-CIDR access.
4. Restore the reviewed pre-cutover Nginx site from the root-only backup area.
5. Run `sudo nginx -t` before a graceful reload.
6. Recheck Nginx, Compose health, listeners, UFW defaults, and certificate
   identity.

Never respond to a certificate incident by exposing plaintext application
traffic, disabling UFW, publishing container ports, allowing public SSH, or
using a wildcard `ALLOWED_HOSTS`/`FORWARDED_ALLOW_IPS` value.

## Zero-downtime future domain transition

The current trusted IP endpoint remains available throughout a future domain
migration:

1. Point the approved domain's A record to the floating IPv4; do not add AAAA
   until IPv6 is deliberately supported end to end.
2. Issue the domain certificate into a separate Certbot lineage while the IP
   endpoint and IP lineage remain active.
3. Add parallel FQDN Nginx server blocks; do not replace the IP blocks yet.
4. Temporarily add both identities to `ALLOWED_HOSTS`, update `PLAYER_APP_URL`
   and Grafana's external URL, and recreate only services whose environment
   changed.
5. Validate the full authenticated admin, OR, and player flows through the
   domain, including browser, TLS, redirect, hidden-route, forwarding-header,
   upload, rate-limit, and SSE checks.
6. Make the domain canonical and redirect the IP while continuing to present
   the valid IP certificate during its TLS handshake.
7. Retire the IP lineage only after the approved migration window.
8. Enable HSTS only after the domain is stable; begin with the separately
   approved policy and do not add `includeSubDomains` or `preload` implicitly.

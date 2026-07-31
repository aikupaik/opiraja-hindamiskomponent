# Task 4 Host-Nginx Change Log

Date started: 2026-07-31

## Project change

Added the version-controlled host-Nginx site template:

- `deploy/nginx/opiraja.conf`

It targets `193.40.157.124`, terminates TLS with the VM-local certificate,
redirects exact-IP HTTP requests with `308`, rejects unknown hosts, proxies
only to `127.0.0.1:8080`, replaces untrusted forwarding headers, preserves the
long SSE timeout without buffering, blocks internal/documentation routes, and
logs request IDs/status/latency without query strings, authorization headers,
cookies, or bodies.

## Follow-up verification

The initial version was a complete standalone `nginx.conf`. That shape would
not be valid when copied into `/etc/nginx/sites-available`, which is the
planned deployment location. It was corrected to an `http`-context site
fragment containing the logging directives and server blocks only. The stock
default site must be disabled when this site is enabled so it does not retain
the old port-80 listener.

The selected Docker edge subnet is `172.30.0.0/24`; VM inspection confirmed
that `172.17.0.0/16`, `172.18.0.0/16`, and `172.19.0.0/16` are already in use,
while the VM routes contain no `172.30.0.0/24` route and the approved VPN
range is `172.20.0.0/16`.

## Validation and deployment status

The initial standalone configuration was checked with the host Nginx binary:

```bash
sudo nginx -t -c /home/ubuntu/opiraja-hindamiskomponent/deploy/nginx/opiraja.conf
```

Result: syntax was OK and the test was successful. The corrected site fragment
was installed at `/etc/nginx/sites-available/opiraja.conf`, enabled through
`/etc/nginx/sites-enabled/opiraja.conf`, and passed the host's complete
`sudo nginx -t` check. The original stock default-site symlink was backed up
under `/var/backups/nginx/opiraja-pre-https-20260731/` and removed from the
active include directory so it could not retain a competing port-80 listener.

After the Compose loopback cutover, host Nginx was enabled and started with
`sudo systemctl enable --now nginx`. It is active and enabled at boot. Final
listeners are host Nginx on IPv4 ports 80 and 443, with no host IPv6 80/443
listener and no host 8000 listener. Local HTTP/HTTPS acceptance checks passed;
the external approved/non-approved source check still requires those clients.

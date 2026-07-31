# Task 4 Host-Nginx Change Log

Date started: 2026-07-31

## Project change

Added the version-controlled host-Nginx template:

- `deploy/nginx/opiraja.conf`

It targets `193.40.157.124`, terminates TLS with the VM-local certificate,
redirects exact-IP HTTP requests with `308`, rejects unknown hosts, proxies
only to `127.0.0.1:8080`, replaces untrusted forwarding headers, preserves the
long SSE timeout without buffering, blocks internal/documentation routes, and
logs request IDs/status/latency without query strings, authorization headers,
cookies, or bodies.

## Validation and deployment status

The configuration was checked with the host Nginx binary:

```bash
sudo nginx -t -c /home/ubuntu/opiraja-hindamiskomponent/deploy/nginx/opiraja.conf
```

Result: syntax is OK and the test was successful. The configuration has not
been installed or enabled yet because the current Compose web service still
owns host port 80. The safe deployment order requires the later loopback-only
Compose publication first.

No host-Nginx service state was changed by Task 4.

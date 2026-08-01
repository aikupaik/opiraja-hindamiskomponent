# Phase 2 — Restricted HTTPS Stabilization and Hardening Runbook

This runbook is for the restricted HTTPS deployment of Opiraja on the
approved VM. It supplements the implementation plan and the sanitized
[Phase 2 change log](../agent-logs/phase-2-restricted-https-stabilization-hardening-change-log.md).

It is an operator procedure, not an unattended deployment script. Run it only
during an approved maintenance window when rollback access and the OpenStack
console/recovery path are available.

## Safety and evidence rules

- Use UTC timestamps in all evidence.
- Never write bearer tokens, access keys, cookies, request bodies, uploaded
  content, private keys, rendered `.env` values, or sensitive query strings to
  this repository or an evidence record.
- Do not paste raw access/error logs into Git. Record sanitized counts,
  statuses, limiter outcomes, and timestamps instead.
- When showing a URL in evidence, use its path without the query string. If the
  query is relevant to a test, record only `query-present`.
- Do not weaken OpenStack, UFW, TLS, or host-listener restrictions to perform
  a test. An unavailable external vantage is an unverified result.
- Preserve the known-good Phase 1 HTTPS commit and the privileged host-Nginx
  backup before changing the live deployment.

## 1. Preconditions and ownership

Confirm the following before making a VM change:

- [ ] The reviewed repository commit is identified and the working tree used
      for deployment is clean.
- [ ] Console/recovery access and a rollback window are available.
- [ ] The exact VM port and its attached OpenStack security groups are known.
- [ ] Approved source CIDRs for ports 80/443 and SSH are available from the
      network owner.
- [ ] A non-approved external source is available for the denial check, or the
      check is explicitly marked unverified.
- [ ] An approved client and a non-production test credential are available
      for authenticated API, upload, rate-limit, and SSE checks.
- [ ] The operator has confirmed that the certificate fingerprint before any
      credential is entered.

The operator owns credentials, browser certificate decisions, maintenance
approval, OpenStack policy, and external-source testing. The deployment agent
may prepare commands, inspect configuration, run checks from an authorized
environment, and record sanitized results.

## 2. Baseline collection

Collect the following before installation. Save raw output only in the
privileged VM evidence area, not in Git; copy only sanitized values into the
evidence record below.

```sh
date --iso-8601=seconds
git rev-parse HEAD
uname -a
nginx -v
sudo nginx -V 2>&1
docker version --format '{{.Server.Version}}'
docker compose version
sudo ss -ltnp
sudo ufw status verbose
sudo systemctl is-active nginx
docker compose ps
docker stats --no-stream
df -h
df -i
docker system df
timedatectl status
```

Also record, without values:

- package source/provenance for Nginx and Docker;
- Compose health state, container restart counts, Docker network names/subnets,
  and listeners;
- certificate subject, SAN, SHA-256 fingerprint, and expiry;
- `nginx -V` support for `limit_req`, `limit_conn`, and their dry-run
  directives;
- `.env` owner and mode, its Git-ignore status, and confirmation that it is
  not present in images or Git;
- absence of `/var/run/docker.sock` mounts from application containers;
- Docker socket ownership/mode and the membership of the Docker group;
- filesystem, inode, Docker disk, and log-rotation baselines.

Do not use `docker compose config` output as evidence if it renders secrets.
Use `docker compose config --quiet` for structural validation and record only
pass/fail.

## 3. Install the reviewed host configuration in dry-run mode

The first Phase 2 host configuration must retain:

```nginx
limit_req_dry_run on;
limit_conn_dry_run on;
```

Back up the active site in the privileged VM backup area, install the reviewed
repository file through the normal root-owned site path, and validate before
reload. The expected active paths are:

```text
/etc/nginx/sites-available/opiraja.conf
/etc/nginx/sites-enabled/opiraja.conf
```

Use the following sequence, adapting the backup directory to the approved VM
backup policy:

```sh
sudo install -d -o root -g root -m 0700 \
  /var/backups/nginx/opiraja-phase-2-YYYYMMDD
sudo cp -a /etc/nginx/sites-available/opiraja.conf \
  /var/backups/nginx/opiraja-phase-2-YYYYMMDD/opiraja.conf.before
sudo install -o root -g root -m 0644 \
  deploy/nginx/opiraja.conf /etc/nginx/sites-available/opiraja.conf
sudo nginx -t
sudo systemctl reload nginx
```

Do not restart Nginx when a graceful reload is sufficient. Record the config
checksum and the `nginx -t`/reload result, not the private certificate or key.

## 4. Dry-run observation and controlled tests

After reload, confirm normal service health from an approved client and review
at least one normal operating day of dry-run logs. Dry-run excesses must not
reject requests; they should appear through limiter status fields and warning
events.

Run controlled probes against harmless paths:

- More than 30 rapid requests to a harmless `/api/` path. Record only the
  response-status counts and limiter statuses.
- More than five rapid requests to the exact admin-session path. Use an
  approved authenticated client where required; never record the credential.
- Three concurrent authenticated SSE connections for one client IP. Confirm
  two remain incremental and the third is identified as an excess without
  interrupting established streams.
- One normal admin workflow and one complete simulation to detect false
  positives.

Review host access/error logs for `413`, `429`, 5xx, `$limit_req_status`, and
`$limit_conn_status`. Summarize counts and time windows. Do not copy raw lines.

If ordinary traffic shows false positives, stop and investigate before
enforcement. Do not silently raise limits or disable the zones.

## 5. Enable enforcement

Only after dry-run observation and controlled tests are reviewed, deploy the
reviewed enforcement revision with both dry-run directives disabled. Keep the
change version-controlled; do not edit the live file without recording the
corresponding commit or change identifier.

```sh
sudo nginx -t
sudo systemctl reload nginx
```

Repeat the controlled probes. Confirm that:

- the general API allows its configured rate/burst and then returns `429` with
  the `rate_limited` JSON envelope;
- the exact admin-session endpoint enforces its stricter rate;
- two SSE streams remain incremental and the third receives `429`;
- established streams are not interrupted by request-rate limiting;
- ordinary UI/API/upload behavior and the existing `413` boundary continue to
  work;
- public responses contain exactly one host-generated `X-Request-ID` header.

## 6. Monitoring cadence

Review the following daily for the first seven days after enforcement, weekly
after stabilization, and immediately before and after package, Nginx,
certificate, or Compose changes:

```sh
docker compose ps
docker compose top
docker stats --no-stream
sudo ss -ltnp
sudo systemctl is-active nginx
sudo nginx -t
df -h
df -i
docker system df
timedatectl status
```

Review sanitized host Nginx access/error totals and container logs for all
unexpected 5xx and 429 responses, readiness failures, restart-count changes,
filesystem/inode use at 80% and 90% thresholds, Docker/log consumption,
certificate validity (fail the checklist below 30 days), and logrotate
coverage for both Opiraja logs.

Create operator-owned reminders 30, 14, and 7 days before the post-rehearsal
certificate expiry.

## 7. Patching and application deployment

Schedule a restricted-access maintenance window and confirm recovery access.
Back up active host Nginx configuration before patching. Review package
provenance and pending updates; keep Ubuntu `docker.io` updates on Ubuntu
repositories and Docker CE updates on the already-configured Docker
repository. Do not migrate repositories in this phase.

Apply Ubuntu security, Nginx, OpenSSL, and Docker updates according to the
approved maintenance procedure. Reboot only when
`/var/run/reboot-required` exists and the window permits it. After patching or
reboot, verify UFW, Nginx, Docker, Compose, listeners, readiness, and TLS
versions before proceeding.

Deploy the reviewed application commit with:

```sh
docker compose config --quiet
docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps
```

Wait for healthy R/API/web services, then repeat loopback readiness and
approved-client HTTPS smoke tests. Do not print or record environment values.

## 8. Certificate replacement rehearsal

Generate a new 90-day IP-SAN certificate beside the live files in the
privileged VM area. Verify key/certificate pairing, ownership, and permissions
without recording key material. Back up the current live pair, install the
replacement at the stable paths, run `sudo nginx -t`, and gracefully reload.
From an approved client, compare the new fingerprint independently. If any
validation fails, restore the previous pair, validate, reload, and record the
sanitized outcome.

## 9. Failure recovery rehearsal

Restart services separately in this order and verify expected readiness
transitions after each recovery:

1. `r-service`
2. `api`
3. `web`

Confirm that recovery does not alter networks, firewall rules, TLS files, or
host listeners. Record only service names, timestamps, health results, and
restart-count changes.

## 10. Rollback

First reconfirm OpenStack and UFW restrictions. Roll back only to the recorded
known-good Phase 1 HTTPS commit and the privileged host-Nginx backup. Validate
with `docker compose config --quiet`, `sudo nginx -t`, health checks, listener
checks, and HTTPS smoke tests before declaring recovery.

Never roll back to public plaintext HTTP or to a Compose revision publishing
port 80 directly. After the cause is understood, redeploy the reviewed Phase
2 revision and repeat the relevant dry-run/enforcement checks.

## Sanitized evidence record

Copy this template into the approved operator evidence system or append a
sanitized entry to the Phase 2 change log. Replace placeholders with metadata,
counts, and pass/fail results only.

| UTC timestamp | Evidence item | Sanitized result | Operator/change ID |
| --- | --- | --- | --- |
| `YYYY-MM-DDThh:mm:ssZ` | Release commit/config checksum | `<commit-or-checksum>` | `<id>` |
| `YYYY-MM-DDThh:mm:ssZ` | VM/package/container baseline | `<versions-and-status-only>` | `<id>` |
| `YYYY-MM-DDThh:mm:ssZ` | OpenStack/UFW/listener gate | `<approved-cidrs-confirmed; listeners-summary>` | `<id>` |
| `YYYY-MM-DDThh:mm:ssZ` | Dry-run API/session/SSE probes | `<status-counts-and-limiter-statuses>` | `<id>` |
| `YYYY-MM-DDThh:mm:ssZ` | Normal workflow observation | `<pass/fail; sanitized finding>` | `<id>` |
| `YYYY-MM-DDThh:mm:ssZ` | Enforcement API/session/SSE probes | `<status-counts-and-envelope-check>` | `<id>` |
| `YYYY-MM-DDThh:mm:ssZ` | Log-sanitization review | `<query-free; no secrets/bodies/cookies>` | `<id>` |
| `YYYY-MM-DDThh:mm:ssZ` | Health/restart/disk/certificate review | `<pass/fail; expiry window>` | `<id>` |
| `YYYY-MM-DDThh:mm:ssZ` | Recovery/rollback rehearsal | `<services-and-health-results>` | `<id>` |

Do not replace placeholders with raw command output if it contains a secret,
cookie, body, private key, or sensitive query value. Record `not run` or
`unverified` when an external dependency or operator decision is unavailable.

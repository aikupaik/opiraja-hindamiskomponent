# Loki, Alloy, and Grafana Runbook

This is the operational runbook for the single-VM API/R log stack. Grafana
Alloy reads Docker logs for the opted-in `api` and `r-service` containers,
forwards the original application JSON to Loki, and Grafana provides the
version-controlled `Opiraja API/R Logs` dashboard and Explore.

Loki retains data for 14 days (`336h`). Its TSDB files are internal storage,
not an operator-readable NDJSON archive. Loki does not enforce a byte ceiling,
so disk and inode monitoring are required.

OBS-02 remains historical evidence of the previous Filebeat implementation but
is superseded by this runbook and OBS-03. Legacy Filebeat NDJSON is not imported
into Loki. Preserve the old archive and registry read-only through acceptance
and the rollback window.

## Security boundary

- Only `api` and `r-service` carry `com.opiraja.logs.enabled=true`.
- Only Alloy mounts `/var/run/docker.sock`. This is host-root-equivalent access
  even though the bind is read-only, so Alloy has no application secrets,
  application-network membership, or published port.
- Loki and Alloy are reachable only on the internal Compose `observability`
  network. Loki has authentication disabled only inside this boundary.
- Grafana straddles the internal network and a Grafana-only bridge required for
  Docker host publishing. It publishes `127.0.0.1:3000`; host Nginx is the only
  external path.
- Host Nginx permits `/grafana` and `/grafana/` only from `172.20.0.0/16` and
  `193.40.0.0/16`, and Grafana authentication is still mandatory.
- Stored Loki stream labels are limited to `service`, `level`, `event`, and
  `stream`. Request IDs, test IDs, paths, statuses, durations, dependency
  timings, and errors stay in the JSON line.
- A malformed or non-schema line is retained unchanged with the bounded labels
  `event=parser_error` and `level=UNKNOWN`.

Routine operators need named Grafana accounts with the OSS `Editor` role so
they can use Explore. Editors must not be given Grafana Server Admin rights.
Keep the bootstrap administrator for recovery and provisioning work only.

## Repository validation

Run from the repository root. These checks do not deploy to the VM:

```sh
docker compose config --quiet
docker compose run --rm --no-deps alloy validate /etc/alloy/config.alloy
docker compose run --rm --no-deps loki \
  -config.file=/etc/loki/local-config.yaml -verify-config=true
python -m json.tool \
  observability/grafana/dashboards/opiraja-api-r-logs.json >/dev/null
cd backend
source .venv/bin/activate
python -m pytest tests/test_nginx_config.py tests/test_observability.py \
  tests/test_observability_stack.py
python -m pyright
```

The two container validations may pull the exact images pinned in
`compose.yaml`. Never substitute a floating tag during validation.

## VM preparation

### Images and host capacity

Record the host architecture and resolved image digests in deployment evidence,
without copying registry credentials or image metadata into Git:

```sh
uname -m
docker info --format '{{.Architecture}}'
docker compose pull loki alloy grafana
docker image inspect --format '{{index .RepoDigests 0}}' \
  grafana/loki:3.7.8
docker image inspect --format '{{index .RepoDigests 0}}' \
  grafana/alloy:v1.19.2
docker image inspect --format '{{index .RepoDigests 0}}' \
  grafana/grafana:13.2.2
df -h /var/lib
df -i /var/lib
```

The expected container users for the pinned configuration are Loki UID/GID
`10001`, Grafana UID `472` with GID `0`, and root for Alloy. Confirm them from
the pinned images before creating directories; if an image reports different
numeric ownership, stop and review the repository configuration rather than
loosening permissions.

### Persistent storage

The following paths are examples of protected locations outside the checkout:

```sh
sudo install -d -o 10001 -g 10001 -m 0750 /var/lib/opiraja/loki
sudo install -d -o root -g root -m 0700 /var/lib/opiraja/alloy
sudo install -d -o 472 -g 0 -m 0750 /var/lib/opiraja/grafana
sudo install -d -o root -g root -m 0700 /etc/opiraja/observability
```

Grafana's directory contains its SQLite account and session database and must be
handled as sensitive data. Do not grant application containers any of these
mounts.

### Bootstrap secrets

Generate independent values. Do not print them, pass them as ordinary Compose
environment values, or store them in the checkout:

```sh
sudo sh -c 'umask 077; openssl rand -base64 48 > /etc/opiraja/observability/grafana-admin-password'
sudo sh -c 'umask 077; openssl rand -base64 64 > /etc/opiraja/observability/grafana-secret-key'
sudo chown root:root /etc/opiraja/observability/grafana-*
sudo chmod 0600 /etc/opiraja/observability/grafana-*
```

Standalone Compose secrets are read-only bind mounts of source files. Keep the
host files root-owned and mode `0600`, and grant only the pinned Grafana UID a
read ACL so the non-root process can consume the `__FILE` settings:

```sh
sudo setfacl -m u:472:r /etc/opiraja/observability/grafana-admin-password
sudo setfacl -m u:472:r /etc/opiraja/observability/grafana-secret-key
sudo getfacl /etc/opiraja/observability/grafana-admin-password
sudo getfacl /etc/opiraja/observability/grafana-secret-key
```

If the VM filesystem does not support POSIX ACLs, stop and agree on a reviewed
secret-delivery alternative. Do not run Grafana as root or make a secret
world-readable.

### Deployment environment

Set these values in the VM's existing root-protected mode-`0600` `.env`:

```dotenv
LOKI_DATA_DIR=/var/lib/opiraja/loki
ALLOY_DATA_DIR=/var/lib/opiraja/alloy
GRAFANA_DATA_DIR=/var/lib/opiraja/grafana
GRAFANA_ROOT_URL=https://193.40.157.124/grafana/
GRAFANA_ADMIN_PASSWORD_FILE=/etc/opiraja/observability/grafana-admin-password
GRAFANA_SECRET_KEY_FILE=/etc/opiraja/observability/grafana-secret-key
```

Change `GRAFANA_ROOT_URL` to the externally correct HTTPS URL during the planned
domain cutover. It must retain the trailing `/grafana/` path.

Before deployment, confirm OpenStack security groups and UFW allow the same
operator sources as Nginx. Do not open TCP ports 3000, 3100, 12345, or a Docker
API port in either layer.

## VM validation and deployment

Run validation with the protected deployment `.env` without printing rendered
Compose configuration or secret contents:

```sh
docker compose config --quiet
docker compose run --rm --no-deps alloy validate /etc/alloy/config.alloy
docker compose run --rm --no-deps loki \
  -config.file=/etc/loki/local-config.yaml -verify-config=true
python -m json.tool \
  observability/grafana/dashboards/opiraja-api-r-logs.json >/dev/null
```

Back up the active Nginx site, install the reviewed `deploy/nginx/opiraja.conf`,
test it, and reload gracefully:

```sh
sudo cp -a /etc/nginx/sites-available/opiraja.conf \
  /etc/nginx/sites-available/opiraja.conf.pre-obs-03
sudo install -o root -g root -m 0644 deploy/nginx/opiraja.conf \
  /etc/nginx/sites-available/opiraja.conf
sudo nginx -t
sudo systemctl reload nginx
```

Start the new stack before removing the orphaned Filebeat container. With the
old Filebeat container still running from the prior revision:

```sh
docker compose up -d loki alloy grafana
docker compose ps loki alloy grafana api r-service
docker compose logs --tail=100 loki alloy grafana
```

After Loki, Alloy, Grafana, `api`, and `r-service` are healthy and initial
acceptance succeeds, remove the old orphan without deleting its data:

```sh
docker stop opiraja-assessment-filebeat-1
docker rm opiraja-assessment-filebeat-1
docker compose up -d --remove-orphans
```

Resolve the actual orphan name with `docker ps` instead of assuming it if the
project name was customized. Leave the old archive and registry unchanged.

## First access and accounts

From an approved network, open
`https://193.40.157.124/grafana/`. Sign in as the bootstrap administrator and:

1. create an individual named user for each operator;
2. assign the organization role `Editor`;
3. store operator and break-glass credentials in the approved password manager;
4. use a named Editor account for routine dashboard and Explore work; and
5. confirm an Editor cannot administer users or data sources.

Disable departed accounts during access review. Anonymous access and
self-registration must remain disabled. OIDC/SSO is not part of this pilot.

## Querying and acceptance

The provisioned `Opiraja API/R Logs` dashboard is canonical and cannot be saved
over from the UI. Operators may create separate non-provisioned dashboards.

Useful Explore queries include:

```logql
{service=~"api|r-service"}
```

```logql
{service=~"api|r-service", event="request_completed"}
| json
| status >= 500
```

```logql
{service=~"api|r-service"}
| json
| __error__=""
| request_id="CONTROLLED_REQUEST_ID"
```

```logql
{service=~"api|r-service", event="request_completed"}
| json
| duration_ms >= 1000
```

```logql
{service="api", event="supabase_operation"}
| json
| outcome="failed"
```

```logql
{service="api", event="assessment_create_received"}
| json
| node_count > 10
```

```logql
{event="parser_error", level="UNKNOWN"}
```

Do not put real production request IDs into shared evidence or shell history.
Application JSON fields parsed at query time are not stored stream labels.

For acceptance:

- make a controlled API call that invokes R and find one event from each
  service with the same `request_id`;
- verify service, event, level, status, duration, `supabase_ms`, `r_ms`, and
  applicable correlation fields;
- inspect every dashboard panel over a controlled time range;
- confirm an Editor can use Explore but cannot change the provisioned dashboard
  or administer users/data sources;
- restart Alloy and confirm persisted positions avoid replay duplication;
- restart Loki and confirm earlier records remain queryable;
- restart Grafana and confirm accounts, datasource, and dashboard persist; and
- confirm no authorization header, cookie, configured secret, sensitive query
  string, or request body is present except the documented bounded allowlist in
  `assessment_create_received`; specifically confirm `user_id` and
  `learning_path_id` are absent.

Grafana Editor users with Loki access can view the allowlisted assessment graph
and configuration content for the 14-day retention period. The dashboard shows
failed Supabase calls, per-operation p50/p95 duration, and calls above the
documented 500 ms slow-operation threshold. Its request-ID view correlates the
create input, Supabase and R operations, request failure, and terminal completion
in timestamp order. These values are parsed JSON fields, not Loki labels.

To verify malformed-line retention, run a short-lived, explicitly labelled test
container outside Compose, then remove it. Use an already approved local image
and a synthetic line containing no sensitive data:

```sh
docker run --rm --name opiraja-malformed-log-test \
  --label com.opiraja.logs.enabled=true \
  --label com.opiraja.logs.service=malformed-test \
  busybox:1.36.1 sh -c 'echo controlled-non-json-line'
```

Confirm the exact line is queryable with `event="parser_error"`, then confirm
the test container no longer exists. This temporary service value is acceptable
only for the controlled acceptance check.

## Network and browser verification

From an approved source, verify HTTPS login, dashboard assets, Explore, the
request-ID lookup, secure/SameSite cookies, and Grafana Live WebSockets. From a
source outside both approved CIDRs, verify `/grafana` and `/grafana/` are denied
before Grafana authentication.

On the VM, confirm the listener boundary:

```sh
ss -lnt
docker compose port grafana 3000
docker compose port loki 3100
docker compose port alloy 12345
sudo ufw status verbose
```

Grafana must show only `127.0.0.1:3000`; Loki and Alloy must return no published
port. Review OpenStack rules separately. Confirm the SPA still has its original
CSP and Grafana has one compatible nonce-aware Grafana CSP, with no duplicate
security headers.

## Disk and inode monitoring

Monitor both bytes and inodes for the filesystem containing Loki. Warn at 80%
and treat 90% as urgent:

```sh
df -h /var/lib/opiraja/loki
df -i /var/lib/opiraja/loki
sudo du -sh /var/lib/opiraja/loki
```

Fourteen-day deletion is time-based and compactor-driven. Do not delete files
inside Loki's directory manually. If capacity is urgent, restrict ingestion or
stop the stack, preserve the directory for diagnosis, and review retention or
storage sizing before resuming.

## Credential and key rotation

- Operators change their own passwords through Grafana and update the approved
  password manager.
- Rotate the break-glass administrator password through the authenticated
  Grafana UI. Replace the bootstrap password file securely with the same value
  so a future clean database bootstrap is consistent. The file is not a live
  password-reset mechanism for an existing SQLite database.
- Rotating `GRAFANA_SECRET_KEY_FILE` invalidates sessions and may invalidate
  encrypted settings. Schedule a maintenance window, back up Grafana first,
  replace the file atomically with a new independent value and the same
  root/`0600`/ACL protections, restart Grafana, and reverify login and the Loki
  datasource. The provisioned datasource contains no stored credential.

Never include secret values in commands, tickets, logs, or deployment evidence.

## Backup

Grafana's data directory is the critical account/session backup. Loki data may
also be backed up for operational recovery, and Alloy's directory preserves
read positions. For a filesystem-consistent cold backup, stop only the three
observability services, copy all three data directories plus the two secret
files into the approved encrypted backup location, and restart the services:

```sh
docker compose stop alloy grafana loki
# Perform the approved root-only backup outside the repository.
docker compose up -d loki alloy grafana
docker compose ps loki alloy grafana
```

Do not back up by copying a live Grafana SQLite file. Test restore procedures in
an isolated environment and keep backup retention aligned with the pilot's data
handling policy.

## Rollback

Keep the previous known-good release/commit containing Filebeat and the backed
up host-Nginx site until acceptance closes. If OBS-03 fails:

1. restore `/etc/nginx/sites-available/opiraja.conf.pre-obs-03`, run
   `sudo nginx -t`, and gracefully reload Nginx;
2. stop Loki, Alloy, and Grafana without deleting their data directories;
3. deploy the previous known-good Compose revision and start Filebeat; and
4. verify application HTTPS, API/R health, Docker logs, and Filebeat archiving.

Preserve Loki, Alloy, Grafana, Filebeat archive, and Filebeat registry data for
diagnosis. Do not delete or rewrite any of them during rollback. Supabase data,
application state, and application containers require no migration or restore.

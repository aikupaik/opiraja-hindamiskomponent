# OBS-03 — Pivot from Filebeat to Loki, Alloy, and Grafana

## Summary

Replace Filebeat's NDJSON archive with a single-host observability stack:

```text
api / r-service
  → Docker json-file logs
  → Grafana Alloy
  → Loki TSDB on the VM filesystem
  → Grafana dashboard and Explore
  → host Nginx /grafana/ over HTTPS
```

Keep the existing structured-log schema, request correlation, redaction rules,
and Docker log rotation unchanged. Collect only `api` and `r-service`. Retain
Loki data for 14 days.

Task ownership labels used throughout this plan:

- **[CODE]** — changes and checks performed in the Git repository;
- **[VM]** — deployment-VM preparation, secrets, installation, operation, or
  external verification; and
- **[CODE + VM]** — configuration is implemented in the repository and then
  separately deployed or accepted on the VM.

Use these pinned official images and immutable manifest digests:

- Loki 3.7.8:
  `grafana/loki:3.7.8@sha256:1107dd5274e0ada47e42472b7a7e71f3b2a2fe878878108f3e2f9e51528f0193`
- Alloy 1.19.2:
  `grafana/alloy:v1.19.2@sha256:b8ec653c44235fbe910879145dac3597d66b0aaecf60bcbbe82580767771a839`
- Grafana 13.2.2:
  `grafana/grafana:13.2.2@sha256:ac461fb352abc50da10a51c7d02462e9c05488f11f53f14b3ad79a8145f638a0`

## Repository Implementation

### Loki collection and filesystem storage

- **[CODE]** Add version-controlled Loki, Alloy, and Grafana provisioning
  configuration under `observability/`.
- **[CODE]** Configure Loki as a single binary using TSDB schema v13,
  filesystem object storage, replication factor one, and `/var/lib/loki` as
  its persistent data root.
- **[CODE]** Enable compactor retention with `retention_period: 336h`, a
  persistent compactor working directory, and filesystem delete-request
  storage.
- **[CODE]** Add a private, internal `observability` Compose network. Loki is
  reachable only by Alloy and Grafana on that network; it has no host-published
  port. `auth_enabled: false` is acceptable only within this boundary.
- **[CODE]** Add a persistent Alloy storage mount so Docker read positions
  survive collector restarts.
- **[CODE]** Configure Alloy to discover containers through
  `/var/run/docker.sock`, selecting only containers with a project-owned
  opt-in label. Put that label only on `api` and `r-service`.
- **[CODE]** Have Alloy unwrap the Docker log record while preserving the
  original application JSON as the Loki log line. Create only the bounded
  labels `service`, `level`, `event`, and stdout/stderr stream.
- **[CODE]** Keep `request_id`, `test_id`, paths, statuses, durations, and error
  details inside the JSON log line instead of turning them into high-cardinality
  Loki labels.
- **[CODE]** Preserve malformed or non-JSON lines with parser-error
  identification instead of silently dropping them.
- **[CODE]** Harden all three services with the existing Compose conventions:
  `restart: unless-stopped`, `init`, read-only root filesystem where supported,
  `no-new-privileges`, dropped capabilities, PID limits, bounded temporary
  storage, health checks, and rotated Docker logs.
- **[CODE]** Run only Alloy as root because access to the Docker socket is
  host-root-equivalent. Give Alloy no application secrets, published ports, or
  application-network membership. Do not mount `/var/lib/docker/containers`;
  `loki.source.docker` reads through the Docker API.

Loki storage is an internal TSDB chunk/index directory, not an
operator-readable NDJSON archive. Retention is time-based rather than capped at
500 MB. VM disk and inode monitoring therefore remains mandatory.

### Grafana provisioning and dashboard

- **[CODE]** Add Grafana to the internal observability network and publish only
  `127.0.0.1:3000:3000` for host Nginx. Loki and Alloy remain unpublished.
- **[CODE]** Persist `/var/lib/grafana`, including Grafana's SQLite user and
  session database.
- **[CODE]** Provision Loki as the default data source at
  `http://loki:3100`, using a stable datasource UID and no embedded secrets.
- **[CODE]** Provision a read-only `Opiraja API/R Logs` dashboard from Git with:
  - time-range, service, level, and event filters;
  - total request completions, warnings, 4xx responses, and 5xx responses;
  - request rate and status/outcome distribution;
  - p50 and p95 request duration by service;
  - FastAPI Supabase and R dependency timing where those fields exist;
  - recent failures and slow requests;
  - correlated API/R lookup by `request_id`; and
  - a raw structured-log panel linking into Explore.
- **[CODE]** Configure the dashboard provider with `allowUiUpdates: false` so
  the canonical dashboard remains version-controlled.
- **[CODE]** Leave Explore enabled. Routine operator accounts receive the
  Grafana OSS `Editor` organization role because Explore is unavailable to the
  basic Viewer role. Editors cannot administer users or data sources, although
  they may create their own non-provisioned dashboards.
- **[CODE]** Disable anonymous access, self-registration, usage reporting,
  update checks, and plugin administration. Enable secure SameSite cookies,
  Grafana's login protection, and Grafana's nonce-aware Content Security
  Policy.
- **[CODE]** Configure the initial administrator password and stable Grafana
  secret key through `GF_SECURITY_ADMIN_PASSWORD__FILE` and
  `GF_SECURITY_SECRET_KEY__FILE`. Never place their values in Git or ordinary
  Compose environment variables.
- **[CODE]** Keep alerting, metrics collection, SMTP, external plugins and
  dashboards, and collection of Nginx, web, player, Grafana, Loki, or Alloy
  logs out of scope.

### Host-Nginx source configuration

- **[CODE]** Extend `deploy/nginx/opiraja.conf` with an exact `/grafana`
  redirect to `/grafana/` and a `/grafana/` reverse proxy to
  `http://127.0.0.1:3000`.
- **[CODE]** Preserve the `/grafana/` subpath through the proxy and configure
  Grafana's `root_url` and `serve_from_sub_path` settings consistently.
- **[CODE]** Restrict both Grafana locations using Nginx `allow` directives for
  the currently approved operator networks, `172.20.0.0/16` and
  `193.40.0.0/16`, followed by `deny all`. Keep this route-level restriction
  even if the main application later becomes Internet-accessible.
- **[CODE]** Proxy Grafana Live WebSocket upgrades and replace client-supplied
  forwarding headers with trusted host-Nginx values.
- **[CODE]** Prevent the application SPA's CSP from being inherited by the
  Grafana location. Pass Grafana's own nonce-aware CSP while retaining the
  repository's frame, referrer, content-type, request-ID, and no-cache
  protections as appropriate.
- **[CODE]** Apply a dedicated login rate limit to `/grafana/login`. Keep query
  strings and credentials out of host access logs.
- **[CODE]** Extend the existing Nginx configuration tests for the loopback
  upstream, subpath redirect/proxy, approved-CIDR boundary, trusted forwarding
  headers, WebSocket support, login limiting, and CSP separation.

### Filebeat removal and documentation

- **[CODE]** Remove the Filebeat Compose service, Elastic discovery labels,
  `observability/filebeat.yml`, the container-log-directory mount, and the old
  archive/registry environment variables.
- **[CODE]** Preserve OBS-01 and OBS-02 as historical completed plans. Mark
  OBS-02 as superseded in the new operational documentation rather than
  rewriting its historical contents.
- **[CODE]** Replace the Filebeat archive runbook and README section with Loki,
  Alloy, and Grafana deployment, access, querying, disk monitoring, credential
  rotation, backup, verification, and rollback instructions.
- **[CODE]** Document that legacy Filebeat NDJSON is not imported into Loki.
  Existing VM archive and registry directories remain read-only during the
  acceptance and rollback window.
- **[CODE]** Replace the old environment examples with:

  ```dotenv
  LOKI_DATA_DIR=./.runtime/observability/loki
  ALLOY_DATA_DIR=./.runtime/observability/alloy
  GRAFANA_DATA_DIR=./.runtime/observability/grafana
  GRAFANA_ROOT_URL=https://193.40.157.124/grafana/
  GRAFANA_ADMIN_PASSWORD_FILE=./.runtime/observability/secrets/grafana-admin-password
  GRAFANA_SECRET_KEY_FILE=./.runtime/observability/secrets/grafana-secret-key
  ```

  The VM overrides these with protected absolute paths outside the checkout.
  `GRAFANA_ROOT_URL` changes during the planned domain cutover.

## Deployment-VM Work

### Preparation and secrets

- **[VM]** Confirm the exact Compose host architecture and pull the three
  pinned image references. Record the resolved digests without copying image
  metadata or credentials into Git.
- **[VM]** Create persistent Loki, Alloy, and Grafana directories outside the
  repository. Give each directory the numeric owner required by its pinned
  container and the minimum writable permissions; Grafana's directory contains
  account/session data and must be treated as sensitive.
- **[VM]** Generate independent high-entropy files for the Grafana bootstrap
  administrator password and secret key. Store them outside Git, owned by
  root, with mode `0600`, and set only their paths in the protected deployment
  `.env`.
- **[VM]** Set absolute `LOKI_DATA_DIR`, `ALLOY_DATA_DIR`, and
  `GRAFANA_DATA_DIR` paths plus the externally correct HTTPS
  `GRAFANA_ROOT_URL` in the VM's existing mode-`0600` `.env`.
- **[VM]** Check free space and inode capacity before deployment. Retain the
  existing warning threshold at 80% filesystem use and treat 90% as urgent;
  Loki does not delete based on available bytes.
- **[VM]** Verify that the current OpenStack and UFW approved sources match the
  Nginx Grafana allowlist. Do not open ports 3000, 3100, 12345, or Docker API
  ports in either layer.

### Configuration validation and deployment

- **[CODE]** Run `docker compose config --quiet`, validate Alloy's
  configuration, run Loki's configuration verification, validate dashboard and
  provisioning files, and run the repository's host-Nginx configuration tests.
- **[VM]** Repeat Compose, Alloy, and Loki validation using the deployment
  `.env` and VM bind-mount paths without printing rendered secrets.
- **[VM]** Back up the active host-Nginx site, install the reviewed repository
  configuration, run `sudo nginx -t`, and use a graceful reload. Do not restart
  Nginx when a reload is sufficient.
- **[VM]** Start Loki, Alloy, and Grafana before stopping Filebeat. This short
  overlap preserves rollback coverage and cannot duplicate Loki records because
  Filebeat never writes to Loki.
- **[VM]** Confirm all three new services are healthy and the application
  services remain healthy. Then stop and remove the orphaned Filebeat
  container.
- **[VM]** Keep the previous Filebeat archive and registry directories
  unchanged through the acceptance window. Delete them only through a later,
  explicitly approved cleanup after rollback is no longer required.

### Accounts and operator access

- **[VM]** Access `https://<deployment-host>/grafana/` from an approved source,
  sign in with the bootstrap administrator, and immediately create an
  individual named account for each operator with the `Editor` role.
- **[VM]** Store operator and break-glass administrator credentials in the
  approved password manager. Do not share a common operator account.
- **[VM]** Use named Editor accounts for normal dashboard and Explore work.
  Reserve the administrator account for account recovery, upgrades, and
  provisioning diagnosis.
- **[VM]** Review and disable departed operator accounts as part of the pilot's
  access-review process. Local Grafana accounts are the selected pilot model;
  OIDC/SSO integration is deferred.

## Verification and Acceptance

### Repository and container checks

- **[CODE]** Confirm rendered Compose contains the pinned images, three
  persistent mounts, the private observability network, only the Grafana
  loopback publication, and existing 5 x 10 MB Docker log rotation.
- **[CODE]** Confirm only `api` and `r-service` have the Alloy opt-in label;
  only Alloy mounts the Docker socket; and no service mounts
  `/var/lib/docker/containers` after Filebeat removal.
- **[CODE]** Confirm `.runtime/`, generated secrets, Loki data, Alloy positions,
  Grafana SQLite data, and legacy archives remain ignored by Git.
- **[CODE]** Re-run the existing API/R structured-logging and redaction tests.
  Application code and the versioned log schema must remain unchanged.

### End-to-end log and dashboard checks

- **[CODE + VM]** Generate a controlled API request that calls R and verify one
  event from each service reaches Loki with the same `request_id`.
- **[CODE + VM]** Verify `service`, `event`, `level`, `status`, `duration_ms`,
  dependency timings, and correlation fields remain queryable. Confirm
  `request_id` and other unbounded values are not stream labels.
- **[CODE + VM]** Inject a controlled malformed source line through a temporary
  labelled test container and verify it remains searchable with parser-error
  identification. Remove the test container after the check.
- **[VM]** Verify every dashboard panel over a controlled time range, including
  service filtering, failures, slow requests, dependency timing, and
  cross-service request-ID correlation.
- **[VM]** Verify an Editor can open Explore and run ad-hoc LogQL but cannot
  administer users or data sources. Confirm the provisioned dashboard cannot
  be overwritten through the UI.
- **[VM]** Restart Alloy and confirm its persisted positions prevent replay
  duplication. Restart Loki and confirm earlier records remain queryable.
  Restart Grafana and confirm accounts, the datasource, and the dashboard
  remain available.
- **[VM]** Confirm no existing redaction sentinel, authorization header,
  cookie, request body, configured secret, or sensitive query string appears
  in Loki.

### Security and network checks

- **[VM]** From an approved source, verify HTTPS login, dashboard assets,
  secure/SameSite cookies, Explore, request-ID lookup, and Grafana Live
  WebSocket behavior.
- **[VM]** From a source outside the approved CIDRs, verify `/grafana` and
  `/grafana/` are denied before Grafana authentication is reached.
- **[VM]** Verify anonymous Grafana access and self-registration are disabled.
- **[VM]** Verify external clients cannot reach ports 3000 or 3100 and that
  `ss`, Docker port inspection, UFW, and OpenStack show no unintended
  observability listener.
- **[VM]** Verify the application SPA still receives its original CSP and the
  Grafana UI receives a single compatible Grafana CSP. Confirm neither route
  has duplicate security headers.
- **[VM]** Review Alloy's Docker-socket privilege explicitly and confirm no
  application container gained the socket, observability data mounts, or
  Grafana secrets.

## Rollback

- **[CODE]** Keep the previous known-good Compose revision and Filebeat plan as
  the documented rollback source; do not retain two collectors in the final
  configuration.
- **[VM]** If the new stack or Grafana route fails acceptance, first restore
  the prior host-Nginx configuration and validate/reload it, then stop Loki,
  Alloy, and Grafana and restore the previous Compose revision with Filebeat.
- **[VM]** Preserve Loki, Alloy, Grafana, and Filebeat data directories for
  diagnosis. Do not delete or rewrite them during rollback.
- **[VM]** Verify application HTTPS, API/R health, Docker logs, and Filebeat
  archiving after rollback. Supabase data, application state, and application
  containers require no migration or restoration.

## Interfaces and Assumptions

- No public application API, response schema, persistence model, or API/R log
  schema changes.
- The only new HTTP interface is the CIDR-restricted and authenticated
  `/grafana/` operational UI. Grafana's port is loopback-only; Loki and Alloy
  have no host ports.
- Fourteen-day retention is the pilot default. Loki cannot enforce the former
  500 MB archive ceiling.
- The approved CIDRs above remain the authoritative operator-source networks;
  a change must update host Nginx and outer OpenStack/UFW controls together.
- Operators need both the canonical dashboard and Explore, accepting the
  broader Grafana OSS Editor role.
- Filesystem-backed, single-node Loki is sufficient for the pilot. High
  availability, object storage, remote backups, metrics, tracing, alerting,
  and SSO are later increments.

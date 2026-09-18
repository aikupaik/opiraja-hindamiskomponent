# API/R Local Structured-Log Archive

## Summary

Add Filebeat as a hardened Compose collector for only `api` and `r-service`.
It will read their existing Docker `json-file` records, decode each application
JSON event, and write normalized NDJSON archives to a host-persistent directory.
This keeps the current structured-log contract intact and makes the same events
ready for a later Elasticsearch output.

## Repository Changes

### Collector configuration

- Add `observability/filebeat.yml`. It is the single version-controlled source
  of the collector's parsing, retention, and output policy.
  - Configure Filebeat's Docker autodiscover provider against
    `unix:///var/run/docker.sock` and enable hint-based discovery. The default
    input must be a `filestream` input whose ID includes the discovered
    container ID, whose path is
    `/var/lib/docker/containers/<container-id>/*.log`, and whose container
    parser explicitly selects Docker's `json-file` format.
  - Mark only `api` and `r-service` with `co.elastic.logs/enabled: "true"` and
    JSON-decoding hints. Do not add the label to `web`, `player`, or Filebeat.
    The label allowlist is the collection boundary; do not rely on service-name
    patterns or collect every container by default.
  - Decode the JSON application line held in Filebeat's `message` field into
    the root event while retaining Filebeat and Docker metadata. Preserve the
    original `message` on a decode failure and add parser-error metadata rather
    than silently discarding a line.
  - Keep Filebeat's registry beneath `${path.data}` and persist that directory
    on the host. It records file identity and offsets, preventing replay after
    a collector restart and allowing Docker's rotated source files to be
    consumed correctly.
  - Configure `output.file` with compact JSON (`pretty: false`), an archive
    directory supplied by Compose, 25 MB `rotate_every_kb`, 20
    `number_of_files`, `0640` output permissions, and rotation on startup.
    This produces bounded `*.ndjson` archives of at most approximately 500 MB.

- Pin the Filebeat image in `compose.yaml` to one reviewed Elastic Stack
  release and immutable digest from `docker.elastic.co/beats/filebeat`; never
  use `latest`. Record the selected version and digest beside the image so a
  later Elasticsearch deployment can deliberately use a compatible Stack
  version.

### Compose and runtime configuration

- Add a `filebeat` service to `compose.yaml`.
  - Run the official image as root because Docker's log directory and socket
    normally require it. Use the documented `filebeat -e --strict.perms=false`
    invocation because the repository-mounted config is intentionally
    read-only. This root identity is restricted to the collector container; it
    does not change application-container users.
  - Mount `observability/filebeat.yml` read-only at
    `/usr/share/filebeat/filebeat.yml`, `/var/lib/docker/containers` read-only,
    and the Docker socket at `/var/run/docker.sock`. Mount host archive and
    registry directories writable at the configured Filebeat output and data
    paths.
  - Keep the collector off every application network and publish no ports. It
    needs only Docker's local Unix socket and local filesystem mounts.
  - Apply `restart: unless-stopped`, `init`, read-only root filesystem,
    `no-new-privileges`, dropped capabilities, a bounded PID limit, and a small
    writable `/tmp` mount. Configure Filebeat's own Docker `json-file`
    rotation; its output is not recursively collected.
  - Preserve the existing 5 × 10 MB Docker `json-file` rotation on every
    existing service. Filebeat supplements it; it does not replace it or write
    files inside the application containers.

- Add documented Compose variables in `.env.example`:

  ```dotenv
  OBSERVABILITY_ARCHIVE_DIR=./.runtime/observability/archive
  OBSERVABILITY_REGISTRY_DIR=./.runtime/observability/registry
  ```

  Use those ignored relative paths for local development. The deployment VM
  overrides them in its existing protected `.env` with absolute directories
  outside the Git checkout:

  ```dotenv
  OBSERVABILITY_ARCHIVE_DIR=/var/log/opiraja/filebeat
  OBSERVABILITY_REGISTRY_DIR=/var/lib/opiraja/filebeat
  ```

- Extend the README/deployment runbook with archive inspection commands for
  failures, slow requests, and correlated API/R events by `request_id`. State
  that the archive is an operational interface, not a public API, and that its
  retention is size-based rather than a guaranteed number of days.

- Keep application code, the versioned API/R log schema, and Nginx formats
  unchanged. A later Elasticsearch slice changes Filebeat's `output.file` to
  an Elasticsearch output while retaining discovery, labels, parsing, and the
  archived event shape.

## VM Preparation and Deployment

### Prerequisites and installation

- Do not install Filebeat as an Ubuntu package or service. Docker Engine and
  Docker Compose are already deployment prerequisites; Filebeat runs from the
  official image and must be pulled from Elastic's registry during deployment.
- Ensure the VM has outbound access to `docker.elastic.co` for the initial
  image pull, or preload the reviewed image through the approved offline image
  process. Record the pulled image digest with the deployment evidence.
- `jq` is optional but recommended for operator inspection. Install it from
  the VM's normal Ubuntu repository if it is absent; this does not install or
  configure an additional log service.
- Before enabling Compose, create a dedicated group and persistent directories.
  Substitute the actual non-root deployment operator for `DEPLOY_OPERATOR`:

  ```sh
  sudo groupadd --system opiraja-logs
  sudo install -d -o root -g opiraja-logs -m 2770 /var/log/opiraja/filebeat
  sudo install -d -o root -g root -m 0700 /var/lib/opiraja/filebeat
  sudo usermod -aG opiraja-logs DEPLOY_OPERATOR
  ```

  The setgid archive directory causes Filebeat-created `0640` files to retain
  the `opiraja-logs` group. The registry stays root-only because it controls
  ingestion state. The operator must start a new login session after group
  membership changes.

### Privileged-access review

- Treat the Docker socket mount as host-root-equivalent access. A `:ro` bind
  mount does not make Docker's Unix-socket API read-only. Approve this access
  explicitly, mount it only into Filebeat, and keep it absent from `web`,
  `player`, `api`, and `r-service`.
- Confirm the collector has no published ports, no Compose network attachment,
  no `.env` secrets beyond archive/registry paths, and no access to certificate
  or host-Nginx key directories. It must never read request bodies, credentials,
  or the application's `.env` file.
- Keep `/var/log/opiraja/filebeat` and `/var/lib/opiraja/filebeat` on a
  filesystem monitored by the existing VM disk/inode checks. Add the 500 MB
  archive budget to the VM's operational capacity baseline.

### Deployment, verification, and rollback

1. On the VM, review the exact repository commit and confirm the working tree
   is clean. Add the two absolute observability paths to the protected `.env`;
   keep its existing owner and mode `0600`.
2. Create the group/directories above, verify free space and inode capacity,
   pull the pinned Filebeat image, and run `docker compose config --quiet`.
   Run Filebeat's `test config` command against the repository configuration
   before starting the service.
3. Deploy with the normal Compose update procedure. Confirm `filebeat`, `api`,
   and `r-service` are running; neither a listener nor a Docker-published port
   may be added.
4. Produce a controlled API request that calls R. Using the archive directory,
   verify one parseable event from each service contains the same `request_id`,
   and verify `service`, `event`, `status`, and `duration_ms` remain usable as
   JSON fields. Record only sanitized field values and counts in deployment
   evidence.
5. Restart Filebeat once and verify the registry prevents duplicate archived
   events. Review Filebeat's own Docker logs for permission, discovery, or
   parsing failures; do not copy raw application log lines into Git evidence.
6. If collection causes a failure or needs to be withdrawn, stop and remove
   only the Filebeat service, retain the existing application services and
   Docker log rotation, and preserve the archive/registry directories for
   diagnosis. Restoring the prior Compose revision removes the collector
   without altering Supabase state, application data, host Nginx, or ingress.

## Test Plan

- Repository checks:
  - Run `docker compose config --quiet` and Filebeat `test config` with the
    same mounted configuration/paths used by Compose.
  - Verify the pinned image reference, `api`/`r-service` labels, all four
    existing service log-rotation settings, and Filebeat's own rotation through
    rendered Compose inspection.
  - Confirm `.runtime/` is ignored and that no archive, registry, image digest
    cache, Docker socket, or VM-specific path enters Git.

- Docker-enabled integration checks:
  - Generate a correlated API-to-R request and verify archive NDJSON contains
    one parseable event for each service with the same `request_id`, expected
    application fields, and Docker metadata.
  - Inject a controlled non-JSON source line into a dedicated test container
    carrying the collection label; assert it remains archived with parse-error
    metadata. Do not alter the production API/R logging contract to perform
    this test.
  - Restart Filebeat, then verify its persistent registry prevents duplication.
    Exercise source/output rotation and verify no more than 20 archive files
    remain.
  - Confirm archive files are `root:opiraja-logs`/`0640` on the VM and readable
    by the designated operator group but not by an unprivileged account.

- Security and regression checks:
  - Confirm Filebeat exposes no host port and joins no application network.
  - Confirm `web` and `player` events are absent, Filebeat does not collect its
    own output, and only Filebeat mounts Docker's socket/container-log path.
  - Re-run the normal API/R smoke tests and confirm existing `docker compose
    logs` inspection remains available. Check that the archive contains no
    redaction sentinel values from the existing logging tests.

## Assumptions

- The deployment VM runs Docker Engine using the existing `json-file` log
  driver and exposes its standard `/var/lib/docker/containers` path.
- Approximately 500 MB of bounded API/R archive retention is acceptable;
  historical retention beyond that belongs in the later Elasticsearch phase.
- The VM administrator can create the dedicated host directories and
  operator-readable group, approve the privileged Docker-socket mount, and
  provide initial outbound registry access or an approved image preload.

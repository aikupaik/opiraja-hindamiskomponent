# API/R Structured-Log Archive Runbook

`filebeat` is a Compose-only collector. It reads Docker `json-file` records for
the labelled `api` and `r-service` containers, decodes each application JSON
event into NDJSON, and keeps its read-offset registry outside the repository.
The archive is an operational interface, not a public API. Its retention is
size-based: 20 files of approximately 25 MB, not a guaranteed number of days.

## VM preparation

Do not install Filebeat as an Ubuntu package or service. The collector is the
pinned official container image referenced in `compose.yaml`. Ensure the VM can
pull from `docker.elastic.co`, or preload that exact digest through the approved
offline image process. Record the pulled digest in deployment evidence.

Set these protected absolute paths in the VM's existing `.env` (do not print the
file; preserve its owner and `0600` mode):

```dotenv
OBSERVABILITY_ARCHIVE_DIR=/var/log/opiraja/filebeat
OBSERVABILITY_REGISTRY_DIR=/var/lib/opiraja/filebeat
```

Before enabling the collector, have the VM administrator explicitly approve the
Docker socket mount as host-root-equivalent access. A read-only bind mount does
not make the Docker Unix-socket API read-only. Create the archive operator group
and storage, replacing `DEPLOY_OPERATOR` with the non-root deployment operator:

```sh
sudo groupadd --system opiraja-logs
sudo install -d -o root -g opiraja-logs -m 2770 /var/log/opiraja/filebeat
sudo install -d -o root -g root -m 0700 /var/lib/opiraja/filebeat
sudo usermod -aG opiraja-logs DEPLOY_OPERATOR
```

The operator must start a new login session after the group change. Keep both
filesystems within existing disk and inode monitoring and include the 500 MB
archive budget in the VM capacity baseline. `jq` is optional but recommended;
install it from the normal Ubuntu repository if it is absent.

## Deploy and verify

From the repository root on the VM, first inspect the exact revision and avoid
printing rendered Compose configuration because it contains environment values:

```sh
git status --short
git rev-parse HEAD
docker compose config --quiet
docker compose pull filebeat
# `compose run` replaces the service command, so repeat strict.perms here for
# the intentionally read-only repository-mounted configuration.
docker compose run --rm --no-deps filebeat filebeat --strict.perms=false test config -c /usr/share/filebeat/filebeat.yml
docker compose up -d
docker compose ps
```

Confirm `filebeat`, `api`, and `r-service` are running. Filebeat must have no
published port and `network_mode: none`; no application service may mount the
Docker socket or `/var/lib/docker/containers`. The `web`, `player`, and
Filebeat containers must not have `co.elastic.logs/enabled=true`. Existing
application `json-file` rotation remains five 10 MB files per service.

Make a controlled API request that invokes R, then inspect only sanitized output
and counts. Set the archive location once for the following commands:

```sh
ARCHIVE_DIR=/var/log/opiraja/filebeat
```

The following `jq` workflow works directly with the NDJSON stream. It is for
operator diagnosis, not an application interface. Do not paste raw output into
Git, tickets, or deployment evidence.

```sh
# Archive files, size, modification time, and permissions. Expect at most 20
# files and root:opiraja-logs with mode 0640 on the VM.
find "$ARCHIVE_DIR" -maxdepth 1 -type f -name 'api-r*' -printf '%TY-%Tm-%Td %TH:%TM %10s %m %u:%g %f\n' | sort
find "$ARCHIVE_DIR" -maxdepth 1 -type f -name 'api-r*' | wc -l

# Verify each NDJSON line parses to an object; malformed input makes jq fail.
jq -n 'reduce inputs as $event (true; . and ($event | type == "object"))' "$ARCHIVE_DIR"/api-r*

# Event volumes grouped by service and event name.
jq -r '[(.service // "unknown"), (.event // "unknown")] | @tsv' "$ARCHIVE_DIR"/api-r* | sort | uniq -c | sort -nr

# HTTP-status distribution for events that have a status field.
jq -r 'select(.status? != null) | [(.service // "unknown"), .status] | @tsv' "$ARCHIVE_DIR"/api-r* | sort | uniq -c | sort -nr

# Server failures, reduced to useful and normally safe correlation fields.
jq -c 'select((.status? // 0) >= 500) | {timestamp, service, event, request_id, status, duration_ms, error_type}' "$ARCHIVE_DIR"/api-r*

# Slow events (example threshold: 1,000 ms).
jq -c --argjson minimum_ms 1000 'select((.duration_ms? // 0) >= $minimum_ms) | {timestamp, service, event, request_id, status, duration_ms}' "$ARCHIVE_DIR"/api-r*

# Every API/R event for one controlled request. Substitute a real request ID;
# do not place production IDs in command history or shared evidence.
jq -c --arg request_id 'REDACTED_REQUEST_ID' 'select(.request_id == $request_id) | {timestamp, service, event, status, duration_ms, level}' "$ARCHIVE_DIR"/api-r*

# Events at or after an ISO-8601 UTC timestamp. Application timestamps sort
# lexicographically in this format, so no date conversion is required.
jq -c --arg since '2026-01-01T00:00:00Z' 'select((.timestamp // "") >= $since) | {timestamp, service, event, request_id, status, duration_ms}' "$ARCHIVE_DIR"/api-r*

# Count JSON-decoding/parser errors without printing the retained original
# message. Investigate the source locally only after confirming it is safe.
jq -n 'reduce inputs as $event (0; if ($event.error.type? == "json" or (($event.error.message? // "") | test("json"; "i"))) then . + 1 else . end)' "$ARCHIVE_DIR"/api-r*
```

For the controlled request, verify one parseable event from each service shares
the request ID and has usable `service`, `event`, `status`, and `duration_ms`
JSON fields, as applicable to its event type. A non-JSON source line must remain
archived as its original `message` with Filebeat parser-error metadata.

Restart only Filebeat once, then verify that the persistent registry prevents
duplicate events and review `docker compose logs filebeat` for discovery,
permission, or parsing failures. Exercise source and output rotation; no more
than 20 archive files should remain. On the VM, archive files must be
`root:opiraja-logs` and `0640`, readable by the designated group but not an
unprivileged account. Do not copy raw log lines, credentials, request bodies, or
the VM `.env` into Git or deployment evidence.

## Rollback

If collection fails or must be withdrawn, stop and remove only the collector:

```sh
docker compose stop filebeat
docker compose rm -f filebeat
```

Keep the archive and registry directories for diagnosis. Restoring the previous
Compose revision removes Filebeat without changing the application services,
their Docker rotation, Supabase state, application data, host Nginx, or ingress.

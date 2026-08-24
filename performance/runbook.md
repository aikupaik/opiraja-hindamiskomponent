# Performance-test runbook

## Scope and safety boundary

Use this harness only in the scheduled pre-launch maintenance window, with no
real students or unrelated administrative work active. The public-load
generator is a separate approved machine. k6 never creates, stores, prints, or
cleans up credentials.

## Before a run

1. Complete the plan's preflight record: deployed commit and image digests, VM
   resources, non-secret timeout/pool settings, Supabase tier/region/limits,
   idle baseline, approved source IP, backups, clock synchronization, log
   capacity, and dependency health.
2. Obtain short-lived OR credentials outside k6 and provide them only through
   protected environment input.
3. For public HTTPS tests, record and approve the self-signed certificate
   fingerprint before allowing the narrowly scoped k6 verification exception.
4. Prepare a unique `perf-<timestamp>-<random>` run ID, run-owned data, and a
   results directory. Do not reuse a prior run ID.
5. Start monitoring and log streaming before any traffic. Record five-second
   VM/container and Supabase samples.
6. Smoke-test the selected scenario with one user before creating volume.

## Component-test overlay

On the pilot VM only, the overlay is used with the root Compose file:

```sh
docker compose -f compose.yaml -f performance/compose.loopback.yaml up -d
```

It publishes API and R only as `127.0.0.1:18000` and `127.0.0.1:18001` by
default. A remote generator reaches them through SSH tunnels; it must not
receive a direct public component port. After the run, stop the overlay and
verify no loopback listeners remain.

## Abort immediately when

- any integrity check fails;
- readiness fails twice consecutively;
- a container restarts or OOMs;
- unexpected failures exceed 5% for 30 seconds;
- p99 exceeds 10 seconds for two minutes;
- VM or Supabase CPU exceeds 90% for two minutes;
- memory or connections exceed 90%; or
- swap growth, I/O exhaustion, or quota alarms appear.

Export evidence before cleanup. Cleanup is a later explicit operation: it
first previews exact matching rows and identifiers, refuses non-performance
markers, deletes in dependency-safe order after confirmation, and verifies no
run-owned rows remain.

## First static edge smoke test

1. Create a results directory.

From repository root:

```sh
RUN_ID="smoke-$(date +%Y%m%dT%H%M%S)"
mkdir -p "performance/results/$RUN_ID"
```
2. Run the k6 script.
From repository root:
```sh
docker run --rm \
    -e PERF_BASE_URL="https://193.40.157.124" \
    -e K6_SUMMARY_EXPORT="/results/summary.json" \
    -v "$PWD/performance/k6:/scripts:ro" \
    -v "$PWD/performance/results/$RUN_ID:/results" \
    grafana/k6:1.5.0 \
    run --insecure-skip-tls-verify /scripts/static-edge-smoke.js
```

## Static-edge HTML and asset scenario

Run this only after the one-request smoke test succeeds and the observed
certificate fingerprint matches the approved pilot fingerprint. It requests
the public admin shell (`/`) and player shell (`/test/perf-static-edge`), then
discovers their currently deployed hashed JavaScript and CSS files from the
HTML and requests them. It sends no API request and does not execute browser
JavaScript, so it cannot create a session or assessment data.

Start with exactly one virtual user and one page-load iteration per virtual
user. The `per-vu-iterations` executor makes that exact: each configured VU
runs once.

```sh
PERF_EDGE_VUS=1
RUN_ID="static-edge-${PERF_EDGE_VUS}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "performance/results/$RUN_ID"

docker run --rm \
    -e PERF_BASE_URL="https://193.40.157.124" \
    -e PERF_EDGE_VUS="$PERF_EDGE_VUS" \
    -e K6_SUMMARY_EXPORT="/results/summary.json" \
    -v "$PWD/performance/k6:/scripts:ro" \
    -v "$PWD/performance/results/$RUN_ID:/results" \
    grafana/k6:1.5.0 \
    run --insecure-skip-tls-verify --out json=/results/raw-k6.json /scripts/static-edge.js
```

Pass criteria for this first run:

- every k6 check passes and both `checks: rate==1` and
  `http_req_failed: rate==0` thresholds pass;
- the admin and player HTML responses are `200` and include `X-Request-ID`;
- both pages discover and fetch at least one JavaScript and one CSS asset;
- asset responses are `200`, have a content type, and advertise immutable
  cache control; and
- no VM/container readiness loss, restart, OOM, Nginx `429`/`5xx`, or resource
  alarm appears while collecting the five-second VM and Supabase samples.

Do not advance to 25 or 100 clients until the still-open preflight items are
resolved: backup confirmation; a Supabase observation covering API/database
latency and error counts; and explanation or a repeat of the idle R CPU spike.
After that clearance, repeat the same command with
`PERF_EDGE_VUS=25`, then `PERF_EDGE_VUS=100`, using a new `RUN_ID` and fresh
monitoring evidence for every level. Keep the public Nginx limits enabled; a
`429` is an edge-policy result to report, not a reason to weaken the limit.

## VM monitoring and log evidence

For every public run, create one result directory with a level-specific run ID
on both machines, for example `static-edge-100-20260824T120000Z`. Start this
monitor on the pilot VM in one terminal **before** starting k6. It writes only
under ignored `performance/results/<run-id>/vm/`; stop it with Ctrl-C after
k6 has finished.

```sh
RUN_ID="static-edge-100-$(date -u +%Y%m%dT%H%M%SZ)"
bash performance/bin/monitor-vm.sh "$RUN_ID"
```

The monitor records five-second host/container samples in
`vm/host-samples.log`, pre/post Compose state, and three live evidence streams:

- `vm/compose-live.log`: API, R, player, and web container logs;
- `vm/host-nginx-live.log`: public-edge access and error logs; and
- `vm/docker-events.log`: container deaths, restarts, and OOM-related events.

Before sharing evidence, verify that logs contain no credentials. Do not commit
raw result files. Correlate a static-edge run by UTC timestamps and request
path; future stateful scenarios additionally use their run/scenario/VU request
ID convention.

During the run, stop immediately for an integrity error, two consecutive
readiness failures, a restart/OOM event, `429`/unexpected `5xx` above the
abort rule, p99 above 10 seconds for two minutes, CPU above 90% for two
minutes, memory/connections above 90%, swap growth, or disk/quota alarms.

## Supabase evidence

Open the pilot project dashboard before starting k6, use the same UTC start/end
range as the VM evidence, and capture the closest available one-minute samples.
Supabase infrastructure metrics refresh on one-minute intervals, so do not
claim five-second Supabase precision.

Record or export screenshots for:

- Database Reports: CPU (including iowait if exposed), RAM, swap, disk IOPS and
  bytes/throughput, disk-I/O budget/consumption, and database size/disk use.
- Database connections: total active connections, connection breakdown
  (Postgres/PostgREST/pooler where available), and the plan's maximum. Record
  both the peak count and percentage of the limit.
- API Reports or Logs Explorer: request count, 4xx/5xx count, API response
  latency, database/origin latency, and the slowest PostgREST (`/rest/v1`)
  routes or queries. Record query shape/timing only—never result rows or
  credentials.
- Query-performance diagnostics, if enabled for the tier: top slow statements,
  mean/max execution time, calls, and any lock/connection wait evidence. If a
  dashboard feature is unavailable on Nano, record it as unavailable rather
  than leaving the field blank.

For static-edge tests, Supabase should remain near its idle baseline because no
API route is called. A material Supabase change is therefore evidence to
investigate, not static-edge capacity. For every subsequent API/stateful test,
record the peak and time of each metric, then compare them to the plan's
thresholds: sustained CPU below 70%, connections below 80%, and no memory,
swap, I/O, or error exhaustion. The abort boundary remains 90% for CPU,
memory, or connections as stated above.

## Generator evidence

Record the exact generator configuration alongside each run before invoking
k6. The raw k6 output contains tagged, timestamped request points; the summary
contains global and per-route (`admin`/`player`, `html`/`js`/`css`) p50 (shown
as `med`), p90, p95, p99, and maximum request-duration submetrics.

```sh
{
  printf 'run_id=%s\n' "$RUN_ID"
  printf 'started_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'base_url=%s\n' "https://193.40.157.124"
  printf 'edge_vus=%s\n' "$PERF_EDGE_VUS"
  printf 'script_sha256=%s\n' "$(shasum -a 256 performance/k6/static-edge.js | awk '{print $1}')"
  docker image inspect grafana/k6:1.5.0 --format 'k6_image={{index .RepoDigests 0}}'
} > "performance/results/$RUN_ID/run-metadata.txt"
```

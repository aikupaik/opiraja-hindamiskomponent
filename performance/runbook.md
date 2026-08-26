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
verify no loopback listeners remain. The overlay also gives R a temporary
gateway-capable network attachment: Docker cannot publish a port for a
container attached only to the root configuration's internal `compute`
network. Re-applying the root configuration removes that attachment.

## R-only v2 component test

The R-only script sends the stateful v2 `model` -> `select` -> `advance` flow.
It uses each live response to construct the next request and checks all three
responses against the selected committed fixture. One k6 iteration is one
complete three-request flow. No credentials, pilot data, database access, YG,
or cleanup are involved.

### Prepare the endpoint and tunnel

The commands below use three terminals:

- **Pilot VM terminal:** the deployed repository and Docker Compose commands.
- **Generator tunnel terminal:** the SSH local-forward, left running during
  k6.
- **Generator k6 terminal:** the k6 commands and result files.

The tunnel may use the pilot VM's normal SSH address or its private VPN
address. The R port itself remains bound to pilot-VM loopback; do not replace
the loopback bind with the VPN address.

1. Before the maintenance window, verify that the fixtures still reproduce
   exactly from the production R implementation:

**Pilot VM terminal** (from the deployed repository root):

```sh
cd /path/to/opiraja-hindamiskomponent
Rscript performance/fixtures/r/generate.R --check
```

2. Start the component overlay on the pilot VM. Force recreation so Docker
   applies the temporary port publication even when the normal Compose stack
   is already running:

**Pilot VM terminal:**

```sh
cd /path/to/opiraja-hindamiskomponent
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  up -d --force-recreate --wait --wait-timeout 120 r-service
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  ps --format json r-service
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  port r-service 8000
```

The JSON output must show `Health` as `healthy` and `Publishers` must include
the selected host port with `URL` set to `127.0.0.1`. The `port` command must
then report `127.0.0.1:18001` (or the explicitly selected
`PERF_R_LOOPBACK_PORT`). Do not continue if either check disagrees. With
Compose v5, `invalid IP:0` from `port` means the requested binding was not
actually published; it is not an alternate address. Inspect the merged model
and actual container state:

```sh
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  config r-service
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  ps --format json r-service
```

If the service is not healthy, stop here and inspect the Compose logs:

```sh
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  logs --tail=100 r-service
```

3. Confirm on the VM that R is published only on loopback and that the health
endpoint works:

**Pilot VM terminal:**

```sh
ss -ltn '( sport = :18001 )'
curl --fail --silent --show-error http://127.0.0.1:18001/health
```

The listener must be `127.0.0.1:18001`, never `0.0.0.0:18001` or the VM's
public address. The health response should be `{"status":"ok"}`.

4. On the remote load generator, open an SSH local-forward and leave it
   running in a dedicated terminal. Use the pilot VM's VPN address in
   `PILOT_SSH_HOST` when SSH is expected to travel through the VPN:

**Generator tunnel terminal:**

```sh
PILOT_SSH_HOST="<ssh-user>@<pilot-vm-vpn-address-or-hostname>"
ssh -N -T \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18001:127.0.0.1:18001 \
  "$PILOT_SSH_HOST"
```

If the local port is already in use, select another generator-side port and
use the same port in both the `-L` option and `PERF_R_BASE_URL`. For example,
with local port `28001`:

```sh
ssh -N -T \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:28001:127.0.0.1:18001 \
  "$PILOT_SSH_HOST"
```

5. From a second load-generator terminal, verify the exact tunneled target:

**Generator k6 terminal:**

```sh
curl --fail --silent --show-error http://127.0.0.1:18001/health
```

The expected response is `{"status":"ok"}`. The Docker commands below use
host networking so the k6 container can reach the generator's loopback-only
SSH tunnel. Run them on a Linux load generator; a native k6 1.5.x binary may be
used instead where Docker host networking is unavailable. Confirm the k6
image is available and that the generator has Docker host-network support:

```sh
docker pull grafana/k6:1.5.0
docker version
```

Run all generator commands below from a checkout containing `performance/`:

```sh
cd /path/to/opiraja-hindamiskomponent
```

### Smoke-test every graph shape

Run this once for each `PERF_R_SHAPE`: `3-chain`, `10-chain`, and
`10-independent`. Use a new run ID and result directory each time.

**Generator k6 terminal:**

```sh
PERF_R_SHAPE="3-chain"
RUN_ID="perf-r-smoke-${PERF_R_SHAPE}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "performance/results/$RUN_ID"

docker run --rm --network host \
    -e PERF_R_BASE_URL="http://127.0.0.1:18001" \
    -e PERF_RUN_ID="$RUN_ID" \
    -e PERF_R_SHAPE="$PERF_R_SHAPE" \
    -e PERF_R_LOAD_MODE="smoke" \
    -e K6_SUMMARY_EXPORT="/results/summary.json" \
    -v "$PWD/performance/k6:/scripts:ro" \
    -v "$PWD/performance/fixtures:/fixtures:ro" \
    -v "$PWD/performance/results/$RUN_ID:/results" \
    grafana/k6:1.5.0 \
    run --out json=/results/raw-k6.json /scripts/r-only.js
```

Do not start volume unless all checks and thresholds pass for all three
fixtures.

### Run the closed-VU concurrency plateaus

For each graph shape, run separate plateaus at 1, 2, 4, 8, and 16 VUs. Start
VM monitoring and log streaming with the exact same `RUN_ID` before starting
k6. Change only one load level at a time, preserve each result directory, and
allow resources to return to baseline between runs.

**Generator k6 terminal:** create and print the run ID:

```sh
PERF_R_SHAPE="3-chain"
PERF_R_VUS=1
PERF_R_DURATION="10m"
RUN_ID="perf-r-${PERF_R_SHAPE}-closed-vu${PERF_R_VUS}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "performance/results/$RUN_ID"
echo "$RUN_ID"
```

On the pilot VM, start monitoring with that printed ID. Run this from the
deployed repository root and leave it running until k6 finishes.

**Pilot VM monitoring terminal:**

```sh
RUN_ID="<run_id>"
sudo bash performance/bin/monitor-vm.sh "$RUN_ID"
```

On the load generator, run the plateau from the repository root.

**Generator k6 terminal:**

```sh
docker run --rm --network host \
    -e PERF_R_BASE_URL="http://127.0.0.1:18001" \
    -e PERF_RUN_ID="$RUN_ID" \
    -e PERF_R_SHAPE="$PERF_R_SHAPE" \
    -e PERF_R_LOAD_MODE="closed" \
    -e PERF_R_VUS="$PERF_R_VUS" \
    -e PERF_R_DURATION="$PERF_R_DURATION" \
    -e K6_SUMMARY_EXPORT="/results/summary.json" \
    -v "$PWD/performance/k6:/scripts:ro" \
    -v "$PWD/performance/fixtures:/fixtures:ro" \
    -v "$PWD/performance/results/$RUN_ID:/results" \
    grafana/k6:1.5.0 \
    run --out json=/results/raw-k6.json /scripts/r-only.js
```

The script reports per-operation and full-flow timings. It aborts on any
successful-but-invalid response, after the configured HTTP failure or latency
abort boundary is crossed, and fails the run on dropped iterations,
unexpected HTTP failures at or above 1%, or the plan's p95/p99 latency limits.
Checks remain visible by operation; successful HTTP responses that fail a
contract check are integrity failures and always fail the run.

### Measure the open arrival-rate ceiling

Only after the closed-VU matrix, use `open` mode to show whether slower R
responses cause the generator to miss a fixed incoming rate. `PERF_R_RATE` is
complete three-request flows per second, so the approximate request rate is
three times that value. Choose the initial rate and VU allocation from the
closed-test throughput instead of guessing a high starting load.

**Generator k6 terminal:** create and print the run ID:

```sh
PERF_R_SHAPE="3-chain"
PERF_R_RATE=1
PERF_R_PRE_ALLOCATED_VUS=2
PERF_R_MAX_VUS=16
PERF_R_DURATION="10m"
RUN_ID="perf-r-${PERF_R_SHAPE}-open-rate${PERF_R_RATE}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "performance/results/$RUN_ID"
echo "$RUN_ID"
```

Run the open arrival-rate test from the generator k6 terminal:

```sh
docker run --rm --network host \
    -e PERF_R_BASE_URL="http://127.0.0.1:18001" \
    -e PERF_RUN_ID="$RUN_ID" \
    -e PERF_R_SHAPE="$PERF_R_SHAPE" \
    -e PERF_R_LOAD_MODE="open" \
    -e PERF_R_RATE="$PERF_R_RATE" \
    -e PERF_R_PRE_ALLOCATED_VUS="$PERF_R_PRE_ALLOCATED_VUS" \
    -e PERF_R_MAX_VUS="$PERF_R_MAX_VUS" \
    -e PERF_R_DURATION="$PERF_R_DURATION" \
    -e K6_SUMMARY_EXPORT="/results/summary.json" \
    -v "$PWD/performance/k6:/scripts:ro" \
    -v "$PWD/performance/fixtures:/fixtures:ro" \
    -v "$PWD/performance/results/$RUN_ID:/results" \
    grafana/k6:1.5.0 \
    run --out json=/results/raw-k6.json /scripts/r-only.js
```

After every run, retain `summary.json`, `raw-k6.json`, VM samples, and streamed
R/container logs. Confirm `r_completed_flows`, the `r_model_requests`,
`r_select_requests`, and `r_advance_requests` counts/rates, per-operation
p50/p90/p95/p99 and max latency, `r_flow_duration`, failure classifications,
VUs, throughput, and `dropped_iterations` in the report. Apply the runbook's
abort rules and do not continue to the next level after an abort until the
cause is understood.

### Remove component exposure

When the R-only stage is complete, stop k6 and the VM monitoring process, then
stop the SSH tunnel with `Ctrl-C` in the tunnel terminal. On the pilot VM,
re-apply the root Compose configuration without the overlay so API and R are
recreated without published component ports:

**Pilot VM terminal:**

```sh
cd /path/to/opiraja-hindamiskomponent
docker compose -f compose.yaml up -d --force-recreate api r-service
```

Verify that neither loopback port remains and that the normal deployment is
healthy before leaving the maintenance window:

```sh
ss -ltn '( sport = :18000 or sport = :18001 )'
docker compose -f compose.yaml ps
docker compose -f compose.yaml exec -T api python -c \
  'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=3).read()'
docker compose -f compose.yaml logs --tail=50 api r-service
```

The `ss` command must show no listeners on ports `18000` or `18001`. The
in-container readiness request must succeed and both services must be healthy.

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

## Real Static Edge test

1. Create a results directory.

From repistory root:
```sh
PERF_EDGE_VUS=25
RUN_ID="static-edge-${PERF_EDGE_VUS}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "performance/results/$RUN_ID"
echo "$RUN_ID"
```

2. Start monitoring from the VM.

Use the exact same RUN_ID:
```sh
RUN_ID="<run_id>"
sudo bash performance/bin/monitor-vm.sh "$RUN_ID"
```

3. Run the script from the laptop.

```sh
docker run --rm \
      -e PERF_BASE_URL="https://193.40.157.124" \
      -e PERF_EDGE_VUS="$PERF_EDGE_VUS" \
      -e PERF_RUN_ID="$RUN_ID" \
      -e K6_SUMMARY_EXPORT="/results/summary.json" \
      -v "$PWD/performance/k6:/scripts:ro" \
      -v "$PWD/performance/results/$RUN_ID:/results" \
      grafana/k6:1.5.0 \
      run \
      --insecure-skip-tls-verify \
      --out json=/results/raw-k6.json \
      /scripts/static-edge.js
```

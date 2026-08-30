# Performance-test runbook

## Scope and safety boundary

Use this harness only in the scheduled pre-launch maintenance window, with no
real students or unrelated administrative work active. The public-load
generator is a separate approved machine. k6 never creates, stores, prints, or
cleans up credentials.

## Before a run

1. Complete the plan's preflight record: deployed commit and image digests, VM
   resources, non-secret timeout/pool settings, Supabase tier/region/limits,
   generator hardware/runner/image digest, idle baseline, approved source IP,
   backups, clock synchronization, log capacity, and dependency health.
2. Obtain short-lived OR credentials outside k6 and provide them only through
   protected environment input.
3. For public HTTPS tests, record and approve the self-signed certificate
   fingerprint before allowing the narrowly scoped k6 verification exception.
4. Prepare a unique `perf-<timestamp>-<random>` run ID, run-owned data, and a
   results directory. Do not reuse a prior run ID.
5. Start monitoring and log streaming before any traffic. Record five-second
   generator, VM/container, and Supabase samples.
6. Smoke-test the selected scenario with one user before creating volume.

## Qualify and monitor the load generator

The generator must be a separate approved machine and must have enough
headroom that it does not become the measured bottleneck. Supported runners
are native k6 1.5.x, rootful Docker on Linux, and Docker Desktop for macOS 4.34
or newer. Use the pinned `grafana/k6:1.5.0` image for Docker runs.

For Docker Desktop on macOS:

1. Use Linux containers.
2. Enable **Settings > Resources > Network > Host networking**, then apply the
   change and restart Docker Desktop.
3. Leave Enhanced Container Isolation disabled. Docker Desktop host networking
   supports TCP and UDP, but not direct binding to host interface addresses;
   the R-only test needs only TCP access to the generator's loopback listener.
4. Keep the Mac connected to AC power, prevent sleep for the test window, and
   stop unrelated CPU-, memory-, disk-, and network-intensive work.

Record non-secret generator identity during preflight:

```sh
sw_vers
system_profiler SPHardwareDataType | awk -F': ' \
  '/Model Name|Model Identifier|Chip|Total Number of Cores|Memory/ {
    gsub(/^[[:space:]]+/, "", $1); print $1 "=" $2
  }'
df -h /
docker version
docker info --format \
  'os={{.OperatingSystem}} ostype={{.OSType}} architecture={{.Architecture}} cpus={{.NCPU}} memory_bytes={{.MemTotal}} kernel={{.KernelVersion}} security={{json .SecurityOptions}}'
docker image inspect grafana/k6:1.5.0 --format \
  'id={{.Id}} repo_digests={{json .RepoDigests}} architecture={{.Architecture}} os={{.Os}}'
```

The filtered `system_profiler` command deliberately omits serial numbers and
hardware UUIDs. Do not copy those identifiers into performance evidence.

Before each non-smoke run on macOS, create the run's generator evidence
directory and start this collector in a separate terminal. Leave it running
until k6 exits, then stop it with `Ctrl-C`:

```sh
RUN_ID="<run_id>"
RESULT_DIR="performance/results/$RUN_ID/generator"
mkdir -p "$RESULT_DIR"

while :; do
  {
    echo "--- time=$(date -u +%Y-%m-%dT%H:%M:%SZ) ---"
    top -l 1 -n 0 | sed -n '1,12p'
    vm_stat
    netstat -ibdn
    docker stats --no-stream \
      --format 'container={{.Name}} cpu={{.CPUPerc}} memory={{.MemUsage}} memory_pct={{.MemPerc}} net={{.NetIO}} block_io={{.BlockIO}} pids={{.PIDs}}'
  } >> "$RESULT_DIR/macos-generator-samples.txt"
  sleep 5
done
```

Treat the run as generator-limited and do not use it to claim pilot capacity
if the Mac or Docker VM exhausts CPU, memory, disk, or network headroom; k6
drops iterations; or generator-side receive time grows while the pilot remains
idle. Preserve the evidence, allow both machines to recover, and rerun the
entire comparison matrix on a more capable generator if needed. Never combine
plateaus produced by different generator environments into one capacity claim.

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
SSH tunnel. Use either rootful Docker on Linux or qualified Docker Desktop on
macOS as described above. A native k6 1.5.x binary may be used instead when
host networking is unavailable. Confirm the k6 image is available and record
the runner versions and immutable image digest:

```sh
docker pull grafana/k6:1.5.0
docker version
docker image inspect grafana/k6:1.5.0 --format \
  'id={{.Id}} repo_digests={{json .RepoDigests}} architecture={{.Architecture}} os={{.Os}}'
```

With the SSH tunnel still open, verify the same endpoint from the generator
host and from a host-networked container. Do not continue if only the host
request succeeds:

```sh
curl --fail --silent --show-error http://127.0.0.1:18001/health
docker run --rm --network host curlimages/curl:8.15.0 \
  --fail --silent --show-error http://127.0.0.1:18001/health
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
generator and VM monitoring plus log streaming with the exact same `RUN_ID`
before starting k6. Change only one load level at a time, preserve each result
directory, and allow resources to return to baseline between runs.

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

After every run, retain `summary.json`, `raw-k6.json`, generator and VM samples,
and streamed R/container logs. Confirm `r_completed_flows`, the `r_model_requests`,
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

## API-only component test

The API-only stage runs a derived performance image beside the normal stack.
It uses the production FastAPI routes, DTOs, JWT validation, middleware,
logging, and assessment service, but replaces Supabase and R with deterministic
in-process implementations. The service is not connected to the edge network,
is never reachable through Nginx, and is published only as pilot-VM loopback
port `18002`. One Uvicorn worker is used, matching the production command.

The `routes` workload repeatedly exercises liveness, authenticated OR status,
player start, and completed-answer replay using two setup-owned sessions. Its
state therefore remains bounded during a 10-minute plateau. The `session`
workload gives each VU one unique complete session, including an accepted-answer
replay and completed OR status check. Session mode is a bounded concurrency and
integrity test, not a sustained plateau.

The 3-chain fixture completes after seven answers. Both 10-node fixtures
complete after ten. Covered inventory is loaded in memory, so any YG order is
an integrity failure.

### Prepare the derived image on the pilot VM

Use the deployed checkout and confirm the normal API image is the image for the
recorded commit. Do not rebuild or retag it merely for this test. The derived
image adds only the performance app and committed fixtures.

**Pilot VM terminal:**

```sh
cd /path/to/opiraja-hindamiskomponent
git rev-parse HEAD
docker image inspect opiraja-assessment-api:local --format \
  'base_id={{.Id}} base_digests={{json .RepoDigests}} created={{.Created}} cmd={{json .Config.Cmd}}'

PERF_RUN_ID="perf-api-build-validation" \
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  --profile api-only config --no-env-resolution > /tmp/api-only-compose.yaml

PERF_RUN_ID="perf-api-build-validation" \
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  --profile api-only build api-perf

docker image inspect opiraja-assessment-api-perf:local --format \
  'derived_id={{.Id}} derived_digests={{json .RepoDigests}} created={{.Created}} cmd={{json .Config.Cmd}}'
```

`--no-env-resolution` is mandatory because an ordinary rendered Compose model
would copy secrets from `.env` into the output file. Inspect
`/tmp/api-only-compose.yaml` before proceeding. `api-perf` must have one
worker, no `depends_on`, only the `api-performance` network, and only a
`127.0.0.1:18002` publication. The normal `api`, `web`, `player`, and
`r-service` definitions are not replaced by `api-perf`.

### Prepare protected OR credentials

Obtain a dedicated OR JWT from the approved credential issuer immediately
before a run. It must contain the normal create/read/launch scopes, have an
`assessment-api` audience, use the configured issuer, and have between 15 and
20 minutes of remaining lifetime. The isolated service raises only its maximum
accepted OR lifetime to 20 minutes; the production API keeps its normal value.

On the generator, store the token in an environment file outside the checkout.
The file must contain exactly `PERF_OR_TOKEN=<token>`, be owned by the operator,
and have mode `0600`. Do not echo, print, commit, attach, or copy this file into
results. Supply it to Docker with `--env-file`, never with a command-line
`-e PERF_OR_TOKEN=...` value.

**Generator terminal:**

```sh
PERF_CREDENTIALS_FILE="/secure/path/api-only-k6.env"
test -f "$PERF_CREDENTIALS_FILE"
chmod 600 "$PERF_CREDENTIALS_FILE"
```

Destroy the credential file after the API-only window ends or the token
expires.

### Start one run-owned API-only service

Every smoke, plateau, open-rate, and session-burst run gets a fresh run ID,
container, and evidence directory. Set the workload and graph shape before
starting the container; those values are written into its shutdown evidence.

**Pilot VM terminal:**

```sh
cd /path/to/opiraja-hindamiskomponent
export PERF_API_WORKLOAD="routes"
export PERF_API_SHAPE="3-chain"
export PERF_RUN_ID="perf-api-${PERF_API_WORKLOAD}-${PERF_API_SHAPE}-smoke-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "performance/results/$PERF_RUN_ID/api-only"
echo "$PERF_RUN_ID"
git rev-parse HEAD > \
  "performance/results/$PERF_RUN_ID/api-only/deployed-commit.txt"
docker image inspect \
  opiraja-assessment-api:local opiraja-assessment-api-perf:local \
  --format \
  'tags={{json .RepoTags}} id={{.Id}} digests={{json .RepoDigests}} created={{.Created}} cmd={{json .Config.Cmd}}' \
  > "performance/results/$PERF_RUN_ID/api-only/image-lineage.txt"

docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  --profile api-only up -d --no-deps --force-recreate --wait \
  --wait-timeout 120 api-perf
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  --profile api-only ps --format json api-perf
ss -ltn '( sport = :18002 )'
curl --fail --silent --show-error http://127.0.0.1:18002/health/ready
```

The listener must be exactly `127.0.0.1:18002`; the readiness response must be
`{"status":"ready","dependencies":{"supabase":"ready","r":"ready"}}`.
These dependency labels describe the in-process seams, not real Supabase or R
traffic.

Start VM monitoring with the same printed run ID and leave it running until
the API-only container has been stopped gracefully after k6 exits.

**Pilot VM monitoring terminal:**

```sh
RUN_ID="<run_id>"
sudo bash performance/bin/monitor-vm.sh "$RUN_ID" api-only
```

### Open and verify the SSH tunnel

**Generator tunnel terminal:**

```sh
PILOT_SSH_HOST="<ssh-user>@<pilot-vm-vpn-address-or-hostname>"
ssh -N -T \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18002:127.0.0.1:18002 \
  "$PILOT_SSH_HOST"
```

With that terminal left open, verify the tunnel from both the generator host
and the host-networked runner environment.

**Generator k6 terminal:**

```sh
curl --fail --silent --show-error http://127.0.0.1:18002/health/ready
docker run --rm --network host curlimages/curl:8.15.0 \
  --fail --silent --show-error http://127.0.0.1:18002/health/ready
```

Do not continue if only the host request succeeds.

### Smoke-test both workloads and every graph shape

Run six independent smokes: `routes` and `session` for each of `3-chain`,
`10-chain`, and `10-independent`. Recreate `api-perf` with the matching run ID,
workload, and shape before every command.

**Generator k6 terminal:**

```sh
cd /path/to/opiraja-hindamiskomponent
RUN_ID="<run_id printed by the pilot VM>"
PERF_API_WORKLOAD="routes"
PERF_API_SHAPE="3-chain"
mkdir -p "performance/results/$RUN_ID"

docker run --rm --network host \
    --env-file "$PERF_CREDENTIALS_FILE" \
    -e PERF_API_BASE_URL="http://127.0.0.1:18002" \
    -e PERF_RUN_ID="$RUN_ID" \
    -e PERF_API_WORKLOAD="$PERF_API_WORKLOAD" \
    -e PERF_API_SHAPE="$PERF_API_SHAPE" \
    -e PERF_API_LOAD_MODE="smoke" \
    -e K6_SUMMARY_EXPORT="/results/summary.json" \
    -v "$PWD/performance/k6:/scripts:ro" \
    -v "$PWD/performance/fixtures:/fixtures:ro" \
    -v "$PWD/performance/results/$RUN_ID:/results" \
    grafana/k6:1.5.0 \
    run --out json=/results/raw-k6.json /scripts/api-only.js
```

All checks and thresholds must pass before volume. The setup requests create
the two bounded route fixtures and are tagged `phase=setup`; load thresholds
apply only to `phase=load`.

### Run closed route plateaus

Run each graph shape at 1, 25, and 100 closed VUs for ten minutes. Select the
limiting shape by the lowest passing level; break ties by highest p99 at 25 VUs
and then highest API-container CPU. Complete that shape's matrix at 5, 10, and
50 VUs. Recreate the API-only container and use a new run ID for every level.

**Generator k6 terminal:**

```sh
RUN_ID="<matching fresh run id>"
PERF_API_SHAPE="10-independent"
PERF_API_VUS=25
PERF_API_DURATION="10m"
mkdir -p "performance/results/$RUN_ID"

docker run --rm --network host \
    --env-file "$PERF_CREDENTIALS_FILE" \
    -e PERF_API_BASE_URL="http://127.0.0.1:18002" \
    -e PERF_RUN_ID="$RUN_ID" \
    -e PERF_API_WORKLOAD="routes" \
    -e PERF_API_SHAPE="$PERF_API_SHAPE" \
    -e PERF_API_LOAD_MODE="closed" \
    -e PERF_API_VUS="$PERF_API_VUS" \
    -e PERF_API_DURATION="$PERF_API_DURATION" \
    -e K6_SUMMARY_EXPORT="/results/summary.json" \
    -v "$PWD/performance/k6:/scripts:ro" \
    -v "$PWD/performance/fixtures:/fixtures:ro" \
    -v "$PWD/performance/results/$RUN_ID:/results" \
    grafana/k6:1.5.0 \
    run --out json=/results/raw-k6.json /scripts/api-only.js
```

If a level fails, repeat that exact level once and repeat the immediately lower
passing level before declaring a route-flow boundary. If 100 VUs passes, report
tested headroom of at least 100 closed VUs rather than claiming an exact VU
ceiling.

### Measure the open route-flow ceiling

For the limiting shape, let `T` be completed route flows/second at its highest
passing closed plateau. Run rates `floor(0.75*T)`, `floor(T)`, and
`ceil(1.25*T)`, with a minimum rate of one. Preallocate the highest passing
closed VU count and set the maximum to twice that count. If the highest rate
passes, increase by 25% until failure; if the lowest fails, decrease by 25%
until one passes. Repeat the first failing rate and the immediately lower
passing rate.

**Generator k6 terminal:**

```sh
RUN_ID="<matching fresh run id>"
PERF_API_SHAPE="<limiting shape>"
PERF_API_RATE="<calculated flows per second>"
PERF_API_PRE_ALLOCATED_VUS="<highest passing closed VUs>"
PERF_API_MAX_VUS="$((PERF_API_PRE_ALLOCATED_VUS * 2))"
PERF_API_DURATION="10m"
mkdir -p "performance/results/$RUN_ID"

docker run --rm --network host \
    --env-file "$PERF_CREDENTIALS_FILE" \
    -e PERF_API_BASE_URL="http://127.0.0.1:18002" \
    -e PERF_RUN_ID="$RUN_ID" \
    -e PERF_API_WORKLOAD="routes" \
    -e PERF_API_SHAPE="$PERF_API_SHAPE" \
    -e PERF_API_LOAD_MODE="open" \
    -e PERF_API_RATE="$PERF_API_RATE" \
    -e PERF_API_PRE_ALLOCATED_VUS="$PERF_API_PRE_ALLOCATED_VUS" \
    -e PERF_API_MAX_VUS="$PERF_API_MAX_VUS" \
    -e PERF_API_DURATION="$PERF_API_DURATION" \
    -e K6_SUMMARY_EXPORT="/results/summary.json" \
    -v "$PWD/performance/k6:/scripts:ro" \
    -v "$PWD/performance/fixtures:/fixtures:ro" \
    -v "$PWD/performance/results/$RUN_ID:/results" \
    grafana/k6:1.5.0 \
    run --out json=/results/raw-k6.json /scripts/api-only.js
```

One route flow is four HTTP requests. Any `dropped_iterations` means the
offered flow rate failed, even when completed-request latency remains low.

### Run bounded stateful session bursts

For every graph shape, run separate 1-, 25-, 50-, and 100-VU bursts. In this
mode `closed` means one complete iteration per VU, not a ten-minute loop. The
container must be configured with `PERF_API_WORKLOAD=session` before it starts.

**Generator k6 terminal:**

```sh
RUN_ID="<matching fresh run id>"
PERF_API_SHAPE="10-chain"
PERF_API_VUS=25
mkdir -p "performance/results/$RUN_ID"

docker run --rm --network host \
    --env-file "$PERF_CREDENTIALS_FILE" \
    -e PERF_API_BASE_URL="http://127.0.0.1:18002" \
    -e PERF_RUN_ID="$RUN_ID" \
    -e PERF_API_WORKLOAD="session" \
    -e PERF_API_SHAPE="$PERF_API_SHAPE" \
    -e PERF_API_LOAD_MODE="closed" \
    -e PERF_API_VUS="$PERF_API_VUS" \
    -e PERF_API_MAX_DURATION="10m" \
    -e K6_SUMMARY_EXPORT="/results/summary.json" \
    -v "$PWD/performance/k6:/scripts:ro" \
    -v "$PWD/performance/fixtures:/fixtures:ro" \
    -v "$PWD/performance/results/$RUN_ID:/results" \
    grafana/k6:1.5.0 \
    run --out json=/results/raw-k6.json /scripts/api-only.js
```

`api_completed_sessions` must equal the configured VUs. Every session creates,
starts, answers seven or ten times, replays the final accepted answer, and
checks completed OR status.

### Export and validate API-only evidence

After k6 exits, leave monitoring running and stop `api-perf` gracefully. The
lifespan shutdown writes aggregate state and event-loop evidence to the run's
VM result directory.

**Pilot VM terminal:**

```sh
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  --profile api-only stop -t 30 api-perf

STATE_FILE="performance/results/$PERF_RUN_ID/api-only/api-only-state.json"
test -s "$STATE_FILE"
jq . "$STATE_FILE"
jq -e '.yg_order_count == 0 and (.integrity_errors | length) == 0' "$STATE_FILE"
```

For `routes`, also require exactly two sessions, one active and one completed:

```sh
jq -e \
  '.session_count == 2 and .session_status_counts == {"active":1,"completed":1}' \
  "$STATE_FILE"
```

For `session`, require every VU to complete and the stored answer count to be
`VUs * 7` for 3-chain or `VUs * 10` for either 10-node shape:

```sh
EXPECTED_VUS="<VU count>"
EXPECTED_ANSWERS="<VU count multiplied by 7 or 10>"
jq -e --argjson vus "$EXPECTED_VUS" --argjson answers "$EXPECTED_ANSWERS" \
  '.session_count == $vus and
   .session_status_counts == {"completed":$vus} and
   .answer_count == $answers and
   .unique_submission_count == $answers' \
  "$STATE_FILE"
```

Stop VM monitoring with `Ctrl-C` only after the state file exists. Inspect the
streamed API logs and fail the run if any application request recorded a real
dependency operation:

```sh
LOG_FILE="performance/results/$PERF_RUN_ID/vm/compose-live.log"
if rg '"(supabase_execute_count|r_request_count)":[1-9]' "$LOG_FILE"; then
  echo "API-only run made a real dependency call" >&2
  exit 1
fi
```

Retain the k6 summary/raw points on the generator and the state summary,
container logs, event-loop lag, Docker events, and VM samples on the pilot VM.
Report per-operation and full-flow latency, completed flow/session counts,
dropped iterations, API CPU/RSS, event-loop p95/p99/max lag, and generator
headroom. One Uvicorn process can saturate one logical core while VM-wide CPU
still appears low, so report API-container CPU separately.

### Remove API-only exposure

Stop the generator tunnel with `Ctrl-C`, then remove only the stopped
performance service. This deletes its in-memory synthetic state; the exported
evidence remains under `performance/results/`.

**Pilot VM terminal:**

```sh
docker compose -f compose.yaml -f performance/compose.loopback.yaml \
  --profile api-only rm -f api-perf
ss -ltn '( sport = :18002 )'
docker compose -f compose.yaml ps
docker compose -f compose.yaml exec -T api python -c \
  'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=3).read()'
```

Port `18002` must have no listener, and the normal deployment must remain
healthy. Do not delete the derived image until the full API-only comparison
matrix and any required reruns are complete.

## Abort immediately when

- any integrity check fails;
- readiness fails twice consecutively;
- a container restarts or OOMs;
- unexpected failures exceed 5% for 30 seconds;
- p99 exceeds 10 seconds for two minutes;
- VM or Supabase CPU exceeds 90% for two minutes;
- memory or connections exceed 90%; or
- swap growth, I/O exhaustion, or quota alarms appear; or
- the generator loses resource headroom or becomes the apparent bottleneck.

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

2. Start generator monitoring on the load generator and VM monitoring on the
   pilot VM.

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

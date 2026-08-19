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
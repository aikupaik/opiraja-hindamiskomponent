# Pilot Capacity and Stress-Testing Plan

## Summary

Build a repository-owned performance harness and run it against the pilot
deployment before launch, using a separate load-generator machine.

The existing single-session report establishes a baseline but not concurrent
capacity:

- 97.2% of measured backend time was attributed to Supabase, 2.4% to R, and
  0.4% to application work.
- One session generated 83 Supabase operations, including 42 sequential item
  loads consuming 4.75 seconds.
- Answer latency averaged about 1.35 seconds, with a maximum of 1.99 seconds.
- R calls were individually fast, but the deployment still has one R process,
  four backend-to-R connections, and a one-second R pool timeout.
- The pilot design point is 25 concurrent students; tests continue through 50
  and 100 to find the capacity knee.

Capacity is the highest repeatable 10-minute plateau that meets all of these:

- Answer latency: p95 <= 3 seconds and p99 <= 5 seconds.
- Unexpected HTTP failures: less than 1%; no integrity failures.
- No dropped load-generator iterations, readiness loss, container restarts, or
  steadily growing queues.
- VM and Supabase CPU remain below 70% sustained utilization, connections below
  80%, and no memory, swap, or I/O exhaustion.
- The next higher load level must fail the criteria twice before declaring the
  lower level the limit.

## Harness, Interfaces, and Safety

- Add a `performance/` harness containing pinned k6 1.5 scripts, fixture
  utilities, a loopback-only Compose overlay, a runbook, and a Markdown report
  template. Ignore generated artifacts under
  `performance/results/<run-id>/`.
- Do not change production APIs, response types, or database schema. Add only
  test interfaces:
  - `seed --run-id <perf-...> --graph <3-chain|10-chain|10-independent>`
  - `run --scenario <name> --run-id <id>`
  - `cleanup --run-id <id>` for preview only
  - `cleanup --run-id <id> --confirm <same-id>` for explicit deletion
- Generate short-lived OR credentials outside k6 and supply them through
  protected environment input. Never commit or print service keys, JWT
  secrets, admin keys, or player tokens.
- Create dedicated run-owned nodes and usable items so item telemetry and graph
  caches cannot be confused with pilot data. Every session uses
  `perf-<timestamp>-<random>` markers in user/path identifiers.
- Cleanup is never automatic from k6. It exports evidence first, previews exact
  row counts and identifiers, refuses non-performance markers, and then deletes
  child results, YG orders, sessions, unreferenced run graphs, and run-owned
  items in dependency-safe order. Verify zero remaining run rows afterward.
- Use covered inventory for all high-volume tests so no YG webhook or LLM work
  is triggered. Exercise missing-inventory/YG behavior with at most three
  controlled functional runs.
- Keep public Nginx limits enabled. Measure edge-policy capacity separately from
  raw service capacity.
- For internal component tests, temporarily bind API and R to VM loopback-only
  ports through the performance Compose overlay and reach them through SSH
  tunnels from the remote generator. Verify those listeners disappear after
  the run.
- Because HTTPS uses a self-signed certificate, verify and record its
  fingerprint first; only then allow k6's certificate-verification exception
  for that exact pilot endpoint.
- Establish abort rules: stop on any integrity error, readiness failure twice
  consecutively, container restart/OOM, more than 5% unexpected failures for 30
  seconds, p99 above 10 seconds for two minutes, VM/Supabase CPU above 90% for
  two minutes, memory or connections above 90%, swap growth, or I/O/quota
  alarms.

## Test Sequence

| Stage | Workload | Levels and purpose |
| --- | --- | --- |
| Preflight | Exact deployed commit/images, VM vCPU/RAM/network/storage, non-secret timeout/pool settings, Supabase tier/region/limits, idle resource baseline | Confirm maintenance window, approved source IP, backups, clock synchronization, log capacity, and healthy dependencies |
| Static edge | Admin/player HTML and hashed assets through public HTTPS | 1, 25, and 100 clients; measure TLS, Nginx, caching, bytes, and edge errors |
| R only | Recorded `model`, `select`, and `advance` payloads | 3-node chain, 10-node chain, and 10-node relation-free graphs at concurrency 1, 2, 4, 8, and 16; identify R CPU/serialization/queueing limits |
| Supabase only | Existing repository operations against run-owned data | Concurrency 1-32; measure graph/session reads, per-node inventory listing, sequential pool loads, answer commits, unique-item telemetry, and same-item telemetry contention |
| API only | One Uvicorn worker with deterministic in-memory repository and R fake | Measure JWT validation, DTO processing, serialization, middleware, and event-loop overhead without network dependencies |
| API to R | Real API and R with deterministic repository | Concurrency 1, 2, 4, 5, 8, and 16; locate R connection-pool waiting and `503` onset |
| API to Supabase | Real API/repository with deterministic R fake | Vary graph and pool size; quantify Supabase amplification and the completion-review N+1 behavior |
| Pilot rehearsal | Full public HTTPS flow with unique sessions, valid player tokens, random valid answers, and 4-9 second think time | Admit 100 students over the rehearsal while limiting active concurrency to 25 |
| Synchronized bursts | Pre-provisioned same-graph sessions | Simultaneous starts and first answers at 25, 50, and 100 students; expose shared-item telemetry contention, R queueing, and same-NAT edge limits |
| Sustained capacity | Complete stateful sessions | Two 10-minute plateaus each at 1, 5, 10, 25, 50, and 100 concurrent students, cooling down between levels; stop at the abort boundary |
| Soak and recovery | 25 concurrent students for 60 minutes | Detect memory/log/connection growth, then verify latency and readiness return to baseline after load |
| YG boundary | Missing inventory | At most three sessions; verify polling, webhook completion, and failure handling without treating LLM throughput as application capacity |

The realistic model uses closed virtual users because students wait for each
answer before sending the next. Stateless component ceilings additionally use
open arrival-rate scenarios and report `dropped_iterations` so slow responses
cannot hide incoming demand.

## Measurement and Diagnosis

- k6 records per-route throughput, active users, p50/p90/p95/p99/max latency,
  checks, status/error classification, bytes, dropped iterations, and
  machine-readable summaries.
- Every request receives a run/scenario/VU-specific `X-Request-ID`, allowing k6
  results to be correlated with Nginx and FastAPI logs.
- Stream logs during tests so Docker rotation cannot remove evidence. Do not
  enable admin experiment diagnostics: its 500-event process-local buffer and
  body capture would truncate and distort high-volume runs.
- Sample VM/container CPU, memory, PIDs, network, disk, restart count, and load
  every five seconds. Capture Supabase CPU, RAM, I/O, connections, API/database
  latency, error counts, and relevant query diagnostics over the same
  timestamps.
- Validate after every scenario:
  - one accepted result per submission ID;
  - no cross-session answers or duplicated state transitions;
  - expected session completion counts;
  - retries do not advance state twice;
  - no YG orders in covered-inventory scenarios.
- Produce one report per run containing environment metadata, workload
  configuration, graphs, thresholds, first failing plateau, recovery time,
  resource saturation evidence, and a conclusion:
  - High Supabase time with low Supabase resource use: optimize round-trip
    fanout first.
  - Supabase resource saturation after fanout is reduced: scale the Supabase
    tier.
  - R queueing/CPU saturation: optimize payload/computation or add R
    processes/replicas.
  - API CPU saturation with dependencies healthy: address process-local
    coordination before adding Uvicorn workers.
  - VM-wide saturation: resize or separate services.
  - Public `429`s with healthy internals: review same-NAT rate-limit policy
    rather than scaling application code.

## Verification and Defaults

- Validate k6 scripts, fixture determinism, cleanup refusal/dry-run behavior,
  Compose configuration, and loopback-only port exposure.
- Run the full backend test suite and `python -m pyright`; run affected frontend
  checks with `npm run lint` if TypeScript changes become necessary.
- Smoke-test every scenario at one user before creating volume, and rehearse the
  abort and cleanup procedures before the stress run.
- The pilot VM and pilot Supabase project are used in a scheduled pre-launch
  maintenance window. No real students or unrelated administrative work may
  run concurrently.
- Results describe this exact VM, Compose revision, Supabase tier/region, data
  shape, and rate-limit policy; changing any of those requires rerunning at
  least the baseline, design-point, and synchronized-burst scenarios.

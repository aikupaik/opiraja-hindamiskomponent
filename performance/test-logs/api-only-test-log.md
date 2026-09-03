# API-only performance test log

Last updated: 2026-08-30

## Purpose and isolation

The API-only stage measures one Uvicorn worker running the production FastAPI
routes, DTOs, JWT validation, middleware, structured request logging, and
assessment service with deterministic in-process repository and KST seams. It
does not contact public Nginx, Supabase, or R and must not be interpreted as
full pilot capacity.

The derived `opiraja-assessment-api-perf:local` image starts beside the normal
stack on a separate network and binds only pilot-VM loopback port `18002`.
Every run recreates the service and exports an aggregate state-integrity and
event-loop-lag file during graceful shutdown.

## Workloads

- `routes`: two setup sessions support a repeatable four-request flow covering
  liveness, authenticated OR status, active player start, and completed-answer
  replay. Closed VUs and open arrival rate are supported.
- `session`: every VU creates and completes one unique covered-inventory
  assessment, replays the final accepted answer, and verifies completed OR
  status. This is a bounded concurrency/integrity burst.

Both workloads cover `3-chain`, `10-chain`, and `10-independent`. The expected
answer counts are seven, ten, and ten respectively.

## Acceptance

- Zero response-contract and state-integrity failures.
- Less than 1% unexpected HTTP failures and zero dropped iterations.
- p95 at or below 3 seconds and p99 at or below 5 seconds, with the shared
  abort boundaries from the capacity plan.
- Zero YG orders and zero real Supabase/R operation counts in request logs.
- Expected session, answer, replay, and completion counts in shutdown evidence.
- Adequate generator headroom and no VM/container restart, OOM, or resource
  exhaustion.

## Current status

Repository implementation validation is complete: focused backend tests cover
concurrent stateful completion, replay idempotency, covered inventory, and
shutdown evidence, and strict Pyright passes. Local Docker/k6 smokes also pass
for the 3-chain route workload and the worst-size 10-independent stateful
workload. The latter exported one completed session, ten unique answers, zero
YG orders, and zero integrity errors. These local checks validate the harness;
they are not capacity results.

Local verification result: 139 backend tests passed, one opt-in contract test
was skipped, Pyright reported zero errors, the Compose model validated, and k6
1.5 successfully inspected route closed/open and stateful closed scenarios.

## Pilot-VM route plateau results

On 2026-08-30, the `3-chain` routes workload completed 10-minute closed-VU
plateaus at 25 and 100 VUs. Both runs had zero dropped iterations, zero
unexpected failures, zero integrity failures, and all checks passed.

| VUs | Completed flows | Flow rate | Flow p95 / p99 |
| ---: | ---: | ---: | ---: |
| 25 | 59,040 | 98.2/s | 444 ms / 610 ms |
| 100 | 66,839 | 111.1/s | 1,058 ms / 1,154 ms |

The API-only container was the bottleneck: average CPU was 89.6% at 25 VUs
and 97.0% at 100 VUs, with peaks above 140%. VM-wide CPU and memory remained
well below saturation. This indicates single-worker/container CPU saturation,
not a VM or generator resource limit; do not interpret these API-only results
as full pilot capacity.

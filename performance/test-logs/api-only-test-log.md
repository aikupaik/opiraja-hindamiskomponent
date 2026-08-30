# API-only performance test log

Last updated: 2026-08-28

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

No pilot-VM API-only capacity run has been performed yet. Execute and record
the matrix using the **API-only component test** section of
`performance/runbook.md`.

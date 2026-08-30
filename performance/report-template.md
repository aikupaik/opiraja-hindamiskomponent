# Performance report: `<run-id>`

## Run metadata

- Date/window:
- Operator:
- Scenario and load model:
- Run ID:
- Generator hardware, OS, power state, and free storage:
- Runner type and k6 version/image ID/repository digest:
- Docker Desktop/client/engine versions and Docker VM CPU/RAM allocation:
- Generator network path and host-networking mode:
- Deployment commit and image digests:
- Derived/base API image lineage (API-only only):
- VM vCPU/RAM/network/storage:
- Supabase tier, region, and documented limits:
- Non-secret application timeout/pool settings:
- Public rate-limit policy:
- Certificate fingerprint (public HTTPS only):

## Workload and data shape

- Graph fixture:
- Inventory coverage:
- Session/token source:
- Arrival/concurrency configuration:
- Think time:

## Results

| Metric | Value |
| --- | --- |
| Throughput | |
| Active users | |
| p50 / p90 / p95 / p99 / max latency | |
| HTTP status and error classification | |
| Checks | |
| Dropped iterations | |
| Completed flows / sessions | |
| Event-loop p95 / p99 / max lag (API-only) | |
| Bytes | |
| First failing plateau | |
| Recovery time | |

## Resource evidence

- Generator CPU, memory, disk, network, Docker/k6 utilization, and headroom:
- VM/container CPU, memory, PIDs, network, disk, load, and restart counts:
- Supabase CPU, RAM, I/O, connections, API/database latency, and errors:
- Relevant query or queue diagnostics:
- API-container CPU/RSS and single-worker saturation assessment:
- Log correlation using `X-Request-ID`:
- Generator bottleneck assessment and comparison-matrix consistency:

## Integrity validation

- One accepted result per submission ID:
- No cross-session answers or duplicate transitions:
- Expected completion counts:
- Retries did not advance state twice:
- No YG orders in covered-inventory scenarios:
- API-only shutdown evidence has zero integrity errors:
- API-only request logs have zero Supabase/R operation counts:

## Conclusion

State the highest repeatable 10-minute plateau meeting every acceptance
criterion. A higher level must fail twice before claiming the lower level as
the capacity limit. Attach the machine-readable k6 summary and raw monitoring
evidence under `performance/results/<run-id>/`. For API-only results, describe
the result as a single-worker route-flow ceiling or bounded session burst, not
as full pilot/student capacity.

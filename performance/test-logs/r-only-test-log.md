# R-only performance test log

Last updated: 2026-08-26

## Test purpose and scope

The R-only scenario measures the deployed R service through its internal HTTP
interface, without API, Supabase, public Nginx, browser, or student-session
work affecting the result. It is intended to identify R request latency,
serialization, queueing, and throughput limits before the component is tested
behind the full application stack.

The scenario is implemented by
[`performance/k6/r-only.js`](../k6/r-only.js). Each flow replays the recorded
R v2 three-request sequence from the selected fixture:

1. `model` computes the model and posterior;
2. `select` chooses a candidate from the supplied inventory; and
3. `advance` updates the state using the selected candidate and response.

The test verifies HTTP 200 responses, JSON response bodies, exact fixture
responses, candidate integrity, and completion of the complete three-request
flow. It records per-operation request latency, full-flow latency, operation
and flow counts/rates, HTTP failures, unexpected failures, integrity failures,
virtual users, and dropped iterations.

The two load models have different meanings:

- **Closed VU:** a fixed number of virtual users repeatedly performs a complete
  flow. A VU starts its next flow only after the previous one finishes. This
  approximates a client waiting for each result and shows the throughput and
  latency produced by a specified concurrency.
- **Open arrival rate:** k6 starts complete flows at a fixed rate independently
  of response time, using additional VUs when needed up to `maxVUs`. This shows
  whether R can sustain a stated incoming flow rate; `dropped_iterations`
  exposes demand that k6 could not start.

The acceptance thresholds used by the script are zero integrity failures,
less than 1% unexpected HTTP failures, zero dropped iterations, full-request
p95 <= 3 seconds, full-request p99 <= 5 seconds, and an abort boundary at p99
> 10 seconds after two minutes. The same p95/p99 latency thresholds are also
  applied separately to `model`, `select`, and `advance`.

These initial runs cover only the `3-chain` fixture at closed 1 VU and open
1 complete flow per second. They are baseline/qualification points, not the
R-only capacity limit. The planned matrix also includes 3-chain, 10-chain,
and 10-independent at closed 1, 2, 4, 8, and 16 VUs, followed by open-rate
tests selected from the closed-test throughput.

The runbook requires generator and VM monitoring for non-smoke runs. The VM
monitoring report is recorded below. Generator-side samples are not present in
the result directories, so generator saturation remains unassessed.

> **k6 summary note:** in the k6 1.5 JSON summary used for these runs, a
> threshold expression mapped to `false` means it did not fail; `true` marks a
> failed threshold. For `http_req_failed`, the summary `value: 0` means no HTTP
> requests failed even though the raw pass/fail counters can look
> counterintuitive.

## 3-chain closed 1-VU baseline

### Run

- Run ID: `perf-r-3-chain-closed-vu1-20260826T144141Z`
- Load model: 1 closed VU, 10-minute duration
- Fixture: `3-chain`
- Generator summary: [`summary.json`](perf-r-3-chain-closed-vu1-20260826T144141Z/summary.json)
- Generator raw points: [`raw-k6.json`](perf-r-3-chain-closed-vu1-20260826T144141Z/raw-k6.json)
- Result: **passed**

### Generator results

| Metric | Result |
| --- | ---: |
| Completed flows | 1,945 |
| R HTTP requests | 5,835 |
| Flow throughput | 3.241 flows/s |
| Approximate request throughput | 9.723 requests/s |
| VUs | 1 |
| Dropped iterations | 0 |
| Checks | 17,505 passed, 0 failed |
| HTTP status results | 5,835 x HTTP 200 |
| HTTP failure rate | 0% |
| Unexpected failure rate | 0% |
| Integrity failure rate | 0% |

| Timing | p50 | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Complete flow | 308.3 ms | 358.3 ms | 400.6 ms | 938.7 ms |
| Any R operation | 93.3 ms | 170.4 ms | 197.2 ms | 606.2 ms |

| Operation | Average | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| `model` | 146.1 ms | 184.9 ms | 213.7 ms | 606.2 ms |
| `select` | 77.8 ms | 99.1 ms | 131.4 ms | 503.2 ms |
| `advance` | 81.8 ms | 102.3 ms | 148.1 ms | 498.4 ms |

### Finding

The 1-VU closed baseline completed 1,945 valid flows without dropped work,
HTTP errors, unexpected failures, or integrity failures. Full-flow p95 and p99
were far below the 3-second and 5-second limits. The normal flow cost was
about 308 ms, with `model` the slowest operation on average and the largest
observed operation maximum. The isolated maximums are tail outliers rather
than a threshold failure.

### VM monitoring

- Monitoring duration: approximately 10m26s; 74 samples.
- All services were healthy before and after the run.
- No status anomalies, restarts, OOM kills, or failed health checks occurred.
- Host one-minute load ranged from 0.08 to 0.27; host CPU peaked at
  approximately 11%.
- Available memory remained approximately 14.6-14.7 GiB.
- The R service peaked at approximately 236 MiB and 28.2% CPU.
- No network errors or dropped packets were observed.

The VM had substantial headroom throughout this baseline. In particular, the
R CPU and memory observations do not indicate VM or R-container saturation at
one closed VU.

## 3-chain open arrival rate: 1 flow/s

### Run

- Run ID: `perf-r-3-chain-open-rate1-20260826T145421Z`
- Load model: constant arrival rate of 1 complete flow/s, 10-minute duration
- VU allocation: 2 pre-allocated, maximum 16
- Fixture: `3-chain`
- Generator summary: [`summary.json`](perf-r-3-chain-open-rate1-20260826T145421Z/summary.json)
- Generator raw points: [`raw-k6.json`](perf-r-3-chain-open-rate1-20260826T145421Z/raw-k6.json)
- Result: **passed**

### Generator results

| Metric | Result |
| --- | ---: |
| Completed flows | 601 |
| R HTTP requests | 1,803 |
| Offered/achieved flow rate | 1.001 flows/s |
| Approximate request throughput | 3.004 requests/s |
| VUs observed | 0-1; VU allocation maximum 2 |
| Dropped iterations | 0 |
| Checks | 5,409 passed, 0 failed |
| HTTP status results | 1,803 x HTTP 200 |
| HTTP failure rate | 0% |
| Unexpected failure rate | 0% |
| Integrity failure rate | 0% |

| Timing | p50 | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Complete flow | 237.2 ms | 289.6 ms | 383.2 ms | 607.8 ms |
| Any R operation | 75.3 ms | 104.6 ms | 162.2 ms | 361.0 ms |

| Operation | Average | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| `model` | 73.4 ms | 102.1 ms | 202.8 ms | 361.0 ms |
| `select` | 79.8 ms | 105.0 ms | 155.5 ms | 182.4 ms |
| `advance` | 84.0 ms | 103.0 ms | 161.2 ms | 254.7 ms |

### Finding

The open-rate run sustained the offered 1 flow/s for the full duration. It
completed 601 flows, dropped none, and required no more than the allocated
two VUs. All correctness and latency thresholds passed. At this lower offered
rate, full-flow p95 was 289.6 ms and p99 was 383.2 ms; the result therefore
shows comfortable headroom at 1 flow/s but does not establish the maximum
sustainable arrival rate.

### VM monitoring

- Monitoring duration: approximately 10m17s; 73 samples.
- All services were healthy before and after the run.
- No status anomalies, restarts, OOM kills, or failed health checks occurred.
- Host one-minute load ranged from 0.24 to 0.47; host CPU peaked at
  approximately 8%.
- Available memory remained approximately 14.6-14.7 GiB.
- The R service peaked at approximately 236 MiB and 17.9% CPU.
- No network errors or dropped packets were observed.

The VM and R service also had substantial headroom at the offered 1 flow/s
rate. The lower R CPU peak is consistent with the lower request rate than the
closed baseline.

## Combined findings and next step

Both initial R-only runs passed their correctness and latency gates. The
closed baseline sustained approximately 3.24 complete flows/s at one VU, while
the open test deliberately offered approximately 1 flow/s and sustained it
without dropped iterations. The open result is consistent with the closed
baseline, but the two runs use different offered loads and should not be read
as a direct capacity comparison.

No evidence indicates an R functional or serialization problem. VM monitoring
shows no host, memory, service-health, network, or R CPU/memory saturation in
either run. R queue depth and load-generator limitation remain unassessed:
queue depth was not directly measured, and generator-side monitoring output was
not retained with the runs.

Proceed with the planned closed-VU 3-chain levels at 2, 4, 8, and 16 VUs,
retaining five-second generator and VM samples plus streamed R/container logs
for each run. After the closed 3-chain curve is understood, continue with the
10-chain and 10-independent shapes, then raise the open arrival rate from the
observed closed-test throughput rather than treating `rate=1` as a ceiling.

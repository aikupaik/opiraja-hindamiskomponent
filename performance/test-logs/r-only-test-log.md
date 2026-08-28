# R-only performance test log

Last updated: 2026-08-28

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

The initial baseline/qualification runs covered the `3-chain` fixture at
closed 1 VU and open 1 complete flow per second. The closed-VU matrix now also
contains the `10-chain` fixture at 2, 4, 8, and 16 VUs. These runs are still
not an R-only capacity limit. The remaining planned matrix includes
`10-independent` at closed 1, 2, 4, 8, and 16 VUs, followed by open-rate tests
selected from the closed-test throughput.

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

## 3-chain closed 2-, 4-, 8-, and 16-VU results

### Consolidated result

All four runs passed. Each completed flow returned the expected HTTP 200,
JSON, and fixture responses; checks and integrity validation had no failures.
There were no dropped iterations or unexpected HTTP failures. Throughput
increased with the closed VU count while latency remained well below the
acceptance thresholds.

| Closed VUs | Run | Completed flows | Flow rate | Flow p95 | Flow p99 | Dropped |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 2 | [`summary.json`](../results/perf-r-3-chain-closed-vu2-20260828T064711Z/summary.json) | 4,768 | 7.94/s | 327 ms | 374 ms | 0 |
| 4 | [`summary.json`](../results/perf-r-3-chain-closed-vu4-20260828T065852Z/summary.json) | 9,631 | 16.05/s | 315 ms | 388 ms | 0 |
| 8 | [`summary.json`](../results/perf-r-3-chain-closed-vu8-20260828T071001Z/summary.json) | 19,245 | 32.07/s | 322 ms | 410 ms | 0 |
| 16 | [`summary.json`](../results/perf-r-3-chain-closed-vu16-20260828T073108Z/summary.json) | 29,911 | 49.83/s | 395 ms | 451 ms | 0 |

### 16-VU detail

| Metric | Result |
| --- | ---: |
| R HTTP requests | 89,733 |
| Approximate request throughput | 149.49 requests/s |
| Checks | 269,199 passed, 0 failed |
| HTTP status results | 89,733 x HTTP 200 |
| HTTP failure rate | 0% |
| Unexpected failure rate | 0% |
| Integrity failure rate | 0% |

| Operation | Average | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| `model` | 106.3 ms | 148.0 ms | 188.5 ms | 515.5 ms |
| `select` | 108.8 ms | 150.5 ms | 186.7 ms | 515.1 ms |
| `advance` | 103.9 ms | 146.2 ms | 182.2 ms | 456.0 ms |

The 16-VU run also passed the full-flow p95/p99 limits, with no sign of a
functional failure or dropped work. It provides a measured result of about
49.8 complete flows/s for this fixture and load model; it is not a capacity
ceiling.

### VM monitoring across the closed-VU runs

- All services were healthy before and after every run. There were no
  container restarts, OOM kills, unhealthy states, or nonzero health-check
  exits.
- Host CPU scaled smoothly from 2.8% average user CPU at 1 VU to 13.0% at
  16 VUs; load peaked at only 1.92 on the 8-CPU VM.
- Memory remained stable at roughly 1.0 GiB used, with at least approximately
  14.6 GiB available. R-service memory stayed around 236–240 MiB, with no
  obvious leak.
- R-service CPU peaked at 114.9% at 16 VUs. This is normal Docker multi-core
  accounting and does not indicate saturation.
- No Nginx error-log activity was recorded.

## 10-chain closed 2-, 4-, 8-, and 16-VU results

### Consolidated result

All four 10-chain runs passed. Each completed flow returned the expected HTTP
200, JSON, and fixture responses; checks and integrity validation had no
failures. There were no dropped iterations or unexpected HTTP failures.
Throughput increased with the closed VU count, while full-flow latency
increased as the load rose but remained below the acceptance thresholds.

| Closed VUs | Run | Completed flows | Flow rate | Flow p95 | Flow p99 | Dropped |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 2 | [`summary.json`](../results/perf-r-10-chain-closed-vu2-20260828T075640Z/summary.json) | 3,899 | 6.50/s | 386 ms | 457 ms | 0 |
| 4 | [`summary.json`](../results/perf-r-10-chain-closed-vu4-20260828T081006Z/summary.json) | 6,912 | 11.52/s | 442 ms | 526 ms | 0 |
| 8 | [`summary.json`](../results/perf-r-10-chain-closed-vu8-20260828T082140Z/summary.json) | 8,959 | 14.92/s | 636 ms | 713 ms | 0 |
| 16 | [`summary.json`](../results/perf-r-10-chain-closed-vu16-20260828T095541Z/summary.json) | 9,110 | 15.17/s | 1,170 ms | 1,477 ms | 0 |

### 16-VU detail

| Metric | Result |
| --- | ---: |
| R HTTP requests | 27,330 |
| Approximate request throughput | 45.50 requests/s |
| Checks | 81,990 passed, 0 failed |
| HTTP status results | 27,330 x HTTP 200 |
| HTTP failure rate | 0% |
| Unexpected failure rate | 0% |
| Integrity failure rate | 0% |

| Operation | Average | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| `model` | 339.0 ms | 434.4 ms | 531.1 ms | 1,763.1 ms |
| `select` | 338.3 ms | 430.6 ms | 532.9 ms | 1,775.9 ms |
| `advance` | 373.8 ms | 448.0 ms | 529.9 ms | 1,662.5 ms |

The 10-chain closed curve shows a clear load-related latency increase. The
2-VU run achieved 6.50 complete flows/s with a 457 ms full-flow p99; the
16-VU run achieved 15.17 flows/s with a 1,477 ms p99. The 16-VU result still
passed the full-flow p95/p99 limits and had no functional failures or dropped
work, but its reduced throughput gain and higher tail latency indicate that
the heavier fixture is approaching a practical contention limit sooner than
the 3-chain fixture. This is a measured point, not a capacity ceiling.

### VM monitoring

Each monitor captured 72 samples over approximately ten minutes. All services
remained healthy, with no evidence of OOM kills or container restarts.

| Run | R-service CPU average / maximum | Host CPU average / maximum | RAM used | Load 1m average / maximum |
| --- | ---: | ---: | ---: | ---: |
| VU 2 | 62.5% / 77.5% | 8.9% / 19.5% | ~1.03 GiB | 0.58 / 0.82 |
| VU 4 | 90.2% / 99.1% | 12.1% / 19.7% | ~1.03 GiB | 0.91 / 1.10 |
| VU 8 | 98.1% / 99.5% | 13.7% / 19.1% | ~1.03 GiB | 1.03 / 1.43 |
| VU 16 | 99.3% / ~110% | 13.7% / 18.3% | ~1.03 GiB | 0.75 / 1.12 |

The R service is the clear bottleneck: it approaches one fully occupied CPU
core at VU 4 and remains saturated at VU 8 and VU 16. The VM itself was not
resource constrained: host CPU stayed below 20%, approximately 14.6 GiB of
memory remained available, swap was unused, and I/O wait was effectively
zero. API, web, and player containers remained light with stable memory use.
The VU 8 and VU 16 results therefore mainly demonstrate saturation of the
single R-service process, not additional VM capacity. These VM measurements do
not by themselves establish latency, throughput, dropped iterations, or the
actual capacity plateau; those conclusions come from the k6 summaries above.

## Combined findings and next step

All closed 3-chain runs from 1 through 16 VUs passed their correctness and
latency gates. Throughput rose from approximately 3.24 complete flows/s at one
VU to 49.83 flows/s at 16 VUs, with full-flow p99 remaining below 451 ms. The
open test deliberately offered approximately 1 flow/s and also sustained it
without dropped iterations; it should not be read as a capacity comparison.

No evidence indicates an R functional or serialization problem. VM monitoring
shows no host, memory, service-health, Nginx, or R memory saturation across the
closed-VU runs, but the 10-chain reports do show saturation of the R service's
CPU at VU 8 and VU 16. R queue depth and load-generator limitation remain
unassessed: queue depth was not directly measured, and generator-side
monitoring output was not retained with the runs.

The 3-chain and 10-chain closed curves both passed the correctness and latency
gates. The 10-chain results show materially higher flow latency and only a
small throughput increase from 8 to 16 VUs, so the next test should retain
five-second generator and VM samples plus streamed R/container logs. Proceed
to the `10-independent` closed matrix, then raise the open arrival rate from
the observed closed-test throughput rather than treating `rate=1` as a
ceiling.

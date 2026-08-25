# Static-edge performance test log

Last updated: 2026-08-25

## Test purpose and scope

The static-edge scenario measures the public HTTPS delivery path before the
stateful application and dependency tests begin. It exercises the path from a
separate load-generator machine through TLS and host Nginx to the admin and
player Nginx containers. This establishes whether the public edge can deliver
the application shells and their production, hashed assets under simultaneous
cold-client load without application API, Supabase, or R activity obscuring
the result.

The scenario is implemented by
[`performance/k6/static-edge.js`](../k6/static-edge.js). Each virtual user
performs one iteration and, in sequence:

1. requests the admin HTML shell at `/`;
2. discovers and requests its hashed JavaScript and CSS assets;
3. requests the player HTML shell below `/test/`; and
4. discovers and requests its hashed JavaScript and CSS assets.

For every page and asset, the script checks successful status, expected content
metadata, immutable asset caching, and request-ID propagation. It records
per-page and per-resource latency tags. The acceptance thresholds are:

- all checks pass;
- HTTP failure rate is zero;
- global request-duration p95 is below 3 seconds; and
- request-duration p95 is below 3 seconds for every admin/player HTML, JS, and
  CSS resource class.

The test is important because a backend with spare CPU can still provide a poor
first-load experience if TLS, reverse-proxy buffering, static-asset size, edge
configuration, or the downstream network path becomes the bottleneck. Hashed
assets are cacheable after first use, but every new student device must complete
an initial load. This scenario deliberately represents that cold-load boundary.

This is an HTTP-level test. It does not execute JavaScript, render a browser,
model browser connection limits, reuse a browser cache, call application APIs,
create assessment sessions, or exercise Supabase and R capacity. The 1, 25,
and 100 VU levels are short synchronized page-load bursts, not the later
10-minute sustained student-capacity plateaus.

The runner is the pinned `grafana/k6:1.5.0` Docker image on a separate personal
laptop. The target environment, certificate fingerprint, deployed images,
resource baseline, and safety gates are recorded in
[`performance/preflight.md`](../preflight.md).

> **k6 summary note:** in the k6 1.5 JSON summary used for these runs, a
> threshold expression mapped to `false` means it did not fail; `true` marks a
> failed threshold. For the `http_req_failed` rate, `value: 0` means no HTTP
> requests failed even though the rate metric's raw boolean sample counters can
> look counterintuitive.

## 1 VU baseline

### Run

- Run ID: `static-edge-1-20260825T090102Z`
- Load model: one VU, one iteration
- Generator summary:
  [`summary.json`](static-edge-1-20260825T090102Z/summary.json)
- Generator raw points:
  [`raw-k6.json`](static-edge-1-20260825T090102Z/raw-k6.json)
- Result: **passed**

### Generator results

| Metric | Result |
| --- | ---: |
| Completed iterations | 1 |
| HTTP requests | 6 |
| Checks | 24 passed, 0 failed |
| HTTP failure rate | 0% |
| Data received | 536,373 bytes |
| Iteration duration | 1.095 s |
| Request duration average | 169.8 ms |
| Request duration median | 181.0 ms |
| Request duration p95 | 269.3 ms |
| Request duration p99 | 280.4 ms |
| Request duration maximum | 283.2 ms |

| Resource | Duration |
| --- | ---: |
| Admin HTML | 185.0 ms |
| Admin JavaScript | 283.2 ms |
| Admin CSS | 176.9 ms |
| Player HTML | 59.9 ms |
| Player JavaScript | 227.5 ms |
| Player CSS | 86.0 ms |

### Finding

The complete scenario worked correctly at one VU. Both application shells and
all discovered assets returned successfully, every correctness/header/cache
check passed, and all latency thresholds had substantial headroom. This run
established the cold single-client comparison point used to diagnose the
25-VU result.

## 25 VU synchronized load

### Run

- Run ID: `static-edge-25-20260825T090656Z`
- Load model: 25 VUs, one iteration per VU
- Generator summary:
  [`summary.json`](static-edge-25-20260825T090656Z/summary.json)
- Generator raw points:
  [`raw-k6.json`](static-edge-25-20260825T090656Z/raw-k6.json)
- Result: **failed the latency threshold**
- 100-VU progression: **paused pending remediation and a successful 25-VU
  rerun**

### Generator results

The scenario itself completed correctly. All 25 iterations finished, all 150
requests returned successfully, and all 600 functional/header/cache checks
passed. k6 exited non-zero because the global and admin-JavaScript p95 latency
thresholds failed.

| Metric | Result |
| --- | ---: |
| Completed iterations | 25 |
| HTTP requests | 150 |
| Checks | 600 passed, 0 failed |
| HTTP failure rate | 0% |
| Data received | 13,409,325 bytes |
| Average receive rate over the run | 1.93 MB/s |
| Iteration duration average | 6.802 s |
| Iteration duration p95 | 6.938 s |
| Request duration average | 1.099 s |
| Request duration median | 530.7 ms |
| Request duration p95 | **4.044 s** |
| Request duration p99 | 4.344 s |
| Request duration maximum | 4.384 s |

| Resource | Average | p95 | Maximum | Threshold |
| --- | ---: | ---: | ---: | --- |
| Admin HTML | 229.7 ms | 288.8 ms | 304.8 ms | Pass |
| Admin JavaScript | **3.880 s** | **4.361 s** | **4.384 s** | **Fail** |
| Admin CSS | 510.1 ms | 830.2 ms | 842.6 ms | Pass |
| Player HTML | 233.8 ms | 557.8 ms | 776.1 ms | Pass |
| Player JavaScript | 1.314 s | 1.625 s | 1.658 s | Pass |
| Player CSS | 427.8 ms | 726.5 ms | 743.9 ms | Pass |

The generator's raw admin-JavaScript timings show where its 3.880-second
average was spent:

| Component | 1 VU | 25-VU average |
| --- | ---: | ---: |
| Waiting for first byte | 75 ms | 901 ms |
| Receiving response body | 208 ms | 2,978 ms |
| Total request duration | 283 ms | 3,880 ms |

The admin-JavaScript requests reused established connections, so connection
blocking, TCP connection establishment, and TLS negotiation were not material
contributors to those requests.

### VM evidence

The VM evidence was reviewed in a separate agent session on the VM. That review
reported:

- all 150 edge requests returned HTTP 200;
- there were no 4xx/5xx responses, timeouts, or rate-limit responses;
- every container remained healthy with zero restarts and no OOM kill;
- the host retained approximately 15 GiB available memory and no swap;
- CPU was mostly 0–6%, with low load and no network, disk, or I/O pressure
  indicators;
- all 25 admin-JavaScript requests targeted
  `/assets/index-DjMxFnIS.js`;
- host-Nginx request latency for that asset averaged 1.665 seconds and reached
  approximately 2.072 seconds at p95/maximum;
- inner-upstream time was only 3–9 ms; and
- each admin-JavaScript response produced an Nginx warning that the upstream
  response was buffered to a temporary file.

The VM evidence therefore rules out VM CPU, memory, container, or upstream web
service saturation for this run. It also shows that host Nginx spent material
time delivering the large response downstream even though the inner container
produced it quickly.

### Combined finding

The generator and VM measurements describe different completion points. Host
Nginx averaged 1.665 seconds to process and hand off the admin bundle, while the
generator averaged 3.880 seconds before the response body was completely
received. Generator-side receive time was the largest component. The remaining
difference lies after the fast inner upstream, in host buffering, socket/network
delivery, and/or the generator's network path.

The temporary-file warning is evidence that proxy buffering was enabled and
the response exceeded the configured in-memory proxy buffers while the
downstream side consumed it more slowly than the upstream supplied it. It may
add some overhead, but it is not by itself proof that temporary-file I/O caused
the failed client-side threshold.

A follow-up header check sent `Accept-Encoding: gzip` for the deployed admin
bundle. The response had `Content-Length: 278113` and no `Content-Encoding`,
confirming that the asset was delivered uncompressed. A comparable local admin
bundle compresses from approximately 278 KB to 85 KB with gzip; the player JS
compresses from approximately 207 KB to 64 KB. Compression is therefore the
first high-confidence correction because it reduces both the upstream payload
that host Nginx must buffer and the downstream bytes each cold client must
receive.

### Remediation plan recorded after the failed run

1. Do not run the 100-VU level yet. Preserve this run as a genuine failed
   25-VU static-edge result.
2. Enable gzip for JavaScript and CSS in the inner admin and player Nginx
   servers so the host proxy receives compressed responses.
3. Verify the deployed assets return `Content-Encoding: gzip` when requested
   with `Accept-Encoding: gzip`, include `Vary: Accept-Encoding`, preserve the
   immutable cache policy, and have materially smaller transferred bodies.
4. Consider proxy-buffer sizing only after compression. Disabling buffering
   alone would remove the warning but would not reduce transferred bytes and
   is not the first remediation.
5. Capture load-generator CPU, memory, and network utilization during the next
   run; the current generator result directory contains only k6 output, so
   generator saturation cannot yet be excluded from the evidence.
6. Because the deployment will change, rerun the complete 1-VU baseline with a
   new run ID, then rerun 25 VUs with a new run ID and full VM evidence.
7. Proceed to 100 VUs only after reviewing the new 25-VU run and confirming
   that every threshold and safety gate passes.

## Gzip remediation and successful 25-VU rerun

### Run

- Run ID: `static-edge-25-20260825T110639Z`
- Load model: 25 VUs, one iteration per VU
- Generator summary:
  [`summary.json`](static-edge-25-20260825T110639Z/summary.json)
- Generator raw points:
  [`raw-k6.json`](static-edge-25-20260825T110639Z/raw-k6.json)
- Result: **passed**

The inner admin and player Nginx servers were updated to gzip JavaScript and
CSS responses, emit `Vary: Accept-Encoding`, and preserve the immutable asset
cache policy. The static-edge k6 scenario explicitly requested gzip and added
checks for `Content-Encoding: gzip` and `Vary: Accept-Encoding`.

### Generator results

| Metric | Result |
| --- | ---: |
| Completed iterations | 25 |
| HTTP requests | 150 |
| Checks | 800 passed, 0 failed |
| HTTP failure rate | 0% |
| Data received | 4,218,737 bytes |
| Iteration duration average | 2.985 s |
| Request duration average | 471.6 ms |
| Request duration p95 | **1.400 s** |
| Request duration maximum | 1.622 s |

| Resource | Average | p95 | Maximum | Threshold |
| --- | ---: | ---: | ---: | --- |
| Admin HTML | 75.9 ms | 138.4 ms | 138.8 ms | Pass |
| Admin JavaScript | 1.255 s | **1.594 s** | 1.622 s | Pass |
| Admin CSS | 471.6 ms | 722.3 ms | 745.0 ms | Pass |
| Player HTML | 172.1 ms | 286.7 ms | 309.9 ms | Pass |
| Player JavaScript | 525.6 ms | 697.9 ms | 846.4 ms | Pass |
| Player CSS | 329.3 ms | 615.2 ms | 649.7 ms | Pass |

The gzip-specific checks passed for every admin/player JavaScript and CSS
asset. The k6 summary represents passing thresholds with `false` threshold
failure values; all thresholds were therefore successful.

### Improvement over the failed run

| Metric | Uncompressed 25 VU | Gzip 25 VU | Change |
| --- | ---: | ---: | ---: |
| Global request p95 | 4.044 s | 1.400 s | 65.4% lower |
| Admin JavaScript p95 | 4.361 s | 1.594 s | 63.4% lower |
| Data received | 13,409,325 bytes | 4,218,737 bytes | 68.5% lower |

### VM evidence

The associated VM log review was performed separately and reported
successful. No VM-side failure, container-health issue, or deployment blocker
was identified for this rerun.

### Conclusion

The static-edge gzip remediation resolved the 25-VU latency failure. The
global and every per-resource p95 threshold passed, all functional and gzip
header checks passed, and HTTP failure rate remained zero. The static-edge
25-VU acceptance gate is therefore **passed**, and the 100-VU progression is
unblocked.

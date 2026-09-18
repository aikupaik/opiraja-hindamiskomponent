# Structured Request Logging and Correlation

## Summary

Introduce a first observability layer for the `api` and `r-service`
containers:

- Emit structured, one-line JSON to stdout/stderr for `docker logs` and future
  Filebeat ingestion.
- Record one completion event per meaningful HTTP request with status and
  duration.
- Propagate the existing `X-Request-ID` from FastAPI to R so requests can be
  followed across containers.
- Keep the existing rotated Docker `json-file` configuration.
- Defer OpenMetrics, Prometheus metrics, Grafana dashboards,
  Elasticsearch/Filebeat deployment, profiling, and OpenTelemetry spans to
  later increments.

## Implementation changes

### Common logging contract

- Use a shared versioned schema containing `timestamp`, `schema_version`,
  `level`, `service`, `event`, and `request_id`.
- Request completion events additionally contain `method`, query-free `path`,
  normalized `route` when available, `status`, `outcome`, and numeric
  `duration_ms`.
- Retain FastAPI's existing `test_id`, Supabase/R durations, and dependency
  call counts.
- Emit completion events at `INFO` for 2xx/3xx, `WARNING` for 4xx, and `ERROR`
  for 5xx.
- Suppress successful health-check completion events; unhealthy responses
  remain logged.
- Never log request or response bodies, query strings, authorization or cookie
  headers, JWTs, configured secrets, or client IP addresses.

### FastAPI backend

- Add a production logging configuration that makes `app.*` and Uvicorn
  lifecycle events visible as JSON without enabling duplicate Uvicorn access
  logs.
- Add validated `APP_LOG_LEVEL` configuration supporting `DEBUG`, `INFO`,
  `WARNING`, and `ERROR`, defaulting to `INFO`.
- Replace the currently pre-serialized completion message with structured log
  fields while preserving exactly one completion event per request.
- Bind `request_id` in request-local context so warnings and errors raised by
  service or integration code automatically receive the active correlation
  ID.
- Log unexpected exceptions as a separate structured error event plus the
  final 500 completion event. Include the exception class and safe diagnostic
  location, but not raw request data or unredacted exception content.
- Send the active request ID as `X-Request-ID` on every FastAPI-to-R call;
  generate a safe ID when an R call occurs outside an HTTP request.

### R service and container operation

- Add production Plumber hooks that capture a monotonic start time, resolve or
  generate a safe request ID, set `X-Request-ID` on the response, and emit the
  completion JSON after serialization.
- Validate incoming IDs with the same bounded character policy as FastAPI;
  generate a process-local unique ID for direct calls such as Docker health
  checks.
- Add structured logging to the Plumber error handler for unexpected
  exceptions, without exposing error messages or request bodies.
- Remove duplicate request timing output from the manual launcher while
  retaining its explicitly opt-in, development-only body inspection.
- Pass `APP_LOG_LEVEL` to both services through Compose. Keep the existing
  `json-file` rotation of five 10 MB files per container.
- Document `docker logs --since`, `--tail`, follow mode, JSON filtering with
  `jq`, and cross-container lookup by `request_id`.

## Interfaces

- Existing public FastAPI response behavior remains unchanged: every
  application response carries `X-Request-ID`.
- The internal R contract gains an optional `X-Request-ID` request header and
  always returns the resolved value in its response header.
- No response-body schemas or business APIs change.
- The log schema becomes an operational interface intended to remain
  compatible with later Filebeat/Elasticsearch collection.

## Test plan

- Backend tests verify valid and generated request IDs, R header propagation,
  structured JSON fields, level mapping, dependency timings, one completion
  event per request, exception correlation, and health-success suppression.
- R tests verify propagated and generated IDs, response headers, durations,
  status-based levels, validation and forced-500 events, health suppression,
  and valid one-line JSON output.
- Redaction tests submit sentinel secrets through headers, bodies, query
  strings, and failures and assert they never appear in captured logs.
- Run the complete backend test suite followed by `python -m pyright`; run the
  complete R `testthat` suite.
- Build and smoke-test both containers, confirming `docker logs` for the API
  and R containers contains parseable events and that one request ID can be
  found in both logs.

## Assumptions

- Request-ID correlation is the intended first meaning of tracing;
  OpenTelemetry trace and span IDs come later.
- Successful health requests are intentionally omitted to avoid thousands of
  repetitive entries per day.
- Application logs record what operation occurred, not request payloads or
  caller identity.
- Current per-container retention of approximately 50 MB is adequate for this
  first step and can be revisited when centralized collection is introduced.

## Examining the logs

List the running containers, then inspect recent API or R output:

```sh
docker compose ps
docker compose logs --tail 100 --no-log-prefix api
docker compose logs --since 30m --no-log-prefix r-service
docker compose logs --follow --no-log-prefix api r-service
```

Each application line is JSON. Use `jq` to select completed requests or
warnings and errors:

```sh
docker compose logs --since 30m --no-log-prefix api \
  | jq -Rrc 'fromjson? | select(.event == "request_completed")'

docker compose logs --since 30m --no-log-prefix api r-service \
  | jq -Rrc 'fromjson? | select(.level == "WARNING" or .level == "ERROR")'
```

Copy a `request_id` from an API response header or log entry and search both
services to follow the same operation across the FastAPI-to-R boundary:

```sh
docker compose logs --since 30m --no-log-prefix api r-service \
  | rg 'request.safe-123'
```

Look first at `status`, `outcome`, and `level` for failures and at
`duration_ms` for slow requests. API completion events also separate
`supabase_ms` and `r_ms` and include their call counts, which indicates where
time was spent. Successful health checks are intentionally absent; health
failures remain visible as warning or error events.

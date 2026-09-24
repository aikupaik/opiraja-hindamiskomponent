# OBS-04 — Detailed Backend Request and Supabase Logging

## Summary

Improve FastAPI production logging so operators can diagnose assessment-creation
and Supabase failures from Loki without relying on the process-local experiment
diagnostic buffer.

The implementation adds three structured production events:

- `assessment_create_received`, containing a bounded allowlist from an
  authorized `POST /api/v1/tests` request;
- `supabase_operation`, emitted for every Supabase execution attempt with
  operation timing, outcome, and sanitized failure information; and
- `request_failed`, emitted for handled and unexpected server-side failures
  with safe exception-chain locations.

Existing request completion events, request-ID propagation, diagnostic reports,
Docker log rotation, and Loki collection remain in place. The public HTTP API,
database schema, and assessment behavior do not change.

## Motivation and Current Gaps

Production request completion events currently show the final status,
`supabase_unavailable` outcome, aggregate Supabase duration, and execute count.
They do not identify which Supabase operation failed or expose the PostgREST
error code, message, details, or hint.

The assessment and admin repositories already produce `supabase_operation`
summaries, but they use `emit_diagnostic`. That function emits only while an
authenticated admin experiment context is active. Normal OR and player requests
therefore produce no per-operation event for Alloy and Loki. The KST
configuration repository records only aggregate timing and emits no comparable
operation event.

Mapped exceptions such as `RepositoryUnavailable` are converted into generic
HTTP responses. Because these are handled exceptions, they bypass the existing
unhandled-exception event. The final completion event consequently identifies
the dependency but not the underlying failure.

Assessment creation also validates the graph before most persistence work. To
investigate whether failures correlate with graph size or shape, operators need
the graph-related portion of the create request before graph validation runs.
No bodies from later assessment, player, or admin requests are needed.

## Objectives

- Make every Supabase execution attempt queryable in Loki by stable operation
  name, outcome, duration, and request ID.
- Preserve useful PostgREST and transport failure details without exposing
  credentials, headers, database rows, or unrestricted exception text.
- Log the relevant fields of each authorized, schema-valid assessment-creation
  request before graph validation and service execution.
- Make node and relation counts available even when a request is too large to
  log in full.
- Preserve the existing experiment-diagnostic stream and report inputs.
- Keep Loki stream labels bounded and place request-specific data only inside
  the JSON log line.

## Non-goals

- Do not log bodies from player start, answer, question-report, admin, health,
  or other API operations.
- Do not log `user_id`, `learning_path_id`, authorization or cookie headers,
  query strings, client addresses, Supabase credentials, database request rows,
  or database response rows.
- Do not add distributed tracing, metrics infrastructure, retries, alerting, or
  a database migration.
- Do not change public response bodies, status codes, authentication, graph
  limits, or assessment behavior.
- Do not change the Alloy label set beyond `service`, `level`, `event`, and
  stdout/stderr stream.

## Structured-log Contract

The changes are additive and retain `schema_version: 1`. Existing consumers of
`request_completed`, including experiment reports, must remain compatible.

All new production events use the existing JSON formatter and automatically
receive `timestamp`, `schema_version`, `level`, `service`, and the active
`request_id`. A `test_id` is included when it is available from the request
path or is explicitly supplied by the caller. Neither correlation field becomes
a Loki label.

### Assessment creation event

Emit one `assessment_create_received` event for every request that satisfies all
of the following conditions:

1. FastAPI has parsed it as a valid `CreateTestRequest`;
2. authentication and `tests:create` authorization have succeeded; and
3. the canonical route handler for `POST /api/v1/tests` has been entered.

Emit the event immediately after `require_or` succeeds and before converting the
DTO to a command or calling `AssessmentService.create_assessment`. This ensures
the event exists when graph normalization rejects an excessive node count,
duplicate nodes, missing relation endpoints, or another graph invariant.

The event contains only this request-body allowlist:

```json
{
  "event": "assessment_create_received",
  "request_id": "request.safe-123",
  "method": "POST",
  "route": "/api/v1/tests",
  "body": {
    "nodes": ["A", "B"],
    "relations": [{"from": "A", "to": "B"}],
    "course": "Course name",
    "goal": "Assessment goal",
    "method": "kst",
    "cognitive_level": "mõistab",
    "parent_node": "Parent"
  },
  "node_count": 2,
  "relation_count": 1,
  "body_bytes": 210,
  "body_sha256": "<hex digest>",
  "body_truncated": false
}
```

Use the Pydantic model values rather than reparsing arbitrary request bytes, so
default values are included and field aliases such as relation `from` and `to`
remain consistent with the public API. Do not place the whole model in the log,
because it also contains `user_id` and `learning_path_id`.

Serialize the complete allowlisted body deterministically as compact UTF-8 JSON.
Use that serialization for `body_bytes` and a lowercase SHA-256 digest. If its
size is at most 32 KiB, log the complete allowlisted body.

If it exceeds 32 KiB, set `body_truncated` to `true` and log a deterministic
preview containing:

- the first 25 nodes;
- the first 50 relations;
- at most 128 UTF-8 bytes for each string value, without splitting a UTF-8
  character;
- `omitted_node_count` and `omitted_relation_count`; and
- the original full-body byte count and digest.

The preview itself must remain valid JSON. The counts and digest always describe
the complete allowlisted body, not the preview. This preserves evidence of an
oversized graph even when its content cannot safely fit in one log line.

Unauthorized requests and requests rejected by FastAPI body validation do not
emit this event because the route body has not reached the authorized,
schema-aware boundary. Their existing completion events remain unchanged.

### Supabase operation event

Create one shared Supabase execution-observability helper and use it from the
assessment, admin, and KST-configuration repositories. It must continue calling
`record_supabase_execute` exactly once for every successful or failed execute
attempt.

For a successful operation, emit an INFO event containing:

```json
{
  "event": "supabase_operation",
  "operation": "testisessioonid.insert",
  "outcome": "success",
  "duration_ms": 18.421,
  "count": 1
}
```

For a failed operation, emit a WARNING event containing the same stable fields
and sanitized error information:

```json
{
  "event": "supabase_operation",
  "operation": "testisessioonid.insert",
  "outcome": "failed",
  "duration_ms": 18.421,
  "count": 0,
  "error_type": "APIError",
  "error_category": "postgrest",
  "error_code": "23505",
  "error_message": "<sanitized message>",
  "error_details": "<sanitized details>",
  "error_hint": "<sanitized hint>"
}
```

Use the following stable `error_category` values:

- `postgrest` for `postgrest.APIError`;
- `timeout` for built-in and HTTPX timeout exceptions; and
- `transport` for other `httpx.HTTPError` failures.

Include optional PostgREST fields only when present. Redact and limit
`error_message`, `error_details`, and `error_hint` independently to 2 KiB of
UTF-8 text. Preserve the existing unique-violation control flow used to resolve
idempotent answer submissions; logging must not change whether that exception is
re-raised for the caller to handle.

The helper must emit the same operation payload into the process-local
diagnostic context when one is active, retaining the existing diagnostic report
behavior. Normal production logging must not depend on an experiment context.

The stable logical `operation` names remain inside the JSON line rather than
becoming labels. Do not derive diagnostic fields from a Supabase request URL,
because its filters may contain identifiers or user-provided values. Do not log
headers, query builders, inserted or updated objects, raw error dictionaries,
or returned data.

### Request failure event

Emit an ERROR `request_failed` event for handled server-side exceptions with an
HTTP status of 500 or greater, including `RepositoryUnavailable`,
`RepositoryDataError`, `InvalidQuestion`, and `RUnavailable`. Continue returning
the existing generic public error envelopes.

The event includes:

- the mapped public `outcome` code;
- `error_type` for the top-level exception;
- a bounded cause chain containing exception classes and safe
  `module:function:line` locations; and
- no exception messages, traceback locals, headers, or request/response bodies.

Unexpected exceptions continue to produce a separate failure event followed by
the terminal `request_completed` event. Consolidate this with the new failure
event shape so handled and unhandled 5xx requests are queryable consistently and
do not produce duplicate `request_failed` events.

Supabase-specific text belongs only in the correlated `supabase_operation`
event. This keeps the request-level event safe even when an exception message
contains database or user data.

### Request completion duration

Add `duration_ms` to FastAPI `request_completed` events using the same value as
the existing `total_ms` field. Retain `total_ms` because the authenticated
experiment reporting code consumes it. This additive alias aligns FastAPI with
the R service, the OBS-03 contract, the runbook queries, and existing Grafana
latency panels.

## Redaction and Size Controls

Move reusable redaction behavior behind one production-safe helper used before
values are attached to a `LogRecord` or diagnostic event. Redaction at emission
time is required because tests and alternate handlers may inspect raw log
records before the JSON formatter runs.

The helper must:

- recursively redact authorization, cookie, password, secret, token, API-key,
  and equivalent normalized key names;
- replace configured Supabase, OR JWT, API JWT, and admin access secret values;
- redact compact JWT strings and token-bearing URL fragments in arbitrary text;
- preserve JSON scalar, mapping, and sequence structure; and
- perform UTF-8-safe length limiting with an explicit truncation marker.

Initialize the production sanitizer from validated settings without logging or
serializing the configured secrets. Reuse it from `DiagnosticHub` so production
logs and experiment diagnostics have one redaction policy. Preserve the
diagnostic buffer's bounds, TTL, replay, and subscriber behavior.

The structured formatter remains responsible for producing one compact JSON
object per physical log line. Exception stacks, when present, must be serialized
as JSON arrays or escaped strings rather than multiline output.

## Loki and Grafana Changes

Alloy already parses `level` and `event`, retains malformed records, and keeps
the application JSON as the log line. No new label or collection pipeline is
needed. Confirm the bounded event names appear as the existing `event` label and
that body, operation, error, and correlation values remain parsed JSON fields.

Extend the provisioned dashboard with:

- recent failed `supabase_operation` events showing time, request ID, operation,
  error category/code, message, details, hint, and duration;
- p50 and p95 Supabase operation duration grouped by the parsed `operation`
  field;
- slow Supabase operations using a documented threshold of 500 ms; and
- a request-ID correlation view that shows create input, Supabase operations,
  request failure, R events, and completion in timestamp order.

Update the existing FastAPI duration queries to use `duration_ms`. Continue
querying parsed fields at read time; do not promote `operation`, `request_id`,
`test_id`, error codes, or request-body fields to labels.

Useful acceptance queries should include equivalents of:

```logql
{service="api", event="supabase_operation"}
| json
| outcome="failed"
```

```logql
{service="api"}
| json
| request_id="CONTROLLED_REQUEST_ID"
```

```logql
{service="api", event="assessment_create_received"}
| json
| node_count > 10
```

## Documentation Changes

Update the active OBS-03 plan and observability runbook so the acceptance rule
becomes: no request body may appear in Loki except the documented, bounded
allowlist in `assessment_create_received`. Explicitly state that `user_id` and
`learning_path_id` remain excluded.

Update the backend README to document the new production events and distinguish
them from authenticated experiment diagnostics. Keep OBS-01 and OBS-02 as
historical completed plans and do not rewrite their original body-free policy.

Document that Grafana Editor users with Loki access can see the allowlisted
graph and configuration content for the 14-day Loki retention period.

## Test Plan

### Assessment request logging

- Submit an authorized create request with every optional field populated and
  assert one `assessment_create_received` event contains the exact allowlisted
  values, counts, defaults where applicable, and active request ID.
- Assert serialized production logs do not contain `user_id`,
  `learning_path_id`, authorization, cookies, or configured secrets.
- Configure a low `MAX_GRAPH_NODES`, submit a larger graph, and assert the event
  is emitted before the `422 invalid_graph` completion with the correct full
  node count.
- Submit duplicate nodes and invalid relation endpoints and confirm their
  authorized, schema-valid bodies are logged before domain rejection.
- Submit a body exceeding 32 KiB and verify valid JSON, deterministic digest,
  full counts, preview bounds, omitted counts, and the truncation marker.
- Verify no production body event for answers, player start, question reports,
  admin operations, health checks, GET requests, unauthorized creates, or
  FastAPI body-validation failures.

### Supabase and failure logging

- Cover successful assessment, admin, and KST-configuration operations and
  assert INFO events contain the stable operation, success outcome, duration,
  count, and request correlation.
- Cover PostgREST errors with code/message/details/hint and assert a WARNING
  event is emitted before conversion to `RepositoryUnavailable`.
- Cover HTTPX connection, read-timeout, and built-in timeout failures and assert
  their stable categories and sanitized fields.
- Verify the unique-violation answer path retains its existing behavior while
  still producing the failed operation event.
- Verify `record_supabase_execute` increments once per attempt and the request
  completion aggregate still matches the number and cumulative duration of the
  operation events.
- Trigger repository decoding/invariant failures after a successful Supabase
  response and assert the correlated success operation, `request_failed`, and
  final `request_completed` events make the failure sequence visible.
- Verify active experiments still receive operation events used by reporting,
  while identical normal requests produce Loki-bound production events without
  requiring `X-Experiment-ID`.

### Redaction and observability integration

- Place sentinel secrets, JWTs, token fragments, and sensitive key names in
  create fields and synthetic Supabase errors; assert none appear in raw log
  records, formatted JSON, diagnostic snapshots, or streamed diagnostics.
- Verify all events are single-line valid JSON and retain the schema envelope.
- Validate dashboard JSON and LogQL expressions, including the FastAPI
  `duration_ms` field and all new event types.
- Re-run existing observability-stack, API, repository, diagnostic-reporting,
  and redaction tests to prevent contract regressions.

Run the complete backend suite with the project environment:

```sh
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m pyright
```

Do not complete implementation while Pyright reports errors. Do not suppress
type errors or weaken the Pyright configuration.

## Deployment and Acceptance

No database or persistent-data migration is required. Deploy the API and
Grafana provisioning changes through the existing Compose process, then perform
a controlled create request whose node count is known and which triggers at
least one Supabase call.

Using the returned `X-Request-ID`, verify in Grafana Explore that:

1. one `assessment_create_received` event contains the expected allowlist and
   full counts;
2. each Supabase call has a `supabase_operation` event;
3. any injected dependency failure exposes the sanitized PostgREST or transport
   cause;
4. the terminal completion retains the same request ID and accurate aggregate
   timings/counts;
5. request and dependency latency panels include FastAPI events; and
6. no excluded body, identifier, credential, query string, header, or database
   row appears in Loki.

Confirm the new event volume remains within the existing Docker rotation and
Loki disk monitoring expectations. Supabase successes intentionally add one log
line per execute call; if capacity becomes a concern, address retention or
sampling in a separate plan rather than silently omitting operation failures.

## Decisions and Assumptions

- “The first POST request” means the assessment-creation endpoint, not only the
  first create call after a process restart. Every authorized create attempt
  emits one pre-service event.
- The event is always enabled at the existing INFO level; no new feature flag is
  introduced.
- Full allowlisted content is preferred for normal requests. A bounded preview
  plus full counts and digest is sufficient for unusually large requests.
- The default graph limit remains `MAX_GRAPH_NODES=10`; logging diagnoses limit
  failures but does not alter that limit.
- New fields and event types are additive, so the log schema remains version 1.
- Loki retains these events for the existing 14-day period and Grafana access
  remains restricted to approved operator networks and authenticated accounts.

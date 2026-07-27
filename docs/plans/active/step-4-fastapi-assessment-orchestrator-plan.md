# Step 4 — FastAPI Assessment Orchestrator

## Summary

Implement the complete Python backend vertical slice on top of the Step 2
persistence contracts and Step 3 R API.

- Add the concrete asynchronous Supabase repository, typed R client,
  assessment service, FastAPI application factory, separate OR/player routers,
  health endpoints, permissive authorization seam, and structured timing logs.
- Activate fully covered tests during creation. For missing coverage, persist a
  restart-safe pending graph snapshot, issue one YG order, and let the
  idempotent player start command activate the test once coverage is complete.
- Preserve retry safety: R calculations happen before answer persistence;
  answer insertion, telemetry, and session compare-and-set remain sequential;
  accepted submission IDs replay the persisted current view.
- Do not modify `ATA_kst/`, `TP_kst/`, React, Docker Compose, the deployed
  schema, or pre-pilot JWT authorization.

## Implementation Changes

### Runtime, dependencies, and configuration

- Pin the top-level runtime packages: `fastapi==0.139.2`,
  `uvicorn==0.51.0`, `httpx==0.28.1`, `pydantic-settings==2.14.2`, and
  the architecture-required `supabase==2.31.0`; add
  `pytest-asyncio==1.4.0` for asynchronous tests.
- Add strict environment settings:
  - required `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `R_SERVICE_URL`;
  - `MAX_GRAPH_NODES=10` as the single graph-size setting;
  - `R_MAX_CONNECTIONS=4`;
  - R timeouts: connect `2s`, read `30s`, write `5s`, pool `1s`;
  - readiness timeout `1s` per dependency and Supabase request timeout `10s`.
- Build the application through `create_app(settings, lifespan=...)`. During
  lifespan:
  - create one HTTPX transport and pass it to
    `await acreate_client(...)` through `AsyncClientOptions`;
  - create one R `httpx.AsyncClient` with `base_url`, explicit four-part
    timeout, and
    `Limits(max_connections=n, max_keepalive_connections=n)`;
  - construct the repository, R client, and assessment service in
    `app.state`;
  - close both shared HTTPX transports during shutdown.
- Follow FastAPI's documented
  [lifespan](https://fastapi.tiangolo.com/advanced/events/) and
  [dependency-override](https://fastapi.tiangolo.com/advanced/testing-dependencies/)
  patterns so tests can replace persistence, R, and authorization
  independently.

### Domain and persistence contracts

- Add `PendingGraph` containing the versioned graph hash plus normalized nodes
  and relations.
- Extend `PlayerState` with optional `pending_graph`; missing fields in
  existing version-1 JSON decode as `None`.
  - A preparing session with no cached graph stores `graph_hash=NULL` and a
    non-null pending snapshot.
  - A preparing session may instead reference an already-cached graph and omit
    the snapshot.
  - Active/completed sessions must have a real `graph_hash`, model, posterior,
    and no pending snapshot.
- Extend `ActivationCommand` with the graph hash so activation atomically
  writes `graaf_hash`, model, initial posterior/current question, clears
  `pending_graph`, and changes the status from preparing to active.
- Add `RepositoryUnavailable` separately from `RepositoryDataError`;
  transport/PostgREST failures become unavailable, while malformed persisted
  rows remain data errors.
- Update the mapping layer to:
  - serialize/deserialize `pending_graph`;
  - treat `NULL` or an empty `testi_loogika` object as "no model" for
    preparing rows;
  - provide all query column/filter/update descriptors so Estonian database
    names remain confined to this adapter.

### Graph normalization and caching

- Validate at the API boundary:
  - 1–`MAX_GRAPH_NODES` non-whitespace, exactly unique nodes;
  - relation endpoints present in the node set;
  - method exactly `kst`;
  - unknown request fields rejected.
- Normalize nodes by UTF-8 byte order; collapse duplicate relation pairs and
  sort them by normalized `from`, then `to`. Preserve node text exactly apart
  from rejecting whitespace-only values.
- Hash compact UTF-8 JSON shaped as
  `{"nodes":[...],"relations":[{"from":...,"to":...}]}` using sorted object
  keys, no insignificant whitespace, and no ASCII escaping. Store the
  identifier as `kst-graph-v1:sha256:<hex>`.
- Test hashes across input order changes, duplicate relations, non-ASCII
  Estonian text, and meaningful graph changes. The new prefix ensures old R
  hashes remain untouched.
- If coverage is complete:
  - call R `/model`, supplying cached knowledge states when available;
  - insert newly calculated states with conflict-ignore semantics and reload
    the canonical cache entry;
  - compose the first question and insert the session directly as active.
- If coverage is incomplete:
  - use an existing graph cache row when available;
  - otherwise keep `graaf_hash=NULL` and persist the normalized pending
    snapshot;
  - create a preparing session and one YG order.
- On a later start, build/cache the graph only after coverage provides real
  beta/eta parameters, then activate with one compare-and-set update. This
  implements the selected deferred-graph behavior without placeholder
  parameters or an R contract change.

### Concrete Supabase repository

Implement every `AssessmentRepository` operation with awaited Supabase calls
and strict row decoding:

- Graphs: select by hash; insert with `on_conflict=graaf_hash` and ignore
  duplicates; reload the canonical row.
- Sessions: insert/get; activate only where `staatus=planeerimisel`; mark
  failed only from preparing; reload when a compare-and-set matches no row.
- Coverage: query each node separately with exact equality to avoid
  comma-containing node failures; select the lowest `yp_id` usable item as the
  stable representative.
- Items: filter only by node and usable status, order by `yp_id`, return unused
  items before fallback items, and never filter by course.
- YG: read latest by descending ID; under a per-test process lock, treat both
  pending and processing as in-flight before inserting. Use course `""`,
  cognitive level `"mõistab"`, volume `3`, and only the missing nodes.
- Readiness: perform a bounded lightweight select without mutating data.

Implement answer commits in this exact order:

1. Insert `tulemustepank` with the caller's explicit `vastus_id`.
2. On a unique violation, reload that UUID and distinguish identical recovery
   from payload conflict.
3. Only after a new insert, increment item telemetry with an optimistic
   compare-and-set retry and set `viimane_kasutus`.
4. Update the session only where the path test ID, active status, and JSON
   current-question submission ID all match.
5. If no session row changed, reload it and classify the result as replayed or
   stale.

No correctness-dependent calls are parallelized and no database RPC or
migration is introduced.

### R client and assessment orchestration

- Introduce an async `KstEngine` protocol with `build_model`, `advance`, and
  `is_ready`; provide an HTTPX implementation and deterministic fake.
- Use strict internal request/response DTOs matching the committed R OpenAPI
  contract.
- Translate the established naming mismatch explicitly:
  - R `safety_cap.minimum_above_floor`;
  - Python domain/persistence `safety_cap.responses_above_floor`.
- Treat pool acquisition timeout, other HTTPX timeouts, connection failures,
  non-success R responses, and malformed bodies as `RUnavailable`. Log
  diagnostic class/status without returning internal details.
- Question construction:
  - choose the first unused usable item for R's `next_node`, falling back to
    the first usable item only after all candidates were used;
  - remove blank and duplicate distractors, require a non-empty key and at
    least two distinct options;
  - preserve the prototype's descending numeric/date/time ordering when all
    choices are comparable; otherwise shuffle once using an injected random
    source;
  - assign fresh opaque UUID option IDs and a fresh submission UUID;
  - persist the complete ordered question before returning it.
- Answer processing:
  - return the current view immediately if the submitted ID is already in
    answered history;
  - reject an ID that is neither current nor previously accepted with `409`;
  - resolve the opaque option against the persisted current question, reload
    the item, and score by exact server-side comparison with its answer key;
  - call R `/advance` with response count including this answer;
  - prepare either a new persisted question or a completed profile transition,
    then call `commit_answer`;
  - map applied, recovered, and replayed commits to the repository's returned
    session view; map stale and payload-conflict outcomes to `409`.
- Never expose answer keys, correctness, node identity, posterior, beta/eta,
  knowledge states, configuration, or item telemetry.

## Public Interfaces

Use strict Pydantic DTOs with `extra="forbid"` and stable English error codes.

| Endpoint | Behavior |
|---|---|
| `GET /health/live` | Always `200 {"status":"ok"}` without dependency calls. |
| `GET /health/ready` | Check Supabase and R concurrently with independent one-second bounds; return `200 {"status":"ready"}` or `503` with only ready/unavailable dependency states. |
| `POST /api/v1/tests` | OR auth seam requiring `tests:create`; return `201` with `test_id`, `active`/`preparing`, relative `player_url`, and ordered `missing_nodes`. |
| `GET /api/v1/tests/{test_id}` | OR auth seam requiring `tests:read`; return `preparing`, `active`, `completed`, or `failed`; include feedback only when completed. |
| `POST /api/v1/player/tests/{test_id}/start` | Player auth seam bound to the test; return persisted question/completion, or `202 {"status":"preparing"}` with `Retry-After: 3`; YG `viga` marks the session failed. |
| `POST /api/v1/player/tests/{test_id}/answers` | Accept only `submission_id` and `option_id`; return the next persisted question or final feedback. |

Question output is limited to:

```json
{
  "submission_id": "uuid",
  "item_id": 123,
  "instruction": "...",
  "prompt": "...",
  "stimulus": null,
  "options": [{"id": "opaque-uuid", "text": "..."}]
}
```

Map the five-way R profile into the three player/OR feedback sections:

- `already_mastered = mastered`;
- `learn_next = ready_to_learn + uncertain_ahead`;
- `review = uncertain_prerequisite`;
- include `summary` and
  `confidence_limited = (stop_reason == "safety_cap")`;
- omit `not_yet` and all confidence/posterior internals.

Return `404` for unknown tests; `409` for failed/legacy sessions, stale
submissions, conflicting retries, or unavailable option IDs; `422` for
request-shape validation; and `503` for R/Supabase unavailability. All errors
use `{"error":{"code":"...","message":"..."}}` except FastAPI's standard
validation details.

Define `AuthContext` with `actor_type` (`or` or `player`), `subject`, immutable
scopes, and optional authorized test ID. Separate permissive OR/player
dependencies populate the required scope and test binding without parsing
credentials; health routes have no authorization dependency.

## Health, Timing, and Logging

- Add request middleware that accepts a safe `X-Request-ID` or generates a
  UUID, echoes it in the response, and emits exactly one JSON completion
  event.
- Track metrics in request-local context:
  - total duration;
  - cumulative Supabase and R duration;
  - actual Supabase execute count and R HTTP request count;
  - request ID, optional path `test_id`, HTTP status, and stable outcome code.
- Instrument the common Supabase execute helper and R request helper so nested
  repository operations contribute accurate dependency totals.
- Never log request bodies, authorization headers, service keys, option IDs,
  selected answers, player tokens, or signing material.
- Ensure unhandled exceptions still produce the completion event and a generic
  `500` response.

## Test Plan

- Domain tests:
  - canonical graph/hash behavior and max-node configuration;
  - pending graph serialization/backward-compatible decoding;
  - activation invariants and clearing of pending state;
  - numeric versus shuffled option ordering, stable reloads, duplicate/blank
    choices, and hidden answer data.
- Supabase adapter tests using a mocked HTTP transport:
  - exact filters, ordering, encoded rows, graph conflicts, session activation
    CAS, YG pending/processing deduplication, and readiness;
  - explicit `vastus_id`, unique-conflict recovery, payload conflict,
    telemetry only on first insert, answer/session CAS, replay, and stale
    outcomes;
  - every PostgREST failure mapped without leaking credentials.
- R client tests:
  - exact `/model` and `/advance` payloads, cached-state use,
    configuration-name translation, in-progress/completed mapping, health;
  - connection/read/write/pool timeout, synthetic `PoolTimeout`, non-2xx, and
    malformed responses.
- Service tests with the existing in-memory repository and fake R engine:
  - covered and missing creation, one YG order, restart-safe pending graph, YG
    processing/completion/failure, cached/new graph activation, concurrent
    starts, and stable first-question reload;
  - correct/incorrect scoring, next question, completion and all feedback
    categories;
  - accepted replay without another R call, interrupted-write recovery, stale
    token, changed-option conflict, concurrent duplicate answers, and exactly
    one result;
  - R failure before commit and Supabase failure at each sequential commit
    stage, proving the persisted session does not incorrectly advance.
- API tests through lifespan-aware `TestClient`:
  - exact status codes, schemas, `Retry-After`, router separation,
    authorization overrides, hidden fields, unknown/legacy/failed tests,
    health semantics, and dependency overrides;
  - structured completion log fields, counts/durations, request-ID
    propagation, and secret/header redaction.
- Add an opt-in contract marker using `R_CONTRACT_BASE_URL` to exercise FastAPI
  against the real R service. Keep it out of normal unit tests until Step 6
  supplies the Dockerized service.
- Acceptance commands:
  - `cd backend && source .venv/bin/activate`
  - `python -m pytest`
  - `python -m pyright`
  - `Rscript R/tests/testthat.R`
  - `git diff --exit-code -- ATA_kst TP_kst`

## Assumptions and Defaults

- The selected deferred-graph design and pending `tp_seisund` snapshot are
  authoritative for missing-coverage sessions.
- The deployed graph foreign key and `vastus_id` uniqueness/default match the
  documented schema; Step 4 adds no migration or RPC.
- The pilot runs one FastAPI process. In-process YG locking plus database
  compare-and-set is sufficient; multi-replica creation hardening remains
  deferred.
- PostgREST operations are intentionally not one database transaction.
  Explicit submission IDs and compare-and-set recovery make answer/session
  interruptions retryable; telemetry remains pilot-only.
- Usable item content and answer keys are assumed not to be edited during an
  active assessment.
- Step 5 owns Estonian UI copy and polling jitter; Step 6 owns containers; Step
  7 owns live Supabase/YG verification and operational documentation;
  pre-pilot bearer authorization remains outside Step 4.

## Implementation Progress

Implement Step 4 through the following sequential, independently verified
checkpoints. Keep the full plan above as the acceptance specification for the
completed vertical slice.

- [ ] **1. Foundation and domain evolution**
  - Pin runtime and test dependencies and add strict application settings.
  - Add `PendingGraph`, activation changes, repository exception types,
    graph canonicalization, and versioned hashing.
  - Update Supabase mappings, query descriptors, the in-memory repository,
    factories, and focused domain tests.
  - Configure Pyright to use the project's Python 3.14 virtual environment so
    the documented acceptance command works without extra CLI flags.

- [ ] **2. R client and question construction**
  - Add strict R request/response DTOs, the asynchronous `KstEngine` protocol,
    its HTTPX implementation, and a deterministic fake.
  - Implement configuration-name translation, option validation and ordering,
    opaque identifiers, and hidden-answer response shaping.
  - Cover exact payloads, response mapping, timeouts, connection failures,
    non-success responses, and malformed bodies.

- [ ] **3. Supabase repository reads and preparation writes**
  - Add the shared instrumented execute helper and concrete repository
    operations for graphs, sessions, coverage, items, YG orders, and readiness.
  - Implement strict decoding, conflict-ignore graph caching, preparation
    compare-and-set behavior, stable selection, and YG deduplication.
  - Cover exact filters, ordering, encoded rows, readiness, and unavailable
    versus malformed-data failures with a mocked HTTP transport.

- [ ] **4. Supabase answer commit protocol**
  - Implement explicit answer UUID insertion, unique-conflict recovery,
    optimistic telemetry updates, and session compare-and-set transitions in
    the required sequential order.
  - Classify applied, recovered, replayed, stale, and payload-conflict results.
  - Cover interrupted writes, retries, concurrency, exact-once telemetry, and
    failure at every persistence stage.

- [ ] **5. Assessment creation and start service**
  - Implement covered and missing-coverage creation, restart-safe pending
    graphs, graph caching, and one YG order.
  - Implement YG polling and failure, cached or newly built graph activation,
    first-question persistence, and idempotent/concurrent starts.
  - Cover stable reloads and every preparing-to-active transition.

- [ ] **6. Assessment answer and completion service**
  - Implement accepted replay, stale-token detection, server-side scoring, R
    advancement, next-question transitions, completion, and feedback mapping.
  - Preserve retry safety across R and repository failures and prevent hidden
    assessment data from reaching public responses.
  - Cover correct and incorrect answers, all feedback categories, duplicate
    submissions, option conflicts, concurrent answers, and completion.

- [ ] **7. FastAPI application and operational behavior**
  - Add the application factory, lifespan-managed clients, dependency
    overrides, permissive authorization seams, strict DTOs, separate routers,
    and stable error mapping.
  - Add liveness/readiness, request IDs, dependency timing, structured
    completion logs, exception handling, and resource shutdown.
  - Complete API, logging, redaction, health, optional R contract, and full
    acceptance tests, including Pyright, R tests, and protected-directory
    verification.

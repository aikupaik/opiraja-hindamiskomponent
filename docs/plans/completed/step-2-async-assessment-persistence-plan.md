# Step 2 — Async Assessment Persistence Foundation

## Summary

Establish the typed persistence boundary required by the later FastAPI implementation.

- Introduce immutable English domain models and one asynchronous,
  domain-focused `AssessmentRepository` protocol.
- Centralize all Estonian Supabase table/column/status mappings, especially
  `submission_id ↔ vastus_id`.
- Add a deterministic, concurrency-safe in-memory repository for backend unit
  tests.
- Do not modify the database, implement FastAPI routes, create the concrete
  Supabase repository, or touch `ATA_kst/`/`TP_kst/`.

## Implementation Changes

### Domain types and persistence mapping

Create framework-independent modules under `backend/app/`, using frozen,
slotted dataclasses, `UUID`, tuples, `StrEnum`, and strict type annotations.

- Define identifiers and enums for test IDs, submission IDs, item IDs,
  assessment/session status, YG status, method, stop reason, and answer-commit
  outcome.
- Model:
  - graph relations, definitions, cached knowledge states, and graph cache
    entries;
  - assessment items, including instruction, prompt, stimulus, answer key,
    distractors, BLIM parameters, and usage telemetry;
  - KST model/configuration and final profile aligned with the committed R
    OpenAPI contract;
  - version-1 player state containing posterior, answered-item history, and
    optional current question;
  - current questions containing `submission_id`, item/node identity, and
    immutable ordered opaque option IDs/text;
  - sessions, YG orders, answer records, activation commands, answer
    transitions, and commit results.
- New sessions always persist `tp_seisund.schema_version = 1`. Rows without
  that version remain readable as legacy sessions but cannot be activated or
  resumed.
- Add one pure Supabase mapping module. Estonian names must not escape it:
  - `submission_id ↔ vastus_id`;
  - `item_id ↔ yp_id`, `learning_path_id ↔ rada_id`, and other documented
    columns;
  - domain statuses ↔ `planeerimisel`, `aktiivne`, `lõpetatud`, `katkenud`;
  - YG statuses ↔ `ootel`, `tootmises`, `tehtud`, `viga`;
  - model/state/profile objects ↔ their JSONB columns.
- Every player answer encoder must explicitly write
  `vastus_id = str(submission_id)`; it must never rely on the database default.
  Unknown statuses, malformed UUIDs, or unsupported JSON schema versions
  produce a repository data error rather than partially populated models.
- Do not read or write the undocumented `testisessioonid.kursus`; course
  belongs only to YG order creation and is never part of item eligibility.

### `AssessmentRepository` protocol

Define one async `Protocol` with domain operations rather than generic table
CRUD:

- Graph cache:
  - get a cached graph by hash;
  - insert if absent and return the canonical stored entry.
- Sessions:
  - create and retrieve a session;
  - idempotently activate a preparing session with its R model and persisted
    first question;
  - mark a session failed;
  - expose a lightweight readiness check for Step 4.
- Item bank:
  - resolve usable coverage/parameters for ordered nodes;
  - list usable items for a node without a course filter;
  - retrieve one item by ID.
- YG:
  - retrieve the latest order;
  - create an order only when no pending order exists.
- Answers:
  - commit an answer using the expected current `submission_id`, answer record,
    next player state, and optional final profile.

Lock the answer-commit semantics in the protocol documentation:

1. Insert the answer using explicit `vastus_id`.
2. Increment item usage only when that insert is new.
3. Compare-and-set the session against the expected current submission token.
4. Return:
   - `applied` for a new insert and successful transition;
   - `recovered` when an identical previously inserted answer finishes an
     interrupted session transition without incrementing telemetry again;
   - `replayed` when the session already advanced, returning its current view;
   - `stale` when the token was never accepted and is no longer current;
   - `payload_conflict` when an existing submission UUID belongs to different
     answer data.
5. Keep these operations sequential; the later concrete adapter must not
   parallelize correctness-dependent writes.

### Async in-memory fake

Add a reusable fake under `backend/tests/fakes/` that structurally satisfies
`AssessmentRepository`.

- Store graphs, sessions, items, YG orders, and answers in typed dictionaries
  while returning defensive copies.
- Protect mutating methods with one `asyncio.Lock` so insert-if-absent, YG
  deduplication, activation, and answer compare-and-set behavior are atomic
  within tests.
- Enforce the same unique submission-ID and state-transition rules as the
  repository contract.
- Provide test-only seed helpers, read-only snapshots, call records, and
  one-shot method failure injection without adding those helpers to the
  production protocol.
- Keep selection deterministic: preserve declared node/item order, use the
  first unused item, and fall back to the first usable item only after all
  candidates have been used.

## Test Plan

- Mapping tests prove exact round trips for every table-facing model and
  specifically assert:
  - `submission_id` is serialized only as `vastus_id`;
  - the UUID is always explicitly included in answer inserts;
  - JSONB state/model/profile values remain structured JSON rather than
    double-encoded strings;
  - course is absent from session and item-eligibility queries.
- Protocol/fake tests cover:
  - graph insert-if-absent races;
  - session creation, legacy-session rejection, idempotent activation, and
    failure transitions;
  - covered and missing nodes, usable-item filtering, and stable ordering;
  - one pending YG order per test;
  - new answer application, identical retry recovery, completed retry replay,
    stale token, conflicting payload, and exactly-once telemetry;
  - injected repository failures leaving session state unchanged where
    required;
  - mutation isolation of seeded and returned objects.
- Run from `backend/` with the project virtual environment:
  - `python -m pytest`
  - `python -m pyright`
- Acceptance requires both commands to pass with strict Pyright and without
  `# type: ignore`, plus
  `git diff --exit-code -- ATA_kst TP_kst`.

## Assumptions and Deferred Work

- Treat the deployed schema as confirmed by the project owner:
  `tulemustepank.vastus_id` is `uuid NOT NULL DEFAULT gen_random_uuid()` and
  has a single-column unique constraint. Step 2 performs no additional live
  verification.
- The concrete `SupabaseAssessmentRepository`, `supabase==2.31.0` client
  wiring/lifecycle, FastAPI dependencies, services, routes, and R HTTP client
  remain Step 4.
- Step 2 may add pure row encoders/decoders, but it does not issue Supabase
  network requests during normal unit tests.
- No schema migration is expected, and existing database rows are preserved.
- Existing unrelated working-tree changes, including the moved Step 1 plan,
  remain untouched.

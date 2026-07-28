# Assessment orchestrator backend

The backend is a FastAPI application that coordinates an adaptive Knowledge
Space Theory (KST) assessment. It is the boundary between:

- the õpiraja (OR) service that creates and monitors assessments;
- the player that starts an assessment and submits answers;
- Supabase, which stores graphs, sessions, items, YG orders, and answers; and
- the internal stateless R service, which builds KST models and advances the
  posterior distribution after each answer.

The backend owns orchestration, validation, question construction, answer
scoring, persistence, retry safety, and public response shaping. It does not
calculate KST models itself, generate missing questions itself, or expose
answer keys and KST internals to API clients.

## Assessment lifecycle

1. OR submits a graph through `POST /api/v1/tests`.
2. The graph is validated, normalized, and assigned a deterministic
   `kst-graph-v1:sha256:...` hash.
3. R builds the v2 KST model and returns its derived safety cap.
4. The backend requires `ceiling(safety_cap / node_count)` distinct usable
   items per node and orders each node's exact deficit from YG.
5. Once every target is met, the backend snapshots a fixed session pool and
   asks R to select the first ordered candidate. Partial generation remains
   `preparing`; later polls recount the bank and order only the remainder.
6. For every answer, the backend resolves the opaque option ID against the
   persisted question, scores it using the persisted correct option, asks R to
   advance with that item's concrete parameters and unused candidates, and
   atomically advances the persisted session using
   the question's submission ID as a compare-and-set token.
7. When R completes the assessment, its five-way profile is reduced to the
   three public feedback groups: `already_mastered`, `learn_next`, and
   `review`.

New sessions use v2 model and player-state documents. Completed v1 sessions
remain readable; nonterminal v1 sessions cannot be started or answered.

## Running the API

The project requires Python 3.14 and uses the virtual environment at
`backend/.venv`.

```sh
cd backend
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn app.main:create_app --factory --reload --env-file ../.env
```

Copy the repository-level `.env.example` to `.env` and configure these
required values:

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL. |
| `SUPABASE_SERVICE_KEY` | Server-side service-role credential. Never expose it to a browser. |
| `R_SERVICE_URL` | Base URL of the internal stateless R KST service. |

Optional settings and their defaults:

| Variable | Default | Purpose |
|---|---:|---|
| `MAX_GRAPH_NODES` | `10` | Maximum nodes accepted in a test graph. |
| `R_MAX_CONNECTIONS` | `4` | R HTTP connection and keep-alive pool size. |
| `R_CONNECT_TIMEOUT_SECONDS` | `2` | R connection timeout. |
| `R_READ_TIMEOUT_SECONDS` | `30` | R response-read timeout. |
| `R_WRITE_TIMEOUT_SECONDS` | `5` | R request-write timeout. |
| `R_POOL_TIMEOUT_SECONDS` | `1` | R connection-pool acquisition timeout. |
| `READINESS_TIMEOUT_SECONDS` | `1` | Independent timeout for each readiness dependency. |
| `SUPABASE_REQUEST_TIMEOUT_SECONDS` | `10` | Supabase/PostgREST request timeout. |

FastAPI exposes generated OpenAPI documentation at `/docs` and `/redoc` while
the application is running.

## Public API

All request DTOs reject unknown fields. Except for FastAPI's standard request
validation response, application errors use:

```json
{
  "error": {
    "code": "assessment_conflict",
    "message": "Assessment state conflicts with this operation."
  }
}
```

Every response has an `X-Request-ID`. A safe caller-provided `X-Request-ID` is
echoed; otherwise the backend creates one.

### Health

| Method and path | Response |
|---|---|
| `GET /health/live` | Always returns `200 {"status":"ok"}` without querying dependencies. |
| `GET /health/ready` | Checks Supabase and R concurrently. Returns `200` when both are ready, otherwise `503`. |

Readiness response:

```json
{
  "status": "ready",
  "dependencies": {
    "supabase": "ready",
    "r": "ready"
  }
}
```

### OR endpoints

The OR authorization seam currently supplies a permissive phase-one identity.
It is deliberately replaceable. Creating a test requires the `tests:create`
scope and reading one requires `tests:read`.

#### `POST /api/v1/tests`

Creates either an immediately active assessment or a preparing assessment
whose missing items have been ordered from YG. The response is `201` and
includes a `Location: /api/v1/tests/{test_id}` header.

Request:

```json
{
  "user_id": "user-123",
  "learning_path_id": "path-456",
  "nodes": ["Liitmine", "Lahutamine"],
  "relations": [
    {"from": "Liitmine", "to": "Lahutamine"}
  ],
  "course": "Matemaatika",
  "goal": "Check prerequisite knowledge",
  "method": "kst",
  "cognitive_level": "mõistab"
}
```

`user_id` and `learning_path_id` must be non-empty. The graph must have
between 1 and `MAX_GRAPH_NODES` unique, non-whitespace nodes, and every
relation endpoint must occur in `nodes`. Duplicate relations are collapsed.
Only the `kst` method is supported. `relations`, `course`, `goal`, `method`,
and `cognitive_level` are optional.

Response:

```json
{
  "test_id": "00000000-0000-0000-0000-000000000000",
  "status": "preparing",
  "player_url": "/test/00000000-0000-0000-0000-000000000000",
  "missing_nodes": ["Lahutamine"]
}
```

`status` is `active` or `preparing`. `missing_nodes` preserves normalized node
order and is empty for an active assessment.

#### `GET /api/v1/tests/{test_id}`

Returns the persisted status without starting or advancing the assessment.
The status is `preparing`, `active`, `completed`, or `failed`. A completed
response also includes public feedback:

```json
{
  "status": "completed",
  "feedback": {
    "already_mastered": ["Liitmine"],
    "learn_next": ["Lahutamine"],
    "review": [],
    "summary": "Assessment completed.",
    "confidence_limited": false
  }
}
```

### Player endpoints

The player authorization seam is currently permissive and binds the generated
identity to the `test_id` in the path. Public player responses never contain
the answer key, correctness, graph node identity, posterior, BLIM parameters,
knowledge states, model configuration, or item telemetry.

#### `POST /api/v1/player/tests/{test_id}/start`

Starts a prepared assessment or returns its already persisted current view.
The operation is idempotent.

- `200` with `status: "active"` and the current question when the assessment
  can run;
- `200` with `status: "completed"` and feedback when it has already finished;
- `202 {"status":"preparing"}` with `Retry-After: 3` while item generation is
  still outstanding; or
- `409` if preparation failed or the session uses an unsupported legacy state.

An active question has this exact public shape:

```json
{
  "status": "active",
  "question": {
    "submission_id": "00000000-0000-0000-0000-000000000000",
    "item_id": 123,
    "instruction": "Choose one answer.",
    "prompt": "What is 2 + 2?",
    "stimulus": null,
    "options": [
      {"id": "opaque-option-id", "text": "4"},
      {"id": "another-opaque-id", "text": "3"}
    ]
  }
}
```

#### `POST /api/v1/player/tests/{test_id}/answers`

Submits one answer:

```json
{
  "submission_id": "00000000-0000-0000-0000-000000000000",
  "option_id": "opaque-option-id"
}
```

The response is the next `active` question or the `completed` feedback view.
The submission UUID identifies the exact persisted question. Retrying an
accepted submission returns the current persisted view without advancing R or
incrementing item usage again. A stale UUID, a conflicting retry, or an option
ID that does not belong to the current question returns `409`.

### Status codes

| Status | Meaning |
|---:|---|
| `200` | Successful read, start, answer, liveness, or readiness request. |
| `201` | Assessment created. |
| `202` | Assessment is still preparing; poll after the `Retry-After` interval. |
| `403` | Authorization dependency denied the operation. |
| `404` | Assessment does not exist. |
| `409` | Persisted state conflicts with the requested operation. |
| `422` | Request or graph validation failed. |
| `503` | Supabase or the R service is unavailable. |

## Internal dependencies and persistence

The R adapter calls the internal KST v2 endpoints:

- `GET /health`;
- `POST /internal/v2/kst/model`;
- `POST /internal/v2/kst/select`; and
- `POST /internal/v2/kst/advance`.

The Supabase mapping layer is the only production module that knows the
Estonian table and column names. It maps the domain to:

- `graafid_kst` for normalized graphs and cached knowledge states;
- `testisessioonid` for session, model, player state, and final profile;
- `ylesandepank` for usable items, answer keys, BLIM parameters, and usage
  telemetry;
- `tulemustepank` for submitted answers; and
- `yg_tellimused` for missing-item generation orders.

Answer persistence is intentionally sequential and retry-safe:

1. insert the answer with the caller's explicit submission UUID;
2. increment item telemetry only for a newly inserted answer;
3. compare-and-set the active session against its current submission UUID;
4. recover an interrupted identical write, replay an already accepted write,
   or classify stale and conflicting attempts without advancing incorrectly.

These PostgREST calls are not one database transaction. The explicit
submission token and persisted player state provide the recovery mechanism.

## Module responsibilities

### Application modules

| Module | Responsibility |
|---|---|
| `app/main.py` | Creates the FastAPI application; constructs and closes shared Supabase and HTTPX clients during lifespan; registers routers and exception mappings; adds request-ID middleware and one structured completion log per request. |
| `app/config.py` | Defines strict environment-backed settings, required service credentials/URLs, limits, and timeout defaults. |
| `app/observability.py` | Holds request-local Supabase/R timing and request-count metrics accumulated by adapters and emitted by middleware. |
| `app/api/auth.py` | Defines the replaceable OR/player authorization boundary, immutable auth context, scope checks, and current permissive phase-one dependencies. |
| `app/api/dependencies.py` | Retrieves configured objects from `app.state` and supports independent FastAPI dependency overrides in tests. |
| `app/api/dtos.py` | Defines strict public request/response DTOs and maps service results to OR-safe and player-safe response unions. |
| `app/api/health_routes.py` | Implements dependency-free liveness and concurrently bounded Supabase/R readiness checks. |
| `app/api/or_routes.py` | Implements assessment creation and OR status routes, including scopes and the creation `Location` header. |
| `app/api/player_routes.py` | Implements idempotent player start/polling and answer-submission routes. |
| `app/domain/models.py` | Defines immutable typed domain IDs, enums, graph/item/model/session/player-state/profile values, transition commands, and answer-commit outcomes. |
| `app/domain/graphs.py` | Validates and deterministically normalizes graph inputs, creates canonical UTF-8 JSON, computes versioned SHA-256 graph IDs, and creates pending snapshots. |
| `app/domain/repository.py` | Declares the asynchronous domain-focused persistence protocol and separates unavailable storage from malformed persisted data. |
| `app/integrations/r_dtos.py` | Defines strict private Pydantic DTOs for the internal R KST v1 HTTP contract. |
| `app/integrations/kst_engine.py` | Defines the calculation-engine protocol and its HTTPX adapter; maps domain values to/from R DTOs, checks R readiness, records timing, and converts transport or contract failures to `RUnavailable`. |
| `app/persistence/supabase_mapping.py` | Centralizes all Estonian schema names, filters, updates, enum translations, and strict row/JSONB encoding and decoding. |
| `app/persistence/supabase_repository.py` | Implements the repository protocol with awaited PostgREST operations, graph caching, session compare-and-set transitions, deterministic item lookup, YG deduplication, readiness, and idempotent answer commits. |
| `app/services/assessment.py` | Orchestrates creation, deferred activation, server-side scoring, R advancement, persistence transitions, public views, and final feedback mapping. |
| `app/services/questions.py` | Validates item choices, orders comparable numeric/date/time values or shuffles other choices once, creates opaque option/submission IDs, and strips server-only data from player output. |
| `app/__init__.py` and package `__init__.py` files | Mark packages and expose selected stable imports; they contain no orchestration or infrastructure behavior. |

### Backend support files

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Declares Python 3.14, strict Pyright settings, the local `.venv`, and the opt-in `r_contract` pytest marker. |
| `requirements.txt` | Pins production FastAPI, HTTPX, settings, Supabase, and Uvicorn dependencies. |
| `requirements-dev.txt` | Extends production dependencies with Pyright, pytest, pytest-asyncio, and formatting/development tools. |
| `tests/factories.py` | Builds consistent domain fixtures shared across tests. |
| `tests/fakes/assessment_repository.py` | Provides a deterministic, concurrency-safe in-memory implementation of the repository contract with seeding, snapshots, call recording, and failure injection. |
| `tests/fakes/kst_engine.py` | Provides a deterministic fake calculation engine and records model/advance calls. |
| `tests/test_foundation.py` | Covers settings, graph normalization/hashing, graph validation, and versioned pending-state compatibility. |
| `tests/test_supabase_mapping.py` | Covers exact database mappings, explicit answer UUIDs, structured JSONB, legacy data, and strict malformed-row rejection. |
| `tests/test_supabase_repository.py` | Covers query filters/order, caching, compare-and-set behavior, YG deduplication, sequential answer commits, concurrency, and failure classification. |
| `tests/test_in_memory_repository.py` | Verifies the test repository conforms to production persistence and concurrency semantics. |
| `tests/test_kst_engine.py` | Covers exact R payload mapping, model/advance variants, readiness, timeouts, HTTP failures, and malformed R responses. |
| `tests/test_questions.py` | Covers safe option construction, ordering/shuffling, opaque IDs, invalid items, and hidden answer metadata. |
| `tests/test_assessment_service.py` | Covers the complete creation, preparation, activation, answer, retry, completion, feedback, and dependency-failure workflows. |
| `tests/test_api.py` | Covers public schemas/status codes, router and authorization seams, health behavior, dependency overrides, resource shutdown, request IDs, logging, and redaction. |
| `tests/test_r_contract.py` | Provides an opt-in readiness contract check against a real R service configured with `R_CONTRACT_BASE_URL`. |

## Verification

Run the backend unit and static-type checks from the backend virtual
environment:

```sh
cd backend
source .venv/bin/activate
python -m pytest
python -m pyright
```

To include the opt-in contract check against a running R service:

```sh
R_CONTRACT_BASE_URL=http://127.0.0.1:8000 python -m pytest -m r_contract
```

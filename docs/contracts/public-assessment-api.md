# Public Assessment API Contract

## Status and authority

This document is the authoritative behavioral contract for the public OR and
test-player assessment flow before JWT enforcement. FastAPI's generated OpenAPI
schema is the machine-readable representation of the request and response
models. Backend contract tests enforce wire behavior that cannot be expressed
fully in OpenAPI, including state-dependent status codes, retry semantics,
headers, and hidden fields.

If this document, generated OpenAPI, and tests disagree, treat the disagreement
as a defect. Change the intended contract here first, then update code, OpenAPI
metadata, tests, and integration documentation in the same change.

This contract covers:

- `POST /api/v1/tests`;
- `GET /api/v1/tests/{test_id}`;
- `POST /api/v1/player/tests/{test_id}/start`; and
- `POST /api/v1/player/tests/{test_id}/answers`.

Admin endpoints, the internal R service, persistence schemas, and the future
JWT issuance/login endpoints are outside this contract.

## Cross-cutting rules

### Transport and identifiers

- Request and response bodies use JSON unless an error has no application
  body, such as an Nginx rejection.
- `test_id` and `submission_id` are UUID identifiers. They are not
  credentials. UUIDs in successful JSON responses use the canonical hyphenated
  string form.
- `option_id` is an opaque, non-empty string scoped to the current persisted
  question. Clients must not derive meaning from it.
- Public request DTOs reject unknown fields.
- String values are not generally trimmed by the API. Graph nodes must contain
  non-whitespace content, but otherwise retain their exact text. Integrators
  should send already normalized identifiers and labels.
- Every application response carries `X-Request-ID`. A caller-supplied value is
  retained only when it matches the backend's safe request-ID format;
  otherwise the backend generates a UUID.

### Authorization seam

The pre-JWT implementation remains restricted to the controlled development
environment:

- OR requests use the `tests:create` or `tests:read` scope as specified per
  route.
- Player requests use `tests:play` and are logically bound to the path
  `test_id`.
- The current dependencies supply permissive OR/player identities when no
  recognized admin credential is present. The bearer header is therefore
  optional in this phase, which generated OpenAPI represents as either bearer
  authentication or anonymous access.
- A valid admin credential remains a distinct profile with no `tests:*`
  scopes. Routes used by the internal simulation explicitly accept an admin
  actor with `admin:simulation` as a privileged exception: create, status
  read, player start, and player answer. Future OR/player routes are strict by
  default and must opt in separately if that exception is intended.
- `X-Experiment-ID` is correlation metadata, not authorization. It is honored
  only for a valid UUID on authenticated admin-simulation create, start, and
  answer calls. Capturing requires `admin:simulation`; streaming or reporting
  retained diagnostics independently requires `admin:diagnostics`.
- A dependency-supplied valid identity without the required actor, scope, or
  test binding receives `403` before assessment processing.

The permissive behavior is not approval for public exposure. JWT authorization
and enforced edge controls remain mandatory pilot gates.

### Public data boundary

Player responses may contain only the current public question or final public
feedback. They never contain answer keys, correctness, graph-node identity,
posterior values, candidate metadata, BLIM parameters, knowledge states, model
configuration, or item telemetry.

The pre-JWT player link is the relative path `/test/{test_id}`. The API route,
not the assessment domain service, owns construction of this presentation URL.
The future fragment form `/test/{test_id}#token=<token>` is reserved for JWT
work. URL fragments and query parameters are not backend credentials in this
phase.

## Shared response models

### Question view

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

`stimulus` is a string or `null`. `options` preserves the order persisted when
the question was created. Reloading or calling `start` again must not reshuffle
it.

### Completed feedback

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

The three arrays contain graph-node labels. `summary` is a string or `null`.
`confidence_limited` is true when completion was caused by insufficient usable
item inventory rather than the normal confidence or safety-cap conditions.

## `POST /api/v1/tests`

Creates one assessment and requires the logical scope `tests:create`.

### Request

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

| Field | Required | Contract |
|---|---|---|
| `user_id` | yes | String with at least one character. |
| `learning_path_id` | yes | String with at least one character. |
| `nodes` | yes | Array of 1 through `MAX_GRAPH_NODES` exact, unique, non-whitespace strings. |
| `relations` | no | Array of `{from,to}` objects; defaults to `[]`. Both endpoints must occur exactly in `nodes`. Duplicate pairs collapse during normalization. |
| `course` | no | String; defaults to `""`. Used when missing item inventory creates a YG order. |
| `goal` | no | String or `null`; defaults to `null`. |
| `method` | no | Must be `"kst"`; defaults to `"kst"`. |
| `cognitive_level` | no | String; defaults to `"mõistab"`. |

Graph normalization sorts nodes and relations by their UTF-8 byte order. It
does not trim node text. The public boundary does not add further cycle or
self-relation validation beyond the rules above.

### Success

Returns `201 Created` and:

```http
Location: /api/v1/tests/{test_id}
```

```json
{
  "test_id": "00000000-0000-0000-0000-000000000000",
  "status": "preparing",
  "player_url": "/test/00000000-0000-0000-0000-000000000000",
  "missing_nodes": ["Lahutamine"]
}
```

`status` is `active` when the fixed session item pool and first question were
created immediately. It is `preparing` when missing usable items were ordered.
`missing_nodes` uses normalized graph-node order and is empty for `active`.

Creating a test is not idempotent: each successful request creates a new
`test_id`.

### Failures

- `403`: the authorization context lacks `tests:create` or is not an OR/admin
  actor.
- `422`: request DTO validation failed, or the graph violated graph-validation
  rules.
- `503`: Supabase or R is unavailable; no successful test link is returned.
- `500`: persisted or internal dependency data violated an invariant.

## `GET /api/v1/tests/{test_id}`

Reads persisted status without starting or advancing the assessment and
requires `tests:read`.

### Success

Returns `200 OK` with exactly one state:

```json
{"status": "preparing"}
```

```json
{"status": "active"}
```

```json
{"status": "failed"}
```

or the shared completed-feedback model. The OR status response does not include
the current player question.

### Failures

- `403`: the authorization context lacks `tests:read` or is not an OR/admin
  actor.
- `404`: no assessment exists for `test_id`.
- `409`: a nonterminal legacy session cannot be represented by the current
  assessment flow.
- `422`: the path value is not a UUID; this uses FastAPI's validation response.
- `503`: persistence is unavailable.
- `500`: persisted data violated an invariant.

## `POST /api/v1/player/tests/{test_id}/start`

Returns or prepares the current player view. It requires `tests:play` bound to
the same `test_id`. It has no request body and is idempotent.

### Success and preparation

- `200 OK` returns the shared question view when active.
- `200 OK` returns the shared completed-feedback view when already completed.
- `202 Accepted` returns the following body while item generation remains
  outstanding:

  ```json
  {"status": "preparing"}
  ```

  The response includes `Retry-After: 3`. A player should wait at least that
  many seconds, add fresh positive jitter, and call `start` again. Polling is
  the only operation that may turn a prepared session active and persist its
  first question.

Repeated calls for an active or completed session return its current persisted
view and do not create a new question or advance assessment state.

### Failures

- `403`: the authorization context lacks `tests:play`, has the wrong actor, or
  is bound to another test.
- `404`: no assessment exists for `test_id`.
- `409`: preparation failed, the session is in an unsupported state, or a
  nonterminal legacy session cannot be resumed.
- `422`: the path value is not a UUID; this uses FastAPI's validation response.
- `503`: Supabase or R is unavailable. The client may retry `start`.
- `500`: persisted or dependency data violated an invariant.

## `POST /api/v1/player/tests/{test_id}/answers`

Submits the answer to the current persisted question. It requires
`tests:play` bound to the same `test_id`.

### Request

```json
{
  "submission_id": "00000000-0000-0000-0000-000000000000",
  "option_id": "opaque-option-id"
}
```

Both fields are required. `submission_id` must be a UUID and `option_id` must
contain at least one character. Unknown fields are rejected.

### Success

Returns `200 OK` with either the next shared question view or shared completed
feedback.

The accepted `submission_id` is the idempotency and compare-and-set token for
that persisted question:

- The first accepted request records one result and advances the persisted
  session once.
- A later replay of an already accepted `submission_id` returns the session's
  current persisted view without calling R, inserting another result, or
  incrementing item usage. Once accepted, the replayed `option_id` is not
  re-evaluated.
- If the request fails with `503` and the caller cannot know whether the commit
  completed, it must retry with the same `submission_id` and `option_id`.

### Failures

- `403`: the authorization context lacks `tests:play`, has the wrong actor, or
  is bound to another test.
- `404`: no assessment exists for `test_id`.
- `409`: the assessment is not active; the submission is stale; the option is
  not in the current question; a concurrent commit won; or a nonterminal legacy
  session cannot be resumed.
- `422`: path/body validation failed; this uses FastAPI's validation response.
- `503`: Supabase or R is unavailable. Assessment state must not be advanced
  unsafely, and the same submission identifiers remain retryable.
- `500`: persisted or dependency data violated an invariant.

The answer endpoint never returns `202` or a `preparing` response.

## Error formats

Application/domain failures use a stable, generic envelope:

```json
{
  "error": {
    "code": "assessment_conflict",
    "message": "Assessment state conflicts with this operation."
  }
}
```

| Status | Application error code |
|---:|---|
| `403` | `forbidden` |
| `404` | `assessment_not_found` |
| `409` | `assessment_conflict` |
| `422` graph validation | `invalid_graph` |
| `503` Supabase | `supabase_unavailable` |
| `503` R | `r_unavailable` |
| `500` | `internal_error` |

FastAPI request/path validation deliberately retains FastAPI's standard `422`
body with a top-level `detail` array. It is the sole exception to the
application error envelope. Clients should branch first on HTTP status and
then accept either documented `422` shape. Internal exception messages and
secrets are never returned in the application envelope.

The future JWT phase adds generic `401` failures for missing or invalid bearer
credentials and preserves `403` for a valid but insufficient or cross-test
credential. That behavior is not active in this pre-JWT contract.

## OpenAPI and compatibility

FastAPI generates OpenAPI from the route decorators and Pydantic DTOs. For
these four operations it must describe:

- the exact successful response unions;
- `202` only on player `start`, with `PlayerPreparingResponse`;
- application error models for `403`, `404`, `409`, `500`, and `503` where the
  route can produce them;
- FastAPI's standard validation `422`; and
- optional bearer authentication during the permissive pre-JWT phase.

The public Nginx deployment may block `/docs`, `/redoc`, and `/openapi.json`.
That exposure policy does not change the generated schema's role as the
machine-readable development and test contract.

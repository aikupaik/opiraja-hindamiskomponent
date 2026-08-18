# OR service API handover

This guide is for the external õpiraja (OR) service. The API base URL is the
deployed backend origin, for example `https://assessment.example`. Keep the
OR signing secret private and share it with the backend operator out of band.

## 1. Create an OR bearer token

Sign a short-lived HS256 JWT with the same `OR_JWT_SECRET` configured on the
backend. The token must contain exactly these claims:

```json
{
  "iss": "<OR_JWT_ISSUER>",
  "aud": "assessment-api",
  "sub": "or-service-name",
  "scope": "tests:create tests:read tests:launch",
  "iat": 1785920000,
  "exp": 1785920300
}
```

Use integer Unix timestamps. `exp - iat` must not exceed the backend's
`OR_JWT_MAX_LIFETIME_SECONDS` (300 seconds by default). `scope` is one
space-separated canonical string: no leading/trailing spaces, repeated spaces,
or duplicate scopes.

Send the compact token on every OR request:

```http
Authorization: Bearer <or-jwt>
```

The repository contains a runnable example at
`.tmp/generate_or_jwt.py`. It reads `OR_JWT_SECRET`, `OR_JWT_ISSUER`, and the
optional lifetime setting from the repository `.env` file and prints only the
token:

```sh
backend/.venv/bin/python .tmp/generate_or_jwt.py
```

Do not commit the generated token or put it in logs, URLs, or shell history.

## 2. Create an assessment

`POST /api/v1/tests` requires `tests:create`.

```sh
curl --fail-with-body -X POST "$API_BASE_URL/api/v1/tests" \
  -H "Authorization: Bearer $OR_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "user-123",
    "learning_path_id": "path-456",
    "nodes": ["Liitmine", "Lahutamine"],
    "relations": [{"from": "Liitmine", "to": "Lahutamine"}],
    "course": "Matemaatika",
    "goal": "Check prerequisite knowledge",
    "method": "kst",
    "cognitive_level": "mõistab"
  }'
```

Required fields are `user_id`, `learning_path_id`, and `nodes`. `nodes` must
contain 1–`MAX_GRAPH_NODES` unique, non-whitespace strings. Relation endpoints
must be present in `nodes`. `method` currently supports only `kst`.

A successful request returns `201 Created`, a `Location` header, and:

```json
{
  "test_id": "00000000-0000-0000-0000-000000000000",
  "status": "preparing",
  "player_url": "https://player.example/test/00000000-0000-0000-0000-000000000000#token=<player-jwt>",
  "missing_nodes": ["Lahutamine"]
}
```

`status` is `active` when the assessment can start immediately, otherwise it
is `preparing`. The `player_url` is the learner link to hand to the player
application. Treat it as a credential, do not log it, and do not cache the
create response (`Cache-Control: no-store`). Each create request creates a new
assessment; it is not idempotent.

## 3. Poll assessment status

`GET /api/v1/tests/{test_id}` requires `tests:read`:

```sh
curl --fail-with-body "$API_BASE_URL/api/v1/tests/$TEST_ID" \
  -H "Authorization: Bearer $OR_ACCESS_TOKEN"
```

The response status is one of `preparing`, `active`, `completed`, or `failed`.
Completed assessments include public feedback:

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

While an assessment is `preparing`, poll at a reasonable interval. The OR
service should not try to start the player session or submit learner answers;
those calls belong to the learner application and use a different, test-bound
player JWT.

## 4. Request a fresh learner link

`POST /api/v1/tests/{test_id}/player-token` requires `tests:launch`:

```sh
curl --fail-with-body -X POST \
  "$API_BASE_URL/api/v1/tests/$TEST_ID/player-token" \
  -H "Authorization: Bearer $OR_ACCESS_TOKEN"
```

The response is `{"player_url":"..."}` and is also `Cache-Control: no-store`.
Use this when scheduling or later access falls outside the learner link's
eight-hour default lifetime. A fresh link can be issued for `preparing`,
`active`, or `completed` assessments; failed assessments cannot receive one.

## Errors and operational rules

Application errors use this envelope:

```json
{
  "error": {
    "code": "assessment_conflict",
    "message": "Assessment state conflicts with this operation."
  }
}
```

| HTTP status | Meaning |
| ---: | --- |
| `401` | Missing, malformed, expired, or invalid OR JWT (`invalid_token`). |
| `403` | The token is valid but lacks the route's required scope. |
| `404` | The assessment does not exist. |
| `409` | The assessment state cannot satisfy the requested operation. |
| `422` | Request or graph validation failed. |
| `503` | Supabase or the internal R service is unavailable; retry where appropriate. |

Every API response contains `X-Request-ID`. Preserve it in logs and support
requests, but never log bearer tokens, player URLs, JWT payloads containing
credentials, or request bodies containing secrets.

FastAPI exposes interactive and machine-readable documentation at
`/docs`, `/redoc`, and `/openapi.json` on a running deployment.

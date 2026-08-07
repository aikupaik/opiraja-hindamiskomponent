# OR JWT integration

OR signs short-lived HS256 tokens with server-side `OR_JWT_SECRET`. Claims are
exactly `iss`, `aud`, `sub`, `scope`, `iat`, and `exp`:

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

Use integer NumericDates with `exp - iat` at or below the configured maximum.
Scope is one U+0020-separated string without leading, trailing, repeated, or
duplicate values. Send the compact token as `Authorization: Bearer <token>`.

- `POST /api/v1/tests` requires `tests:create`.
- `GET /api/v1/tests/{test_id}` requires `tests:read`.
- `POST /api/v1/tests/{test_id}/player-token` requires `tests:launch` and
  returns a fresh link for a preparing, active, or completed assessment.

Example calls (keep the token in process memory rather than shell history):

```sh
curl -H "Authorization: Bearer $OR_ACCESS_TOKEN" \
  https://assessment.example/api/v1/tests/TEST_ID

curl -X POST -H "Authorization: Bearer $OR_ACCESS_TOKEN" \
  https://assessment.example/api/v1/tests/TEST_ID/player-token
```

Creation and player-token responses are `Cache-Control: no-store`. Learner
links expire after eight hours by default; OR should issue a fresh link when
scheduling or later access falls outside that window. There is no refresh
token, per-token revocation, anonymous fallback, or raw-admin-key fallback.
Rotating `API_JWT_SECRET` invalidates player and admin tokens; rotating
`OR_JWT_SECRET` invalidates OR credentials independently.

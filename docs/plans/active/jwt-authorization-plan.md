# Phase 3: Non-Permissive JWT Authorization

## Summary

Replace permissive OR/player access and static-key admin authorization with JWT
validation while preserving `AuthContext` and assessment-service interfaces. Keep
`ADMIN_ACCESS_KEY` only for admin login; all subsequent admin, OR, and player
requests use bearer JWTs.

## Key changes

- Add PyJWT and a small centralized token service in the backend. It permits
  only `HS256`, requires `iss`, `aud`, `exp`, `sub`, and `scope`, uses 30
  seconds of clock leeway, and returns generic `401` responses with
  `WWW-Authenticate: Bearer` for missing, malformed, expired, or invalid
  tokens.
- Add required, distinct high-entropy settings: `OR_JWT_SECRET`,
  `API_JWT_SECRET`, `OR_JWT_ISSUER`, and HTTPS-only `PLAYER_APP_URL`; reject
  secrets shorter than 32 characters or equal OR/API secrets. Add configurable
  8-hour player and admin token lifetimes.
- Define the external OR contract: OR signs an HS256 JWT with
  `iss=<OR_JWT_ISSUER>`, `aud=assessment-api`, non-empty service `sub`,
  expiry, and space-delimited scopes. Supported scopes are `tests:create`,
  `tests:read`, and `tests:launch`.
- Enforce OR scopes on create/read routes and add
  `POST /api/v1/tests/{test_id}/player-token`, requiring `tests:launch`. It
  does not alter assessment state and returns a new player link.
- Issue player JWTs from the API using `API_JWT_SECRET`,
  `iss=assessment-api`, `aud=assessment-player`, `sub=player:<test_id>`,
  `scope=tests:play`, expiry, and `test_id`. Player routes require that
  token's `test_id` to equal the path ID; a valid but cross-test token returns
  `403`.
- Change create-test and player-token responses to return an absolute
  configured link: `https://player-host/test/{test_id}#token=<player-jwt>`.
  The future test-player frontend must read the fragment, keep the token only
  in memory or session storage, remove it from the address bar, and send it as
  a bearer token. No player-frontend implementation is included now.
- Add `POST /api/v1/admin/login`: it verifies `ADMIN_ACCESS_KEY` in constant
  time and returns an 8-hour API-signed admin JWT plus the existing session
  details. All admin routes, including `GET /api/v1/admin/session`, then
  require an `assessment-admin` JWT; the static key no longer authorizes them
  directly.
- Update the admin React app to store only the admin JWT in `sessionStorage`,
  never the access key. On login it exchanges the entered key for a JWT; on any
  authenticated `401`, it clears the token and returns to the unlock screen.
  Admin JWTs retain the current admin scopes and may run existing simulations.
- Reuse centralized JWT validation for diagnostic correlation, allowing it only
  for a valid admin token with `admin:simulation`. Remove JWT fragments/tokens
  from diagnostic payloads and reports; request logs remain header-free.
- Update `.env.example`, backend documentation, and an OR integration guide
  with exact claims, required environment variables, secret-generation
  guidance, endpoint examples, and the no-fallback cutover procedure.

## Test plan

- Backend tests cover anonymous, wrong-scheme, malformed, expired,
  bad-signature, wrong-algorithm, wrong-issuer, wrong-audience, missing-claim,
  and wrong-scope tokens; verify `401` versus valid-token `403` behavior.
- Verify valid OR create/read/link-refresh flow; player access for the intended
  test only; OR/player/admin profile separation; and health endpoints remaining
  anonymous.
- Verify admin login accepts only the configured key, protected admin routes
  reject that key directly, issued admin JWTs work until expiry, and simulation
  diagnostics work only with a valid simulation-capable admin JWT.
- Verify absolute player links use fragments, no response/diagnostic/log output
  exposes a JWT, and settings reject missing, weak, or reused JWT secrets.
- Run backend tests plus `python -m pyright`; run admin tests, lint, and build
  plus `npm run lint`.

## Assumptions

- Phase 2's remaining one-day dry run does not block Phase 3 code work; HTTPS,
  authorization tests, and the later trusted-certificate gate remain mandatory
  before public exposure.
- HS256 is chosen for the pilot because it is the lowest-friction OR
  integration. `OR_JWT_SECRET` is shared only with that service;
  `API_JWT_SECRET` stays solely in this backend and signs player/admin tokens.
- The current `frontend/` test player is not implemented or changed in this
  phase. The API link contract is ready for its later implementation.

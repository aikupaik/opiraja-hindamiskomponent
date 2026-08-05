# Phase 3: Non-Permissive JWT Authorization

## Prerequisite: Pre-JWT Player and Contract Work

Do not start the JWT implementation until this prerequisite is complete. The
purpose of this work is to exercise the real player flow, settle the public
contracts, and leave JWT as a bounded replacement of the permissive
authorization dependencies rather than combining authorization, frontend, and
API redesign in one change. The application must remain restricted to its
controlled development environment while authorization is permissive.

### Priority 1: Make the public contracts authoritative

**Status: complete (2026-08-04).**

1. Inventory the existing OR, player, and admin routes, DTOs, error envelopes,
   authorization dependencies, and the places that construct or consume
   `player_url`.
2. Maintain
   [`docs/contracts/public-assessment-api.md`](../../contracts/public-assessment-api.md)
   as the authoritative assessment-flow contract. Generated OpenAPI and
   contract tests back it. It defines:
   - `POST /api/v1/tests` request, response, status code, and `Location` header;
   - `GET /api/v1/tests/{test_id}` states and completed feedback;
   - `POST /api/v1/player/tests/{test_id}/start`, including `202` polling and
     `Retry-After`;
   - `POST /api/v1/player/tests/{test_id}/answers`, including idempotent replay,
     stale submissions, dependency failures, and terminal states;
   - the error-envelope shape and the intended `401`, `403`, `404`, `409`,
     `422`, and `503` meanings.
3. Use the authoritative `tests:play` player scope consistently in architecture
   documents, code constants, tests, and integration examples.
4. Decide which layer owns player-link construction. Assessment domain and
   service code should deal in assessment identifiers and state; URL origin,
   routing, and future credential presentation should have one explicit owner
   at the API/application boundary.
5. Define the pre-JWT player-link contract as `/test/{test_id}`. Reserve the
   fragment form `/test/{test_id}#token=<token>` for the later JWT phase and
   state that fragments and query parameters are never backend credentials in
   the permissive phase.

**Exit criteria:** the contracts are documented, contract tests cover the
agreed behavior, and no route, DTO, or scope name relevant to the player flow
requires an implementation agent to choose between competing definitions.

### Priority 2: Build the sample React test player

**Status: complete (2026-08-04).** The standalone player, credential boundary,
behavior tests, hardened container, same-origin Compose routing, reload/retry
semantics, and real API completion flow passed local acceptance.

1. Create the player entry point for `/test/{test_id}` and validate the path
   identifier before making API requests.
2. Implement explicit `preparing`, `question`, `submitting`, `completed`, and
   `failed` UI states using the existing player endpoints.
3. Poll `start` only while the API returns `202`, honor `Retry-After`, add the
   specified positive jitter, and cancel timers and requests on unmount or
   state transition.
4. Render one accessible radio-group question at a time, require a selection,
   prevent double submission, and preserve the stable option order returned by
   the API.
5. Submit the server-provided `submission_id` and opaque `option_id`; preserve
   the same `submission_id` when retrying a request whose outcome is unknown.
6. Render the three Estonian feedback sections without exposing answer keys,
   correctness, posterior state, or internal KST data.
7. Define reload behavior for preparing, active, and completed tests. A reload
   must recover from backend-persisted state and must not rely on browser-only
   question state.
8. Add a small credential abstraction to the player API client. It may return
   no credential during the permissive phase, but it must be the single place
   where the later fragment-derived bearer token is attached.
9. Add behavior tests for polling, jitter, timer cleanup, double submission,
   retries, reload recovery, errors, completion, and accessible interaction.

**Exit criteria:** a locally created link opens a working player, reaches final
feedback through the real API contract, survives a browser reload, and has no
JWT-specific code outside the credential abstraction and reserved fragment
bootstrap boundary.

### Priority 3: Unify frontend API behavior

1. Align the admin and player clients on one error-envelope decoder, request-ID
   handling, JSON/content-type behavior, abort handling, and typed response
   conventions. Share code only where it reduces duplication without coupling
   the two applications' UI state.
2. Centralize bearer-header construction so feature components never assemble
   `Authorization` headers themselves.
3. Define one authenticated-`401` notification path that can later clear a
   stored credential and return the relevant app to its locked or expired-link
   state. Login failures must remain distinguishable from expiry of an already
   authenticated session.
4. Ensure API errors shown to users remain generic while request IDs remain
   available for diagnostics.
5. Confirm that neither client stores credentials in persistent
   `localStorage`, sends them in query parameters, or includes them in reports
   and telemetry.

**Exit criteria:** adding a bearer token later requires changing the credential
bootstrap/storage boundary and centralized request client, not every page or
feature request.

### Priority 4: Settle admin simulation boundaries

1. Document whether an admin simulation is a privileged internal workflow or
   an exact emulation of independent OR and player credentials.
2. If it is privileged, specify the deliberate exception that lets an admin
   simulation call OR/player routes, the required `admin:simulation` grant,
   and when `X-Experiment-ID` is honored. Define profile-separation tests around
   that explicit exception.
3. If it is an exact emulation, define how the simulation obtains an OR
   credential, extracts the issued player credential, switches credentials
   between calls, and retains authenticated diagnostic correlation.
4. Keep diagnostic capture opt-in, bounded, and restricted to authenticated
   simulations. Redact any future token-bearing fragment or field before an
   event enters the diagnostic buffer so reports and replay cannot recover it.
5. Add tests for unauthorized correlation attempts, cross-profile tokens, and
   diagnostic redaction at the capture boundary.

**Exit criteria:** the chosen model is documented and tested; the JWT
implementation does not need to infer whether admin tokens may authorize OR or
player operations.

### Priority 5: Freeze the JWT contracts and revise this plan

After the player and contract work above is complete, update the remainder of
this plan with decisions grounded in the implemented flow:

1. Define exact OR, player, and admin JWT claim profiles, including issuer,
   audience, subject, scope syntax, claim types, allowed algorithms, clock
   leeway, and token lifetimes.
2. Define the complete `POST /api/v1/admin/login` request and response DTOs,
   failure behavior, cache headers, rate limit, and disabled-configuration
   behavior.
3. Define the complete player-token response, eligibility rules for unknown and
   terminal tests, repeat-call behavior, and which OR subjects may refresh a
   test link.
4. Define `PLAYER_APP_URL` validation and URL-joining rules, including local
   development behavior and rejection of user info, query strings, and
   fragments in configuration.
5. Resolve the intentional token-response exception: create-test and
   player-token responses may contain a JWT only inside the returned
   `player_url`; logs, diagnostics, reports, errors, and all other responses
   must not expose it. Mark token-bearing and admin-login responses
   `Cache-Control: no-store`.
6. Specify the operational expiry and rotation policy: who refreshes learner
   links, expected creation-to-use delay, client-side logout behavior, and
   emergency invalidation through API signing-secret rotation.
7. Add the mandatory Nginx work to the implementation and acceptance scope:
   rate-limit admin login, test creation, and player-token issuance; retain
   shared-IP-safe player limits; verify request/header timeouts; and complete
   the reviewed transition from dry-run to enforced limits.
8. Replace every provisional or contradictory statement in this plan and its
   test plan before assigning JWT implementation to a coding agent.

**JWT entry gate:** the sample player works end to end; public contracts and
scope names are authoritative; frontend credential handling has one boundary;
admin simulation behavior is explicit; JWT/admin-login/player-token contracts
are exact; diagnostic redaction and cache policy are specified; and deployed
abuse-control work has defined acceptance checks.

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

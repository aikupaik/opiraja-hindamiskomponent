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

**Status: complete (2026-08-05).** The admin and player now use a shared
transport/error contract, centralized credential attachment, distinct login
validation and authenticated-`401` paths, generic user-facing API errors with
diagnostic request IDs, and independently verified container builds.

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

**Status: complete (2026-08-05).** Admin simulation is a privileged internal
workflow, not an exact emulation of independent OR and player credentials.

1. Admin credentials remain a distinct profile and carry only `admin:*`
   grants. They do not carry or impersonate `tests:create`, `tests:read`, or
   `tests:play`.
2. The current create, status-read, player-start, and player-answer routes each
   opt in explicitly to the `admin:simulation` exception. Strict OR/player
   profile checks remain the default, so future routes, including player-token
   refresh, do not inherit admin access without a deliberate decision.
3. `X-Experiment-ID` activates capture only for a valid UUID on authenticated
   admin-simulation calls to create, start, or answer. It is ignored for OR and
   player profiles, invalid or insufficient admin credentials, malformed IDs,
   and other routes. `admin:simulation` permits capture while the independent
   `admin:diagnostics` grant controls event and report access.
4. Diagnostic capture remains opt-in, bounded, process-local, and ephemeral.
   Token fields, compact JWT values, and token-bearing URL fragments are
   redacted at the diagnostic-hub ingestion boundary before buffering, replay,
   streaming, or report generation.
5. Authorization-seam tests cover the privileged exception and cross-profile
   denial. Correlation and capture-boundary tests cover unauthorized attempts,
   route eligibility, and dynamic-token redaction. The JWT phase must repeat
   profile-separation coverage with actually signed OR, player, and admin
   tokens and retain a separate exact OR-to-player end-to-end acceptance flow.

**Exit criteria:** satisfied. The JWT implementation must preserve this
explicit route-level exception and must not add public `tests:*` scopes to the
admin token profile.

### Priority 5: Freeze the JWT contracts and revise this plan

**Status: complete (2026-08-05).** The target claim profiles, login and
player-token DTOs, link rules, browser credential lifecycle, cache and
redaction boundary, rotation policy, and edge-control acceptance checks are
frozen below. JWT implementation may now use this plan without choosing among
competing contracts.

The completed contract pass made the following decisions grounded in the
implemented flow:

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

**JWT entry gate:** satisfied. The sample player works end to end; public
contracts and scope names are authoritative; frontend credential handling has
one boundary; admin simulation behavior is explicit; JWT, admin-login, and
player-token contracts are exact; diagnostic redaction and cache policy are
specified; and deployed abuse-control work has defined acceptance checks.

## Summary

Replace permissive OR/player access and static-key admin authorization with
JWT validation while preserving `AuthContext` and assessment-service
interfaces. Keep `ADMIN_ACCESS_KEY` only for admin login; all subsequent
admin, OR, and player requests use bearer JWTs. The already implemented player
and shared frontend transport gain credentials only at their existing
bootstrap and credential-source boundaries.

## Frozen JWT contract

### Common validation rules

- Use PyJWT with the allowed algorithm supplied as the fixed list
  `["HS256"]`.
  Never derive the allowed algorithm from the JOSE header. Require the
  profile's claims through PyJWT decode options and supply the expected issuer,
  audience, and 30-second leeway explicitly.
- Each accepted payload contains only the claims listed for its profile.
  `iss`, `aud`, `sub`, and `scope` are strings. `iat` and `exp` are integer
  NumericDate values; booleans and floats are invalid. API-issued `jti` values
  and player `test_id` values are canonical hyphenated UUID strings.
- A subject must contain at least one non-whitespace character. An `aud` array
  is invalid even if it contains the expected audience.
- Scope uses U+0020 spaces only, with no leading, trailing, or repeated space
  and no duplicates. OR scopes are a non-empty subset of `tests:create`,
  `tests:read`, and `tests:launch`. Player scope is exactly `tests:play`.
  Admin scope contains exactly `admin:read`, `admin:write`,
  `admin:diagnostics`, and `admin:simulation`; scope order has no authorization
  meaning.
- Require `exp > iat`. Reject `iat` values more than 30 seconds in the future.
  Expiration and any future-time check use the same 30-second leeway.
- Missing credentials, a non-Bearer scheme, malformed compact JWTs, invalid
  signatures, wrong algorithms, missing or mistyped claims, and failed
  issuer/audience/time/profile validation all return the same generic `401`
  application error below with `WWW-Authenticate: Bearer`. A valid token with
  the wrong profile, insufficient scope, or wrong player test binding returns
  the existing generic `403 forbidden` envelope before assessment processing.

  ```json
  {
    "error": {
      "code": "invalid_token",
      "message": "Valid bearer credentials are required."
    }
  }
  ```

### Claim profiles

| Profile | Signing and exact claims | Lifetime and authorization |
|---|---|---|
| OR | OR signs with `OR_JWT_SECRET`; `iss=<OR_JWT_ISSUER>`, `aud="assessment-api"`, nonblank service `sub`, canonical `scope`, integer `iat`, integer `exp`. | Require `exp - iat <= OR_JWT_MAX_LIFETIME_SECONDS`, default `300`. Create requires `tests:create`, status read requires `tests:read`, and link issuance requires `tests:launch`. |
| Player | API signs with `API_JWT_SECRET`; `iss="assessment-api"`, `aud="assessment-player"`, `sub="player:<test_id>"`, `scope="tests:play"`, integer `iat`, integer `exp`, UUID `jti`, and UUID `test_id`. | Default lifetime `PLAYER_JWT_LIFETIME_SECONDS=28800` (eight hours). Both `sub` and `test_id` must identify the path test. |
| Admin | API signs with `API_JWT_SECRET`; `iss="assessment-api"`, `aud="assessment-admin"`, `sub="development-admin"`, the exact four-scope admin profile, integer `iat`, integer `exp`, and UUID `jti`. | Default lifetime `ADMIN_JWT_LIFETIME_SECONDS=28800` (eight hours). Public `tests:*` grants are forbidden; simulation remains the explicit route-level exception already documented above. |

`jti` makes separately issued API tokens distinct; there is no lookup,
per-token revocation list, refresh token, or `kid`-based overlapping-key grace
period in the pilot.

### Settings and player URL construction

- Add required `OR_JWT_SECRET`, `API_JWT_SECRET`, `OR_JWT_ISSUER`, and
  `PLAYER_APP_URL` settings. Each secret must contain at least 32 characters,
  and the two secrets must not be equal. Generate each from at least 32 random
  bytes; `OR_JWT_SECRET` is shared only with OR and `API_JWT_SECRET` remains
  API-only.
- Add positive integer `OR_JWT_MAX_LIFETIME_SECONDS`,
  `PLAYER_JWT_LIFETIME_SECONDS`, and `ADMIN_JWT_LIFETIME_SECONDS` settings with
  defaults `300`, `28800`, and `28800` respectively.
- `PLAYER_APP_URL` is an absolute origin, not a path base. Require HTTPS except
  that HTTP is permitted for the exact local-development hosts `localhost`,
  `127.0.0.1`, and `[::1]`, with an optional port. Reject user information,
  non-root paths, query strings, and fragments. Accept an empty path or `/`
  and normalize the optional trailing slash away.
- Construct links from validated components, not generic relative URL joining:
  `<origin>/test/<canonical-test-id>#token=<compact-jwt>`. The API/application
  route remains the sole owner of link construction; domain and service code
  continue to deal only in identifiers and state.

## Frozen endpoint contracts

### `POST /api/v1/admin/login`

- Accept JSON only through a strict request DTO with no unknown fields:
  `{"access_key":"<string>"}`. `access_key` has length 1 through 1024.
- Compare the supplied UTF-8 value with `ADMIN_ACCESS_KEY` in constant time.
  Do not log, persist, normalize, or return it.
- On success return `200` with the strict response DTO below. `expires_in`
  equals the configured admin lifetime, whose default is 28800 seconds.

  ```json
  {
    "access_token": "<admin-jwt>",
    "token_type": "Bearer",
    "expires_in": 28800,
    "session": {
      "subject": "development-admin",
      "capabilities": [
        "admin:diagnostics",
        "admin:read",
        "admin:simulation",
        "admin:write"
      ],
      "max_graph_nodes": 10,
      "diagnostic_max_events": 500,
      "diagnostic_ttl_seconds": 3600,
      "source_max_bytes": 10000000,
      "source_max_pdf_pages": 100,
      "source_max_text_chars": 1000000
    }
  }
  ```

- An absent `ADMIN_ACCESS_KEY` disables login. Disabled login and an incorrect
  key return the same generic `401 admin_unauthorized` envelope and do not
  disclose configuration state. Request validation retains FastAPI's standard
  `422`; the public edge may return its documented minimal `429` response.
- Add `Cache-Control: no-store` to every login response, including failures.
  Login does not use `WWW-Authenticate`; protected admin endpoints use the
  common Bearer challenge.
- After cutover, `ADMIN_ACCESS_KEY` is invalid on every endpoint except login.
  `GET /api/v1/admin/session` and all other admin routes require the admin JWT.

### `POST /api/v1/tests/{test_id}/player-token`

- Accept no request body. Require a valid OR token with `tests:launch`.
  `admin:simulation` is deliberately not accepted on this new route.
- Any trusted OR subject with `tests:launch` may issue a new link for any
  eligible test. The pilot does not persist or compare the creating OR
  subject.
- Preparing, active, and completed tests are eligible. Return `404` for an
  unknown test, `409` for failed or unsupported persisted states, `503` when
  persistence is unavailable, and the existing generic `500` fallback.
- A successful call does not mutate assessment state. It always mints a new
  player JWT and returns `200` with the strict DTO
  `{"player_url":"<absolute-token-bearing-url>"}`. Repeat calls are not
  idempotent and are not guaranteed to return the same URL.
- Return `Cache-Control: no-store` on success. Add the route's `401`, `403`,
  `404`, `409`, `422`, `503`, and `500` contracts to generated OpenAPI.

### Test creation and token exposure

- Keep the existing create request, `201`, `Location`, status, and
  `missing_nodes` contracts. Replace only its relative `player_url` with a
  newly issued absolute token-bearing link and mark the successful response
  `Cache-Control: no-store`.
- The only response-body locations allowed to contain compact JWTs are
  `access_token` in a successful admin-login response and the fragment of
  `player_url` in successful create-test and player-token responses. Errors,
  status/player responses, diagnostics, diagnostic reports, telemetry, and
  logs must not contain JWTs. Retain redaction of token-named fields, compact
  JWT values, and token-bearing URL fragments at diagnostic ingestion.

## Frontend credential lifecycle

- The player bootstrap reads only an exact `#token=<non-empty-token>` fragment,
  stores the token under a test-ID-specific `sessionStorage` key, and removes
  the fragment with `history.replaceState` before starting API work. A reload
  without a fragment reuses only the credential stored for that path's
  `test_id`; another test's token is never selected.
- The centralized player credential source attaches the token. An
  authenticated `401` clears that test's stored token and moves the existing
  player to its expired-link state. The credential remains available after
  completion so a same-tab reload can recover completed feedback, and it
  disappears when the tab session ends.
- The admin unlock flow posts the entered key to `/api/v1/admin/login`, stores
  only `access_token` in `sessionStorage` under a JWT-specific storage key, and
  uses the returned `session` directly. Manual lock and any authenticated
  `401` clear the JWT and return to the unlock screen. The access key is never
  written to browser storage.

## Expiry, rotation, and deployed abuse controls

- Eight-hour player links are same-day credentials. OR owns learner-link
  refresh and calls the player-token endpoint when scheduling, YG preparation,
  or later feedback access falls outside that window. The learner has no login
  or refresh flow.
- Emergency replacement of `API_JWT_SECRET` followed by API restart
  immediately invalidates every outstanding player and admin token. Replace
  `OR_JWT_SECRET` independently to invalidate OR credentials. After API-secret
  rotation, OR must issue replacement learner links.
- Split the host-Nginx policy into per-client-IP locations. Apply
  `5r/m` with `burst=5 nodelay` to admin login; a shared `2r/s` issuance zone
  with `burst=10 nodelay` to exact test creation and player-token routes; and
  `50r/s` with `burst=100 nodelay` to player start/answer routes. Retain the
  current general API limiter for other routes and the existing two-connection
  admin SSE limit.
- Preserve `client_header_timeout 10s`, `client_body_timeout 30s`, the current
  bounded proxy connect/send/read timeouts, query-free request logging, and
  header-free logs. Sensitive endpoint responses and edge-generated `429`
  responses must not be cached.
- Deploy the endpoint limits in dry-run first. Run controlled probes that
  cross each threshold, a shared-IP player burst representing the 100-student
  pilot, and normal admin/OR/player workflows. Review summarized
  `$limit_req_status` and `$limit_conn_status` results without copying token or
  request data. Remove both dry-run directives only after the expected
  thresholds trigger and normal workflows show no false positives during the
  observation window; repeat the probes and verify enforced `429` responses.

## Implementation changes

- Add PyJWT and a centralized token service. Replace the three permissive
  authorization dependencies while preserving `AuthContext`, route-level
  `require_*` checks, admin-simulation opt-ins, and assessment-service
  interfaces.
- Add the login and player-token DTOs/routes, application-boundary link
  builder, cache headers, settings validation, and OpenAPI declarations above.
- Update the existing React player and admin credential boundaries exactly as
  specified; feature pages continue to use the shared transport and never
  assemble authorization headers.
- Update `.env.example`, Compose settings, backend and frontend documentation,
  and an OR integration guide with exact claims, secret-generation guidance,
  endpoint examples, expiry/rotation behavior, and the no-fallback cutover.
- Update `docs/pilot_architecture_plan.md` and the future-JWT transition notes
  in `docs/contracts/public-assessment-api.md` with this frozen contract. The
  latter remains authoritative for currently implemented pre-JWT wire behavior
  until JWT implementation updates its examples, OpenAPI, and contract tests
  in the same change.

## Test plan

- Token-unit tests cover fixed-algorithm enforcement; every missing and
  mistyped claim; blank subjects; list audiences; malformed, unknown, and
  duplicate scopes; invalid UUID claims; bad signatures; wrong profiles;
  `iat`/`exp` ordering; the OR five-minute maximum; and both sides of the
  30-second leeway boundary.
- API tests cover anonymous and wrong-scheme requests; generic `401` plus the
  exact `invalid_token` envelope and Bearer challenge; valid-token `403` for
  wrong scope/profile/test binding;
  valid OR create/read/link issuance; player access to its intended test only;
  signed admin simulation; cross-profile denial; and anonymous health routes.
- Admin-login tests cover the strict request and response DTOs, constant-time
  comparison boundary, absent configuration, invalid key, validation error,
  no-store headers on success and failure, protected-route rejection of the
  raw key, eight-hour expiry, manual logout, and authenticated-`401` cleanup.
- Link tests cover exact `PLAYER_APP_URL` acceptance and rejection, canonical
  construction, no-store headers, preparing/active/completed eligibility,
  unknown and failed tests, persistence failure, fresh repeat issuance, and
  the deliberate denial of `admin:simulation` on the new route.
- Player behavior tests cover fragment removal before requests, test-specific
  session storage, reload recovery in preparing/active/completed states,
  cross-test isolation, expired-link cleanup, and absence of query or
  persistent-local-storage credentials.
- Redaction tests exercise both allowed JWT response locations and verify that
  all errors, other responses, structured logs, diagnostic events/replay, and
  generated reports contain neither compact JWTs nor token-bearing fragments.
- Settings and rotation tests reject missing, weak, or reused secrets and
  prove that an API-secret change invalidates both player and admin tokens
  while leaving OR verification independent.
- Nginx configuration checks and deployed probes verify each exact endpoint
  limit, shared-IP player headroom, request/header and proxy timeouts, dry-run
  observations, the reviewed transition to enforcement, and enforced `429`.
- Run backend tests with `backend/.venv`, then `python -m pyright`; run shared,
  player, and admin tests, builds, and `npm run lint`. Complete the exact
  signed OR-to-player end-to-end flow separately from admin simulation.

## Assumptions

- HS256 is the agreed pilot integration. OR can issue tokens with integer
  `iat`/`exp` no more than five minutes apart and keep the shared OR secret
  server-side.
- OR subjects are trusted service identities, not ownership tenants. Any OR
  subject granted `tests:launch` may refresh any eligible test link.
- The player is deployed at `/test/{test_id}` on a root, same-origin host.
  Path-prefixed player deployments, student accounts, refresh tokens, and
  individual token revocation remain out of scope.
- Phase 2 observation does not block JWT code development, but enforced edge
  limits, HTTPS, signed authorization acceptance, and the later
  trusted-certificate gate remain mandatory before public exposure.

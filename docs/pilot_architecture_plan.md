# Phase-One Pilot: FastAPI + Stateless R + React

## Summary

Replace the Shiny runtime with a small vertical slice:

```text
OR/demo client ───────────────┐
Browser → Nginx → React       ├→ FastAPI → Supabase
                 └─ /api ─────┘       │
                                      └→ internal R/Plumber service

Supabase INSERT webhook → existing YG Edge Function → ylesandepank
```

- Nginx is the only public container; it serves React and proxies `/api`.
- FastAPI is the modular-monolith orchestrator and the only component accessing Supabase.
- R is an internal, stateless calculation service with no database credentials.
- The existing Supabase YG webhook workflow remains unchanged.
- The Shiny applications are replaced in place after their behavior is captured in regression tests.

## Architecture and Responsibilities

### FastAPI backend

- Use English code, DTOs, routes, and comments; map existing Estonian database names in one Supabase repository adapter.
- Define one asynchronous, domain-focused `AssessmentRepository` interface rather than generic CRUD. Its Supabase implementation covers graph caching, sessions, item-bank access, YG orders, results, and idempotent answer commits.
- Use `async def` FastAPI route and service functions with Supabase's official `AsyncClient`. Create one shared client during application lifespan with `await acreate_client(...)`, await all database operations, and close its initialized async transports during shutdown.
- Pin the stable Python package `supabase==2.31.0`; do not adopt the `3.0.0a1` prerelease during the pilot. [PyPI package metadata](https://pypi.org/project/supabase/2.31.0/)
- Use one lifespan-managed `httpx.AsyncClient` for R calls, with explicit connection, read, write, and pool timeouts. Bound its connection pool with the single backend setting `R_MAX_CONNECTIONS` (default `4`) and keep no more idle connections than that limit. [HTTPX resource-limit documentation](https://www.python-httpx.org/advanced/resource-limits/)
- Treat an R connection-pool acquisition timeout like other R unavailability: return `503` without advancing session state so the same `submission_id` can be retried safely.
- Keep correctness-dependent answer-processing operations sequentially awaited. Do not parallelize result insertion, telemetry, or session compare-and-set updates merely because the clients are asynchronous.
- Do not call blocking network or file APIs directly on the event loop; offload any unavoidable blocking operation to a worker thread.
- Keep the application modular by responsibility—API routes, assessment service, repository, R client, and domain models—but deploy it as one process.
- Keep OR-facing and player-facing endpoints in separate `APIRouter` modules. Both use an injected authorization dependency that returns a small `AuthContext` (`actor_type`, `subject`, `scopes`, and optional authorized `test_id`); the phase-one implementation permits requests, while the pre-pilot implementation defined below validates bearer credentials. Assessment services do not parse JWTs or depend on FastAPI security classes.
- Expose dependency-free liveness and bounded dependency-aware readiness endpoints. Readiness checks use short timeouts and report unavailable when Supabase or R is not ready; liveness does not call dependencies.
- Emit one structured completion log per request with request ID, optional `test_id`, outcome/status, total duration, cumulative Supabase and R durations, and Supabase/R call counts. Keep these as log fields rather than adding monitoring infrastructure, and never log authorization headers, player tokens, or signing secrets.
- Validate non-empty unique nodes, relation endpoints, supported method `kst`, and `MAX_GRAPH_NODES`. The default limit is `10` and exists in exactly one backend setting.
- Compute a language-neutral graph hash from canonical sorted UTF-8 JSON and prefix/version the algorithm. Old R-generated cache rows remain untouched and may coexist.

### Stateless R service

Expose only:

- `GET /health`
- `POST /internal/v1/kst/model`: build or restore the knowledge-space matrix, uniform prior, node parameters, and initial half-split node.
- `POST /internal/v1/kst/advance`: apply the Bayesian update, stopping rule, final-profile classification, and either return the next node or the completed profile.

The model endpoint may receive cached knowledge states from Python; otherwise it calculates them from nodes and relations. Every response is plain JSON and contains no database operations or item content.

Move the current behavior into pure tested functions:

- valid KST-state generation;
- `kmassesshalfsplit`;
- `kmassessbayesian`;
- reliability floor and safety cap;
- credible-state set and five-way final profile.

Put researcher-adjustable values in one version-controlled KST configuration file:

- stop confidence `0.8`;
- feedback credible mass `0.9`;
- reliability formula parameters equivalent to `min(max(7, ceil(1.5n)), 10)`;
- safety-cap parameters equivalent to `max(2n, floor+1)`.

The model response includes the full configuration snapshot and a calculated config hash. FastAPI stores that snapshot in `testi_loogika`, so changing configuration affects only new tests.

Create and commit an `renv.lock`; the container must restore it rather than relying on global packages. Include `plumber`, `kst`, `kstMatrix`, `jsonlite`, `digest`, and `testthat`. The currently published `kstMatrix` is 2.3-4 and requires R ≥4.4.0. [CRAN package metadata](https://cran.r-project.org/web/packages/kstMatrix/index.html)

### React test player

- Use React, TypeScript, and Vite without a router framework or global state library.
- Load `test_id` from `/test/{test_id}`.
- Model the UI as explicit states: preparing, question, submitting, completed, and failed.
- Poll the idempotent start endpoint only while it returns `202`. Honor its `Retry-After` value and add fresh positive jitter on every cycle—when the header is `3`, wait randomly between three and four seconds—to avoid synchronized polling bursts. Clean up polling when the component unmounts or status changes.
- Render one accessible radio-group question at a time, disable submission until an option is selected, and prevent double submission.
- Never receive the answer key, posterior, node parameters, or correctness result.
- Preserve current Estonian learner-facing copy and the three feedback sections: “Juba oskad”, “Võid õppida / rohkem süveneda”, and “Tasuks korrata”.
- Do not reveal correctness after each answer; show only the next question or final feedback.

## Interfaces, State, and Data Flow

### Operational API

- `GET /health/live`
  - Dependency-free liveness check for the FastAPI process.
- `GET /health/ready`
  - Lightweight readiness check for the lifespan-managed Supabase and R clients.
  - Uses short bounded dependency timeouts and returns `503` while either required dependency is unavailable.

### Public API

The phase-one MVP keeps these routes callable without credentials through the permissive authorization dependency. Their separation and required pre-pilot permissions are defined now so authorization can later be enabled without changing assessment services or persistence.

- `POST /api/v1/tests`
  - OR-facing; pre-pilot permission: `tests:create`.
  - Input: `user_id`, `learning_path_id`, optional `course`/`goal`, `method="kst"`, optional `cognitive_level`, `nodes: string[]`, and `relations: {from,to}[]`.
  - Output: `test_id`, `status`, `player_url`, and `missing_nodes`.
  - Builds/caches the graph, creates the session, checks item coverage, and either activates immediately or creates one non-duplicate `yg_tellimused` row.

- `GET /api/v1/tests/{test_id}`
  - OR-facing; pre-pilot permission: `tests:read`.
  - Read-only polling endpoint.
  - Returns `preparing`, `active`, `completed`, or `failed`; completed responses include mapped feedback.

- `POST /api/v1/player/tests/{test_id}/start`
  - Player-facing; pre-pilot permission: `test:play` for the same `test_id`.
  - Idempotent player command.
  - While YG is pending, returns `202` with `Retry-After: 3`.
  - When coverage becomes complete, builds and stores the R model, activates the session, selects and persists the first question, and returns it.
  - Repeated calls return the already-persisted question and option order.
  - YG status `viga` marks the session failed.

- `POST /api/v1/player/tests/{test_id}/answers`
  - Player-facing; pre-pilot permission: `test:play` for the same `test_id`.
  - Input: `submission_id` and opaque `option_id`.
  - Resolves the selected text server-side, scores it, calls R `/advance`, commits the result/session state, and returns either the next question or final feedback.
  - Replaying an accepted `submission_id` returns the current session view without inserting another result.
  - Unknown stale tokens return `409`; unknown tests return `404`; unavailable R/Supabase returns `503` without advancing state.

Question responses contain `submission_id`, `item_id`, instruction, prompt, optional stimulus, and ordered `{id,text}` options only.

### Persistence

- The required Supabase schema change is already deployed and documented: `tulemustepank.vastus_id uuid NOT NULL DEFAULT gen_random_uuid()` with a unique constraint. In English domain models and API contracts, map `vastus_id` to `submission_id`; no further table changes are planned.
- Extend `tp_seisund` JSONB with a schema version and `current_question`, containing the submission token, chosen item/node, and stable option order.
- Keep posterior and answered-item history in `tp_seisund`; keep the R model and KST configuration snapshot in `testi_loogika`; retain the existing `lopp_profiil` structure.
- Commit results idempotently by writing the API `submission_id` explicitly to the unique `tulemustepank.vastus_id` column, then compare-and-set `tp_seisund` against the expected current submission token. Do not rely on the database UUID default for player submissions, because retries must reuse the same token. A retry can safely finish an interrupted update.
- Treat `kasutamiste_arv` as pilot telemetry; increment only for the request that first inserts the submission.
- Do not depend on the undocumented `testisessioonid.kursus` column. Course is used when creating a YG order but not for item eligibility.
- New sessions are identified by their JSON schema version. Existing rows are preserved but old planning/active sessions are not resumed or migrated.

## Implementation Order

1. Capture the current R behavior in numerical regression fixtures before removing Shiny entrypoints; document the experimental KST configuration and API contracts.
2. Verify the deployed `vastus_id` constraint/default and its `submission_id` repository mapping, then add the asynchronous repository/domain interfaces with async in-memory fakes.
3. Extract the pure KST functions into the R service, add Plumber contracts, validation, health checks, `testthat`, and `renv`.
4. Implement FastAPI creation, preparation/YG polling, question selection, scoring, idempotent answer handling, feedback mapping, bounded R-call capacity, operational health endpoints, structured request/dependency timing logs, separate OR/player routers, and the permissive `AuthContext` dependency seam.
5. Build the React player and behavior tests, then replace the Shiny UI/API entrypoints.
6. Add Docker Compose with `web`, `api`, and `r-service`; only `web` publishes a host port. Supabase secrets go only to `api`.
7. Verify the deployed Supabase webhook contract with one real missing-coverage test, then update the README with local startup, configuration, migration, smoke-test, and VM deployment instructions.

## Test and Acceptance Plan

- R tests: chain and relation-free knowledge spaces, known Bayesian vectors, half-split validity, natural and safety-cap stopping, five-way profile classification, malformed matrices, and configuration snapshots.
- Backend tests: covered versus missing item banks, duplicate YG prevention, YG success/failure, stable reloads, hidden answer keys, correct/incorrect scoring, stale tokens, duplicate answer replay, completion, R failure, Supabase failure, R pool-acquisition timeout without state advancement, health endpoint semantics, structured request/dependency timing fields, OR/player router separation, and authorization-dependency overrides.
- Contract tests run FastAPI against the real Dockerized R service; normal backend unit tests replace both async R and Supabase adapters through dependency injection.
- React tests use Vitest and Testing Library for `Retry-After` polling with deterministic jitter, timer cleanup, accessible option selection, disabled/double-submit behavior, reloads, errors, completion, and all feedback sections.
- Supabase/YG tests are opt-in smoke tests against the configured pilot project, not part of normal unit-test execution.
- End-to-end acceptance: `docker compose up --build` starts services that pass their readiness checks; a created link survives browser/API container restarts; missing items progress through the existing webhook; every accepted submission creates exactly one result; and a test reaches reproducible final feedback.
- Changing `MAX_GRAPH_NODES` in one setting changes the enforced limit; changing the KST configuration file affects new sessions while existing sessions retain their stored configuration.

## Pre-Pilot Security and Authorization

This section is deliberately outside the phase-one MVP implementation and acceptance scope, but it is mandatory before exposing the application for a student pilot. It adds bearer authorization without adding student accounts, login screens, Supabase Auth, RLS changes, or authorization between FastAPI and the internal R service.

### Authorization model

- Replace the permissive phase-one authorization dependency with a JWT-validating implementation while preserving the same `AuthContext` contract and route handlers. FastAPI router/security dependencies enforce route-level scopes. [FastAPI security dependency documentation](https://fastapi.tiangolo.com/reference/dependencies/#fastapisecurity)
- Treat OR and player credentials as separate token profiles with separate audiences and signing configuration. An OR credential must never authorize a player route, and a player credential must never authorize an OR route.
- Treat `test_id` and `submission_id` as identifiers, not credentials. `submission_id` remains an idempotency token only.
- Return `401` for missing, expired, or invalid credentials and `403` for a valid credential that lacks the required scope or is bound to a different test.

### OR service token

- The external õpirada/OR service sends `Authorization: Bearer <token>`.
- Require a trusted OR issuer, audience `assessment-api`, a service subject, expiration, and the relevant scopes: `tests:create`, `tests:read`, and `tests:launch`.
- `POST /api/v1/tests` requires `tests:create`; `GET /api/v1/tests/{test_id}` requires `tests:read`.
- Add `POST /api/v1/tests/{test_id}/player-token`, requiring `tests:launch`, so OR can obtain a fresh test-bound player link when the original token has expired. This endpoint creates no new assessment session and does not change test state.
- Prefer asymmetric signing when OR can provide a stable public verification key: OR retains its private key and FastAPI receives only the public key. If OR cannot issue JWTs for the first pilot, a configured high-entropy bearer-key validator may implement the same `AuthContext` temporarily without changing routes or services.

### Player token

- FastAPI issues a player JWT when a test is created or when authorized OR calls the player-token endpoint.
- Require issuer `assessment-api`, audience `assessment-player`, subject, expiration, scope `test:play`, and a `test_id` claim. Do not include the learner's name, answer data, or other unnecessary personal information.
- On every player request, validate the token and require its `test_id` claim to equal the path `{test_id}` before assessment processing. A token for one test cannot start, read, or answer another test.
- Make the player-token lifetime a single configurable setting long enough for the scheduled pilot and expected YG preparation delay. There is no refresh-token flow, student login, or per-token revocation list in this pilot; completed and failed session states still prevent further assessment progress.
- Put the token in the URL fragment, for example `/test/{test_id}#token=...`, rather than a query parameter. React reads the fragment and sends the token in the `Authorization` header; fragments are not sent in HTTP requests or normal reverse-proxy access logs. Keep the token in memory or session storage, not persistent local storage.

### Token validation and transport

- Pin one JWT library when this phase is implemented. Configure a fixed allowed algorithm rather than trusting the token header, and require and validate `iss`, `aud`, `exp`, and `sub`; validate scopes and player `test_id` separately. Allow only a small configured clock-skew leeway. [PyJWT usage documentation](https://pyjwt.readthedocs.io/en/stable/usage.html)
- Keep OR verification keys, player signing keys, expected issuers/audiences, and token lifetimes in backend environment settings. Never send signing material to React or commit it to the repository.
- Require HTTPS at Nginx for the externally reachable pilot. Keep the browser and API same-origin, do not enable broad CORS, and set `Referrer-Policy: no-referrer` so player links are not disclosed to external resources.

### Basic abuse controls

- Authorization prevents unauthorized assessment work but is not denial-of-service protection. Configure Nginx request-body limits and bounded request/header timeouts before external exposure.
- Apply a strict endpoint-specific rate limit to test creation and player-token issuance. Give start/answer/polling endpoints a more generous limit because many students may share one school IP address; validate the limits with the opt-in concurrency smoke test rather than choosing production-scale values speculatively.
- Keep only Nginx public, keep R unreachable from the public network, and use the VM provider's firewall or upstream protection for traffic floods that cannot be handled inside the application.

### Pre-pilot acceptance

- Tests cover missing, malformed, expired, wrong-issuer, wrong-audience, wrong-scope, and wrong-`test_id` tokens; valid OR and player flows; fresh player-link issuance; redacted logs; and unauthenticated health endpoints.
- An end-to-end test confirms that an authorized OR can create and poll a test, its issued player token can operate only that test, and requests without valid credentials cannot create tests or advance sessions.
- The pilot is not opened to external users until HTTPS, authorization enforcement, secret injection, log redaction, and the basic Nginx abuse controls are verified in the deployed environment.

## Recommendations for the 100-Student Pilot

These are deliberately outside the phase-one MVP implementation and acceptance scope. Revisit them after the vertical slice works end to end and before running the larger pilot.

### Opt-in concurrency smoke test

- Add a manually run test that ramps to 100 simulated students with realistic answer think time, plus one worst-case scenario where all students open the test together.
- Exercise preparation polling, starts, answers, temporary `503` retries with the same `submission_id`, completion, and restart-safe reloads.
- Record error rate, median and p95 response times, R calls in flight, dependency timeout counts, duplicate result count, and invalid/stale transition count.
- Use its results to tune `R_MAX_CONNECTIONS`, timeouts, and process counts rather than increasing them speculatively. Do not put this test in normal CI.

### Query and index review

- Once repository queries and representative data exist, inspect their query plans and use the Supabase Performance/Index Advisor before adding indexes. [Supabase Index Advisor documentation](https://supabase.com/docs/guides/database/extensions/index_advisor)
- Verify likely access paths for `ylesandepank (graafi_objekt, staatus)`, `yg_tellimused (test_id, staatus)`, and `tulemustepank (test_id)`.
- Preserve the indexes already supplied by primary-key and unique constraints, including `testisessioonid.test_id`, `graafid_kst.graaf_hash`, and `tulemustepank.vastus_id`.
- Add only indexes justified by real query plans because additional indexes also increase write and storage cost.

## Assumptions and Deferred Work

- The deployed Supabase INSERT webhook invokes the existing YG Edge Function and uses the documented order payload/status values.
- The phase-one MVP runs in a controlled development environment with a permissive authorization dependency. The externally reachable pilot enables the mandatory pre-pilot authorization section above, while still having no student login, Supabase Auth, or RLS changes.
- Only KST and multiple-choice questions are supported.
- No YG migration, OR UI integration, calibration/AN component, WebSockets, queues, Redis, background workers, load balancing, or multi-replica concurrency work is included.
- Full identity management, student accounts, fine-grained administrative roles, general token revocation, production-scale denial-of-service protection, transaction redesign beyond submission idempotency, monitoring infrastructure, and multi-replica hardening remain later phases.

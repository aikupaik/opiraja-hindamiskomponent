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
- Define one domain-focused `AssessmentRepository` interface rather than generic CRUD. Its Supabase implementation covers graph caching, sessions, item-bank access, YG orders, results, and idempotent answer commits.
- Use synchronous FastAPI route functions because `supabase-py` is blocking; FastAPI executes them in its thread pool.
- Use one lifespan-managed synchronous HTTP client for R calls, with explicit connection/read timeouts.
- Keep the application modular by responsibility—API routes, assessment service, repository, R client, and domain models—but deploy it as one process.
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
- Poll the idempotent start endpoint every three seconds only while it returns `202`; clean up polling when the component unmounts or status changes.
- Render one accessible radio-group question at a time, disable submission until an option is selected, and prevent double submission.
- Never receive the answer key, posterior, node parameters, or correctness result.
- Preserve current Estonian learner-facing copy and the three feedback sections: “Juba oskad”, “Võid õppida / rohkem süveneda”, and “Tasuks korrata”.
- Do not reveal correctness after each answer; show only the next question or final feedback.

## Interfaces, State, and Data Flow

### Public API

- `POST /api/v1/tests`
  - Input: `user_id`, `learning_path_id`, optional `course`/`goal`, `method="kst"`, optional `cognitive_level`, `nodes: string[]`, and `relations: {from,to}[]`.
  - Output: `test_id`, `status`, `player_url`, and `missing_nodes`.
  - Builds/caches the graph, creates the session, checks item coverage, and either activates immediately or creates one non-duplicate `yg_tellimused` row.

- `GET /api/v1/tests/{test_id}`
  - Read-only OR-facing polling endpoint.
  - Returns `preparing`, `active`, `completed`, or `failed`; completed responses include mapped feedback.

- `POST /api/v1/player/tests/{test_id}/start`
  - Idempotent player command.
  - While YG is pending, returns `202` with `Retry-After: 3`.
  - When coverage becomes complete, builds and stores the R model, activates the session, selects and persists the first question, and returns it.
  - Repeated calls return the already-persisted question and option order.
  - YG status `viga` marks the session failed.

- `POST /api/v1/player/tests/{test_id}/answers`
  - Input: `submission_id` and opaque `option_id`.
  - Resolves the selected text server-side, scores it, calls R `/advance`, commits the result/session state, and returns either the next question or final feedback.
  - Replaying an accepted `submission_id` returns the current session view without inserting another result.
  - Unknown stale tokens return `409`; unknown tests return `404`; unavailable R/Supabase returns `503` without advancing state.

Question responses contain `submission_id`, `item_id`, instruction, prompt, optional stimulus, and ordered `{id,text}` options only.

### Persistence

- Add one documented migration: `tulemustepank.submission_id uuid NOT NULL DEFAULT gen_random_uuid()` with a unique constraint. No other table changes.
- Extend `tp_seisund` JSONB with a schema version and `current_question`, containing the submission token, chosen item/node, and stable option order.
- Keep posterior and answered-item history in `tp_seisund`; keep the R model and KST configuration snapshot in `testi_loogika`; retain the existing `lopp_profiil` structure.
- Commit results idempotently using the unique submission ID, then compare-and-set `tp_seisund` against the expected current submission token. A retry can safely finish an interrupted update.
- Treat `kasutamiste_arv` as pilot telemetry; increment only for the request that first inserts the submission.
- Do not depend on the undocumented `testisessioonid.kursus` column. Course is used when creating a YG order but not for item eligibility.
- New sessions are identified by their JSON schema version. Existing rows are preserved but old planning/active sessions are not resumed or migrated.

## Implementation Order

1. Capture the current R behavior in numerical regression fixtures before removing Shiny entrypoints; document the experimental KST configuration and API contracts.
2. Add the `submission_id` migration and repository/domain interfaces with in-memory fakes.
3. Extract the pure KST functions into the R service, add Plumber contracts, validation, health checks, `testthat`, and `renv`.
4. Implement FastAPI creation, preparation/YG polling, question selection, scoring, idempotent answer handling, feedback mapping, and structured logs keyed by `test_id`/request ID.
5. Build the React player and behavior tests, then replace the Shiny UI/API entrypoints.
6. Add Docker Compose with `web`, `api`, and `r-service`; only `web` publishes a host port. Supabase secrets go only to `api`.
7. Verify the deployed Supabase webhook contract with one real missing-coverage test, then update the README with local startup, configuration, migration, smoke-test, and VM deployment instructions.

## Test and Acceptance Plan

- R tests: chain and relation-free knowledge spaces, known Bayesian vectors, half-split validity, natural and safety-cap stopping, five-way profile classification, malformed matrices, and configuration snapshots.
- Backend tests: covered versus missing item banks, duplicate YG prevention, YG success/failure, stable reloads, hidden answer keys, correct/incorrect scoring, stale tokens, duplicate answer replay, completion, R failure, and Supabase failure.
- Contract tests run FastAPI against the real Dockerized R service; normal backend unit tests replace both R and Supabase through dependency injection.
- React tests use Vitest and Testing Library for preparation polling, timer cleanup, accessible option selection, disabled/double-submit behavior, reloads, errors, completion, and all feedback sections.
- Supabase/YG tests are opt-in smoke tests against the configured pilot project, not part of normal unit-test execution.
- End-to-end acceptance: `docker compose up --build` starts healthy services; a created link survives browser/API container restarts; missing items progress through the existing webhook; every accepted submission creates exactly one result; and a test reaches reproducible final feedback.
- Changing `MAX_GRAPH_NODES` in one setting changes the enforced limit; changing the KST configuration file affects new sessions while existing sessions retain their stored configuration.

## Assumptions and Deferred Work

- The deployed Supabase INSERT webhook invokes the existing YG Edge Function and uses the documented order payload/status values.
- The pilot runs in a controlled environment with UUID links but no login, Supabase Auth, service-to-service authorization, or RLS changes.
- Only KST and multiple-choice questions are supported.
- No admin UI, YG migration, OR UI integration, calibration/AN component, WebSockets, queues, Redis, background workers, load balancing, or multi-replica concurrency work is included.
- Production hardening for approximately 100 simultaneous students, transaction redesign beyond submission idempotency, monitoring infrastructure, and authentication are later phases.

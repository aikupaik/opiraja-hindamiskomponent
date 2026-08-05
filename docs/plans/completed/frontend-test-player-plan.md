# Prerequisite 2: React Test Player

**Status: complete (2026-08-04).** Implemented and accepted locally through
the real Compose/API flow. Deployment-VM rollout remains part of the separate
deployment procedure, not this prerequisite implementation.

## Summary

- Replace the Vite starter in `frontend/` with an Estonian, accessible
  assessment player for `/test/{test_id}`.
- Keep the admin dashboard and player as separate React applications and
  separate runtime containers. The admin web service continues to own `/`; its
  Nginx forwards `/test/*` to the internal player container and `/api/*` to
  FastAPI.
- Do not introduce a shared UI package now. The learner player and operator
  dashboard have different users, presentation, state, and security
  lifecycles. Priority 3 can later extract only genuinely shared API-client
  infrastructure.
- Treat the player URL as unlisted—not secured—during the permissive phase. It
  will not be linked from the admin UI, but anyone who knows a valid UUID can
  open it until JWT enforcement is implemented.
- Make no backend, persistence, or public API contract changes.

## Player Application and API Client

- Keep one React root with no routing or global-state library. On startup,
  parse `window.location.pathname` as exactly `/test/{canonical UUID}`:
  - accept a hyphenated UUID case-insensitively and normalize it to lowercase;
  - ignore query parameters and fragments during the permissive phase;
  - render “Testi link ei ole kehtiv” and make no API request for missing,
    malformed, or extra path segments.
- Represent the UI with a discriminated state model:
  - `preparing`: initial `start` request or documented preparation polling;
  - `question`: persisted question plus current selection;
  - `submitting`: question, selection, and immutable pending submission payload;
  - `completed`: final feedback;
  - `failed`: generic learner message, diagnostic request ID, and an optional
    typed recovery action.
- Add a typed player API module for:
  - `POST /api/v1/player/tests/{test_id}/start`, with no request body;
  - `POST /api/v1/player/tests/{test_id}/answers`, with JSON
    `{submission_id, option_id}`;
  - decoding the documented preparing, active-question, and completed unions;
  - decoding application envelopes, FastAPI validation errors,
    malformed/non-JSON responses, HTTP status, and `X-Request-ID`;
  - accepting an `AbortSignal` on every request.
- Add one credential-source boundary used by the API client when constructing
  headers. Its permissive implementation always returns no credential; query
  strings and fragments are not credentials. Later JWT work will replace this
  bootstrap implementation with fragment extraction and attach the bearer
  token here, without changing feature components.
- Never use `localStorage`, `sessionStorage`, cookies, telemetry, or logs for
  question or credential state.

## State Transitions and Learner Experience

- Call `start` immediately for every valid page load:
  - `200 active` renders the exact persisted question and returned option order;
  - `200 completed` renders feedback immediately;
  - `202 preparing` schedules one new `start` call;
  - no other status starts a polling loop.
- For each `202`, parse the integer `Retry-After` seconds, fall back to three
  seconds if the header is absent or malformed, and add fresh positive jitter
  of 1–1000 ms. Maintain at most one timer and one in-flight request.
- Abort the current request and clear the timer on unmount, retry/recovery, or
  transition away from preparation. Ignore responses belonging to an aborted
  or superseded request.
- Render questions with native accessible controls:
  - instruction and optional stimulus precede the prompt;
  - use a `<fieldset>` and `<legend>` with one radio input and label per option;
  - preserve server order and use opaque option IDs only as values;
  - keep “Edasi” disabled until selection and while submitting;
  - reset selection when a new persisted question arrives;
  - use live status text for preparation/submission and `role="alert"` for
    failures.
- On submission, capture the current server-provided `submission_id` and
  selected `option_id` before sending:
  - repeated clicks cannot create additional requests;
  - a successful active response replaces the question;
  - a successful completed response immediately replaces the question with
    feedback;
  - transport errors, `503`, and other uncertain server failures show “Proovi
    uuesti” and retain the exact captured payload for retry;
  - `409` offers “Laadi test uuesti,” which calls `start` to recover the
    authoritative persisted state;
  - definitive `403`, `404`, or validation failures render generic Estonian
    terminal messages without exposing backend details;
  - show the request ID as a diagnostic reference when available.
- Reload always starts from backend state:
  - preparing tests resume `start` polling;
  - active tests restore the persisted question and stable option order;
  - completed tests restore feedback;
  - an answer accepted just before reload yields the next question or
    completion, while an unaccepted answer yields the original persisted
    question.
- Render `summary` when present and always render these three sections,
  including legacy empty-state copy:
  - “Juba oskad”
  - “Võid õppida / rohkem süveneda”
  - “Tasuks korrata”
- When `confidence_limited` is true, show the legacy explanation that the test
  could not distinguish the learner’s knowledge with enough confidence. Never
  display correctness, answer keys, posterior/KST data, internal node identity,
  submission IDs, or item IDs.
- Use a responsive learner-specific design based on the restrained legacy
  player palette. Set the document language to Estonian, use no external
  fonts/assets, and do not reuse admin-dashboard presentation components.

## Runtime, Routing, and Documentation

- Give the player its own production Dockerfile and unprivileged Nginx
  configuration, following the existing read-only/container-hardening pattern.
- Configure Vite’s production base as `/test/`, producing collision-free assets
  under `/test/assets/`; use `/` during development and proxy `/api` to local
  FastAPI.
- Player Nginx:
  - serves hashed `/test/assets/*` with immutable caching;
  - serves the SPA shell without long-term caching for `/test/*`;
  - exposes only an internal health endpoint and returns `404` for unrelated
    paths;
  - does not proxy API requests—the browser calls same-origin `/api/*` through
    the public web tier.
- Replace the admin Nginx `/test/*` denial with a proxy to the player service
  while retaining `404` for bare `/test`. Keep `/`, admin assets, API proxying,
  security headers, and public port ownership unchanged.
- Add a hardened `player` service to `compose.yaml` on the edge network with no
  published host port. The existing `web` service remains the only published
  Compose service and waits for player health.
- Update player/root deployment documentation and stale architecture
  assumptions to explain:
  - standalone player development;
  - full same-origin Compose routing;
  - the unlisted-but-not-secured pre-JWT limitation;
  - reload and retry behavior;
  - the future credential bootstrap boundary.
- Mark Priority 2 complete in the JWT plan only after all automated and
  end-to-end acceptance checks pass.

## Test and Acceptance Plan

- Add Vitest, jsdom, Testing Library, user-event, and a `npm test` script to the
  player package.
- Path and client tests cover valid/invalid paths, no request for invalid links,
  exact request methods/bodies, absent credentials, conditional bearer
  attachment through the credential source, runtime response decoding, generic
  error mapping, and request-ID retention.
- Polling tests use fake timers and deterministic randomness to verify:
  - immediate initial `start`;
  - exact `Retry-After` plus fresh positive jitter;
  - fallback delay for an invalid header;
  - one timer/request per cycle;
  - polling only after `202`;
  - cleanup and abort on unmount, success, failure, retry, and state transition.
- Interaction tests cover radio-group semantics and keyboard use, stable option
  order, required selection, disabled submitting state, double-click prevention,
  selection reset, and no correctness disclosure.
- Retry tests verify that an uncertain answer retry sends byte-equivalent
  `submission_id` and `option_id`, while `409` recovery calls `start` instead of
  inventing client state.
- Reload tests remount the application against preparing, active, advanced, and
  completed backend views and verify recovery uses persisted API state rather
  than browser storage.
- Feedback tests cover populated and empty arrays, nullable summary, all three
  fixed headings, and the confidence-limited notice.
- Run:
  - player `npm test`, `npm run lint`, and `npm run build`;
  - admin `npm test`, `npm run lint`, and `npm run build` because its Nginx
    boundary changes;
  - both Nginx configuration checks through image builds;
  - `docker compose config` and full Compose health checks.
- Routing smoke tests verify `/` serves admin, `/test` returns `404`,
  `/test/{uuid}` serves the player shell, player assets resolve under
  `/test/assets/`, `/api/*` remains same-origin, and the player has no published
  host port.
- Final real-flow acceptance creates a test through the real API, opens its
  returned relative link, exercises preparation and question submission through
  completion, refreshes during preparation/active/completed states, and confirms
  the final three-section feedback contains no restricted assessment data.

## Assumptions and Defaults

- Explicit retry is used for transient failures; only documented `202`
  preparation responses trigger automatic polling.
- Final feedback appears immediately rather than using the legacy intermediate
  “Tulemused” button.
- The player remains Estonian-only for this prerequisite.
- No progress count is shown because the public API does not expose a stable
  total or question position.
- Separate services share the existing origin and security headers; no CORS
  configuration or additional public port is introduced.
- Reusable UI extraction is deferred. Priority 3 may introduce a narrow shared
  API package after both clients’ error, request-ID, abort, and credential
  behavior can be compared against working implementations.

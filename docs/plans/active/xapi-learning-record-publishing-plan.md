# xAPI 1.0.3 Learning-Record Publishing

## Summary

Implement the assessment backend as an xAPI Learning Record Provider. It will
produce immutable xAPI Statements and asynchronously POST them to an external
Learning Record Store (LRS). Data collectors will query that LRS through its
standard xAPI API.

A full LRS will not be built: conformant LRS implementations must support
substantially more than Statements, including Agent, Activity, State, Profile,
and About resources. See the
[ADL xAPI communication specification](https://github.com/adlnet/xAPI-Spec/blob/master/xAPI-Communication.md).

`testisessioonid` and `tulemustepank` remain authoritative. LRS availability
never blocks a student's test.

## Statement Contract

| Event | xAPI representation |
| --- | --- |
| First authorized player start | `initialized` verb; object is the test Activity; timestamp is the new learner-start time |
| Accepted answer | `answered` verb; object is a `cmi.interaction` choice Activity; result contains response ID, `success`, and raw/scaled 0-or-1 score |
| Final accepted answer | Emit the answer Statement, then `completed`; completion result contains ISO-8601 duration and the final profile extension |

All Statements will:

- Identify the learner with an Agent `account`: configured `homePage` plus the
  existing stable `kasutaja_id` as `name`.
- Use `test_id` as `context.registration`.
- Use controlled Activity IRIs under a required `XAPI_ACTIVITY_BASE_IRI` for
  tests, items, learning paths, courses, and objectives.
- Use the test as the answer Activity's parent; course and learning path as
  grouping Activities; and an assessment-profile IRI as category.
- Carry Estonian item text, choice descriptions, `correctResponsesPattern`,
  instruction/stimulus extensions, method/goal context, and completed
  final-profile data.
- Generate stable choice IDs from item ID, canonical option position, and
  text, not the player's random opaque option UUID.
- Omit `stored`, `authority`, and the Statement `version`; the LRS supplies
  these. Requests carry `X-Experience-API-Version: 1.0.3`. See the
  [ADL Statement and interaction model](https://github.com/adlnet/xAPI-Spec/blob/master/xAPI-Data.md).
- Exclude posterior probabilities, KST model/cache contents, calibration
  parameters, JWTs, and signing secrets.

## Implementation Changes

- Extend the session model and `testisessioonid` with nullable `kursus`,
  `oppija_alustatud`, `lopetatud`, and `xapi_seadistus`. The configuration
  snapshot contains mapping version, xAPI version, language, Activity base
  IRI, and Actor account home page; no credentials. Existing sessions keep it
  null and are not exported.
- Mark learner start idempotently on the first `/start` request, including
  while preparation is pending. Set completion time from the final accepted
  answer timestamp. Tighten creation validation so learner and learning-path
  identifiers cannot be blank.
- Add `xapi_outbox` with a unique source key, Statement UUID, event type,
  immutable event snapshot, materialized Statement JSON, occurrence time,
  retry/lease state, delivery timestamp, and redacted failure code.
- Add database triggers that atomically enqueue snapshots when a tracked
  session first starts, an answer is inserted, or a tracked session becomes
  completed. This avoids changing the existing answer-commit recovery
  semantics while preventing lost learning events.
- Add a dedicated Python xAPI module containing strict Pydantic Statement
  types, the versioned event-to-Statement mapper, a Supabase outbox adapter,
  and a lifespan-managed publisher.
- Have the publisher claim work through a service-role-only PostgreSQL RPC
  using leases and `FOR UPDATE SKIP LOCKED`, materialize each Statement once,
  and send Statements individually with stable IDs and HTTP Basic
  authentication.
- Treat matching `200` responses and duplicate `204` responses as delivered.
  Retry transport errors, `408`, `429`, and `5xx` with jittered exponential
  backoff capped at five minutes; pause on authentication/endpoint
  configuration errors; quarantine invalid or conflicting Statements such as
  `400`, `409`, or `413`.
- Add `XAPI_ENABLED=false` plus conditionally required LRS Statements URL,
  Basic credentials, Activity base IRI, and Actor account home-page settings.
  Validate HTTPS outside loopback. Never log credentials, Actor IDs,
  responses, item text, or LRS response bodies.
- Keep API readiness independent of the LRS. Emit redacted
  delivery/backlog/dead-letter diagnostics and document inspection, requeue,
  credential rotation, and rollback procedures.
- Purge delivered Statement payloads and event snapshots after 30 days while
  retaining the Statement ID, source key, and delivery timestamp as an
  idempotency receipt.
- Add a documented, versioned project vocabulary for every custom Activity
  and extension IRI. No frontend, player API response, Nginx route, or public
  xAPI endpoint changes are required.

## Test and Rollout Plan

- Unit-test exact initialized, answered, and completed JSON; stable IDs; Agent
  accounts; interaction choice formatting; timestamps/duration; context
  hierarchy; final-profile extensions; and absence of nulls or internal KST
  data.
- Test idempotent start, answer replay, final-answer ordering, concurrent
  trigger behavior, outbox uniqueness, lease recovery, retry classification,
  `Retry-After`, credential redaction, payload cleanup, and disabled
  configuration.
- Apply the migration to a local/test Supabase instance and verify each source
  transaction creates exactly one outbox event, including interrupted answer
  recovery.
- Use a mock LRS to verify Basic authentication, required headers, response-ID
  checking, retries, and that LRS failure never changes assessment API
  results.
- Run the backend suite and `backend/.venv/bin/python -m pyright`; Pyright must
  report no errors.
- Deploy the additive migration first, then the backend with xAPI disabled.
  Once an LRS is selected, configure a controlled namespace and test tenant,
  enable xAPI for newly created sessions, and verify the three Statements can
  be retrieved by registration and Actor.
- Roll back by disabling the publisher; preserve pending outbox records for
  later delivery.

## Assumptions

- xAPI 1.0.3 is intentionally targeted although IEEE 9274.1.1/xAPI 2.0 is the
  current standard. The mapper remains versioned so 2.0 can be added later.
  See the
  [current IEEE xAPI standard](https://opensource.ieee.org/xapi/xapi-base-standard-documentation).
- Initial authentication support is HTTP Basic. Vendor-specific OAuth or
  bearer authentication is added only if the eventual LRS requires it.
- Only sessions created while `XAPI_ENABLED` is active are tracked; existing
  sessions and answers are not backfilled.
- `kasutaja_id` is stable and unique within the configured Actor account
  system.
- Sending learner identifiers, answers, item content, and answer-key metadata
  to the selected LRS will receive the required privacy, access-control, and
  retention approval before production enablement.

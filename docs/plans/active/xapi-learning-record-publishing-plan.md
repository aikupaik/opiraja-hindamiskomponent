# xAPI 1.0.3 Publishing to Learning Locker

## Summary

Implement the assessment backend as an xAPI Learning Record Provider (LRP).
It will produce immutable xAPI Statements and asynchronously publish them to
the existing Learning Locker Learning Record Store (LRS). Learning Locker is
an external managed dependency: this project does not install, configure, or
operate the LRS itself.

Use only Learning Locker's standard xAPI HTTP interface, normally rooted at
`https://<host>/data/xAPI`. Do not integrate with Learning Locker's internal
MongoDB, `/api/v2` REST API, queues, or UI data model. Learning Locker documents
both the [xAPI endpoint and Basic authentication](https://learninglocker.atlassian.net/wiki/spaces/DOCS/pages/106496109/xAPI)
and its [client/store model](https://learninglocker.atlassian.net/wiki/spaces/DOCS/pages/106496046/Clients).

`testisessioonid` and `tulemustepank` remain authoritative for assessment
state. Learning Locker is authoritative only for the accepted copy of the
published learning record. LRS slowness or unavailability never blocks or
changes a student's test.

## Scope and Ownership

This project owns:

- the event-to-Statement mapping and project xAPI vocabulary;
- the stable Statement IDs, outbox, delivery retries, and diagnostics;
- the learner Actor identifier mapping and Activity IRIs;
- xAPI conformance of every request sent to Learning Locker; and
- application-side secret handling and credential rotation.

The Learning Locker provider owns:

- the Learning Locker deployment, upgrades, availability, backups, and
  monitoring;
- organisations, stores, clients, client authority, and permissions;
- the HTTPS endpoint, certificate, ingress limits, and any IP allowlist;
- LRS-side retention, access control, audit, and privacy procedures; and
- separate credentials for downstream data collectors.

This plan does not add a public xAPI endpoint to the assessment service and
does not give the browser or React applications LRS credentials.

## Statement Contract

| Assessment event | xAPI representation |
| --- | --- |
| First authorized player start | `initialized` verb; object is the test Activity; timestamp is the new learner-start time |
| Accepted answer | `answered` verb; object is a `cmi.interaction` Activity with `interactionType: "choice"`; result contains the selected canonical choice ID in `response`, `success`, and raw/min/max/scaled 0-or-1 score |
| Final accepted answer | Publish the answer Statement first, then `completed`; the completion result contains `completion: true`, ISO-8601 duration, and the final-profile extension |

All Statements will:

- identify the learner with an Agent `account`: configured `homePage` plus
  the existing stable `kasutaja_id` as `name`. The `homePage` is the canonical
  identifier of our learner-account namespace, not the Learning Locker URL;
- use `test_id` as `context.registration` and validate that it is a UUID;
- use controlled Activity IRIs under a required `XAPI_ACTIVITY_BASE_IRI` for
  tests, items, learning paths, courses, and objectives;
- use the test as the answer Activity's parent; course and learning path as
  grouping Activities; and the versioned assessment-profile IRI as category;
- carry Estonian item text, choice descriptions, `correctResponsesPattern`,
  instruction/stimulus extensions, method/goal context, and completed
  final-profile data;
- generate stable choice IDs from item ID, canonical option position, and
  text, not the player's random opaque option UUID;
- use standard ADL verb and Activity-type IRIs where they exist, and
  project-owned HTTPS IRIs for every custom Activity type and extension;
- omit `stored`, `authority`, and Statement `version`. Learning Locker adds
  them; in particular, `authority` comes from the configured Learning Locker
  client;
- include `Accept: application/json`, `Content-Type: application/json` where
  there is a body, and `X-Experience-API-Version: 1.0.3` on every LRS request;
  and
- exclude posterior probabilities, KST model/cache contents, calibration
  parameters, JWTs, and signing or LRS credentials.

The mapper must produce the same complete JSON for a source event forever.
Do not enrich or regenerate an already materialized Statement after a mapping,
item, or profile definition changes.

## Learning Locker Integration Contract

### Store and client isolation

Use a dedicated Learning Locker store for this application in each
environment. At minimum, test and production have different stores and
different clients. Do not publish test Statements into the production store.
A shared production store is acceptable only after an explicit privacy and
access review, because standard Learning Locker read scopes apply to the
store rather than to an Activity-IRI prefix. Use separate organisations too
when the people allowed to view or administer test and production differ;
Learning Locker organisation membership controls UI visibility across its
stores.

Create one dedicated, enabled publisher client bound to each store. Grant the
minimum Learning Locker scopes accepted by the installed version:

- `statements/write`; and
- `statements/read/mine`, because Learning Locker documents that its
  `statements/write` scope must be paired with a read scope.

The Learning Locker client binding selects the store. The backend does not
send or configure the Learning Locker organisation or store ID at runtime.

Do not grant the publisher `xapi/all`, `all`, `all/read`, State/Profile access,
or Learning Locker administrative/API permissions. If the provider's version
or policy cannot express the proposed minimum, record the actual scopes and
approve the exception before production. Learning Locker may automatically
create an enabled `all`-scope client with a new store; the operator must reduce
or replace that default before handing it over.

Data collectors use separate read-only clients. A collector that needs all
Statements in this application's dedicated store normally receives
`statements/read`; it must not reuse the publisher key or receive a write or
admin scope. Collector provisioning and queries are outside the backend
implementation, but successful readback is a rollout acceptance test.

### Authentication and authority

Use HTTPS and HTTP Basic authentication with the Learning Locker client Key
as username and Secret as password. Store Key and Secret as separate secrets;
construct the `Authorization` header in the HTTP client and never accept or
persist a pre-encoded header value. Learning Locker recommends Basic auth for
server-to-server xAPI integrations. OAuth bearer-token support is not in the
initial scope.

Configure the publisher client's Learning Locker authority as a non-personal
service Agent, preferably using an `account` inverse functional identifier,
for example:

```json
{
  "objectType": "Agent",
  "name": "Õpiraja hindamiskomponent (production)",
  "account": {
    "homePage": "https://<project-controlled-authority-namespace>",
    "name": "opiraja-hindamiskomponent-production"
  }
}
```

The exact authority is agreed with the provider before provisioning and must
be different for test and production. It identifies the publishing service;
it is not the learner Actor and must not use an employee's email address.

### Endpoint and delivery semantics

Configure the xAPI base URL, for example `https://lrs.example/data/xAPI`, not
a Learning Locker UI or `/api/v2` URL. Derive the following resources without
discarding a provider-supplied path prefix:

- `GET <base>/about` for provisioning and deployment smoke tests; and
- `POST <base>/statements` for publishing; and
- `GET <base>/statements?statementId=<uuid>&format=exact` only to resolve an
  ambiguous or duplicate publishing result.

Publish Statements individually with their stable UUID in the JSON `id`. The
xAPI 1.0.3 specification recommends `POST` when an LRP supplies an ID; the
normal success response is `200 OK` with an array containing that ID. A retry
after an ambiguous timeout sends the identical materialized Statement with
the same ID. Learning Locker must not insert or modify anything when that ID
already exists, but it may report the duplicate as `204` or `409`. Resolve
either response by reading that ID with `format=exact` and comparing all
application-supplied fields while ignoring the LRS-supplied `stored`,
`authority`, and `version`. Retry a temporarily absent readback because an LRS
may accept a Statement before it becomes queryable. See the
[xAPI 1.0.3 Statement resource](https://github.com/adlnet/xAPI-Spec/blob/master/xAPI-Communication.md#212-post-statements).

Classify responses as follows:

| Result | Publisher behavior |
| --- | --- |
| `200` with exactly the submitted ID | Mark delivered |
| Duplicate `204` or `409` | `GET` the Statement by ID with `format=exact`; retry boundedly if not yet queryable, mark delivered only if application-supplied fields match, otherwise quarantine |
| Transport failure, timeout, `408`, `429`, or `5xx` | Retry the identical request with jittered exponential backoff; honor bounded `Retry-After` |
| `401` or `403` | Pause publishing and alert: client credential, enabled state, or scope problem |
| `404` or `405` | Pause publishing and alert: wrong base URL, proxy route, or unsupported method |
| `400` or `413` | Quarantine for operator review: invalid Statement or request-size rejection |
| Malformed `200` response | Perform the same exact readback because acceptance is ambiguous; quarantine or pause only after the bounded verification fails |
| Other `4xx` | Quarantine with a redacted status/reason code; do not retry indefinitely |

Never use response-body text as an application error or metric label. It may
be inspected only in a controlled operator workflow because a provider can
echo Statement data.

## Provider Handoff: What to Ask the Learning Locker Operator

Send the provider a request containing the following checklist. Values must
be supplied separately for test and production.

### Required before implementation can be connected

1. **Learning Locker product and version** — confirm whether this is Open
   Source or a managed/enterprise offering and provide the deployed Learning
   Locker and xAPI-service versions. This lets us reproduce vendor-specific
   validation behavior.
2. **Dedicated store** — provide the organisation and store names/IDs, confirm
   that the client is bound to the intended store, and confirm that test and
   production are isolated. Confirm which Learning Locker users and roles can
   see each environment; use separate organisations if those access lists
   differ. Acknowledge that any auto-created broad-scope client has been
   restricted, disabled, or replaced.
3. **Exact xAPI base URL** — provide the externally reachable HTTPS URL ending
   at the xAPI root (commonly `/data/xAPI`), including any tenant or reverse-
   proxy path prefix. Confirm that query strings, `Authorization`,
   `Content-Type`, and `X-Experience-API-Version` headers reach the xAPI
   service unchanged and that the proxy preserves xAPI response headers.
4. **Supported version evidence** — with the provisioned client, confirm that
   `GET <base>/about` succeeds and advertises support compatible with requests
   using xAPI `1.0.3`. Return the status, response version header, and `version`
   array, but no credentials.
5. **Publisher client** — create an enabled/trusted client named for this
   application and environment, bound only to that store, with
   `statements/write` plus `statements/read/mine`. Confirm the final scopes in
   writing and explain any broader permission that cannot be avoided.
6. **Key and Secret** — deliver the Basic-auth Key and Secret through the
   approved secret channel, not email, a ticket, chat, or this repository.
   State who can revoke and rotate them, expected rotation notice, and whether
   old/new credentials can overlap during rotation.
7. **Client authority** — configure and return the exact non-personal Agent
   JSON that Learning Locker will add as `authority`. Confirm that only one
   Agent IFI is present and that test and production authorities differ.
8. **Network requirements** — provide DNS, certificate-chain/private-CA
   requirements, required source-IP allowlisting, and any proxy or mutual-TLS
   requirements. If an allowlist is used, ask us for the backend's stable
   egress IP; do not allowlist learner browsers.
9. **Service limits** — provide request/body-size limits, sustained and burst
   rate limits, connection and request timeouts, maintenance windows, and the
   documented behavior of `429` and `Retry-After`.
10. **Operational contact and service expectations** — identify the incident
    contact, support hours, status/maintenance channel, availability target,
    and escalation path for authentication failures, backlog growth, or
    suspected data loss.
11. **Data governance** — confirm hosting region, subprocessors as applicable,
    encryption in transit/at rest, backup and restore policy, audit-log
    availability, LRS retention period, and the approved process for
    access/export/correction/erasure requests involving pseudonymous learner
    IDs and immutable xAPI Statements.
12. **Read-only verification access** — create a separate collector or
    acceptance-test client with only the required read scope, or nominate the
    provider operator who will perform readback. Never broaden or share the
    publisher credentials merely to run acceptance checks.

### Information we must give the operator

- application and environment names plus technical/privacy contacts;
- expected volume: concurrent sessions, Statements per test, normal and peak
  Statements per minute, and maximum Statement size from a representative
  payload;
- backend egress IPs if the provider uses an allowlist;
- the proposed publisher authority Agent JSON;
- the learner Actor account `homePage`, Activity base IRI, and custom
  vocabulary/profile IRI prefixes we control;
- the three verbs emitted (`initialized`, `answered`, `completed`), absence of
  attachments, and xAPI version header `1.0.3`; and
- the data classification: stable pseudonymous learner identifier, answer and
  correctness data, assessment content/answer key, timestamps, and final
  profile.

The Activity namespace, Actor account namespace, and learner-ID policy are
product/data-governance decisions. The Learning Locker operator may validate
them but must not invent them from the LRS hostname.

## Application Configuration

Add these backend settings:

| Setting | Purpose |
| --- | --- |
| `XAPI_ENABLED=false` | Master switch; only new sessions created while enabled are tracked |
| `XAPI_LRS_BASE_URL` | Provider-supplied HTTPS xAPI root, not the UI URL or a `/statements` URL |
| `XAPI_LRS_KEY` | Learning Locker client Key; secret setting |
| `XAPI_LRS_SECRET` | Learning Locker client Secret; secret setting |
| `XAPI_ACTIVITY_BASE_IRI` | Project-controlled stable Activity/vocabulary namespace |
| `XAPI_ACTOR_ACCOUNT_HOME_PAGE` | Project-controlled learner-account namespace |

When `XAPI_ENABLED=true`, require all five dependent settings. Validate both
IRIs as absolute HTTPS URLs outside exact loopback development hosts, reject
userinfo/query/fragment components for the LRS base URL, and normalize exactly
one path separator when constructing resources. Keep xAPI `1.0.3` and the
mapping version as code-level versioned constants rather than deployment
choices.

The per-session configuration snapshot contains the mapping version, xAPI
version, language, Activity base IRI, and Actor account home page, but never
the LRS hostname, store ID, client authority, Key, Secret, or authorization
header. Endpoint and credential rotation must not change Statement content.

## Implementation Changes

- Extend the session model and `testisessioonid` with nullable `kursus`,
  `oppija_alustatud`, `lopetatud`, and `xapi_seadistus`. Existing sessions keep
  `xapi_seadistus` null and are not exported.
- Mark learner start idempotently on the first authorized `/start` request,
  including while preparation is pending. Set completion time from the final
  accepted answer timestamp. Tighten creation validation so learner and
  learning-path identifiers cannot be blank.
- Add `xapi_outbox` with a unique source key, Statement UUID, event type,
  immutable event snapshot, materialized Statement JSON, occurrence time,
  retry/lease state, delivery timestamp, and redacted failure code.
- Add database triggers that atomically enqueue snapshots when a tracked
  session first starts, an answer is inserted, or a tracked session becomes
  completed. This avoids changing the existing answer-commit recovery
  semantics while preventing lost learning events.
- Preserve ordering per registration: `initialized` before answers and a
  final `answered` before `completed`. A retrying earlier event prevents later
  events for that registration from being claimed, while unrelated tests can
  publish concurrently.
- Add a dedicated Python xAPI module containing strict Pydantic Statement
  types, the versioned event-to-Statement mapper, a Supabase outbox adapter,
  and a lifespan-managed publisher using one bounded `httpx.AsyncClient`.
- Have the publisher claim work through a service-role-only PostgreSQL RPC
  using leases and `FOR UPDATE SKIP LOCKED`, materialize each Statement once,
  and use the Learning Locker `POST` and duplicate-readback contract above.
- Keep API liveness and readiness independent of Learning Locker. Expose
  redacted publisher state, oldest pending age, retry count, delivery count,
  paused reason class, and quarantine count through existing operator
  diagnostics; do not add the LRS to `/health/ready`.
- Never log credentials, authorization headers, Actor IDs, Statement payloads,
  response bodies, item text, or answer data. Include only internal outbox ID,
  event type, attempt count, latency, HTTP status, and redacted reason class.
- Purge delivered Statement payloads and event snapshots from the application
  outbox after 30 days while retaining the Statement ID, source key, and
  delivery timestamp as an idempotency receipt. This does not delete the LRS
  copy and is separate from the provider's retention policy.
- Add a documented, versioned project vocabulary for every custom Activity
  and extension IRI. No frontend, player API response, Nginx route, or public
  xAPI endpoint changes are required.

## Test and Rollout Plan

### Automated tests

- Unit-test exact `initialized`, `answered`, and `completed` JSON; stable IDs;
  Agent accounts; interaction choice formatting; timestamps/duration; context
  hierarchy; final-profile extensions; and absence of nulls or internal KST
  data.
- Test idempotent start, answer replay, final-answer ordering, per-registration
  blocking, cross-registration concurrency, trigger behavior, outbox
  uniqueness, lease recovery, retry classification, bounded `Retry-After`,
  credential redaction, payload cleanup, and disabled configuration.
- Apply the migration to a local/test Supabase instance and verify each source
  transaction creates exactly one outbox event, including interrupted answer
  recovery.
- Use a mock LRS to verify `POST` URL construction, stable JSON Statement IDs,
  Basic authentication, required headers, exact `200` response-ID checking,
  idempotent timeout retry, `204`/`409` exact readback, mismatch quarantine,
  response-version-header diagnostics, pauses, and that LRS failure never
  changes assessment API results.
- Run the backend suite and `backend/.venv/bin/python -m pyright`; Pyright must
  report no errors.

### Provider acceptance and rollout

1. Complete the provider handoff and privacy/security approval. Record
   non-secret store/client metadata and operator contacts in the deployment
   runbook; place Key and Secret only in the secret manager.
2. From the deployed backend network, use the test client to call `/about` and
   verify TLS, routing, authentication, response version header, advertised
   version, latency, and redaction. This is a deployment smoke test, not an API
   readiness dependency.
3. Publish a synthetic Statement to the test store with a UUID reserved for
   provisioning. Verify the first `POST` returns `200` with that UUID. Repeat
   the identical `POST`, observe the installed Learning Locker version's
   duplicate response, and verify exact readback. Change the payload while
   keeping the UUID and verify the original is not modified and the mismatch
   is detectable. Delete or clearly label this synthetic record according to
   provider policy.
4. Apply the additive database migration, deploy the backend with xAPI
   disabled, and verify normal assessment behavior.
5. Enable xAPI only for controlled newly created sessions in the test
   environment. Verify `initialized`, each `answered`, and `completed` can be
   retrieved by both `registration` and Actor using the separate read-only
   client. Verify Learning Locker supplied the agreed authority and `stored`
   fields and preserved all custom IRI keys and UTF-8 Estonian text.
6. Reconcile assessment events to Learning Locker by Statement ID and event
   type; verify exact counts, ordering, timestamps, scores, duration, and no
   cross-store records. Exercise credential failure, throttling if the
   provider supports a safe test, recovery, and credential rotation.
7. Repeat the connection checks against production with a production-specific
   synthetic record, then enable production publishing for newly created
   sessions. Monitor backlog age, quarantines, and auth pauses during the
   agreed observation window.

Roll back by setting `XAPI_ENABLED=false` to stop tracking new sessions and
stop publisher claims. Preserve pending outbox records for later delivery;
disabling does not remove already accepted Learning Locker Statements.

## Operational Runbook Requirements

Document before production:

- how to inspect publisher state and individual redacted failure classes;
- who can pause/resume delivery and requeue a quarantined record after fixing
  its cause;
- how to rotate Learning Locker Key/Secret without exposing them or
  rematerializing Statements;
- how to distinguish provider outage, local network failure, rejected
  credentials, invalid payload, UUID conflict, throttling, and capacity limit;
- reconciliation by source key and Statement ID without logging payloads;
- escalation contacts and what non-sensitive evidence to send the provider;
- the coordinated privacy request process across application and LRS; and
- recovery after an extended outage without bypassing ordering or flooding
  the provider's rate limit.

## Assumptions and Decisions Requiring Confirmation

- xAPI `1.0.3` remains the intentional target. The mapper is versioned so a
  later IEEE xAPI 2.0 mapper can be introduced separately; Learning Locker's
  `/about` response must confirm a compatible 1.0.x interface before rollout.
- Initial authentication is Learning Locker HTTP Basic. Do not add its OAuth2
  extension unless the provider explicitly prohibits long-lived Basic client
  credentials and supplies a tested token contract.
- Only sessions created while `XAPI_ENABLED` is active are tracked. Existing
  sessions and answers are not backfilled.
- `kasutaja_id` is stable and unique within the configured Actor account
  system. Product/privacy owners must still confirm that it is the correct
  pseudonymous identifier to disclose to the provider.
- Sending learner identifiers, answers, item content, answer-key metadata, and
  final profiles to Learning Locker requires privacy, access-control,
  processing-agreement, retention, and erasure-procedure approval before
  production enablement.
- Learning Locker-side dashboards, visualisations, statement forwarding, and
  Learning Locker metadata APIs are not part of this plan.

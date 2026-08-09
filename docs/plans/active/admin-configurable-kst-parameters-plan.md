# Admin-configurable KST parameters plan

## Summary and confirmed current behavior

`R/config/kst.json` is not loaded once at R application startup. The v1 and
v2 model operations call `read_kst_configuration()` while handling each model
request. Health, select, and advance requests do not reread the file.

FastAPI currently builds the model in `AssessmentService.create_assessment()`,
before the learner starts answering. The returned model, including its full
configuration snapshot, configuration hash, and derived limits, is persisted
in `testisessioonid.testi_loogika`. Later select and advance requests send that
stored model back to R, where its configuration and hash are validated. An
active assessment therefore already remains bound to the parameters with which
it was created.

The target design is:

- one global active KST configuration for all newly created assessments;
- immutable configuration drafts with explicit activation and rollback;
- Supabase as the runtime source of truth;
- `R/config/kst.json` retained as the version-controlled initial seed,
  characterization baseline, and fallback for direct/manual R callers;
- FastAPI, rather than R, owns persistence and supplies the selected snapshot
  to the stateless R service.

Runtime editing of `kst.json` is not part of the design. The deployed R image
contains the file at build time, the container root filesystem is read-only,
and there is no shared writable configuration volume. A runtime file would
also create restart, replica synchronization, atomic-write, audit, and
repository synchronization problems.

## Supabase prerequisite

Apply the following additive SQL to Supabase before deploying application code
that reads KST configuration from the database. These are the exact tables,
fields, constraints, indexes, access restrictions, initial seed, and
immutability rules expected by the implementation.

```sql
begin;

create table public.kst_configuration_versions (
    id uuid primary key default gen_random_uuid(),
    schema_version integer not null,
    configuration jsonb not null,
    configuration_hash text not null unique,
    created_by text not null,
    created_at timestamptz not null default now(),

    constraint kst_configuration_versions_schema_version_v1
        check (schema_version = 1),
    constraint kst_configuration_versions_configuration_object
        check (jsonb_typeof(configuration) = 'object'),
    constraint kst_configuration_versions_payload_schema_version
        check (
            jsonb_typeof(configuration -> 'schema_version') = 'number'
            and configuration ->> 'schema_version' = '1'
        ),
    constraint kst_configuration_versions_hash_format
        check (
            configuration_hash
            ~ '^kst-config-v1:sha256:[0-9a-f]{64}$'
        ),
    constraint kst_configuration_versions_created_by_nonblank
        check (length(btrim(created_by)) > 0)
);

create table public.kst_configuration_activations (
    id bigint generated always as identity primary key,
    configuration_version_id uuid not null
        references public.kst_configuration_versions(id)
        on update restrict
        on delete restrict,
    activated_by text not null,
    activated_at timestamptz not null default now(),

    constraint kst_configuration_activations_activated_by_nonblank
        check (length(btrim(activated_by)) > 0)
);

create index kst_configuration_activations_version_history_idx
    on public.kst_configuration_activations
        (configuration_version_id, id desc);


create or replace function public.reject_kst_configuration_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    raise exception '% is append-only; update and delete are forbidden',
        tg_table_name;
end;
$$;

create trigger kst_configuration_versions_append_only
before update or delete on public.kst_configuration_versions
for each row execute function public.reject_kst_configuration_mutation();

create trigger kst_configuration_activations_append_only
before update or delete on public.kst_configuration_activations
for each row execute function public.reject_kst_configuration_mutation();

insert into public.kst_configuration_versions (
    id,
    schema_version,
    configuration,
    configuration_hash,
    created_by
)
values (
    '00000000-0000-4000-8000-000000000001'::uuid,
    1,
    '{
      "feedback_credible_mass": 0.9,
      "reliability_floor": {
        "maximum": 10,
        "minimum": 7,
        "multiplier": 1.5
      },
      "safety_cap": {
        "minimum_above_floor": 1,
        "node_multiplier": 2
      },
      "schema_version": 1,
      "stop_confidence": 0.8
    }'::jsonb,
    'kst-config-v1:sha256:89b7af74a8eca453d36a3410e18f8c221000ea67cc06388418ec675de766c774',
    'repository-seed'
)
on conflict (configuration_hash) do nothing;

insert into public.kst_configuration_activations (
    configuration_version_id,
    activated_by
)
select
    version.id,
    'repository-seed'
from public.kst_configuration_versions as version
where version.configuration_hash =
    'kst-config-v1:sha256:89b7af74a8eca453d36a3410e18f8c221000ea67cc06388418ec675de766c774'
  and not exists (
      select 1
      from public.kst_configuration_activations
  );

commit;
```

The tables have these responsibilities:

| Table | Field | Meaning |
| --- | --- | --- |
| `kst_configuration_versions` | `id` | Stable identifier for an immutable version. |
|  | `schema_version` | KST configuration wire-schema version; initially exactly `1`. |
|  | `configuration` | Validated full configuration snapshot as JSONB. |
|  | `configuration_hash` | Unique canonical R hash, used to identify and verify the snapshot. |
|  | `created_by` | Admin JWT subject or `repository-seed`. |
|  | `created_at` | Database creation time. |
| `kst_configuration_activations` | `id` | Monotonic activation sequence and primary key. |
|  | `configuration_version_id` | Activated immutable version. |
|  | `activated_by` | Admin JWT subject or `repository-seed`. |
|  | `activated_at` | Database activation time. |

The active configuration is the activation with the greatest `id`, joined to
its version. Activation is one insert into
`kst_configuration_activations`; no existing row is updated. Reactivating an
older version is the rollback operation and creates another audit event.

Both tables are server-managed.

Before application deployment, verify the seed with:

```sql
select
    activation.id as activation_id,
    activation.activated_at,
    version.id as version_id,
    version.configuration_hash,
    version.configuration
from public.kst_configuration_activations as activation
join public.kst_configuration_versions as version
  on version.id = activation.configuration_version_id
order by activation.id desc
limit 1;
```

The query must return the seeded hash above and the snapshot currently stored
in `R/config/kst.json`. Supabase changes are applied manually through the
Supabase UI; the project does not contain, and will not introduce, an automatic
migration workflow or repository migration artifact.

The seed was applied and verified through the Supabase UI on 2026-08-07. The
confirmation query returned activation `1` at
`2026-08-07 11:29:01.219956+00`, version
`00000000-0000-4000-8000-000000000001`, activated by `repository-seed`, with
hash `kst-config-v1:sha256:89b7af74a8eca453d36a3410e18f8c221000ea67cc06388418ec675de766c774`.

## R service and internal contracts

- Add the full `configuration` object to v1 and v2 model requests as an
  optional, backward-compatible field. FastAPI always supplies it. If a
  direct/manual caller omits it, R reads `kst.json` as it does today.
- Add `POST /internal/v2/kst/configuration/validate`. It accepts a
  configuration object and returns R's canonical snapshot and
  `kst-config-v1:sha256:...` hash. Draft creation and activation call this
  operation so R remains authoritative for configuration validation and hash
  generation.
- In the v2 OpenAPI document, replace the permissive
  `Configuration.additionalProperties: true` definition with the exact nested
  fields and constraints already enforced by `validate_kst_configuration()`.
- When a supplied configuration is present, validate and canonicalize it in
  memory rather than reading the file. Model responses continue to include the
  snapshot, hash, reliability floor, and safety cap.
- Select and advance continue to validate the configuration/hash embedded in
  the supplied model. They never consult the currently active database version
  or `kst.json`.
- Keep contract examples fixed and fixture-backed. Examples describe valid
  payloads; they are not assertions about the currently active runtime version.

The validation operation has this wire shape:

```json
{
  "configuration": {
    "feedback_credible_mass": 0.9,
    "reliability_floor": {
      "maximum": 10,
      "minimum": 7,
      "multiplier": 1.5
    },
    "safety_cap": {
      "minimum_above_floor": 1,
      "node_multiplier": 2
    },
    "schema_version": 1,
    "stop_confidence": 0.8
  }
}
```

```json
{
  "configuration": {
    "feedback_credible_mass": 0.9,
    "reliability_floor": {
      "maximum": 10,
      "minimum": 7,
      "multiplier": 1.5
    },
    "safety_cap": {
      "minimum_above_floor": 1,
      "node_multiplier": 2
    },
    "schema_version": 1,
    "stop_confidence": 0.8
  },
  "configuration_hash": "kst-config-v1:sha256:89b7af74a8eca453d36a3410e18f8c221000ea67cc06388418ec675de766c774"
}
```

Invalid configuration returns the existing `422 validation_error` envelope.
Unexpected R failures retain the existing `500` envelope and FastAPI maps R
unavailability or contract violations to `503`.

## Backend configuration flow and Admin API

Introduce a narrow `KstConfigurationRepository` instead of making assessment
logic depend on the broader admin repository. Its production Supabase
implementation provides:

- `get_active_configuration()` by reading the greatest activation ID and its
  joined version;
- `list_configuration_versions()` with each version's latest activation
  metadata and whether it is currently active;
- `insert_configuration_version()` as an insert-only operation;
- `activate_configuration_version()` as an insert-only activation event.

At assessment creation:

1. Read the active configuration once.
2. Pass that exact snapshot to `KstEngine.build_model()`.
3. Require the returned snapshot and hash to match the selected version.
4. Persist the returned model in `testi_loogika` as today.
5. Never reread or rebind configuration during start, select, answer, or
   completion.

The configuration lookup defines the activation boundary. If activation races
with assessment creation, the assessment uses whichever version its completed
lookup returned. Missing active configuration is an operational configuration
failure returned as `503`; FastAPI must not silently fall back to the R file.

Add these authenticated endpoints:

- `GET /api/v1/admin/kst-configurations`
  - requires `admin:read`;
  - returns `active_version_id` and versions ordered newest first;
  - each version contains `id`, `schema_version`, `configuration`,
    `configuration_hash`, `created_by`, `created_at`, `is_active`, and nullable
    `last_activated_by`/`last_activated_at`.
- `POST /api/v1/admin/kst-configurations`
  - requires `admin:write`;
  - accepts exactly one strict KST configuration object;
  - validates it through R, then stores the returned canonical snapshot/hash;
  - returns `201` with the immutable version;
  - maps an existing identical hash to `409 configuration_already_exists`.
- `POST /api/v1/admin/kst-configurations/{version_id}/activate`
  - requires `admin:write`;
  - reloads the version and revalidates it through R;
  - requires R's snapshot/hash to match the stored row before inserting the
    activation;
  - returns the newly active version;
  - returns `404` for an unknown ID and `409` when it is already active.

Use the authenticated admin subject for `created_by` and `activated_by`.
Continue using the existing `admin:read` and `admin:write` capabilities; no new
JWT scope is required.

## Admin UI

- Add a `KST parameters` navigation tab.
- Load the active version and version history from the admin API.
- Present typed numeric controls for all schema-v1 fields rather than a raw
  JSON editor. Apply the same field ranges client-side for immediate feedback,
  while treating backend/R validation as authoritative.
- Show the active hash, creator, and activation time.
- Preview reliability-floor and safety-cap results for node counts from `1`
  through the session's `max_graph_nodes`.
- `Save draft` creates a new immutable version but does not activate it.
- `Activate` requires an explicit confirmation explaining that only
  assessments created afterward are affected.
- Historical versions expose `Reactivate` as the rollback action. There are no
  edit or delete actions for stored versions or activations.
- Refresh active state and history after every successful save or activation,
  and surface safe request-reference errors through the shared API client.

## R test and fixture changes

- Decouple frozen prototype characterization from the configurable runtime
  seed. Keep the original parameter values, configuration hash, stopping
  boundaries, and numerical expectations in a dedicated fixed fixture.
- Stop generating the prototype fixture's expected hash or stopping results
  from live `kst.json`.
- Test `kst.json` only for strict schema validity, canonical serialization,
  sorted canonical keys, and a self-consistent hash. Valid value changes must
  not require regeneration of unrelated numerical fixtures.
- Inject the fixed prototype configuration explicitly into numerical
  characterization tests.
- Add table-driven configuration validation tests for every allowed range,
  unknown/missing fields, finite numbers, integer requirements, and
  `reliability_floor.minimum <= maximum`.
- On one router instance, submit model requests with configuration A and then B
  and verify different snapshots, hashes, and derived limits without an R
  restart.
- Advance a model created with A after validating/building B and verify that
  the assessment still uses embedded A.
- Test request-supplied configuration precedence, invalid supplied
  configuration as `422`, persisted snapshot/hash mismatches, and the
  direct/manual file fallback.
- Update OpenAPI tests for the exact configuration schema, validation endpoint,
  and supplied model configuration while leaving fixed examples independent
  of runtime activation.

## Backend, persistence, and UI tests

- Repository tests cover decoding, insert payloads, active lookup, ordered
  history, unknown versions, append-only activation, and Supabase failures.
- Service tests cover active version A followed by B, new-assessment selection,
  persisted-assessment isolation, missing active configuration, and rejection
  of R snapshot/hash mismatches before session persistence.
- Admin route tests cover read/write authorization, strict request validation,
  duplicate drafts, activation, already-active conflicts, rollback, audit
  subjects, R validation failure, and database failure mappings.
- Adapter tests assert that FastAPI sends configuration in every v2 model
  request and strictly decodes the new R validation operation.
- Extend the opt-in real-R contract test to validate configuration and build
  two models with different supplied snapshots.
- Admin React tests cover initial loading, typed validation, derived-limit
  preview, draft creation, activation confirmation, rollback, loading states,
  and safe errors.
- Add a repository test that calculates the canonical hash of
  `R/config/kst.json` and checks it against the database seed embedded in the
  migration artifact.

After implementation, run:

- the complete R `testthat` suite;
- backend tests from `backend/.venv`;
- `backend/.venv/bin/python -m pyright` with no errors;
- Admin Vitest tests and production build;
- `npm run lint` in `admin` with no Oxlint errors.

## Rollout and acceptance

1. Review and apply the additive Supabase SQL, then record the target
   environment and application date.
2. Run the verification query and confirm the active hash matches
   `R/config/kst.json`.
3. Deploy the backward-compatible R contract and verify health plus the new
   validation operation.
4. Deploy FastAPI configuration persistence and supplied-model flow. Confirm a
   missing active configuration fails safely rather than falling back.
5. Deploy the Admin UI tab.
6. Create assessment A, save and activate changed parameters, then create
   assessment B. Confirm A retains the original hash/derived limits and B uses
   the new ones.
7. Reactivate the seeded version and confirm a newly created assessment uses
   the seeded hash while A and B remain unchanged.

Acceptance requires that UI changes survive container restarts, require no R
restart, create an immutable audit trail, affect only subsequently created
assessments, and do not require regenerating frozen prototype fixtures.

## Assumptions

- Configuration scope is global, not per course or experiment.
- Drafts and activation events are immutable and append-only.
- Database version identity is not added to the R model. The unique canonical
  configuration hash links persisted models to version history without
  coupling R to database identifiers.
- JSONB stores the normalized object, while R's canonical serialization defines
  the hash; PostgreSQL JSONB key ordering is not used for hashing.
- The Admin UI does not rewrite or commit `R/config/kst.json`.
- R remains stateless and has no Supabase credentials.

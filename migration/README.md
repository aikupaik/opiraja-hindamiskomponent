# PostgreSQL schema V1

[`production_schema_v1.sql`](production_schema_v1.sql) is the first executable
version of [`production_schema_v1_draft.md`](production_schema_v1_draft.md).
It installs a **fresh** PostgreSQL 16 schema in `hindamiskomponent` in one
transaction. It deliberately fails on an existing installation. It does not
import data or change the live Supabase pilot.

The restored `review_queries_1.csv` through `review_queries_4.csv` supply the
source definitions. V1 retains all 88 source columns and adds six worker columns;
preserves numeric precision, identity modes/options, source constraint names
and FK update actions; and applies the explicit target changes in the draft.
It adds only the two approved indexes, alongside the existing activation index.
There are no database HTTP calls or Supabase dependencies.

## Installation

The provisioning DBA must already have created the five roles from draft section
6.1, granted owner membership with SET permission to the NOINHERIT migrator,
and made `hindamiskomponent_owner` the database owner. Runtime roles must have no
membership path to any of those other roles and no elevated role attributes.
The DDL checks these prerequisites and creates all application objects as owner.
The owner must be able to manage `public` (the standard PostgreSQL 16
`pg_database_owner` schema ownership supports this). Role credentials, TLS/SCRAM,
`pg_hba.conf`, and security groups remain provisioning concerns.

Configure `shared_preload_libraries` to include `pg_stat_statements`, preserving
other configured libraries, and restart PostgreSQL. Run
[`production_observability.sql`](production_observability.sql) as the provisioning
DBA. Then run the schema as the migrator using your existing TLS connection
settings, for example:

```sh
psql -X -v ON_ERROR_STOP=1 -d hindamiskomponent -U hindamiskomponent_migrator \
  -f migration/production_schema_v1.sql
```

The DDL removes PUBLIC database access, runtime CREATE/TEMP privileges, and
PUBLIC schema CREATE. It removes the owner's global and public-schema blanket
default table/sequence/function grants; future objects get no automatic runtime
access. Table/column/sequence/function privileges are explicit. All ten tables
enable and FORCE RLS and have a role-targeted owner migration/seed policy.

## Transaction context

Choose the database login after FastAPI authorization. In **each explicit
transaction**, initialize `hk.actor`, `hk.operation`, and `hk.test_id` on the
connection executing the SQL, using parameterized `set_config(name, value, true)`.
Initialize `hk.subject` too if used for attribution. Set unused test IDs to an
empty string, reinitialize on retries, and leave pool/session defaults empty.

| Login | Actor | Operations | Test ID |
|---|---|---|---|
| app | `or` | `test_create`, `test_read`, `test_launch` | Generated/authorized selected test |
| app | `player` | `player_start`, `player_answer`, `player_report` | Token-bound selected test |
| admin | `admin` | `test_create`, `test_read`, `player_start`, `player_answer` | Explicit selected simulation test |
| admin | `admin` | `admin_sources`, `admin_rules`, `admin_items`, `admin_configuration` | Empty; shared maintenance resources |
| worker | `worker` | `worker_generate` | Empty; shared queue/resources |

The draft names assessment operations; this implementation names the previously
unnamed maintenance and worker operations above. Admin simulation cannot launch
player tokens or report questions. Maintenance never admits session/answer rows.
Unknown/missing operations, wrong actors, and empty assessment test IDs deny
access. Shared assessment caches/configuration/items also require nonempty test
context, but no preexisting session is needed during creation.

Context predicates live in `hk_private`; all functions are SECURITY INVOKER
with an empty search path. The item update guard is necessary because a role's
column grants combine across operations, whereas RLS predicates constrain rows
([PostgreSQL policy semantics](https://www.postgresql.org/docs/16/sql-createpolicy.html)).
It prevents maintenance-column edits during simulation and separates usage from
inadequate-item reports. Admin-editable item fields follow the current
`encode_editable()` mapping; identity/course/node/cognitive metadata are excluded
from UPDATE. Generated items and admin copies may be inserted without explicit
identity values. Runtime order inserts contain only request fields, start in
`ootel`, and leave result/worker fields at their defaults.

Usage increments require an active selected session, a saved answer, and both
the answer UUID and item ID matching its persisted current question. The
PostgreSQL answer transaction must **insert the answer, increment usage only if
newly inserted, then advance the session**. Replays use SELECT or ON CONFLICT DO
NOTHING and never update the append-only result. Reporting checks the active
session's persisted current item directly. The atomic counter functions retain
their source semantics; direct eligible counter assignments remain permitted
as agreed in the draft.

## Queue and integration limits

The six worker fields and grants support polling, claims, renewal, completion,
retry, failure and reclamation. NULL/due `next_attempt_at` makes an `ootel` job
eligible; expired `locked_until` makes a `tootmises` job eligible. Terminal jobs
are excluded by the worker claim query, not by RLS visibility. The worker must
claim using `FOR UPDATE SKIP LOCKED`, commit before generation, then lock and
verify status/token/unexpired lease before committing generated items and
terminal status together. Validation includes representative SQL for these
steps. RLS intentionally does not enforce claim ownership against arbitrary
SQL from the trusted worker. No automatic worker or retries are implemented by
the schema migration.

The schema stores immutable graph payloads but does not independently recompute
their SHA256 hashes. New graph inserts must follow `backend/app/domain/graphs.py`:
canonical UTF-8 sorting, unique nodes/relations, compact sorted-key JSON and
`kst-graph-v1:sha256:` hashes. Cache conflicts must read/verify the stored payload
and use DO NOTHING, not an UPDATE upsert.

The backend still needs PostgreSQL adapters, context propagation, snapshot-aware
answer writes/feedback, and transaction/worker integration from the draft.
Required snapshots deliberately reject the old snapshot-free answer insert.
Use the persisted question content, including optional explanation absence;
never reconstruct snapshots from a subsequently edited item row. No extra graph
hash, request JSON, or job-state constraints have been added beyond the draft.
Data reconciliation/backfills, identity resets, write freeze and cutover remain
separate work.

## Synthetic validation

With Docker available, run:

```sh
bash migration/validate_schema_v1.sh
```

The runner uses `postgres:16-alpine` (override with `HK_VALIDATION_IMAGE`), a
temporary container with no network or published ports, and no host volumes.
Trust authentication is confined to this disposable test container. It creates
synthetic fixtures, installs through the real migrator login, seeds through the
owner policy, and checks each runtime through its **actual login**. The container
is removed on exit. Validation scripts are for disposable databases only.

Checks cover source column counts, identity options, indexes/FKs, append-only
triggers, JSON NULL/missing-field rejection, required/optional snapshots,
repeat answers, role grants, default privileges, selected-test reads/writes
without WHERE, RETURNING/conflict/replay, wrong/missing context, transaction-local
context cleanup, counter eligibility, maintenance/simulation separation, worker
claim/retry/reclamation and atomic rollback. Worker stale-claim checks validate
the required SQL protocol. Full parallel-worker, external generation/crash
recovery, backend pool/retry isolation and end-to-end flows remain integration
acceptance work.

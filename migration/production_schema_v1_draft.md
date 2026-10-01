# Hindamiskomponent — Production PostgreSQL Schema V1 (Draft)

**Status:** Draft for review; not an executable migration.  
**Target:** PostgreSQL 16, self-hosted database `hindamiskomponent`.  
**Goal:** Reproduce the working pilot's application schema with targeted integrity, durability, and access-control improvements. Defer major redesign until after pilot integration.

## 1. Scope and decisions

- Keep all ten existing application tables and their Estonian identifiers. Retain the current four-choice item-bank structure and existing assessment-method fields.
- Preserve existing primary keys, unique constraints, validation checks, and indexes; add exactly two approved query indexes (section 5).
- Keep `yg_tellimused.test_id` as an informational correlation field **without** a foreign key to `testisessioonid`. 
- Keep repeated answers possible: `vastus_id` remains unique, but `(test_id, yp_id)` must **not** be unique.
- Preserve assessment history: change `tulemustepank.test_id` from `ON DELETE CASCADE` to `ON DELETE RESTRICT`; change `testisessioonid.graaf_hash` from `ON DELETE SET NULL` to `ON DELETE RESTRICT`. Retain `tulemustepank.yp_id ON DELETE RESTRICT`. Consider separate controlled deletion procedures later if required by retention obligations.
- Make `graafid_kst` append-only using a trigger, in addition to protecting it through privileges. Keep existing append-only triggers on KST configuration history and model cache.
- Retain `yg_tellimused` as the durable job record and extend it with six worker fields. Do not recreate the Supabase HTTP webhook. The worker will poll and claim jobs using short transactions.
- Replace `timezone('utc', now())` defaults on `timestamptz` columns with `now()`.
- Use owner/migrator/runtime roles with table-specific grants, rather than broad default runtime DML permissions.
- Defer speculative indexing, item-bank normalization, general-purpose generation-source metadata, and larger schema changes.

## 2. Application tables

The column inventory below is the source of truth for drafting the executable DDL. Preserve all existing columns and types unless an explicit change appears here.

| Table | Primary key | Purpose | V1-specific notes |
|---|---|---|---|
| `graafid_kst` | `graaf_hash text` | Graph structure and knowledge-space matrix | `graafi_struktuur jsonb NOT NULL`, `teadmusruum_maatriks jsonb NOT NULL`, `loodud timestamptz NOT NULL DEFAULT now()`; append-only. |
| `kst_configuration_versions` | `id uuid DEFAULT gen_random_uuid()` | Versioned KST configuration | Preserve `schema_version`, `configuration jsonb`, unique `configuration_hash`, `created_by`, `created_at`, all current CHECKs and append-only trigger. |
| `kst_configuration_activations` | `id bigint GENERATED ... AS IDENTITY` | Configuration activation history | Preserve `configuration_version_id` FK (`ON UPDATE RESTRICT ON DELETE RESTRICT`), `activated_by`, `activated_at`, nonblank check, append-only trigger. Determine exact identity generation mode from source before DDL. |
| `kst_model_cache` | `(graph_hash, configuration_hash, model_schema_version)` | Versioned derived KST models | Preserve both restrictive FKs, JSON payload checks, supported schema-version check, append-only trigger. |
| `repo_materjalid` | `id bigint IDENTITY` | Course source material | Preserve `kursus`, `pealkiri`, `allika_url`, `sisu_tekst`, `lisatud`; timestamp default becomes `now()`. |
| `testisessioonid` | `test_id text` | Session state and metadata | Preserve current fields, status/method checks, JSON defaults. Graph FK becomes `ON DELETE RESTRICT`. |
| `tulemustepank` | `id bigint IDENTITY` | Per-answer records | Keep unique `vastus_id uuid DEFAULT gen_random_uuid()`, snapshots and repeat-answer support. Make `test_id` and `yp_id` NOT NULL; both FKs `ON DELETE RESTRICT`. `vastatud_ajal DEFAULT now()`. |
| `yg_reeglid` | `id bigint IDENTITY` | Course-specific generation rules | Preserve existing fields and constraints. |
| `yg_tellimused` | `id bigint IDENTITY` | Durable generation requests/jobs | Retain existing columns, status/cognitive-level checks, and `test_id` without FK. Add worker fields in section 3. `maht NOT NULL DEFAULT 1 CHECK (maht > 0)`; `loodud DEFAULT now()`. |
| `ylesandepank` | `yp_id bigint IDENTITY` | Four-option item bank | Preserve current columns, checks and psychometric parameters. Set `ebaadekvaatne_arv integer NOT NULL DEFAULT 0 CHECK (ebaadekvaatne_arv >= 0)`. Retain atomic counter functions. |

**Identity caution:** Source metadata reports `is_identity=YES` for six integer IDs but does not show `identity_generation` (`ALWAYS` versus `BY DEFAULT`). Retrieve it before emitting final executable DDL, especially if importing explicit source IDs.

### 2.1 Existing checks and uniqueness to preserve

- `kst_configuration_versions`: unique `configuration_hash`; configuration must be a JSON object; nonblank `created_by`; hash format `^kst-config-v1:sha256:[0-9a-f]{64}$`; schema version `1` both in the column and payload.
- `kst_configuration_activations`: nonblank `activated_by`.
- `kst_model_cache`: payload must be a JSON object containing `schema_version`, `method`, `configuration_hash`, with matching values; `method = 'kst'`; model schema version `2`.
- `testisessioonid.staatus`: `planeerimisel`, `aktiivne`, `lõpetatud`, `katkenud`; `metoodika`: `ct`, `kst`, `irt`, `dina`.
- `yg_tellimused.staatus`: `ootel`, `tootmises`, `tehtud`, `viga`.
- `ylesandepank.staatus`: `kavand`, `kasutatav`, `läbi vaatamisel`, `arhiivis`.
- `yg_tellimused.kognitiivne_tase` and `ylesandepank.kognitiivne_tase`: `mäletab`, `mõistab`, `rakendab`, `analüüsib`, `hindab`, `loob`.
- `tulemustepank.vastus_id`: unique.

### 2.2 Referential integrity

| Child | Parent | Action on parent deletion |
|---|---|---|
| `kst_configuration_activations.configuration_version_id` | `kst_configuration_versions.id` | RESTRICT |
| `kst_model_cache.configuration_hash` | `kst_configuration_versions.configuration_hash` | RESTRICT |
| `kst_model_cache.graph_hash` | `graafid_kst.graaf_hash` | RESTRICT |
| `testisessioonid.graaf_hash` (nullable) | `graafid_kst.graaf_hash` | **RESTRICT** (changed) |
| `tulemustepank.test_id` (NOT NULL) | `testisessioonid.test_id` | **RESTRICT** (changed) |
| `tulemustepank.yp_id` (NOT NULL) | `ylesandepank.yp_id` | RESTRICT |
| `yg_tellimused.test_id` | No enforced parent | No FK by design |

Use `ON UPDATE RESTRICT` for immutable identifiers where appropriate; preserve existing explicit restrictions on KST FKs. Do not silently change other FK update actions without checking application behavior.

## 3. Durable generation worker (`yg_tellimused`)

Retain the existing request/result JSON and status columns. Add:

```sql
attempt_count   integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
next_attempt_at timestamptz,
locked_until    timestamptz,
claim_token     uuid,
last_error      text,
completed_at    timestamptz
```

**Suggested initialization:** existing pending orders with `next_attempt_at IS NULL` are immediately eligible; a newly inserted order may default to `now()` for clarity. Decide the precise eligibility predicate when implementing the worker, and use it consistently.

**Processing contract:**
1. In a short transaction, claim an eligible order with `FOR UPDATE SKIP LOCKED`, increment `attempt_count`, assign a new `claim_token`, set `locked_until`, and change status to `tootmises`.
2. Commit before calling the AI generator. Renew the lease if necessary.
3. On success, in a new transaction verify the claim token and unexpired ownership; persist generated items and mark the order `tehtud` atomically. Set `completed_at`, store `taitmise_tulemus`, and clear lease fields.
4. On recoverable failure, record a sanitized `last_error`, schedule retry with backoff, and return to `ootel`; after retry exhaustion set `viga`.
5. Reclaim expired leases. A stale worker must not commit results after losing its claim.

**Delivery semantics:** At-least-once processing, not exactly-once external AI calls. The item-persistence step must be idempotent for retries. Do not invent a source-order foreign key or uniqueness constraint in V1 without first checking how the current generator inserts items; implement idempotency in the worker/insertion contract before enabling automatic retries.

**Indexes:** No additional queue index in the agreed V1 index set. Revisit only after observing the claim query and queue performance. The current order count is small.

## 4. Functions, triggers and extensions

### 4.1 Retain application functions

- `public.increment_ebaadekvaatne_arv(bigint)` — atomic increment, return affected item ID.
- `public.increment_ylesande_kasutus(bigint, timestamptz)` — atomic usage increment and monotonic latest-use timestamp; reject null timestamp.
- `public.reject_kst_configuration_mutation()` — reject UPDATE and DELETE on configuration versions and activations.
- `public.reject_kst_model_cache_mutation()` — reject UPDATE and DELETE on model cache.
- **New:** `public.reject_graph_mutation()` — reject UPDATE and DELETE on `graafid_kst`.

Use fully qualified table names and controlled function `search_path`. Explicitly revoke public execution and grant only the runtime functions needed by the application. Trigger functions need not be callable by the runtime role directly.

### 4.2 Triggers

Preserve:
- `kst_configuration_activations_append_only`
- `kst_configuration_versions_append_only`
- `kst_model_cache_append_only`

Add:
- `graafid_kst_append_only` (`BEFORE UPDATE OR DELETE`, invoking `reject_graph_mutation`).

**Remove:** `yg_order_webhook`, which calls `supabase_functions.http_request`. No database-side HTTP calls or embedded bearer credentials in production DDL.

### 4.3 Extensions

- Keep built-in `plpgsql`.
- Enable `pg_stat_statements` for observability; configure `shared_preload_libraries` and restart during a planned maintenance window.
- PostgreSQL 16 provides `gen_random_uuid()` without `pgcrypto`; do not install `uuid-ossp`, `pgcrypto`, `pg_net` or `supabase_vault` unless the final dependency audit identifies another requirement.
- Check application SQL, non-public schema dependencies, RLS policies and remaining defaults before declaring the extension inventory complete.

## 5. Indexes

Preserve all existing primary-key/unique indexes by defining the corresponding constraints. Preserve the explicitly defined activation-history index:

```sql
CREATE INDEX kst_configuration_activations_version_history_idx
    ON public.kst_configuration_activations (configuration_version_id, id DESC);
```

Add exactly the two indexes supported by backend query analysis:

```sql
CREATE INDEX ylesandepank_usable_node_order_idx
    ON public.ylesandepank (graafi_objekt, yp_id)
    WHERE staatus = 'kasutatav';

CREATE INDEX tulemustepank_test_id_idx
    ON public.tulemustepank (test_id);
```

No additional speculative indexes in V1. Evaluate worker-claim indexing and other queries after integration and representative query plans.

## 6. Ownership and least-privilege access

Roles already established on the target cluster:

| Role | Intended responsibility |
|---|---|
| `hindamiskomponent_owner` (`NOLOGIN`) | Owns database and application schema objects. |
| `hindamiskomponent_migrator` (`LOGIN NOINHERIT`) | Runs versioned migrations after `SET ROLE hindamiskomponent_owner`. |
| `hindamiskomponent_app` (`LOGIN`) | Application and initial worker runtime; no DDL privileges. |

**Migration execution:** use migrator credentials and `SET ROLE hindamiskomponent_owner` before creating application objects, so ownership and owner-scoped default privileges are consistent. Do not rely on the previously configured blanket default DML grants; replace them with explicit table grants and narrow future defaults. Revoke `CREATE` on the application schema from `PUBLIC` and revoke unnecessary default `EXECUTE` on functions from `PUBLIC`.

**Proposed runtime privileges (confirm against real application SQL before cutover):**

| Objects | Runtime privileges |
|---|---|
| `graafid_kst` | SELECT, INSERT; no UPDATE/DELETE |
| `kst_configuration_versions`, `kst_configuration_activations`, `kst_model_cache` | SELECT, INSERT where application needs it; no UPDATE/DELETE |
| `repo_materjalid` | SELECT, INSERT, UPDATE, DELETE if repository management requires it |
| `testisessioonid` | SELECT, INSERT, UPDATE; no routine DELETE |
| `tulemustepank` | SELECT, INSERT; no routine UPDATE/DELETE unless answer-correction workflow requires it |
| `yg_reeglid` | SELECT; administrative writes through migrator or a separate privileged admin role |
| `yg_tellimused` | SELECT, INSERT, UPDATE for durable worker lifecycle; DELETE restricted |
| `ylesandepank` | SELECT, INSERT, UPDATE for status, counters and item maintenance; DELETE restricted |
| Identity sequences | USAGE (and SELECT only where actually needed) for inserts |
| Counter functions | EXECUTE for `hindamiskomponent_app`; no general PUBLIC execution |

**Operational caveat:** If the generator or repository management currently uses the same app role for DELETE or other writes, reconcile the actual SQL before applying the restrictive grants. A separate worker role can be introduced later if necessary. Superusers and object owners can bypass some trigger/privilege protections; reserve those credentials for migrations and administration.

**Networking:** Continue TLS-only SCRAM authentication from the authorized application VM, CA verification (`sslmode=verify-full`), and OpenStack security-group restrictions already tested.

## 7. Data migration and validation

1. Create and review executable V1 DDL in version control. Apply it to a fresh target database using the migrator/owner role. **Do not modify the live Supabase pilot during the audit.**
2. Rotate the bearer credential exposed in the original Supabase webhook definition if not already done. Never embed replacement secrets in migrations.
3. Export application tables and import in FK dependency order: graphs and KST configurations; KST activations/cache; sessions and item bank; results; other independent tables. Preserve source IDs and reset identity sequences after import.
4. Exclude the eight confirmed obsolete `yg_tellimused` rows. Do not drop repeated answers: the alternate prototype intentionally supports item re-presentation.
5. Verify counts and constraints. Prior audit snapshot: `ylesandepank` 1,054 rows, `yg_tellimused` 72 rows before excluding eight obsolete rows, `tulemustepank` 784 rows. These are **audit-time snapshots**, not final cutover targets; repeat counts after the write freeze.
6. Verify that new graph/configuration/cache mutation attempts are rejected, restrictive foreign keys protect history, both new indexes exist, and runtime permissions allow actual backend operations.
7. Run an end-to-end test of order creation, worker claiming, failure/retry, crash recovery, generated-item persistence, test completion and result retrieval. Confirm TLS and backup/PITR continue to work.
8. For cutover, freeze source writes, perform final delta/full transfer, validate target, switch application connection and worker, and retain Supabase temporarily for rollback. Define rollback behavior before enabling production writes to the target.

## 8. Outstanding checks before executable migration

These are implementation checks, **not reasons to reopen the agreed architecture**:

- Retrieve `information_schema.columns.identity_generation` for the six identity columns and verify their underlying sequence options.
- Confirm the runtime's actual table/function access (including whether the item generator writes `ylesandepank` directly) before finalizing GRANT statements.
- Check whether any application queries depend on Supabase Auth, Storage, Realtime, RLS, non-public functions, or other extension-specific objects; migrate or replace only genuine dependencies.
- Confirm whether source graph rows have ever been mutated in place and whether all imported hashes accurately identify their payloads. The append-only trigger prevents future changes but does not validate the hash algorithm.
- Define worker claim SQL and retry/idempotency behavior before turning on automatic retries. No new queue index is approved yet.
- Establish the final source write-freeze procedure, final counts and sequence reset strategy.

---

**V1 acceptance criterion:** The self-hosted PostgreSQL 16 database supports the existing pilot's reads and writes, preserves historical results and graph/KST integrity, processes generation orders without Supabase database webhooks, and can be deployed reproducibly from version-controlled migrations.

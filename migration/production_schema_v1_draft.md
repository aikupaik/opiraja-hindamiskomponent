# Hindamiskomponent — Production PostgreSQL Schema V1 (Draft)

**Status:** Draft for review; not an executable migration.  
**Target:** PostgreSQL 16, self-hosted database `hindamiskomponent`.  
**Goal:** Reproduce the working pilot's application schema with targeted integrity, durability, and access-control improvements. Defer major redesign until after pilot integration.

**Review update (2026-10-01):** Incorporates the four supplied Supabase schema query exports, all five follow-up results, and the user's decisions to preserve admin rule creation, use the current production backend as the generation contract, and preserve saved answer snapshots across later item edits. This remains an exploratory draft; application changes and executable DDL have not been implemented.

**Current scope:** Schema migration first. The user confirms that existing rows are mostly development test data; detailed import exclusions, historical backfills, write-freeze handling and cutover policy are deferred. Audit exports remain supporting evidence, but development-data treatment is not a gate for this schema discussion. Production RLS is a required target capability; its proposed design is in section 6.1.

## 1. Scope and decisions

- Keep all ten existing application tables and their Estonian identifiers. Retain the current four-choice item-bank structure and existing assessment-method fields.
- Preserve existing primary keys, unique constraints, validation checks, and indexes; add exactly two approved query indexes (section 5).
- Keep `yg_tellimused.test_id` as an informational correlation field **without** a foreign key to `testisessioonid`. 
- Keep repeated answers possible: `vastus_id` remains unique, but `(test_id, yp_id)` must **not** be unique.
- Preserve assessment history: change `tulemustepank.test_id` from `ON DELETE CASCADE` to `ON DELETE RESTRICT`; change `testisessioonid.graaf_hash` from `ON DELETE SET NULL` to `ON DELETE RESTRICT`. Retain `tulemustepank.yp_id ON DELETE RESTRICT`. Consider separate controlled deletion procedures later if required by retention obligations.
- Preserve the six existing answer-snapshot columns. Populate snapshots when saving new answers, retain their saved values on retries, and use them for historical feedback. Later item-bank edits must not rewrite or replace saved snapshots; see section 2.3.
- Make `graafid_kst` append-only using a trigger, in addition to protecting it through privileges. Keep existing append-only triggers on KST configuration history and model cache.
- Retain `yg_tellimused` as the durable job record and extend it with six worker fields. Do not recreate the Supabase HTTP webhook. The worker will poll and claim jobs using short transactions.
- Use the current production backend's per-node generation requests and inventory logic as the worker's behavioral contract. `YG_edge_function_v2.ts` is the confirmed deployed prototype generator, but its behavior is not authoritative for the production pilot.
- Replace `timezone('utc', now())` defaults on `timestamptz` columns with `now()`.
- Use owner/migrator/runtime roles with table-specific grants, rather than broad default runtime DML permissions.
- Enable production row-level security with explicit policies. Runtime database roles must be subject to those policies; database grants and API authorization remain necessary alongside RLS.
- Defer speculative indexing, item-bank normalization, general-purpose generation-source metadata, and larger schema changes.

## 2. Application tables

The table below summarizes the target. The complete source inventory is [review_queries_1.csv](review_queries_1.csv) (88 columns across ten tables); exact source constraints, indexes and trigger metadata are in [review_queries_2.csv](review_queries_2.csv). Use these exports together with the explicit target changes in this draft when writing DDL. Preserve every source column, its full type (including numeric precision/scale), nullability and default unless an explicit change appears here.

| Table | Primary key | Purpose | V1-specific notes |
|---|---|---|---|
| `graafid_kst` | `graaf_hash text` | Graph structure and knowledge-space matrix | `graafi_struktuur jsonb NOT NULL`, `teadmusruum_maatriks jsonb NOT NULL`, `loodud timestamptz NOT NULL DEFAULT now()`; append-only. |
| `kst_configuration_versions` | `id uuid DEFAULT gen_random_uuid()` | Versioned KST configuration | Preserve `schema_version`, `configuration jsonb`, unique `configuration_hash`, `created_by`, `created_at`, all current CHECKs and append-only trigger. |
| `kst_configuration_activations` | `id bigint GENERATED ALWAYS AS IDENTITY` | Configuration activation history | Preserve `configuration_version_id` FK (`ON UPDATE RESTRICT ON DELETE RESTRICT`), `activated_by`, `activated_at`, nonblank check, append-only trigger. |
| `kst_model_cache` | `(graph_hash, configuration_hash, model_schema_version)` | Versioned derived KST models | Preserve both restrictive FKs, JSON payload checks, supported schema-version check, append-only trigger. |
| `repo_materjalid` | `id bigint GENERATED BY DEFAULT AS IDENTITY` | Course source material | Preserve `kursus`, `pealkiri`, `allika_url`, `sisu_tekst`, `lisatud`; timestamp default becomes `now()`. |
| `testisessioonid` | `test_id text` | Session state and metadata | Preserve current fields, including nullable `kursus`, status/method checks, JSON defaults. Graph FK becomes `ON DELETE RESTRICT`; the current backend does not rely on `kursus`. |
| `tulemustepank` | `id bigint GENERATED BY DEFAULT AS IDENTITY` | Per-answer records | Keep unique `vastus_id uuid NOT NULL DEFAULT gen_random_uuid()`, all six snapshot columns and repeat-answer support. Make `test_id` and `yp_id` NOT NULL; both FKs `ON DELETE RESTRICT`. `vastatud_ajal DEFAULT now()`. |
| `yg_reeglid` | `id bigint GENERATED BY DEFAULT AS IDENTITY` | Course-specific generation rules | Preserve existing fields and constraints; runtime SELECT and INSERT retain admin rule creation. |
| `yg_tellimused` | `id bigint GENERATED BY DEFAULT AS IDENTITY` | Durable generation requests/jobs | Retain all existing columns, including nullable `ylesande_taotlused` and `taitmise_tulemus` (both `DEFAULT '[]'::jsonb`), status/cognitive-level checks, and `test_id` without FK. Add worker fields in section 3. `maht NOT NULL DEFAULT 1 CHECK (maht > 0)`; `loodud DEFAULT now()`. |
| `ylesandepank` | `yp_id bigint GENERATED BY DEFAULT AS IDENTITY` | Four-option item bank | Preserve all columns, including nullable `arvutuskaik` and `ebasobiv_signaale integer NOT NULL DEFAULT 0`. Retain `irt_a`/`irt_b numeric(4,2)` and `beeta_error`/`g_guess numeric(3,2)`. Set `ebaadekvaatne_arv integer NOT NULL DEFAULT 0 CHECK (ebaadekvaatne_arv >= 0)`. Retain atomic counter functions. |

**Identity modes confirmed:** Only `kst_configuration_activations.id` uses `ALWAYS`; the other five identity columns use `BY DEFAULT`. All six sequences start at 1, increment by 1, have minimum 1 and maximum 9223372036854775807, use cache 1 and do not cycle. Preserve these options. Import mechanics and sequence resets belong to the later data-migration phase.

### 2.1 Existing checks and uniqueness to preserve

- `kst_configuration_versions`: unique `configuration_hash`; configuration must be a JSON object; nonblank `created_by`; hash format `^kst-config-v1:sha256:[0-9a-f]{64}$`; schema version `1` both in the column and payload.
- `kst_configuration_activations`: nonblank `activated_by`.
- `kst_model_cache`: payload must be a JSON object containing `schema_version`, `method`, `configuration_hash`, with matching values; `method = 'kst'`; model schema version `2`.
- `testisessioonid.staatus`: `planeerimisel`, `aktiivne`, `lõpetatud`, `katkenud`; `metoodika`: `ct`, `kst`, `irt`, `dina`.
- `yg_tellimused.staatus`: `ootel`, `tootmises`, `tehtud`, `viga`.
- `ylesandepank.staatus`: `kavand`, `kasutatav`, `läbi vaatamisel`, `arhiivis`.
- `yg_tellimused.kognitiivne_tase` and `ylesandepank.kognitiivne_tase`: `mäletab`, `mõistab`, `rakendab`, `analüüsib`, `hindab`, `loob`.
- `tulemustepank.vastus_id`: unique.

**JSON CHECK review:** The export confirms a loophole in `kst_configuration_versions_payload_schema_version`: a missing `schema_version` produces SQL NULL and passes the source CHECK. `kst_model_cache_payload_shape` checks key presence, but JSON null values in its required fields can also produce SQL NULL and pass. PostgreSQL accepts CHECK expressions evaluating to NULL ([documentation](https://www.postgresql.org/docs/16/ddl-constraints.html#DDL-CONSTRAINTS-CHECK-CONSTRAINTS)). A proposed targeted correction is to require the existing complete expressions to evaluate `IS TRUE`. [followup_query_2.csv](followup_query_2.csv) reports zero rows failing either proposed expression. The correction remains proposed for executable DDL; verify rejection of missing/JSON-null required fields with synthetic schema fixtures.

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

### 2.3 Saved answer snapshots

The source already contains six nullable text columns on `tulemustepank`:

```text
graafi_objekt_snapshot
juhis_snapshot
tyvi_snapshot
stiimul_snapshot
voti_snapshot
arvutuskaik_snapshot
```

**Confirmed requirement:** Snapshots record the answer's saved question state and retain that state across future item edits. Preserve existing snapshot values exactly during import. Normal runtime access remains SELECT and INSERT only on `tulemustepank`.

**Current implementation gap:** The source has no trigger on `tulemustepank`. The backend's `AnswerRecord`, `encode_answer`, answer SELECT columns and decoder omit all six fields. Completed-test feedback loads prompt, stimulus and answer key from the current `ylesandepank` row. Existing schema columns alone therefore do not satisfy the requirement.

**Development-data evidence:** [followup_query_1.csv](followup_query_1.csv) and [followup_query_4.csv](followup_query_4.csv) show that snapshot columns exist but are incompletely populated, including in v2 sessions. Their import/backfill treatment is deferred. Those development rows do not determine target nullability: decide required production snapshot fields from the new write contract, allowing optional instruction, stimulus and calculation text to be absent where appropriate.

**Required integration behavior:**

- Save the question content used for that submission together with the answer. For the current backend, copy node, instruction, prompt, stimulus and correct-option text from the persisted `tp_seisund.current_question`. Reading the latest item-bank content at answer insertion can capture an edit made after the question was presented and disagree with the backend's scoring state.
- The backend currently does not carry `arvutuskaik` in `AssessmentItem` or `CurrentQuestion`; extend question capture to retain this optional calculation text so `arvutuskaik_snapshot` can preserve its saved state, including legitimate absence. Do not resolve it from the subsequently edited item during result retrieval.
- Replaying the same `vastus_id` must read and reuse the original snapshot; it must not refresh snapshot values from the current item.
- Completed-test results must use saved snapshots and the saved score/correctness, without requiring the current item content or answer key to match.
- Required production snapshots must be enforced by the schema/write contract. Node, prompt and answer key are candidates for NOT NULL constraints; optional instruction, stimulus and calculation text need their legitimate absence represented. Finalize these constraints with the snapshot-aware insertion contract rather than weakening them to accommodate development rows.

**Still to specify for the production schema:** Required snapshot-field constraints; whether full option order/IDs and measurement parameters must also be retained in the answer snapshot; and whether to add an append-only result trigger alongside restrictive runtime grants. This review does not approve additional snapshot columns or a final trigger implementation. Historical development-data handling is deferred.

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

**Production request contract:** Use the current backend (`backend/app/services/assessment.py` and `backend/app/persistence/supabase_mapping.py`) as the source of truth. A nonempty `ylesande_taotlused` array contains unique `node` values and positive `amount` values; generate the amount requested for each node. `graafi_objektid` and `maht` are legacy compatibility fields, with backend `maht` set to the largest requested amount. The backend decoder falls back to those fields for NULL/empty request arrays. Handling existing prototype orders belongs to the later data-migration phase.

The confirmed deployed `YG_edge_function_v2.ts` instead uses `maht` for every node, inserts items one at a time, tests only whether each node has any usable item, and does not write `taitmise_tulemus`. Preserve reusable generation/prompt code only where it fits the production backend contract; do not reproduce prototype-specific behavior as a production requirement.

**Development-data evidence:** The order audit is retained in [followup_query_3.csv](followup_query_3.csv) and [followup_query_5.csv](followup_query_5.csv). The user classified IDs `9`, `11`, `12` as obsolete prototype work. Import exclusions and source-job reconciliation are deferred; they are not schema-design gates.

When writing `taitmise_tulemus`, use the exact per-node fields accepted by the backend decoder: `node`, `requested`, `baseline_usable`, `created`, `usable_after`, `remaining` (nonnegative integer counts). Completion must account for the requested quantities. The backend recomputes actual item inventory and creates a smaller follow-up order after a terminal order if shortages remain; keep a retrying order in `ootel`/`tootmises` so that retries do not also provoke a follow-up for the same in-flight work.

**Suggested initialization:** For new production orders, `next_attempt_at IS NULL` can mean immediately eligible; a newly inserted order may default to `now()` for clarity. Decide the precise eligibility predicate when implementing the worker, and use it consistently.

**Processing contract:**
1. In a short transaction, claim an eligible order with `FOR UPDATE SKIP LOCKED`, increment `attempt_count`, assign a new `claim_token`, set `locked_until`, and change status to `tootmises`.
2. Commit before calling the AI generator. Renew the lease if necessary.
3. On success, in a new transaction lock the order row and verify status, claim token and unexpired ownership; persist generated items and mark the order `tehtud` atomically. Set `completed_at`, store `taitmise_tulemus`, and clear lease fields. An ownership check outside this transaction is insufficient.
4. On recoverable failure, record a sanitized `last_error`, schedule retry with backoff, and return to `ootel`; after retry exhaustion set `viga`.
5. Reclaim expired leases. A stale worker must not commit results after losing its claim.

**Delivery semantics:** At-least-once processing, not exactly-once external AI calls. The source generator's individual inserts have no order-linked persistence key. A proposed production approach is to commit all generated items and terminal order status in the same transaction, guarded by the locked claim: an aborted transaction leaves neither persisted items nor completion, and an already completed order is not reprocessed. This may avoid adding a source-order FK or uniqueness constraint. Decide partial-output handling and verify crash/ambiguous-commit recovery before enabling automatic retries; do not reuse individually committed prototype inserts without a separate idempotency design.

**Indexes:** No additional queue index in the agreed V1 index set. Revisit only after observing the claim query and queue performance. The current order count is small.

## 4. Functions, triggers and extensions

### 4.1 Retain application functions

- `public.increment_ebaadekvaatne_arv(bigint)` — atomic increment, return affected item ID.
- `public.increment_ylesande_kasutus(bigint, timestamptz)` — atomic usage increment and monotonic latest-use timestamp; reject null timestamp.
- `public.reject_kst_configuration_mutation()` — reject UPDATE and DELETE on configuration versions and activations.
- `public.reject_kst_model_cache_mutation()` — reject UPDATE and DELETE on model cache.
- **New:** `public.reject_graph_mutation()` — reject UPDATE and DELETE on `graafid_kst`.

Use fully qualified table names and controlled function `search_path`. Explicitly revoke public execution and grant only the runtime functions needed by the application. Trigger functions need not be callable by the runtime role directly.

**Source function audit:** [review_queries_4.csv](review_queries_4.csv) confirms that all four retained functions are SECURITY INVOKER with an empty `search_path`. Both counters fully qualify `public.ylesandepank`; usage rejects NULL timestamps and maintains monotonic latest use. Source counter execution is limited to `postgres`/`service_role`; replace these source grants with target-role grants. The two rejection trigger functions currently also grant PUBLIC execution; do not carry that broad grant to the target.

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

**Source access audit:** All ten application tables have RLS disabled, RLS forcing disabled and no policies. The only non-public trigger function in their exported trigger inventory is `supabase_functions.http_request`, used by the webhook being removed. The reviewed backend and deployed generator use table access/RPCs; no Supabase Auth, Storage or Realtime API use was found in those code paths. This is not a database-wide dependency audit.

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
| `hindamiskomponent_app` (`LOGIN`) | Existing application login; proposed assessment-runtime role under section 6.1. No DDL privileges. |

**Migration execution:** use migrator credentials and `SET ROLE hindamiskomponent_owner` before creating application objects, so ownership and owner-scoped default privileges are consistent. Do not rely on the previously configured blanket default DML grants; replace them with explicit table grants and narrow future defaults. Revoke `CREATE` on the application schema from `PUBLIC` and revoke unnecessary default `EXECUTE` on functions from `PUBLIC`.

The previous single-role grant matrix is superseded by the proposed role separation below. Keeping admin rule creation is an explicit requirement: the admin runtime connection must retain SELECT and INSERT on `yg_reeglid`. Configuration-version creation/activation also require SELECT and INSERT; cache writes retain insert-if-absent behavior. Grant identity-sequence USAGE only where each role inserts, and EXECUTE only on functions it needs.

### 6.1 Production RLS — proposed design for discussion

**Required target:** Enable RLS on all ten application tables and define explicit role/operation policies before enabling application access. Use `FORCE ROW LEVEL SECURITY` as a proposed additional safeguard. Runtime roles must be NOSUPERUSER and NOBYPASSRLS, own no application objects, and have no path to assume the owner/migrator roles. An enabled table with no applicable policy denies rows by default; superusers and BYPASSRLS roles bypass policies, and owners normally bypass them unless FORCE is set ([PostgreSQL RLS documentation](https://www.postgresql.org/docs/16/ddl-rowsecurity.html)). FORCE does not prevent an owner from changing its table's policies or disabling RLS.

**Existing identity model:** `AuthContext` already distinguishes OR, player and admin profiles. Player JWTs bind access to `authorized_test_id`; `kasutaja_id` is learner metadata supplied in the create request, not the authenticated service subject. The current authorization contract treats OR subjects as trusted services, not ownership tenants. Preserve that model unless organization/OR ownership isolation is explicitly chosen. There is no existing organization or creating-OR ownership column to filter on.

**Proposed database roles:**

- `hindamiskomponent_app`: assessment-service SQL for authorized OR/player requests.
- `hindamiskomponent_admin`: a separate runtime login/pool for authorized admin operations and explicit simulation paths; limited grants and RLS policies, not ownership or BYPASSRLS.
- `hindamiskomponent_worker`: a separate login for job claims and generated-item persistence; limited grants and RLS policies, not ownership or BYPASSRLS.

The last two roles are proposals, not roles confirmed to exist on the target. Do not give the assessment login membership allowing it to assume the admin or worker role. Database role choice must follow validated API authorization, not a client-supplied role setting.

**Proposed table access (S = SELECT, I = INSERT, U = UPDATE):**

| Objects | Assessment runtime | Admin runtime | Worker runtime | RLS boundary |
|---|---|---|---|---|
| `testisessioonid` | S/I/U for permitted operations on the authorized test | S/I/U on the selected test for explicit simulation operations | None | Test-scoped |
| `tulemustepank` | S/I for the authorized test; no U/DELETE | S/I for the selected simulation test; no U/DELETE | None | Test-scoped; immutable saved answers |
| `yg_tellimused` | S/I for the authorized test | S/I for the selected simulation test | S/U for queue processing | Test-scoped submission/read; worker queue policies |
| `ylesandepank` | S for assessment use; U only on counter columns/functions | S/I/U for item maintenance | S/I for generation | Shared item bank; role-specific operations; counter updates limited to items used by the authorized test |
| `graafid_kst`, `kst_model_cache` | S/I for assessment preparation/cache writes | S/I for explicit simulation/cache writes | None | Shared immutable cache, role/operation policies |
| `kst_configuration_versions`, `kst_configuration_activations` | S | S/I for configuration administration | None | Shared configuration; append-only administrative writes |
| `repo_materjalid`, `yg_reeglid` | None | S/I for current admin features | S for generation context | Shared source material/rules; role-specific access |

Shared reference rows may intentionally be visible to an allowed backend role across tests. An explicit role-scoped shared-read policy does not imply public access. Learners never connect to PostgreSQL; the backend still needs answer keys and server-only state for scoring, and API DTOs must continue hiding them. RLS controls rows; it does not replace column grants, snapshot immutability or API response filtering.

**Passing verified context to PostgreSQL:**

1. FastAPI validates the JWT and profile/scope/test binding through the existing authorization boundary.
2. Each short repository transaction sets an authorized test ID and permitted operation using parameterized, transaction-local settings on the same checked-out connection, for example `set_config('hk.test_id', <validated ID>, true)`. For creation, use the backend-generated new test ID; for a player, it must match the validated token's binding. Trusted OR access can select any API-authorized test under the current contract, but each transaction is still scoped to that selected test.
3. Policies use that context for `USING` on existing rows and `WITH CHECK` on inserted/updated rows. Missing/empty context must deny test-scoped access; a target row cannot be moved to another test by UPDATE. Context must be reset/set for every transaction, including retries.
4. Use request-scoped/explicit authorization context, not mutable caller fields on the currently shared repository/service objects. Do not hold a database transaction open while calling R or the AI generator. `SET LOCAL`/`set_config(..., true)` lasts only for the transaction ([PostgreSQL SET documentation](https://www.postgresql.org/docs/16/sql-set.html)).

For illustration, the assessment SELECT policy on session rows can include:

```sql
test_id = NULLIF(current_setting('hk.test_id', true), '')
```

This is only the test-boundary predicate, not complete executable policy DDL. INSERT/UPDATE permissions also need the permitted operation and role checks. Do not add a general unrestricted policy for the assessment role: permissive policies combine with OR and could defeat the test restriction. Worker/admin allowances should target their separate roles ([PostgreSQL CREATE POLICY documentation](https://www.postgresql.org/docs/16/sql-createpolicy.html)).

**Trust boundary:** Plain custom settings are assertions supplied by the trusted backend, not independently verified identities. A database client able to issue arbitrary SQL as the assessment login can change such context. This design protects against accidental cross-test queries but does not independently contain a compromised backend credential or context-changing SQL. If production requires PostgreSQL to reject forged caller context independently of FastAPI, choose a verified-context mechanism (such as database verification of signed claims) before finalizing policies. Do not claim arbitrary `hk.actor = 'admin'` settings provide role separation.

**Integration details to resolve with policy DDL:**

- Check `USING`, `WITH CHECK`, SELECT policies for RETURNING/insert-if-absent, and the worker's SELECT FOR UPDATE SKIP LOCKED claim path.
- Keep counter functions SECURITY INVOKER with role-appropriate column UPDATE grants. Counter-row eligibility must cover current-question reports and usage after a saved answer; assessment callers must not gain item-content UPDATE.
- Specify a controlled schema-seed/migration DML path under FORCE without granting its authority to runtime roles.
- Test under the actual non-owner runtime logins: missing context, access to another test, mismatched answer/order insertion, attempted test-ID reassignment, context reuse after commit/rollback/concurrent requests, admin rule creation, worker claims, and denied runtime DDL/DELETE/TRUNCATE. Tests need fresh synthetic data, not the development import.

**Networking:** Continue TLS-only SCRAM authentication from the authorized application VM, CA verification (`sslmode=verify-full`), and OpenStack security-group restrictions already tested.

## 7. Schema migration and validation

1. Create and review version-controlled executable V1 DDL for a fresh target schema, including ownership, grants, RLS policies, constraints, functions and triggers. **Do not modify the live Supabase pilot during this review.**
2. Validate schema installation and any required configuration seed under the intended migrator/owner path. Verify RLS and grants under actual runtime credentials, rather than relying on successful owner queries.
3. Use synthetic fixtures to verify append-only graph/configuration/cache behavior, restrictive FKs, repeat-answer support, production snapshots, both approved indexes and role-specific operations.
4. Verify the backend PostgreSQL authorization-context contract, cross-test denial, pooling/concurrency isolation, admin features and worker claims. RLS must be active before runtime access is considered ready.
5. Run an integration flow for unequal per-node generation amounts, worker failure/retry and crash recovery, snapshot-preserving answer saving/replay and result retrieval after item edits.

Data import, development-row exclusions, historical backfills, sequence resets after import and cutover procedures will be addressed in the data-migration phase. Existing audit counts are evidence snapshots, not current acceptance targets.

## 8. Outstanding checks before executable migration

These are implementation checks, **not reasons to reopen the agreed architecture**:

- Identity generation modes and sequence options are confirmed; preserve them in target DDL.
- Agree the production RLS access model: preserve current trusted-OR/player/admin authorization, or explicitly introduce organization/OR ownership isolation and the fields it requires.
- Finalize assessment/admin/worker role separation, per-command policies and the trust boundary for request context. Verify target grants against the replacement PostgreSQL repositories/worker; current admin rule INSERT and generator item INSERT must remain supported.
- Check whether any application queries depend on Supabase Auth, Storage, Realtime, RLS, non-public functions, or other extension-specific objects; migrate or replace only genuine dependencies.
- Specify the canonical graph hashing/insertion contract and append-only enforcement. Auditing or correcting existing prototype graph payloads/hashes is deferred to data migration.
- Define worker claim SQL and retry/idempotency behavior before turning on automatic retries. No new queue index is approved yet.
- Agree required production snapshot fields/constraints and the final JSON CHECK correction; development-data handling is deferred.
- Specify snapshot-aware answer saving/reading and verify edit/retry stability with synthetic production-format fixtures.
- Define RLS-aware configuration seeds, health probes, counter calls and worker claims; test using non-owner runtime logins and pooled concurrent requests.

---

**V1 acceptance criterion:** The self-hosted PostgreSQL 16 schema can be installed reproducibly from version-controlled migrations, enforces production RLS and role-specific grants, supports the pilot's authorized reads/writes, preserves newly saved result snapshots and graph/KST integrity, and supports durable generation processing without Supabase database webhooks. Migrating existing development data is a later phase.

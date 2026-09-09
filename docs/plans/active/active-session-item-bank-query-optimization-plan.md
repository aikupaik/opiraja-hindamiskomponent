# Active-Session Item-Bank Query Optimization Plan

## Summary

Reduce the Supabase round-trip amplification in active assessments without
changing the public API, the R contract, the persisted player-state schema, or
the rule that an administratively withdrawn item must not be offered as a
future question.

The captured report
`reports/simulation-report-e1428474-6d6f-4848-8454-ed8714c2cbb2-20260909T154442Z.json`
shows that Supabase accounts for 9,542.070 ms of 10,410.482 ms total API time.
The two largest avoidable item-bank read groups are:

| Operation | Calls | Total | Cause |
| --- | ---: | ---: | --- |
| `ylesandepank.load_pool_item` | 42 | 4,192.714 ms | One sequential query for every remaining pool item, followed by another query for the item selected by R. |
| `ylesandepank.get` | 14 | 1,304.827 ms | Seven usage-telemetry reads and seven single-item loads for the completed-question review. |

The nine-item report is consistent with the code path exactly:

- activation loads the selected first item once;
- seven answer submissions reload candidate sets of 8, 7, 6, 5, 4, 3, and 2
  items, for 35 calls;
- the first six advances reload the item selected by R, for another six calls;
- `1 + 35 + 6 = 42` pool-item calls;
- every accepted answer reads its item once before the optimistic telemetry
  update, for seven `get` calls;
- completion reloads all seven answered items one by one, for the other seven
  `get` calls.

The primary fix is batching and request-local reuse, not a process-local cache.
The session already persists the fixed candidate identities and measurement
metadata. A long-lived memory cache would be duplicated between workers,
would be lost on restart, and could continue serving an item after an
administrator withdrew it. One batched live eligibility read per accepted
answer preserves the existing safety behavior while eliminating the N+1
pattern.

For the report-shaped session, the target operation profile is:

| Operation after change | Target calls | Notes |
| --- | ---: | --- |
| `ylesandepank.load_usable_batch` | 7 | One live batch before each R advance. |
| `ylesandepank.load_review_batch` | 1 | One unfiltered batch for the final review. |
| `ylesandepank.get` | 0 | Removed from the assessment service. |
| `ylesandepank.increment_telemetry` | 7 | One atomic RPC per newly inserted answer. |

Including the existing three creation-time inventory reads, this reduces
item-bank network operations from 66 to 18 for the captured session. It removes
48 Supabase round trips. At the measured per-request latency, that should save
roughly 4-5 seconds across the session, but the post-change report rather than
this estimate is authoritative.

## Goals and non-goals

### Goals

- Make an ordinary active-answer request perform one item-bank eligibility
  read regardless of the number of remaining candidates, up to the configured
  batch size.
- Reuse the item rows from that eligibility read to build the R-selected next
  question.
- Load completed-question review data in one batch rather than one row at a
  time.
- Replace usage telemetry's read/compare/update loop with one concurrency-safe
  database RPC.
- Preserve candidate order, item-specific `beta`/`eta`, retry semantics,
  withdrawal filtering, and current player-visible responses.
- Keep dependency timings visible under distinct batch/RPC operation names so
  a new simulation report proves the reduction.

### Non-goals

- Do not add Redis, Supabase Realtime subscriptions, an in-process TTL cache,
  background workers, or another runtime dependency.
- Do not snapshot every item prompt and answer into `tp_seisund`; rewriting
  the entire content pool on every answer would increase session JSONB payloads
  and would remove the live withdrawal check.
- Do not change how R scores candidates, computes the posterior, or decides to
  stop.
- Do not change the fixed activation pool, allow newly created items into an
  active session, or change the researcher-policy decisions tracked in
  `researcher-assessment-rules-reconciliation-plan.md`.
- Do not make the broader answer-insert, telemetry, and session-CAS sequence a
  single database transaction. That is a separate persistence redesign.
- Do not modify `ATA_kst/` or `TP_kst/`.

## Current execution path

### Candidate refresh before R

`AssessmentService.submit_answer()` calls `_remaining_candidates()`. That
helper removes the current and previously answered IDs from the persisted
`SessionPool`, then calls the repository with all remaining IDs.

The repository interface already accepts a tuple of IDs, but
`SupabaseAssessmentRepository.load_items_by_ids()` loops over that tuple and
awaits one `select` for each ID. The calls are sequential, so a pool of size
`P` makes the answer path grow linearly with `P` in network latency rather than
only in local decoding work.

After R returns a candidate, `_question_for_candidate()` calls the same
repository method again for the selected ID even though that item's full row
was just loaded while constructing the candidate set.

### First question

Both immediate activation and preparation completion already have all usable
`AssessmentItem` values in memory. The service converts them into a
`SessionPool`, asks R to select the first candidate, and then unnecessarily
reloads the selected item from Supabase.

### Completion review

`get_question_results()` loads all answer records in one query but loops over
the answered history and calls `get_item()` once per answer. These reads are
unfiltered by status intentionally: a question that is archived after it was
answered must still appear in the learner's completed review.

### Usage telemetry

For every newly inserted answer, `_increment_item_telemetry()` currently:

1. reads the item and its current `kasutamiste_arv`;
2. conditionally updates the row where the count still equals that value;
3. retries up to eight times under contention.

This prevents a simple lost update, but costs at least two requests per answer
and costs more under same-item contention. PostgreSQL can perform the numeric
increment atomically in a single statement exposed as a restricted RPC.

## Repository and Supabase-query changes

### 1. Split usable-pool and historical-review batch reads

Make the internal `AssessmentRepository` contract explicit:

```python
async def load_usable_items_by_ids(
    self, item_ids: tuple[ItemId, ...]
) -> tuple[AssessmentItem, ...]: ...

async def get_items_by_ids(
    self, item_ids: tuple[ItemId, ...]
) -> tuple[AssessmentItem, ...]: ...
```

- `load_usable_items_by_ids()` is for active selection. It filters
  `staatus = kasutatav` and applies `is_domain_valid_usable_item()`.
- `get_items_by_ids()` is for historical review. It does not filter by status
  and does not require the item to remain currently usable.
- Remove the assessment repository's single-item `get_item()` after all
  service, fake, and test callers use the batch methods. The admin repository
  has a separate `get_item()` contract and is not changed.
- Preserve the current behavior for duplicate input IDs: reject them as a
  `RepositoryDataError` before making a request.
- Return an empty tuple without contacting Supabase when the input is empty.

The concrete Supabase implementation must issue `.in_("yp_id", ids)` queries.
The pinned `supabase==2.31.0`/PostgREST async query builder supports `in_()` and
awaited execution. See the
[supabase-py async filter examples](https://github.com/supabase/supabase-py/blob/main/src/postgrest/tests/_async/test_filter_request_builder_integration.py).

For usable items, each request is equivalent to:

```python
await (
    client.table(ITEM_TABLE)
    .select(ITEM_COLUMNS)
    .in_(ITEM_ID_COLUMN, [int(item_id) for item_id in batch])
    .eq(ITEM_STATUS_COLUMN, USABLE_ITEM_STATUS)
    .execute()
)
```

Use an internal batch size of 100 IDs. This keeps normal pilot pools in one
request, bounds the encoded URL length, and stays well below Supabase's default
1,000-row response cap. Larger pools are split into deterministic consecutive
chunks; all chunks are still validated and combined before the caller proceeds.

Do not depend on response order. For each complete load:

1. decode returned rows;
2. reject any returned `yp_id` not requested in that chunk;
3. reject duplicate returned IDs;
4. for usable-pool reads, omit rows that are no longer usable or are not
   domain-valid;
5. combine chunk results into a mapping by ID;
6. return items in the original caller-provided ID order, omitting requested
   IDs that were absent, withdrawn, or invalid.

Historical-review reads use the same batching and ordering machinery without
the usable-status filter. A malformed returned row remains a persistence error,
matching the current single-item decoder behavior.

Record one diagnostic per executed chunk using:

- `ylesandepank.load_usable_batch` for active eligibility;
- `ylesandepank.load_review_batch` for completed review.

The diagnostic payload's existing `count` field records rows returned by that
chunk. No per-item diagnostic should be emitted.

### 2. Replace telemetry reads with one RPC

Add the database function specified in the Supabase operator section below.
Replace `_increment_item_telemetry()` with one awaited call:

```python
await client.rpc(
    INCREMENT_ITEM_USAGE_FUNCTION,
    {
        "p_yp_id": int(answer.item_id),
        "p_used_at": used_at.isoformat(),
    },
).execute()
```

- Keep the operation name `ylesandepank.increment_telemetry` so before/after
  reports compare the same logical operation.
- Require exactly one returned row and verify that its `yp_id` equals the
  submitted item ID. An empty or mismatched result is a
  `RepositoryDataError`.
- Route PostgREST/HTTP failures through the existing `_execute()` error
  translation and dependency timing.
- Remove `_TELEMETRY_RETRIES`, the preliminary `get_item()`, and the
  conditional item-table update.
- Invoke the RPC only when `tulemustepank.insert` inserted a new answer. Do not
  call it for recovered, replayed, stale, or payload-conflicting submissions.
- Preserve the current non-transactional limitation: if the answer insert
  succeeds but a later dependency call fails, retry recovery does not
  reconstruct missing telemetry. `kasutamiste_arv` remains pilot telemetry,
  not correctness-bearing assessment state.

The RPC makes concurrent increments atomic and changes the normal accepted
answer path from one item read plus one item update to one database call.

## Assessment-service changes

### 1. Reuse activation inventory for the first question

Change `_first_question()` to receive the usable `AssessmentItem` values that
were used to create the `SessionPool`.

- Ask R to select from the ordered pool exactly as today.
- Verify the selected candidate against the supplied pool.
- Resolve the matching item from the already-loaded activation inventory.
- Validate item ID, node, `beta`, and `eta` against the candidate.
- Build and persist the first question without another repository read.

Use the same path for immediate activation in `create_assessment()` and delayed
activation in `start_assessment()`.

### 2. Carry loaded items through answer selection

Replace `_remaining_candidates()` with a private helper that returns ordered
candidate/item pairs, or an equivalent private value containing both:

1. calculate the ordered eligible IDs from the persisted pool after excluding
   the current and answered items;
2. call `load_usable_items_by_ids()` once for those IDs;
3. map the returned items back to their candidates;
4. validate each item's snapshotted candidate metadata;
5. return only still-usable validated pairs.

Pass only the ordered candidate portion to R. If R returns
`AdvanceInProgress`, resolve the selected pair and call a synchronous
`_question_for_candidate(candidate, item)` helper. That helper validates and
builds the question but performs no repository work.

This keeps the race and failure semantics equivalent to the current code: an
item withdrawn before the batch query is excluded; unexpected item metadata
changes are rejected; later-created items cannot enter the fixed pool. As
today, a status change after the read but before session commit is an
unavoidable narrow race and is not expanded by the batching change.

### 3. Batch completed-question review

In `get_question_results()`:

- keep the single `list_answers_for_test()` call and all existing history,
  score, and submission-ID validation;
- collect answered item IDs in history order;
- call `get_items_by_ids()` once;
- build an ID mapping, require every history item to exist, and produce results
  in persisted answer order;
- retain the existing check that stored correctness agrees with the current
  answer key.

This preserves the public `question_results` shape and the ability to review a
question whose status changed after administration.

## Supabase operator action required

The batched `.in_()` reads require no schema or Supabase configuration change.
The telemetry optimization requires one additive PostgreSQL function. The
repository currently has no committed Supabase migration workflow and the
`supabase/` directory is ignored, so this remains an explicit manual database
operation unless a migration system is introduced separately.

### 1. Apply the function before deploying the backend

In the Supabase Dashboard for the pilot project:

1. Open **SQL Editor** and create a new query.
2. Confirm that the selected project is the intended pilot project.
3. Run the following reviewed SQL:

```sql
create or replace function public.increment_ylesande_kasutus(
  p_yp_id bigint,
  p_used_at timestamp with time zone
)
returns table (yp_id bigint)
language plpgsql
security invoker
set search_path = ''
as $function$
begin
  if p_used_at is null then
    raise exception 'p_used_at must not be null' using errcode = '22004';
  end if;

  return query
  update public.ylesandepank as item
  set
    kasutamiste_arv = item.kasutamiste_arv + 1,
    viimane_kasutus = case
      when item.viimane_kasutus is null
        or item.viimane_kasutus < p_used_at
      then p_used_at
      else item.viimane_kasutus
    end
  where item.yp_id = p_yp_id
  returning item.yp_id;
end;
$function$;

revoke execute on function public.increment_ylesande_kasutus(
  bigint,
  timestamp with time zone
) from public;

revoke execute on function public.increment_ylesande_kasutus(
  bigint,
  timestamp with time zone
) from anon, authenticated;

grant execute on function public.increment_ylesande_kasutus(
  bigint,
  timestamp with time zone
) to service_role;

notify pgrst, 'reload schema';
```

`SECURITY INVOKER` is sufficient because the backend already uses the service
role, which can update `ylesandepank`. The empty `search_path` and fully
qualified table reference follow Supabase's current
[database-function security guidance](https://supabase.com/docs/guides/database/functions).
Do not change the function to `SECURITY DEFINER`; elevated execution is not
needed.

### 2. Verify the function and privileges

Run these read-only checks in SQL Editor:

```sql
select
  has_function_privilege(
    'service_role',
    'public.increment_ylesande_kasutus(bigint,timestamp with time zone)',
    'execute'
  ) as service_role_can_execute,
  has_function_privilege(
    'anon',
    'public.increment_ylesande_kasutus(bigint,timestamp with time zone)',
    'execute'
  ) as anon_can_execute,
  has_function_privilege(
    'authenticated',
    'public.increment_ylesande_kasutus(bigint,timestamp with time zone)',
    'execute'
  ) as authenticated_can_execute;
```

The required result is `true, false, false`.

Verify behavior against a deliberately selected non-production/test item and
roll the test back:

```sql
begin;

select kasutamiste_arv, viimane_kasutus
from public.ylesandepank
where yp_id = <test_yp_id>;

select *
from public.increment_ylesande_kasutus(<test_yp_id>, now());

select kasutamiste_arv, viimane_kasutus
from public.ylesandepank
where yp_id = <test_yp_id>;

rollback;
```

Replace `<test_yp_id>` with an explicitly reviewed test item ID. Confirm that
the function returns that ID, the count rises by one inside the transaction,
the timestamp does not move backwards, and the rollback restores the row.
Do not paste service keys or bearer tokens into SQL Editor or documentation.

### 3. Deployment and rollback order

1. Apply and verify the additive function and grants.
2. Deploy the backend that calls the RPC and uses the batch reads.
3. Run one run-owned assessment and inspect its result count, session state,
   item telemetry, and dependency-operation logs.
4. Rerun the captured simulation shape and compare operation counts and
   cumulative latency.

The database-first order is backward-compatible because the current backend
does not call the new function. If the new backend must be rolled back,
redeploy the previous backend and leave the function in place temporarily; it
is inert and avoids making rollback depend on another database change. Drop
the function only in a later maintenance step after confirming no deployed
backend calls it:

```sql
drop function public.increment_ylesande_kasutus(
  bigint,
  timestamp with time zone
);
```

After successful rollout, document the deployed function in
`docs/supabase_andmemudel.md` and refresh the tracked schema snapshot through
the project's normal database-export procedure rather than manually editing a
generated dump.

## Interfaces and compatibility

### Public interfaces

- No route, request DTO, response DTO, status code, player token, or OpenAPI
  change.
- No R request/response or KST behavior change.
- No `tp_seisund`, `testi_loogika`, `tulemustepank`, or `ylesandepank` column
  change.
- No migration or conversion of existing sessions.

### Internal interfaces

- Replace assessment-repository single-item access with the two ordered batch
  operations described above.
- Update the in-memory repository fake to implement the same filtering and
  caller-order contract.
- Add `INCREMENT_ITEM_USAGE_FUNCTION = "increment_ylesande_kasutus"` to the
  Supabase vocabulary mapping.
- Change the internal question builder call path to receive an already-loaded
  `AssessmentItem`.

### Compatibility guarantees

- Completed and active player-state schema version 2 rows remain readable.
- Active sessions keep their existing fixed candidate pools.
- A candidate archived before the answer-time batch is excluded from R.
- Completed review can still show items archived after they were answered.
- R receives the same ordered candidate descriptors it would receive after the
  current per-ID loads.
- Duplicate submissions retain the current replay and conflict behavior.

## Test plan

### Repository unit tests

Extend `backend/tests/test_supabase_repository.py` to cover:

- multiple usable IDs generate one GET with `yp_id=in.(...)` and
  `staatus=eq.kasutatav`;
- 101 IDs generate exactly two deterministic chunks;
- empty input generates no HTTP request;
- reversed Supabase response order is restored to caller order;
- absent, archived, and domain-invalid usable items are omitted;
- duplicate input IDs, duplicate response IDs, and unexpected response IDs are
  rejected;
- historical batch loading omits the status filter and returns archived items;
- the telemetry path calls the RPC once with the item ID and timestamp;
- empty or mismatched RPC output is rejected;
- a newly inserted answer calls `tulemustepank.insert`, telemetry RPC, then the
  session CAS in that order;
- recovered/replayed answers do not call telemetry again;
- RPC HTTP/PostgREST failures remain `RepositoryUnavailable` and are recorded
  in dependency timing.

### Service tests

Extend `backend/tests/test_assessment_service.py` to verify:

- immediate and delayed activation build the first question from the inventory
  already loaded for pool creation;
- one answer-time repository batch produces both the candidates sent to R and
  the next question selected by R;
- the selected item is not fetched a second time;
- candidate order is unchanged after Supabase response reordering;
- a withdrawn pool item is not supplied to R;
- an item whose ID/node/`beta`/`eta` no longer matches its snapshot produces a
  persistence error;
- natural, safety-cap, and inventory-exhaustion completion remain unchanged;
- completed review uses one historical batch and retains answered-history
  order;
- completed review succeeds when an answered item is now archived and fails
  when an answered item is missing.

Update the in-memory repository tests and API tests for the revised internal
method names. Public response assertions must remain byte-for-byte equivalent
apart from deliberately non-deterministic IDs already normalized by tests.

### Database and concurrency verification

Against a local/test Supabase project or an explicitly approved run-owned
pilot item:

- run concurrent RPC calls for one `yp_id` and confirm the final
  `kasutamiste_arv` increases by the number of successful calls;
- submit the same `submission_id` twice and confirm only the first accepted
  insert invokes telemetry;
- archive one remaining pool item before an answer and confirm it is absent
  from the corresponding R request;
- verify `anon` and `authenticated` cannot invoke the RPC while the backend
  service role can.

### Performance regression

Add a deterministic nine-item/seven-answer test around the repository/service
fake or diagnostic collector. Require:

- seven `load_usable_batch` executions for the seven accepted answers;
- one `load_review_batch` execution at completion;
- zero assessment-side `ylesandepank.get` executions;
- seven `increment_telemetry` executions;
- unchanged R candidate sequences of 9 for initial selection followed by
  8, 7, 6, 5, 4, 3, and 2 for advances;
- unchanged final posterior, stopping reason, feedback, answer count, and
  submission uniqueness.

Do not assert wall-clock latency in unit tests. After deployment, rerun the
same simulation shape and require the operation-count targets above. Treat a
materially smaller latency improvement as a reason to profile the remaining
session, answer-insert, and session-CAS calls, not as a reason to reintroduce
unsafe caching.

### Required checks

From `backend/` using the project's virtual environment:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pyright
```

Pyright must report zero errors. No TypeScript or R source is changed, so
frontend lint and R tests are not required for this implementation; run them
only if the implementation expands beyond this plan.

## Documentation updates

- Update `backend/README.md` to describe one batched live eligibility refresh
  per answer and the atomic telemetry RPC.
- Update `docs/supabase_andmemudel.md` with the RPC signature, security model,
  mutation semantics, and deployment status.
- Update the Supabase-only and API-to-Supabase stages in
  `pilot-capacity-and-stress-testing-plan.md` so the new expected baseline is
  batched pool loads and batched completion review rather than known N+1
  behavior.
- Retain the original simulation report as baseline evidence; generated future
  reports remain untracked according to the repository's ignore rules.

## Acceptance criteria

The work is complete when all of the following are true:

- An answer with up to 100 remaining candidates performs one usable-item
  Supabase read before R, not one read per candidate.
- The next question is built from that same batch without a selected-item
  reload.
- First-question creation adds no item-bank read after inventory loading.
- Completed review performs one historical item batch for the report-shaped
  session.
- Normal telemetry uses one atomic RPC and no preliminary item read.
- Withdrawn candidates remain excluded, archived historical questions remain
  reviewable, and candidate ordering is unchanged.
- The public API and R contract tests remain unchanged and passing.
- The complete backend tests pass and Pyright reports zero errors.
- The Supabase function is deployed with `service_role=true`, `anon=false`,
  and `authenticated=false` execute privileges.
- A post-deployment simulation shows 7 usable-pool batches, 1 review batch,
  0 assessment-side `ylesandepank.get` calls, and no assessment-integrity
  errors for the same nine-item/seven-answer shape.

## Assumptions

- Administrative withdrawal must take effect for future selection during an
  active session; this is why one live batch remains before R.
- `yp_id` remains the immutable identity for content and measurement metadata;
  in-place changes to node/`beta`/`eta` during an active session remain an
  error.
- `kasutamiste_arv` remains non-correctness-bearing telemetry and does not
  influence candidate selection under the currently implemented policy.
- The backend continues to use Supabase's service-role credential and the
  shared lifespan-managed async client.
- The SQL function is deployed manually before the backend because no tracked
  migration mechanism currently exists in this repository.

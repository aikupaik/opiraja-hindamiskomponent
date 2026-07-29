# Candidate-aware adaptive item inventory implementation

## Summary

Replace node-only selection with a versioned, candidate-aware flow:

1. R builds the KST model and exposes its derived reliability floor and safety cap.
2. Python calculates the required per-node inventory, requests exact deficits from YG, and activates only when all targets are met.
3. Python persists a session-local item pool and supplies only unused, still-eligible candidates to R.
4. R selects within that candidate set and updates the posterior using the administered item's concrete `beta` and `eta`.
5. Inventory exhaustion completes explicitly without repeating an item.

Keep the internal v1 R contract frozen. New sessions use v2; nonterminal v1 sessions are not migrated or resumed.

## Implementation tasks

### 1. Introduce the internal R v2 contract

- Retain `R/contracts/internal-kst-v1.openapi.json` and existing v1 routes unchanged.
- Add `internal-kst-v2.openapi.json` with three operations:
  - `POST /internal/v2/kst/model`
    - Input: graph, configuration, optional cached knowledge states.
    - Output: v2 model, initial posterior, derived `reliability_floor` and `safety_cap`.
    - Remove representative node-level `beta`/`eta` vectors and initial node selection.
  - `POST /internal/v2/kst/select`
    - Input: model, posterior, ordered candidate descriptors.
    - Output: selected `candidate_id` and `node`.
  - `POST /internal/v2/kst/advance`
    - Input: model, posterior, administered `{candidate_id,node,beta,eta}`, correctness, response count, and ordered remaining candidates.
    - Output: updated posterior plus either a selected next candidate or a completed profile.
- Define candidates as:

  ```json
  {"candidate_id":"yp:101","node":"B","beta":0.05,"eta":0.25}
  ```

- Validate unique candidate IDs, valid model nodes, finite probability parameters, and nonblank IDs. Reject candidates outside the model.
- Change half-split selection to score only nodes represented by supplied candidates. Resolve ties by original candidate order.
- Change the Bayesian update function to accept scalar `beta` and `eta` from the administered candidate and apply them to that node's matrix column.
- Evaluate natural and safety-cap stopping immediately after the update. If neither applies and no candidate remains, return:
  - `stop_reason = "item_inventory_exhausted"`
  - `confidence_limited = true`
- Expose both v1 and v2 routes through `R/plumber.R`; update serialization, validation, profiles, README, and manual examples.

### 2. Version the Python domain and persisted JSON documents

- Add candidate, derived-limit, inventory-request/result, inventory-plan, and session-pool domain values.
- Change `KstModel` v2 to contain derived limits but no representative-item parameter vectors.
- Bump `KST_MODEL_SCHEMA_VERSION` and `PLAYER_STATE_SCHEMA_VERSION` to 2.
- Make player state v2 persist:
  - the complete activation-time candidate pool;
  - the current candidate/question;
  - answered item history;
  - posterior;
  - preparation inventory plan where applicable.
- Persist `candidate_id`, `item_id`, `node`, `beta`, and `eta` in the pool and current question.
- Persist the correct option identity with the current question so scoring and retries do not depend on mutable item-bank content.
- Add `ITEM_INVENTORY_EXHAUSTED` to `StopReason`; map both safety-cap and exhaustion completion to public `confidence_limited=true`.
- Keep explicit decoders for v1 player/model documents so completed historical sessions remain readable. Reject start/answer operations for nonterminal v1 sessions.

### 3. Replace coverage checks with inventory planning

- Build or load the graph model before checking inventory, because R's returned safety cap is the source of truth.
- Calculate:

  ```text
  required_per_node = ceiling(model.safety_cap / graph_node_count)
  deficit[node] = max(0, required_per_node - usable_distinct_count[node])
  ```

- Replace `resolve_usable_coverage()` and fallback-ordered item access with repository operations that:
  - count/load every usable item for the graph nodes;
  - return stable ordering by graph-node order and `yp_id`;
  - load exact usable items by pool ID;
  - never return a used item as a fallback.
- Count only distinct, domain-valid, `kasutatav` items with valid measurement parameters and question content.
- If any deficit exists:
  - persist a preparing session containing its model and inventory plan;
  - create one YG order with exact per-node deficits;
  - return the existing preparing response and missing-node list.
- On every preparation poll:
  - recount the actual item bank;
  - recalculate deficits instead of trusting YG's status alone;
  - activate only when every deficit is zero;
  - after a partial/failed order, remain preparing and create at most one replacement order for the newly calculated remaining deficits when no order is in flight.

### 4. Activate and advance using a fixed session pool

- Once inventory is sufficient, snapshot all currently eligible items into the session pool. Do not add items generated later.
- Validate before activation:
  - candidate and item IDs are unique;
  - each candidate node belongs to the model;
  - every node meets the calculated target;
  - the total pool contains at least the safety cap;
  - pool metadata matches the item loaded at activation.
- Call R v2 selection with the ordered, unused candidate descriptors.
- Verify R's returned candidate ID and node exactly match one supplied descriptor, load that exact item, build the question, and persist activation atomically.
- On answer submission:
  - verify the current item is not already in answered history;
  - score using the persisted correct option;
  - remove the current item and all answered items from the candidate set;
  - filter administratively withdrawn items from the remaining pool;
  - call R advancement using the current question's snapshotted node, `beta`, and `eta`;
  - verify and persist the exact returned next candidate.
- Strengthen transition validation so duplicate answered item IDs, a current item already in history, or an R candidate outside the supplied set are persistence errors.
- Preserve existing submission-ID/CAS idempotency and usage-count telemetry. Usage count must never influence session eligibility.
- Add structured inventory-exhaustion telemetry including test ID, safety cap, response count, original pool size, and remaining usable count.

## Manual database action — required outside the codebase

Apply an additive migration to `yg_tellimused` before deploying the new backend:

- Add `ylesande_taotlused jsonb`, containing:

  ```json
  [
    {"node":"A","amount":1},
    {"node":"B","amount":3}
  ]
  ```

- Add `taitmise_tulemus jsonb`, containing per-node completion details:

  ```json
  [
    {
      "node":"A",
      "requested":1,
      "baseline_usable":2,
      "created":1,
      "usable_after":3,
      "remaining":0
    }
  ]
  ```

- Backfill `ylesande_taotlused` for historical rows from `graafi_objektid` and `maht`.
- Add defaults of `[]`, `NOT NULL`, and array-type JSON checks after backfill. Validate individual object fields in Python and the Edge Function.
- Retain `graafi_objektid` and `maht` during the compatibility period, but make `ylesande_taotlused` authoritative for new orders. Remove legacy columns only in a later, separately approved migration.

No new columns are required in `testisessioonid`, `ylesandepank`, or `tulemustepank`: the model and pool fit in the existing JSONB columns. Their internal JSON schemas do change to v2.

Treat an existing `yp_id` as immutable item-version identity: content or measurement changes must create a new item row and archive the old row. If in-place item edits must remain supported, add explicit item-version storage before implementing pool snapshots.

## Manual YG Edge Function action — required outside the codebase

Update and deploy the actual Supabase YG Edge Function; changing the repository's `YG_edge_function.ts` reference alone is insufficient.

- Parse and validate `ylesande_taotlused`; temporarily support legacy `graafi_objektid` plus `maht` for old orders.
- Claim only an `ootel` order using a conditional status update, so duplicate webhook deliveries cannot generate items twice.
- For each node:
  - record its usable baseline count;
  - request exactly that node's `amount`;
  - require Gemini to return exactly that many structurally valid items;
  - insert each valid item and count successful inserts.
- Recount actual `kasutatav` items after generation.
- Populate `taitmise_tulemus` with requested, created, usable-after, and remaining values.
- Set `staatus="tehtud"` only when every node reaches `baseline_usable + requested`; otherwise set `staatus="viga"` and retain the partial results for Python to calculate a smaller retry.
- Do not create retry orders in YG; Python remains responsible for recalculating deficits and ordering the remainder.
- Keep the existing `yg_tellimused` INSERT database webhook. Its `record.id` payload and function secrets remain compatible.
- Deploy the function after the database migration and before enabling backend writes of the new order format.

## Tests and acceptance

- R tests:
  - v1 contract remains byte-for-byte behaviorally frozen;
  - v2 limits match configured formulas;
  - depleted nodes are excluded;
  - candidate-order ties are deterministic;
  - concrete item parameters change the posterior as expected;
  - foreign/duplicate candidates fail validation;
  - empty remaining inventory produces the exhaustion profile.
- Python tests:
  - exact per-node deficits, including partially stocked nodes;
  - partial YG results remain preparing and retry only remaining deficits;
  - activation requires the full target and persists a stable pool;
  - no used item is ever supplied to or accepted from R;
  - withdrawals are excluded;
  - current/answered item uniqueness is enforced;
  - item-specific parameters reach R;
  - concurrent and interrupted retries return the same persisted question;
  - internal pool, node, parameters, correct option, and answer key never enter player APIs.
- Integration scenario:
  - run the demonstrated three-node assessment with three usable items per node through the eight-response cap and assert all administered item IDs are distinct.
- Required verification:
  - run all R `testthat` and OpenAPI contract tests;
  - run backend pytest;
  - run `backend/.venv/bin/python -m pyright` with zero errors;
  - type-check the Edge Function and perform a live opt-in Supabase/YG smoke test with different amounts for two nodes.

## Rollout order and assumptions

1. Complete and test R v2 and Python changes locally.
2. Manually apply the additive Supabase migration.
3. Manually deploy the dual-format YG Edge Function and test one order.
4. Deploy R with v1 and v2 routes available.
5. Confirm or drain all active/preparing v1 sessions.
6. Deploy the backend that writes v2 state and per-node YG requests.
7. Run the three-node and partial-generation smoke tests and monitor exhaustion/deficit logs.

Assume no automatic migration for nonterminal v1 sessions, no live generation after activation, stable candidate order by graph-node order then `yp_id`, and immutable usable item rows.

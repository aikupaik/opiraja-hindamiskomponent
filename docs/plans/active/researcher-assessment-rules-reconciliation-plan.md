# Researcher assessment rules reconciliation and refactor plan

## Status

Discussion draft. Do not implement the assessment-logic changes in this plan
until the decisions in **Questions for the researcher** have been resolved.

The purpose of this document is to reconcile three sources that currently do
not describe the same assessment:

1. the earlier candidate-aware, no-repeat design in
   `docs/adaptive_item_inventory.md`;
2. the current production implementation in `R/` and `backend/`;
3. the researcher's updated rules and prototype in
   `R/assessment_rules.md`, `TP_kst/`, and `ATA_kst/`.

Code structure is deliberately secondary here. The comparison concerns which
node and item are administered, how evidence updates the posterior, and when
the assessment stops.

## Executive summary

The largest conflict is a genuine policy reversal, not a small implementation
difference:

- The previous agreement prohibits administering the same concrete item twice
  in one assessment and constrains R to the unused candidates supplied by
  Python.
- The updated researcher rules explicitly permit concrete-item repetition
  after every usable item for the selected node has been used. Half-split may
  keep selecting that node, and the least-repeated item is then administered
  again.

Adopting the updated rule would invalidate the core assumptions behind the
fixed session pool, unused-candidate selection, inventory-exhaustion stop, and
duplicate-item persistence checks. It should therefore be confirmed with the
researcher before refactoring.

Other clear differences are the natural-stop threshold (`0.8` versus `0.9`),
inventory preparation (top-up versus only generating for empty nodes), and
item choice (stable item order versus global/session usage balancing).

There are also two apparent inconsistencies in the researcher prototype:

1. it selects and returns the concrete item's `beta`/`eta`, but updates the
   posterior using a representative node-level pair instead;
2. it requests five generated items for an empty node, but can declare the
   node covered as soon as one usable item is visible.

These look more like implementation gaps than intentional assessment rules,
but that must be confirmed.

## Logic differences

### 1. What half-split is allowed to select

**Previous agreement and current implementation**

- R receives only unused, currently eligible candidates.
- Nodes without a remaining unused candidate are excluded from half-split
  selection.
- This intentionally trades unconstrained half-split optimality for the
  no-repeat invariant.

References:

- `docs/adaptive_item_inventory.md:5-17` — candidate-aware decision and
  no-repeat rule.
- `docs/adaptive_item_inventory.md:185-203` — depleted nodes are ignored.
- `R/src/assessment.R:41-53` — half-split scores only the supplied candidate
  nodes.
- `backend/app/services/assessment.py:508-533` — current and answered items are
  excluded from the next candidate set.

**Updated researcher rules and prototype**

- Half-split selects a node from the full KST matrix before a concrete item is
  considered.
- The selected node is not removed merely because all of its items have been
  used in the session.

References:

- `R/assessment_rules.md:5-15` — node-first half-split rule.
- `TP_kst/TP_loogika.R:130-139` — `vali_jargmine_solm()` calls
  `kmassesshalfsplit(posterior, K)` without an inventory restriction.
- `TP_kst/app.R:116-131` — the node is selected before
  `vali_ylesanne_solmele()` is called.

**Consequence**

The two implementations can ask different nodes from the same posterior as
soon as the statistically best node has no unused item left.

### 2. Whether a concrete item may repeat

**Previous agreement and current implementation**

- A concrete item may appear at most once in an assessment.
- Repetition is treated as non-independent evidence that could make the
  posterior overconfident through memory of the earlier prompt.
- Persisted-state and transition validation reject duplicate answered item IDs.

References:

- `docs/adaptive_item_inventory.md:34-45` — reason repeated prompts were judged
  invalid.
- `docs/adaptive_item_inventory.md:53-71` — explicit no-repeat invariants.
- `backend/app/services/assessment.py:390-408` — rejects an already answered
  current item and supplies only remaining candidates.
- `backend/app/persistence/supabase_repository.py:486-516` and
  `backend/app/persistence/supabase_mapping.py:865-873` — persistence rejects
  duplicate item IDs.

**Updated researcher rules and prototype**

- Unused items are preferred, but repetition is explicitly allowed after the
  selected node's pool has been exhausted.
- The item used the fewest times in the current assessment is repeated.

References:

- `R/assessment_rules.md:28-36` — two-stage selection, including least-repeated
  fallback.
- `TP_kst/TP_loogika.R:141-171` — `vali_ylesanne_solmele()` implements that
  fallback using per-session counts.

**Consequence**

This is the central research decision. If repetition is allowed, the current
fixed unused-candidate flow and duplicate-ID invariants must be removed or
versioned. If repetition remains forbidden, the updated researcher item
fallback must not be copied.

### 3. Fixed activation pool versus live item-bank selection

**Previous agreement and current implementation**

- All eligible items are snapshotted into a session-local pool at activation.
- The pool fixes item identities and measurement metadata for reproducibility.
- Later-created items are not added to an active assessment; withdrawn items
  can only reduce the remaining pool.

References:

- `docs/adaptive_item_inventory.md:165-183` — fixed session-pool decision.
- `backend/app/services/assessment.py:220-239` and `557-596` — activation
  snapshots the pool.
- `backend/app/services/assessment.py:508-533` — later selection is restricted
  to that pool.

**Updated researcher rules and prototype**

- Every question selection queries `ylesandepank` live for all usable items of
  the selected node.
- Newly usable items can therefore enter an active assessment, and current
  global usage counts affect selection.

References:

- `R/assessment_rules.md:17-36` — concrete item is selected from
  `ylesandepank` after node selection.
- `TP_kst/TP_loogika.R:151-171` — live node/status query and item selection.

**Consequence**

The researcher flow improves live global balancing but gives up the previous
agreement's fixed-pool reproducibility. A hybrid is possible—snapshot item
identity but refresh telemetry—but it would be a new rule not expressed by
either source.

### 4. How a concrete item is chosen within a node

**Previous agreement and current implementation**

- Same-node items have equal half-split score.
- Stable candidate order resolves the tie; the repository currently orders by
  graph-node order and item ID.
- `usage_count` is telemetry and does not affect the chosen item.

References:

- `docs/adaptive_item_inventory.md:197-208` — stable candidate-order tie rule.
- `R/src/assessment.R:41-53` — first candidate at the best distance wins.
- `backend/app/persistence/supabase_repository.py:156-184` — usable items are
  loaded in item-ID order for each node.

**Updated researcher rules and prototype**

- Among items unused in the session, the smallest global
  `kasutamiste_arv` wins.
- After all items have been used, the smallest per-session repetition count
  wins.

References:

- `R/assessment_rules.md:28-36` — global balancing followed by session-local
  repeat balancing.
- `TP_kst/TP_loogika.R:159-168` — implementation of both orderings.

**Consequence**

The updated rule deliberately avoids repeatedly favoring the lowest item ID.
It also requires a deterministic secondary tie rule and safe concurrent usage
counter updates, neither of which the researcher rule currently specifies.

### 5. Inventory preparation and generator volume

**Previous agreement**

- Provision enough distinct items to reach the safety cap without repetition.
- The agreed target is `ceil(safety_cap / node_count)` usable items per node,
  with existing stock topped up by its exact deficit.

References:

- `docs/adaptive_item_inventory.md:73-125` — derived inventory formula and
  rationale.
- `docs/adaptive_item_inventory.md:129-160` — top-up and exact per-node request
  behavior.

**Current implementation**

- Uses a simplified fixed target of three usable items per node, not the
  documented safety-cap-derived formula.
- Nodes with one or two items are topped up to three.

References:

- `backend/app/services/assessment.py:25-26` — fixed target and generation
  ceiling.
- `backend/app/services/assessment.py:535-555` — deficit-to-three logic.

This means the current implementation already does not completely implement
the earlier inventory agreement. In particular, three items per node cannot
guarantee a no-repeat eight-response cap for one- or two-node graphs.

**Updated researcher rules and prototype**

- Generate only when a node has zero usable items.
- Request five items for every such empty node.
- A node with one to four existing usable items is not topped up.

References:

- `R/assessment_rules.md:44-54` — zero-stock trigger and volume five.
- `ATA_kst/api.R:186-209` — coverage means at least one usable item.
- `ATA_kst/api.R:212-237` — `trigger_yg_kui_vaja()` requests `maht=5`.

**Consequence**

The researcher rule relies on permitted repetition as the ultimate fallback.
It is incompatible with the previous guarantee that every assessment can
reach the safety cap using distinct items.

### 6. When a five-item generation order is considered ready

This point is ambiguous inside the researcher implementation.

- The rules explain that five items are requested to reduce repetition:
  `R/assessment_rules.md:44-54`.
- ATA's coverage function checks only for one usable item and requests only one
  row: `ATA_kst/api.R:186-209`.
- The status route activates the assessment once every node passes that
  one-item coverage check: `ATA_kst/api.R:393-412`.

If YG inserts items one at a time, the assessment may become active before all
five requested items exist. The earlier draft plan said to wait for all five;
that was an inference from the stated rationale, not behavior established by
the researcher code. The researcher should clarify whether readiness means:

1. at least one usable item exists; or
2. the five-item order has completed successfully.

### 7. Inventory exhaustion as a stopping reason

**Previous agreement and current implementation**

- If no unused candidate remains before natural or safety-cap completion, the
  assessment ends with `item_inventory_exhausted` rather than repeating an
  item.

References:

- `docs/adaptive_item_inventory.md:234-247` — explicit exhaustion fallback.
- `R/src/service.R:105-141` — v2 advancement and exhaustion profile.
- `backend/app/services/assessment.py:438-456` — exhaustion telemetry.

**Updated researcher rules and prototype**

- Inventory exhaustion is handled by repeating the least-repeated item.
- The only stated completion paths are natural confidence after the global
  floor or the safety cap.

References:

- `R/assessment_rules.md:28-36` — repetition after pool exhaustion.
- `R/assessment_rules.md:56-79` — only natural and safety-cap stopping.
- `TP_kst/app.R:264-279` — implementation of those two stop paths.

**Consequence**

`item_inventory_exhausted` cannot remain an assessment stop for new sessions
if the researcher repeat rule is adopted. It would remain necessary only for
historical sessions or if the no-repeat agreement is retained.

### 8. Natural-stop confidence threshold

**Previous agreement and current implementation**

- The version-controlled/default threshold is `0.8`.
- The reliability floor and safety-cap formulas are otherwise the same as the
  updated rules.

References:

- `docs/pilot_architecture_plan.md:59-66` — earlier agreed KST configuration.
- `R/config/kst.json:1` — current repository default.
- `R/src/assessment.R:72-87` — configuration-driven stopping.

The active database configuration can override the repository default, so its
current value must be checked separately before rollout.

**Updated researcher rules and prototype**

- Natural completion requires `max(posterior) >= 0.9` after the same global
  reliability floor.

References:

- `R/assessment_rules.md:56-77` — formula, explanation, and global-not-per-node
  requirement.
- `TP_kst/app.R:264-276` — implemented `0.9` boundary.
- `R/assessment_rules.md:85-88` — recorded change from `0.8` to `0.9`.

**Consequence**

This appears to be an intentional researcher change backed by simulations,
not a prototype accident. It should still be confirmed because it supersedes
the architecture plan and changes assessment length/accuracy.

### 9. Which `beta` and `eta` update the posterior

**Previous agreement and current implementation**

- The posterior update uses the concrete administered item's snapshotted
  `beta` and `eta`.

References:

- `docs/adaptive_item_inventory.md:15-17` and `215-228` — explicit item-level
  parameter decision.
- `R/src/assessment.R:55-70` — current item-specific likelihood update.
- `backend/app/services/assessment.py:393-408` — administered item parameters
  are passed to R.

**Researcher prototype**

- `vali_ylesanne_solmele()` returns the selected item's `beta` and `eta`:
  `TP_kst/TP_loogika.R:151-171`.
- ATA builds one representative `beta`/`eta` pair per node from one covered
  item: `ATA_kst/api.R:250-270`.
- The actual response update uses those model-level node vectors, not the
  selected item's returned values: `TP_kst/app.R:249-257`.
- The rules document does not specify parameter granularity.

**Consequence**

This is likely an unintentional prototype inconsistency. Copying the runtime
literally would regress the calibrated-item behavior agreed earlier. The
default recommendation is to retain item-specific parameters unless the
researcher explicitly says that parameters are intended to be node-level.

### 10. Logic that already matches

The following behavior does not need conceptual refactoring:

- prerequisite-closed KST state construction and a uniform prior;
- Bayesian correct/incorrect likelihood semantics;
- the global reliability-floor formula;
- the safety-cap formula and natural-over-safety precedence;
- cumulative `0.9` credible-state feedback and existing node classification;
- selecting items by exact graph node and usable status without a course
  filter;
- incrementing global item usage telemetry after an accepted answer.

Relevant researcher references include
`R/assessment_rules.md:21-26,56-79`,
`TP_kst/TP_loogika.R:136-139,257-358`, and
`TP_kst/app.R:239-276`.

## Potential bugs or underspecified behavior in the researcher sources

These should be raised separately from policy disagreements:

1. **Selected item parameters are ignored.** The item selector returns them,
   but the update uses representative node vectors.
2. **Five-item generation can activate after one item.** The stated rationale
   and readiness behavior do not align.
3. **Tie handling is implicit.** Both usage-based `order()` calls have no
   explicit secondary key, and the database query has no explicit ordering.
4. **Global usage increment is vulnerable to lost updates.** The prototype
   reads `kasutamiste_arv` and writes `old + 1` in
   `TP_kst/app.R:249-252`; concurrent sessions can overwrite one another.
   The current backend's optimistic retry is safer and should be retained.
5. **No usable item after node selection becomes an error.** The researcher
   selector stops at `TP_kst/TP_loogika.R:157`; no withdrawal/failure policy is
   documented.

## Questions for the researcher

These decisions should be answered before selecting an implementation path:

1. May the same concrete item be administered more than once in one
   assessment, despite the memory/non-independent-evidence concern?
2. Must half-split always choose from all model nodes, or may nodes without an
   unused item be temporarily excluded?
3. Should an assessment use a fixed activation-time item pool or query the
   live item bank for every question?
4. Is global `kasutamiste_arv` intended to affect item choice? If tied, what is
   the required deterministic secondary rule?
5. For a node with zero usable items, must activation wait for all five newly
   requested items, or only the first usable item?
6. Should nodes with one to four existing items be topped up, or is generation
   strictly zero-stock only?
7. Is `item_inventory_exhausted` still a valid stop reason, or must repetition
   always prevent it?
8. Is the `0.9` stop-confidence threshold now authoritative for production?
9. Must Bayesian updates use the administered item's parameters or a
   representative node-level pair?
10. If repetition is allowed, is the repeated response intentionally treated
    as independent Bayesian evidence with no memory adjustment?

## Refactoring plan after reconciliation

### 1. Record the resolved assessment policy

- Update `R/assessment_rules.md` or add an approved decision record that
  answers every question above.
- Mark `docs/adaptive_item_inventory.md` as confirmed, superseded, or amended;
  do not leave contradictory normative documents active.
- Update `docs/pilot_architecture_plan.md` if `0.9` is confirmed.

### 2. Refresh the researcher characterization baseline

- Update the reference harness, hashes, and stopping fixtures for the newly
  supplied `TP_kst/` and `ATA_kst/` sources.
- Add characterization cases for unused-item global balancing, repeat
  balancing, generation volume, and threshold boundaries.
- Add a test that exposes the selected-item versus representative-node
  parameter discrepancy so the final decision is intentional.

### 3. Implement only the confirmed differences

- If **no-repeat remains authoritative**, retain fixed pools, unused-candidate
  selection, duplicate-item invariants, and exhaustion handling. Apply only
  confirmed threshold, generation, or balancing changes compatible with that
  model.
- If **researcher repetition becomes authoritative**, version the internal R
  contract and persisted player state. New sessions must support node-first
  selection and repeated item IDs; historical/in-progress sessions retain
  their snapshotted old behavior.
- In either branch, keep item-specific `beta`/`eta` and safe usage-counter
  increments unless the researcher explicitly decides otherwise.

### 4. Verify behavior with scenario tests

- Run identical posterior/response scenarios through the approved reference
  and the refactored R/backend path.
- Cover a node selected more times than its item count, one- and two-node
  graphs, confidence values immediately around the chosen threshold, partial
  YG generation, concurrent usage increments, and tied item-selection counts.
- Run the complete R suite, backend pytest suite, and
  `backend/.venv/bin/python -m pyright` with zero errors.

### 5. Roll out with version isolation

- Persist the confirmed configuration as a new immutable KST configuration
  version and activate it only when the matching code is deployed.
- Existing assessments keep their stored model/configuration and execution
  semantics; do not change logic midway through an assessment.
- Monitor natural stops, safety-cap stops, inventory exhaustion/repetition,
  item exposure counts, and assessment length after rollout.

## Defaults pending researcher confirmation

These are recommendations, not approved rules:

- retain concrete item-specific `beta`/`eta`;
- retain optimistic/concurrency-safe global usage increments;
- use deterministic item-ID ordering only as a secondary tie-breaker;
- preserve old behavior for already active/preparing sessions;
- do not implement repeated items until the researcher explicitly confirms
  that responses to repeated prompts should count as new Bayesian evidence.

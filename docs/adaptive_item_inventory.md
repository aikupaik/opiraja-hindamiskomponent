# Adaptive assessment item inventory

## Decision

The long-term solution is constrained, item-aware adaptive selection:

1. Python owns item-bank eligibility, session-local exposure history, and
   inventory preparation.
2. R selects the best next candidate only from the unused candidates supplied
   by Python.
3. A concrete item must not be administered more than once in one assessment
   session.
4. The assessment is provisioned before activation with enough distinct items
   to reach the R safety cap without repetition.
5. The Bayesian update uses the parameters of the concrete administered item,
   rather than parameters copied from an arbitrary representative item for its
   node.

This is a combined R and Python change. Increasing a fixed generator volume or
adding an unconditional per-node selection limit does not solve the problem
correctly.

## Problem

The current R service selects a graph node, not a concrete test item. Repeating
a node can be valid adaptive behaviour because several different items can
provide independent evidence about the same competency.

The demonstrated three-node session in `R/manual/demo_results.md` selected node
`C` six times. This was expected half-split behaviour, not an accidental loop:
after each correct response, `C` remained the best half-split node while the
global reliability floor required at least seven responses.

The invalid behaviour occurs after R has selected the node:

- Python considers a node covered when one usable item exists.
- Missing nodes receive a generator order with a shared `volume=3`.
- Generator completion requires only one usable item per requested node.
- Python prefers an unused item for the selected node, but falls back to a used
  item when the node's inventory is exhausted.
- R treats the repeated prompt as a new Bayesian observation.

Repeated exposure can make the posterior overconfident because the learner may
answer from memory and the response is no longer independent evidence under
the assumed model.

There is also a related parameter problem. The R model currently stores one
`beta` and `eta` pair per node, copied from the first usable item found during
coverage resolution. Python may later administer a different item for that
node. This is hidden while all values are uncalibrated defaults, but becomes
incorrect when concrete items receive different calibrated parameters.

## Required invariants

The implementation must maintain these invariants:

- A session's `current_question.item_id` is not present in that session's
  answered-item history.
- Every answered `item_id` occurs at most once in a session.
- Python never supplies an already-used item as an R selection candidate.
- R never selects a node or item outside the supplied candidate set.
- An active session has enough session-eligible distinct items to reach its
  stored safety cap, unless an item is administratively withdrawn after
  activation.
- The response update uses the `node`, `beta`, and `eta` of the administered
  item recorded in the persisted current question.
- Inventory exhaustion never falls back to repeated exposure.

The no-repeat rule is session-local. A usable item may be offered in many
different learners' sessions; it is not globally consumed and does not require
exclusive reservation.

## Inventory requirement

Let:

- `n` be the number of graph nodes;
- `C` be the safety cap calculated by R for the assessment's stored
  configuration;
- `m` be the minimum usable inventory per node.

Use:

```text
m = ceiling(C / n)
deficit(node) = max(0, m - usable_item_count(node))
```

The current R configuration is:

```text
reliability_floor(n) =
    min(max(7, ceiling(1.5 * n)), 10)

safety_cap(n) =
    max(2 * n, reliability_floor(n) + 1)
```

The resulting targets are:

| Graph nodes | Reliability floor | Safety cap `C` | Items per node `m` |
| ---: | ---: | ---: | ---: |
| 1 | 7 | 8 | 8 |
| 2 | 7 | 8 | 4 |
| 3 | 7 | 8 | 3 |
| 4 | 7 | 8 | 2 |
| 5 | 8 | 10 | 2 |
| 7 | 10 | 14 | 2 |
| 10 | 10 | 20 | 2 |

This is a strict no-repeat bound when R selects only from unused candidates.
There are at least `n * ceiling(C / n) >= C` distinct items in the session
pool. Before response `C`, at least one item must therefore remain. After
response `C`, the safety-cap stopping rule completes the assessment and no
next item is needed.

This bound is substantially smaller than provisioning `C` items for every
node. For the demonstrated three-node graph, three items per node are enough
when depleted nodes are removed from R's candidate set. They are not enough
under the current unconstrained selector, which can continue choosing `C`.

The target must be derived from the safety cap embedded in the assessment
model. Python must not duplicate the R formulas or use an independently
configured fixed volume. R should expose the calculated `reliability_floor`
and `safety_cap` as model metadata.

## Assessment lifecycle

### 1. Build the assessment model and inventory plan

R builds the knowledge-space model from the graph and stored KST configuration.
The model response includes the derived reliability floor and safety cap for
that graph.

Python counts usable, distinct items for every node, calculates `m`, and
creates per-node deficits. A node with some inventory is topped up only by its
deficit; existing usable items are reused.

The R model-building contract should no longer depend on parameters copied
from one representative item per node. Concrete response parameters belong to
selection and advancement, not graph construction.

### 2. Prepare missing inventory

When any deficit is positive, the session remains `preparing`. The generator
order must express the requested amount per node:

```json
{
  "item_requests": [
    {"node": "A", "amount": 1},
    {"node": "B", "amount": 3}
  ]
}
```

The generator marks the order completed only after the requested usable counts
actually exist. Partial generation leaves the session preparing and exposes
the remaining deficits for retry. A shared `volume` applied to all nodes is no
longer the authoritative contract.

Generation does not run during an active assessment. Live generation has
unbounded latency and does not provide a dependable item-quality guarantee.

### 3. Activate with a session item pool

Once all deficits are zero, Python persists a session-local pool containing
the eligible item IDs and the item version or immutable measurement metadata
needed by the assessment:

- candidate ID or item ID;
- node;
- `beta`;
- `eta`.

The item prompt and answer key remain in Python/Supabase and are not sent to R.
The pool fixes which item versions the session can use and makes restart and
retry behaviour reproducible.

If an item must be withdrawn for a content or safety reason after activation,
Python removes it from future candidate sets. The exhaustion rule below
protects the session if withdrawals invalidate its original inventory
guarantee.

### 4. Select only from unused candidates

For the first question and after each accepted answer, Python sends R the
remaining candidate descriptors. Candidate identifiers are opaque to R:

```json
[
  {"candidate_id": "item-101-v1", "node": "B", "beta": 0.05, "eta": 0.25},
  {"candidate_id": "item-205-v2", "node": "C", "beta": 0.08, "eta": 0.20}
]
```

The initial selection rule should preserve current half-split behaviour:

1. calculate the half-split distance for each candidate's node;
2. ignore nodes that have no remaining candidate;
3. select the candidate whose node has the smallest distance;
4. resolve equal scores using stable candidate order so retries are
   reproducible.

Several candidates for the same node have the same half-split score. The
stable tie rule is sufficient while parameters are uncalibrated. When
calibrated item parameters are trustworthy, R can replace the tie rule with a
validated expected-information criterion without changing Python's inventory
responsibility.

R returns the opaque `candidate_id` and node. Python verifies that both match
the supplied set, loads the corresponding item content, and persists the
question before returning it to the player.

### 5. Advance with the administered item's parameters

The advance request identifies the persisted current candidate and supplies:

- its node;
- its concrete `beta` and `eta`;
- correctness;
- response count;
- the unused candidates available for the next selection.

The R update uses the concrete item's error parameters for the selected node.
The pure update function should accept those scalar response parameters
directly rather than relying on model-wide vectors derived from representative
items.

R first updates the posterior and evaluates natural and safety-cap completion.
If the assessment remains in progress, R selects the next candidate from the
supplied unused set and returns it in the same response.

### 6. Handle unexpected exhaustion explicitly

If the assessment has not otherwise completed and no unused candidate remains,
R completes from the current posterior with:

```text
stop_reason = "item_inventory_exhausted"
confidence_limited = true
```

This is an exceptional fallback for administrative withdrawal, corrupt
inventory, or a violated preparation invariant. It must be observable in
structured logs and telemetry. Python must not rotate or reuse previously
answered items.

## Internal R API direction

Implement the change as a new version of the internal KST contract rather than
silently changing v1.

The versioned contract should support three pure operations:

1. model construction from graph/configuration, returning the posterior and
   derived assessment limits;
2. initial selection from supplied candidate descriptors;
3. posterior advancement using the administered item parameters, followed by
   completion or selection from the remaining candidates.

R remains stateless and has no database credentials or item content. Python
persists the returned model, configuration, item pool, current question,
posterior, and exposure history.

## Persistence and concurrency

The player-state schema must be versioned again because it gains a session
item pool and candidate/version identity. Existing v1 sessions remain readable
but must not be resumed through the new selection contract unless an explicit
migration is designed.

Answer submission keeps the existing idempotent order:

1. validate the persisted current question;
2. score it;
3. call R with that concrete item's parameters and the remaining candidate
   set;
4. build the next persisted state;
5. insert/recover the answer and compare-and-set the session.

Concurrent retries may calculate the same R transition, but the existing
submission-ID and compare-and-set rules ensure that only one transition is
accepted. Stable candidate ordering ensures identical requests calculate the
same next candidate.

Global item `usage_count` remains telemetry and must not be used as a
session-level exclusion mechanism. Session history and the persisted pool are
authoritative for no-repeat selection.

## Relevant modules and files

### R service and contract

- `R/contracts/internal-kst-v1.openapi.json`: retain as the frozen v1
  contract; add a new versioned contract for limits, candidate selection,
  concrete item parameters, and `item_inventory_exhausted`.
- `R/plumber.R`: expose the versioned selection and advancement routes.
- `R/src/model.R`: remove representative-item parameters from graph-model
  construction and include derived assessment limits in the stored model.
- `R/src/assessment.R`: implement candidate-constrained half-split selection,
  concrete-item Bayesian updates, and exhaustion stopping.
- `R/src/service.R`: orchestrate model, initial selection, and
  advance-then-select responses.
- `R/src/validation.R`: validate candidate identity, node membership,
  parameters, uniqueness, and remaining-candidate requests.
- `R/src/http.R`: serialize the new candidate and completion response shapes.
- `R/src/profile.R`: accept and preserve the new exhaustion stop reason.
- `R/src/configuration.R` and `R/config/kst.json`: remain the source of truth
  for reliability and safety-cap policy; expose calculated values without
  duplicating their formulas in Python.
- `R/tests/testthat/`: add constrained-selection, concrete-parameter,
  exhaustion, limit-metadata, deterministic-retry, and new-contract tests.
- `R/README.md` and `R/manual/`: document and demonstrate the versioned
  candidate-aware flow.

### Python domain and service

- `backend/app/domain/models.py`: add inventory-plan, candidate, session-pool,
  derived-limit, and exhaustion-stop values; bump the player-state and KST
  model schema versions.
- `backend/app/domain/repository.py`: replace boolean coverage and
  used-item-fallback semantics with usable counts, candidate-pool resolution,
  and strict unused-item access.
- `backend/app/services/assessment.py`: calculate deficits, keep incomplete
  sessions preparing, persist the pool, pass remaining candidates to R, use
  concrete item parameters, and remove repeated-item fallback.
- `backend/app/integrations/r_dtos.py`: define the new versioned R request and
  response DTOs.
- `backend/app/integrations/kst_engine.py`: implement model-limit, initial
  selection, and candidate-aware advancement calls.
- `backend/app/services/questions.py`: build a question only for the exact
  selected candidate and preserve its version/measurement identity.
- `backend/app/api/dtos.py`: continue exposing `confidence_limited`; map
  inventory exhaustion to it without exposing internal item metadata.

### Python persistence

- `backend/app/persistence/supabase_repository.py`: count usable items, load
  the activation pool, enforce strict candidate lookup, and persist the new
  session state.
- `backend/app/persistence/supabase_mapping.py`: encode/decode the versioned
  model, item pool, per-node generation deficits, and new stop reason.
- `backend/tests/fakes/assessment_repository.py` and
  `backend/tests/fakes/kst_engine.py`: model the strict inventory and
  candidate-selection contracts.
- `backend/tests/test_assessment_service.py`: cover inventory planning,
  activation, no-repeat advancement, exhaustion, retries, and item-specific
  parameters.
- `backend/tests/test_in_memory_repository.py`,
  `backend/tests/test_supabase_repository.py`, and
  `backend/tests/test_supabase_mapping.py`: cover counts, pool persistence,
  order deficits, and schema mappings.
- `backend/tests/test_kst_engine.py` and `backend/tests/test_r_contract.py`:
  cover the new versioned internal R contract.
- `backend/tests/test_api.py`: verify that exhaustion is confidence-limited
  and that candidate/node/parameter metadata remains private.

### Generator and database contract

- `YG_edge_function.ts`: consume per-node requested amounts and declare
  success only when every requested target count exists.
- `yg_tellimused` persistence schema: replace or supplement shared `maht` with
  a per-node request representation and store enough completion information
  to retry only remaining deficits.
- `docs/supabase_andmemudel.md`: document the order payload, session item pool,
  item-version semantics, and new stop reason.

## Acceptance criteria

The change is complete when:

- no accepted session can contain the same item/version twice;
- activation requires the calculated per-node inventory target;
- partial generation cannot activate a session;
- R never returns a candidate outside the supplied unused set;
- depleted nodes are excluded without preventing R from selecting another
  informative node;
- the concrete administered item's parameters drive the posterior update;
- the three-node demonstrated response sequence completes without repeating an
  item when three usable items per node exist;
- an unexpected empty candidate set completes explicitly as
  `item_inventory_exhausted`;
- idempotent retries return the same persisted next question;
- answer keys, node identity, candidate-pool metadata, and measurement
  parameters remain hidden from the player API; only the selected question
  content is exposed.

# Adaptive assessment item inventory

## Purpose

This note records a limitation in the current adaptive assessment flow and
possible ways to address it. It is intended as a basis for later architecture
work and discussion with the assessment researcher.

## Current behaviour

The R KST service selects a **node**, not a concrete test item. After an answer,
`POST /internal/v1/kst/advance` updates the posterior and may return the same
`next_node` repeatedly. Repeating a node is valid adaptive behaviour: each
visit can gather more evidence about the same competency, provided that the
learner receives a different item.

The backend currently handles item inventory as follows:

1. When an assessment is created, it checks whether each graph node has at
   least one usable item.
2. A node is considered covered as soon as one usable item exists.
3. If a node has no usable items, the assessment enters `preparing` and the
   backend creates a generator order with `volume=3`.
4. The generator attempts to create three different items for each missing
   node.
5. The assessment can become active once every node has at least one usable
   item. It does not require all three requested items to exist.
6. During an active assessment, the backend queries the usable items for the
   node returned by R. It prefers items that have not yet been used in that
   session.
7. When every available item for a node has been used, the backend reuses an
   existing item. With the current ordering logic, it repeatedly selects the
   first used item rather than rotating evenly through all used items.
8. The backend does not create a new generator order during an active
   assessment. It can notice items added externally because it queries the
   item bank again, but it does not request those additions itself.

Consequently, in the normal case a previously empty node receives three
automatically generated items and is then treated as permanently covered.
Later assessment creation does not top up that node because the coverage check
only distinguishes zero items from one-or-more items. Partial generator
success can leave a node with fewer than three.

Multiple concurrent generator orders or manual additions can incidentally
produce more items, but this is not a dependable inventory policy.

## Why this is a problem

R has no per-node selection limit. A node can be selected more often than the
number of distinct items available for it. For example, a demonstrated
adaptive session selected one node six times. With only three items, the
learner sees those items again, weakening the validity of the evidence:

- the learner may answer from memory rather than competency;
- repeated exposure changes item difficulty and response independence;
- the posterior update treats each response as new evidence even when the
  prompt is familiar;
- repeated items can make the adaptive experience appear defective;
- the resulting competency profile may be more confident than the item
  evidence warrants.

Increasing the generator volume from three to five would reduce repetition but
would not solve the observed six-selection case and would not provide a
general guarantee.

## Relevant R stopping limits

The current R configuration uses a global reliability floor and safety cap:

```text
reliability_floor(n) =
    min(max(7, ceiling(1.5 * n)), 10)

safety_cap(n) =
    max(2 * n, reliability_floor(n) + 1)
```

Here, `n` is the number of graph nodes. Natural completion requires posterior
confidence of at least `0.8` and reaching the reliability floor. Otherwise the
assessment stops at the safety cap.

Examples:

| Graph nodes | Reliability floor | Safety cap |
| ---: | ---: | ---: |
| 1 | 7 | 8 |
| 2 | 7 | 8 |
| 3 | 7 | 8 |
| 4 | 7 | 8 |
| 5 | 8 | 10 |
| 7 | 10 | 14 |
| 10 | 10 | 20 |

The cap limits the total number of questions, not the number for any one node.
In the strict worst case, R could select the same node for every question.

## Options

### Option 1: Increase the fixed volume

Change the generated amount from three to a larger fixed value, such as eight.

Eight has a useful rationale: it covers the strict no-repeat worst case for
graphs containing up to four nodes under the current R configuration, and it
would cover the observed six-selection session.

Advantages:

- very small backend change;
- no live generation during an assessment;
- suitable as a near-term demo mitigation.

Disadvantages:

- still not a guarantee for larger graphs;
- generates the same amount regardless of existing inventory;
- can create unnecessary items for nodes that already have enough;
- the number can become incorrect if R stopping configuration changes.

Five is not recommended as the new fixed value because it is already below an
observed requirement.

### Option 2: Pre-session inventory based on the safety cap

Before activating an assessment, count the usable items for every node and
generate the deficit up to the graph's R safety cap:

```text
target = safety_cap(graph_node_count)
deficit(node) = max(0, target - usable_item_count(node))
```

Activate only after every node reaches the target.

Advantages:

- guarantees no repeated item within the current maximum assessment length;
- keeps generation outside the live assessment;
- reuses existing item-bank inventory;
- derives the requirement from the assessment algorithm.

Disadvantages:

- conservative: it assumes one node might receive every question;
- potentially expensive for large graphs;
- couples backend preparation to R stopping configuration;
- requires counting items rather than checking only for existence;
- requires a way to express different deficits for different nodes.

The current generator order has one shared `volume` for all listed nodes.
Variable deficits would require either:

- separate orders grouping nodes with the same deficit; or
- a revised payload such as `{node, amount}` for each node.

### Option 3: Configurable pre-session buffer

Define a configurable inventory target, for example eight usable items per
node, and top up every node to that target before activation.

Advantages:

- simpler than deriving and synchronizing the R safety cap;
- generation remains outside the active session;
- avoids repeatedly generating a full fixed amount when some inventory exists;
- permits operational tuning based on observed adaptive sessions.

Disadvantages:

- does not provide a strict guarantee for all graph sizes;
- needs monitoring and periodic review;
- the chosen value needs research justification.

This can be a practical intermediate design: start with eight, record actual
maximum selections per node, and revise the target using evidence.

### Option 4: Research-based per-node inventory policy

Develop a less conservative requirement from simulations or empirical test
runs. For each supported graph shape and R configuration, simulate response
patterns and measure the distribution of the maximum number of selections for
one node. Choose inventory targets at an agreed percentile and add a safety
margin.

Advantages:

- may require substantially fewer items than the strict worst case;
- provides a defensible link between item-bank cost and repetition risk;
- can account for graph structure, stopping rules, and realistic response
  patterns.

Disadvantages:

- probabilistic rather than an absolute guarantee;
- requires research work and representative assumptions;
- must be repeated when the adaptive algorithm or configuration changes.

### Option 5: Prevent repetition as a final safety rule

Regardless of the inventory policy, the backend should not silently serve an
already-used item as if it were new evidence. If R requests a node with no
unused item, possible policies include:

- finish the assessment with `confidence_limited=true`;
- stop with an explicit `item_inventory_exhausted` reason;
- ask R to choose from nodes that still have unused items, if a
  psychometrically valid constrained-selection interface is designed.

Advantages:

- protects assessment validity when inventory assumptions fail;
- makes shortages observable;
- prevents accidental repeated-item evidence from inflating confidence.

Disadvantages:

- early termination may reduce assessment precision;
- constraining R's node selection changes the adaptive algorithm and requires
  research validation;
- introduces a new stopping condition and feedback semantics.

Rotating evenly through used items would improve presentation but would not
solve the validity problem. Repeated items should not normally be treated as
independent evidence.

## Suggested direction

A staged approach is recommended:

1. For the near-term demo, increase the fixed generation volume from three to
   eight.
2. Change coverage from a boolean check to an item-count check and top up
   inventory before activation.
3. Make the target configurable initially.
4. Add a no-repeat exhaustion guard so a shortage cannot silently produce
   repeated evidence.
5. Use simulations and observed session telemetry to decide whether the final
   target should be the strict R safety cap or a smaller research-supported
   buffer.

The more robust long-term rule is:

> An assessment session should not start unless its item inventory satisfies
> an explicit policy for the maximum plausible number of visits to each node.

## Questions for research discussion

- Is it psychometrically acceptable to ask multiple different items associated
  with the same node using the same node-level `beta` and `eta` parameters?
- Should the same item ever be repeated in one session, and if so, should its
  repeated response update the posterior?
- Is a strict worst-case guarantee required, or is an agreed probability of
  no repetition sufficient?
- What percentile and safety margin would be acceptable for a simulation-based
  inventory target?
- Should inventory targets vary by graph size, graph topology, node, course,
  or item quality?
- If inventory is exhausted, is early `confidence_limited` completion
  preferable to constraining R to another node?
- Should items be reserved for a session, or is sharing a usable item bank
  across concurrent sessions acceptable?
- How should archived or newly reviewed items affect an already prepared
  session?
- Should R expose its calculated reliability floor and safety cap as model
  metadata so the backend does not duplicate the formulas?

## Relevant implementation locations

- `backend/app/services/assessment.py`: coverage decision, fixed generator
  volume, R advancement, and next-question selection.
- `backend/app/persistence/supabase_repository.py`: one-item coverage lookup
  and unused-before-used item ordering.
- `R/src/service.R`: posterior update and returned `next_node`.
- `R/src/assessment.R`: stopping decision.
- `R/src/configuration.R` and `R/config/kst.json`: reliability-floor and
  safety-cap definitions.
- `YG_edge_function.ts`: generation volume and completion based on at least
  one usable item per requested node.

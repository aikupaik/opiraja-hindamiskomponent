# Fixtures

Fixtures will be added in the next harness step. They must be deterministic,
contain no pilot data or credentials, and use run-owned `perf-...` markers.

The first fixture set will cover the plan's three graph shapes:

- 3-node chain;
- 10-node chain; and
- 10-node relation-free graph.

High-volume scenarios must use covered inventory. Missing-inventory/YG cases
remain separate controlled functional tests with a maximum of three sessions.

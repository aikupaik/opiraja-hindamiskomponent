# Fixtures

Fixtures are deterministic, contain no pilot data or credentials, and use
`perf-...` markers for opaque identifiers.

## R component fixtures

The `r/` directory contains one JSON fixture for each graph shape in the
capacity plan:

- `3-chain.json`: 3 nodes, 2 prerequisite relations, and 4 knowledge states;
- `10-chain.json`: 10 nodes, 9 prerequisite relations, and 11 knowledge states;
- `10-independent.json`: 10 nodes, no relations, and 1,024 knowledge states.

Each file records replayable `model`, `select`, and first-answer `advance`
requests for the internal v2 R API together with their expected responses.
Candidate order, the correct first response, and three candidates per node are
fixed. Three candidates per node matches the application's covered-inventory
minimum without using database-owned item identifiers.

Generate the files only through the repository script:

```sh
Rscript performance/fixtures/r/generate.R --write
```

Check that committed files still recompute byte-for-byte from the production R
implementation without changing them:

```sh
Rscript performance/fixtures/r/generate.R --check
```

High-volume scenarios must use covered inventory. Missing-inventory/YG cases
remain separate controlled functional tests with a maximum of three sessions.

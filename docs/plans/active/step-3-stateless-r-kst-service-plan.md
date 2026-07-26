# Step 3 — Stateless R KST Service

## Summary

Implement the production R calculation service under `R/`, using the Step 1
fixtures and OpenAPI document as the authoritative behavior and wire contract.

- Keep `ATA_kst/` and `TP_kst/` unchanged; copy only applicable algorithms
  into new English-named, side-effect-free modules.
- Limit the service to KST calculation, validation, and JSON transport. It
  receives no Supabase credentials and performs no database, item-bank, Shiny,
  or external network operations.
- Defer FastAPI integration, Docker Compose, Shiny replacement, and question
  selection/scoring to later implementation steps.

## Implementation Changes

### Restore the regression baseline and lock dependencies

- Restore `R/config/kst.json` to its canonical compact JSON representation so
  its bytes again produce the committed
  `kst-config-v1:sha256:89b7…c774` hash.
- Make fixture `--check` stable across unrelated commits: preserve the
  manifest's recorded Git revision during checks while continuing to use the
  protected source-file SHA-256 values to detect changes in `ATA_kst/` or
  `TP_kst/`.
- Initialize an renv project rooted at `R/`, committing `.Rprofile`,
  `renv/activate.R`, settings, and `renv.lock`.
- Pin R 4.6.1, `kst` 0.5-5, `kstMatrix` 2.3-4, and exact resolved versions of
  `plumber`, `jsonlite`, `digest`, `testthat`, and required transitive
  dependencies. Restore from the lock in tests and future containers.
- Remove test/runtime reliance on the ignored `R/library/` path without
  deleting that local directory.

### Pure KST modules

Create production modules under `R/src/`, loaded by `R/plumber.R`, covering:

- Configuration loading, schema validation, canonical serialization,
  reliability-floor/safety-cap formulas, and versioned hashing.
- Knowledge-state generation using the prototype's prerequisite-closed subset
  algorithm and ordering.
- Model construction: binary matrix, uniform prior, node-aligned `beta`/`eta`,
  configuration snapshot/hash, and initial node.
- Deterministic half-split selection: retain package-compatible behavior, but
  select the first tied candidate in declared node order.
- Bayesian updates through `kstMatrix::kmassessbayesian()`, always returning
  finite, normalized, unnamed probability arrays.
- Natural/safety-cap stopping with natural-stop precedence.
- Credible-state selection and five-way English profile classification copied
  from `lopeta_test()`, including the existing Estonian summary strings but
  excluding its database write.

`/model` loads the current configuration file and embeds its snapshot/hash.
`/advance` uses only the configuration embedded in the submitted model,
ensuring configuration changes affect new assessments without changing active
ones.

### Validation and Plumber adapter

Implement a thin Plumber adapter with an app/router factory and these routes:

- `GET /health` → `200 {"status":"ok"}` without reading configuration or
  invoking KST calculations.
- `POST /internal/v1/kst/model` → validated model, initial posterior, and first
  node.
- `POST /internal/v1/kst/advance` → either `in_progress` with the updated
  posterior/next node or `completed` with the final profile.

Validation must reject with the contract's `422` envelope:

- Malformed JSON, missing/unknown fields, incorrect scalar/array types,
  non-finite numbers, and whitespace-only or duplicate nodes.
- Relations whose endpoints are absent from `nodes`.
- Missing, duplicate, or extra node parameters and `beta`/`eta` outside
  `[0,1]`.
- Structurally invalid cached states: unknown/duplicate members, duplicate
  states, relation violations, missing empty/full states, or order inconsistent
  with declared nodes.
- Invalid persisted models: unsupported schema/method, matrix/state mismatch,
  non-binary or ragged matrices, inconsistent vector lengths, non-normalized
  probabilities, configuration/hash mismatch, unknown `question_node`, or
  invalid `response_count`.

Use manual JSON parsing with stable `{field, issue}` detail entries. A global
Plumber error handler returns a generic contract-shaped `500` without leaking
stack traces. Response shaping must preserve arrays—including empty and
single-element arrays—and strip R vector names.

Keep `R/contracts/internal-kst-v1.openapi.json` as the served API
specification, strengthen its configuration/validation descriptions where
needed, and remove its "future service" wording without changing the
established wire shape.

## Test Plan

- Compare every production pure function against the Step 1 fixtures: chain,
  fork, independent and redundant-relation spaces; generated/cached models;
  Bayesian vectors and sequences; deterministic half-split ties; stopping
  boundaries; and all profile categories.
- Test configuration hashing, old embedded configuration use during
  `/advance`, probability invariants, matrix/state alignment, natural-stop
  precedence, and preservation of JSON array shapes.
- Add table-driven validation tests for every malformed request/model category
  and assert exact `422` details; inject an unexpected calculation failure and
  assert the redacted `500` response.
- Exercise the Plumber router in-process with mock HTTP requests, covering all
  three routes, response content types/statuses, OpenAPI route parity,
  fixture-backed success responses, and health independence.
- Verify reproducibility and acceptance with:
  - `cd R && Rscript -e 'renv::restore(prompt = FALSE); renv::status()'`
  - `Rscript R/tests/reference/generate_fixtures.R --check`
  - `Rscript R/tests/testthat.R`
  - `git diff --exit-code -- ATA_kst TP_kst`

## Assumptions and Defaults

- The committed OpenAPI contract and Step 1 numerical fixtures remain
  authoritative; Step 3 may clarify schemas but will not redesign the API.
- R does not introduce a second graph-size setting; `MAX_GRAPH_NODES` remains
  the single FastAPI-side limit planned for Step 4.
- Existing unrelated working-tree changes, including the Step 2 plan move, are
  preserved.
- No Python or TypeScript changes are expected, so Pyright and frontend lint
  are not required for this step.

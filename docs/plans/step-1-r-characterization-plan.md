# Step 1 — Characterize Legacy KST Behavior

## Summary

Create a self-contained characterization suite under `R/` that freezes the
prototype’s numerical behavior before production extraction.

- Treat `ATA_kst/` and `TP_kst/` as immutable reference code.
- Do not create production KST modules or Plumber handlers yet; those remain
  Step 3.
- Add only reference adapters, committed JSON fixtures, experimental
  configuration, API contracts, tests, and supporting documentation.
- Exclude database, Shiny UI, YG, item selection, and persistence behavior from
  these numerical fixtures.

## Implementation Changes

### Reference harness and provenance

- Add an isolated harness under `R/tests/reference/` that loads legacy functions
  into private environments and replaces `sb_get`, `sb_post`, and `sb_patch`
  with in-memory stubs before invoking behavior.
- Exercise graph/state and model construction from `ATA_kst/api.R`, and
  half-split, Bayesian update, and final-profile behavior from
  `TP_kst/TP_loogika.R`.
- Do not source the Shiny entrypoints. Reproduce only the inaccessible stopping
  expressions from `TP_kst/app.R` in the reference harness, recording their
  source file and source hash.
- Normalize outputs before serialization: remove timestamps and R classes,
  remove vector names, preserve matrix row/column order, and serialize numbers
  with full precision.
- Record a fixture manifest containing fixture schema version, R version,
  `kst`/`kstMatrix` versions, Git revision, numerical tolerance, and SHA-256
  hashes of all three reference files. Omit generation timestamps so
  regeneration is deterministic.
- Provide explicit modes:
  - `Rscript R/tests/reference/generate_fixtures.R --check` recomputes and
    compares without writing.
  - `Rscript R/tests/reference/generate_fixtures.R --write` is the only
    fixture-update path.

### Numerical fixture catalogue

Store language-neutral JSON fixtures under `R/tests/fixtures/` with inputs and
expected outputs.

- Knowledge spaces:
  - Three-node chain `A → B → C`: `{}`, `{A}`, `{A,B}`, `{A,B,C}`.
  - Three-node fork `A → B`, `A → C`.
  - Three independent nodes: all eight subsets.
  - A chain containing an explicit redundant transitive relation, which must
    produce the same states as the simple chain.
- Model construction:
  - Exact state and matrix ordering.
  - Uniform prior and probability sum.
  - Alignment of node-specific `beta` and `eta` values with matrix columns.
  - Generated versus supplied cached knowledge states producing the same
    normalized model.
  - Initial half-split selection for a case with a unique optimum.
- Adaptive calculations:
  - Correct and incorrect Bayesian updates for the same node.
  - A fixed multi-answer update sequence with the posterior captured after
    every response.
  - Posterior invariants: unchanged length, non-negative values, sum equal to
    one, and unnamed JSON arrays.
  - Half-split tie characterization as an allowed-node set rather than one
    frozen random result.
- Stopping behavior:
  - Reliability floor and safety-cap boundary table for node counts
    `1, 4, 5, 7, 10`.
  - Confidence immediately below, exactly at, and above `0.8`.
  - Response count immediately below and exactly at the reliability floor and
    safety cap.
  - Natural stopping takes precedence when natural and safety-cap conditions
    are simultaneously true.
- Final profiles:
  - Single credible state, multiple credible states, all-mastered,
    multiple-next-direction, and safety-cap cases.
  - Coverage of mastered, ready-to-learn, uncertain-ahead, and not-yet
    classifications.
  - Preserve the uncertain-prerequisite output field and document that it
    remains empty in valid legacy fixtures if no reachable reference case
    produces it.
  - Verify credible-state selection uses the smallest descending-probability
    prefix whose mass reaches `0.9`.
- Use an explicit `1e-12` comparison tolerance for posterior and confidence
  values; use exact comparison for states, indices, categories, strings, and
  configuration hashes. This follows `testthat`’s distinction between
  approximate numeric and strict structural equality
  ([testthat equality expectations](https://testthat.r-lib.org/reference/equality-expectations.html)).

### Experimental KST configuration

Add `R/config/kst.json` as the single documented experimental configuration:

- `schema_version: 1`
- `stop_confidence: 0.8`
- `feedback_credible_mass: 0.9`
- Reliability floor parameters: minimum `7`, multiplier `1.5`, maximum `10`.
- Safety-cap parameters: node multiplier `2`, minimum `1` response above the
  calculated floor.

Define the formulas explicitly:

- `floor(n) = min(max(7, ceiling(1.5 × n)), 10)`
- `cap(n) = max(2 × n, floor(n) + 1)`

Canonicalize recursively sorted JSON keys, UTF-8 encoding, full-precision
numbers, and no insignificant whitespace. Expose the hash as
`kst-config-v1:sha256:<hex>`. Tests must prove that the file reproduces the
hard-coded prototype values.

### Internal API contract

Add a versioned OpenAPI JSON contract under `R/contracts/` and explain it in
`R/README.md`.

- `GET /health` returns `200 {"status":"ok"}` without dependencies.
- `POST /internal/v1/kst/model` accepts ordered nodes,
  prerequisite-to-dependent relations, ordered node parameters, and optional
  cached knowledge states.
- Its response contains:
  - A reusable `model` object with schema version, method, nodes, knowledge
    states, binary matrix, uniform prior, aligned `beta`/`eta`, configuration
    snapshot, and configuration hash.
  - The initial posterior and next node.
- `POST /internal/v1/kst/advance` accepts the stored model, current posterior,
  `question_node`, boolean `response_correct`, and `response_count` including
  the answer currently being processed.
- Its response is a discriminated union:
  - `status="in_progress"` with updated posterior and `next_node`.
  - `status="completed"` with updated posterior and final profile.
- Use node strings at the HTTP boundary; one-based R column indices remain
  internal.
- Define `422` validation and `500` unexpected-error envelopes as
  `{"error":{"code","message","details"}}`.
- Define exact English contract mappings:

| Legacy field/value | Internal API field/value |
|---|---|
| `omandatud` | `mastered` |
| `valmis_oppima` | `ready_to_learn` |
| `ebamaarane_edasi` | `uncertain_ahead` |
| `ebamaarane_tagasi` | `uncertain_prerequisite` |
| `veel_mitte` | `not_yet` |
| `kokkuvote` | `summary` |
| `peatumise_pohjus` | `stop_reason` |
| `loomulik` | `natural` |
| `turvapiir` | `safety_cap` |
| `kindlus_parim_olek` | `best_state_confidence` |
| `kindlus_C_hulgas` | `credible_mass` |
| `n_usutavaid_olekuid` | `credible_state_count` |

Document one intentional future divergence: legacy `kmassesshalfsplit()`
randomly samples exact ties. The contract selects the first tied node in
declared node order so Step 3 can produce reproducible sessions;
characterization fixtures retain the full legacy tie candidate set.

## Test and Acceptance Plan

- Add a non-package `testthat` runner invoked with
  `Rscript R/tests/testthat.R`.
- Tests must:
  - Recompute fixtures through the isolated legacy harness and detect any
    mismatch.
  - Validate fixture schemas, dimensions, state ordering, probability
    invariants, and profile mappings.
  - Validate the configuration formulas, canonical snapshot, and hash.
  - Parse the OpenAPI JSON and verify its examples match fixture-backed model
    and advance payloads.
  - Fail if reference source hashes differ, instructing the developer to
    investigate rather than silently regenerate.
- Acceptance requires:
  - `Rscript R/tests/reference/generate_fixtures.R --check` passes.
  - `Rscript R/tests/testthat.R` passes without network or Supabase
    credentials.
  - Two consecutive fixture generations are byte-identical.
  - `git diff --exit-code -- ATA_kst TP_kst` confirms both reference
    directories are untouched.
- No Pyright or frontend lint run is required because Step 1 changes no Python
  or TypeScript.

## Assumptions and Defaults

- Use R 4.6.1, `kst` 0.5-5, and `kstMatrix` 2.3-4 for fixture generation;
  record these versions in the manifest. The relevant package signatures and
  R ≥4.4 requirement are confirmed in the
  [official kstMatrix 2.3-4 manual](https://cran.r-project.org/web/packages/kstMatrix/kstMatrix.pdf).
- Dependency locking with `renv.lock`, production pure functions, Plumber
  wiring, request validation, and health implementation remain Step 3.
- Fixtures characterize deterministic calculation behavior and explicitly
  describe stochastic tie behavior; they do not declare the prototype
  authoritative for security, persistence, or validation.
- Existing unrelated working-tree changes are preserved.

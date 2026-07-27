#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1 || !args[[1]] %in% c("--check", "--write")) {
  stop("Usage: Rscript R/tests/reference/generate_fixtures.R --check|--write")
}
mode <- args[[1]]

script_arg <- grep("^--file=", commandArgs(), value = TRUE)
script_path <- if (length(script_arg) == 1) {
  normalizePath(sub("^--file=", "", script_arg), mustWork = TRUE)
} else {
  normalizePath("R/tests/reference/generate_fixtures.R", mustWork = TRUE)
}
source(file.path(dirname(script_path), "harness.R"))

root <- characterization_root()
characterization_use_local_library(root)
required <- c("digest", "jsonlite", "kst", "kstMatrix")
missing <- required[!vapply(required, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing) > 0) {
  stop("Missing R packages: ", paste(missing, collapse = ", "))
}

environments <- load_reference_environments(root)
tolerance <- 1e-12
nodes <- c("A", "B", "C")
chain_relations <- list(
  list(from = "A", to = "B"),
  list(from = "B", to = "C")
)
fork_relations <- list(
  list(from = "A", to = "B"),
  list(from = "A", to = "C")
)
redundant_relations <- c(
  chain_relations,
  list(list(from = "A", to = "C"))
)
parameters <- list(
  list(node = "A", beta = 0.1, eta = 0.2, item_id = "item-a"),
  list(node = "B", beta = 0.15, eta = 0.25, item_id = "item-b"),
  list(node = "C", beta = 0.2, eta = 0.3, item_id = "item-c")
)

chain_states <- generate_knowledge_space(
  environments, nodes, chain_relations
)
fork_states <- generate_knowledge_space(
  environments, nodes, fork_relations
)
independent_states <- generate_knowledge_space(
  environments, nodes, list()
)
redundant_states <- generate_knowledge_space(
  environments, nodes, redundant_relations
)

spaces <- list(
  schema_version = 1,
  cases = list(
    list(
      id = "three_node_chain",
      nodes = I(nodes),
      relations = chain_relations,
      expected_states = chain_states
    ),
    list(
      id = "three_node_fork",
      nodes = I(nodes),
      relations = fork_relations,
      expected_states = fork_states
    ),
    list(
      id = "three_independent_nodes",
      nodes = I(nodes),
      relations = list(),
      expected_states = independent_states
    ),
    list(
      id = "chain_with_redundant_transitive_relation",
      nodes = I(nodes),
      relations = redundant_relations,
      expected_states = redundant_states,
      same_states_as = "three_node_chain"
    )
  )
)

generated_model <- build_legacy_model(
  environments, nodes, chain_states, parameters
)
cached_states <- restore_knowledge_space(
  environments, nodes, chain_relations, chain_states
)
cached_model <- build_legacy_model(
  environments, nodes, cached_states, parameters
)
chain_matrix <- model_matrix(generated_model)
initial_posterior <- unlist(generated_model$prior, use.names = FALSE)
initial_candidates <- half_split_candidates(initial_posterior, chain_matrix)
initial_selected <- unname(environments$tp$vali_jargmine_solm(
  initial_posterior, chain_matrix
))

models <- list(
  schema_version = 1,
  input = list(
    nodes = I(nodes),
    relations = chain_relations,
    node_parameters = parameters
  ),
  generated_model = generated_model,
  cached_model = cached_model,
  generated_equals_cached = identical(generated_model, cached_model),
  initial_half_split = list(
    candidate_indices = I(unname(as.integer(initial_candidates))),
    allowed_nodes = I(unname(nodes[initial_candidates])),
    selected_index = as.integer(initial_selected),
    selected_node = nodes[[initial_selected]],
    unique_optimum = length(initial_candidates) == 1
  )
)

beta <- unlist(generated_model$beta, use.names = FALSE)
eta <- unlist(generated_model$eta, use.names = FALSE)
correct <- bayesian_update(
  environments, initial_posterior, chain_matrix, 2L, TRUE, beta, eta
)
incorrect <- bayesian_update(
  environments, initial_posterior, chain_matrix, 2L, FALSE, beta, eta
)
sequence_spec <- list(
  list(question_index = 2L, question_node = "B", response_correct = TRUE),
  list(question_index = 3L, question_node = "C", response_correct = FALSE),
  list(question_index = 1L, question_node = "A", response_correct = TRUE),
  list(question_index = 2L, question_node = "B", response_correct = TRUE)
)
sequence_posterior <- initial_posterior
sequence_steps <- lapply(seq_along(sequence_spec), function(index) {
  step <- sequence_spec[[index]]
  sequence_posterior <<- bayesian_update(
    environments,
    sequence_posterior,
    chain_matrix,
    step$question_index,
    step$response_correct,
    beta,
    eta
  )
  c(step, list(posterior = sequence_posterior))
})

tie_posterior <- c(0.5, 0, 0, 0.5)
tie_candidates <- half_split_candidates(tie_posterior, chain_matrix)
adaptive <- list(
  schema_version = 1,
  tolerance = tolerance,
  model_case = "three_node_chain",
  beta = beta,
  eta = eta,
  initial_posterior = initial_posterior,
  single_updates = list(
    correct = list(
      question_index = 2L,
      question_node = "B",
      response_correct = TRUE,
      posterior = correct
    ),
    incorrect = list(
      question_index = 2L,
      question_node = "B",
      response_correct = FALSE,
      posterior = incorrect
    )
  ),
  multi_answer_sequence = sequence_steps,
  posterior_invariants = list(
    length = length(initial_posterior),
    non_negative = TRUE,
    sum = 1,
    json_representation = "unnamed_array"
  ),
  half_split_tie = list(
    posterior = tie_posterior,
    allowed_indices = I(unname(as.integer(tie_candidates))),
    allowed_nodes = I(unname(nodes[tie_candidates]))
  )
)

node_counts <- c(1L, 4L, 5L, 7L, 10L)
stopping_rows <- unlist(lapply(node_counts, function(node_count) {
  floor_count <- min(max(7, ceiling(1.5 * node_count)), 10)
  cap_count <- max(2 * node_count, floor_count + 1)
  cases <- list(
    list(label = "below_confidence_at_floor", confidence = 0.8 - 1e-12,
         response_count = floor_count),
    list(label = "at_confidence_below_floor", confidence = 0.8,
         response_count = floor_count - 1L),
    list(label = "at_confidence_at_floor", confidence = 0.8,
         response_count = floor_count),
    list(label = "above_confidence_at_floor", confidence = 0.8 + 1e-12,
         response_count = floor_count),
    list(label = "below_confidence_before_cap", confidence = 0.8 - 1e-12,
         response_count = cap_count - 1L),
    list(label = "below_confidence_at_cap", confidence = 0.8 - 1e-12,
         response_count = cap_count),
    list(label = "natural_and_cap_simultaneous", confidence = 0.8,
         response_count = cap_count)
  )
  lapply(cases, function(case) {
    c(
      list(
        node_count = node_count,
        reliability_floor = floor_count,
        safety_cap = cap_count
      ),
      case,
      legacy_stopping_decision(
        node_count, case$confidence, case$response_count
      )
    )
  })
}), recursive = FALSE)
stopping <- list(
  schema_version = 1,
  tolerance = tolerance,
  source = stopping_source(root),
  cases = stopping_rows
)

fork_model <- build_legacy_model(
  environments, nodes, fork_states, parameters
)
fork_matrix <- model_matrix(fork_model)
profile_specs <- list(
  list(
    id = "single_credible_state",
    model_case = "three_node_chain",
    posterior = c(0.03, 0.91, 0.04, 0.02),
    matrix = chain_matrix,
    stop_reason = "natural"
  ),
  list(
    id = "multiple_credible_states",
    model_case = "three_node_chain",
    posterior = c(0.05, 0.45, 0.45, 0.05),
    matrix = chain_matrix,
    stop_reason = "natural"
  ),
  list(
    id = "all_mastered",
    model_case = "three_node_chain",
    posterior = c(0.02, 0.02, 0.02, 0.94),
    matrix = chain_matrix,
    stop_reason = "natural"
  ),
  list(
    id = "multiple_next_directions",
    model_case = "three_node_fork",
    posterior = c(0.01, 0.96, 0.01, 0.01, 0.01),
    matrix = fork_matrix,
    stop_reason = "natural"
  ),
  list(
    id = "safety_cap",
    model_case = "three_node_chain",
    posterior = c(0.25, 0.25, 0.25, 0.25),
    matrix = chain_matrix,
    stop_reason = "safety_cap"
  )
)
profiles <- list(
  schema_version = 1,
  credible_mass_threshold = 0.9,
  cases = lapply(profile_specs, function(spec) {
    prefix <- credible_prefix(spec$posterior, 0.9)
    list(
      id = spec$id,
      model_case = spec$model_case,
      posterior = spec$posterior,
      credible_state_indices = I(as.integer(prefix)),
      expected = legacy_profile(
        environments,
        spec$posterior,
        nodes,
        spec$matrix,
        spec$stop_reason
      )
    )
  }),
  uncertain_prerequisite_note = paste(
    "The field is preserved but empty in all valid legacy fixtures;",
    "no reachable valid knowledge-state case produces it."
  )
)

config_path <- file.path(root, "R", "config", "kst.json")
config_bytes <- readBin(
  config_path, what = "raw", n = file.info(config_path)$size
)
config_hash <- paste0(
  "kst-config-v1:sha256:",
  digest::digest(config_bytes, algo = "sha256", serialize = FALSE)
)
configuration <- list(
  schema_version = 1,
  canonical_snapshot = jsonlite::fromJSON(
    rawToChar(config_bytes), simplifyVector = FALSE
  ),
  configuration_hash = config_hash,
  formulas = list(
    reliability_floor = "min(max(7, ceiling(1.5 * n)), 10)",
    safety_cap = "max(2 * n, reliability_floor(n) + 1)"
  )
)

manifest_path <- file.path(root, "R", "tests", "fixtures", "manifest.json")
git_revision <- if (identical(mode, "--check") && file.exists(manifest_path)) {
  existing_manifest <- jsonlite::fromJSON(
    manifest_path,
    simplifyVector = TRUE
  )
  existing_manifest$git_revision
} else {
  unname(system2(
    "git", c("-C", root, "rev-parse", "HEAD"), stdout = TRUE
  )[[1L]])
}
manifest <- list(
  fixture_schema_version = 1,
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  package_versions = list(
    kst = utils::packageDescription("kst")$Version,
    kstMatrix = utils::packageDescription("kstMatrix")$Version
  ),
  git_revision = unname(git_revision),
  numerical_tolerance = tolerance,
  reference_sha256 = as.list(reference_hashes(root)),
  fixtures = c(
    "knowledge_spaces.json",
    "models.json",
    "adaptive.json",
    "stopping.json",
    "profiles.json",
    "configuration.json"
  )
)

fixtures <- list(
  "manifest.json" = manifest,
  "knowledge_spaces.json" = spaces,
  "models.json" = models,
  "adaptive.json" = adaptive,
  "stopping.json" = stopping,
  "profiles.json" = profiles,
  "configuration.json" = configuration
)

serialize_fixture <- function(value) {
  as.character(jsonlite::toJSON(
    value,
    auto_unbox = TRUE,
    null = "null",
    digits = NA,
    pretty = TRUE,
    force = TRUE
  ))
}

fixture_directory <- file.path(root, "R", "tests", "fixtures")
if (identical(mode, "--write")) {
  dir.create(fixture_directory, recursive = TRUE, showWarnings = FALSE)
}

mismatches <- character(0)
for (name in names(fixtures)) {
  path <- file.path(fixture_directory, name)
  expected <- serialize_fixture(fixtures[[name]])
  if (identical(mode, "--write")) {
    writeLines(expected, path, useBytes = TRUE)
  } else if (!file.exists(path)) {
    mismatches <- c(mismatches, paste0(name, " is missing"))
  } else {
    actual <- paste(
      readLines(path, warn = FALSE, encoding = "UTF-8"),
      collapse = "\n"
    )
    if (!identical(actual, expected)) {
      mismatches <- c(mismatches, paste0(name, " differs"))
    }
  }
}

if (length(mismatches) > 0) {
  stop(
    "Characterization fixture mismatch: ",
    paste(mismatches, collapse = "; "),
    ". Investigate legacy source/runtime changes; use --write only after review."
  )
}
message(
  if (identical(mode, "--write")) {
    "Wrote deterministic characterization fixtures."
  } else {
    "Characterization fixtures match the legacy reference behavior."
  }
)

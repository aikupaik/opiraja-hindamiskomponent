#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L || !args[[1L]] %in% c("--check", "--write")) {
  stop(
    "Usage: Rscript performance/fixtures/r/generate.R --check|--write"
  )
}
mode <- args[[1L]]

script_arg <- grep("^--file=", commandArgs(), value = TRUE)
script_path <- if (length(script_arg) == 1L) {
  normalizePath(sub("^--file=", "", script_arg), mustWork = TRUE)
} else {
  normalizePath("performance/fixtures/r/generate.R", mustWork = TRUE)
}
fixture_directory <- dirname(script_path)
root <- normalizePath(file.path(fixture_directory, "../../.."), mustWork = TRUE)

Sys.setenv(
  RENV_PROJECT = normalizePath(file.path(root, "R"), mustWork = TRUE),
  RENV_CONFIG_SANDBOX_ENABLED = "FALSE"
)
source(file.path(root, "R", "renv", "activate.R"), local = FALSE)
for (package in c("digest", "jsonlite")) {
  if (!requireNamespace(package, quietly = TRUE)) {
    stop("Missing R package: ", package)
  }
}

options(kst.service.root = file.path(root, "R"))
for (source_file in c(
  "configuration.R", "knowledge_space.R", "model.R", "assessment.R",
  "profile.R", "validation.R", "service.R", "http.R"
)) {
  source(file.path(root, "R", "src", source_file))
}

as_http_value <- function(value) {
  jsonlite::fromJSON(
    serialize_http_json(shape_response_for_json(value)),
    simplifyVector = FALSE
  )
}

make_nodes <- function(count) {
  sprintf("N%02d", seq_len(count))
}

make_chain_relations <- function(nodes) {
  lapply(seq_len(length(nodes) - 1L), function(index) {
    list(from = nodes[[index]], to = nodes[[index + 1L]])
  })
}

make_candidates <- function(shape, nodes) {
  candidates <- list()
  for (node_index in seq_along(nodes)) {
    for (item_index in seq_len(3L)) {
      ordinal <- (node_index - 1L) * 3L + item_index
      candidates[[length(candidates) + 1L]] <- list(
        candidate_id = sprintf(
          "perf-fixture-%s-item-%03d", shape, ordinal
        ),
        node = nodes[[node_index]],
        beta = 0.05,
        eta = 0.25
      )
    }
  }
  candidates
}

make_operation <- function(path, request, response) {
  list(
    method = "POST",
    path = path,
    request = request,
    expected_response = response
  )
}

make_fixture <- function(shape, nodes, relations) {
  model_request <- as_http_value(list(
    nodes = as.list(nodes),
    relations = relations
  ))
  model_response <- as_http_value(create_model_response_v2(model_request))
  candidates <- make_candidates(shape, nodes)

  select_request <- list(
    model = model_response$model,
    posterior = model_response$posterior,
    candidates = candidates
  )
  select_response <- as_http_value(
    select_assessment_candidate_v2(select_request)
  )
  selected_id <- select_response$candidate_id
  selected <- Filter(
    function(candidate) identical(candidate$candidate_id, selected_id),
    candidates
  )
  if (length(selected) != 1L) {
    stop(shape, " select response did not identify exactly one candidate")
  }
  remaining <- Filter(
    function(candidate) !identical(candidate$candidate_id, selected_id),
    candidates
  )

  advance_request <- list(
    model = model_response$model,
    posterior = model_response$posterior,
    administered = selected[[1L]],
    response_correct = TRUE,
    response_count = 1L,
    remaining_candidates = remaining
  )
  advance_response <- as_http_value(advance_assessment_v2(advance_request))
  if (!identical(advance_response$status, "in_progress")) {
    stop(shape, " first-answer advance fixture must remain in progress")
  }

  list(
    fixture_schema_version = 1L,
    shape = shape,
    graph = list(nodes = as.list(nodes), relations = relations),
    candidates_per_node = 3L,
    operations = list(
      model = make_operation(
        "/internal/v2/kst/model", model_request, model_response
      ),
      select = make_operation(
        "/internal/v2/kst/select", select_request, select_response
      ),
      advance = make_operation(
        "/internal/v2/kst/advance", advance_request, advance_response
      )
    )
  )
}

three_nodes <- make_nodes(3L)
ten_nodes <- make_nodes(10L)
fixtures <- list(
  "3-chain.json" = make_fixture(
    "3-chain", three_nodes, make_chain_relations(three_nodes)
  ),
  "10-chain.json" = make_fixture(
    "10-chain", ten_nodes, make_chain_relations(ten_nodes)
  ),
  "10-independent.json" = make_fixture(
    "10-independent", ten_nodes, list()
  )
)

expected_state_counts <- c(
  "3-chain.json" = 4L,
  "10-chain.json" = 11L,
  "10-independent.json" = 1024L
)
for (name in names(fixtures)) {
  state_count <- length(
    fixtures[[name]]$operations$model$expected_response$model$knowledge_states
  )
  if (!identical(state_count, expected_state_counts[[name]])) {
    stop(name, " has an unexpected knowledge-state count: ", state_count)
  }
}

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

if (length(mismatches) > 0L) {
  stop(
    "R performance fixture mismatch: ", paste(mismatches, collapse = "; "),
    ". Review the R behavior before regenerating with --write."
  )
}
message(if (identical(mode, "--write")) {
  "Wrote deterministic R performance fixtures."
} else {
  "R performance fixtures match the production R behavior."
})

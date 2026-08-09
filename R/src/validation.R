new_validation_error <- function(details) {
  structure(
    list(
      message = "Request validation failed.",
      call = NULL,
      details = details
    ),
    class = c("kst_validation_error", "error", "condition")
  )
}

throw_validation <- function(details) {
  if (length(details) > 0L) stop(new_validation_error(details))
  invisible(NULL)
}

detail <- function(field, issue) {
  list(field = field, issue = issue)
}

is_array <- function(value) {
  is.list(value) && is.null(names(value))
}

is_scalar_string <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value)
}

is_scalar_number <- function(value) {
  is.numeric(value) && length(value) == 1L && is.finite(value)
}

is_scalar_integer <- function(value) {
  is_scalar_number(value) && value == floor(value)
}

is_scalar_boolean <- function(value) {
  is.logical(value) && length(value) == 1L && !is.na(value)
}

validate_object_fields <- function(value, field, required, allowed = required) {
  if (!is_json_object(value)) {
    return(list(detail(field, "must be an object")))
  }
  details <- list()
  for (name in setdiff(required, names(value))) {
    details[[length(details) + 1L]] <- detail(
      if (nzchar(field)) paste(field, name, sep = ".") else name,
      "is required"
    )
  }
  for (name in setdiff(names(value), allowed)) {
    details[[length(details) + 1L]] <- detail(
      if (nzchar(field)) paste(field, name, sep = ".") else name,
      "is unknown"
    )
  }
  details
}

parse_json_body <- function(text) {
  if (!is.character(text) || length(text) != 1L || is.na(text)) {
    throw_validation(list(detail("body", "must contain JSON")))
  }
  parsed <- tryCatch(
    jsonlite::fromJSON(text, simplifyVector = FALSE),
    error = function(error) NULL
  )
  if (is.null(parsed)) {
    throw_validation(list(detail("body", "contains malformed JSON")))
  }
  if (!is_json_object(parsed)) {
    throw_validation(list(detail("body", "must be a JSON object")))
  }
  parsed
}

validate_string_array <- function(value, field, non_empty = TRUE,
                                  unique = FALSE) {
  if (!is_array(value) || (non_empty && length(value) == 0L)) {
    return(list(detail(
      field,
      if (non_empty) "must be a non-empty array" else "must be an array"
    )))
  }
  details <- list()
  normalized <- character(length(value))
  for (index in seq_along(value)) {
    path <- sprintf("%s[%d]", field, index)
    if (!is_scalar_string(value[[index]])) {
      details[[length(details) + 1L]] <- detail(path, "must be a string")
    } else if (!nzchar(trimws(value[[index]]))) {
      details[[length(details) + 1L]] <- detail(
        path, "must not be blank"
      )
    } else {
      normalized[[index]] <- value[[index]]
    }
  }
  if (unique && length(details) == 0L && anyDuplicated(normalized)) {
    details[[length(details) + 1L]] <- detail(
      field, "must not contain duplicates"
    )
  }
  details
}

validate_probability_array <- function(value, field, expected_length = NULL,
                                       normalized = FALSE) {
  if (!is_array(value) || length(value) == 0L) {
    return(list(detail(field, "must be a non-empty array")))
  }
  details <- list()
  numbers <- numeric(length(value))
  for (index in seq_along(value)) {
    path <- sprintf("%s[%d]", field, index)
    item <- value[[index]]
    if (!is_scalar_number(item)) {
      details[[length(details) + 1L]] <- detail(
        path, "must be a finite number"
      )
    } else {
      numbers[[index]] <- item
      if (item < 0 || item > 1) {
        details[[length(details) + 1L]] <- detail(
          path, "must be between 0 and 1"
        )
      }
    }
  }
  if (!is.null(expected_length) && length(value) != expected_length) {
    details[[length(details) + 1L]] <- detail(
      field, sprintf("must contain exactly %d values", expected_length)
    )
  }
  if (normalized && length(details) == 0L &&
      abs(sum(numbers) - 1) > 1e-12) {
    details[[length(details) + 1L]] <- detail(
      field, "must sum to 1"
    )
  }
  details
}

validate_relations <- function(value, nodes) {
  if (!is_array(value)) {
    return(list(
      details = list(detail("relations", "must be an array")),
      value = list()
    ))
  }
  details <- list()
  normalized <- vector("list", length(value))
  for (index in seq_along(value)) {
    path <- sprintf("relations[%d]", index)
    relation <- value[[index]]
    current <- validate_object_fields(
      relation, path, c("from", "to")
    )
    details <- c(details, current)
    if (length(current) > 0L) next
    for (field in c("from", "to")) {
      item_path <- paste(path, field, sep = ".")
      endpoint <- relation[[field]]
      if (!is_scalar_string(endpoint)) {
        details[[length(details) + 1L]] <- detail(
          item_path, "must be a string"
        )
      } else if (!nzchar(trimws(endpoint))) {
        details[[length(details) + 1L]] <- detail(
          item_path, "must not be blank"
        )
      } else if (!endpoint %in% nodes) {
        details[[length(details) + 1L]] <- detail(
          item_path, "must reference a declared node"
        )
      }
    }
    normalized[[index]] <- relation
  }
  list(details = details, value = normalized)
}

validate_node_parameters <- function(value, nodes) {
  if (!is_array(value) || length(value) == 0L) {
    return(list(
      details = list(detail("node_parameters", "must be a non-empty array")),
      value = list()
    ))
  }
  details <- list()
  normalized <- vector("list", length(value))
  parameter_nodes <- character(length(value))
  for (index in seq_along(value)) {
    path <- sprintf("node_parameters[%d]", index)
    parameter <- value[[index]]
    current <- validate_object_fields(
      parameter, path, c("node", "beta", "eta")
    )
    details <- c(details, current)
    if (length(current) > 0L) next
    node <- parameter$node
    if (!is_scalar_string(node)) {
      details[[length(details) + 1L]] <- detail(
        paste0(path, ".node"), "must be a string"
      )
    } else if (!node %in% nodes) {
      details[[length(details) + 1L]] <- detail(
        paste0(path, ".node"), "must reference a declared node"
      )
    } else {
      parameter_nodes[[index]] <- node
    }
    for (field in c("beta", "eta")) {
      parameter_value <- parameter[[field]]
      if (!is_scalar_number(parameter_value)) {
        details[[length(details) + 1L]] <- detail(
          paste(path, field, sep = "."), "must be a finite number"
        )
      } else if (parameter_value < 0 || parameter_value > 1) {
        details[[length(details) + 1L]] <- detail(
          paste(path, field, sep = "."), "must be between 0 and 1"
        )
      }
    }
    normalized[[index]] <- list(
      node = node,
      beta = parameter$beta,
      eta = parameter$eta
    )
  }
  if (length(details) == 0L) {
    if (anyDuplicated(parameter_nodes)) {
      details[[length(details) + 1L]] <- detail(
        "node_parameters", "must not contain duplicate nodes"
      )
    }
    missing <- setdiff(nodes, parameter_nodes)
    extra <- setdiff(parameter_nodes, nodes)
    if (length(missing) > 0L) {
      details[[length(details) + 1L]] <- detail(
        "node_parameters", "must contain parameters for every node"
      )
    }
    if (length(extra) > 0L) {
      details[[length(details) + 1L]] <- detail(
        "node_parameters", "contains parameters for an unknown node"
      )
    }
  }
  list(details = details, value = normalized)
}

validate_model_request <- function(request) {
  details <- validate_object_fields(
    request,
    "",
    c("nodes", "relations", "node_parameters"),
    c("nodes", "relations", "node_parameters", "cached_knowledge_states", "configuration")
  )
  if (length(details) > 0L) throw_validation(details)

  details <- validate_string_array(request$nodes, "nodes", unique = TRUE)
  if (length(details) > 0L) throw_validation(details)
  nodes <- unlist(request$nodes, use.names = FALSE)
  relation_result <- validate_relations(request$relations, nodes)
  parameter_result <- validate_node_parameters(request$node_parameters, nodes)
  details <- c(relation_result$details, parameter_result$details)
  relations <- relation_result$value
  if (!is.null(request$cached_knowledge_states)) {
    details <- c(details, validate_knowledge_states(
      request$cached_knowledge_states,
      nodes,
      relations
    ))
  }
  configuration <- NULL
  if (!is.null(request$configuration)) {
    configuration_details <- validate_kst_configuration(request$configuration)
    details <- c(details, configuration_details)
    if (length(configuration_details) == 0L) {
      configuration <- list(
        snapshot = canonicalize_json_value(request$configuration),
        hash = configuration_hash(request$configuration)
      )
    }
  }
  throw_validation(details)
  list(
    nodes = nodes,
    relations = relations,
    node_parameters = parameter_result$value,
    cached_knowledge_states = request$cached_knowledge_states,
    configuration = configuration
  )
}

validate_matrix <- function(value, nodes, states, field = "model.matrix") {
  if (!is_array(value) || length(value) == 0L) {
    return(list(detail(field, "must be a non-empty array")))
  }
  details <- list()
  expected_columns <- length(nodes)
  rows <- vector("list", length(value))
  for (row_index in seq_along(value)) {
    path <- sprintf("%s[%d]", field, row_index)
    row <- value[[row_index]]
    if (!is_array(row)) {
      details[[length(details) + 1L]] <- detail(path, "must be an array")
      next
    }
    if (length(row) != expected_columns) {
      details[[length(details) + 1L]] <- detail(
        path, sprintf("must contain exactly %d values", expected_columns)
      )
      next
    }
    binary <- vapply(row, function(item) {
      is_scalar_integer(item) && item %in% c(0, 1)
    }, logical(1))
    if (!all(binary)) {
      details[[length(details) + 1L]] <- detail(
        path, "must contain only binary integers"
      )
      next
    }
    rows[[row_index]] <- as.integer(unlist(row, use.names = FALSE))
  }
  if (length(value) != length(states)) {
    details[[length(details) + 1L]] <- detail(
      field, "row count must match knowledge_states"
    )
  }
  if (length(details) == 0L) {
    expected <- knowledge_states_matrix(states, nodes)
    actual <- matrix(
      unlist(rows, use.names = FALSE),
      nrow = length(rows),
      byrow = TRUE
    )
    if (!identical(unname(actual), unname(expected))) {
      details[[length(details) + 1L]] <- detail(
        field, "must match knowledge_states and node order"
      )
    }
  }
  details
}

validate_persisted_model <- function(model) {
  required <- c(
    "schema_version", "method", "nodes", "knowledge_states", "matrix",
    "uniform_prior", "beta", "eta", "configuration", "configuration_hash"
  )
  details <- validate_object_fields(model, "model", required)
  if (length(details) > 0L) return(details)
  if (!is_scalar_integer(model$schema_version) || model$schema_version != 1) {
    details[[length(details) + 1L]] <- detail(
      "model.schema_version", "must equal 1"
    )
  }
  if (!is_scalar_string(model$method) || model$method != "kst") {
    details[[length(details) + 1L]] <- detail(
      "model.method", "must equal kst"
    )
  }
  node_details <- validate_string_array(
    model$nodes, "model.nodes", unique = TRUE
  )
  details <- c(details, node_details)
  if (length(node_details) > 0L) return(details)
  nodes <- unlist(model$nodes, use.names = FALSE)
  state_details <- validate_knowledge_states(
    model$knowledge_states, nodes, field = "model.knowledge_states"
  )
  details <- c(details, state_details)
  if (length(state_details) > 0L) return(details)
  states <- lapply(
    model$knowledge_states,
    function(state) as.character(unlist(state, use.names = FALSE))
  )
  details <- c(details, validate_matrix(model$matrix, nodes, states))
  details <- c(details, validate_probability_array(
    model$uniform_prior,
    "model.uniform_prior",
    expected_length = length(states),
    normalized = TRUE
  ))
  details <- c(details, validate_probability_array(
    model$beta, "model.beta", expected_length = length(nodes)
  ))
  details <- c(details, validate_probability_array(
    model$eta, "model.eta", expected_length = length(nodes)
  ))
  config_details <- validate_kst_configuration(model$configuration)
  details <- c(details, config_details)
  if (!is_scalar_string(model$configuration_hash) ||
      !grepl(
        "^kst-config-v1:sha256:[0-9a-f]{64}$",
        model$configuration_hash
      )) {
    details[[length(details) + 1L]] <- detail(
      "model.configuration_hash", "has an unsupported format"
    )
  } else if (length(config_details) == 0L &&
             !identical(
               model$configuration_hash,
               configuration_hash(model$configuration)
             )) {
    details[[length(details) + 1L]] <- detail(
      "model.configuration_hash", "does not match configuration"
    )
  }
  if (length(details) == 0L) {
    prior <- unlist(model$uniform_prior, use.names = FALSE)
    if (max(prior) - min(prior) > 1e-12) {
      details[[length(details) + 1L]] <- detail(
        "model.uniform_prior", "must be uniform"
      )
    }
  }
  details
}

normalize_persisted_model <- function(model) {
  model$schema_version <- as.integer(model$schema_version)
  model$nodes <- unlist(model$nodes, use.names = FALSE)
  model$knowledge_states <- lapply(
    model$knowledge_states,
    function(state) as.character(unlist(state, use.names = FALSE))
  )
  model$matrix <- lapply(model$matrix, function(row) {
    as.integer(unlist(row, use.names = FALSE))
  })
  for (field in c("uniform_prior", "beta", "eta")) {
    model[[field]] <- unname(as.numeric(unlist(
      model[[field]], use.names = FALSE
    )))
  }
  model
}

validate_advance_request <- function(request) {
  required <- c(
    "model", "posterior", "question_node", "response_correct",
    "response_count"
  )
  details <- validate_object_fields(request, "", required)
  if (length(details) > 0L) throw_validation(details)
  model_details <- validate_persisted_model(request$model)
  if (length(model_details) > 0L) throw_validation(model_details)
  model <- normalize_persisted_model(request$model)
  details <- validate_probability_array(
    request$posterior,
    "posterior",
    expected_length = length(model$knowledge_states),
    normalized = TRUE
  )
  if (!is_scalar_string(request$question_node)) {
    details[[length(details) + 1L]] <- detail(
      "question_node", "must be a string"
    )
  } else if (!request$question_node %in% model$nodes) {
    details[[length(details) + 1L]] <- detail(
      "question_node", "must reference a model node"
    )
  }
  if (!is_scalar_boolean(request$response_correct)) {
    details[[length(details) + 1L]] <- detail(
      "response_correct", "must be a boolean"
    )
  }
  if (!is_scalar_integer(request$response_count) ||
      request$response_count < 1) {
    details[[length(details) + 1L]] <- detail(
      "response_count", "must be an integer of at least 1"
    )
  }
  throw_validation(details)
  list(
    model = model,
    posterior = unname(as.numeric(unlist(
      request$posterior, use.names = FALSE
    ))),
    question_node = request$question_node,
    response_correct = request$response_correct,
    response_count = as.integer(request$response_count)
  )
}

validate_model_request_v2 <- function(request) {
  details <- validate_object_fields(
    request,
    "",
    c("nodes", "relations"),
    c("nodes", "relations", "cached_knowledge_states", "configuration")
  )
  if (length(details) > 0L) throw_validation(details)
  details <- validate_string_array(request$nodes, "nodes", unique = TRUE)
  if (length(details) > 0L) throw_validation(details)
  nodes <- unlist(request$nodes, use.names = FALSE)
  relation_result <- validate_relations(request$relations, nodes)
  details <- relation_result$details
  if (!is.null(request$cached_knowledge_states)) {
    details <- c(details, validate_knowledge_states(
      request$cached_knowledge_states,
      nodes,
      relation_result$value
    ))
  }
  configuration <- NULL
  if (!is.null(request$configuration)) {
    configuration_details <- validate_kst_configuration(request$configuration)
    details <- c(details, configuration_details)
    if (length(configuration_details) == 0L) {
      configuration <- list(
        snapshot = canonicalize_json_value(request$configuration),
        hash = configuration_hash(request$configuration)
      )
    }
  }
  throw_validation(details)
  list(
    nodes = nodes,
    relations = relation_result$value,
    cached_knowledge_states = request$cached_knowledge_states,
    configuration = configuration
  )
}

validate_persisted_model_v2 <- function(model) {
  required <- c(
    "schema_version", "method", "nodes", "knowledge_states", "matrix",
    "uniform_prior", "configuration", "configuration_hash",
    "reliability_floor", "safety_cap"
  )
  details <- validate_object_fields(model, "model", required)
  if (length(details) > 0L) return(details)
  if (!is_scalar_integer(model$schema_version) || model$schema_version != 2) {
    details[[length(details) + 1L]] <- detail(
      "model.schema_version", "must equal 2"
    )
  }
  if (!is_scalar_string(model$method) || model$method != "kst") {
    details[[length(details) + 1L]] <- detail(
      "model.method", "must equal kst"
    )
  }
  node_details <- validate_string_array(
    model$nodes, "model.nodes", unique = TRUE
  )
  details <- c(details, node_details)
  if (length(node_details) > 0L) return(details)
  nodes <- unlist(model$nodes, use.names = FALSE)
  state_details <- validate_knowledge_states(
    model$knowledge_states, nodes, field = "model.knowledge_states"
  )
  details <- c(details, state_details)
  if (length(state_details) > 0L) return(details)
  states <- lapply(
    model$knowledge_states,
    function(state) as.character(unlist(state, use.names = FALSE))
  )
  details <- c(details, validate_matrix(model$matrix, nodes, states))
  details <- c(details, validate_probability_array(
    model$uniform_prior,
    "model.uniform_prior",
    expected_length = length(states),
    normalized = TRUE
  ))
  config_details <- validate_kst_configuration(model$configuration)
  details <- c(details, config_details)
  if (!is_scalar_string(model$configuration_hash) ||
      !grepl(
        "^kst-config-v1:sha256:[0-9a-f]{64}$",
        model$configuration_hash
      )) {
    details[[length(details) + 1L]] <- detail(
      "model.configuration_hash", "has an unsupported format"
    )
  } else if (length(config_details) == 0L &&
             !identical(
               model$configuration_hash,
               configuration_hash(model$configuration)
             )) {
    details[[length(details) + 1L]] <- detail(
      "model.configuration_hash", "does not match configuration"
    )
  }
  for (field in c("reliability_floor", "safety_cap")) {
    if (!is_scalar_integer(model[[field]]) || model[[field]] < 0) {
      details[[length(details) + 1L]] <- detail(
        paste0("model.", field), "must be a non-negative integer"
      )
    }
  }
  if (length(config_details) == 0L) {
    expected_floor <- reliability_floor(length(nodes), model$configuration)
    expected_cap <- safety_cap(length(nodes), model$configuration)
    if (!identical(as.integer(model$reliability_floor), expected_floor)) {
      details[[length(details) + 1L]] <- detail(
        "model.reliability_floor", "does not match configuration"
      )
    }
    if (!identical(as.integer(model$safety_cap), expected_cap)) {
      details[[length(details) + 1L]] <- detail(
        "model.safety_cap", "does not match configuration"
      )
    }
  }
  if (length(details) == 0L) {
    prior <- unlist(model$uniform_prior, use.names = FALSE)
    if (max(prior) - min(prior) > 1e-12) {
      details[[length(details) + 1L]] <- detail(
        "model.uniform_prior", "must be uniform"
      )
    }
  }
  details
}

normalize_persisted_model_v2 <- function(model) {
  model$schema_version <- as.integer(model$schema_version)
  model$nodes <- unlist(model$nodes, use.names = FALSE)
  model$knowledge_states <- lapply(
    model$knowledge_states,
    function(state) as.character(unlist(state, use.names = FALSE))
  )
  model$matrix <- lapply(model$matrix, function(row) {
    as.integer(unlist(row, use.names = FALSE))
  })
  model$uniform_prior <- unname(as.numeric(unlist(
    model$uniform_prior, use.names = FALSE
  )))
  model$reliability_floor <- as.integer(model$reliability_floor)
  model$safety_cap <- as.integer(model$safety_cap)
  model
}

validate_candidates_v2 <- function(value, field, nodes, non_empty = TRUE) {
  if (!is_array(value) || (non_empty && length(value) == 0L)) {
    return(list(
      details = list(detail(
        field,
        if (non_empty) "must be a non-empty array" else "must be an array"
      )),
      value = list()
    ))
  }
  details <- list()
  normalized <- vector("list", length(value))
  ids <- character(length(value))
  for (index in seq_along(value)) {
    path <- sprintf("%s[%d]", field, index)
    candidate <- value[[index]]
    current <- validate_object_fields(
      candidate, path, c("candidate_id", "node", "beta", "eta")
    )
    details <- c(details, current)
    if (length(current) > 0L) next
    if (!is_scalar_string(candidate$candidate_id) ||
        !nzchar(trimws(candidate$candidate_id))) {
      details[[length(details) + 1L]] <- detail(
        paste0(path, ".candidate_id"), "must be a nonblank string"
      )
    } else {
      ids[[index]] <- candidate$candidate_id
    }
    if (!is_scalar_string(candidate$node) ||
        !candidate$node %in% nodes) {
      details[[length(details) + 1L]] <- detail(
        paste0(path, ".node"), "must reference a model node"
      )
    }
    for (parameter in c("beta", "eta")) {
      parameter_value <- candidate[[parameter]]
      if (!is_scalar_number(parameter_value) ||
          parameter_value < 0 || parameter_value > 1) {
        details[[length(details) + 1L]] <- detail(
          paste(path, parameter, sep = "."),
          "must be a finite number between 0 and 1"
        )
      }
    }
    normalized[[index]] <- list(
      candidate_id = candidate$candidate_id,
      node = candidate$node,
      beta = candidate$beta,
      eta = candidate$eta
    )
  }
  if (length(details) == 0L && anyDuplicated(ids)) {
    details[[length(details) + 1L]] <- detail(
      field, "must not contain duplicate candidate IDs"
    )
  }
  list(details = details, value = normalized)
}

validate_model_and_posterior_v2 <- function(request) {
  model_details <- validate_persisted_model_v2(request$model)
  if (length(model_details) > 0L) throw_validation(model_details)
  model <- normalize_persisted_model_v2(request$model)
  details <- validate_probability_array(
    request$posterior,
    "posterior",
    expected_length = length(model$knowledge_states),
    normalized = TRUE
  )
  list(model = model, details = details)
}

validate_select_request_v2 <- function(request) {
  required <- c("model", "posterior", "candidates")
  details <- validate_object_fields(request, "", required)
  if (length(details) > 0L) throw_validation(details)
  common <- validate_model_and_posterior_v2(request)
  candidates <- validate_candidates_v2(
    request$candidates, "candidates", common$model$nodes
  )
  throw_validation(c(common$details, candidates$details))
  list(
    model = common$model,
    posterior = unname(as.numeric(unlist(
      request$posterior, use.names = FALSE
    ))),
    candidates = candidates$value
  )
}

validate_advance_request_v2 <- function(request) {
  required <- c(
    "model", "posterior", "administered", "response_correct",
    "response_count", "remaining_candidates"
  )
  details <- validate_object_fields(request, "", required)
  if (length(details) > 0L) throw_validation(details)
  common <- validate_model_and_posterior_v2(request)
  administered <- validate_candidates_v2(
    list(request$administered),
    "administered",
    common$model$nodes
  )
  remaining <- validate_candidates_v2(
    request$remaining_candidates,
    "remaining_candidates",
    common$model$nodes,
    non_empty = FALSE
  )
  details <- c(common$details, administered$details, remaining$details)
  if (length(administered$details) == 0L &&
      length(remaining$details) == 0L &&
      administered$value[[1L]]$candidate_id %in%
        vapply(
          remaining$value,
          `[[`,
          character(1),
          "candidate_id"
        )) {
    details[[length(details) + 1L]] <- detail(
      "remaining_candidates",
      "must not contain the administered candidate"
    )
  }
  if (!is_scalar_boolean(request$response_correct)) {
    details[[length(details) + 1L]] <- detail(
      "response_correct", "must be a boolean"
    )
  }
  if (!is_scalar_integer(request$response_count) ||
      request$response_count < 1) {
    details[[length(details) + 1L]] <- detail(
      "response_count", "must be an integer of at least 1"
    )
  }
  throw_validation(details)
  list(
    model = common$model,
    posterior = unname(as.numeric(unlist(
      request$posterior, use.names = FALSE
    ))),
    administered = administered$value[[1L]],
    response_correct = request$response_correct,
    response_count = as.integer(request$response_count),
    remaining_candidates = remaining$value
  )
}

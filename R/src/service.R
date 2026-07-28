create_model_response <- function(request, configuration_path = NULL) {
  validated <- validate_model_request(request)
  configuration <- if (is.null(configuration_path)) {
    read_kst_configuration()
  } else {
    read_kst_configuration(configuration_path)
  }
  model <- build_kst_model(
    validated$nodes,
    validated$relations,
    validated$node_parameters,
    validated$cached_knowledge_states,
    configuration
  )
  posterior <- model$uniform_prior
  matrix <- model_matrix(model)
  list(
    model = model,
    posterior = posterior,
    next_node = select_half_split_node(posterior, matrix, model$nodes)
  )
}

advance_assessment <- function(request) {
  validated <- validate_advance_request(request)
  model <- validated$model
  matrix <- model_matrix(model)
  question_index <- match(validated$question_node, model$nodes)
  posterior <- update_posterior(
    validated$posterior,
    matrix,
    model$beta,
    model$eta,
    question_index,
    validated$response_correct
  )
  decision <- stopping_decision(
    length(model$nodes),
    posterior,
    validated$response_count,
    model$configuration
  )
  if (decision$completed) {
    return(list(
      status = "completed",
      posterior = posterior,
      profile = build_final_profile(
        posterior,
        model$nodes,
        matrix,
        decision$stop_reason,
        model$configuration$feedback_credible_mass
      )
    ))
  }
  list(
    status = "in_progress",
    posterior = posterior,
    next_node = select_half_split_node(posterior, matrix, model$nodes)
  )
}

create_model_response_v2 <- function(request, configuration_path = NULL) {
  validated <- validate_model_request_v2(request)
  configuration <- if (is.null(configuration_path)) {
    read_kst_configuration()
  } else {
    read_kst_configuration(configuration_path)
  }
  model <- build_kst_model_v2(
    validated$nodes,
    validated$relations,
    validated$cached_knowledge_states,
    configuration
  )
  list(model = model, posterior = model$uniform_prior)
}

select_assessment_candidate_v2 <- function(request) {
  validated <- validate_select_request_v2(request)
  selected <- select_candidate(
    validated$posterior,
    model_matrix(validated$model),
    validated$model$nodes,
    validated$candidates
  )
  list(candidate_id = selected$candidate_id, node = selected$node)
}

advance_assessment_v2 <- function(request) {
  validated <- validate_advance_request_v2(request)
  model <- validated$model
  matrix <- model_matrix(model)
  posterior <- update_posterior_for_candidate(
    validated$posterior,
    matrix,
    validated$administered,
    validated$response_correct
  )
  decision <- stopping_decision(
    length(model$nodes),
    posterior,
    validated$response_count,
    model$configuration
  )
  if (decision$completed || length(validated$remaining_candidates) == 0L) {
    stop_reason <- if (decision$completed) {
      decision$stop_reason
    } else {
      "item_inventory_exhausted"
    }
    profile <- build_final_profile(
      posterior,
      model$nodes,
      matrix,
      stop_reason,
      model$configuration$feedback_credible_mass
    )
    profile$confidence_limited <- stop_reason %in% c(
      "safety_cap", "item_inventory_exhausted"
    )
    return(list(
      status = "completed",
      posterior = posterior,
      profile = profile
    ))
  }
  selected <- select_candidate(
    posterior,
    matrix,
    model$nodes,
    validated$remaining_candidates
  )
  list(
    status = "in_progress",
    posterior = posterior,
    next_candidate = list(
      candidate_id = selected$candidate_id,
      node = selected$node
    )
  )
}

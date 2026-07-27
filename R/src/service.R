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

testthat::test_that("production knowledge spaces match every fixture", {
  fixture <- read_fixture("knowledge_spaces.json", simplify = FALSE)
  for (case in fixture$cases) {
    nodes <- unlist(case$nodes, use.names = FALSE)
    actual <- generate_knowledge_states(nodes, case$relations)
    expected <- lapply(
      case$expected_states,
      function(state) as.character(unlist(state, use.names = FALSE))
    )
    testthat::expect_identical(actual, expected, info = case$id)
  }
})

testthat::test_that("generated and cached production models match fixtures", {
  configuration <- read_kst_configuration()
  expected <- read_fixture("models.json", simplify = TRUE)$generated_model

  for (cached in c(FALSE, TRUE)) {
    request <- validate_model_request(fixture_model_request(cached))
    model <- build_kst_model(
      request$nodes,
      request$relations,
      request$node_parameters,
      request$cached_knowledge_states,
      configuration
    )
    testthat::expect_identical(model$method, expected$method)
    testthat::expect_identical(model$nodes, expected$nodes)
    testthat::expect_identical(
      model$knowledge_states,
      lapply(
        read_fixture("models.json", simplify = FALSE)$generated_model$
          knowledge_states,
        function(state) as.character(unlist(state, use.names = FALSE))
      )
    )
    testthat::expect_identical(
      unname(model_matrix(model)),
      unname(expected$matrix)
    )
    testthat::expect_equal(
      model$uniform_prior, expected$prior, tolerance = 1e-12
    )
    testthat::expect_identical(model$beta, expected$beta)
    testthat::expect_identical(model$eta, expected$eta)
  }
})

testthat::test_that("production adaptive updates match all fixtures", {
  model <- create_model_response(fixture_model_request())$model
  matrix <- model_matrix(model)
  fixture <- read_fixture("adaptive.json", simplify = TRUE)

  for (name in c("correct", "incorrect")) {
    case <- fixture$single_updates[[name]]
    actual <- update_posterior(
      fixture$initial_posterior,
      matrix,
      model$beta,
      model$eta,
      case$question_index,
      case$response_correct
    )
    testthat::expect_equal(
      actual, case$posterior, tolerance = fixture$tolerance
    )
    testthat::expect_null(names(actual))
  }

  posterior <- fixture$initial_posterior
  for (index in seq_len(nrow(fixture$multi_answer_sequence))) {
    step <- fixture$multi_answer_sequence[index, ]
    posterior <- update_posterior(
      posterior,
      matrix,
      model$beta,
      model$eta,
      step$question_index[[1L]],
      step$response_correct[[1L]]
    )
    testthat::expect_equal(
      posterior,
      step$posterior[[1L]],
      tolerance = fixture$tolerance
    )
  }
  tie <- fixture$half_split_tie
  testthat::expect_identical(
    select_half_split_node(tie$posterior, matrix, model$nodes),
    tie$allowed_nodes[[1L]]
  )
})

testthat::test_that("production stopping decisions match boundaries", {
  configuration <- read_kst_configuration()$snapshot
  fixture <- read_fixture("stopping.json", simplify = TRUE)
  for (index in seq_len(nrow(fixture$cases))) {
    case <- fixture$cases[index, ]
    posterior <- c(
      case$confidence,
      rep(
        (1 - case$confidence) / (case$node_count - 1),
        max(case$node_count - 1, 0)
      )
    )
    if (case$node_count == 1L) posterior <- case$confidence
    actual <- stopping_decision(
      case$node_count,
      posterior,
      case$response_count,
      configuration
    )
    testthat::expect_identical(actual$completed, case$completed)
    expected_reason <- case$stop_reason
    if (is.na(expected_reason)) expected_reason <- NULL
    testthat::expect_identical(actual$stop_reason, expected_reason)
  }
})

testthat::test_that("production final profiles match all fixtures", {
  profiles <- read_fixture("profiles.json", simplify = FALSE)
  spaces <- read_fixture("knowledge_spaces.json", simplify = FALSE)
  spaces <- setNames(
    spaces$cases,
    vapply(spaces$cases, `[[`, character(1), "id")
  )
  for (case in profiles$cases) {
    space_name <- if (case$model_case == "three_node_fork") {
      "three_node_fork"
    } else {
      "three_node_chain"
    }
    nodes <- c("A", "B", "C")
    states <- lapply(
      spaces[[space_name]]$expected_states,
      function(state) as.character(unlist(state, use.names = FALSE))
    )
    actual <- build_final_profile(
      unlist(case$posterior, use.names = FALSE),
      nodes,
      knowledge_states_matrix(states, nodes),
      case$expected$stop_reason,
      profiles$credible_mass_threshold
    )
    for (field in c(
      "mastered", "ready_to_learn", "uncertain_ahead",
      "uncertain_prerequisite", "not_yet"
    )) {
      testthat::expect_identical(
        actual[[field]],
        as.character(unlist(case$expected[[field]], use.names = FALSE)),
        info = paste(case$id, field)
      )
    }
    for (field in c(
      "summary", "stop_reason", "best_state_confidence",
      "credible_mass", "credible_state_count"
    )) {
      testthat::expect_equal(
        actual[[field]], case$expected[[field]], tolerance = 1e-12,
        info = paste(case$id, field)
      )
    }
  }
})

testthat::test_that("active assessments use embedded configuration", {
  request <- fixture_model_request()
  response <- create_model_response(request)
  altered <- jsonlite::fromJSON(
    serialize_http_json(shape_model_for_json(response$model)),
    simplifyVector = FALSE
  )
  altered$configuration$stop_confidence <- 1
  altered$configuration_hash <- configuration_hash(altered$configuration)
  advance <- list(
    model = altered,
    posterior = as.list(c(0.02, 0.02, 0.02, 0.94)),
    question_node = "C",
    response_correct = TRUE,
    response_count = 7L
  )
  result <- advance_assessment(advance)
  testthat::expect_identical(result$status, "in_progress")
})

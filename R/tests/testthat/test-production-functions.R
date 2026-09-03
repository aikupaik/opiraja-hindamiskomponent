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

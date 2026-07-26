testthat::test_that("knowledge-space states and ordering are frozen", {
  fixture <- read_fixture("knowledge_spaces.json", simplify = FALSE)
  cases <- setNames(fixture$cases, vapply(
    fixture$cases, `[[`, character(1), "id"
  ))
  expected_chain <- list(
    list(), list("A"), list("A", "B"), list("A", "B", "C")
  )
  expected_fork <- list(
    list(), list("A"), list("A", "B"), list("A", "C"),
    list("A", "B", "C")
  )
  expected_independent <- list(
    list(), list("A"), list("B"), list("C"), list("A", "B"),
    list("A", "C"), list("B", "C"), list("A", "B", "C")
  )

  testthat::expect_identical(
    cases$three_node_chain$expected_states, expected_chain
  )
  testthat::expect_identical(
    cases$three_node_fork$expected_states, expected_fork
  )
  testthat::expect_identical(
    cases$three_independent_nodes$expected_states, expected_independent
  )
  testthat::expect_identical(
    cases$chain_with_redundant_transitive_relation$expected_states,
    expected_chain
  )
})

testthat::test_that("model order, dimensions, priors, and parameters align", {
  fixture <- read_fixture("models.json", simplify = TRUE)
  model <- fixture$generated_model
  cached <- fixture$cached_model

  testthat::expect_identical(model$nodes, c("A", "B", "C"))
  testthat::expect_identical(dim(model$matrix), c(4L, 3L))
  testthat::expect_identical(
    unname(model$matrix),
    matrix(c(
      0L, 0L, 0L,
      1L, 0L, 0L,
      1L, 1L, 0L,
      1L, 1L, 1L
    ), nrow = 4L, byrow = TRUE)
  )
  expect_probability_vector(model$prior, 4L)
  testthat::expect_equal(model$prior, rep(0.25, 4L), tolerance = 1e-12)
  testthat::expect_identical(model$beta, c(0.1, 0.15, 0.2))
  testthat::expect_identical(model$eta, c(0.2, 0.25, 0.3))
  testthat::expect_identical(model, cached)
  testthat::expect_true(fixture$generated_equals_cached)
  testthat::expect_true(fixture$initial_half_split$unique_optimum)
  testthat::expect_identical(fixture$initial_half_split$allowed_nodes, "B")
  testthat::expect_identical(fixture$initial_half_split$selected_node, "B")
})

testthat::test_that("Bayesian fixtures preserve posterior invariants", {
  fixture <- read_fixture("adaptive.json", simplify = TRUE)
  expected_length <- fixture$posterior_invariants$length
  posteriors <- c(
    list(fixture$single_updates$correct$posterior),
    list(fixture$single_updates$incorrect$posterior),
    fixture$multi_answer_sequence$posterior
  )

  for (posterior in posteriors) {
    expect_probability_vector(posterior, expected_length, fixture$tolerance)
    testthat::expect_null(names(posterior))
  }
  testthat::expect_false(isTRUE(all.equal(
    fixture$single_updates$correct$posterior,
    fixture$single_updates$incorrect$posterior,
    tolerance = fixture$tolerance
  )))
  testthat::expect_identical(
    fixture$half_split_tie$allowed_nodes,
    c("A", "B", "C")
  )
})

testthat::test_that("stopping boundaries and natural precedence are frozen", {
  fixture <- read_fixture("stopping.json", simplify = TRUE)
  expected_bounds <- data.frame(
    node_count = c(1L, 4L, 5L, 7L, 10L),
    reliability_floor = c(7L, 7L, 8L, 10L, 10L),
    safety_cap = c(8L, 8L, 10L, 14L, 20L)
  )
  rows <- fixture$cases
  actual_bounds <- unique(rows[
    c("node_count", "reliability_floor", "safety_cap")
  ])
  rownames(actual_bounds) <- NULL

  testthat::expect_identical(actual_bounds, expected_bounds)
  simultaneous <- rows[rows$label == "natural_and_cap_simultaneous", ]
  testthat::expect_true(all(simultaneous$completed))
  testthat::expect_true(all(simultaneous$stop_reason == "natural"))
  at_floor <- rows[rows$label == "at_confidence_at_floor", ]
  testthat::expect_true(all(at_floor$completed))
  testthat::expect_true(all(at_floor$stop_reason == "natural"))
  below_floor <- rows[rows$label == "at_confidence_below_floor", ]
  testthat::expect_true(all(!below_floor$completed))
})

testthat::test_that("final profiles map all reachable legacy categories", {
  fixture <- read_fixture("profiles.json", simplify = FALSE)
  cases <- setNames(fixture$cases, vapply(
    fixture$cases, `[[`, character(1), "id"
  ))
  categories <- c(
    "mastered", "ready_to_learn", "uncertain_ahead",
    "uncertain_prerequisite", "not_yet"
  )

  for (case in cases) {
    testthat::expect_named(case$expected, c(
      categories, "summary", "stop_reason", "best_state_confidence",
      "credible_mass", "credible_state_count"
    ))
    testthat::expect_true(
      case$expected$credible_mass + 1e-12 >= fixture$credible_mass_threshold
    )
    testthat::expect_identical(
      length(case$credible_state_indices),
      case$expected$credible_state_count
    )
    testthat::expect_identical(
      case$expected$uncertain_prerequisite,
      list()
    )
  }
  testthat::expect_identical(
    cases$single_credible_state$expected$mastered, list("A")
  )
  testthat::expect_identical(
    cases$single_credible_state$expected$ready_to_learn, list("B")
  )
  testthat::expect_identical(
    cases$single_credible_state$expected$not_yet, list("C")
  )
  testthat::expect_identical(
    cases$multiple_credible_states$expected$uncertain_ahead,
    list("B", "C")
  )
  testthat::expect_identical(
    cases$all_mastered$expected$mastered,
    list("A", "B", "C")
  )
  testthat::expect_identical(
    cases$multiple_next_directions$expected$ready_to_learn,
    list("B", "C")
  )
  testthat::expect_identical(
    cases$safety_cap$expected$stop_reason, "safety_cap"
  )
})

testthat::test_that("credible states use the smallest descending prefix to 0.9", {
  fixture <- read_fixture("profiles.json", simplify = TRUE)

  for (index in seq_len(nrow(fixture$cases))) {
    posterior <- fixture$cases$posterior[[index]]
    actual <- fixture$cases$credible_state_indices[[index]]
    order_desc <- order(posterior, decreasing = TRUE)
    count <- which(cumsum(posterior[order_desc]) >= 0.9)[1]
    expected <- order_desc[seq_len(count)]
    testthat::expect_identical(as.integer(actual), as.integer(expected))
    if (count > 1) {
      testthat::expect_lt(
        sum(posterior[order_desc[seq_len(count - 1L)]]),
        0.9
      )
    }
  }
})

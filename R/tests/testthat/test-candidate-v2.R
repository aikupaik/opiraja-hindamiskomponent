v2_request <- function() {
  list(
    nodes = list("A", "B"),
    relations = list(list(from = "A", to = "B"))
  )
}

v2_candidates <- function() {
  list(
    list(candidate_id = "yp:1", node = "A", beta = 0.05, eta = 0.25),
    list(candidate_id = "yp:2", node = "B", beta = 0.15, eta = 0.35)
  )
}

v2_built_json <- function() {
  built <- create_model_response_v2(v2_request())
  built$model$nodes <- as.list(built$model$nodes)
  built$model$knowledge_states <- lapply(
    built$model$knowledge_states, as.list
  )
  built$model$matrix <- lapply(built$model$matrix, as.list)
  built$model$uniform_prior <- as.list(built$model$uniform_prior)
  built$posterior <- as.list(built$posterior)
  built
}

testthat::test_that("v2 model exposes derived limits without item vectors", {
  response <- create_model_response_v2(v2_request())
  testthat::expect_identical(response$model$schema_version, 2L)
  testthat::expect_identical(response$model$reliability_floor, 7L)
  testthat::expect_identical(response$model$safety_cap, 8L)
  testthat::expect_false("beta" %in% names(response$model))
  testthat::expect_false("eta" %in% names(response$model))
  testthat::expect_identical(response$posterior, response$model$uniform_prior)
})

testthat::test_that("v2 selection excludes depleted nodes and preserves ties", {
  built <- v2_built_json()
  only_b <- list(v2_candidates()[[2L]])
  selected <- select_assessment_candidate_v2(list(
    model = built$model,
    posterior = built$posterior,
    candidates = only_b
  ))
  testthat::expect_identical(selected$candidate_id, "yp:2")
  tied <- list(
    list(candidate_id = "yp:first", node = "A", beta = 0.1, eta = 0.2),
    list(candidate_id = "yp:second", node = "A", beta = 0.2, eta = 0.3)
  )
  selected_tie <- select_assessment_candidate_v2(list(
    model = built$model,
    posterior = built$posterior,
    candidates = tied
  ))
  testthat::expect_identical(selected_tie$candidate_id, "yp:first")
})

testthat::test_that("v2 uses concrete parameters and exhausts explicitly", {
  built <- v2_built_json()
  request <- list(
    model = built$model,
    posterior = built$posterior,
    administered = v2_candidates()[[1L]],
    response_correct = TRUE,
    response_count = 1L,
    remaining_candidates = list()
  )
  result <- advance_assessment_v2(request)
  testthat::expect_identical(result$status, "completed")
  testthat::expect_identical(
    result$profile$stop_reason, "item_inventory_exhausted"
  )
  testthat::expect_true(result$profile$confidence_limited)

  changed <- request
  changed$administered$beta <- 0.4
  changed$administered$eta <- 0.4
  changed_result <- advance_assessment_v2(changed)
  testthat::expect_false(isTRUE(all.equal(
    result$posterior, changed_result$posterior
  )))
})

testthat::test_that("v2 rejects foreign and duplicate candidates", {
  built <- v2_built_json()
  duplicate <- v2_candidates()
  duplicate[[2L]]$candidate_id <- duplicate[[1L]]$candidate_id
  testthat::expect_error(
    select_assessment_candidate_v2(list(
      model = built$model,
      posterior = built$posterior,
      candidates = duplicate
    )),
    class = "kst_validation_error"
  )
  foreign <- v2_candidates()
  foreign[[1L]]$node <- "foreign"
  testthat::expect_error(
    select_assessment_candidate_v2(list(
      model = built$model,
      posterior = built$posterior,
      candidates = foreign
    )),
    class = "kst_validation_error"
  )
})

testthat::test_that("v2 OpenAPI declares exactly three candidate operations", {
  contract <- jsonlite::fromJSON(
    file.path(test_root, "R", "contracts", "internal-kst-v2.openapi.json"),
    simplifyVector = FALSE
  )
  testthat::expect_setequal(
    names(contract$paths),
    c(
      "/internal/v2/kst/model",
      "/internal/v2/kst/select",
      "/internal/v2/kst/advance"
    )
  )
})

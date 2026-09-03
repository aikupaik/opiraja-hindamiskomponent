testthat::test_that("cached-state validation rejects structural corruption", {
  nodes <- list("A", "B", "C")
  states <- list(list(), list("A"), list("A", "B"), list("A", "B", "C"))
  relations <- list(list(from = "A", to = "B"), list(from = "B", to = "C"))
  corruptions <- list(
    duplicate_member = function(value) {
      value[[2L]] <- list("A", "A")
      value
    },
    duplicate_state = function(value) {
      value[[3L]] <- value[[2L]]
      value
    },
    missing_empty = function(value) value[-1L],
    relation_violation = function(value) {
      value[[2L]] <- list("B")
      value
    },
    wrong_order = function(value) {
      value[[3L]] <- list("B", "A")
      value
    }
  )
  for (name in names(corruptions)) {
    testthat::expect_gt(
      validate_knowledge_states(corruptions[[name]](states), nodes, relations),
      0L,
      info = name
    )
  }
})

testthat::test_that("canonical state ordering is checked without subset ranks", {
  nodes <- c("A", "B", "C")
  ordered <- list(
    character(), "A", "B", "C", c("A", "B"), c("A", "C"),
    c("B", "C"), nodes
  )
  out_of_order <- ordered
  out_of_order[[5L]] <- c("A", "C")
  out_of_order[[6L]] <- c("A", "B")

  testthat::expect_true(states_follow_canonical_order(ordered, nodes))
  testthat::expect_false(states_follow_canonical_order(out_of_order, nodes))

  validation_environment <- environment(validate_knowledge_states)
  original_generator <- get(
    "generate_knowledge_states", envir = validation_environment
  )
  assign(
    "generate_knowledge_states",
    function(...) stop("subset generation should not be needed"),
    envir = validation_environment
  )
  on.exit(assign(
    "generate_knowledge_states", original_generator,
    envir = validation_environment
  ), add = TRUE)
  testthat::expect_identical(
    validate_knowledge_states(lapply(ordered, as.list), nodes),
    list()
  )
})

testthat::test_that("manual JSON parsing has stable malformed envelope", {
  testthat::expect_error(
    parse_json_body("{"),
    class = "kst_validation_error"
  )
  error <- tryCatch(
    parse_json_body("[]"),
    kst_validation_error = identity
  )
  testthat::expect_identical(
    error$details,
    list(detail("body", "must be a JSON object"))
  )
})

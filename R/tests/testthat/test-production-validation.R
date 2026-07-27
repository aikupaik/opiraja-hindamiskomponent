testthat::test_that("model validation rejects malformed request categories", {
  cases <- list(
    list(
      request = list(relations = list(), node_parameters = list()),
      expected = detail("nodes", "is required")
    ),
    list(
      request = list(
        nodes = list("A", "A"),
        relations = list(),
        node_parameters = list()
      ),
      expected = detail("nodes", "must not contain duplicates")
    ),
    list(
      request = list(
        nodes = list(" "),
        relations = list(),
        node_parameters = list()
      ),
      expected = detail("nodes[1]", "must not be blank")
    ),
    list(
      request = list(
        nodes = list("A"),
        relations = list(list(from = "A", to = "B")),
        node_parameters = list(list(node = "A", beta = 0.1, eta = 0.2))
      ),
      expected = detail(
        "relations[1].to", "must reference a declared node"
      )
    ),
    list(
      request = list(
        nodes = list("A"),
        relations = list(),
        node_parameters = list(list(node = "A", beta = Inf, eta = 0.2))
      ),
      expected = detail(
        "node_parameters[1].beta", "must be a finite number"
      )
    )
  )
  for (case in cases) {
    error <- tryCatch(
      {
        validate_model_request(case$request)
        NULL
      },
      kst_validation_error = identity
    )
    testthat::expect_s3_class(error, "kst_validation_error")
    testthat::expect_identical(error$details[[1L]], case$expected)
  }
})

testthat::test_that("cached-state validation rejects structural corruption", {
  base <- fixture_model_request(TRUE)
  corruptions <- list(
    duplicate_member = function(value) {
      value$cached_knowledge_states[[2L]] <- list("A", "A")
      value
    },
    duplicate_state = function(value) {
      value$cached_knowledge_states[[3L]] <-
        value$cached_knowledge_states[[2L]]
      value
    },
    missing_empty = function(value) {
      value$cached_knowledge_states <- value$cached_knowledge_states[-1L]
      value
    },
    relation_violation = function(value) {
      value$cached_knowledge_states[[2L]] <- list("B")
      value
    },
    wrong_order = function(value) {
      value$cached_knowledge_states[[3L]] <- list("B", "A")
      value
    }
  )
  for (name in names(corruptions)) {
    testthat::expect_error(
      validate_model_request(corruptions[[name]](base)),
      class = "kst_validation_error",
      info = name
    )
  }
})

testthat::test_that("persisted model validation rejects inconsistent data", {
  response <- create_model_response(fixture_model_request())
  model <- jsonlite::fromJSON(
    serialize_http_json(shape_model_for_json(response$model)),
    simplifyVector = FALSE
  )
  valid <- list(
    model = model,
    posterior = as.list(response$posterior),
    question_node = response$next_node,
    response_correct = TRUE,
    response_count = 1L
  )
  testthat::expect_no_error(validate_advance_request(valid))

  corruptions <- list(
    schema = function(value) {
      value$model$schema_version <- 2L
      value
    },
    ragged = function(value) {
      value$model$matrix[[1L]] <- list(0L)
      value
    },
    non_binary = function(value) {
      value$model$matrix[[1L]][[1L]] <- 2L
      value
    },
    probability = function(value) {
      value$posterior[[1L]] <- 0.5
      value
    },
    hash = function(value) {
      value$model$configuration_hash <- paste0(
        "kst-config-v1:sha256:", paste(rep("0", 64), collapse = "")
      )
      value
    },
    question = function(value) {
      value$question_node <- "unknown"
      value
    },
    count = function(value) {
      value$response_count <- 0L
      value
    }
  )
  for (name in names(corruptions)) {
    testthat::expect_error(
      validate_advance_request(corruptions[[name]](valid)),
      class = "kst_validation_error",
      info = name
    )
  }
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

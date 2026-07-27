testthat::test_that("router exposes exact contract paths", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  router <- environment$create_kst_router()
  route_paths <- function(value) {
    if (inherits(value, "PlumberEndpoint")) return(value$path)
    unlist(lapply(value, route_paths), use.names = FALSE)
  }
  actual <- route_paths(router$routes)
  contract <- jsonlite::fromJSON(
    file.path(
      test_root, "R", "contracts", "internal-kst-v1.openapi.json"
    ),
    simplifyVector = FALSE
  )
  testthat::expect_setequal(unique(actual), names(contract$paths))
  testthat::expect_identical(
    names(router$getApiSpec()$paths),
    names(contract$paths)
  )
})

testthat::test_that("health is dependency-free and JSON shaped", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  old_root <- getOption("kst.service.root")
  on.exit(options(kst.service.root = old_root), add = TRUE)
  options(kst.service.root = tempfile("missing-kst-config-"))
  router <- environment$create_kst_router(
    model_operation = function(request) stop("must not run"),
    advance_operation = function(request) stop("must not run")
  )
  response <- router$call(mock_http_request("GET", "/health"))
  testthat::expect_identical(response$status, 200L)
  testthat::expect_identical(
    response$headers$`Content-Type`[[1L]], "application/json"
  )
  testthat::expect_identical(
    jsonlite::fromJSON(response$body)$status, "ok"
  )
})

testthat::test_that("model and advance routes preserve JSON arrays", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  router <- environment$create_kst_router()
  request <- fixture_model_request()
  body <- jsonlite::toJSON(
    request, auto_unbox = TRUE, null = "null", digits = NA
  )
  response <- router$call(mock_http_request(
    "POST", "/internal/v1/kst/model", body
  ))
  testthat::expect_identical(response$status, 200L)
  parsed <- jsonlite::fromJSON(response$body, simplifyVector = FALSE)
  testthat::expect_true(is.list(parsed$model$nodes))
  testthat::expect_true(is.list(parsed$model$knowledge_states[[1L]]))
  testthat::expect_true(is.list(parsed$model$matrix[[1L]]))
  testthat::expect_true(is.list(parsed$model$uniform_prior))

  advance <- list(
    model = parsed$model,
    posterior = parsed$posterior,
    question_node = parsed$next_node,
    response_correct = TRUE,
    response_count = 1L
  )
  advance_response <- router$call(mock_http_request(
    "POST",
    "/internal/v1/kst/advance",
    jsonlite::toJSON(
      advance, auto_unbox = TRUE, null = "null", digits = NA
    )
  ))
  testthat::expect_identical(advance_response$status, 200L)
  parsed_advance <- jsonlite::fromJSON(
    advance_response$body, simplifyVector = FALSE
  )
  testthat::expect_identical(parsed_advance$status, "in_progress")
  testthat::expect_true(is.list(parsed_advance$posterior))

  completed <- list(
    model = parsed$model,
    posterior = as.list(c(0.02, 0.02, 0.02, 0.94)),
    question_node = "C",
    response_correct = TRUE,
    response_count = 7L
  )
  completed_response <- router$call(mock_http_request(
    "POST",
    "/internal/v1/kst/advance",
    jsonlite::toJSON(
      completed, auto_unbox = TRUE, null = "null", digits = NA
    )
  ))
  testthat::expect_identical(completed_response$status, 200L)
  parsed_completed <- jsonlite::fromJSON(
    completed_response$body, simplifyVector = FALSE
  )
  testthat::expect_identical(parsed_completed$status, "completed")
  testthat::expect_true(is.list(parsed_completed$profile$mastered))
  testthat::expect_true(
    is.list(parsed_completed$profile$ready_to_learn)
  )
})

testthat::test_that("router returns exact 422 and redacted 500 envelopes", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  router <- environment$create_kst_router()
  invalid <- router$call(mock_http_request(
    "POST", "/internal/v1/kst/model", "{"
  ))
  testthat::expect_identical(invalid$status, 422L)
  invalid_body <- jsonlite::fromJSON(invalid$body)
  testthat::expect_identical(
    invalid_body$error$code, "validation_error"
  )
  testthat::expect_identical(
    invalid_body$error$details$field, "body"
  )

  failing <- environment$create_kst_router(
    model_operation = function(request) {
      stop("secret calculation detail")
    }
  )
  unexpected <- failing$call(mock_http_request(
    "POST",
    "/internal/v1/kst/model",
    jsonlite::toJSON(
      fixture_model_request(),
      auto_unbox = TRUE,
      null = "null",
      digits = NA
    )
  ))
  testthat::expect_identical(unexpected$status, 500L)
  testthat::expect_false(grepl("secret", unexpected$body, fixed = TRUE))
  testthat::expect_identical(
    jsonlite::fromJSON(unexpected$body)$error$code,
    "internal_error"
  )
})

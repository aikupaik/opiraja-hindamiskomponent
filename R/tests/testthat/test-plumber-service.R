testthat::test_that("router exposes the v2 contract paths", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  router <- environment$create_kst_router()
  route_paths <- function(value) {
    if (inherits(value, "PlumberEndpoint")) return(value$path)
    unlist(lapply(value, route_paths), use.names = FALSE)
  }
  contract <- jsonlite::fromJSON(
    file.path(test_root, "R", "contracts", "internal-kst-v2.openapi.json"),
    simplifyVector = FALSE
  )
  expected <- c("/health", names(contract$paths))
  testthat::expect_setequal(unique(route_paths(router$routes)), expected)
  testthat::expect_setequal(names(router$getApiSpec()$paths), expected)
})

testthat::test_that("health is dependency-free and JSON shaped", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  router <- environment$create_kst_router()
  response <- router$call(mock_http_request("GET", "/health"))
  testthat::expect_identical(response$status, 200L)
  testthat::expect_identical(
    response$headers$`Content-Type`[[1L]], "application/json"
  )
  testthat::expect_match(
    response$headers$`X-Request-ID`[[1L]],
    "^r-[A-Za-z0-9.-]+$"
  )
  testthat::expect_identical(jsonlite::fromJSON(response$body)$status, "ok")
})

testthat::test_that("health success logging is suppressed", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  router <- environment$create_kst_router()
  output <- capture.output({
    response <- router$call(mock_http_request("GET", "/health"))
  })
  testthat::expect_identical(response$status, 200L)
  testthat::expect_length(output, 0L)
})

testthat::test_that("log level configuration is validated", {
  previous <- Sys.getenv("APP_LOG_LEVEL", unset = NA_character_)
  on.exit({
    if (is.na(previous)) {
      Sys.unsetenv("APP_LOG_LEVEL")
    } else {
      Sys.setenv(APP_LOG_LEVEL = previous)
    }
  })
  Sys.setenv(APP_LOG_LEVEL = "verbose")
  environment <- new.env(parent = globalenv())
  testthat::expect_error(
    sys.source(file.path(test_root, "R", "plumber.R"), envir = environment),
    "APP_LOG_LEVEL must be DEBUG, INFO, WARNING, or ERROR"
  )
})

testthat::test_that("request logs are correlated structured completion events", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  router <- environment$create_kst_router()
  body <- jsonlite::toJSON(
    list(nodes = list("A", "B"), relations = list()),
    auto_unbox = TRUE,
    null = "null"
  )
  output <- capture.output({
    response <- router$call(mock_http_request(
      "POST",
      "/internal/v2/kst/model",
      body,
      request_id = "request.safe-123"
    ))
  })
  testthat::expect_length(output, 1L)
  event <- jsonlite::fromJSON(output[[1L]], simplifyVector = FALSE)
  testthat::expect_identical(event$schema_version, 1L)
  testthat::expect_identical(event$level, "INFO")
  testthat::expect_identical(event$service, "r-service")
  testthat::expect_identical(event$event, "request_completed")
  testthat::expect_identical(event$request_id, "request.safe-123")
  testthat::expect_identical(event$method, "POST")
  testthat::expect_identical(event$path, "/internal/v2/kst/model")
  testthat::expect_identical(event$status, 200L)
  testthat::expect_true(is.numeric(event$duration_ms))
  testthat::expect_identical(
    response$headers$`X-Request-ID`[[1L]],
    "request.safe-123"
  )
})

testthat::test_that("unsafe request IDs are replaced", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  router <- environment$create_kst_router()
  output <- capture.output({
    response <- router$call(mock_http_request(
      "POST",
      "/internal/v2/kst/model",
      "{",
      request_id = "unsafe request id"
    ))
  })
  event <- jsonlite::fromJSON(output[[1L]], simplifyVector = FALSE)
  generated <- response$headers$`X-Request-ID`[[1L]]
  testthat::expect_match(generated, "^r-[A-Za-z0-9.-]+$")
  testthat::expect_identical(event$request_id, generated)
  testthat::expect_identical(event$level, "WARNING")
  testthat::expect_identical(event$status, 422L)
  testthat::expect_false(grepl("unsafe request id", output[[1L]], fixed = TRUE))
})

testthat::test_that("v2 model route preserves JSON arrays", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  router <- environment$create_kst_router()
  body <- jsonlite::toJSON(
    list(
      nodes = list("A", "B"),
      relations = list(list(from = "A", to = "B"))
    ),
    auto_unbox = TRUE,
    null = "null",
    digits = NA
  )
  response <- router$call(mock_http_request(
    "POST", "/internal/v2/kst/model", body
  ))
  testthat::expect_identical(response$status, 200L)
  parsed <- jsonlite::fromJSON(response$body, simplifyVector = FALSE)
  testthat::expect_identical(parsed$model$schema_version, 2L)
  testthat::expect_true(is.list(parsed$model$nodes))
  testthat::expect_true(is.list(parsed$model$knowledge_states[[1L]]))
  testthat::expect_true(is.list(parsed$model$matrix[[1L]]))
  testthat::expect_true(is.list(parsed$model$uniform_prior))
})

testthat::test_that("router returns exact 422 and redacted 500 envelopes", {
  environment <- new.env(parent = globalenv())
  sys.source(file.path(test_root, "R", "plumber.R"), envir = environment)
  router <- environment$create_kst_router()
  invalid <- router$call(mock_http_request(
    "POST", "/internal/v2/kst/model", "{"
  ))
  testthat::expect_identical(invalid$status, 422L)
  invalid_body <- jsonlite::fromJSON(invalid$body)
  testthat::expect_identical(invalid_body$error$code, "validation_error")
  testthat::expect_identical(invalid_body$error$details$field, "body")

  failing <- environment$create_kst_router(
    model_operation_v2 = function(request) stop("secret calculation detail")
  )
  failure_logs <- capture.output({
    unexpected <- failing$call(mock_http_request(
      "POST",
      "/internal/v2/kst/model",
      jsonlite::toJSON(
        list(nodes = list("A"), relations = list()),
        auto_unbox = TRUE,
        null = "null",
        digits = NA
      ),
      request_id = "failed-request-123"
    ))
  })
  testthat::expect_identical(unexpected$status, 500L)
  testthat::expect_false(grepl("secret", unexpected$body, fixed = TRUE))
  testthat::expect_identical(
    jsonlite::fromJSON(unexpected$body)$error$code,
    "internal_error"
  )
  testthat::expect_length(failure_logs, 2L)
  failure_events <- lapply(
    failure_logs,
    jsonlite::fromJSON,
    simplifyVector = FALSE
  )
  testthat::expect_identical(
    vapply(failure_events, `[[`, character(1L), "event"),
    c("unhandled_request_exception", "request_completed")
  )
  testthat::expect_true(all(vapply(
    failure_events,
    function(event) identical(event$request_id, "failed-request-123"),
    logical(1L)
  )))
  testthat::expect_false(any(grepl("secret", failure_logs, fixed = TRUE)))
})

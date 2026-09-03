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
  testthat::expect_identical(jsonlite::fromJSON(response$body)$status, "ok")
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
  unexpected <- failing$call(mock_http_request(
    "POST",
    "/internal/v2/kst/model",
    jsonlite::toJSON(
      list(nodes = list("A"), relations = list()),
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

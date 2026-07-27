test_root <- normalizePath("../../..", mustWork = TRUE)
source(file.path(test_root, "R", "tests", "reference", "harness.R"))
characterization_use_local_library(test_root)
options(kst.service.root = file.path(test_root, "R"))
for (source_file in c(
  "configuration.R", "knowledge_space.R", "model.R", "assessment.R",
  "profile.R", "validation.R", "service.R", "http.R"
)) {
  source(file.path(test_root, "R", "src", source_file))
}

fixture_path <- function(name) {
  file.path(test_root, "R", "tests", "fixtures", name)
}

read_fixture <- function(name, simplify = FALSE) {
  jsonlite::fromJSON(
    fixture_path(name),
    simplifyVector = simplify,
    simplifyDataFrame = simplify,
    simplifyMatrix = simplify
  )
}

as_atomic <- function(value) {
  unname(unlist(value, use.names = FALSE))
}

expect_probability_vector <- function(value, expected_length,
                                      tolerance = 1e-12) {
  vector <- as.numeric(as_atomic(value))
  testthat::expect_length(vector, expected_length)
  testthat::expect_true(all(vector >= 0))
  testthat::expect_equal(sum(vector), 1, tolerance = tolerance)
}

fixture_model_request <- function(cached = FALSE) {
  fixture <- read_fixture("models.json", simplify = FALSE)$input
  fixture$node_parameters <- lapply(fixture$node_parameters, function(value) {
    value$item_id <- NULL
    value
  })
  if (cached) {
    fixture$cached_knowledge_states <-
      read_fixture("models.json", simplify = FALSE)$cached_model$
        knowledge_states
  }
  fixture
}

as_json_request <- function(value) {
  jsonlite::fromJSON(
    jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA),
    simplifyVector = FALSE
  )
}

mock_http_request <- function(method, path, body = NULL) {
  req <- new.env(parent = globalenv())
  req$REQUEST_METHOD <- method
  req$PATH_INFO <- path
  req$QUERY_STRING <- ""
  req$HTTP_CONTENT_TYPE <- "application/json"
  input <- new.env(parent = globalenv())
  input$read <- if (is.null(body)) {
    function(...) raw()
  } else {
    force(body)
    function(...) charToRaw(body)
  }
  req$rook.input <- input
  req
}

test_root <- normalizePath("../../..", mustWork = TRUE)
source(file.path(test_root, "R", "tests", "reference", "harness.R"))
characterization_use_local_library(test_root)

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

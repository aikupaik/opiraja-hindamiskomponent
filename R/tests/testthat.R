#!/usr/bin/env Rscript

root <- normalizePath(getwd(), mustWork = TRUE)
if (!file.exists(file.path(root, "R", "tests", "testthat.R"))) {
  stop("Run this test runner from the repository root.")
}
Sys.setenv(RENV_PROJECT = normalizePath(file.path(root, "R"), mustWork = TRUE))
source(file.path(root, "R", "renv", "activate.R"), local = FALSE)
if (!requireNamespace("testthat", quietly = TRUE)) {
  stop("The testthat package is required to run R/tests/testthat.R.")
}

testthat::test_dir(
  file.path(root, "R", "tests", "testthat"),
  reporter = "summary",
  stop_on_failure = TRUE,
  stop_on_warning = TRUE
)

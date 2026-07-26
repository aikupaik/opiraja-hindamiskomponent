#!/usr/bin/env Rscript

root <- normalizePath(getwd(), mustWork = TRUE)
if (!file.exists(file.path(root, "R", "tests", "testthat.R"))) {
  stop("Run this test runner from the repository root.")
}
local_library <- file.path(root, "R", "library")
if (dir.exists(local_library)) {
  .libPaths(c(local_library, .libPaths()))
  Sys.setenv(R_LIBS_USER = local_library)
}
if (!requireNamespace("testthat", quietly = TRUE)) {
  stop("The testthat package is required to run R/tests/testthat.R.")
}

testthat::test_dir(
  file.path(root, "R", "tests", "testthat"),
  reporter = "summary",
  stop_on_failure = TRUE,
  stop_on_warning = TRUE
)

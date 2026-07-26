sorted_recursively <- function(value) {
  if (!is.list(value) || is.null(names(value))) {
    return(TRUE)
  }
  identical(names(value), sort(names(value))) &&
    all(vapply(value, sorted_recursively, logical(1)))
}

testthat::test_that("experimental configuration is canonical and hashable", {
  path <- file.path(test_root, "R", "config", "kst.json")
  size <- file.info(path)$size
  bytes <- readBin(path, what = "raw", n = size)
  text <- rawToChar(bytes)
  parsed <- jsonlite::fromJSON(text, simplifyVector = FALSE)
  fixture <- read_fixture("configuration.json", simplify = TRUE)
  expected_hash <- paste0(
    "kst-config-v1:sha256:",
    digest::digest(bytes, algo = "sha256", serialize = FALSE)
  )
  canonical_text <- as.character(jsonlite::toJSON(
    parsed,
    auto_unbox = TRUE,
    null = "null",
    digits = NA
  ))

  testthat::expect_identical(text, canonical_text)
  testthat::expect_true(sorted_recursively(parsed))
  testthat::expect_identical(fixture$configuration_hash, expected_hash)
  testthat::expect_match(
    fixture$configuration_hash,
    "^kst-config-v1:sha256:[0-9a-f]{64}$"
  )
})

testthat::test_that("configuration reproduces hard-coded prototype values", {
  config <- jsonlite::fromJSON(
    file.path(test_root, "R", "config", "kst.json")
  )
  app_source <- paste(
    readLines(file.path(test_root, "TP_kst", "app.R"), warn = FALSE),
    collapse = "\n"
  )
  logic_source <- paste(
    readLines(file.path(test_root, "TP_kst", "TP_loogika.R"), warn = FALSE),
    collapse = "\n"
  )
  floor_count <- function(n) {
    min(max(
      config$reliability_floor$minimum,
      ceiling(config$reliability_floor$multiplier * n)
    ), config$reliability_floor$maximum)
  }
  cap_count <- function(n) {
    max(
      config$safety_cap$node_multiplier * n,
      floor_count(n) + config$safety_cap$minimum_above_floor
    )
  }

  testthat::expect_identical(config$schema_version, 1L)
  testthat::expect_identical(config$stop_confidence, 0.8)
  testthat::expect_identical(config$feedback_credible_mass, 0.9)
  testthat::expect_identical(
    vapply(c(1L, 4L, 5L, 7L, 10L), floor_count, numeric(1)),
    c(7, 7, 8, 10, 10)
  )
  testthat::expect_identical(
    vapply(c(1L, 4L, 5L, 7L, 10L), cap_count, numeric(1)),
    c(8, 8, 10, 14, 20)
  )
  testthat::expect_match(
    app_source,
    "min\\(max\\(7, ceiling\\(1\\.5 \\* n\\)\\), 10\\)"
  )
  testthat::expect_match(
    app_source,
    "max\\(2 \\* n, reliaabluse_pohi\\(n\\) \\+ 1\\)"
  )
  testthat::expect_match(app_source, "max\\(uus_posterior\\) >= 0\\.8")
  testthat::expect_match(logic_source, "tau_tagasiside = 0\\.9")
})

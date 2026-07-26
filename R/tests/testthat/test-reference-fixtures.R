testthat::test_that("the isolated harness uses private environments and stubs", {
  environments <- load_reference_environments(test_root)

  testthat::expect_true(is.environment(environments$ata))
  testthat::expect_true(is.environment(environments$tp))
  testthat::expect_false(identical(environments$ata, .GlobalEnv))
  testthat::expect_false(identical(environments$tp, .GlobalEnv))
  testthat::expect_identical(
    environments$ata$sb_get,
    environments$ata_stub$sb_get
  )
  testthat::expect_identical(
    environments$tp$sb_patch,
    environments$tp_stub$sb_patch
  )
})

testthat::test_that("committed fixtures recompute byte-for-byte", {
  generator <- file.path(
    test_root, "R", "tests", "reference", "generate_fixtures.R"
  )
  output <- system2(
    file.path(R.home("bin"), "Rscript"),
    c(generator, "--check"),
    stdout = TRUE,
    stderr = TRUE
  )
  status <- attr(output, "status")
  if (is.null(status)) {
    status <- 0L
  }
  testthat::expect_identical(
    status,
    0L,
    info = paste(output, collapse = "\n")
  )
})

testthat::test_that("reference source hashes are unchanged", {
  manifest <- read_fixture("manifest.json", simplify = TRUE)
  expected <- unlist(manifest$reference_sha256, use.names = TRUE)
  actual <- reference_hashes(test_root)

  testthat::expect_identical(
    unname(actual[names(expected)]),
    unname(expected),
    info = paste(
      "Legacy reference hashes changed. Investigate ATA_kst/api.R,",
      "TP_kst/TP_loogika.R, or TP_kst/app.R; do not silently regenerate."
    )
  )
})

testthat::test_that("manifest records the pinned characterization runtime", {
  manifest <- read_fixture("manifest.json", simplify = TRUE)

  testthat::expect_identical(manifest$fixture_schema_version, 1L)
  testthat::expect_identical(manifest$r_version, "4.6.1")
  testthat::expect_identical(manifest$package_versions$kst, "0.5-5")
  testthat::expect_identical(manifest$package_versions$kstMatrix, "2.3-4")
  testthat::expect_identical(manifest$numerical_tolerance, 1e-12)
  testthat::expect_false("generated_at" %in% names(manifest))
})

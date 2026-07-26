testthat::test_that("OpenAPI contract defines the versioned internal boundary", {
  contract <- jsonlite::fromJSON(
    file.path(test_root, "R", "contracts", "internal-kst-v1.openapi.json"),
    simplifyVector = FALSE
  )

  testthat::expect_identical(contract$openapi, "3.1.0")
  testthat::expect_setequal(
    names(contract$paths),
    c("/health", "/internal/v1/kst/model", "/internal/v1/kst/advance")
  )
  testthat::expect_identical(
    contract$paths$`/health`$get$responses$`200`$content$
      `application/json`$example,
    list(status = "ok")
  )
  response_schema <- contract$paths$`/internal/v1/kst/advance`$post$
    responses$`200`$content$`application/json`$schema
  testthat::expect_identical(
    response_schema$discriminator$propertyName,
    "status"
  )
  testthat::expect_named(
    response_schema$discriminator$mapping,
    c("in_progress", "completed")
  )
  for (path in c(
    "/internal/v1/kst/model",
    "/internal/v1/kst/advance"
  )) {
    responses <- contract$paths[[path]]$post$responses
    testthat::expect_true(all(c("422", "500") %in% names(responses)))
  }
})

testthat::test_that("model contract example is fixture-backed", {
  contract <- jsonlite::fromJSON(
    file.path(test_root, "R", "contracts", "internal-kst-v1.openapi.json"),
    simplifyVector = TRUE
  )
  model_fixture <- read_fixture("models.json", simplify = TRUE)
  config_fixture <- read_fixture("configuration.json", simplify = TRUE)
  example <- contract$paths$`/internal/v1/kst/model`$post$responses$`200`$
    content$`application/json`$example

  testthat::expect_identical(
    example$model$nodes, model_fixture$generated_model$nodes
  )
  testthat::expect_identical(
    unname(example$model$matrix),
    unname(model_fixture$generated_model$matrix)
  )
  testthat::expect_equal(
    example$model$uniform_prior,
    model_fixture$generated_model$prior,
    tolerance = 1e-12
  )
  testthat::expect_identical(
    example$model$beta, model_fixture$generated_model$beta
  )
  testthat::expect_identical(
    example$model$eta, model_fixture$generated_model$eta
  )
  testthat::expect_identical(
    example$model$configuration_hash,
    config_fixture$configuration_hash
  )
  testthat::expect_equal(
    example$posterior,
    model_fixture$generated_model$prior,
    tolerance = 1e-12
  )
  testthat::expect_identical(
    example$next_node,
    model_fixture$initial_half_split$selected_node
  )
})

testthat::test_that("advance examples use characterized update and profile", {
  contract <- jsonlite::fromJSON(
    file.path(test_root, "R", "contracts", "internal-kst-v1.openapi.json"),
    simplifyVector = TRUE
  )
  adaptive <- read_fixture("adaptive.json", simplify = TRUE)
  profiles <- read_fixture("profiles.json", simplify = TRUE)
  examples <- contract$paths$`/internal/v1/kst/advance`$post$responses$`200`$
    content$`application/json`$examples
  in_progress <- examples$in_progress$value
  completed <- examples$completed$value
  all_mastered_index <- which(profiles$cases$id == "all_mastered")
  all_mastered_profile <- lapply(
    profiles$cases$expected,
    function(column) column[[all_mastered_index]]
  )
  all_mastered_profile$summary <-
    profiles$cases$expected$summary[[all_mastered_index]]
  all_mastered_profile$stop_reason <-
    profiles$cases$expected$stop_reason[[all_mastered_index]]
  all_mastered_profile$best_state_confidence <-
    profiles$cases$expected$best_state_confidence[[all_mastered_index]]
  all_mastered_profile$credible_mass <-
    profiles$cases$expected$credible_mass[[all_mastered_index]]
  all_mastered_profile$credible_state_count <-
    profiles$cases$expected$credible_state_count[[all_mastered_index]]
  for (field in c(
    "mastered", "ready_to_learn", "uncertain_ahead",
    "uncertain_prerequisite", "not_yet"
  )) {
    if (length(all_mastered_profile[[field]]) == 0) {
      all_mastered_profile[[field]] <- list()
    }
  }

  testthat::expect_identical(in_progress$status, "in_progress")
  testthat::expect_equal(
    in_progress$posterior,
    adaptive$single_updates$correct$posterior,
    tolerance = 1e-12
  )
  testthat::expect_true(
    in_progress$next_node %in% adaptive$half_split_tie$allowed_nodes
  )
  testthat::expect_identical(completed$status, "completed")
  testthat::expect_equal(
    completed$posterior,
    profiles$cases$posterior[[all_mastered_index]],
    tolerance = 1e-12
  )
  testthat::expect_identical(
    completed$profile,
    all_mastered_profile
  )
})

testthat::test_that("contract exposes exact English legacy mappings", {
  contract <- jsonlite::fromJSON(
    file.path(test_root, "R", "contracts", "internal-kst-v1.openapi.json"),
    simplifyVector = FALSE
  )
  properties <- contract$components$schemas$FinalProfile$properties
  mappings <- c(
    mastered = "omandatud",
    ready_to_learn = "valmis_oppima",
    uncertain_ahead = "ebamaarane_edasi",
    uncertain_prerequisite = "ebamaarane_tagasi",
    not_yet = "veel_mitte",
    summary = "kokkuvote",
    best_state_confidence = "kindlus_parim_olek",
    credible_mass = "kindlus_C_hulgas",
    credible_state_count = "n_usutavaid_olekuid"
  )

  for (english in names(mappings)) {
    testthat::expect_match(
      properties[[english]]$description,
      mappings[[english]],
      fixed = TRUE
    )
  }
  testthat::expect_identical(
    properties$stop_reason$enum,
    list("natural", "safety_cap")
  )
  testthat::expect_match(
    properties$stop_reason$description,
    "peatumise_pohjus: loomulik or turvipiir",
    fixed = TRUE
  )
})

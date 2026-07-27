KST_CONFIGURATION_HASH_PREFIX <- "kst-config-v1:sha256:"

kst_service_root <- function() {
  configured <- getOption("kst.service.root")
  if (!is.null(configured)) {
    return(normalizePath(configured, mustWork = TRUE))
  }

  candidates <- c(
    normalizePath(getwd(), mustWork = FALSE),
    normalizePath(file.path(getwd(), "R"), mustWork = FALSE)
  )
  matches <- candidates[file.exists(file.path(candidates, "config", "kst.json"))]
  if (length(matches) == 0L) {
    stop("Could not locate the R service root.")
  }
  matches[[1L]]
}

is_json_object <- function(value) {
  is.list(value) && !is.null(names(value))
}

canonicalize_json_value <- function(value) {
  if (is_json_object(value)) {
    keys <- sort(names(value))
    return(setNames(lapply(value[keys], canonicalize_json_value), keys))
  }
  if (is.list(value)) {
    return(unname(lapply(value, canonicalize_json_value)))
  }
  unname(value)
}

canonical_json <- function(value) {
  as.character(jsonlite::toJSON(
    canonicalize_json_value(value),
    auto_unbox = TRUE,
    null = "null",
    digits = NA,
    force = TRUE
  ))
}

configuration_hash <- function(configuration) {
  text <- canonical_json(configuration)
  paste0(
    KST_CONFIGURATION_HASH_PREFIX,
    digest::digest(charToRaw(text), algo = "sha256", serialize = FALSE)
  )
}

configuration_detail <- function(field, issue) {
  list(field = field, issue = issue)
}

validate_kst_configuration <- function(configuration) {
  details <- list()
  add <- function(field, issue) {
    details[[length(details) + 1L]] <<- configuration_detail(field, issue)
  }

  required <- c(
    "feedback_credible_mass", "reliability_floor", "safety_cap",
    "schema_version", "stop_confidence"
  )
  if (!is_json_object(configuration)) {
    return(list(configuration_detail("configuration", "must be an object")))
  }
  missing <- setdiff(required, names(configuration))
  unknown <- setdiff(names(configuration), required)
  for (field in missing) add(paste0("configuration.", field), "is required")
  for (field in unknown) add(paste0("configuration.", field), "is unknown")
  if (length(missing) > 0L) return(details)

  scalar_number <- function(value) {
    is.numeric(value) && length(value) == 1L && is.finite(value)
  }
  integer_number <- function(value) {
    scalar_number(value) && value == floor(value)
  }
  probability_fields <- c("feedback_credible_mass", "stop_confidence")
  for (field in probability_fields) {
    value <- configuration[[field]]
    if (!scalar_number(value) || value <= 0 || value > 1) {
      add(
        paste0("configuration.", field),
        "must be a finite number greater than 0 and at most 1"
      )
    }
  }
  if (!integer_number(configuration$schema_version) ||
      configuration$schema_version != 1) {
    add("configuration.schema_version", "must equal 1")
  }

  validate_section <- function(section, required_fields, integer_fields,
                               positive_fields = character(0)) {
    value <- configuration[[section]]
    path <- paste0("configuration.", section)
    if (!is_json_object(value)) {
      add(path, "must be an object")
      return()
    }
    for (field in setdiff(required_fields, names(value))) {
      add(paste0(path, ".", field), "is required")
    }
    for (field in setdiff(names(value), required_fields)) {
      add(paste0(path, ".", field), "is unknown")
    }
    for (field in intersect(required_fields, names(value))) {
      item <- value[[field]]
      valid <- if (field %in% integer_fields) {
        integer_number(item) && item >= 0
      } else {
        scalar_number(item) && item > 0
      }
      if (!valid) {
        add(
          paste0(path, ".", field),
          if (field %in% integer_fields) {
            "must be a non-negative integer"
          } else {
            "must be a positive finite number"
          }
        )
      }
    }
  }
  validate_section(
    "reliability_floor",
    c("maximum", "minimum", "multiplier"),
    c("maximum", "minimum"),
    "multiplier"
  )
  validate_section(
    "safety_cap",
    c("minimum_above_floor", "node_multiplier"),
    c("minimum_above_floor"),
    "node_multiplier"
  )

  floor_config <- configuration$reliability_floor
  if (is_json_object(floor_config) &&
      all(c("minimum", "maximum") %in% names(floor_config)) &&
      integer_number(floor_config$minimum) &&
      integer_number(floor_config$maximum) &&
      floor_config$minimum > floor_config$maximum) {
    add(
      "configuration.reliability_floor.minimum",
      "must not exceed maximum"
    )
  }
  details
}

read_kst_configuration <- function(
    path = file.path(kst_service_root(), "config", "kst.json")) {
  size <- file.info(path)$size
  if (is.na(size)) stop("KST configuration file does not exist.")
  bytes <- readBin(path, what = "raw", n = size)
  parsed <- tryCatch(
    jsonlite::fromJSON(rawToChar(bytes), simplifyVector = FALSE),
    error = function(error) stop("KST configuration is not valid JSON.")
  )
  details <- validate_kst_configuration(parsed)
  if (length(details) > 0L) {
    stop(paste0(
      "KST configuration is invalid: ",
      details[[1L]]$field, " ", details[[1L]]$issue
    ))
  }
  canonical <- canonical_json(parsed)
  if (!identical(rawToChar(bytes), canonical)) {
    stop("KST configuration file is not canonically serialized.")
  }
  list(
    snapshot = canonicalize_json_value(parsed),
    hash = paste0(
      KST_CONFIGURATION_HASH_PREFIX,
      digest::digest(bytes, algo = "sha256", serialize = FALSE)
    )
  )
}

reliability_floor <- function(node_count, configuration) {
  floor_config <- configuration$reliability_floor
  as.integer(min(max(
    floor_config$minimum,
    ceiling(floor_config$multiplier * node_count)
  ), floor_config$maximum))
}

safety_cap <- function(node_count, configuration) {
  cap_config <- configuration$safety_cap
  as.integer(ceiling(max(
    cap_config$node_multiplier * node_count,
    reliability_floor(node_count, configuration) +
      cap_config$minimum_above_floor
  )))
}

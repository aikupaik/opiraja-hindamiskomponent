array_value <- function(value) {
  unname(I(value))
}

shape_model_for_json <- function(model) {
  model$nodes <- array_value(model$nodes)
  model$knowledge_states <- unname(lapply(
    model$knowledge_states, array_value
  ))
  model$matrix <- unname(lapply(model$matrix, array_value))
  model$uniform_prior <- array_value(model$uniform_prior)
  for (field in c("beta", "eta")) {
    if (!is.null(model[[field]])) {
      model[[field]] <- array_value(model[[field]])
    }
  }
  model
}

shape_profile_for_json <- function(profile) {
  for (field in c(
    "mastered", "ready_to_learn", "uncertain_ahead",
    "uncertain_prerequisite", "not_yet"
  )) {
    profile[[field]] <- array_value(profile[[field]])
  }
  profile
}

shape_response_for_json <- function(value) {
  if (!is.null(value$model)) {
    value$model <- shape_model_for_json(value$model)
  }
  if (!is.null(value$posterior)) {
    value$posterior <- array_value(value$posterior)
  }
  if (!is.null(value$profile)) {
    value$profile <- shape_profile_for_json(value$profile)
  }
  value
}

serialize_http_json <- function(value) {
  as.character(jsonlite::toJSON(
    value,
    auto_unbox = TRUE,
    null = "null",
    digits = NA,
    force = TRUE
  ))
}

error_envelope <- function(code, message, details = list()) {
  list(error = list(
    code = code,
    message = message,
    details = unname(details)
  ))
}

write_json_response <- function(res, value, status = 200L) {
  res$status <- as.integer(status)
  res$setHeader("Content-Type", "application/json")
  serialize_http_json(value)
}

handle_http_operation <- function(req, res, operation) {
  tryCatch(
    {
      raw_body <- req$bodyRaw
      body <- if (is.raw(raw_body)) {
        rawToChar(raw_body)
      } else {
        req$postBody
      }
      request <- parse_json_body(body)
      result <- operation(request)
      write_json_response(res, shape_response_for_json(result))
    },
    kst_validation_error = function(error) {
      write_json_response(
        res,
        error_envelope(
          "validation_error",
          "Request validation failed.",
          error$details
        ),
        422L
      )
    }
  )
}

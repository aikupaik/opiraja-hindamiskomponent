#!/usr/bin/env Rscript

script_arguments <- commandArgs(trailingOnly = FALSE)
script_argument <- grep("^--file=", script_arguments, value = TRUE)
if (length(script_argument) != 1L) {
  stop("Run this file with Rscript.")
}

script_file <- normalizePath(
  sub("^--file=", "", script_argument[[1L]]),
  mustWork = TRUE
)
service_root <- dirname(dirname(script_file))

Sys.setenv(RENV_PROJECT = service_root)
source(file.path(service_root, "renv", "activate.R"), local = FALSE)

host <- Sys.getenv("KST_HOST", unset = "127.0.0.1")
port_text <- Sys.getenv("KST_PORT", unset = "8001")
port <- suppressWarnings(as.integer(port_text))
if (is.na(port) || port < 1L || port > 65535L) {
  stop("KST_PORT must be an integer between 1 and 65535.")
}

is_enabled <- function(name, default = FALSE) {
  value <- Sys.getenv(name, unset = if (default) "true" else "false")
  tolower(value) %in% c("1", "true", "yes", "on")
}

log_bodies <- is_enabled("KST_LOG_BODIES")
configuration_path <- Sys.getenv("KST_CONFIG_PATH", unset = "")
if (nzchar(configuration_path)) {
  configuration_path <- normalizePath(configuration_path, mustWork = TRUE)
}

options(kst.service.root = service_root)
service_environment <- new.env(parent = globalenv())
sys.source(
  file.path(service_root, "plumber.R"),
  envir = service_environment
)

model_operation <- if (nzchar(configuration_path)) {
  function(request) {
    service_environment$create_model_response(
      request,
      configuration_path = configuration_path
    )
  }
} else {
  service_environment$create_model_response
}

router <- service_environment$create_kst_router(
  model_operation = model_operation,
  advance_operation = service_environment$advance_assessment
)

request_counter <- 0L

body_text <- function(value) {
  if (is.null(value)) return("")
  if (is.raw(value)) return(rawToChar(value))
  if (is.character(value)) return(paste(value, collapse = ""))
  as.character(value)
}

pretty_json <- function(value) {
  text <- body_text(value)
  if (!nzchar(text)) return("<empty>")
  parsed <- tryCatch(
    jsonlite::fromJSON(text, simplifyVector = FALSE),
    error = function(error) NULL
  )
  if (is.null(parsed)) return(text)
  as.character(jsonlite::toJSON(
    parsed,
    auto_unbox = TRUE,
    null = "null",
    digits = NA,
    pretty = TRUE,
    force = TRUE
  ))
}

router <- plumber::pr_hook(
  router,
  "preroute",
  function(data, req) {
    request_counter <<- request_counter + 1L
    data$request_id <- request_counter
    data$started_at <- proc.time()[["elapsed"]]
    cat(sprintf(
      "[%s] --> #%d %s %s\n",
      format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
      data$request_id,
      req$REQUEST_METHOD,
      req$PATH_INFO
    ))
    flush.console()
  }
)

router <- plumber::pr_hook(
  router,
  "postroute",
  function(req) {
    if (log_bodies && req$REQUEST_METHOD != "GET") {
      request_body <- if (is.raw(req$bodyRaw)) {
        req$bodyRaw
      } else {
        req$postBody
      }
      cat("Request body:\n", pretty_json(request_body), "\n", sep = "")
      flush.console()
    }
  }
)

router <- plumber::pr_hook(
  router,
  "postserialize",
  function(data, res) {
    elapsed_ms <- round(
      (proc.time()[["elapsed"]] - data$started_at) * 1000
    )
    status <- if (is.null(res$status)) 200L else as.integer(res$status)
    cat(sprintf(
      "[%s] <-- #%d %d (%d ms)\n",
      format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
      data$request_id,
      status,
      elapsed_ms
    ))
    if (log_bodies) {
      cat("Response body:\n", pretty_json(res$body), "\n", sep = "")
    }
    flush.console()
  }
)

cat("KST manual test service\n")
cat(sprintf("Listening at http://%s:%d\n", host, port))
cat(sprintf(
  "OpenAPI documentation: http://%s:%d/__docs__/\n",
  host,
  port
))
cat(sprintf("Full JSON body logging: %s\n", if (log_bodies) "on" else "off"))
cat(sprintf(
  "Configuration: %s\n",
  if (nzchar(configuration_path)) {
    configuration_path
  } else {
    file.path(service_root, "config", "kst.json")
  }
))
cat("Press Ctrl+C to stop.\n\n")
flush.console()

plumber::pr_run(
  router,
  host = host,
  port = port,
  quiet = TRUE
)

KST_LOG_SCHEMA_VERSION <- 1L
KST_LOG_LEVELS <- c(DEBUG = 10L, INFO = 20L, WARNING = 30L, ERROR = 40L)

configured_log_level <- function() {
  level <- toupper(Sys.getenv("APP_LOG_LEVEL", unset = "INFO"))
  if (!level %in% names(KST_LOG_LEVELS)) {
    stop("APP_LOG_LEVEL must be DEBUG, INFO, WARNING, or ERROR.")
  }
  level
}

should_log_level <- function(level, minimum_level) {
  unname(KST_LOG_LEVELS[[level]]) >= unname(KST_LOG_LEVELS[[minimum_level]])
}

write_log_event <- function(level, event, fields = list(),
                            minimum_level = configured_log_level()) {
  if (!should_log_level(level, minimum_level)) return(invisible(NULL))
  payload <- c(list(
    timestamp = format(
      Sys.time(),
      "%Y-%m-%dT%H:%M:%OS3Z",
      tz = "UTC"
    ),
    schema_version = KST_LOG_SCHEMA_VERSION,
    level = level,
    service = "r-service",
    event = event
  ), fields)
  cat(as.character(jsonlite::toJSON(
    payload,
    auto_unbox = TRUE,
    null = "null",
    digits = NA,
    force = TRUE
  )), "\n", sep = "")
  flush.console()
  invisible(NULL)
}

safe_request_id <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    grepl("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", value, perl = TRUE)
}

request_id_generator <- local({
  instance <- paste0(
    Sys.getpid(), "-", format(Sys.time(), "%Y%m%dT%H%M%OS6", tz = "UTC")
  )
  counter <- 0L
  function() {
    counter <<- counter + 1L
    paste0("r-", instance, "-", counter)
  }
})

resolve_request_id <- function(req) {
  supplied <- req$HTTP_X_REQUEST_ID
  if (safe_request_id(supplied)) supplied else request_id_generator()
}

http_log_level <- function(status) {
  if (status >= 500L) return("ERROR")
  if (status >= 400L) return("WARNING")
  "INFO"
}

http_outcome <- function(status) {
  if (status < 300L) return("success")
  if (status == 422L) return("validation_error")
  if (status < 500L) return("client_error")
  "server_error"
}

register_observability_hooks <- function(router, minimum_level) {
  router <- plumber::pr_hook(
    router,
    "preroute",
    function(data, req, res) {
      request_id <- resolve_request_id(req)
      data$observability <- list(
        request_id = request_id,
        started_at = proc.time()[["elapsed"]]
      )
      req$observability_request_id <- request_id
      res$setHeader("X-Request-ID", request_id)
    }
  )
  plumber::pr_hook(
    router,
    "postserialize",
    function(data, req, res) {
      status <- if (is.null(res$status)) 200L else as.integer(res$status)
      if (identical(req$PATH_INFO, "/health") && status < 400L) {
        return(invisible(NULL))
      }
      context <- data$observability
      duration_ms <- round(
        (proc.time()[["elapsed"]] - context$started_at) * 1000,
        digits = 3L
      )
      write_log_event(
        http_log_level(status),
        "request_completed",
        list(
          request_id = context$request_id,
          method = req$REQUEST_METHOD,
          path = req$PATH_INFO,
          route = req$PATH_INFO,
          status = status,
          outcome = http_outcome(status),
          duration_ms = duration_ms
        ),
        minimum_level
      )
    }
  )
}

log_unhandled_http_error <- function(req, error, minimum_level) {
  request_id <- req$observability_request_id
  if (!safe_request_id(request_id)) request_id <- request_id_generator()
  write_log_event(
    "ERROR",
    "unhandled_request_exception",
    list(
      request_id = request_id,
      method = req$REQUEST_METHOD,
      path = req$PATH_INFO,
      error_type = class(error)[[1L]]
    ),
    minimum_level
  )
}

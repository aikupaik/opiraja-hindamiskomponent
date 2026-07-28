configured_root <- getOption("kst.service.root")
if (!is.null(configured_root)) {
  service_root <- normalizePath(configured_root, mustWork = TRUE)
} else {
  source_candidates <- unlist(lapply(sys.frames(), function(frame) {
    if (is.null(frame$ofile)) character(0) else frame$ofile
  }), use.names = FALSE)
  source_candidates <- source_candidates[
    basename(source_candidates) == "plumber.R" & file.exists(source_candidates)
  ]
  service_file <- if (length(source_candidates) > 0L) {
    normalizePath(
      source_candidates[[length(source_candidates)]],
      mustWork = TRUE
    )
  } else {
    normalizePath("plumber.R", mustWork = TRUE)
  }
  service_root <- dirname(service_file)
}
options(kst.service.root = service_root)

for (source_file in c(
  "configuration.R",
  "knowledge_space.R",
  "model.R",
  "assessment.R",
  "profile.R",
  "validation.R",
  "service.R",
  "http.R"
)) {
  sys.source(
    file.path(service_root, "src", source_file),
    envir = environment()
  )
}

create_kst_router <- function(
    model_operation = create_model_response,
    advance_operation = advance_assessment,
    model_operation_v2 = create_model_response_v2,
    select_operation_v2 = select_assessment_candidate_v2,
    advance_operation_v2 = advance_assessment_v2) {
  plumber::register_parser(
    "kst_raw_json",
    function() {
      function(value, ...) value
    },
    fixed = c("application/json", "text/json"),
    verbose = FALSE
  )
  json_serializer <- plumber::serializer_content_type(
    "application/json",
    serialize_fn = identity
  )
  router <- plumber::pr()
  router <- plumber::pr_get(
    router,
    "/health",
    function(req, res) {
      write_json_response(res, list(status = "ok"))
    },
    serializer = json_serializer
  )
  router <- plumber::pr_post(
    router,
    "/internal/v1/kst/model",
    function(req, res) {
      handle_http_operation(req, res, model_operation)
    },
    serializer = json_serializer,
    parsers = "kst_raw_json"
  )
  router <- plumber::pr_post(
    router,
    "/internal/v1/kst/advance",
    function(req, res) {
      handle_http_operation(req, res, advance_operation)
    },
    serializer = json_serializer,
    parsers = "kst_raw_json"
  )
  router <- plumber::pr_post(
    router,
    "/internal/v2/kst/model",
    function(req, res) {
      handle_http_operation(req, res, model_operation_v2)
    },
    serializer = json_serializer,
    parsers = "kst_raw_json"
  )
  router <- plumber::pr_post(
    router,
    "/internal/v2/kst/select",
    function(req, res) {
      handle_http_operation(req, res, select_operation_v2)
    },
    serializer = json_serializer,
    parsers = "kst_raw_json"
  )
  router <- plumber::pr_post(
    router,
    "/internal/v2/kst/advance",
    function(req, res) {
      handle_http_operation(req, res, advance_operation_v2)
    },
    serializer = json_serializer,
    parsers = "kst_raw_json"
  )
  plumber::pr_set_error(router, function(req, res, error) {
    write_json_response(
      res,
      error_envelope(
        "internal_error",
        "An unexpected internal error occurred.",
        list()
      ),
      500L
    )
  })
}

create_kst_app <- function(...) {
  create_kst_router(...)
}

create_kst_router()

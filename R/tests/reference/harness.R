characterization_root <- function() {
  candidates <- c(
    normalizePath(getwd(), mustWork = FALSE),
    normalizePath(file.path(getwd(), ".."), mustWork = FALSE),
    normalizePath(file.path(getwd(), "../.."), mustWork = FALSE),
    normalizePath(file.path(getwd(), "../../.."), mustWork = FALSE)
  )
  matches <- candidates[file.exists(file.path(candidates, "ATA_kst", "api.R"))]
  if (length(matches) == 0) {
    stop("Run the characterization suite from the repository or R/ directory.")
  }
  matches[[1]]
}

characterization_use_local_library <- function(root = characterization_root()) {
  local_library <- file.path(root, "R", "library")
  if (dir.exists(local_library)) {
    .libPaths(c(local_library, .libPaths()))
  }
}

reference_files <- function(root = characterization_root()) {
  c(
    ata_api = file.path(root, "ATA_kst", "api.R"),
    tp_logic = file.path(root, "TP_kst", "TP_loogika.R"),
    tp_app = file.path(root, "TP_kst", "app.R")
  )
}

reference_hashes <- function(root = characterization_root()) {
  files <- reference_files(root)
  setNames(
    vapply(files, digest::digest, character(1), algo = "sha256", file = TRUE),
    names(files)
  )
}

source_hash <- function(path) {
  digest::digest(path, algo = "sha256", file = TRUE)
}

new_memory_stub <- function() {
  records <- new.env(parent = emptyenv())
  records$gets <- list()
  records$posts <- list()
  records$patches <- list()
  records$get_response <- list()

  list(
    records = records,
    sb_get = function(path_with_query) {
      records$gets <- c(records$gets, list(path_with_query))
      records$get_response
    },
    sb_get_q = function(path, parameters) {
      records$gets <- c(records$gets, list(list(path = path, parameters = parameters)))
      records$get_response
    },
    sb_post = function(path, body_list, prefer = "return=representation") {
      records$posts <- c(records$posts, list(list(
        path = path,
        body = body_list,
        prefer = prefer
      )))
      invisible(NULL)
    },
    sb_patch = function(path_with_query, body_list) {
      records$patches <- c(records$patches, list(list(
        path = path_with_query,
        body = body_list
      )))
      invisible(NULL)
    }
  )
}

load_reference_environments <- function(root = characterization_root()) {
  characterization_use_local_library(root)
  files <- reference_files(root)

  ata <- new.env(parent = globalenv())
  tp <- new.env(parent = globalenv())
  suppressWarnings(sys.source(files[["ata_api"]], envir = ata))
  suppressWarnings(sys.source(files[["tp_logic"]], envir = tp))

  ata_stub <- new_memory_stub()
  tp_stub <- new_memory_stub()
  for (name in c("sb_get", "sb_get_q", "sb_post", "sb_patch")) {
    assign(name, ata_stub[[name]], envir = ata)
    assign(name, tp_stub[[name]], envir = tp)
  }

  list(ata = ata, tp = tp, ata_stub = ata_stub, tp_stub = tp_stub)
}

relations_frame <- function(relations) {
  if (length(relations) == 0) {
    return(data.frame(from = character(0), to = character(0)))
  }
  data.frame(
    from = vapply(relations, `[[`, character(1), "from"),
    to = vapply(relations, `[[`, character(1), "to"),
    stringsAsFactors = FALSE
  )
}

plain_states <- function(states) {
  unname(lapply(states, function(state) I(unname(as.character(state)))))
}

plain_matrix <- function(value) {
  unname(lapply(seq_len(nrow(value)), function(row) {
    I(unname(as.integer(value[row, ])))
  }))
}

plain_numeric <- function(value) {
  I(unname(as.numeric(value)))
}

generate_knowledge_space <- function(environments, nodes, relations) {
  environments$ata_stub$records$get_response <- list()
  result <- environments$ata$koosta_teadmusmudel(
    "kst",
    "characterization-graph",
    nodes,
    relations_frame(relations)
  )
  plain_states(result$teadmusruum)
}

restore_knowledge_space <- function(environments, nodes, relations, states) {
  environments$ata_stub$records$get_response <- data.frame(
    graaf_hash = "characterization-graph",
    teadmusruum_maatriks = jsonlite::toJSON(states, auto_unbox = TRUE),
    stringsAsFactors = FALSE
  )
  result <- environments$ata$koosta_teadmusmudel(
    "kst",
    "characterization-graph",
    nodes,
    relations_frame(relations)
  )
  plain_states(result$teadmusruum)
}

build_legacy_model <- function(environments, nodes, states, parameters) {
  parameter_map <- setNames(lapply(seq_along(nodes), function(index) {
    list(
      beta = parameters[[index]]$beta,
      eta = parameters[[index]]$eta,
      yp_id = parameters[[index]]$item_id
    )
  }), nodes)
  result <- environments$ata$koosta_hindamisloogika(
    "kst", states, nodes, parameter_map
  )
  list(
    method = result$metoodika,
    nodes = I(unname(result$solmed)),
    knowledge_states = plain_states(states),
    matrix = plain_matrix(result$K),
    prior = plain_numeric(result$P_K),
    beta = plain_numeric(result$beta),
    eta = plain_numeric(result$eta)
  )
}

model_matrix <- function(model) {
  matrix(
    unlist(model$matrix, use.names = FALSE),
    nrow = length(model$matrix),
    byrow = TRUE,
    dimnames = list(NULL, unlist(model$nodes, use.names = FALSE))
  )
}

half_split_candidates <- function(posterior, matrix) {
  distances <- abs(as.numeric(crossprod(posterior, matrix)) - 0.5)
  which(abs(distances - min(distances)) <= .Machine$double.eps^0.5)
}

bayesian_update <- function(environments, posterior, matrix, question, correct,
                            beta, eta) {
  plain_numeric(environments$tp$uuenda_posterior(
    posterior, matrix, question, correct, beta, eta
  ))
}

stopping_source <- function(root = characterization_root()) {
  path <- reference_files(root)[["tp_app"]]
  list(
    source_file = "TP_kst/app.R",
    source_sha256 = source_hash(path),
    reliability_expression =
      "min(max(7, ceiling(1.5 * n)), 10)",
    safety_cap_expression =
      "max(2 * n, reliability_floor(n) + 1)",
    natural_expression =
      "max(posterior) >= 0.8 && response_count >= reliability_floor(n)",
    completion_expression =
      "natural || response_count >= safety_cap(n)",
    precedence_expression =
      "if (natural) \"natural\" else \"safety_cap\""
  )
}

legacy_stopping_decision <- function(node_count, confidence, response_count) {
  reliability_floor <- function(n) min(max(7, ceiling(1.5 * n)), 10)
  safety_cap <- function(n) max(2 * n, reliability_floor(n) + 1)
  natural <- confidence >= 0.8 &&
    response_count >= reliability_floor(node_count)
  completed <- natural || response_count >= safety_cap(node_count)
  list(
    completed = completed,
    stop_reason = if (!completed) {
      NULL
    } else if (natural) {
      "natural"
    } else {
      "safety_cap"
    }
  )
}

legacy_profile <- function(environments, posterior, nodes, matrix,
                           stop_reason, credible_mass = 0.9) {
  environments$tp_stub$records$patches <- list()
  result <- environments$tp$lopeta_test(
    "characterization-test",
    posterior,
    nodes,
    matrix,
    if (identical(stop_reason, "natural")) "loomulik" else "turvipiir",
    tau_tagasiside = credible_mass
  )
  list(
    mastered = I(unname(result$omandatud)),
    ready_to_learn = I(unname(result$valmis_oppima)),
    uncertain_ahead = I(unname(result$ebamaarane_edasi)),
    uncertain_prerequisite = I(unname(result$ebamaarane_tagasi)),
    not_yet = I(unname(result$veel_mitte)),
    summary = result$kokkuvote,
    stop_reason = if (identical(result$peatumise_pohjus, "loomulik")) {
      "natural"
    } else {
      "safety_cap"
    },
    best_state_confidence = unname(result$kindlus_parim_olek),
    credible_mass = unname(result$kindlus_C_hulgas),
    credible_state_count = unname(result$n_usutavaid_olekuid)
  )
}

credible_prefix <- function(posterior, mass = 0.9) {
  order_desc <- order(posterior, decreasing = TRUE)
  count <- which(cumsum(posterior[order_desc]) >= mass)[1]
  if (is.na(count)) {
    count <- length(posterior)
  }
  I(unname(order_desc[seq_len(count)]))
}

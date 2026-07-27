credible_state_indices <- function(posterior, credible_mass) {
  descending <- order(posterior, decreasing = TRUE)
  count <- which(cumsum(posterior[descending]) >= credible_mass)[[1L]]
  if (is.na(count)) count <- length(posterior)
  unname(as.integer(descending[seq_len(count)]))
}

state_fringe <- function(state, matrix) {
  result <- integer(ncol(matrix))
  for (index in seq_len(ncol(matrix))) {
    if (state[[index]] == 0L) {
      candidate <- state
      candidate[[index]] <- 1L
      result[[index]] <- as.integer(any(apply(
        matrix, 1L, function(row) identical(as.integer(row), candidate)
      )))
    }
  }
  result
}

build_final_profile <- function(posterior, nodes, matrix, stop_reason,
                                credible_mass = 0.9) {
  credible <- credible_state_indices(posterior, credible_mass)
  state_information <- lapply(credible, function(index) {
    state <- as.integer(matrix[index, ])
    list(state = state, fringe = state_fringe(state, matrix))
  })
  classification <- character(length(nodes))
  for (index in seq_along(nodes)) {
    included <- vapply(
      state_information, function(info) info$state[[index]] == 1L, logical(1)
    )
    ready <- vapply(state_information, function(info) {
      info$fringe[[index]] == 1L && info$state[[index]] == 0L
    }, logical(1))
    classification[[index]] <- if (all(included)) {
      "mastered"
    } else if (all(ready)) {
      "ready"
    } else if (!any(included) && !any(ready)) {
      "not_yet"
    } else {
      "uncertain"
    }
  }
  names(classification) <- nodes
  mastered <- unname(nodes[classification == "mastered"])
  ready <- unname(nodes[classification == "ready"])
  uncertain <- unname(nodes[classification == "uncertain"])
  not_yet <- unname(nodes[classification == "not_yet"])

  mastered_indices <- which(nodes %in% mastered)
  is_prerequisite_of_mastered <- function(node_index) {
    if (length(mastered_indices) == 0L) return(FALSE)
    rows <- apply(
      matrix[, mastered_indices, drop = FALSE],
      1L,
      function(row) all(row == 1L)
    )
    any(rows) && all(matrix[rows, node_index] == 1L)
  }
  uncertain_prerequisite <- uncertain[vapply(
    match(uncertain, nodes),
    is_prerequisite_of_mastered,
    logical(1)
  )]
  uncertain_ahead <- uncertain[!uncertain %in% uncertain_prerequisite]
  summary <- if (length(mastered) == length(nodes)) {
    "Teadsid kõike! Võta uus õpiväljund."
  } else if (length(ready) + length(uncertain_ahead) > 1L) {
    paste(
      "Sul on nüüd mitu võimalikku suunda, kust jätkata -",
      "kõik sobivad järgmiseks võrdselt hästi."
    )
  } else {
    NULL
  }

  list(
    mastered = mastered,
    ready_to_learn = ready,
    uncertain_ahead = unname(uncertain_ahead),
    uncertain_prerequisite = unname(uncertain_prerequisite),
    not_yet = not_yet,
    summary = summary,
    stop_reason = stop_reason,
    best_state_confidence = unname(max(posterior)),
    credible_mass = unname(sum(posterior[credible])),
    credible_state_count = as.integer(length(credible))
  )
}

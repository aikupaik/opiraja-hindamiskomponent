normalize_probability_vector <- function(probabilities) {
  probabilities <- unname(as.numeric(probabilities))
  if (length(probabilities) == 0L || any(!is.finite(probabilities))) {
    stop("Posterior contains non-finite values.")
  }
  total <- sum(probabilities)
  if (!is.finite(total) || total <= 0) {
    stop("Posterior cannot be normalized.")
  }
  probabilities <- probabilities / total
  probabilities[probabilities < 0 & probabilities > -1e-15] <- 0
  unname(probabilities / sum(probabilities))
}

select_half_split_index <- function(posterior, matrix) {
  distances <- abs(as.numeric(crossprod(posterior, matrix)) - 0.5)
  minimum <- min(distances)
  candidates <- which(
    abs(distances - minimum) <= .Machine$double.eps^0.5
  )
  as.integer(candidates[[1L]])
}

select_half_split_node <- function(posterior, matrix, nodes) {
  nodes[[select_half_split_index(posterior, matrix)]]
}

update_posterior <- function(posterior, matrix, beta, eta, question_index,
                             response_correct) {
  updated <- kstMatrix::kmassessbayesian(
    unname(as.numeric(posterior)),
    matrix,
    unname(as.numeric(beta)),
    unname(as.numeric(eta)),
    as.integer(question_index),
    as.integer(response_correct)
  )
  normalize_probability_vector(updated)
}

select_candidate <- function(posterior, matrix, nodes, candidates) {
  candidate_nodes <- vapply(candidates, `[[`, character(1), "node")
  candidate_columns <- match(candidate_nodes, nodes)
  distances <- abs(
    as.numeric(crossprod(posterior, matrix[, candidate_columns, drop = FALSE])) -
      0.5
  )
  minimum <- min(distances)
  selected <- which(
    abs(distances - minimum) <= .Machine$double.eps^0.5
  )[[1L]]
  candidates[[selected]]
}

update_posterior_for_candidate <- function(posterior, matrix, candidate,
                                           response_correct) {
  question_index <- match(candidate$node, colnames(matrix))
  mastered <- matrix[, question_index] == 1L
  correct_likelihood <- ifelse(
    mastered,
    1 - candidate$beta,
    candidate$eta
  )
  likelihood <- if (response_correct) {
    correct_likelihood
  } else {
    1 - correct_likelihood
  }
  normalize_probability_vector(posterior * likelihood)
}

stopping_decision <- function(node_count, posterior, response_count,
                              configuration) {
  confidence <- max(posterior)
  natural <- confidence >= configuration$stop_confidence &&
    response_count >= reliability_floor(node_count, configuration)
  cap_reached <- response_count >= safety_cap(node_count, configuration)
  list(
    completed = natural || cap_reached,
    stop_reason = if (natural) {
      "natural"
    } else if (cap_reached) {
      "safety_cap"
    } else {
      NULL
    }
  )
}

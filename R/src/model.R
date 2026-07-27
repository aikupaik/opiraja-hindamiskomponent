knowledge_states_matrix <- function(knowledge_states, nodes) {
  matrix(
    as.integer(unlist(lapply(knowledge_states, function(state) {
      nodes %in% state
    }), use.names = FALSE)),
    nrow = length(knowledge_states),
    byrow = TRUE,
    dimnames = list(NULL, nodes)
  )
}

build_kst_model <- function(nodes, relations, node_parameters,
                            cached_knowledge_states = NULL,
                            configuration = read_kst_configuration()) {
  states <- if (is.null(cached_knowledge_states)) {
    generate_knowledge_states(nodes, relations)
  } else {
    lapply(cached_knowledge_states, function(state) {
      unname(as.character(unlist(state, use.names = FALSE)))
    })
  }
  matrix_value <- knowledge_states_matrix(states, nodes)
  state_count <- length(states)
  parameter_nodes <- vapply(node_parameters, `[[`, character(1), "node")
  parameter_order <- match(nodes, parameter_nodes)
  prior <- unname(rep(1 / state_count, state_count))

  list(
    schema_version = 1L,
    method = "kst",
    nodes = unname(nodes),
    knowledge_states = unname(states),
    matrix = unname(lapply(seq_len(nrow(matrix_value)), function(index) {
      unname(as.integer(matrix_value[index, ]))
    })),
    uniform_prior = prior,
    beta = unname(vapply(
      node_parameters[parameter_order], `[[`, numeric(1), "beta"
    )),
    eta = unname(vapply(
      node_parameters[parameter_order], `[[`, numeric(1), "eta"
    )),
    configuration = configuration$snapshot,
    configuration_hash = configuration$hash
  )
}

model_matrix <- function(model) {
  matrix(
    unlist(model$matrix, use.names = FALSE),
    nrow = length(model$matrix),
    byrow = TRUE,
    dimnames = list(NULL, model$nodes)
  )
}

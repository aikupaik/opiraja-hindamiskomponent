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

build_kst_model_v2 <- function(nodes, relations,
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

  list(
    schema_version = 2L,
    method = "kst",
    nodes = unname(nodes),
    knowledge_states = unname(states),
    matrix = unname(lapply(seq_len(nrow(matrix_value)), function(index) {
      unname(as.integer(matrix_value[index, ]))
    })),
    uniform_prior = unname(rep(1 / state_count, state_count)),
    configuration = configuration$snapshot,
    configuration_hash = configuration$hash,
    reliability_floor = reliability_floor(length(nodes), configuration$snapshot),
    safety_cap = safety_cap(length(nodes), configuration$snapshot)
  )
}

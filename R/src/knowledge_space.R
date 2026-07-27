state_respects_relations <- function(state, relations) {
  if (length(relations) == 0L) return(TRUE)
  all(vapply(relations, function(relation) {
    !(relation$to %in% state) || relation$from %in% state
  }, logical(1)))
}

generate_knowledge_states <- function(nodes, relations) {
  subsets <- unlist(
    lapply(0:length(nodes), function(size) {
      utils::combn(nodes, size, simplify = FALSE)
    }),
    recursive = FALSE
  )
  unname(Filter(
    function(state) state_respects_relations(state, relations),
    subsets
  ))
}

state_key <- function(state) {
  paste(state, collapse = "\u001f")
}

validate_knowledge_states <- function(states, nodes, relations = NULL,
                                      field = "cached_knowledge_states") {
  details <- list()
  add <- function(path, issue) {
    details[[length(details) + 1L]] <<- list(field = path, issue = issue)
  }
  if (!is.list(states) || !is.null(names(states)) || length(states) == 0L) {
    return(list(list(field = field, issue = "must be a non-empty array")))
  }

  keys <- character(length(states))
  normalized <- vector("list", length(states))
  for (index in seq_along(states)) {
    path <- sprintf("%s[%d]", field, index)
    state <- states[[index]]
    if (!is.list(state) || !is.null(names(state))) {
      add(path, "must be an array")
      next
    }
    if (!all(vapply(state, function(item) {
      is.character(item) && length(item) == 1L && !is.na(item)
    }, logical(1)))) {
      add(path, "must contain only strings")
      next
    }
    state <- as.character(unlist(state, use.names = FALSE))
    normalized[[index]] <- state
    if (anyDuplicated(state)) add(path, "contains duplicate members")
    unknown <- setdiff(state, nodes)
    if (length(unknown) > 0L) add(path, "contains an unknown node")
    expected_order <- nodes[nodes %in% state]
    if (!identical(state, expected_order)) {
      add(path, "members must follow declared node order")
    }
    if (!is.null(relations) && !state_respects_relations(state, relations)) {
      add(path, "violates a prerequisite relation")
    }
    keys[[index]] <- state_key(state)
  }
  if (anyDuplicated(keys)) add(field, "contains duplicate states")
  if (!any(lengths(normalized) == 0L)) add(field, "must contain the empty state")
  if (!any(vapply(normalized, identical, logical(1), nodes))) {
    add(field, "must contain the full state")
  }

  if (length(details) == 0L) {
    all_subsets <- generate_knowledge_states(nodes, list())
    ranks <- match(
      vapply(normalized, state_key, character(1)),
      vapply(all_subsets, state_key, character(1))
    )
    if (is.unsorted(ranks, strictly = TRUE)) {
      add(field, "states must follow canonical declared-node ordering")
    }
  }
  if (length(details) == 0L && !is.null(relations)) {
    expected <- generate_knowledge_states(nodes, relations)
    if (!identical(normalized, expected)) {
      add(field, "states must use canonical prerequisite-closed ordering")
    }
  }
  details
}

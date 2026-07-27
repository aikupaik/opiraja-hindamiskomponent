"""Canonical graph validation, normalization, and versioned hashing."""

import hashlib
import json
from collections.abc import Iterable

from .models import *

GRAPH_HASH_PREFIX = "kst-graph-v1:sha256:"


class GraphValidationError(ValueError):
    """A graph cannot be represented by the supported KST graph contract."""


def normalize_graph(
    nodes: Iterable[str],
    relations: Iterable[GraphRelation],
    *,
    max_nodes: int,
) -> GraphDefinition:
    """Validate and canonicalize a graph without changing node text."""

    node_values = tuple(nodes)
    if not 1 <= len(node_values) <= max_nodes:
        raise GraphValidationError(
            f"nodes must contain between 1 and {max_nodes} entries"
        )
    if any(not node.strip() for node in node_values):
        raise GraphValidationError("nodes must be non-whitespace strings")
    if len(set(node_values)) != len(node_values):
        raise GraphValidationError("nodes must be exactly unique")

    normalized_nodes = tuple(sorted(node_values, key=_utf8_key))
    node_set = set(normalized_nodes)
    relation_pairs: set[tuple[str, str]] = set()
    for relation in relations:
        if relation.prerequisite not in node_set or relation.dependent not in node_set:
            raise GraphValidationError(
                "relation endpoints must be present in the node set"
            )
        relation_pairs.add((relation.prerequisite, relation.dependent))

    normalized_relations = tuple(
        GraphRelation(prerequisite=prerequisite, dependent=dependent)
        for prerequisite, dependent in sorted(
            relation_pairs, key=lambda pair: (_utf8_key(pair[0]), _utf8_key(pair[1]))
        )
    )
    return GraphDefinition(nodes=normalized_nodes, relations=normalized_relations)


def canonical_graph_json(graph: GraphDefinition) -> str:
    """Return the language-neutral compact UTF-8 JSON hash input."""

    payload = {
        "nodes": list(graph.nodes),
        "relations": [
            {"from": relation.prerequisite, "to": relation.dependent}
            for relation in graph.relations
        ],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def graph_hash(graph: GraphDefinition) -> str:
    digest = hashlib.sha256(canonical_graph_json(graph).encode("utf-8")).hexdigest()
    return f"{GRAPH_HASH_PREFIX}{digest}"


def make_pending_graph(graph: GraphDefinition) -> PendingGraph:
    return PendingGraph(
        graph_hash=graph_hash(graph),
        nodes=graph.nodes,
        relations=graph.relations,
    )


def _utf8_key(value: str) -> bytes:
    return value.encode("utf-8")

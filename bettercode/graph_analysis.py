from __future__ import annotations

from dataclasses import dataclass

from bettercode.models import NodeKind, ProjectGraph


@dataclass(slots=True)
class GraphInsights:
    cycle_node_ids: set[str]
    cycle_edge_ids: set[str]
    isolated_node_ids: set[str]
    incoming_node_ids: dict[str, list[str]]
    outgoing_node_ids: dict[str, list[str]]
    incoming_internal_counts: dict[str, int]
    outgoing_internal_counts: dict[str, int]


def analyze_graph_structure(graph: ProjectGraph) -> GraphInsights:
    all_node_ids = {node.id for node in graph.nodes}
    internal_node_ids = {
        node.id for node in graph.nodes if node.kind is not NodeKind.EXTERNAL_PACKAGE
    }
    incoming_node_ids = {node_id: [] for node_id in all_node_ids}
    outgoing_node_ids = {node_id: [] for node_id in all_node_ids}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in internal_node_ids}
    incoming_internal_counts = {node_id: 0 for node_id in internal_node_ids}
    outgoing_internal_counts = {node_id: 0 for node_id in internal_node_ids}

    internal_edges = []
    for edge in graph.edges:
        if edge.source in all_node_ids and edge.target in all_node_ids:
            outgoing_node_ids[edge.source].append(edge.target)
            incoming_node_ids[edge.target].append(edge.source)
        if edge.source not in internal_node_ids or edge.target not in internal_node_ids:
            continue
        adjacency[edge.source].append(edge.target)
        outgoing_internal_counts[edge.source] += 1
        incoming_internal_counts[edge.target] += 1
        internal_edges.append(edge)

    isolated_node_ids = {
        node_id
        for node_id in internal_node_ids
        if incoming_internal_counts[node_id] == 0 and outgoing_internal_counts[node_id] == 0
    }

    cycle_components = _find_cycle_components(adjacency)
    cycle_node_ids = {node_id for component in cycle_components for node_id in component}
    cycle_edge_ids = {
        edge.id
        for edge in internal_edges
        if any(edge.source in component and edge.target in component for component in cycle_components)
    }

    return GraphInsights(
        cycle_node_ids=cycle_node_ids,
        cycle_edge_ids=cycle_edge_ids,
        isolated_node_ids=isolated_node_ids,
        incoming_node_ids=incoming_node_ids,
        outgoing_node_ids=outgoing_node_ids,
        incoming_internal_counts=incoming_internal_counts,
        outgoing_internal_counts=outgoing_internal_counts,
    )


def _find_cycle_components(adjacency: dict[str, list[str]]) -> list[set[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[set[str]] = []

    def strongconnect(node_id: str) -> None:
        nonlocal index
        indices[node_id] = index
        lowlinks[node_id] = index
        index += 1
        stack.append(node_id)
        on_stack.add(node_id)

        for neighbor_id in adjacency[node_id]:
            if neighbor_id not in indices:
                strongconnect(neighbor_id)
                lowlinks[node_id] = min(lowlinks[node_id], lowlinks[neighbor_id])
            elif neighbor_id in on_stack:
                lowlinks[node_id] = min(lowlinks[node_id], indices[neighbor_id])

        if lowlinks[node_id] != indices[node_id]:
            return

        component: set[str] = set()
        while stack:
            member_id = stack.pop()
            on_stack.remove(member_id)
            component.add(member_id)
            if member_id == node_id:
                break
        if len(component) > 1:
            components.append(component)
            return
        only_node_id = next(iter(component))
        if only_node_id in adjacency[only_node_id]:
            components.append(component)

    for node_id in adjacency:
        if node_id not in indices:
            strongconnect(node_id)

    return components

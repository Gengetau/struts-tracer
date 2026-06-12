"""
Weighted shortest-path tracing for the Struts route graph.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import networkx as nx

from core.graph_builder import RouteGraph

DEFAULT_MAX_DEPTH = 30
MAX_PATHS_PER_QUERY = 100


class TracePath:
    def __init__(self, nodes: List[str], graph: RouteGraph) -> None:
        self.nodes = nodes
        self.graph = graph

    def __len__(self) -> int:
        return len(self.nodes)

    def labels(self) -> List[Tuple[str, str]]:
        return [(self.graph.node_type_label(node), node) for node in self.nodes]


class TraceResult:
    def __init__(self, target: str, direction: str) -> None:
        self.target = target
        self.direction = direction
        self.paths: List[TracePath] = []
        self.warnings: List[str] = []


class TracerEngine:
    def __init__(self, graph: RouteGraph, max_depth: int = DEFAULT_MAX_DEPTH) -> None:
        self.graph = graph
        self.max_depth = max_depth

    def trace_reverse(self, target_node: str, entries: List[str] = None, ignore: List[str] = None) -> TraceResult:
        """Trace backwards from a target page to likely entry points."""
        result = TraceResult(target_node, "reverse")
        target = self._resolve_target(target_node, result)
        if not target:
            return result

        filtered_graph = self.graph.g
        if ignore:
            ignore_lower = [item.lower() for item in ignore]
            nodes_to_remove = [
                node for node in filtered_graph.nodes if any(item in node.lower() for item in ignore_lower) and node != target
            ]
            if nodes_to_remove:
                filtered_graph = filtered_graph.copy()
                filtered_graph.remove_nodes_from(nodes_to_remove)
                result.warnings.append(f"Removed {len(nodes_to_remove)} ignored nodes from the graph.")

        found_paths = []
        potential_sources = []
        if entries:
            for entry in entries:
                resolved_entry = self.graph._resolve_node(entry, is_file=True)
                if filtered_graph.has_node(resolved_entry):
                    potential_sources.append(resolved_entry)

        if not potential_sources:
            potential_sources = [
                node for node in filtered_graph.nodes if filtered_graph.in_degree(node) == 0 and node.lower().endswith(".jsp")
            ]

        for source in potential_sources:
            try:
                path = nx.shortest_path(filtered_graph, source=source, target=target, weight="weight")
                if len(path) <= self.max_depth:
                    found_paths.append(path)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

        unique_paths = []
        seen = set()
        for path in found_paths:
            signature = "|".join(path)
            if signature not in seen:
                unique_paths.append(path)
                seen.add(signature)

        sorted_paths = sorted(unique_paths, key=len, reverse=True)
        for path in sorted_paths[:MAX_PATHS_PER_QUERY]:
            result.paths.append(TracePath(path, self.graph))

        if not result.paths:
            result.warnings.append("No valid route was found. Try fewer ignored nodes or a larger search depth.")

        return result

    def trace_forward(self, start_node: str, ignore: List[str] = None) -> TraceResult:
        """Trace forward from a page to all reachable JSP nodes."""
        result = TraceResult(start_node, "forward")
        source = self._resolve_target(start_node, result)
        if not source:
            return result

        filtered_graph = self.graph.g
        if ignore:
            ignore_lower = [item.lower() for item in ignore]
            nodes_to_remove = [
                node for node in self.graph.g.nodes if any(item in node.lower() for item in ignore_lower) and node != source
            ]
            if nodes_to_remove:
                filtered_graph = self.graph.g.copy()
                filtered_graph.remove_nodes_from(nodes_to_remove)

        all_paths = []
        for node in self.graph._jsp_nodes:
            if node == source or not filtered_graph.has_node(node):
                continue
            try:
                path = nx.shortest_path(filtered_graph, source=source, target=node, weight="weight")
                if len(path) <= self.max_depth:
                    all_paths.append(path)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

        for path in sorted(all_paths, key=len)[:MAX_PATHS_PER_QUERY]:
            result.paths.append(TracePath(path, self.graph))
        return result

    def _resolve_target(self, target: str, result: TraceResult) -> Optional[str]:
        if self.graph.has_node(target):
            return target

        resolved = self.graph._resolve_node(target, is_file=True)
        if self.graph.has_node(resolved):
            return resolved

        matches = self.graph.fuzzy_find(target, limit=1)
        if matches:
            return matches[0]

        result.warnings.append(f"Target was not found in the graph: {target}")
        return None

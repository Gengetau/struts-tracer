"""
Build the route graph used by the tracing engine.

The graph combines Struts XML forwards, JSP/JS source jumps, include
relationships, and JavaScript constant references. Edge weights keep
business-local paths preferred over broad global configuration links.
"""

from __future__ import annotations

import os
from typing import Dict, List, Set

import networkx as nx

from parser.source_scanner import ScanResult
from parser.xml_parser import ParseResult
from utils.regex_rules import RE_DO_SUFFIX

EDGE_JUMP = "jump"
EDGE_FORWARD = "forward"
EDGE_INCLUDE = "include"


class RouteGraph:
    def __init__(self) -> None:
        self.g = nx.DiGraph()
        self._jsp_nodes: Set[str] = set()
        self._action_nodes: Set[str] = set()
        self._case_map: Dict[str, str] = {}

    def build(self, xml_result: ParseResult, scan_result: ScanResult) -> Dict[str, int]:
        stats = {
            "jsp_nodes": 0,
            "action_nodes": 0,
            "jump_edges": 0,
            "forward_edges": 0,
            "include_edges": 0,
            "inherited_edges": 0,
            "constant_jumps": 0,
        }

        all_files = set(scan_result.jump_map.keys()) | set(scan_result.include_map.keys()) | set(scan_result.mentions.keys())
        for file_path in all_files:
            self._register_node(file_path, is_file=True)

        for parent, children in scan_result.include_map.items():
            source = self._resolve_node(parent)
            for child in children:
                target = self._resolve_node(child, is_file=child.lower().endswith((".jsp", ".js", ".inc")))
                self.g.add_edge(source, target, type=EDGE_INCLUDE, weight=self._calc_weight(source, target, EDGE_INCLUDE))
                stats["include_edges"] += 1

        for src, targets in scan_result.jump_map.items():
            source = self._resolve_node(src)
            for raw_target in targets:
                is_target_file = any(raw_target.lower().endswith(ext) for ext in [".jsp", ".js", ".inc"])
                target = self._resolve_node(raw_target, is_file=is_target_file)
                if source.lower().endswith(".jsp") and target.lower().endswith(".js"):
                    if not self.g.has_edge(source, target):
                        self.g.add_edge(source, target, type=EDGE_INCLUDE, weight=self._calc_weight(source, target, EDGE_INCLUDE))
                        stats["include_edges"] += 1
                else:
                    self.g.add_edge(source, target, type=EDGE_JUMP, weight=self._calc_weight(source, target, EDGE_JUMP))
                    stats["jump_edges"] += 1

        for src, words in scan_result.mentions.items():
            source = self._resolve_node(src)
            for word in words:
                if word in scan_result.constants:
                    real_path = scan_result.constants[word]
                    target = self._resolve_node(real_path, is_file=any(real_path.lower().endswith(ext) for ext in [".jsp", ".js", ".inc"]))
                    if source != target and not self.g.has_edge(source, target):
                        self.g.add_edge(source, target, type=EDGE_JUMP, weight=3, note=f"via {word}")
                        stats["constant_jumps"] += 1

        for action, targets in xml_result.action_forwards.items():
            source = self._resolve_node(action, is_file=False)
            for target_path in targets:
                target = self._resolve_node(target_path, is_file=True)
                self.g.add_edge(source, target, type=EDGE_FORWARD, weight=2)
                stats["forward_edges"] += 1

        for forward_name, target_path in xml_result.global_forwards.items():
            source = self._resolve_node(f"/GlobalForward:{forward_name}", is_file=False)
            target = self._resolve_node(target_path, is_file=True)
            self.g.add_edge(source, target, type=EDGE_FORWARD, weight=10)
            stats["forward_edges"] += 1

        stats["inherited_edges"] = self._count_inheritances()
        stats["jsp_nodes"] = len(self._jsp_nodes)
        stats["action_nodes"] = len(self._action_nodes)
        return stats

    def _calc_weight(self, source: str, target: str, edge_type: str) -> int:
        source_lower, target_lower = source.lower(), target.lower()
        penalty_keywords = ["define", "appport", "constant", "common"]
        if any(kw in source_lower for kw in penalty_keywords) or any(kw in target_lower for kw in penalty_keywords):
            return 100
        if self.is_action(source) or self.is_action(target):
            return 2
        source_dir, target_dir = os.path.dirname(source), os.path.dirname(target)
        if source_dir == target_dir:
            return 1
        return 5 if edge_type == EDGE_INCLUDE else 20

    def _register_node(self, path: str, is_file: bool) -> str:
        if is_file:
            self._jsp_nodes.add(path)
        else:
            self._action_nodes.add(path)
        lower_path = path.lower()
        if lower_path not in self._case_map:
            self._case_map[lower_path] = path
        return path

    def _resolve_node(self, raw_path: str, is_file: bool = True) -> str:
        path = RE_DO_SUFFIX.sub("", raw_path.strip())
        if not path.startswith("/"):
            path = "/" + path
        if path in self._jsp_nodes or path in self._action_nodes:
            return path
        lower_path = path.lower()
        if lower_path in self._case_map:
            return self._case_map[lower_path]

        all_nodes = self._jsp_nodes | self._action_nodes
        candidates = [node for node in all_nodes if node.endswith(path) or node.lower().endswith(lower_path)]
        if candidates:
            return min(candidates, key=len)

        sorted_nodes = sorted(list(all_nodes), key=len, reverse=True)
        for node in sorted_nodes:
            if path.endswith(node) or lower_path.endswith(node.lower()):
                return node
        return self._register_node(path, is_file=is_file)

    def _count_inheritances(self) -> int:
        dependency_graph = nx.DiGraph()
        for source, target, data in self.g.edges(data=True):
            if data.get("type") == EDGE_INCLUDE:
                dependency_graph.add_edge(source, target)

        count = 0
        for node in list(dependency_graph.nodes):
            try:
                for descendant in nx.descendants(dependency_graph, node):
                    for _src, target, data in self.g.out_edges(descendant, data=True):
                        if data.get("type") == EDGE_JUMP and not self.g.has_edge(node, target):
                            count += 1
            except Exception:
                continue
        return count

    def is_jsp(self, node: str) -> bool:
        return node in self._jsp_nodes

    def is_action(self, node: str) -> bool:
        return node in self._action_nodes

    def node_type_label(self, node: str) -> str:
        if self.is_jsp(node):
            return "JSP"
        if self.is_action(node):
            return "Action"
        return "?"

    def node_count(self) -> int:
        return self.g.number_of_nodes()

    def edge_count(self) -> int:
        return self.g.number_of_edges()

    def predecessors(self, node: str) -> List[str]:
        return list(self.g.predecessors(node))

    def successors(self, node: str) -> List[str]:
        return list(self.g.successors(node))

    def has_node(self, node: str) -> bool:
        return self.g.has_node(node)

    def fuzzy_find(self, keyword: str, limit: int = 20) -> List[str]:
        lowered = keyword.lower()
        matches = [node for node in self.g.nodes if lowered in node.lower()]
        return sorted(matches, key=lambda item: (len(item), item))[:limit]

"""
graph_builder.py — 构建逻辑有向图
核心策略：通过精细化权重，区分业务主干与全局配置，确保回溯链路符合人工逻辑。
"""

from __future__ import annotations
import os
from typing import Dict, List, Set, Any
import networkx as nx
from parser.xml_parser import ParseResult
from parser.source_scanner import ScanResult
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
            "jsp_nodes": 0, "action_nodes": 0, "jump_edges": 0,
            "forward_edges": 0, "include_edges": 0, "inherited_edges": 0,
            "constant_jumps": 0
        }

        # 1. 注册物理文件
        all_files = set(scan_result.jump_map.keys()) | set(scan_result.include_map.keys()) | set(scan_result.mentions.keys())
        for f in all_files: self._register_node(f, is_file=True)

        # 2. 建立包含/引用边 (JSP -> JS/JSP)
        for parent, children in scan_result.include_map.items():
            u = self._resolve_node(parent)
            for child in children:
                v = self._resolve_node(child, is_file=child.lower().endswith((".jsp", ".js", ".inc")))
                self.g.add_edge(u, v, type=EDGE_INCLUDE, weight=self._calc_weight(u, v, EDGE_INCLUDE))
                stats["include_edges"] += 1

        # 3. 建立源码跳转边 (JSP/JS -> Target)
        for src, targets in scan_result.jump_map.items():
            u = self._resolve_node(src)
            for raw_target in targets:
                is_target_file = any(raw_target.lower().endswith(ext) for ext in [".jsp", ".js", ".inc"])
                v = self._resolve_node(raw_target, is_file=is_target_file)
                # 再次确认 JSP -> JS 的关系视为 Include
                if u.lower().endswith(".jsp") and v.lower().endswith(".js"):
                    if not self.g.has_edge(u, v):
                        self.g.add_edge(u, v, type=EDGE_INCLUDE, weight=self._calc_weight(u, v, EDGE_INCLUDE))
                        stats["include_edges"] += 1
                else:
                    self.g.add_edge(u, v, type=EDGE_JUMP, weight=self._calc_weight(u, v, EDGE_JUMP))
                    stats["jump_edges"] += 1

        # 4. 常量引用解析
        for src, words in scan_result.mentions.items():
            u = self._resolve_node(src)
            for word in words:
                if word in scan_result.constants:
                    real_path = scan_result.constants[word]
                    v = self._resolve_node(real_path, is_file=any(real_path.lower().endswith(ext) for ext in [".jsp", ".js", ".inc"]))
                    if u != v and not self.g.has_edge(u, v):
                        self.g.add_edge(u, v, type=EDGE_JUMP, weight=3, note=f"via {word}")
                        stats["constant_jumps"] += 1

        # 5. XML Forward
        for action, targets in xml_result.action_forwards.items():
            u = self._resolve_node(action, is_file=False)
            for target in targets:
                v = self._resolve_node(target, is_file=True)
                self.g.add_edge(u, v, type=EDGE_FORWARD, weight=2)
                stats["forward_edges"] += 1

        # 6. Global Forward
        for fwd, target in xml_result.global_forwards.items():
            u = self._resolve_node(f"/GlobalForward:{fwd}", is_file=False)
            v = self._resolve_node(target, is_file=True)
            self.g.add_edge(u, v, type=EDGE_FORWARD, weight=10)
            stats["forward_edges"] += 1

        stats["inherited_edges"] = self._count_inheritances()
        stats["jsp_nodes"] = len(self._jsp_nodes)
        stats["action_nodes"] = len(self._action_nodes)
        return stats

    def _calc_weight(self, u: str, v: str, edge_type: str) -> int:
        u_lower, v_lower = u.lower(), v.lower()
        penalty_keywords = ["define", "appport", "constant", "common"]
        if any(kw in u_lower for kw in penalty_keywords) or any(kw in v_lower for kw in penalty_keywords):
            return 100
        if self.is_action(u) or self.is_action(v): return 2
        u_dir, v_dir = os.path.dirname(u), os.path.dirname(v)
        if u_dir == v_dir: return 1
        return 5 if edge_type == EDGE_INCLUDE else 20

    def _register_node(self, path: str, is_file: bool) -> str:
        if is_file: self._jsp_nodes.add(path)
        else: self._action_nodes.add(path)
        lower_p = path.lower()
        if lower_p not in self._case_map: self._case_map[lower_p] = path
        return path

    def _resolve_node(self, raw_path: str, is_file: bool = True) -> str:
        p = RE_DO_SUFFIX.sub("", raw_path.strip())
        if not p.startswith("/"): p = "/" + p
        if p in self._jsp_nodes or p in self._action_nodes: return p
        lower_p = p.lower()
        if lower_p in self._case_map: return self._case_map[lower_p]
        all_nodes = self._jsp_nodes | self._action_nodes
        candidates = [n for n in all_nodes if n.endswith(p) or n.lower().endswith(lower_p)]
        if candidates: return min(candidates, key=len)
        sorted_nodes = sorted(list(all_nodes), key=len, reverse=True)
        for node in sorted_nodes:
            if p.endswith(node) or lower_p.endswith(node.lower()): return node
        return self._register_node(p, is_file=is_file)

    def _count_inheritances(self) -> int:
        dep_graph = nx.DiGraph()
        for u, v, d in self.g.edges(data=True):
            if d.get("type") == EDGE_INCLUDE: dep_graph.add_edge(u, v)
        count = 0
        for node in list(dep_graph.nodes):
            try:
                for desc in nx.descendants(dep_graph, node):
                    for _, target, d in self.g.out_edges(desc, data=True):
                        if d.get("type") == EDGE_JUMP and not self.g.has_edge(node, target):
                            count += 1
            except Exception: continue
        return count

    def is_jsp(self, node: str) -> bool: return node in self._jsp_nodes
    def is_action(self, node: str) -> bool: return node in self._action_nodes
    def node_type_label(self, node: str) -> str:
        if self.is_jsp(node): return "JSP"
        if self.is_action(node): return "Action"
        return "?"
    def node_count(self) -> int: return self.g.number_of_nodes()
    def edge_count(self) -> int: return self.g.number_of_edges()
    def predecessors(self, node: str) -> List[str]: return list(self.g.predecessors(node))
    def successors(self, node: str) -> List[str]: return list(self.g.successors(node))
    def has_node(self, node: str) -> bool: return self.g.has_node(node)
    def fuzzy_find(self, keyword: str, limit: int = 20) -> List[str]:
        kw = keyword.lower()
        matches = [n for n in self.g.nodes if kw in n.lower()]
        return sorted(matches, key=lambda x: (len(x), x))[:limit]

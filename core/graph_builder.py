"""
graph_builder.py — 构建逻辑有向图
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
        }

        # 1. 预载所有扫描到的物理文件
        all_files = set(scan_result.jump_map.keys()) | set(scan_result.include_map.keys())
        for f in all_files: self._register_node(f, is_jsp=True)

        # 2. 建立显式/隐式引用边 (Include/Script)
        for parent, children in scan_result.include_map.items():
            u = self._resolve_node(parent)
            for child in children:
                v = self._resolve_node(child, is_jsp=child.lower().endswith(".jsp"))
                self.g.add_edge(u, v, type=EDGE_INCLUDE, weight=self._calc_weight(u, v))
                stats["include_edges"] += 1

        # 3. 建立源码跳转边 (JSP/JS -> Target)
        for src, targets in scan_result.jump_map.items():
            u = self._resolve_node(src)
            for raw_target in targets:
                # 判断目标是 Action 还是可能存在的内联 JSP
                is_jsp = raw_target.lower().endswith(".jsp")
                v = self._resolve_node(raw_target, is_jsp=is_jsp)
                # 如果 src 是 JSP 且目标是 JS，视为 Include
                if u.lower().endswith(".jsp") and v.lower().endswith(".js"):
                    self.g.add_edge(u, v, type=EDGE_INCLUDE, weight=self._calc_weight(u, v))
                    stats["include_edges"] += 1
                else:
                    self.g.add_edge(u, v, type=EDGE_JUMP, weight=self._calc_weight(u, v))
                    stats["jump_edges"] += 1

        # 4. 建立 XML Forward 边
        for action, targets in xml_result.action_forwards.items():
            u = self._resolve_node(action, is_jsp=False)
            for target in targets:
                v = self._resolve_node(target, is_jsp=True)
                self.g.add_edge(u, v, type=EDGE_FORWARD, weight=self._calc_weight(u, v))
                stats["forward_edges"] += 1

        # 5. 全局 Forward
        for fwd, target in xml_result.global_forwards.items():
            u = self._resolve_node(f"/GlobalForward:{fwd}", is_jsp=False)
            v = self._resolve_node(target, is_jsp=True)
            self.g.add_edge(u, v, type=EDGE_FORWARD, weight=self._calc_weight(u, v))
            stats["forward_edges"] += 1

        stats["inherited_edges"] = self._count_inheritances()
        stats["jsp_nodes"] = len(self._jsp_nodes)
        stats["action_nodes"] = len(self._action_nodes)
        return stats

    def _calc_weight(self, u: str, v: str) -> int:
        # 同目录权重 1，跨目录权重 10，Action 权重 2
        if self.is_action(u) or self.is_action(v): return 2
        u_dir = os.path.dirname(u)
        v_dir = os.path.dirname(v)
        return 1 if u_dir == v_dir else 10

    def _register_node(self, path: str, is_jsp: bool) -> str:
        if is_jsp: self._jsp_nodes.add(path)
        else: self._action_nodes.add(path)
        lower_p = path.lower()
        if lower_p not in self._case_map: self._case_map[lower_p] = path
        return path

    def _resolve_node(self, raw_path: str, is_jsp: bool = True) -> str:
        p = RE_DO_SUFFIX.sub("", raw_path.strip())
        if not p.startswith("/"): p = "/" + p
        if p in self._jsp_nodes or p in self._action_nodes: return p
        lower_p = p.lower()
        if lower_p in self._case_map: return self._case_map[lower_p]
        
        all_nodes = self._jsp_nodes | self._action_nodes
        # 跨目录后缀对齐
        candidates = [n for n in all_nodes if n.endswith(p) or n.lower().endswith(lower_p)]
        if candidates: return min(candidates, key=len)
        # 逆向对齐
        sorted_nodes = sorted(list(all_nodes), key=len, reverse=True)
        for node in sorted_nodes:
            if p.endswith(node) or lower_p.endswith(node.lower()): return node
        
        return self._register_node(p, is_jsp=is_jsp)

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

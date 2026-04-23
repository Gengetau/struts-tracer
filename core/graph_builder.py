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
            "forward_edges": 0, "include_edges": 0, "constant_jumps": 0
        }

        # 1. 注册物理文件
        all_files = set(scan_result.jump_map.keys()) | set(scan_result.include_map.keys()) | set(scan_result.mentions.keys())
        for f in all_files: self._register_node(f, is_jsp=True)

        # 2. 建立包含/引用边 (JSP -> JS/JSP)
        for parent, children in scan_result.include_map.items():
            u = self._resolve_node(parent)
            for child in children:
                v = self._resolve_node(child, is_jsp=child.lower().endswith(".jsp"))
                self.g.add_edge(u, v, type=EDGE_INCLUDE, weight=self._calc_weight(u, v, EDGE_INCLUDE))
                stats["include_edges"] += 1

        # 3. 建立源码跳转边 (JSP/JS -> Target)
        for src, targets in scan_result.jump_map.items():
            u = self._resolve_node(src)
            for raw_target in targets:
                is_jsp = raw_target.lower().endswith(".jsp")
                v = self._resolve_node(raw_target, is_jsp=is_jsp)
                # 再次确认 JSP -> JS 的关系视为 Include
                if u.lower().endswith(".jsp") and v.lower().endswith(".js"):
                    self.g.add_edge(u, v, type=EDGE_INCLUDE, weight=self._calc_weight(u, v, EDGE_INCLUDE))
                else:
                    self.g.add_edge(u, v, type=EDGE_JUMP, weight=self._calc_weight(u, v, EDGE_JUMP))
                    stats["jump_edges"] += 1

        # 4. 常量引用解析 (把 NAME 映射回 PATH)
        for src, words in scan_result.mentions.items():
            u = self._resolve_node(src)
            for word in words:
                if word in scan_result.constants:
                    real_path = scan_result.constants[word]
                    v = self._resolve_node(real_path, is_jsp=real_path.lower().endswith(".jsp"))
                    if u != v and not self.g.has_edge(u, v):
                        # 常量调用的权重设为中等，但高于同目录跳转
                        self.g.add_edge(u, v, type=EDGE_JUMP, weight=3, note=f"via {word}")
                        stats["constant_jumps"] += 1

        # 5. XML Forward
        for action, targets in xml_result.action_forwards.items():
            u = self._resolve_node(action, is_jsp=False)
            for target in targets:
                v = self._resolve_node(target, is_jsp=True)
                self.g.add_edge(u, v, type=EDGE_FORWARD, weight=2)
                stats["forward_edges"] += 1

        # 6. Global Forward
        for fwd, target in xml_result.global_forwards.items():
            u = self._resolve_node(f"/GlobalForward:{fwd}", is_jsp=False)
            v = self._resolve_node(target, is_jsp=True)
            self.g.add_edge(u, v, type=EDGE_FORWARD, weight=10)
            stats["forward_edges"] += 1

        stats["jsp_nodes"] = len(self._jsp_nodes)
        stats["action_nodes"] = len(self._action_nodes)
        return stats

    def _calc_weight(self, u: str, v: str, edge_type: str) -> int:
        """
        计算边权重：
        - 同一目录下：1 (核心业务主干)
        - 跨目录：
            - Include: 5
            - Jump: 20 (极力避免跨目录跳转作为回溯路径)
        - 涉及全局配置文件：
            - 如果 u 或 v 包含 "define", "appport", "constant", "common"：给一个巨大的惩罚值 100
        """
        u_lower = u.lower()
        v_lower = v.lower()
        
        # 惩罚全局配置文件，防止它们成为链路中的“捷径”
        penalty_keywords = ["define", "appport", "constant", "common"]
        if any(kw in u_lower for kw in penalty_keywords) or any(kw in v_lower for kw in penalty_keywords):
            return 100

        if self.is_action(u) or self.is_action(v):
            return 2
        
        u_dir = os.path.dirname(u)
        v_dir = os.path.dirname(v)
        
        if u_dir == v_dir:
            return 1
        
        return 5 if edge_type == EDGE_INCLUDE else 20

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
        candidates = [n for n in all_nodes if n.endswith(p) or n.lower().endswith(lower_p)]
        if candidates: return min(candidates, key=len)
        sorted_nodes = sorted(list(all_nodes), key=len, reverse=True)
        for node in sorted_nodes:
            if p.endswith(node) or lower_p.endswith(node.lower()): return node
        return self._register_node(p, is_jsp=is_jsp)

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

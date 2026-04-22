"""
graph_builder.py — 构建有向图
支持节点路径融合与递归 Include 继承。
"""

from __future__ import annotations
from typing import Dict, List, Set
import networkx as nx
from parser.xml_parser import ParseResult
from parser.source_scanner import ScanResult

EDGE_JUMP = "jump"
EDGE_FORWARD = "forward"
EDGE_INCLUDE = "include"

class RouteGraph:
    def __init__(self) -> None:
        self.g = nx.DiGraph()
        self._jsp_nodes: Set[str] = set()
        self._action_nodes: Set[str] = set()

    def build(self, xml_result: ParseResult, scan_result: ScanResult) -> Dict[str, int]:
        stats = {
            "jsp_nodes": 0, "action_nodes": 0, "jump_edges": 0,
            "forward_edges": 0, "include_edges": 0, "inherited_edges": 0,
        }

        # 1. 预载所有扫描到的 JSP 节点
        for jsp in scan_result.jump_map: self._jsp_nodes.add(jsp)
        for jsp in scan_result.include_map: self._jsp_nodes.add(jsp)

        # 2. JSP -> Target (Source Jump)
        for jsp, targets in scan_result.jump_map.items():
            for target in targets:
                # 尝试解析目标是 JSP 还是 Action
                if target.lower().endswith(".jsp"):
                    real_target = self._resolve_jsp_node(target)
                    self.g.add_edge(jsp, real_target, type=EDGE_JUMP)
                else:
                    self._action_nodes.add(target)
                    self.g.add_edge(jsp, target, type=EDGE_JUMP)
                stats["jump_edges"] += 1

        # 3. Action -> JSP (XML Forward)
        for action, targets in xml_result.action_forwards.items():
            self._action_nodes.add(action)
            for xml_jsp in targets:
                real_jsp = self._resolve_jsp_node(xml_jsp)
                self._jsp_nodes.add(real_jsp)
                self.g.add_edge(action, real_jsp, type=EDGE_FORWARD)
                stats["forward_edges"] += 1

        # 4. Global Forwards
        for fwd_name, xml_jsp in xml_result.global_forwards.items():
            node_key = f"/GlobalForward:{fwd_name}"
            self._action_nodes.add(node_key)
            real_jsp = self._resolve_jsp_node(xml_jsp)
            self._jsp_nodes.add(real_jsp)
            self.g.add_edge(node_key, real_jsp, type=EDGE_FORWARD)
            stats["forward_edges"] += 1

        # 5. Include 继承注入
        self._inject_includes(scan_result.include_map, stats)

        stats["jsp_nodes"] = len(self._jsp_nodes)
        stats["action_nodes"] = len(self._action_nodes)
        return stats

    def _resolve_jsp_node(self, path: str) -> str:
        """路径融合逻辑：处理大小写与相对路径差异"""
        if path in self._jsp_nodes: return path
        
        # 尝试忽略大小写匹配
        path_lower = path.lower()
        for node in self._jsp_nodes:
            if node.lower() == path_lower: return node
            
        # 后缀匹配 (e.g. /Login.jsp -> /docroot/jsp/Login.jsp)
        candidates = [n for n in self._jsp_nodes if n.endswith(path) or n.lower().endswith(path_lower)]
        if candidates: return min(candidates, key=len)
            
        return path

    def _inject_includes(self, include_map: Dict[str, List[str]], stats: Dict[str, int]) -> None:
        inc_graph = nx.DiGraph()
        for parent, children in include_map.items():
            p_node = self._resolve_jsp_node(parent)
            self._jsp_nodes.add(p_node)
            for child in children:
                c_node = self._resolve_jsp_node(child)
                self._jsp_nodes.add(c_node)
                inc_graph.add_edge(p_node, c_node)
                self.g.add_edge(p_node, c_node, type=EDGE_INCLUDE)
                stats["include_edges"] += 1

        inherited = 0
        for parent in list(inc_graph.nodes):
            try:
                descendants = nx.descendants(inc_graph, parent)
            except Exception: continue
            
            for desc in descendants:
                for _, target, data in list(self.g.out_edges(desc, data=True)):
                    if data.get("type") == EDGE_JUMP and not self.g.has_edge(parent, target):
                        self.g.add_edge(parent, target, type="inherited")
                        inherited += 1
        stats["inherited_edges"] = inherited

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

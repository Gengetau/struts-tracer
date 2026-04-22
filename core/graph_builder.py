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

        # 2. 建立 Include/Script 依赖关系 (JSP -> Included JSP/JS)
        # 注意：这里我们不仅处理 Include，还处理 <script src> 的依赖
        self._inject_dependencies(scan_result.include_map, stats)

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

        # 5. JSP/JS -> Target (Source Jump)
        for src_file, targets in scan_result.jump_map.items():
            # 这里 src_file 可能是 .jsp 也可能是 .js
            self._jsp_nodes.add(src_file) 
            for target in targets:
                if target.lower().endswith(".jsp"):
                    real_target = self._resolve_jsp_node(target)
                    self.g.add_edge(src_file, real_target, type=EDGE_JUMP)
                else:
                    self._action_nodes.add(target)
                    self.g.add_edge(src_file, target, type=EDGE_JUMP)
                stats["jump_edges"] += 1

        # 6. 特殊逻辑：让父级 JSP 继承子级（被 Include 的 JSP 或被引用的 JS）的跳转能力
        self._inject_inheritance(stats)

        stats["jsp_nodes"] = len(self._jsp_nodes)
        stats["action_nodes"] = len(self._action_nodes)
        return stats

    def _inject_dependencies(self, include_map: Dict[str, List[str]], stats: Dict[str, int]) -> None:
        """建立基础依赖边"""
        for parent, children in include_map.items():
            p_node = self._resolve_jsp_node(parent)
            self._jsp_nodes.add(p_node)
            for child in children:
                c_node = self._resolve_jsp_node(child)
                self._jsp_nodes.add(c_node)
                # 建立依赖边：父 -> 子
                self.g.add_edge(p_node, c_node, type=EDGE_INCLUDE)
                stats["include_edges"] += 1

    def _inject_inheritance(self, stats: Dict[str, int]) -> None:
        """递归继承注入：如果 A 引用了 B，且 B 有出边到 C，则建立 A 到 C 的虚拟边"""
        # 建立一个只有依赖关系的子图
        dep_graph = nx.DiGraph()
        for u, v, data in self.g.edges(data=True):
            if data.get("type") == EDGE_INCLUDE:
                dep_graph.add_edge(u, v)

        inherited = 0
        for parent in list(dep_graph.nodes):
            try:
                # 找到该文件所有直接或间接引用的“子件”（JSP 或 JS）
                descendants = nx.descendants(dep_graph, parent)
            except Exception: continue
            
            for desc in descendants:
                # 收集子件所有的跳转出边（Jump 到 Action 或 JSP）
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

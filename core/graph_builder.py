"""
graph_builder.py — 构建逻辑有向图
核心策略：对 Action 采用不区分大小写的匹配，对 JSP 采用路径对齐，并建立包含引用边。
"""

from __future__ import annotations
from typing import Dict, List, Set
import networkx as nx
from parser.xml_parser import ParseResult
from parser.source_scanner import ScanResult
from utils.regex_rules import RE_DO_SUFFIX

EDGE_JUMP = "jump"        # 源码跳转 (JSP/JS -> Action/JSP)
EDGE_FORWARD = "forward"  # 配置文件 (Action -> JSP)
EDGE_INCLUDE = "include"  # 引用关系 (JSP -> JS/JSP)

class RouteGraph:
    def __init__(self) -> None:
        self.g = nx.DiGraph()
        self._jsp_nodes: Set[str] = set()
        self._action_nodes: Set[str] = set()
        # 映射：不区分大小写的路径 -> 实际出现在文件系统/配置中的第一个路径
        self._case_map: Dict[str, str] = {}

    def build(self, xml_result: ParseResult, scan_result: ScanResult) -> Dict[str, int]:
        stats = {
            "jsp_nodes": 0, "action_nodes": 0, "jump_edges": 0,
            "forward_edges": 0, "include_edges": 0, "inherited_edges": 0,
        }

        # 1. 注册所有扫描到的文件节点
        all_files = set(scan_result.jump_map.keys()) | set(scan_result.include_map.keys())
        for f in all_files: self._register_node(f, is_jsp=True)

        # 2. 建立包含关系边 (JSP -> Included JSP/JS)
        for parent, children in scan_result.include_map.items():
            u = self._register_node(parent, is_jsp=True)
            for child in children:
                v = self._resolve_node(child, hint_jsp=True)
                self.g.add_edge(u, v, type=EDGE_INCLUDE)
                stats["include_edges"] += 1

        # 3. 建立源码跳转边 (JSP/JS -> Target)
        for src, targets in scan_result.jump_map.items():
            u = self._register_node(src, is_jsp=True)
            for raw_target in targets:
                # 判断目标是 Action 还是 JSP
                if raw_target.lower().endswith(".jsp"):
                    v = self._resolve_node(raw_target, hint_jsp=True)
                else:
                    v = self._resolve_node(raw_target, hint_jsp=False)
                self.g.add_edge(u, v, type=EDGE_JUMP)
                stats["jump_edges"] += 1

        # 4. 建立 XML Forward 边 (Action -> JSP)
        for action, targets in xml_result.action_forwards.items():
            u = self._resolve_node(action, hint_jsp=False)
            for target in targets:
                v = self._resolve_node(target, hint_jsp=True)
                self.g.add_edge(u, v, type=EDGE_FORWARD)
                stats["forward_edges"] += 1

        # 5. 全局 Forward
        for fwd, target in xml_result.global_forwards.items():
            u = self._resolve_node(f"/GlobalForward:{fwd}", hint_jsp=False)
            v = self._resolve_node(target, hint_jsp=True)
            self.g.add_edge(u, v, type=EDGE_FORWARD)
            stats["forward_edges"] += 1

        # 6. 注入继承边 (优化：不仅继承 Jump，还帮助回溯)
        # 我们不再单独注入大量继承边，而是让回溯引擎具备穿透 Include 的能力
        
        stats["jsp_nodes"] = len(self._jsp_nodes)
        stats["action_nodes"] = len(self._action_nodes)
        return stats

    def _register_node(self, path: str, is_jsp: bool) -> str:
        """注册节点并维护大小写映射"""
        if is_jsp: self._jsp_nodes.add(path)
        else: self._action_nodes.add(path)
        
        key = path.lower()
        if key not in self._case_map:
            self._case_map[key] = path
        return path

    def _resolve_node(self, raw_path: str, hint_jsp: bool) -> str:
        """对齐路径，处理大小写不敏感匹配"""
        # 规范化：如果是 Action，去掉 .do
        p = RE_DO_SUFFIX.sub("", raw_path)
        if not p.startswith("/"): p = "/" + p
        
        # 1. 精确匹配
        if p in self._jsp_nodes or p in self._action_nodes: return p
        
        # 2. 大小写不敏感匹配
        key = p.lower()
        if key in self._case_map:
            return self._case_map[key]
        
        # 3. 后缀匹配 (仅针对 JSP)
        if hint_jsp or p.lower().endswith(".jsp"):
            for node in self._jsp_nodes:
                if node.lower().endswith(key):
                    return node
        
        # 4. 新建 Action 节点
        return self._register_node(p, is_jsp=False)

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

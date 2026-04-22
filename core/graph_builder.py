"""
graph_builder.py — 构建逻辑有向图
核心策略：通过增强型路径融合逻辑，连接 XML 定义与源码中的各种调用变体。
"""

from __future__ import annotations
from typing import Dict, List, Set, Any
import os
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
        # 映射：路径的小写形式 -> 实际路径（用于路径融合）
        self._case_map: Dict[str, str] = {}

    def build(self, xml_result: ParseResult, scan_result: ScanResult) -> Dict[str, int]:
        stats = {
            "jsp_nodes": 0, "action_nodes": 0, "jump_edges": 0,
            "forward_edges": 0, "include_edges": 0, "inherited_edges": 0,
        }

        # 1. 注册所有扫描到的物理文件节点
        all_files = set(scan_result.jump_map.keys()) | set(scan_result.include_map.keys())
        for f in all_files: self._register_node(f, is_jsp=True)

        # 2. 建立包含关系边 (JSP -> Included JSP/JS)
        for parent, children in scan_result.include_map.items():
            u = self._resolve_node(parent)
            for child in children:
                v = self._resolve_node(child)
                self.g.add_edge(u, v, type=EDGE_INCLUDE, weight=self._calc_weight(u, v))
                stats["include_edges"] += 1

        # 3. 建立源码跳转边 (JSP/JS -> Target)
        for src, targets in scan_result.jump_map.items():
            u = self._resolve_node(src)
            for raw_target in targets:
                is_target_jsp = raw_target.lower().endswith(".jsp")
                v = self._resolve_node(raw_target, is_jsp=is_target_jsp)
                self.g.add_edge(u, v, type=EDGE_JUMP, weight=self._calc_weight(u, v))
                stats["jump_edges"] += 1

        # 4. 建立 XML Forward 边 (Action -> JSP)
        for action, targets in xml_result.action_forwards.items():
            u = self._resolve_node(action, is_jsp=False)
            for target in targets:
                v = self._resolve_node(target, is_jsp=True)
                self.g.add_edge(u, v, type=EDGE_FORWARD, weight=self._calc_weight(u, v))
                stats["forward_edges"] += 1

        # 5. 全局 Forward 处理
        for fwd, target in xml_result.global_forwards.items():
            u = self._resolve_node(f"/GlobalForward:{fwd}", is_jsp=False)
            v = self._resolve_node(target, is_jsp=True)
            self.g.add_edge(u, v, type=EDGE_FORWARD, weight=self._calc_weight(u, v))
            stats["forward_edges"] += 1

        # 6. 计算继承统计
        stats["inherited_edges"] = self._count_potential_inheritances()
        stats["jsp_nodes"] = len(self._jsp_nodes)
        stats["action_nodes"] = len(self._action_nodes)
        return stats

    def _calc_weight(self, u: str, v: str) -> int:
        """
        计算边权重以优化搜索逻辑：
        - 同一目录下：权重 1 (极高优先级)
        - 跨目录跳转：权重 10 (低优先级)
        - 涉及 Action 的跳转：权重 2 (常规优先级)
        """
        if self.is_action(u) or self.is_action(v):
            return 2
        
        u_dir = os.path.dirname(u)
        v_dir = os.path.dirname(v)
        if u_dir == v_dir:
            return 1
        return 10

    def _register_node(self, path: str, is_jsp: bool) -> str:
        """记录节点并维护路径融合映射"""
        if is_jsp: self._jsp_nodes.add(path)
        else: self._action_nodes.add(path)
        
        lower_path = path.lower()
        if lower_path not in self._case_map:
            self._case_map[lower_path] = path
        return path

    def _resolve_node(self, raw_path: str, is_jsp: bool = True) -> str:
        """
        极致路径融合算法：
        1. 规范化处理
        2. 精确与大小写不敏感匹配
        3. 增强型双向后缀匹配：
           - 源码中是 /admin/Edit 而 XML 中定义为 /Edit -> 融合
           - XML 中定义为 /WEB-INF/jsp/A.jsp 而源码中是 A.jsp -> 融合
        """
        p = RE_DO_SUFFIX.sub("", raw_path.strip())
        if not p.startswith("/"): p = "/" + p
        
        # 1. 直接匹配
        if p in self._jsp_nodes or p in self._action_nodes: return p
        lower_p = p.lower()
        if lower_p in self._case_map: return self._case_map[lower_p]
            
        # 2. 增强型后缀匹配 (核心：连接定义与调用)
        # 查找是否存在一个已知节点是当前路径的后缀，或者当前路径是已知节点的后缀
        all_nodes = self._jsp_nodes | self._action_nodes
        
        # A. 寻找包含此后缀的已知节点 (e.g., 调用 Edit.do -> 匹配 /admin/Edit)
        candidates = [n for n in all_nodes if n.endswith(p) or n.lower().endswith(lower_p)]
        if candidates:
            return min(candidates, key=len)
            
        # B. 寻找此路径包含的已知节点 (e.g., 调用 /myApp/admin/Edit.do -> 匹配 /admin/Edit)
        # 注意：这里需要从长往短匹配以保证精度
        sorted_nodes = sorted(list(all_nodes), key=len, reverse=True)
        for node in sorted_nodes:
            if p.endswith(node) or lower_p.endswith(node.lower()):
                return node
        
        # 3. 最终回退：注册为新节点
        return self._register_node(p, is_jsp=is_jsp)

    def _count_potential_inheritances(self) -> int:
        """统计通过引用关系继承的跳转能力"""
        dep_graph = nx.DiGraph()
        for u, v, d in self.g.edges(data=True):
            if d.get("type") == EDGE_INCLUDE: dep_graph.add_edge(u, v)
        
        count = 0
        for node in list(dep_graph.nodes):
            try:
                descendants = nx.descendants(dep_graph, node)
                for desc in descendants:
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

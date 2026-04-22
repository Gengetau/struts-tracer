"""
graph_builder.py — 构建逻辑有向图
核心策略：统一路径融合逻辑，支持大小写敏感性与不区分大小写的匹配，建立全谱系引用与跳转关系。
"""

from __future__ import annotations
from typing import Dict, List, Set, Any
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
                self.g.add_edge(u, v, type=EDGE_INCLUDE)
                stats["include_edges"] += 1

        # 3. 建立源码跳转边 (JSP/JS -> Target)
        for src, targets in scan_result.jump_map.items():
            u = self._resolve_node(src)
            for raw_target in targets:
                # 判定目标类型：如果是 .jsp 则视为页面，否则视为 Action
                is_target_jsp = raw_target.lower().endswith(".jsp")
                v = self._resolve_node(raw_target, is_jsp=is_target_jsp)
                self.g.add_edge(u, v, type=EDGE_JUMP)
                stats["jump_edges"] += 1

        # 4. 建立 XML Forward 边 (Action -> JSP)
        for action, targets in xml_result.action_forwards.items():
            u = self._resolve_node(action, is_jsp=False)
            for target in targets:
                v = self._resolve_node(target, is_jsp=True)
                self.g.add_edge(u, v, type=EDGE_FORWARD)
                stats["forward_edges"] += 1

        # 5. 全局 Forward 处理
        for fwd, target in xml_result.global_forwards.items():
            u = self._resolve_node(f"/GlobalForward:{fwd}", is_jsp=False)
            v = self._resolve_node(target, is_jsp=True)
            self.g.add_edge(u, v, type=EDGE_FORWARD)
            stats["forward_edges"] += 1

        # 6. 计算继承统计（虽然引擎现在动态处理，但为了展示复杂度，我们进行一次预算）
        stats["inherited_edges"] = self._count_potential_inheritances()
        stats["jsp_nodes"] = len(self._jsp_nodes)
        stats["action_nodes"] = len(self._action_nodes)
        return stats

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
        核心路径融合算法：
        1. 规范化（去 .do，补 /）
        2. 尝试精确匹配
        3. 尝试不区分大小写匹配
        4. 尝试后缀匹配（处理 /jsp/A.jsp -> /docroot/jsp/A.jsp）
        """
        p = RE_DO_SUFFIX.sub("", raw_path.strip())
        if not p.startswith("/"): p = "/" + p
        
        # 1. 精确匹配
        if p in self._jsp_nodes or p in self._action_nodes:
            return p
            
        # 2. 不区分大小写匹配 (Case-Insensitive Fusion)
        lower_p = p.lower()
        if lower_p in self._case_map:
            return self._case_map[lower_p]
            
        # 3. 后缀匹配 (用于连接 XML 中的抽象路径与磁盘上的真实路径)
        if is_jsp or lower_p.endswith(".jsp"):
            for node in self._jsp_nodes:
                if node.endswith(p) or node.lower().endswith(lower_p):
                    return node
        
        # 4. 若仍未找到，注册为新节点（通常是 Action）
        return self._register_node(p, is_jsp=is_jsp)

    def _count_potential_inheritances(self) -> int:
        """统计总共有多少跳转能力被通过 Include 关系继承了"""
        dep_graph = nx.DiGraph()
        for u, v, d in self.g.edges(data=True):
            if d.get("type") == EDGE_INCLUDE: dep_graph.add_edge(u, v)
        
        count = 0
        for node in list(dep_graph.nodes):
            try:
                descendants = nx.descendants(dep_graph, node)
                for desc in descendants:
                    # 统计子件的出边中，有多少是父件没有的
                    for _, target, d in self.g.out_edges(desc, data=True):
                        if d.get("type") == EDGE_JUMP and not self.g.has_edge(node, target):
                            count += 1
            except Exception: continue
        return count

    # ─── 查询辅助 ───
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

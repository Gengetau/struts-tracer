"""
graph_builder.py — 使用 networkx 构建路由有向图
核心逻辑：JSP ↔ Action 双向边 + Include 递归继承注入。
"""

from __future__ import annotations

from typing import Dict, List, Set

import networkx as nx

from parser.xml_parser import ParseResult
from parser.source_scanner import ScanResult


# ─── 边类型常量 ───
EDGE_JUMP = "jump"        # JSP → Action（源码跳转）
EDGE_FORWARD = "forward"  # Action → JSP（XML forward）
EDGE_INCLUDE = "include"  # JSP → JSP（Include 关系）


class RouteGraph:
    """路由有向图：封装 networkx.DiGraph 及其构建逻辑"""

    def __init__(self) -> None:
        self.g = nx.DiGraph()
        self._jsp_nodes: Set[str] = set()
        self._action_nodes: Set[str] = set()

    # ─── 构建入口 ───

    def build(
        self,
        xml_result: ParseResult,
        scan_result: ScanResult,
    ) -> Dict[str, int]:
        """
        从解析结果构建完整有向图。
        Returns: 统计信息 dict。
        """
        stats: Dict[str, int] = {
            "jsp_nodes": 0,
            "action_nodes": 0,
            "jump_edges": 0,
            "forward_edges": 0,
            "include_edges": 0,
            "inherited_edges": 0,
        }

        # ── 1. Action → JSP（XML forward / input） ──
        for action, targets in xml_result.action_forwards.items():
            self._action_nodes.add(action)
            for jsp in targets:
                self._jsp_nodes.add(jsp)
                self.g.add_edge(action, jsp, type=EDGE_FORWARD)
                stats["forward_edges"] += 1

        # ── 2. 全局 Forward（按名称匹配 Action 的 forward ref） ──
        # global forward 可被 Action 内的 <forward name="xxx"> 引用
        # 这里直接把全局 forward 当作独立 Action 节点
        for fwd_name, jsp in xml_result.global_forwards.items():
            node_key = f"/GlobalForward:{fwd_name}"
            self._action_nodes.add(node_key)
            self._jsp_nodes.add(jsp)
            self.g.add_edge(node_key, jsp, type=EDGE_FORWARD)
            stats["forward_edges"] += 1

        # ── 3. JSP → Action（源码跳转） ──
        for jsp, actions in scan_result.jump_map.items():
            self._jsp_nodes.add(jsp)
            for action in actions:
                self._action_nodes.add(action)
                self.g.add_edge(jsp, action, type=EDGE_JUMP)
                stats["jump_edges"] += 1

        # ── 4. Action → JSP (修正：映射 XML 路径到实际文件路径) ──
        # 我们已经有了从源码扫描得到的 jsp_nodes（基于实际文件路径）
        # 现在将 XML 中的目标 JSP 映射到这些实际节点上
        resolved_forward_edges = 0
        for action, targets in xml_result.action_forwards.items():
            for xml_jsp in targets:
                real_jsp = self._resolve_jsp_node(xml_jsp)
                self._jsp_nodes.add(real_jsp)
                self.g.add_edge(action, real_jsp, type=EDGE_FORWARD)
                resolved_forward_edges += 1
        stats["forward_edges"] = resolved_forward_edges

        # ── 5. 全局 Forward 映射 ──
        for fwd_name, xml_jsp in xml_result.global_forwards.items():
            node_key = f"/GlobalForward:{fwd_name}"
            self._action_nodes.add(node_key)
            real_jsp = self._resolve_jsp_node(xml_jsp)
            self._jsp_nodes.add(real_jsp)
            self.g.add_edge(node_key, real_jsp, type=EDGE_FORWARD)
            stats["forward_edges"] += 1

        # ── 6. Include 边 + 递归继承注入 ──
        self._inject_includes(scan_result.include_map, stats)

        stats["jsp_nodes"] = len(self._jsp_nodes)
        stats["action_nodes"] = len(self._action_nodes)
        return stats

    def _resolve_jsp_node(self, xml_path: str) -> str:
        """
        尝试将 XML 中的 JSP 路径 (/jsp/A.jsp) 映射到实际扫描到的节点 (/docroot/jsp/A.jsp)。
        由于内部已全小写化，这里直接进行后缀匹配。
        """
        xml_path_lower = xml_path.lower()
        if xml_path_lower in self._jsp_nodes:
            return xml_path_lower
        
        # 后缀匹配
        candidates = [n for n in self._jsp_nodes if n.endswith(xml_path_lower)]
        if candidates:
            return min(candidates, key=len)
            
        return xml_path_lower

    # ─── Include 递归继承 ───

    def _inject_includes(
        self,
        include_map: Dict[str, List[str]],
        stats: Dict[str, int],
    ) -> None:
        """
        递归处理 Include 关系：父 JSP 自动继承子 JSP 的所有跳转能力。
        """
        inc_graph = nx.DiGraph()
        for parent, children in include_map.items():
            self._jsp_nodes.add(parent)
            for child in children:
                self._jsp_nodes.add(child)
                inc_graph.add_edge(parent, child)
                self.g.add_edge(parent, child, type=EDGE_INCLUDE)
                stats["include_edges"] += 1

        # 递归继承：每个 parent 继承所有 descendant 的出边
        inherited = 0
        visited_sets: Dict[str, Set[str]] = {}

        # 1700 JSP 规模，直接使用 transitive_closure 可能太慢，
        # 我们对每个节点进行有限深度的 DFS 收集。
        for parent in list(include_map.keys()):
            # 找到该 parent 所有可达的子 JSP (transitive)
            # 使用 networkx 内置的 descendants 效率更高且自带环路处理
            try:
                descendants = nx.descendants(inc_graph, parent)
            except Exception:
                # 若图逻辑异常，回退到手动收集
                descendants = self._collect_include_descendants(parent, inc_graph, visited_sets, set())
            
            for desc in descendants:
                # desc 的出边（跳转到 Action 的边）→ 复刻到 parent
                for _, target, data in self.g.out_edges(desc, data=True):
                    if data.get("type") == EDGE_JUMP and not self.g.has_edge(parent, target):
                        self.g.add_edge(parent, target, type="inherited")
                        inherited += 1

        stats["inherited_edges"] = inherited
        stats["cycles_broken"] = 0  # networkx.descendants 自动处理环路，无需手动断开

    def _collect_include_descendants(
        self,
        jsp: str,
        inc_graph: nx.DiGraph,
        cache: Dict[str, Set[str]],
        trail: Set[str],
    ) -> Set[str]:
        """递归收集 jsp 通过 include 链可达的所有后代 JSP（不含自身）"""
        if jsp in cache:
            return cache[jsp]
        if jsp in trail:
            return set()  # 防御环路

        trail.add(jsp)
        descendants: Set[str] = set()
        for child in inc_graph.successors(jsp):
            descendants.add(child)
            descendants |= self._collect_include_descendants(child, inc_graph, cache, trail)

        trail.discard(jsp)
        cache[jsp] = descendants
        return descendants

    # ─── 查询辅助 ───

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
        """模糊搜索节点名（大小写不敏感）"""
        kw = keyword.lower()
        matches = [n for n in self.g.nodes if kw in n.lower()]
        return sorted(matches)[:limit]

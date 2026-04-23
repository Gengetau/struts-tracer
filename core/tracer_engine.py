"""
tracer_engine.py — 加权最短路径引擎
"""

from __future__ import annotations
import networkx as nx
from typing import List, Optional, Tuple, Dict, Set
from core.graph_builder import RouteGraph

DEFAULT_MAX_DEPTH = 30
MAX_PATHS_PER_QUERY = 100

class TracePath:
    def __init__(self, nodes: List[str], graph: RouteGraph) -> None:
        self.nodes = nodes
        self.graph = graph
    def __len__(self) -> int: return len(self.nodes)
    def labels(self) -> List[Tuple[str, str]]:
        return [(self.graph.node_type_label(n), n) for n in self.nodes]

class TraceResult:
    def __init__(self, target: str, direction: str) -> None:
        self.target = target
        self.direction = direction
        self.paths: List[TracePath] = []
        self.warnings: List[str] = []

class TracerEngine:
    def __init__(self, graph: RouteGraph, max_depth: int = DEFAULT_MAX_DEPTH) -> None:
        self.graph = graph
        self.max_depth = max_depth

    def trace_reverse(self, target_node: str, entries: List[str] = None, ignore: List[str] = None) -> TraceResult:
        """逆向回溯：优先使用最短路径算法提升性能"""
        result = TraceResult(target_node, "reverse")
        target = self._resolve_target(target_node, result)
        if not target: return result

        # 1. 准备过滤后的临时图谱
        g_filtered = self.graph.g
        if ignore:
            ignore_lower = [i.lower() for i in ignore]
            to_rm = [n for n in g_filtered.nodes if any(i in n.lower() for i in ignore_lower) and n != target]
            if to_rm:
                g_filtered = g_filtered.copy()
                g_filtered.remove_nodes_from(to_rm)
                result.warnings.append(f"已从图谱中屏蔽 {len(to_rm)} 个包含忽略关键字的节点。")

        all_found_paths = []

        # 2. 确定源头节点
        potential_sources = []
        if entries:
            for e in entries:
                resolved_e = self.graph._resolve_node(e, is_file=True)
                if g_filtered.has_node(resolved_e):
                    potential_sources.append(resolved_e)
        
        # 自动搜索图中入度为 0 的 JSP 节点
        if not potential_sources:
            potential_sources = [n for n in g_filtered.nodes if g_filtered.in_degree(n) == 0 and n.lower().endswith(".jsp")]

        # 3. 寻找最短路径
        for src in potential_sources:
            try:
                p = nx.shortest_path(g_filtered, source=src, target=target, weight='weight')
                if len(p) <= self.max_depth:
                    all_found_paths.append(p)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

        # 4. 去重与排序
        unique_paths = []
        seen = set()
        for p in all_found_paths:
            sig = "|".join(p)
            if sig not in seen:
                unique_paths.append(p)
                seen.add(sig)
        
        # 按长度降序排列（找最完整路径）
        sorted_paths = sorted(unique_paths, key=len, reverse=True)
        for p in sorted_paths[:MAX_PATHS_PER_QUERY]:
            result.paths.append(TracePath(p, self.graph))

        if not result.paths:
            result.warnings.append("未发现有效链路。请尝试减少屏蔽项或增加搜索深度。")

        return result

    def trace_forward(self, start_node: str, ignore: List[str] = None) -> TraceResult:
        """正向推演：使用最短路径寻找可达节点"""
        result = TraceResult(start_node, "forward")
        source = self._resolve_target(start_node, result)
        if not source: return result

        g_filtered = self.graph.g
        if ignore:
            ignore_lower = [i.lower() for i in ignore]
            nodes_to_remove = [n for n in self.graph.g.nodes if any(i in n.lower() for i in ignore_lower) and n != source]
            if nodes_to_remove:
                g_filtered = self.graph.g.copy()
                g_filtered.remove_nodes_from(nodes_to_remove)

        all_paths = []
        for node in self.graph._jsp_nodes:
            if node == source: continue
            if not g_filtered.has_node(node): continue
            try:
                path = nx.shortest_path(g_filtered, source=source, target=node, weight='weight')
                if len(path) <= self.max_depth:
                    all_paths.append(path)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
        
        for p in sorted(all_paths, key=len)[:MAX_PATHS_PER_QUERY]:
            result.paths.append(TracePath(p, self.graph))
        return result

    def _resolve_target(self, target: str, result: TraceResult) -> Optional[str]:
        if self.graph.has_node(target): return target
        resolved = self.graph._resolve_node(target, is_file=True)
        if self.graph.has_node(resolved): return resolved
        matches = self.graph.fuzzy_find(target, limit=1)
        if matches: return matches[0]
        return None

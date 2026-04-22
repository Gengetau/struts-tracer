"""
tracer_engine.py — 寻踪引擎
优化：采用 Dijkstra 加权最短路径算法，优先寻找同目录下的逻辑链路。
"""

from __future__ import annotations
import networkx as nx
from collections import deque
from typing import Dict, List, Optional, Set, Tuple
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
        """逆向回溯：使用加权最短路径算法，优先保持在同级目录"""
        result = TraceResult(target_node, "reverse")
        target = self._resolve_target(target_node, result)
        if not target: return result

        # 1. 准备过滤后的临时图谱
        g_filtered = self.graph.g
        if ignore:
            ignore_lower = [i.lower() for i in ignore]
            nodes_to_remove = [n for n in self.graph.g.nodes if any(i in n.lower() for i in ignore_lower) and n != target]
            if nodes_to_remove:
                g_filtered = self.graph.g.copy()
                g_filtered.remove_nodes_from(nodes_to_remove)
                result.warnings.append(f"已屏蔽 {len(nodes_to_remove)} 个包含忽略关键字的节点。")

        all_found_paths = []

        # 2. 尝试寻找从指定入口到目标的【加权最短路径】
        if entries:
            for e in entries:
                resolved_e = self.graph._resolve_node(e, is_jsp=True)
                if g_filtered.has_node(resolved_e):
                    try:
                        # 使用 weight='weight' 触发 Dijkstra，优先走同目录边（权重1）
                        path = nx.shortest_path(g_filtered, source=resolved_e, target=target, weight='weight')
                        if len(path) <= self.max_depth:
                            all_found_paths.append(path)
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        continue

        # 3. 如果未指定入口或未找到路径，则从目标逆向寻找最近的“根节点”
        if not all_found_paths:
            roots = [n for n in g_filtered.nodes if g_filtered.in_degree(n) == 0]
            for root in roots:
                try:
                    path = nx.shortest_path(g_filtered, source=root, target=target, weight='weight')
                    if len(path) <= self.max_depth:
                        all_found_paths.append(path)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue

        # 4. 结果去重与展示（最短权重路径优先）
        unique_paths = []
        seen = set()
        for p in all_found_paths:
            sig = "|".join(p)
            if sig not in seen:
                unique_paths.append(p)
                seen.add(sig)
        
        for p in unique_paths[:MAX_PATHS_PER_QUERY]:
            result.paths.append(TracePath(p, self.graph))

        if not result.paths:
            result.warnings.append("未发现有效链路。请检查目标页面是否确实被系统引用，或尝试减少屏蔽项。")

        return result

    def trace_forward(self, start_node: str, ignore: List[str] = None) -> TraceResult:
        """正向推演：使用加权最短路径寻找可达节点"""
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
                result.warnings.append(f"已屏蔽 {len(nodes_to_remove)} 个包含忽略关键字的节点。")

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
        resolved = self.graph._resolve_node(target, is_jsp=True)
        if self.graph.has_node(resolved): return resolved
        matches = self.graph.fuzzy_find(target, limit=1)
        if matches: return matches[0]
        return None

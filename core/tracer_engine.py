"""
tracer_engine.py — 加权最短路径引擎
"""

from __future__ import annotations
import networkx as nx
from typing import List, Optional, Tuple
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
        result = TraceResult(target_node, "reverse")
        target = self._resolve_target(target_node, result)
        if not target: return result

        g_filtered = self.graph.g
        if ignore:
            ignore_lower = [i.lower() for i in ignore]
            to_rm = [n for n in g_filtered.nodes if any(i in n.lower() for i in ignore_lower) and n != target]
            if to_rm:
                g_filtered = g_filtered.copy()
                g_filtered.remove_nodes_from(to_rm)
                result.warnings.append(f"已屏蔽 {len(to_rm)} 个节点。")

        all_paths = []
        # 1. 优先搜索指定入口
        if entries:
            for e in entries:
                res_e = self.graph._resolve_node(e, is_jsp=True)
                if g_filtered.has_node(res_e):
                    try:
                        p = nx.shortest_path(g_filtered, source=res_e, target=target, weight='weight')
                        if len(p) <= self.max_depth: all_paths.append(p)
                    except Exception: continue

        # 2. 回退：从所有 true root 回溯
        if not all_paths:
            roots = [n for n in g_filtered.nodes if g_filtered.in_degree(n) == 0]
            for r in roots:
                try:
                    p = nx.shortest_path(g_filtered, source=r, target=target, weight='weight')
                    if len(p) <= self.max_depth: all_paths.append(p)
                except Exception: continue

        seen = set()
        for p in all_paths:
            sig = "|".join(p)
            if sig not in seen:
                seen.add(sig)
                result.paths.append(TracePath(p, self.graph))
        
        result.paths = sorted(result.paths, key=len)[:MAX_PATHS_PER_QUERY]
        if not result.paths: result.warnings.append("未发现路径。")
        return result

    def trace_forward(self, start_node: str, ignore: List[str] = None) -> TraceResult:
        result = TraceResult(start_node, "forward")
        source = self._resolve_target(start_node, result)
        if not source: return result
        g_filtered = self.graph.g
        if ignore:
            ignore_lower = [i.lower() for i in ignore]
            to_rm = [n for n in g_filtered.nodes if any(i in n.lower() for i in ignore_lower) and n != source]
            if to_rm:
                g_filtered = g_filtered.copy()
                g_filtered.remove_nodes_from(to_rm)

        all_paths = []
        for n in self.graph._jsp_nodes:
            if n == source or not g_filtered.has_node(n): continue
            try:
                p = nx.shortest_path(g_filtered, source=source, target=n, weight='weight')
                if len(p) <= self.max_depth: all_paths.append(p)
            except Exception: continue
        for p in sorted(all_paths, key=len)[:MAX_PATHS_PER_QUERY]:
            result.paths.append(TracePath(p, self.graph))
        return result

    def _resolve_target(self, target: str, result: TraceResult) -> Optional[str]:
        if self.graph.has_node(target): return target
        res = self.graph._resolve_node(target, is_jsp=True)
        if self.graph.has_node(res): return res
        matches = self.graph.fuzzy_find(target, limit=1)
        return matches[0] if matches else None

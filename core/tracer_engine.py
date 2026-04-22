"""
tracer_engine.py — 双向寻踪引擎
优化：支持指定入口优先搜索，并提供单路径精简输出模式。
"""

from __future__ import annotations
from collections import deque
from typing import Dict, List, Optional, Set, Tuple
import networkx as nx
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

    def trace_reverse(self, target_node: str, entries: List[str] = None) -> TraceResult:
        result = TraceResult(target_node, "reverse")
        target = self._resolve_target(target_node, result)
        if not target: return result

        # 1. 找到所有可能的源头（入度为 0 的 JSP，或者是用户指定的 entry）
        potential_sources = []
        if entries:
            for e in entries:
                resolved_e = self.graph._resolve_node(e, is_jsp=True)
                if self.graph.has_node(resolved_e):
                    potential_sources.append(resolved_e)
        
        # 如果没有指定入口或找不到，则寻找所有入度为 0 的节点作为候选源头
        if not potential_sources:
            potential_sources = [n for n in self.graph.g.nodes if self.graph.g.in_degree(n) == 0]

        # 2. 使用 networkx 寻找所有简单路径
        # 为了性能和准确性，我们先找从 potential_sources 到 target 的路径
        all_found_paths = []
        for src in potential_sources:
            try:
                # 寻找从 src 到 target 的路径（限制深度）
                # 注意：nx.all_simple_paths 可能会很慢，对于大图，我们使用 shortest_path 的变体
                paths = nx.all_simple_paths(self.graph.g, source=src, target=target, cutoff=self.max_depth)
                for p in paths:
                    all_found_paths.append(p)
                    if len(all_found_paths) >= MAX_PATHS_PER_QUERY: break
            except nx.NetworkXNoPath:
                continue
            if len(all_found_paths) >= MAX_PATHS_PER_QUERY: break

        # 3. 如果通过 entry 到 target 的路没找到，退而求其次，执行原始的 BFS 回溯
        if not all_found_paths:
            queue = deque([(target, [target])])
            while queue:
                node, path = queue.popleft()
                if len(path) > self.max_depth: continue
                preds = list(self.graph.g.predecessors(node))
                if not preds:
                    all_found_paths.append(path[::-1])
                    continue
                for pred in preds:
                    if pred in path: continue
                    new_path = path + [pred]
                    queue.append((pred, new_path))
                if len(all_found_paths) >= MAX_PATHS_PER_QUERY: break

        # 4. 排序与去重：优先选择包含指定入口的路径，其次选最长的（最完整）
        unique_paths = []
        seen = set()
        for p in all_found_paths:
            sig = "|".join(p)
            if sig not in seen:
                unique_paths.append(p)
                seen.add(sig)
        
        # 排序规则：如果指定了 entry，含有 entry 的排前面；长度越长越完整排前面
        def path_rank(p):
            score = 0
            if entries:
                if any(e.lower() in p[0].lower() for e in entries):
                    score += 1000
            return score + len(p)

        sorted_paths = sorted(unique_paths, key=path_rank, reverse=True)
        for p in sorted_paths[:MAX_PATHS_PER_QUERY]:
            result.paths.append(TracePath(p, self.graph))

        return result

    def trace_forward(self, start_node: str) -> TraceResult:
        result = TraceResult(start_node, "forward")
        target = self._resolve_target(start_node, result)
        if not target: return result

        all_paths = []
        queue = deque([(target, [target])])
        while queue:
            node, path = queue.popleft()
            if len(path) > self.max_depth: continue
            succs = list(self.graph.g.successors(node))
            if not succs:
                all_paths.append(path)
                continue
            for succ in succs:
                if succ in path: continue
                queue.append((succ, path + [succ]))
                if len(all_paths) >= MAX_PATHS_PER_QUERY: break
        
        for p in all_paths:
            result.paths.append(TracePath(p, self.graph))
        return result

    def _resolve_target(self, target: str, result: TraceResult) -> Optional[str]:
        if self.graph.has_node(target): return target
        resolved = self.graph._resolve_node(target, is_jsp=True)
        if self.graph.has_node(resolved): return resolved
        matches = self.graph.fuzzy_find(target, limit=5)
        if matches: return matches[0]
        return None

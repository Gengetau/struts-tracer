"""
tracer_engine.py — 双向寻踪引擎
"""

from __future__ import annotations
from collections import deque
from typing import Dict, List, Optional, Set, Tuple
from core.graph_builder import RouteGraph

DEFAULT_MAX_DEPTH = 15
MAX_PATHS_PER_QUERY = 500

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

    def trace_reverse(self, target_jsp: str) -> TraceResult:
        result = TraceResult(target_jsp, "reverse")
        target = self._resolve_target(target_jsp, result)
        if not target: return result

        all_paths: List[List[str]] = []
        # 使用 BFS 寻找最短路径，避免 DFS 深度爆炸且能更早发现入口
        queue = deque([(target, [target])])
        visited_nodes: Dict[str, int] = {target: 0} # node -> min_depth

        while queue:
            node, path = queue.popleft()
            depth = len(path) - 1

            if depth >= self.max_depth:
                all_paths.append(path)
                continue

            preds = self.graph.predecessors(node)
            if not preds:
                all_paths.append(path)
                continue

            for pred in preds:
                # 允许访问同一个节点，只要路径不重复且深度在限制内
                if pred in path: continue
                
                new_path = path + [pred]
                queue.append((pred, new_path))
                if len(all_paths) > MAX_PATHS_PER_QUERY * 2: break

        # 去重 & 筛选
        seen = set()
        for p in all_paths:
            p.reverse()
            sig = "|".join(p)
            if sig not in seen:
                seen.add(sig)
                result.paths.append(TracePath(p, self.graph))
        
        result.paths = sorted(result.paths, key=len)[:MAX_PATHS_PER_QUERY]
        return result

    def trace_forward(self, start_jsp: str) -> TraceResult:
        result = TraceResult(start_jsp, "forward")
        target = self._resolve_target(start_jsp, result)
        if not target: return result

        all_paths: List[List[str]] = []
        queue = deque([(target, [target], 0)])
        while queue:
            node, path, depth = queue.popleft()
            if depth >= self.max_depth:
                all_paths.append(path)
                continue
            succs = self.graph.successors(node)
            if not succs:
                all_paths.append(path)
                continue
            for succ in succs:
                if succ in path: continue
                queue.append((succ, path + [succ], depth + 1))
                if len(all_paths) > MAX_PATHS_PER_QUERY: break
        
        for p in all_paths[:MAX_PATHS_PER_QUERY]:
            result.paths.append(TracePath(p, self.graph))
        return result

    def _resolve_target(self, target: str, result: TraceResult) -> Optional[str]:
        if self.graph.has_node(target): return target
        # 路径融合尝试
        resolved = self.graph._resolve_jsp_node(target)
        if self.graph.has_node(resolved): return resolved
        
        matches = self.graph.fuzzy_find(target, limit=5)
        if not matches:
            result.warnings.append(f"节点 '{target}' 在图中不存在。")
            return None
        return matches[0]

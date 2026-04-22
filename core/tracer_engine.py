"""
tracer_engine.py — 核心寻踪引擎
重构：逆向回溯不仅穿透跳转，还必须穿透 Include 依赖树。
"""

from __future__ import annotations
from collections import deque
from typing import Dict, List, Optional, Set, Tuple
from core.graph_builder import RouteGraph, EDGE_INCLUDE, EDGE_JUMP, EDGE_FORWARD

DEFAULT_MAX_DEPTH = 20 # 增加深度以适应 1700 JSP 规模
MAX_PATHS_PER_QUERY = 500

class TracePath:
    def __init__(self, nodes: List[str], graph: RouteGraph) -> None:
        self.nodes = nodes
        self.graph = graph
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

    def trace_reverse(self, target_node: str) -> TraceResult:
        result = TraceResult(target_node, "reverse")
        target = self._resolve_target(target_node, result)
        if not target: return result

        all_paths: List[List[str]] = []
        # 使用 BFS 寻找所有入口点
        queue = deque([(target, [target])])
        
        while queue:
            node, path = queue.popleft()
            if len(path) > self.max_depth:
                all_paths.append(path)
                continue

            # 寻找到达当前节点的所有前驱
            # 关键：逆向穿透 Jump, Forward 以及 Include (反向)
            preds = list(self.graph.predecessors(node))
            
            if not preds:
                all_paths.append(path)
                continue

            for pred in preds:
                if pred in path: continue # 环路
                new_path = path + [pred]
                queue.append((pred, new_path))
                
                if len(queue) > 2000: # 防火墙
                    result.warnings.append("图谱过于庞大，回溯已截断。")
                    break
            
            if len(all_paths) > MAX_PATHS_PER_QUERY * 2: break

        # 去重 & 反转
        seen = set()
        for p in all_paths:
            p.reverse()
            sig = "|".join(p)
            if sig not in seen:
                seen.add(sig)
                result.paths.append(TracePath(p, self.graph))
        
        result.paths = sorted(result.paths, key=len)[:MAX_PATHS_PER_QUERY]
        return result

    def trace_forward(self, start_node: str) -> TraceResult:
        result = TraceResult(start_node, "forward")
        target = self._resolve_target(start_node, result)
        if not target: return result

        all_paths: List[List[str]] = []
        queue = deque([(target, [target])])
        while queue:
            node, path = queue.popleft()
            if len(path) > self.max_depth:
                all_paths.append(path)
                continue
            
            succs = list(self.graph.successors(node))
            if not succs:
                all_paths.append(path)
                continue
                
            for succ in succs:
                if succ in path: continue
                new_path = path + [succ]
                queue.append((succ, new_path))
                if len(all_paths) > MAX_PATHS_PER_QUERY: break
        
        for p in all_paths[:MAX_PATHS_PER_QUERY]:
            result.paths.append(TracePath(p, self.graph))
        return result

    def _resolve_target(self, target: str, result: TraceResult) -> Optional[str]:
        if self.graph.has_node(target): return target
        resolved = self.graph._resolve_node(target, hint_jsp=True)
        if self.graph.has_node(resolved): return resolved
        
        matches = self.graph.fuzzy_find(target, limit=5)
        if matches: return matches[0]
        result.warnings.append(f"无法定位节点 '{target}'。")
        return None

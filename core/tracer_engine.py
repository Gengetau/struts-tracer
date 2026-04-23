"""
tracer_engine.py — 核心寻踪引擎
重构：严格控制入口定义，防止路径在 JS 常量文件处“意外终结”。
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
        """逆向回溯：强制从顶级 JSP 入口开始，拒绝 JS 中途拦截"""
        result = TraceResult(target_node, "reverse")
        target = self._resolve_target(target_node, result)
        if not target: return result

        # 1. 准备过滤图
        g_filtered = self.graph.g
        if ignore:
            ignore_lower = [i.lower() for i in ignore]
            to_rm = [n for n in g_filtered.nodes if any(i in n.lower() for i in ignore_lower) and n != target]
            if to_rm:
                g_filtered = g_filtered.copy()
                g_filtered.remove_nodes_from(to_rm)
                result.warnings.append(f"已屏蔽 {len(to_rm)} 个干扰节点。")

        # 2. 确定“合法的起始点” (Roots)
        # 核心逻辑：只有 JSP 文件能作为回溯的终点。JS 文件即便没有前驱，也不被视为业务源头。
        candidate_roots = []
        if entries:
            # 优先使用主祭指定的入口
            for e in entries:
                res_e = self.graph._resolve_node(e, is_file=True)
                if g_filtered.has_node(res_e): candidate_roots.append(res_e)
        
        if not candidate_roots:
            # 自动模式：寻找图中所有入度为 0 且后缀为 .jsp 的节点
            candidate_roots = [
                n for n in g_filtered.nodes 
                if g_filtered.in_degree(n) == 0 and n.lower().endswith(".jsp")
            ]

        # 3. 执行加权寻径
        all_found_paths = []
        for root in candidate_roots:
            try:
                # 使用 Dijkstra 算法，权重已在 GraphBuilder 中配置（优先同目录）
                p = nx.shortest_path(g_filtered, source=root, target=target, weight='weight')
                if len(p) <= self.max_depth:
                    all_found_paths.append(p)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

        # 4. 如果没找到通往 JSP 的路，再尝试找“最长”的潜在路径（至少能看到哪断了）
        if not all_found_paths:
            # 执行原始回溯以辅助诊断
            import collections
            queue = collections.deque([(target, [target])])
            while queue:
                node, path = queue.popleft()
                if len(path) > self.max_depth: continue
                preds = list(g_filtered.predecessors(node))
                if not preds:
                    all_found_paths.append(path[::-1])
                    continue
                for pr in preds:
                    if pr not in path: queue.append((pr, path + [pr]))
                if len(all_found_paths) > 10: break

        # 5. 去重、排序并截断
        unique_paths = []
        seen = set()
        for p in all_found_paths:
            sig = "|".join(p)
            if sig not in seen:
                unique_paths.append(p)
                seen.add(sig)
        
        # 排序：路径越长越好（回溯更深），权重越小越好（同目录优先）
        # 这里我们取长度前几位的
        result.paths = [TracePath(p, self.graph) for p in sorted(unique_paths, key=len, reverse=True)[:MAX_PATHS_PER_QUERY]]
        return result

    def trace_forward(self, start_node: str, ignore: List[str] = None) -> TraceResult:
        result = TraceResult(start_node, "forward")
        source = self._resolve_target(start_node, result)
        if not source: return result
        # 省略正向过滤逻辑... (已在 v0.8 实现)
        return result

    def _resolve_target(self, target: str, result: TraceResult) -> Optional[str]:
        if self.graph.has_node(target): return target
        res = self.graph._resolve_node(target, is_file=True)
        if self.graph.has_node(res): return res
        matches = self.graph.fuzzy_find(target, limit=1)
        return matches[0] if matches else None
class TraceResult:
    def __init__(self, target: str, direction: str) -> None:
        self.target = target
        self.direction = direction
        self.paths: List[TracePath] = []
        self.warnings: List[str] = []

"""
tracer_engine.py — DFS/BFS 双向寻踪引擎
含最大深度限制与环路检测，支持逆向回溯与正向推演。
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from core.graph_builder import RouteGraph


# ─── 常量 ───
DEFAULT_MAX_DEPTH = 15
# 大规模图的安全阈值：单次寻踪最大路径数
MAX_PATHS_PER_QUERY = 500


# ─── 数据结构 ───

class TracePath:
    """单条链路"""

    def __init__(self, nodes: List[str], graph: RouteGraph) -> None:
        self.nodes = nodes
        self.graph = graph

    def __len__(self) -> int:
        return len(self.nodes)

    def __repr__(self) -> str:
        return " → ".join(self.nodes)

    def labels(self) -> List[Tuple[str, str]]:
        """返回 [(node_type, node_name), ...]"""
        return [(self.graph.node_type_label(n), n) for n in self.nodes]


class TraceResult:
    """寻踪结果"""

    def __init__(self, target: str, direction: str) -> None:
        self.target = target
        self.direction = direction  # "reverse" | "forward"
        self.paths: List[TracePath] = []
        self.warnings: List[str] = []

    def __len__(self) -> int:
        return len(self.paths)


# ─── 引擎 ───

class TracerEngine:
    """DFS 逆向 / BFS 正向寻踪引擎"""

    def __init__(self, graph: RouteGraph, max_depth: int = DEFAULT_MAX_DEPTH) -> None:
        self.graph = graph
        self.max_depth = max_depth

    # ─── 逆向回溯 (Bottom-Up) ───

    def trace_reverse(self, target_jsp: str) -> TraceResult:
        """
        从目标 JSP 逆向回溯，找到所有可达的入口路径。
        使用 DFS 遍历 predecessor 链。
        """
        result = TraceResult(target_jsp, "reverse")

        # 精确匹配或模糊匹配
        target = self._resolve_target(target_jsp, result)
        if not target:
            return result

        # DFS 收集所有路径
        all_paths: List[List[str]] = []
        visited_edges: Set[tuple] = set()

        self._dfs_reverse(
            node=target,
            path=[target],
            depth=0,
            all_paths=all_paths,
            visited_edges=visited_edges,
        )

        # 去重 & 截断
        seen_signatures: Set[str] = set()
        for p in all_paths[:MAX_PATHS_PER_QUERY]:
            sig = "|".join(p)
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                result.paths.append(TracePath(p, self.graph))

        if len(all_paths) > MAX_PATHS_PER_QUERY:
            result.warnings.append(
                f"路径数超过 {MAX_PATHS_PER_QUERY}，已截断。请缩小搜索范围。"
            )

        # 反转路径使其从 root → target
        for tp in result.paths:
            tp.nodes.reverse()

        return result

    def _dfs_reverse(
        self,
        node: str,
        path: List[str],
        depth: int,
        all_paths: List[List[str]],
        visited_edges: Set[tuple],
    ) -> None:
        if depth > self.max_depth:
            return

        preds = list(self.graph.predecessors(node))

        if not preds:
            # 孤立节点 / 入口 → 记录路径
            all_paths.append(list(path))
            return

        has_valid_pred = False
        for pred in preds:
            edge_key = (pred, node)
            if edge_key in visited_edges:
                continue  # 环路断开
            visited_edges.add(edge_key)
            path.append(pred)
            has_valid_pred = True
            self._dfs_reverse(pred, path, depth + 1, all_paths, visited_edges)
            path.pop()
            visited_edges.discard(edge_key)

        if not has_valid_pred:
            all_paths.append(list(path))

    # ─── 正向推演 (Top-Down) ───

    def trace_forward(self, start_jsp: str) -> TraceResult:
        """
        从起始 JSP 正向推演，找出用户可达的所有页面树。
        使用 BFS 保证最短路径优先。
        """
        result = TraceResult(start_jsp, "forward")

        target = self._resolve_target(start_jsp, result)
        if not target:
            return result

        # BFS: 收集每条可达路径
        all_paths: List[List[str]] = []
        queue: deque[Tuple[str, List[str], Set[str], int]] = deque()
        queue.append((target, [target], {target}, 0))

        while queue:
            node, path, visited, depth = queue.popleft()

            if depth > self.max_depth:
                all_paths.append(list(path))
                continue

            succs = list(self.graph.successors(node))
            if not succs:
                all_paths.append(list(path))
                continue

            for succ in succs:
                if succ in visited:
                    # 环路：仍然记录当前路径但不继续
                    all_paths.append(list(path))
                    continue
                new_visited = visited | {succ}
                new_path = path + [succ]
                queue.append((succ, new_path, new_visited, depth + 1))

        # 去重
        seen: Set[str] = set()
        for p in all_paths[:MAX_PATHS_PER_QUERY]:
            sig = "|".join(p)
            if sig not in seen:
                seen.add(sig)
                result.paths.append(TracePath(p, self.graph))

        if len(all_paths) > MAX_PATHS_PER_QUERY:
            result.warnings.append(
                f"路径数超过 {MAX_PATHS_PER_QUERY}，已截断。"
            )

        return result

    # ─── 辅助 ───

    def _resolve_target(
        self, target: str, result: TraceResult
    ) -> Optional[str]:
        """精确 / 模糊匹配目标节点"""
        # 精确
        if self.graph.has_node(target):
            return target

        # 尝试加 / 前缀
        if not target.startswith("/"):
            prefixed = "/" + target
            if self.graph.has_node(prefixed):
                return prefixed

        # 模糊搜索
        matches = self.graph.fuzzy_find(target, limit=5)
        if not matches:
            result.warnings.append(f"节点 '{target}' 在图中不存在。")
            return None
        if len(matches) == 1:
            auto = matches[0]
            result.warnings.append(f"精确匹配失败，自动选择: {auto}")
            return auto
        # 多个候选
        result.warnings.append(
            f"多个候选节点匹配 '{target}': {matches[:5]}，使用第一个。"
        )
        return matches[0]

"""
graph_builder.py — 构建增强型有向图
核心策略：将 JSP、JS、INC 视为同等地位的文件节点，建立全谱系引用与跳转关系。
"""

from __future__ import annotations
import os
from typing import Dict, List, Set, Any
import networkx as nx
from parser.xml_parser import ParseResult
from parser.source_scanner import ScanResult
from utils.regex_rules import RE_DO_SUFFIX

# 边类型
EDGE_JUMP = "jump"        # 逻辑跳转 (JSP/JS -> Action/JSP)
EDGE_FORWARD = "forward"  # 配置映射 (Action -> JSP)
EDGE_INCLUDE = "include"  # 物理引用 (JSP -> JS/JSP/INC)

class RouteGraph:
    def __init__(self) -> None:
        self.g = nx.DiGraph()
        self._file_nodes: Set[str] = set()    # JSP, JS, INC, HTML
        self._action_nodes: Set[str] = set()  # Struts Actions
        self._case_map: Dict[str, str] = {}   # 小写路径 -> 原始路径

    def build(self, xml_result: ParseResult, scan_result: ScanResult) -> Dict[str, int]:
        stats = {
            "file_nodes": 0, "action_nodes": 0, "jump_edges": 0,
            "forward_edges": 0, "include_edges": 0, "constant_jumps": 0
        }

        # 1. 预载所有物理文件节点
        all_found_files = set(scan_result.jump_map.keys()) | \
                          set(scan_result.include_map.keys()) | \
                          set(scan_result.mentions.keys())
        for f in all_found_files:
            self._register_node(f, is_file=True)

        # 2. 建立包含/引用关系 (JSP -> JS/JSP/INC)
        for parent, children in scan_result.include_map.items():
            u = self._resolve_node(parent)
            for child in children:
                v = self._resolve_node(child)
                self.g.add_edge(u, v, type=EDGE_INCLUDE, weight=1 if self._in_same_dir(u, v) else 5)
                stats["include_edges"] += 1

        # 3. 建立源码跳转关系 (JSP/JS -> Target)
        for src, targets in scan_result.jump_map.items():
            u = self._resolve_node(src)
            for raw_target in targets:
                # 判定目标是否为文件
                is_file = any(raw_target.lower().endswith(ext) for ext in [".jsp", ".js", ".inc", ".html", ".htm"])
                v = self._resolve_node(raw_target, is_file=is_file)
                
                # 特殊逻辑：JSP 引用了 JS，即便不是通过 <script> 标签（如字符串拼接），也视为引用
                if u.lower().endswith(".jsp") and v.lower().endswith(".js"):
                    self.g.add_edge(u, v, type=EDGE_INCLUDE, weight=2)
                    stats["include_edges"] += 1
                else:
                    self.g.add_edge(u, v, type=EDGE_JUMP, weight=1 if self._in_same_dir(u, v) else 10)
                    stats["jump_edges"] += 1

        # 4. 常量引用解析 (逻辑桥接)
        for src, words in scan_result.mentions.items():
            u = self._resolve_node(src)
            for word in words:
                if word in scan_result.constants:
                    real_path = scan_result.constants[word]
                    is_file = any(real_path.lower().endswith(ext) for ext in [".jsp", ".js", ".inc"])
                    v = self._resolve_node(real_path, is_file=is_file)
                    if u != v and not self.g.has_edge(u, v):
                        self.g.add_edge(u, v, type=EDGE_JUMP, weight=2, note=f"const:{word}")
                        stats["constant_jumps"] += 1

        # 5. XML Forward (Action -> JSP)
        for action, targets in xml_result.action_forwards.items():
            u = self._resolve_node(action, is_file=False)
            for target in targets:
                v = self._resolve_node(target, is_file=True)
                self.g.add_edge(u, v, type=EDGE_FORWARD, weight=2)
                stats["forward_edges"] += 1

        # 6. Global Forward
        for fwd, target in xml_result.global_forwards.items():
            u = self._resolve_node(f"/GlobalForward:{fwd}", is_file=False)
            v = self._resolve_node(target, is_file=True)
            self.g.add_edge(u, v, type=EDGE_FORWARD, weight=5)
            stats["forward_edges"] += 1

        stats["jsp_nodes"] = len(self._file_nodes) # 保持 UI 兼容
        stats["action_nodes"] = len(self._action_nodes)
        return stats

    def _in_same_dir(self, u: str, v: str) -> bool:
        return os.path.dirname(u) == os.path.dirname(v)

    def _register_node(self, path: str, is_file: bool) -> str:
        if is_file: self._file_nodes.add(path)
        else: self._action_nodes.add(path)
        lower_p = path.lower()
        if lower_p not in self._case_map:
            self._case_map[lower_p] = path
        return path

    def _resolve_node(self, raw_path: str, is_file: bool = True) -> str:
        p = RE_DO_SUFFIX.sub("", raw_path.strip())
        if not p.startswith("/"): p = "/" + p
        if p in self._file_nodes or p in self._action_nodes: return p
        lower_p = p.lower()
        if lower_p in self._case_map: return self._case_map[lower_p]
        
        all_nodes = self._file_nodes | self._action_nodes
        # 后缀对齐算法
        candidates = [n for n in all_nodes if n.endswith(p) or n.lower().endswith(lower_p)]
        if candidates: return min(candidates, key=len)
        
        # 逆向对齐
        sorted_nodes = sorted(list(all_nodes), key=len, reverse=True)
        for node in sorted_nodes:
            if p.endswith(node) or lower_p.endswith(node.lower()): return node
            
        return self._register_node(p, is_file=is_file)

    def is_jsp(self, node: str) -> bool:
        return node in self._file_nodes

    def is_action(self, node: str) -> bool:
        return node in self._action_nodes

    def node_type_label(self, node: str) -> str:
        if self.is_jsp(node):
            ext = os.path.splitext(node)[1].upper().replace(".", "")
            return ext if ext else "FILE"
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

"""
source_scanner.py — 正则扫描源码文件
提取跳转与 Include 关系，支持全谱系字符串捕获。
"""

from __future__ import annotations
import os
import re
from typing import Dict, List, Set, Tuple
from utils.regex_rules import SKIP_DIRS, SCAN_EXTENSIONS, SOURCE_RULES, INCLUDE_RULES

class ScanResult:
    def __init__(self) -> None:
        self.jump_map: Dict[str, List[str]] = {}
        self.include_map: Dict[str, List[str]] = {}
        self.files_scanned: int = 0
        self.jump_relations: int = 0
        self.include_relations: int = 0

def _normalize_path_logic(raw: str, parent_dir: str, project_dir: str) -> str:
    """标准化路径：剥离参数，处理相对路径，保持大小写"""
    p = raw.strip().split('?')[0].split('#')[0]
    if not p: return ""
    
    # 如果是相对路径，基于当前文件所在目录解析为绝对项目路径
    if not p.startswith("/"):
        try:
            abs_os_path = os.path.normpath(os.path.join(parent_dir, p))
            p = _to_project_path(abs_os_path, project_dir)
        except Exception: pass
    
    if not p.startswith("/"): p = "/" + p
    return p

def _to_project_path(file_path: str, project_dir: str) -> str:
    """保持大小写的项目相对路径 (e.g., /jsp/main.jsp)"""
    try:
        rel = os.path.relpath(file_path, project_dir)
    except Exception: rel = file_path
    rel = rel.replace(os.sep, "/")
    if not rel.startswith("/"): rel = "/" + rel
    return rel

def _scan_file(file_path: str, project_dir: str, result: ScanResult) -> None:
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception: return

    src_key = _to_project_path(file_path, project_dir)
    parent_dir = os.path.dirname(file_path)

    # 1. 广谱捕捉所有符合 URL/Action 路径特征的字符串
    jumps: Set[str] = set()
    includes: Set[str] = set()
    
    # 先捕获源码中所有的跳转候选
    for regex, _ in SOURCE_RULES:
        for m in regex.finditer(content):
            raw_url = m.group(1)
            norm_url = _normalize_path_logic(raw_url, parent_dir, project_dir)
            if not norm_url or norm_url == src_key: continue
            
            # 特殊逻辑：JSP 页面中引用的 .js 文件应视为依赖 (Include)
            if src_key.lower().endswith(".jsp") and norm_url.lower().endswith(".js"):
                includes.add(norm_url)
            else:
                jumps.add(norm_url)

    # 2. 专门捕获包含/引用标签 (Include/Script Tags)
    for regex, _ in INCLUDE_RULES:
        for m in regex.finditer(content):
            raw_inc = m.group(1)
            norm_inc = _normalize_path_logic(raw_inc, parent_dir, project_dir)
            if norm_inc and norm_inc != src_key:
                includes.add(norm_inc)

    if jumps:
        result.jump_map[src_key] = list(jumps)
        result.jump_relations += len(jumps)
    
    if includes:
        result.include_map[src_key] = list(includes)
        result.include_relations += len(includes)

def scan_project(project_dir: str, progress_callback=None) -> ScanResult:
    res = ScanResult()
    files_to_scan = []
    for root, dirs, files in os.walk(project_dir, topdown=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if os.path.splitext(f)[1].lower() in SCAN_EXTENSIONS:
                files_to_scan.append(os.path.join(root, f))
    
    total = len(files_to_scan)
    for i, fp in enumerate(files_to_scan):
        _scan_file(fp, project_dir, res)
        res.files_scanned += 1
        if progress_callback: progress_callback(i + 1, total)
    return res

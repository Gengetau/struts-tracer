"""
source_scanner.py — 源码扫描
核心逻辑：保持大小写，内部匹配采用对齐后的路径。
"""

from __future__ import annotations
import os
import re
from typing import Dict, List, Set, Tuple
from utils.regex_rules import SKIP_DIRS, SCAN_EXTENSIONS, SOURCE_RULES, INCLUDE_RULES, RE_DO_SUFFIX

class ScanResult:
    def __init__(self) -> None:
        self.jump_map: Dict[str, List[str]] = {}
        self.include_map: Dict[str, List[str]] = {}
        self.files_scanned: int = 0
        self.jump_relations: int = 0
        self.include_relations: int = 0

def _normalize_path(raw: str, parent_dir: str, project_dir: str) -> str:
    """标准化路径：剥离参数，处理相对路径，保留大小写"""
    p = raw.strip().split('?')[0].split('#')[0]
    if not p: return ""
    
    # 相对路径转换
    if not p.startswith("/"):
        abs_os_path = os.path.normpath(os.path.join(parent_dir, p))
        p = _to_project_path(abs_os_path, project_dir)
    
    if not p.startswith("/"): p = "/" + p
    return p

def _to_project_path(file_path: str, project_dir: str) -> str:
    """保持大小写的项目相对路径"""
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

    # 1. 跳转提取
    jumps: Set[str] = set()
    includes: Set[str] = set()
    
    for regex, _ in SOURCE_RULES:
        for m in regex.finditer(content):
            raw_url = m.group(1)
            url = _normalize_path(raw_url, parent_dir, project_dir)
            if not url or url == src_key: continue
            
            # 如果是 JSP 引用了 JS 文件，归类为 Include
            if src_key.lower().endswith(".jsp") and url.lower().endswith(".js"):
                includes.add(url)
            else:
                jumps.add(url)

    if jumps:
        result.jump_map[src_key] = list(jumps)
        result.jump_relations += len(jumps)

    # 2. 显式引用提取 (Include/Script Tags)
    for regex, _ in INCLUDE_RULES:
        for m in regex.finditer(content):
            url = _normalize_path(m.group(1), parent_dir, project_dir)
            if url and url != src_key: includes.add(url)
            
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

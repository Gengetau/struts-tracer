"""
source_scanner.py — 源码扫描
核心逻辑：提取路径、Include 关系、以及路径常量的定义与引用。
"""

from __future__ import annotations
import os
import re
from typing import Dict, List, Set, Tuple
from utils.regex_rules import SKIP_DIRS, SCAN_EXTENSIONS, SOURCE_RULES, INCLUDE_RULES, RE_CONST_DEF

class ScanResult:
    def __init__(self) -> None:
        self.jump_map: Dict[str, List[str]] = {}
        self.include_map: Dict[str, List[str]] = {}
        # NAME -> REAL_PATH
        self.constants: Dict[str, str] = {}
        # FILE -> Set of potential constant identifiers used
        self.mentions: Dict[str, Set[str]] = {}
        self.files_scanned: int = 0
        self.jump_relations: int = 0
        self.include_relations: int = 0

def _normalize_path(raw: str, parent_dir: str, project_dir: str) -> str:
    p = raw.strip().split('?')[0].split('#')[0]
    if not p: return ""
    if not p.startswith("/"):
        try:
            abs_os_path = os.path.normpath(os.path.join(parent_dir, p))
            p = _to_project_path(abs_os_path, project_dir)
        except Exception: pass
    if not p.startswith("/"): p = "/" + p
    return p

def _to_project_path(file_path: str, project_dir: str) -> str:
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

    # 1. 提取常量定义 (NAME = "/path")
    # 记录哪些路径是被定义为常量的，这样我们可以从跳转图中排除掉定义者本身（防止它成为终点）
    defined_paths_in_file = set()
    for m in RE_CONST_DEF.finditer(content):
        name = m.group(1)
        raw_val = m.group(2)
        norm_val = _normalize_path(raw_val, parent_dir, project_dir)
        if norm_val:
            result.constants[name] = norm_val
            defined_paths_in_file.add(norm_val)

    # 2. 跳转提取
    jumps: Set[str] = set()
    includes: Set[str] = set()
    for regex, _ in SOURCE_RULES:
        for m in regex.finditer(content):
            url = _normalize_path(m.group(1), parent_dir, project_dir)
            if not url or url == src_key: continue
            # 过滤：如果是本文件定义的常量路径，不作为本文件的跳转出边（防止定义文件被误认为业务入口）
            if url in defined_paths_in_file: continue
            
            if src_key.lower().endswith(".jsp") and url.lower().endswith(".js"):
                includes.add(url)
            else:
                jumps.add(url)

    # 3. 显式标签引用
    for regex, _ in INCLUDE_RULES:
        for m in regex.finditer(content):
            url = _normalize_path(m.group(1), parent_dir, project_dir)
            if url and url != src_key: includes.add(url)

    # 4. 捕捉所有可能的标识符（用于常量匹配）
    # 查找所有单词，后续在图构建时匹配 constants 字典
    possible_identifiers = set(re.findall(r"\b[a-zA-Z_]\w*\b", content))
    if possible_identifiers:
        result.mentions[src_key] = possible_identifiers

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

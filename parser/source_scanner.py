"""
source_scanner.py — 正则扫描源码文件
提取跳转与 Include 关系，支持全谱系字符串捕获与常量定义识别。
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
        # 新增：常量定义映射 NAME -> PATH
        self.constants: Dict[str, str] = {}
        # 新增：文件提及的单词，用于常量解析
        self.mentions: Dict[str, Set[str]] = {}
        self.files_scanned: int = 0
        self.jump_relations: int = 0
        self.include_relations: int = 0

def _normalize_path_logic(raw: str, parent_dir: str, project_dir: str) -> str:
    """标准化路径：剥离参数，处理相对路径，保持大小写"""
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

    # 1. 广谱捕捉跳转
    jumps: Set[str] = set()
    includes: Set[str] = set()
    
    for regex, _ in SOURCE_RULES:
        for m in regex.finditer(content):
            raw_url = m.group(1)
            norm_url = _normalize_path_logic(raw_url, parent_dir, project_dir)
            if not norm_url or norm_url == src_key: continue
            
            if src_key.lower().endswith(".jsp") and norm_url.lower().endswith(".js"):
                includes.add(norm_url)
            else:
                jumps.add(norm_url)

    # 2. 专门捕获包含标签
    for regex, _ in INCLUDE_RULES:
        for m in regex.finditer(content):
            raw_inc = m.group(1)
            norm_inc = _normalize_path_logic(raw_inc, parent_dir, project_dir)
            if norm_inc and norm_inc != src_key:
                includes.add(norm_inc)

    # 3. 提取常量定义 (NAME = "/path")
    for m in RE_CONST_DEF.finditer(content):
        name = m.group(1)
        raw_val = m.group(2)
        norm_val = _normalize_path_logic(raw_val, parent_dir, project_dir)
        if norm_val:
            result.constants[name] = norm_val

    # 4. 提取文件提及的所有可能常量名的单词 (全大写+蛇形)
    # 这一步是为了后续在 Graph 层面建立虚拟边
    all_words = set(re.findall(r"\b[A-Z_][A-Z0-9_]{2,}\b", content))
    if all_words:
        result.mentions[src_key] = all_words

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

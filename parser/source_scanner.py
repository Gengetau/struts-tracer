"""
source_scanner.py — 正则扫描源代码文件
提取跳转与 Include 关系，支持路径规范化与大小写保持。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from utils.regex_rules import (
    SKIP_DIRS,
    SCAN_EXTENSIONS,
    SOURCE_RULES,
    INCLUDE_RULES,
    RE_DO_SUFFIX,
)


# ─── 数据结构 ───

class ScanResult:
    def __init__(self) -> None:
        self.jump_map: Dict[str, List[str]] = {}
        self.include_map: Dict[str, List[str]] = {}
        self.files_scanned: int = 0
        self.jump_relations: int = 0
        self.include_relations: int = 0


def _normalize_path_logic(raw: str, parent_dir: str, project_dir: str) -> str:
    """
    统一路径处理逻辑：
    1. 剥离查询参数
    2. 如果是 .do，去后缀
    3. 如果是相对路径，基于 parent_dir 转换为项目相对绝对路径
    4. 确保以 / 开头
    """
    # 1. 剥离参数
    p = raw.strip().split('?')[0].split('#')[0]
    if not p:
        return ""

    # 2. .do 处理
    p = RE_DO_SUFFIX.sub("", p)

    # 3. 相对路径转绝对项目路径
    if not p.startswith("/"):
        # 计算 OS 绝对路径
        abs_os_path = os.path.normpath(os.path.join(parent_dir, p))
        # 转回项目相对路径
        p = _to_project_path(abs_os_path, project_dir)
    
    if not p.startswith("/"):
        p = "/" + p
        
    return p


def _to_project_path(file_path: str, project_dir: str) -> str:
    """转换为项目相对路径（保持大小写）"""
    try:
        rel = os.path.relpath(file_path, project_dir)
    except ValueError:
        rel = file_path
    rel = rel.replace(os.sep, "/")
    if not rel.startswith("/"):
        rel = "/" + rel
    return rel


def _scan_file(
    file_path: str,
    project_dir: str,
    result: ScanResult,
) -> None:
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return

    src_key = _to_project_path(file_path, project_dir)
    parent_dir = os.path.dirname(file_path)

    # ── 跳转提取 ──
    targets: Set[str] = set()
    for regex, _desc in SOURCE_RULES:
        for m in regex.finditer(content):
            raw_url = m.group(1)
            norm_url = _normalize_path_logic(raw_url, parent_dir, project_dir)
            if norm_url and norm_url != src_key:
                targets.add(norm_url)

    if targets:
        existing = result.jump_map.setdefault(src_key, [])
        for t in targets:
            if t not in existing:
                existing.append(t)
        result.jump_relations += len(targets)

    # ── Include 提取 ──
    includes: Set[str] = set()
    for regex, _desc in INCLUDE_RULES:
        for m in regex.finditer(content):
            raw_inc = m.group(1)
            norm_inc = _normalize_path_logic(raw_inc, parent_dir, project_dir)
            if norm_inc and norm_inc != src_key:
                includes.add(norm_inc)

    if includes:
        existing = result.include_map.setdefault(src_key, [])
        for inc in includes:
            if inc not in existing:
                existing.append(inc)
        result.include_relations += len(includes)


def scan_project(project_dir: str, progress_callback=None) -> ScanResult:
    result = ScanResult()
    project_dir = os.path.abspath(project_dir)

    all_files = []
    for root, dirs, files in os.walk(project_dir, topdown=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SCAN_EXTENSIONS:
                all_files.append(os.path.join(root, fname))

    total = len(all_files)
    for i, file_path in enumerate(all_files):
        _scan_file(file_path, project_dir, result)
        result.files_scanned += 1
        if progress_callback:
            progress_callback(i + 1, total)

    return result

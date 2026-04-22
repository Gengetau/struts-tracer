"""
source_scanner.py — 正则扫描 JSP / JS / INC 文件
提取跳转关系与 Include 依赖，优化 1700+ 文件规模。
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
    """源码扫描结果容器"""

    def __init__(self) -> None:
        # source_jsp -> [action_paths]
        self.jump_map: Dict[str, List[str]] = {}
        # parent_jsp -> [included_jsp]  (Include 关系，用于图注入)
        self.include_map: Dict[str, List[str]] = {}
        # 扫描文件计数
        self.files_scanned: int = 0
        self.jump_relations: int = 0
        self.include_relations: int = 0


def _normalize_action(raw: str) -> str:
    """提取到的 action 字符串规范化：去 .do 后缀、加 / 前缀"""
    p = raw.strip()
    p = RE_DO_SUFFIX.sub("", p)
    if not p.startswith("/"):
        p = "/" + p
    return p


def _to_project_path(file_path: str, project_dir: str) -> str:
    """将绝对文件路径转换为项目相对 JSP 路径（/jsp/xxx.jsp 格式）"""
    try:
        rel = os.path.relpath(file_path, project_dir)
    except ValueError:
        # 不同驱动器 (Windows)，回退
        rel = file_path
    # 统一分隔符
    rel = rel.replace(os.sep, "/")
    if not rel.startswith("/"):
        rel = "/" + rel
    return rel


def _normalize_include_path(raw: str, parent_dir: str) -> str:
    """
    Include 路径可能是绝对 (/jsp/Header.jsp) 或相对 (../Header.jsp)。
    统一转为项目绝对路径格式。
    """
    p = raw.strip()
    if p.startswith("/"):
        return p
    # 相对路径：基于 parent 文件目录解析
    resolved = os.path.normpath(os.path.join(parent_dir, p))
    resolved = resolved.replace(os.sep, "/")
    if not resolved.startswith("/"):
        resolved = "/" + resolved
    return resolved


def _scan_file(
    file_path: str,
    project_dir: str,
    result: ScanResult,
) -> None:
    """扫描单个文件，提取跳转与 Include 关系"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return

    src_key = _to_project_path(file_path, project_dir)
    parent_dir = os.path.dirname(file_path)

    # ── 跳转提取 ──
    actions: Set[str] = set()
    for regex, _desc in SOURCE_RULES:
        for m in regex.finditer(content):
            raw_action = m.group(1)
            action = _normalize_action(raw_action)
            if action:
                actions.add(action)

    if actions:
        existing = result.jump_map.setdefault(src_key, [])
        for a in actions:
            if a not in existing:
                existing.append(a)
        result.jump_relations += len(actions)

    # ── Include 提取 ──
    includes: Set[str] = set()
    for regex, _desc in INCLUDE_RULES:
        for m in regex.finditer(content):
            raw_inc = m.group(1)
            inc_path = _normalize_include_path(raw_inc, parent_dir)
            if inc_path:
                includes.add(inc_path)

    if includes:
        existing = result.include_map.setdefault(src_key, [])
        for inc in includes:
            if inc not in existing:
                existing.append(inc)
        result.include_relations += len(includes)


# ─── 公开 API ───

def scan_project(project_dir: str, progress_callback=None) -> ScanResult:
    """
    扫描项目目录下所有 JSP / JS / INC 文件。
    针对大规模文件优化：先按后缀过滤、跳过无关目录、逐文件流式处理。
    """
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

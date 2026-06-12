"""
Source scanner for JSP, JavaScript, and include files.

The scanner extracts route-like paths, include relationships, and
JavaScript constants that may later resolve to navigation targets.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Set

from utils.regex_rules import INCLUDE_RULES, RE_CONST_DEF, SCAN_EXTENSIONS, SKIP_DIRS, SOURCE_RULES


class ScanResult:
    def __init__(self) -> None:
        self.jump_map: Dict[str, List[str]] = {}
        self.include_map: Dict[str, List[str]] = {}
        self.constants: Dict[str, str] = {}
        self.mentions: Dict[str, Set[str]] = {}
        self.defined_paths: Dict[str, Set[str]] = {}
        self.files_scanned: int = 0
        self.jump_relations: int = 0
        self.include_relations: int = 0


def _normalize_path(raw: str, parent_dir: str, project_dir: str) -> str:
    path = raw.strip().split("?")[0].split("#")[0]
    if not path:
        return ""
    if not path.startswith("/"):
        try:
            abs_os_path = os.path.normpath(os.path.join(parent_dir, path))
            path = _to_project_path(abs_os_path, project_dir)
        except Exception:
            pass
    if not path.startswith("/"):
        path = "/" + path
    return path


def _to_project_path(file_path: str, project_dir: str) -> str:
    try:
        rel = os.path.relpath(file_path, project_dir)
    except Exception:
        rel = file_path
    rel = rel.replace(os.sep, "/")
    if not rel.startswith("/"):
        rel = "/" + rel
    return rel


def _scan_file(file_path: str, project_dir: str, result: ScanResult) -> None:
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return

    src_key = _to_project_path(file_path, project_dir)
    parent_dir = os.path.dirname(file_path)

    # Collect local constants first so they are not misclassified as jumps.
    local_defs = set()
    for match in RE_CONST_DEF.finditer(content):
        name = match.group(1)
        url = _normalize_path(match.group(2), parent_dir, project_dir)
        if url:
            result.constants[name] = url
            local_defs.add(url)
    if local_defs:
        result.defined_paths[src_key] = local_defs

    jumps: Set[str] = set()
    includes: Set[str] = set()
    for regex, _label in SOURCE_RULES:
        for match in regex.finditer(content):
            url = _normalize_path(match.group(1), parent_dir, project_dir)
            if not url or url == src_key:
                continue
            if url in local_defs:
                continue

            if src_key.lower().endswith(".jsp") and url.lower().endswith(".js"):
                includes.add(url)
            else:
                jumps.add(url)

    for regex, _label in INCLUDE_RULES:
        for match in regex.finditer(content):
            url = _normalize_path(match.group(1), parent_dir, project_dir)
            if url and url != src_key:
                includes.add(url)

    words = set(re.findall(r"\b[a-zA-Z_]\w*\b", content))
    if words:
        result.mentions[src_key] = words

    if jumps:
        result.jump_map[src_key] = list(jumps)
        result.jump_relations += len(jumps)
    if includes:
        result.include_map[src_key] = list(includes)
        result.include_relations += len(includes)


def scan_project(project_dir: str, progress_callback=None) -> ScanResult:
    result = ScanResult()
    files_to_scan = []
    for root, dirs, files in os.walk(project_dir, topdown=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in files:
            if os.path.splitext(filename)[1].lower() in SCAN_EXTENSIONS:
                files_to_scan.append(os.path.join(root, filename))

    total = len(files_to_scan)
    for index, file_path in enumerate(files_to_scan):
        _scan_file(file_path, project_dir, result)
        result.files_scanned += 1
        if progress_callback:
            progress_callback(index + 1, total)
    return result

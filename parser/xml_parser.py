"""
xml_parser.py — 解析 struts-config*.xml
提取 Action ↔ JSP 映射，支持大小写保持。
"""

from __future__ import annotations

import os
import glob
from pathlib import Path
from typing import Dict, List, Tuple
from xml.etree import ElementTree as ET

from utils.regex_rules import STRUTS_CONFIG_GLOB, RE_DO_SUFFIX


class ParseResult:
    def __init__(self) -> None:
        self.action_forwards: Dict[str, List[str]] = {}
        self.action_inputs: Dict[str, str] = {}
        self.global_forwards: Dict[str, str] = {}


def _normalize_path(raw: str | None) -> str | None:
    if not raw: return None
    p = raw.strip()
    p = RE_DO_SUFFIX.sub("", p)
    if not p.startswith("/"):
        p = "/" + p
    return p


def _normalize_jsp(raw: str | None) -> str | None:
    if not raw: return None
    p = raw.strip()
    if not p.startswith("/"):
        p = "/" + p
    return p


def _parse_single_config(xml_path: str, result: ParseResult) -> int:
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        with open(xml_path, "rb") as f:
            raw = f.read()
        cleaned = raw.strip(b"\xef\xbb\xbf")
        cleaned = b"".join(b for b in cleaned if b >= 0x20 or b in (0x09, 0x0A, 0x0D))
        try:
            root = ET.fromstring(cleaned.decode("utf-8", errors="replace"))
        except ET.ParseError:
            return 0
    else:
        root = tree.getroot()

    action_count = 0
    for gf in root.iter("global-forwards"):
        for fwd in gf.findall("forward"):
            name = fwd.get("name")
            path = _normalize_jsp(fwd.get("path"))
            if name and path:
                result.global_forwards[name] = path

    for am in root.iter("action-mappings"):
        for action_el in am.findall("action"):
            raw_path = action_el.get("path")
            action_path = _normalize_path(raw_path)
            if not action_path: continue

            targets: List[str] = []
            forward_attr = _normalize_jsp(action_el.get("forward"))
            if forward_attr: targets.append(forward_attr)
            input_attr = _normalize_jsp(action_el.get("input"))
            if input_attr:
                result.action_inputs[action_path] = input_attr
                targets.append(input_attr)

            for fwd in action_el.findall("forward"):
                fwd_path = _normalize_jsp(fwd.get("path"))
                if fwd_path: targets.append(fwd_path)

            if targets:
                existing = result.action_forwards.setdefault(action_path, [])
                for t in targets:
                    if t not in existing: existing.append(t)
            action_count += 1
    return action_count


def scan_struts_configs(project_dir: str) -> Tuple[ParseResult, List[str]]:
    result = ParseResult()
    found_configs: List[str] = []
    for root, dirs, _files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in (".svn", ".git", "node_modules", "target")]
        if os.path.basename(root).upper() == "WEB-INF":
            pattern = os.path.join(root, STRUTS_CONFIG_GLOB)
            for cfg in glob.glob(pattern):
                found_configs.append(cfg)
                _parse_single_config(cfg, result)
    return result, found_configs

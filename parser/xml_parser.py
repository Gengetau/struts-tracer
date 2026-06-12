"""
Parser for struts-config*.xml files.

It extracts Action-to-JSP and global forward mappings while preserving
the original path casing where possible.
"""

from __future__ import annotations

import glob
import os
from typing import Dict, List, Tuple
from xml.etree import ElementTree as ET

from utils.regex_rules import RE_DO_SUFFIX, STRUTS_CONFIG_GLOB


class ParseResult:
    def __init__(self) -> None:
        self.action_forwards: Dict[str, List[str]] = {}
        self.action_inputs: Dict[str, str] = {}
        self.global_forwards: Dict[str, str] = {}


def _normalize_path(raw: str | None) -> str | None:
    if not raw:
        return None
    path = raw.strip()
    path = RE_DO_SUFFIX.sub("", path)
    if not path.startswith("/"):
        path = "/" + path
    return path


def _normalize_jsp(raw: str | None) -> str | None:
    if not raw:
        return None
    path = raw.strip()
    if not path.startswith("/"):
        path = "/" + path
    return path


def _parse_single_config(xml_path: str, result: ParseResult) -> int:
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        with open(xml_path, "rb") as f:
            raw = f.read()
        cleaned = raw.strip(b"\xef\xbb\xbf")
        cleaned = b"".join(byte for byte in cleaned if byte >= 0x20 or byte in (0x09, 0x0A, 0x0D))
        try:
            root = ET.fromstring(cleaned.decode("utf-8", errors="replace"))
        except ET.ParseError:
            return 0
    else:
        root = tree.getroot()

    action_count = 0
    for global_forwards in root.iter("global-forwards"):
        for forward in global_forwards.findall("forward"):
            name = forward.get("name")
            path = _normalize_jsp(forward.get("path"))
            if name and path:
                result.global_forwards[name] = path

    for action_mappings in root.iter("action-mappings"):
        for action_el in action_mappings.findall("action"):
            raw_path = action_el.get("path")
            action_path = _normalize_path(raw_path)
            if not action_path:
                continue

            targets: List[str] = []
            forward_attr = _normalize_jsp(action_el.get("forward"))
            if forward_attr:
                targets.append(forward_attr)

            input_attr = _normalize_jsp(action_el.get("input"))
            if input_attr:
                result.action_inputs[action_path] = input_attr
                targets.append(input_attr)

            for forward in action_el.findall("forward"):
                forward_path = _normalize_jsp(forward.get("path"))
                if forward_path:
                    targets.append(forward_path)

            if targets:
                existing = result.action_forwards.setdefault(action_path, [])
                for target in targets:
                    if target not in existing:
                        existing.append(target)
            action_count += 1

    return action_count


def scan_struts_configs(project_dir: str) -> Tuple[ParseResult, List[str]]:
    result = ParseResult()
    found_configs: List[str] = []
    for root, dirs, _files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in (".svn", ".git", "node_modules", "target")]
        if os.path.basename(root).upper() == "WEB-INF":
            pattern = os.path.join(root, STRUTS_CONFIG_GLOB)
            for config_path in glob.glob(pattern):
                found_configs.append(config_path)
                _parse_single_config(config_path, result)
    return result, found_configs

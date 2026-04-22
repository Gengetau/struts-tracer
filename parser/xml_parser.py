"""
xml_parser.py — 解析 struts-config*.xml
递归扫描 WEB-INF 下所有配置，提取 Action → JSP 映射与全局 Forward。
"""

from __future__ import annotations

import os
import glob
from pathlib import Path
from typing import Dict, List, Tuple
from xml.etree import ElementTree as ET

from utils.regex_rules import STRUTS_CONFIG_GLOB, RE_DO_SUFFIX


# ─── 数据结构 ───

class ParseResult:
    """XML 解析结果容器"""

    def __init__(self) -> None:
        # action_path -> [forward_jsp_paths]
        self.action_forwards: Dict[str, List[str]] = {}
        # action_path -> input_jsp (若 action 指定了 input)
        self.action_inputs: Dict[str, str] = {}
        # forward_name -> jsp_path
        self.global_forwards: Dict[str, str] = {}

    def __repr__(self) -> str:
        return (
            f"ParseResult(actions={len(self.action_forwards)}, "
            f"globals={len(self.global_forwards)})"
        )


# ─── 内部辅助 ───

def _normalize_path(raw: str | None) -> str | None:
    """将 XML 中的 path 规范化：去除 .do 后缀、确保以 / 开头、转小写"""
    if not raw:
        return None
    p = raw.strip()
    if not p:
        return None
    p = RE_DO_SUFFIX.sub("", p)
    if not p.startswith("/"):
        p = "/" + p
    return p.lower()


def _normalize_jsp(raw: str | None) -> str | None:
    """JSP 路径规范化：确保以 / 开头、保留 .jsp 后缀、转小写"""
    if not raw:
        return None
    p = raw.strip()
    if not p:
        return None
    if not p.startswith("/"):
        p = "/" + p
    return p.lower()


def _parse_single_config(xml_path: str, result: ParseResult) -> int:
    """解析单个 struts-config XML，返回提取的 action 数量"""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        # 容错：lxml 不可用时回退到逐行清洗（处理 JSP 染色的 XML）
        # 尝试移除非法字节后重解析
        with open(xml_path, "rb") as f:
            raw = f.read()
        # 移除 BOM 与非法控制字符
        cleaned = raw.strip(b"\xef\xbb\xbf")
        cleaned = b"".join(b for b in cleaned if b >= 0x20 or b in (0x09, 0x0A, 0x0D))
        try:
            root = ET.fromstring(cleaned.decode("utf-8", errors="replace"))
        except ET.ParseError:
            return 0
    else:
        root = tree.getroot()

    action_count = 0

    # ── global-forwards ──
    for gf in root.iter("global-forwards"):
        for fwd in gf.findall("forward"):
            name = fwd.get("name")
            path = _normalize_jsp(fwd.get("path"))
            if name and path:
                result.global_forwards[name] = path

    # ── action-mappings ──
    for am in root.iter("action-mappings"):
        for action_el in am.findall("action"):
            raw_path = action_el.get("path")
            action_path = _normalize_path(raw_path)
            if not action_path:
                continue

            targets: List[str] = []

            # action 自身的 forward / input 属性
            forward_attr = _normalize_jsp(action_el.get("forward"))
            if forward_attr:
                targets.append(forward_attr)

            input_attr = _normalize_jsp(action_el.get("input"))
            if input_attr:
                result.action_inputs[action_path] = input_attr
                targets.append(input_attr)

            # 子级 <forward>
            for fwd in action_el.findall("forward"):
                fwd_path = _normalize_jsp(fwd.get("path"))
                if fwd_path:
                    targets.append(fwd_path)

            if targets:
                existing = result.action_forwards.setdefault(action_path, [])
                # 去重追加
                for t in targets:
                    if t not in existing:
                        existing.append(t)

            action_count += 1

    return action_count


# ─── 公开 API ───

def scan_struts_configs(project_dir: str) -> Tuple[ParseResult, List[str]]:
    """
    递归扫描 project_dir 下所有 WEB-INF 中的 struts-config*.xml。

    Returns:
        (ParseResult, list_of_config_paths_found)
    """
    result = ParseResult()
    found_configs: List[str] = []

    # 递归查找所有 WEB-INF 目录
    for root, dirs, _files in os.walk(project_dir):
        # 剪枝：跳过无关目录
        dirs[:] = [d for d in dirs if d not in (".svn", ".git", "node_modules", "target")]
        if os.path.basename(root).upper() == "WEB-INF":
            pattern = os.path.join(root, STRUTS_CONFIG_GLOB)
            for cfg in glob.glob(pattern):
                found_configs.append(cfg)
                _parse_single_config(cfg, result)

    return result, found_configs

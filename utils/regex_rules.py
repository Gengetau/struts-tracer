"""
regex_rules.py — 正则表达式集中管理
升级：极致捕获所有可能的 URL 和跳转信号。
"""

import re

SKIP_DIRS: frozenset = frozenset({
    ".svn", ".git", "__pycache__", "node_modules",
    ".idea", ".vscode", "target", "build", "dist",
})

SCAN_EXTENSIONS: frozenset = frozenset({".jsp", ".js", ".inc", ".html", ".htm"})
STRUTS_CONFIG_GLOB = "struts-config*.xml"
RE_DO_SUFFIX = re.compile(r"\.do$", re.IGNORECASE)

# ─── 核心匹配逻辑 ───
# 捕捉引号内任何看起来像路径或 Action 的字符串
# 1. 包含 .do 或 .jsp/.inc/.js
# 2. 或者是以 / 开头的字符串（Action 路径常用格式）
RE_URL_PATTERN = r"""["']((?:/[^"']+?)|(?:[^"']+?\.(?:do|jsp|inc|js|html|htm)(?:[^"']*)))["']"""

# 广谱捕捉
RE_GENERIC_URL = re.compile(RE_URL_PATTERN, re.IGNORECASE)

# 专门针对 Include/Script 的特征捕获，用于建立引用树
RE_INCLUDE_TAG = re.compile(
    r"""<(?:jsp:include|patlics:frame|script|%@\s*include)\s+[^>]*(?:page|file|src|url)\s*=\s*""" + RE_URL_PATTERN,
    re.IGNORECASE,
)

SOURCE_RULES = [(RE_GENERIC_URL, "generic url")]
INCLUDE_RULES = [(RE_INCLUDE_TAG, "inclusion/reference")]

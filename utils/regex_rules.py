"""
regex_rules.py — 极致路径捕获规则
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
# 捕捉引号内任何看起来像路径、Action 或 JSP 的字符串
# 1. 包含 .do 或 .jsp/.inc/.js/.html
# 2. 或者是以 / 开头且长度大于 2 的路径字符串
RE_URL_PATTERN = r"""["']((?:/[^"']+?)|(?:[^"']+?\.(?:do|jsp|inc|js|html|htm)(?:[^"']*)))["']"""

# 广谱捕捉：不放过源码中出现的任何疑似路径字符串
RE_GENERIC_URL = re.compile(RE_URL_PATTERN, re.IGNORECASE)

# 专门针对包含关系的标签捕获，用于建立引用树
RE_INCLUDE_TAG = re.compile(
    r"""<(?:jsp:include|patlics:frame|script|%@\s*include)\s+[^>]*(?:page|file|src|url)\s*=\s*""" + RE_URL_PATTERN,
    re.IGNORECASE,
)

# ─── 常量定义捕获 (JS 变量赋值) ───
# 捕捉形如 var PATH_NAME = "/action.do" 的逻辑
# 限制：常量名全大写或蛇形命名，且值必须符合路径特征
RE_CONST_DEF = re.compile(
    r"""(?:var|const|let|this)\s+([A-Z_][A-Z0-9_]{2,})\s*=\s*""" + RE_URL_PATTERN,
)

SOURCE_RULES = [(RE_GENERIC_URL, "generic url string")]
INCLUDE_RULES = [(RE_INCLUDE_TAG, "explicit reference tag")]

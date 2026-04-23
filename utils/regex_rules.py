"""
regex_rules.py — 极致路径与常量捕获规则
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
# 引号包裹的路径/Action特征
RE_URL_PATTERN = r"""["']((?:/[^"']+?)|(?:[^"']+?\.(?:do|jsp|inc|js|html|htm)(?:[^"']*)))["']"""

# 广谱捕捉：源码中的所有疑似路径
RE_GENERIC_URL = re.compile(RE_URL_PATTERN, re.IGNORECASE)

# 专门捕捉包含关系的标签
RE_INCLUDE_TAG = re.compile(
    r"""<(?:jsp:include|patlics:frame|script|%@\s*include)\s+[^>]*(?:page|file|src|url)\s*=\s*""" + RE_URL_PATTERN,
    re.IGNORECASE,
)

# ─── 常量定义捕获 (JS 变量赋值) ───
# 捕捉形如 var PATH_NAME = "/action.do" 的逻辑
# 支持多种声明方式，不限全大写（兼容驼峰名）
RE_CONST_DEF = re.compile(
    r"""(?:var|const|let|this\.)\s*([a-zA-Z_]\w*)\s*=\s*""" + RE_URL_PATTERN,
)

SOURCE_RULES = [(RE_GENERIC_URL, "generic url")]
INCLUDE_RULES = [(RE_INCLUDE_TAG, "explicit reference")]

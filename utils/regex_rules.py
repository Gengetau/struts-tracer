"""
regex_rules.py — 正则表达式集中管理
覆盖 Struts 1.x 遗留系统所有常见跳转写法，包含动态路径拼接与自定义标签。
"""

import re

# ─── 跳过目录 ───
SKIP_DIRS: frozenset = frozenset({
    ".svn", ".git", "__pycache__", "node_modules",
    ".idea", ".vscode", "target", "build", "dist",
})

# ─── 扫描文件后缀 ───
SCAN_EXTENSIONS: frozenset = frozenset({".jsp", ".js", ".inc", ".html", ".htm"})

# ─── XML 配置文件 glob ───
STRUTS_CONFIG_GLOB = "struts-config*.xml"

# ─── Action 路径规范化 ───
RE_DO_SUFFIX = re.compile(r"\.do$", re.IGNORECASE)


# ──────────────────────────────────────────────
#  JSP / JS / INC 源码跳转提取规则 (针对 Action 和 JSP)
# ──────────────────────────────────────────────

# 核心捕获逻辑：抓取引号内的路径字符串
# 重点抓取：1. 以 / 开头的路径  2. 包含 .do 或 .jsp 的路径
RE_URL_PATTERN = r"""["']((?:/[^"']+?)|(?:[^"']+?\.(?:do|jsp|inc|html|htm)(?:[^"']*)))["']"""

# 1. 广谱标签捕获 (Struts & HTML)
# <html:form action="...">, <a href="...">, <patlics:frame src="...">
RE_TAG_URL = re.compile(
    r"""<(?:html|bean|logic|patlics|form|a|frame|iframe|script)\s+[^>]*(?:action|property|forward|href|page|src|url|path)\s*=\s*""" + RE_URL_PATTERN,
    re.IGNORECASE,
)

# 2. JavaScript 中的路径字面量
# 针对 location = '...', window.open(...), submitForm(..., '...')
# 我们在源码中寻找一切引号包裹的、符合 URL 特征的字符串
RE_JS_URL = re.compile(RE_URL_PATTERN, re.IGNORECASE)

# ─── 汇总：按优先级依次执行的规则列表 ───
SOURCE_RULES: list[tuple[re.Pattern, str]] = [
    (RE_TAG_URL, "tag attribute url"),
    (RE_JS_URL, "generic string literal url"),
]


# ──────────────────────────────────────────────
#  Include 规则（专门用于建立依赖关系）
# ──────────────────────────────────────────────

# <jsp:include page="..." />, <%@ include file="..." />, <patlics:frame page="..." />
RE_INCLUDE = re.compile(
    r"""<(?:jsp:include|patlics:frame|%@\s*include)\s+[^>]*(?:page|file|src)\s*=\s*""" + RE_URL_PATTERN,
    re.IGNORECASE,
)

INCLUDE_RULES: list[tuple[re.Pattern, str]] = [
    (RE_INCLUDE, "include/frame dependency"),
]

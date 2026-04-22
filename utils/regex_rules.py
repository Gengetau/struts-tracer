"""
regex_rules.py — 正则表达式集中管理
覆盖 Struts 1.x 遗留系统所有常见跳转写法，含动态路径拼接处理。
"""

import re

# ─── 跳过目录（扫描时排除） ───
SKIP_DIRS: frozenset = frozenset({
    ".svn", ".git", "__pycache__", "node_modules",
    ".idea", ".vscode", "target", "build", "dist",
})

# ─── 扫描文件后缀 ───
SCAN_EXTENSIONS: frozenset = frozenset({".jsp", ".js", ".inc"})

# ─── XML 配置文件 glob ───
STRUTS_CONFIG_GLOB = "struts-config*.xml"

# ─── Action 路径规范化 ───
RE_DO_SUFFIX = re.compile(r"\.do$", re.IGNORECASE)


# ──────────────────────────────────────────────
#  JSP / JS / INC 源码跳转提取规则
# ──────────────────────────────────────────────

# 1. 广谱 Struts 标签捕获: <html:XXX action="..." > 或 property="..."
#    覆盖 link, form, rewrite, button, submit 等
RE_STRUTS_TAG_ACTION = re.compile(
    r"""<(?:html|bean|logic):\w+\s+[^>]*(?:action|property|forward|href|page)\s*=\s*["']/?([^"']+?)["']""",
    re.IGNORECASE,
)

# 2. 标准 HTML 标签捕获: <form action="...">, <a href="...">
#    侧重于捕获带 .do 的跳转
RE_HTML_JUMP = re.compile(
    r"""<(?:form|a|frame|iframe)\s+[^>]*(?:action|href|src)\s*=\s*["']/?([^"']+?)["']""",
    re.IGNORECASE,
)

# 3. 自定义内联标签捕获: <patlics:frame src="..." />
#    针对特定项目的非标准内联组件
RE_CUSTOM_FRAME_JUMP = re.compile(
    r"""<patlics:frame\s+[^>]*(?:src|url|page|path)\s*=\s*["']/?([^"']+?)["']""",
    re.IGNORECASE,
)

# 4. JavaScript 字符串字面量中的 .do 捕获
#    覆盖 submitForm(..., '/XXX.do'), window.open('/XXX.do'), location = 'XXX.do'
RE_JS_DO_LITERAL = re.compile(
    r"""["']/?([^"']+?\.do(?:[^"']*)?)["']""",
    re.IGNORECASE,
)

# 5. JS 动态路径拼接增强型捕获
RE_JS_CONCAT_ACTION = re.compile(
    r"""(?:[A-Za-z_]\w*\s*\+\s*)?["']/?([^"']+?\.do[^"']*)["']""",
    re.IGNORECASE,
)

# 6. 特殊：针对特定跳转函数的捕获
RE_JS_FUNC_CALL = re.compile(
    r"""(?:submit|jump|go|open|call|send|request)(?:To|Page|Form)?\s*\([^,]*?,\s*["']/?([^"']+?)["']""",
    re.IGNORECASE,
)

# ─── 汇总：按优先级依次执行的规则列表 ───
SOURCE_RULES: list[tuple[re.Pattern, str]] = [
    (RE_STRUTS_TAG_ACTION, "struts tag"),
    (RE_HTML_JUMP, "html tag"),
    (RE_CUSTOM_FRAME_JUMP, "custom patlics tag"),
    (RE_JS_DO_LITERAL, "js literal"),
    (RE_JS_CONCAT_ACTION, "js concat"),
    (RE_JS_FUNC_CALL, "js func"),
]


# ──────────────────────────────────────────────
#  JSP Include 规则（递归注入）
# ──────────────────────────────────────────────

# <jsp:include page="/XXX.jsp" />
RE_JSP_INCLUDE = re.compile(
    r"""<jsp:include\s+[^>]*page\s*=\s*["'](/?[^"']+?\.jsp)["']""",
    re.IGNORECASE,
)

# <%@ include file="/XXX.jsp" %>
RE_INCLUDE_DIRECTIVE = re.compile(
    r"""<%@\s*include\s+file\s*=\s*["'](/?[^"']+?\.jsp)["']""",
    re.IGNORECASE,
)

# <patlics:frame src="..." /> 指向 JSP 的情况
RE_CUSTOM_FRAME_INCLUDE = re.compile(
    r"""<patlics:frame\s+[^>]*(?:src|url|page|path)\s*=\s*["'](/?[^"']+?\.jsp)["']""",
    re.IGNORECASE,
)

# ─── 汇总 ───
INCLUDE_RULES: list[tuple[re.Pattern, str]] = [
    (RE_JSP_INCLUDE, "jsp:include"),
    (RE_INCLUDE_DIRECTIVE, "directive"),
    (RE_CUSTOM_FRAME_INCLUDE, "custom patlics include"),
]

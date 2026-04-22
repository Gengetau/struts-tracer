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
RE_DO_SUFFIX = re.compile(r"\.do$")


# ──────────────────────────────────────────────
#  JSP / JS / INC 源码跳转提取规则
# ──────────────────────────────────────────────

# 1. Struts html:form action="/XXX" 或 action="XXX.do"
RE_HTML_FORM_ACTION = re.compile(
    r"""<html:form\s+[^>]*action\s*=\s*["']/?([^"']+?)["']""",
    re.IGNORECASE,
)

# 2. 原生 <form action="/XXX.do">
RE_NATIVE_FORM_ACTION = re.compile(
    r"""<form\s+[^>]*action\s*=\s*["']/?([^"']+?\.do)["']""",
    re.IGNORECASE,
)

# 3. JS 显式跳转: location.href = "XXX.do" | location = "XXX.do"
#    同时覆盖 location.replace / location.assign
RE_JS_LOCATION_HREF = re.compile(
    r"""(?:location(?:\.href)?|location\.(?:replace|assign))\s*=\s*["']/?([^"']+?\.do)["']""",
    re.IGNORECASE,
)

# 4. JS window.open("XXX.do")
RE_JS_WINDOW_OPEN = re.compile(
    r"""window\.open\s*\(\s*["']/?([^"']+?\.do)["']""",
    re.IGNORECASE,
)

# 5. 封装函数提交: submitForm('form', '/XXX.do') | submit('form','/XXX.do')
RE_SUBMIT_FORM = re.compile(
    r"""submit(?:Form)?\s*\(\s*[^,]+,\s*["']/?([^"']+?\.do)""",
    re.IGNORECASE,
)

# 6. 动态路径拼接: APP_URL + "/XXX.do" | baseUrl + '/XXX.do'
#    只抓取字符串字面量中的 .do 路径部分
RE_DYNAMIC_CONCAT = re.compile(
    r"""[A-Za-z_]\w*\s*\+\s*["'](/[^"']+?\.do)""",
)

# 7. 超链接跳转: <a href="XXX.do"> 或 <a href="/XXX.do">
RE_ANCHOR_HREF = re.compile(
    r"""<a\s+[^>]*href\s*=\s*["']/?([^"']+?\.do)""",
    re.IGNORECASE,
)

# 8. JavaScript 重定向: window.location = "XXX.do"
RE_JS_REDIRECT = re.compile(
    r"""window\.location(?:(?:\.href)?\s*=|\.replace\(|\.assign\()\s*["']/?([^"']+?\.do)""",
    re.IGNORECASE,
)

# ─── 汇总：按优先级依次执行的规则列表 ───
#    每项: (regex, description)
SOURCE_RULES: list[tuple[re.Pattern, str]] = [
    (RE_HTML_FORM_ACTION, "html:form action"),
    (RE_NATIVE_FORM_ACTION, "form action .do"),
    (RE_JS_LOCATION_HREF, "location.href .do"),
    (RE_JS_WINDOW_OPEN, "window.open .do"),
    (RE_SUBMIT_FORM, "submitForm .do"),
    (RE_DYNAMIC_CONCAT, "dynamic concat .do"),
    (RE_ANCHOR_HREF, "anchor href .do"),
    (RE_JS_REDIRECT, "js redirect .do"),
]


# ──────────────────────────────────────────────
#  JSP Include 规则（递归注入）
# ──────────────────────────────────────────────

# <jsp:include page="/XXX.jsp" /> | <jsp:include page="XXX.jsp">
RE_JSP_INCLUDE = re.compile(
    r"""<jsp:include\s+[^>]*page\s*=\s*["'](/?[^"']+?\.jsp)["']""",
    re.IGNORECASE,
)

# <%@ include file="/XXX.jsp" %> (静态 include)
RE_INCLUDE_DIRECTIVE = re.compile(
    r"""<%@\s*include\s+file\s*=\s*["'](/?[^"']+?\.jsp)["']""",
    re.IGNORECASE,
)

# ─── 汇总 ───
INCLUDE_RULES: list[tuple[re.Pattern, str]] = [
    (RE_JSP_INCLUDE, "jsp:include"),
    (RE_INCLUDE_DIRECTIVE, "include directive"),
]

"""
Regex rules for path, include, and JavaScript constant extraction.
"""

import re

SKIP_DIRS: frozenset = frozenset({
    ".svn",
    ".git",
    "__pycache__",
    "node_modules",
    ".idea",
    ".vscode",
    "target",
    "build",
    "dist",
})

SCAN_EXTENSIONS: frozenset = frozenset({".jsp", ".js", ".inc", ".html", ".htm"})
STRUTS_CONFIG_GLOB = "struts-config*.xml"
RE_DO_SUFFIX = re.compile(r"\.do$", re.IGNORECASE)

# Capture quoted strings that look like routes, JSP files, includes, or scripts.
RE_URL_PATTERN = r"""["']((?:/[^"']+?)|(?:[^"']+?\.(?:do|jsp|inc|js|html|htm)(?:[^"']*)))["']"""

# Broad capture for route-like literals in source files.
RE_GENERIC_URL = re.compile(RE_URL_PATTERN, re.IGNORECASE)

# Explicit include references, used to build the dependency tree.
RE_INCLUDE_TAG = re.compile(
    r"""<(?:jsp:include|patlics:frame|script|%@\s*include)\s+[^>]*(?:page|file|src|url)\s*=\s*""" + RE_URL_PATTERN,
    re.IGNORECASE,
)

# JavaScript-style constant definitions such as:
#   var PATH_NAME = "/action.do"
#   PATH_NAME: "/action.do"
RE_CONST_DEF = re.compile(
    r"""(?:var|const|let|this\.|[a-zA-Z_]\w*\s*:)\s*([a-zA-Z_]\w*)\s*[=:]\s*""" + RE_URL_PATTERN,
)

SOURCE_RULES = [(RE_GENERIC_URL, "generic url")]
INCLUDE_RULES = [(RE_INCLUDE_TAG, "explicit reference")]

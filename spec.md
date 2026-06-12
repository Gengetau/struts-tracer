# Struts 1.x Static Link Analyzer - Technical Specification

## 1. Background and Goal

Legacy Struts 1.x Java Web systems often spread navigation logic across
`struts-config.xml`, JSP templates, JavaScript redirects, and shared include
files. Manually tracing a route from a deep JSP page back to an entry point is
slow and error-prone.

This project provides a local Python CLI that parses a full project tree,
builds a directed graph of `[JSP] <-> [Action] <-> [JSP]` relationships, and
supports both reverse route tracing and forward reachability analysis.

## 2. Technology Stack

* **Language**: Python 3.9+
* **Core dependencies**:
  * `xml.etree.ElementTree` for resilient Struts XML parsing
  * `networkx` for directed graph modeling and path search
  * `rich` for readable CLI output, tables, progress indicators, and trees
* **Runtime model**: offline static analysis; no database connection required

## 3. Architecture

```text
struts_tracer/
├── main.py                 # CLI entry point and argument handling
├── parser/
│   ├── xml_parser.py       # Parses struts-config*.xml files
│   └── source_scanner.py   # Scans JSP, JS, INC, HTML files
├── core/
│   ├── graph_builder.py    # Builds and normalizes the route graph
│   └── tracer_engine.py    # Performs reverse and forward path search
├── utils/
│   └── regex_rules.py      # Centralized regex patterns
└── requirements.txt
```

## 4. Module Details

### 4.1 XML Parser (`xml_parser.py`)

**Input**: project root directory.

**Behavior**:

1. Scan all `struts-config*.xml` files under `WEB-INF`.
2. Extract global forwards from `<global-forwards>`.
3. Extract Action mappings from `<action-mappings>`.
4. Extract nested `<forward>` targets and `input` targets from each Action.

**Output shape**:

```python
{
    "/TransGroupMail": ["/jsp/mail/MailSuccess.jsp", "/jsp/common/Error.jsp"],
    "GLOBAL_FORWARDS": {"login": "/Login.jsp"},
}
```

### 4.2 Source Scanner (`source_scanner.py`)

**Input**: project directory, limited to `.jsp`, `.js`, `.inc`, `.html`, and
`.htm` files. Generated and dependency folders are skipped.

**Rules**:

1. HTML/Struts form actions such as `<html:form action="/Search.do">`.
2. Native form actions such as `<form action="/Search.do">`.
3. JavaScript redirects such as `location.href = "/Search.do"`.
4. Popup navigation such as `window.open("/Search.do")`.
5. Wrapped submit helpers such as `submitForm("form", "/Search.do")`.
6. Include references such as `<jsp:include page="/Header.jsp" />`.
7. JavaScript constants that later resolve to navigation targets.

**Output shape**:

```python
{
    "/jsp/mail/WwBiblioList.jsp": ["/TransGroupMail.do", "/GetWwBiblioList.do"]
}
```

### 4.3 Graph Builder (`graph_builder.py`)

The graph builder merges XML and source scan results into a single
`networkx.DiGraph`.

Key conventions:

* Actions drop the `.do` suffix during normalization.
* JSP and source-file nodes preserve their project-relative path.
* Include edges carry lower weight than global forwards so local business paths
  are prioritized.
* JavaScript constants are resolved when a source file references a known
  constant name.

### 4.4 Tracing Engine (`tracer_engine.py`)

The engine exposes two search modes:

1. **Reverse trace**: given a target JSP, find likely paths from entry pages to
   that target.
2. **Forward trace**: given a starting JSP, find pages that can be reached from
   it.

Guardrails:

* Maximum path depth is configurable.
* Repeated paths are deduplicated.
* Common layout or auth noise can be excluded with the `--ignore` option.

## 5. CLI Example

```bash
python main.py trace --target WwBiblioList.jsp --dir /path/to/project --direction reverse
```

Example output:

```text
Starting reverse trace: WwBiblioList.jsp

Path 1
  [JSP] /Login.jsp
    [Action] /LoginAction
      [JSP] /MainMenu.jsp
        [Action] /InitWwSearch
          [JSP] /WwSearchCondition.jsp
            [Action] /GetWwBiblioList
              [JSP] /WwBiblioList.jsp target
```

## 6. Edge Cases

* **Dynamic path concatenation**: for expressions such as
  `location.href = APP_URL + "/action.do"`, the scanner should keep the static
  route segment and ignore the variable prefix where possible.
* **JSP includes**: if `Header.jsp` contains a route, a parent JSP that includes
  it should be treated as inheriting that navigation capability.
* **Global forwards**: global routes are useful but noisy, so they receive a
  higher graph weight than local business routes.

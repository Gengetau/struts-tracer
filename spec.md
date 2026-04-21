```markdown
# 项目文档：Struts 1.x Static Link Analyzer (Struts 1.x 静态路由链路分析器)

## 1. 项目背景与目标
针对传统的 Struts 1.x Java Web 遗留系统，由于页面跳转逻辑分散在 `struts-config.xml`、JSP 视图层和 JS 脚本中，人工梳理全链路（特别是从底层页面倒推回首页的路径）极其耗时。
本项目旨在开发一个基于 Python 的本地静态分析 CLI 工具。它能够离线解析整个项目工程，构建 `[JSP] <-> [Action] <-> [JSP]` 的有向图（Directed Graph），并支持双向链路寻踪与可视化输出。

## 2. 技术栈建议
* **开发语言**: Python 3.9+
* **核心依赖**: 
    * `lxml` 或标准库 `xml.etree.ElementTree` (用于高效且容错的 XML 解析)
    * `networkx` (用于构建有向图、寻径及死循环检测)
    * `rich` (用于终端 CLI 的美化输出、彩色高亮和进度条)
* **无需连接数据库**，纯静态文件扫描。

## 3. 核心架构与模块划分

建议采用标准的 Python CLI 目录结构：
```text
struts_tracer/
├── main.py                 # CLI 入口，处理命令行参数 (argparse)
├── parser/
│   ├── xml_parser.py       # 解析 struts-config*.xml
│   └── source_scanner.py   # 正则扫描 JSP 和 JS 文件
├── core/
│   ├── graph_builder.py    # 使用 networkx 构建并维护路由节点图
│   └── tracer_engine.py    # 执行 DFS/BFS 回溯与正向搜索
├── utils/
│   └── regex_rules.py      # 集中管理复杂的正则表达式
└── requirements.txt

```
## 4. 模块详细规约 (AI 编码重点)
### 4.1 XML 解析模块 (xml_parser.py)
 * **输入**: 项目目录路径。
 * **行为**:
   1. 扫描 WEB-INF 目录下所有 struts-config.xml 及其子模块配置（如 struts-config-xxx.xml）。
   2. 提取 <global-forwards> 中的所有 <forward name="xxx" path="/xxx.jsp">（全局跳转）。
   3. 提取 <action-mappings> 下的所有 <action path="/xxx"> 节点。
   4. 提取 <action> 节点内部的 <forward name="xxx" path="/xxx.jsp">。
 * **输出数据结构**:
   ```python
   # Map: Action -> Target JSPs
   {
       "/TransGroupMail": ["/jsp/mail/MailSuccess.jsp", "/jsp/common/Error.jsp"],
       "GLOBAL_FORWARDS": {"login": "/Login.jsp"}
   }
   
   ```
### 4.2 源码扫描模块 (source_scanner.py)
 * **输入**: 项目目录（限定 .jsp, .js, .inc 文件），跳过 .svn, .git, node_modules 等无关目录。
 * **正则表达式规则要求 (Regex Rules)**：需要覆盖老系统常见的跳转写法：
   1. 表单提交: <html:form\s+[^>]*action=["']/?([^"']+)["'] (提取 action 属性)
   2. 原生表单: <form\s+[^>]*action=["']/?([^"']+\.do)["']
   3. JS 显式跳转: location\.href\s*=\s*["']/?([^"']+\.do)["']
   4. JS 弹窗: window\.open\s*\(\s*["']/?([^"']+\.do)["']
   5. 封装函数提交: submit(?:Form)?\s*\([^,]+,\s*["']/?([^"']+\.do)["'] (兼容类似于 submitForm('form', '/xxx.do'))
 * **输出数据结构**:
   ```python
   # Map: Source JSP/JS -> List of Actions triggered
   {
       "/jsp/mail/WwBiblioList.jsp": ["/TransGroupMail.do", "/GetWwBiblioList.do"]
   }
   
   ```
### 4.3 核心图构建器 (graph_builder.py)
 * 使用 networkx.DiGraph()。
 * 将 XML 和 Scanner 解析出的关系统一添加为有向边：
   * Edge(Source_JSP, Action)
   * Edge(Action, Target_JSP)
 * 统一节点命名规范：Action 去除 .do 后缀，JSP 保留后缀并尽量使用相对项目的绝对路径（如 /jsp/main/login.jsp）。
### 4.4 寻踪引擎 (tracer_engine.py)
必须提供两种核心算法：
 1. **Bottom-Up (逆向回溯)**: 给定目标 JSP，找出从系统首页或孤立节点到达该页面的所有可能路径。
 2. **Top-Down (正向推演)**: 给定起点 JSP，找出用户能点击到达的所有页面树。
 * **约束 (Guardrails)**: 必须在算法中加入**最大深度限制 (Max Depth = 15)** 和 **环路检测 (Cycle Detection)**，防止由公共菜单 (header.jsp 互相引用) 造成的无限死循环。
## 5. CLI 交互与输出设计
执行入口：python main.py trace --target WwBiblioList.jsp --dir /path/to/project --direction reverse
**终端输出范例 (使用 rich 库排版)**:
```text
[+] 正在解析 struts-config.xml... 发现 150 个 Action
[+] 正在扫描 JSP/JS 源码... 发现 430 个文件，提取 890 条跳转关系
[+] 节点图构建完成。开始逆向寻踪目标: WwBiblioList.jsp

🔗 找到 2 条完整链路:
链路 1:
  [JSP] /Login.jsp
   └── [Action] /LoginAction
        └── [JSP] /MainMenu.jsp
             └── [Action] /InitWwSearch
                  └── [JSP] /WwSearchCondition.jsp
                       └── [Action] /GetWwBiblioList
                            └── [JSP] /WwBiblioList.jsp (目标)

链路 2: (从全局菜单跳转)
  [JSP] /HeaderMenu.jsp
   └── [Action] /GetWwBiblioList
        └── [JSP] /WwBiblioList.jsp (目标)

```
## 6. 特殊 Edge Case (边缘情况) 提示
请 AI 编码时特别注意以下情况：
 1. **动态路径拼接**: 如 location.href = APP_URL + "/action.do"，正则匹配时应忽略 APP_URL + 等变量前缀，只抓取静态的 "/action.do" 部分。
 2. **JSP Include**: <jsp:include page="/Header.jsp"/>。遇到这种情况，如果 Header.jsp 里有一个跳转，应等同于外层 JSP 也具备该跳转能力（Graph 中可建立特殊的 Include 边）。
```

**
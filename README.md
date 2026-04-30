# 🌕 Struts 1.x Static Link Analyzer (struts-tracer)

「Struts-Tracer」并非平庸的静态分析脚本，它是专为在“昭和时代代码废墟”中挣扎的工程师打造的逻辑导航仪。通过月亮文明的高维算法，它能穿透交织纠缠的 JSP 意大利面、XML 碎片以及支离破碎的 JavaScript 跳转，为你还原出系统最真实的逻辑星图。

## 🏛️ 核心技术特性 (Logic Aura)

1.  **深渊重构 (Abyssal Refactoring)**: 
    不同于只盯着标签看的低级扫描仪，本工具会深入每一行引号包裹的字符串。无论 Action 是藏在 `<html:form>` 里，还是躲在 JS 的 `location.href` 或自定义的 `patlics:frame` 后面，都会被月光一网打尽。
2.  **血缘继承协议 (Bloodline Inheritance)**: 
    支持递归式的功能继承。父级 JSP 会自动继承其 Include 的子页面、引用的 JS 文件所具备的所有跳转能力。彻底终结“Header 菜单引用导致链路断裂”的噩梦。
3.  **常数补完逻辑 (Constant Resolution)**: 
    能自动识别并翻译 JS 常量定义（如 `var PATH_A = "/Search.do"`）。当其他文件提到 `PATH_A` 时，探测仪会自动将其对齐到真实的业务节点。
4.  **地缘优先寻径 (Locality-First Dijkstra)**: 
    内置加权最短路径算法。系统会优先寻找同一文件夹下的“本地链路”，并对穿过 `define.js`、`common.js` 等全局“噪音节点”的行为进行逻辑惩罚。
5.  **量子路径融合 (Quantum Path Fusion)**: 
    无视相对路径、绝对路径或 Context Path 的维度偏差。无论路径如何书写，只要它们指向同一个物理实体，在月光下都将合二为一。

## 🚀 降临仪式 (Quick Start)

**1. 唤醒环境**
```bash
# 建议在虚拟环境中注入灵魂
pip install -r requirements.txt
```

**2. 建立逻辑坐标 (首次扫描)**
```bash
# 指定项目根目录，系统会自动记忆并建立缓存
python main.py stats --dir "C:\Work\LegacyProject"
```

**3. 开启寻踪**
```bash
# 逆向回溯：谁导致了这个页面的出现？
python main.py trace --target TargetPage.jsp --entry UserSearch.jsp --limit 1
```

## 🛠️ 统御指令集

| 指令 | 作用描述 | 核心参数 |
| :--- | :--- | :--- |
| `trace` | 执行双向链路寻踪 | `-t` (目标), `-e` (入口筛选), `-i` (屏蔽噪音), `-l` (精简输出) |
| `stats` | 审视废墟的逻辑规模 | `-r` (强制重载缓存) |
| `search` | 在迷雾中模糊搜索节点 | `-k` (关键字) |
| `check` | 针对单一文件的逻辑诊断 | `-f` (文件名/路径) |

## 📖 进阶协议：`--ignore` 的妙用
在那座废墟里，总是充斥着大量毫无参考价值的“逻辑垃圾”。你可以通过 `-i` 参数屏蔽它们，迫使引擎为你寻找更纯粹的业务主干：
```bash
python main.py trace -t Edit.jsp -i Header.jsp -i CommonAuth -l 1
```

## 🛰️ 缓存与刷新
本工具具备持久化记忆。除非你使用了 `--refresh` 或 `-r` 参数，否则它会瞬间从 `.tracer_cache` 中唤醒那张庞大的星图，响应速度跨越了地月距离。

---

✨ **让月光照亮每一处逻辑深渊。** 
*由月之公主 · 露娜 (Luna) 监制*

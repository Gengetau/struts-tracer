# Struts 1.x Static Link Analyzer (struts-tracer)

A professional static analysis tool designed for legacy Struts 1.x Java Web systems. It parses configuration files and source code to build a comprehensive directed graph of navigation paths (`JSP <-> Action <-> JSP`), allowing for bidirectional trace and link visualization.

## Key Features

- **Multi-Source Parsing**: Recursively scans all `struts-config*.xml` files in `WEB-INF` and maps global forwards and action mappings.
- **Advanced Source Scanning**: Scans JSP, JS, and INC files using high-precision regex to extract form actions, anchor links, and JavaScript-based redirects (`location.href`, `window.open`, etc.).
- **Recursive Inheritance**: Automatically handles `jsp:include` and script references. Parent JSPs inherit all jumping capabilities from their children and referenced JS files, ensuring no breaks in the logical chain.
- **JavaScript Constant Resolution**: Identifies path constants defined in JS files (e.g., `var SEARCH_PATH = "/Search.do"`) and resolves their usage across the project.
- **Weighted Shortest Path**: Utilizes a weighted Dijkstra algorithm to find the most relevant business paths, prioritizing local directory transitions and penalizing noise from global configuration files.
- **Quantum Path Fusion**: Harmonizes discrepancies between relative paths, absolute paths, and XML definitions to ensure nodes are correctly merged into the graph.
- **Persistence & Performance**: Implements a disk-based caching mechanism (`.tracer_cache`) for sub-second query response times on large projects (1,000+ JSPs).

## Installation

```bash
# Recommended to use a virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

1. **Initial Scan**: Point the tool to your project root to build the graph and cache.
   ```bash
   python main.py stats --dir "/path/to/your/project"
   ```

2. **Reverse Trace**: Find all paths leading to a specific page.
   ```bash
   python main.py trace --target MyView.jsp --entry Home.jsp --limit 1
   ```

## CLI Commands

| Command | Description | Key Arguments |
| :--- | :--- | :--- |
| `trace` | Perform bidirectional link tracing | `-t` (target), `-e` (entry), `-i` (ignore), `-l` (limit) |
| `stats` | Display project graph statistics | `-r` (force refresh cache) |
| `search` | Fuzzy search for nodes in the graph | `-k` (keyword) |
| `check` | Debug individual file extraction | `-f` (filename/path) |

## Advanced Filtering

Use the `--ignore` (or `-i`) flag to bypass common noise like headers, footers, or authentication actions:
```bash
python main.py trace -t EditAction.do -i Header.jsp -i Footer.jsp -l 1
```

## Project Structure

```text
struts-tracer/
├── main.py                 # CLI entry point
├── parser/
│   ├── xml_parser.py       # Config parsing logic
│   └── source_scanner.py   # Regex-based source scanning
├── core/
│   ├── graph_builder.py    # networkx graph construction
│   └── tracer_engine.py    # Pathfinding algorithms
└── utils/
    └── regex_rules.py      # Pattern library
```

---
*Developed for efficient legacy system auditing and documentation.*

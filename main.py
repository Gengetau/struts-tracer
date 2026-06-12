"""
CLI entry point for the Struts 1.x static route analyzer.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pickle
import sys
import time

import networkx as nx
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from core.graph_builder import RouteGraph
from core.tracer_engine import DEFAULT_MAX_DEPTH, TracerEngine
from parser.source_scanner import scan_project
from parser.xml_parser import scan_struts_configs

console = Console()
CONFIG_FILE = ".tracer_config"
CACHE_DIR = ".tracer_cache"


def _get_cache_path(project_dir: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path_hash = hashlib.md5(project_dir.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"graph_{path_hash}.pkl")


def _save_cache(project_dir: str, graph: RouteGraph, stats: dict, config_paths: list) -> None:
    cache_path = _get_cache_path(project_dir)
    try:
        with open(cache_path, "wb") as f:
            pickle.dump(
                {
                    "graph": graph,
                    "stats": stats,
                    "config_paths": config_paths,
                    "timestamp": time.time(),
                },
                f,
            )
    except Exception as exc:
        console.print(f"[dim yellow]Warning: failed to write cache: {exc}[/]")


def _load_cache(project_dir: str) -> dict | None:
    cache_path = _get_cache_path(project_dir)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None
    return None


def _save_config(project_dir: str) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(project_dir)
    except Exception:
        pass


def _load_config() -> str | None:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return None
    return None


def _get_project_dir(args_dir: str | None) -> str:
    """Resolve the project directory from CLI args or saved config."""
    if args_dir:
        abs_path = os.path.abspath(args_dir)
        _save_config(abs_path)
        return abs_path

    saved = _load_config()
    if saved:
        if os.path.isdir(saved):
            return saved
        console.print(f"[yellow]Warning: saved project path is no longer valid: {saved}[/]")

    console.print(
        "[red]Error: project directory is required. Pass --dir, or run once with --dir to save it.[/]"
    )
    sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="struts_tracer",
        description="Static route analyzer for Struts 1.x applications.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    trace = sub.add_parser("trace", help="Trace routes to or from a target page.")
    trace.add_argument("--target", "-t", required=True, help="Target page name; fuzzy matching is supported.")
    trace.add_argument("--dir", "-d", required=False, help="Project root directory.")
    trace.add_argument("--refresh", "-r", action="store_true", help="Force a fresh scan and ignore the cache.")
    trace.add_argument("--entry", "-e", action="append", help="Entry page to start from, such as UserSearch.jsp.")
    trace.add_argument("--ignore", "-i", action="append", help="Page or Action name to ignore; partial matches work.")
    trace.add_argument("--limit", "-l", type=int, default=0, help="Limit the number of displayed paths; 0 means no limit.")
    trace.add_argument(
        "--direction",
        choices=["reverse", "forward"],
        default="reverse",
        help="Trace direction: reverse traces back to entries; forward expands reachable pages.",
    )
    trace.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH, help=f"Maximum search depth; default {DEFAULT_MAX_DEPTH}.")

    stats = sub.add_parser("stats", help="Show project graph statistics.")
    stats.add_argument("--dir", "-d", required=False, help="Project root directory.")
    stats.add_argument("--refresh", "-r", action="store_true", help="Force a fresh scan and ignore the cache.")

    check = sub.add_parser("check", help="Debug extraction results for a specific JSP or JS file.")
    check.add_argument("--file", "-f", required=True, help="JSP or JS file path, relative or absolute.")
    check.add_argument("--dir", "-d", required=False, help="Project root directory.")

    search = sub.add_parser("search", help="Fuzzy search graph nodes.")
    search.add_argument("--dir", "-d", required=False, help="Project root directory.")
    search.add_argument("--keyword", "-k", required=True, help="Search keyword.")
    search.add_argument("--refresh", "-r", action="store_true", help="Force a fresh scan and ignore the cache.")

    return parser


def _build_graph(project_dir: str, refresh: bool = False) -> RouteGraph:
    """Run the parser pipeline and return the route graph, using cache when possible."""
    if not refresh:
        cached_data = _load_cache(project_dir)
        if cached_data:
            graph = cached_data["graph"]
            stats = cached_data["stats"]
            config_paths = cached_data["config_paths"]
            timestamp = cached_data["timestamp"]

            console.print(
                f"[dim blue]Loaded cached route graph from {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}[/]"
            )
            _print_summary(stats, config_paths)
            return graph

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        xml_task = progress.add_task("Parsing struts-config*.xml files...", total=None)
        xml_result, config_paths = scan_struts_configs(project_dir)
        progress.update(
            xml_task,
            description=f"Found {len(config_paths)} config files and {len(xml_result.action_forwards)} actions",
        )

        source_task = progress.add_task("Scanning JSP and JS source files...", total=100)

        def on_scan_progress(current, total):
            progress.update(source_task, total=total, completed=current, description=f"Scanning source files ({current}/{total})...")

        scan_result = scan_project(project_dir, progress_callback=on_scan_progress)
        progress.update(source_task, description=f"Scan complete: {scan_result.files_scanned} files")

        graph_task = progress.add_task("Building route graph and include inheritance...", total=None)
        graph = RouteGraph()
        stats = graph.build(xml_result, scan_result)
        progress.update(graph_task, description="Route graph built")

    _save_cache(project_dir, graph, stats, config_paths)
    _print_summary(stats, config_paths)
    return graph


def _print_summary(stats: dict, config_paths: list) -> None:
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_row("[bold]Config files[/]", str(len(config_paths)))
    summary.add_row("[bold]Actions[/]", str(stats.get("action_nodes", 0)))
    summary.add_row("[bold]JSP nodes[/]", str(stats.get("jsp_nodes", 0)))
    summary.add_row("[bold]Jump edges[/]", str(stats.get("jump_edges", 0)))
    summary.add_row("[bold]Constant jumps[/]", str(stats.get("constant_jumps", 0)))
    summary.add_row("[bold]Forward edges[/]", str(stats.get("forward_edges", 0)))
    summary.add_row("[bold]Include edges[/]", str(stats.get("include_edges", 0)))
    summary.add_row("[bold]Inherited edges[/]", str(stats.get("inherited_edges", 0)))
    console.print(Panel(summary, title="[bold cyan]Analysis Summary[/]", border_style="cyan"))


def _render_paths(result, target: str) -> None:
    """Render trace results with rich.Tree."""
    direction_label = "reverse" if result.direction == "reverse" else "forward"

    if not result.paths:
        console.print(f"[yellow]Warning: no path found for '{target}'[/]")
        return

    for warning in result.warnings:
        console.print(f"[dim yellow]Warning: {warning}[/]")

    console.print()
    console.print(
        Panel(
            f"[bold]Target:[/] {target}    [bold]Direction:[/] {direction_label}    [bold]Paths:[/] {len(result.paths)}",
            title="[bold magenta]Trace Results[/]",
            border_style="magenta",
        )
    )

    for index, trace_path in enumerate(result.paths, 1):
        tree = Tree(f"[bold green]Path {index}[/]")
        first_type, first_name = trace_path.labels()[0]
        first_label = _node_label(first_type, first_name, is_target=(len(trace_path.labels()) == 1))
        branch = tree.add(first_label)

        for type_tag, name in trace_path.labels()[1:]:
            is_target = name == target or name.endswith(target)
            label = _node_label(type_tag, name, is_target=is_target)
            branch = branch.add(label)

        console.print(tree)
        console.print()


def _node_label(node_type: str, name: str, is_target: bool = False) -> Text:
    """Build a styled node label."""
    color_map = {"JSP": "cyan", "Action": "yellow", "?": "white"}
    color = color_map.get(node_type, "white")

    text = Text()
    text.append(f"[{node_type}] ", style=color)
    text.append(name, style=f"bold {color}")

    if is_target:
        text.append(" target", style="bold red")

    return text


def cmd_trace(args) -> None:
    project_dir = _get_project_dir(args.dir)
    if not os.path.isdir(project_dir):
        console.print(f"[red]Error: directory does not exist: {project_dir}[/]")
        sys.exit(1)

    graph = _build_graph(project_dir, refresh=args.refresh)
    engine = TracerEngine(graph, max_depth=args.max_depth)

    console.print()
    action = "reverse trace" if args.direction == "reverse" else "forward trace"
    console.rule(f"[bold]Starting {action}: {args.target}[/]")

    if args.direction == "reverse":
        result = engine.trace_reverse(args.target, entries=args.entry, ignore=args.ignore)
    else:
        result = engine.trace_forward(args.target, ignore=args.ignore)

    if args.limit > 0:
        result.paths = result.paths[:args.limit]

    _render_paths(result, args.target)


def cmd_stats(args) -> None:
    project_dir = _get_project_dir(args.dir)
    if not os.path.isdir(project_dir):
        console.print(f"[red]Error: directory does not exist: {project_dir}[/]")
        sys.exit(1)

    graph = _build_graph(project_dir, refresh=args.refresh)

    jsp_nodes = [n for n in graph.g.nodes if graph.is_jsp(n)]
    isolated = list(nx.isolates(graph.g))
    entry_jsp = [n for n in jsp_nodes if graph.g.in_degree(n) == 0]

    extra = Table(show_header=False, box=None, padding=(0, 2))
    extra.add_row("[bold]Total nodes[/]", str(graph.node_count()))
    extra.add_row("[bold]Total edges[/]", str(graph.edge_count()))
    extra.add_row("[bold]Entry JSPs (in_degree=0)[/]", str(len(entry_jsp)))
    extra.add_row("[bold]Isolated nodes[/]", str(len(isolated)))

    console.print(Panel(extra, title="[bold cyan]Graph Statistics[/]", border_style="cyan"))

    if entry_jsp[:10]:
        console.print("[dim]Entry JSP examples:[/]")
        for jsp in entry_jsp[:10]:
            console.print(f"  [cyan]- {jsp}[/]")
        if len(entry_jsp) > 10:
            console.print(f"  [dim]... {len(entry_jsp)} total[/]")


def cmd_search(args) -> None:
    project_dir = _get_project_dir(args.dir)
    if not os.path.isdir(project_dir):
        console.print(f"[red]Error: directory does not exist: {project_dir}[/]")
        sys.exit(1)

    graph = _build_graph(project_dir, refresh=args.refresh)
    matches = graph.fuzzy_find(args.keyword, limit=30)

    if not matches:
        console.print(f"[yellow]Warning: no nodes matched '{args.keyword}'[/]")
        return

    console.print(f"\n[bold]Nodes matching '{args.keyword}' ({len(matches)}):[/]")
    for match in matches:
        tag = graph.node_type_label(match)
        color = "cyan" if tag == "JSP" else "yellow"
        console.print(f"  [{color}][{tag}] {match}[/{color}]")


def cmd_check(args) -> None:
    """Print regex extraction results for one source file."""
    from parser.source_scanner import ScanResult, _scan_file
    from utils.regex_rules import SKIP_DIRS

    project_dir = _get_project_dir(args.dir)
    file_input = args.file

    target_path = file_input
    if not os.path.isabs(target_path):
        target_path = os.path.abspath(os.path.join(project_dir, target_path))

    if not os.path.exists(target_path):
        console.print(f"[dim yellow]Direct path lookup failed. Searching project for: {file_input}...[/]")
        found_files = []
        filename_to_find = os.path.basename(file_input)
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            if filename_to_find in files:
                found_files.append(os.path.join(root, filename_to_find))

        if not found_files:
            console.print(f"[red]Error: file was not found in project: {file_input}[/]")
            return

        if len(found_files) > 1:
            console.print("[yellow]Warning: multiple candidate files found; using the first one:[/]")
            for candidate in found_files:
                console.print(f"  [cyan]- {candidate}[/]")

        target_path = found_files[0]

    console.print(
        Panel(
            f"Diagnostic file: [bold cyan]{target_path}[/]\nProject root: [dim]{project_dir}[/]",
            title="[bold]Extractor Debug[/]",
        )
    )

    scan_result = ScanResult()
    _scan_file(target_path, project_dir, scan_result)

    table = Table(title="Extracted Relations")
    table.add_column("Type", style="magenta")
    table.add_column("Target Path", style="green")

    for _jsp, actions in scan_result.jump_map.items():
        for action in actions:
            table.add_row("Jump (Action)", action)

    for _jsp, includes in scan_result.include_map.items():
        for include in includes:
            table.add_row("Include (JSP)", include)

    console.print(table)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    console.print(
        Panel(
            "[bold magenta]Struts 1.x Static Route Analyzer[/]",
            border_style="magenta",
        )
    )

    if args.command == "trace":
        cmd_trace(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "check":
        cmd_check(args)


if __name__ == "__main__":
    main()

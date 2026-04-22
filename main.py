"""
main.py — Struts 1.x 静态链路分析器 CLI 入口
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn

from parser.xml_parser import scan_struts_configs
from parser.source_scanner import scan_project
from core.graph_builder import RouteGraph
from core.tracer_engine import TracerEngine, DEFAULT_MAX_DEPTH

console = Console()


# ─── CLI 参数 ───

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="struts_tracer",
        description="Struts 1.x 静态路由链路分析器 — 月之公主御用",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # trace 子命令
    tr = sub.add_parser("trace", help="寻踪指定页面的链路")
    tr.add_argument("--target", "-t", required=True, help="目标页面名（支持模糊匹配）")
    tr.add_argument("--dir", "-d", required=True, help="项目根目录路径")
    tr.add_argument(
        "--direction",
        choices=["reverse", "forward"],
        default="reverse",
        help="寻踪方向: reverse=逆向回溯(默认), forward=正向推演",
    )
    tr.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH, help=f"最大搜索深度 (默认 {DEFAULT_MAX_DEPTH})")

    # stats 子命令
    st = sub.add_parser("stats", help="输出项目图统计信息")
    st.add_argument("--dir", "-d", required=True, help="项目根目录路径")

    # search 子命令
    se = sub.add_parser("search", help="模糊搜索节点")
    se.add_argument("--dir", "-d", required=True, help="项目根目录路径")
    se.add_argument("--keyword", "-k", required=True, help="搜索关键词")

    return p


# ─── 构建图 ───

def _build_graph(project_dir: str) -> RouteGraph:
    """执行完整解析流程并返回路由图"""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:

        # ── Phase 1: XML 解析 ──
        task = progress.add_task("解析 struts-config*.xml ...", total=None)
        xml_result, config_paths = scan_struts_configs(project_dir)

        progress.update(task, description=f"发现 {len(config_paths)} 个配置, {len(xml_result.action_forwards)} 个 Action")

        # ── Phase 2: 源码扫描 ──
        task2 = progress.add_task("正在扫描源码文件...", total=100)

        def on_scan_progress(current, total):
            progress.update(task2, total=total, completed=current, description=f"扫描 JSP/JS 源码 ({current}/{total})...")

        scan_result = scan_project(project_dir, progress_callback=on_scan_progress)

        progress.update(
            task2,
            description=(
                f"扫描完成: {scan_result.files_scanned} 文件, "
                f"提取 {scan_result.jump_relations} 跳转, "
                f"{scan_result.include_relations} Include"
            ),
        )

        # ── Phase 3: 构建图 ──
        task3 = progress.add_task("构建节点图 + Include 递归继承 ...", total=None)
        graph = RouteGraph()
        stats = graph.build(xml_result, scan_result)

        progress.update(
            task3,
            description=(
                f"图构建完成: {graph.node_count()} 节点, {graph.edge_count()} 边 "
                f"(继承 {stats.get('inherited_edges', 0)} 条, "
                f"环路断开 {stats.get('cycles_broken', 0)} 处)"
            ),
        )

    # ── 汇总面板 ──
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_row("[bold]配置文件[/]", str(len(config_paths)))
    summary.add_row("[bold]Action 数[/]", str(stats.get("action_nodes", 0)))
    summary.add_row("[bold]JSP 节点[/]", str(stats.get("jsp_nodes", 0)))
    summary.add_row("[bold]Jump 边[/]", str(stats.get("jump_edges", 0)))
    summary.add_row("[bold]Forward 边[/]", str(stats.get("forward_edges", 0)))
    summary.add_row("[bold]Include 边[/]", str(stats.get("include_edges", 0)))
    summary.add_row("[bold]继承边[/]", str(stats.get("inherited_edges", 0)))
    summary.add_row("[bold]环路断开[/]", str(stats.get("cycles_broken", 0)))
    console.print(Panel(summary, title="[bold cyan]📊 解析结果[/]", border_style="cyan"))

    return graph


# ─── 渲染链路 ───

def _render_paths(result, target: str) -> None:
    """用 rich.Tree 渲染寻踪结果"""
    direction_label = "逆向回溯" if result.direction == "reverse" else "正向推演"

    if not result.paths:
        console.print(f"[yellow]⚠ 未找到到达 '{target}' 的链路[/]")
        return

    for w in result.warnings:
        console.print(f"[dim yellow]⚠ {w}[/]")

    console.print()
    console.print(
        Panel(
            f"[bold]目标:[/] {target}    [bold]方向:[/] {direction_label}    [bold]链路数:[/] {len(result.paths)}",
            title="[bold magenta]🔗 寻踪结果[/]",
            border_style="magenta",
        )
    )

    for i, tp in enumerate(result.paths, 1):
        tree = Tree(f"[bold green]链路 {i}[/]")
        # 第一层
        first_type, first_name = tp.labels()[0]
        first_label = _node_label(first_type, first_name, is_target=(len(tp.labels()) == 1))
        branch = tree.add(first_label)

        for type_tag, name in tp.labels()[1:]:
            is_last = (name == tp.labels()[-1][1])
            is_tgt = (name == target or name.endswith(target))
            label = _node_label(type_tag, name, is_target=is_tgt)
            branch = branch.add(label)

        console.print(tree)
        console.print()


def _node_label(node_type: str, name: str, is_target: bool = False) -> Text:
    """生成带颜色的节点标签"""
    color_map = {"JSP": "cyan", "Action": "yellow", "?": "white"}
    color = color_map.get(node_type, "white")

    text = Text()
    text.append(f"[{node_type}] ", style=color)
    text.append(name, style=f"bold {color}")

    if is_target:
        text.append(" ★ 目标", style="bold red")

    return text


# ─── 子命令处理 ───

def cmd_trace(args) -> None:
    project_dir = os.path.abspath(args.dir)
    if not os.path.isdir(project_dir):
        console.print(f"[red]✗ 目录不存在: {project_dir}[/]")
        sys.exit(1)

    graph = _build_graph(project_dir)
    engine = TracerEngine(graph, max_depth=args.max_depth)

    console.print()
    console.rule(f"[bold]🔍 开始{'逆向回溯' if args.direction == 'reverse' else '正向推演'}: {args.target}[/]")

    if args.direction == "reverse":
        result = engine.trace_reverse(args.target)
    else:
        result = engine.trace_forward(args.target)

    _render_paths(result, args.target)


def cmd_stats(args) -> None:
    project_dir = os.path.abspath(args.dir)
    if not os.path.isdir(project_dir):
        console.print(f"[red]✗ 目录不存在: {project_dir}[/]")
        sys.exit(1)

    graph = _build_graph(project_dir)

    # 额外统计
    jsp_nodes = [n for n in graph.g.nodes if graph.is_jsp(n)]
    action_nodes = [n for n in graph.g.nodes if graph.is_action(n)]
    isolated = list(nx.isolates(graph.g))  # noqa: F821 (networkx already imported in graph_builder)

    # 入度为 0 的 JSP（入口页面）
    entry_jsp = [n for n in jsp_nodes if graph.g.in_degree(n) == 0]

    extra = Table(show_header=False, box=None, padding=(0, 2))
    extra.add_row("[bold]总节点[/]", str(graph.node_count()))
    extra.add_row("[bold]总边数[/]", str(graph.edge_count()))
    extra.add_row("[bold]入口 JSP (in_degree=0)[/]", str(len(entry_jsp)))
    extra.add_row("[bold]孤立节点[/]", str(len(isolated)))

    console.print(Panel(extra, title="[bold cyan]📈 图统计[/]", border_style="cyan"))

    if entry_jsp[:10]:
        console.print("[dim]入口 JSP 示例:[/]")
        for j in entry_jsp[:10]:
            console.print(f"  [cyan]• {j}[/]")
        if len(entry_jsp) > 10:
            console.print(f"  [dim]... 共 {len(entry_jsp)} 个[/]")


def cmd_search(args) -> None:
    project_dir = os.path.abspath(args.dir)
    if not os.path.isdir(project_dir):
        console.print(f"[red]✗ 目录不存在: {project_dir}[/]")
        sys.exit(1)

    graph = _build_graph(project_dir)
    matches = graph.fuzzy_find(args.keyword, limit=30)

    if not matches:
        console.print(f"[yellow]⚠ 未找到匹配 '{args.keyword}' 的节点[/]")
        return

    console.print(f"\n[bold]🔍 匹配 '{args.keyword}' 的节点 ({len(matches)}):[/]")
    for m in matches:
        tag = graph.node_type_label(m)
        color = "cyan" if tag == "JSP" else "yellow"
        console.print(f"  [{color}][{tag}] {m}[/{color}]")


# ─── Main ───

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    console.print(Panel(
        "[bold magenta]🌕 Struts 1.x 静态链路分析器[/]\n[dim]月之公主 · 降维审视地球遗产系统[/]",
        border_style="magenta",
    ))

    if args.command == "trace":
        cmd_trace(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "search":
        cmd_search(args)


if __name__ == "__main__":
    main()

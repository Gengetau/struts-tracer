"""
main.py — Struts 1.x 静态链路分析器 CLI 入口
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import pickle
import hashlib

import networkx as nx
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
CONFIG_FILE = ".tracer_config"
CACHE_DIR = ".tracer_cache"

# ─── 配置与缓存持久化 ───

def _get_cache_path(project_dir: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    # 使用路径哈希作为文件名，防止冲突
    h = hashlib.md5(project_dir.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f"graph_{h}.pkl")


def _save_cache(project_dir: str, graph: RouteGraph, stats: dict, config_paths: list) -> None:
    cache_path = _get_cache_path(project_dir)
    try:
        with open(cache_path, "wb") as f:
            pickle.dump({
                "graph": graph,
                "stats": stats,
                "config_paths": config_paths,
                "timestamp": time.time()
            }, f)
    except Exception as e:
        console.print(f"[dim yellow]⚠ 缓存写入失败: {e}[/]")


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
    """获取项目目录：优先使用参数，其次使用保存的配置"""
    if args_dir:
        abs_path = os.path.abspath(args_dir)
        _save_config(abs_path)
        return abs_path

    saved = _load_config()
    if saved:
        if os.path.isdir(saved):
            return saved
        else:
            console.print(f"[yellow]⚠ 已保存的路径不再有效: {saved}[/]")

    console.print("[red]✗ 错误: 未指定项目目录。请使用 --dir 指定，或先执行一次带 --dir 的指令以记录路径。[/]")
    sys.exit(1)


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
    tr.add_argument("--dir", "-d", required=False, help="项目根目录路径")
    tr.add_argument("--refresh", "-r", action="store_true", help="强制重新扫描（忽略缓存）")
    tr.add_argument("--entry", "-e", action="append", help="指定起始/入口页面（如 UserSearch.jsp）")
    tr.add_argument("--limit", "-l", type=int, default=0, help="限制显示的链路数量（0为不限制）")
    tr.add_argument(
        "--direction",
        choices=["reverse", "forward"],
        default="reverse",
        help="寻踪方向: reverse=逆向回溯(默认), forward=正向推演",
    )
    tr.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH, help=f"最大搜索深度 (默认 {DEFAULT_MAX_DEPTH})")

    # stats 子命令
    st = sub.add_parser("stats", help="输出项目图统计信息")
    st.add_argument("--dir", "-d", required=False, help="项目根目录路径")
    st.add_argument("--refresh", "-r", action="store_true", help="强制重新扫描（忽略缓存）")

    # check 子命令
    ck = sub.add_parser("check", help="调试：查看特定文件的跳转提取结果")
    ck.add_argument("--file", "-f", required=True, help="要检查的 JSP/JS 文件路径（相对或绝对）")
    ck.add_argument("--dir", "-d", required=False, help="项目根目录路径")

    # search 子命令
    se = sub.add_parser("search", help="模糊搜索节点")
    se.add_argument("--dir", "-d", required=False, help="项目根目录路径")
    se.add_argument("--keyword", "-k", required=True, help="搜索关键词")
    se.add_argument("--refresh", "-r", action="store_true", help="强制重新扫描（忽略缓存）")

    return p


# ─── 构建图 ───

def _build_graph(project_dir: str, refresh: bool = False) -> RouteGraph:
    """执行完整解析流程并返回路由图，支持缓存"""
    
    if not refresh:
        cached_data = _load_cache(project_dir)
        if cached_data:
            graph = cached_data["graph"]
            stats = cached_data["stats"]
            config_paths = cached_data["config_paths"]
            ts = cached_data["timestamp"]
            
            console.print(f"[dim blue]🌙 已加载缓存节点图 (更新于: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))})[/]")
            _print_summary(stats, config_paths)
            return graph

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        # ... (rest of the logic unchanged, but we need to capture stats and config_paths to save)
        # XML
        task = progress.add_task("解析 struts-config*.xml ...", total=None)
        xml_result, config_paths = scan_struts_configs(project_dir)
        progress.update(task, description=f"发现 {len(config_paths)} 个配置, {len(xml_result.action_forwards)} 个 Action")

        # Source
        task2 = progress.add_task("正在扫描源码文件...", total=100)
        def on_scan_progress(current, total):
            progress.update(task2, total=total, completed=current, description=f"扫描 JSP/JS 源码 ({current}/{total})...")
        scan_result = scan_project(project_dir, progress_callback=on_scan_progress)
        progress.update(task2, description=f"扫描完成: {scan_result.files_scanned} 文件")

        # Graph
        task3 = progress.add_task("构建节点图 + Include 递归继承 ...", total=None)
        graph = RouteGraph()
        stats = graph.build(xml_result, scan_result)
        progress.update(task3, description="图构建完成")

    # 保存缓存
    _save_cache(project_dir, graph, stats, config_paths)
    _print_summary(stats, config_paths)
    return graph


def _print_summary(stats: dict, config_paths: list) -> None:
    # ── 汇总面板 ──
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_row("[bold]配置文件[/]", str(len(config_paths)))
    summary.add_row("[bold]Action 数[/]", str(stats.get("action_nodes", 0)))
    summary.add_row("[bold]JSP 节点[/]", str(stats.get("jsp_nodes", 0)))
    summary.add_row("[bold]Jump 边[/]", str(stats.get("jump_edges", 0)))
    summary.add_row("[bold]Forward 边[/]", str(stats.get("forward_edges", 0)))
    summary.add_row("[bold]Include 边[/]", str(stats.get("include_edges", 0)))
    summary.add_row("[bold]继承边[/]", str(stats.get("inherited_edges", 0)))
    console.print(Panel(summary, title="[bold cyan]📊 解析结果[/]", border_style="cyan"))


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
    project_dir = _get_project_dir(args.dir)
    if not os.path.isdir(project_dir):
        console.print(f"[red]✗ 目录不存在: {project_dir}[/]")
        sys.exit(1)

    graph = _build_graph(project_dir, refresh=args.refresh)
    engine = TracerEngine(graph, max_depth=args.max_depth)

    console.print()
    console.rule(f"[bold]🔍 开始{'逆向回溯' if args.direction == 'reverse' else '正向推演'}: {args.target}[/]")

    if args.direction == "reverse":
        result = engine.trace_reverse(args.target, entries=args.entry)
    else:
        result = engine.trace_forward(args.target)

    # 限制显示数量
    if args.limit > 0:
        result.paths = result.paths[:args.limit]

    _render_paths(result, args.target)


def cmd_stats(args) -> None:
    project_dir = _get_project_dir(args.dir)
    if not os.path.isdir(project_dir):
        console.print(f"[red]✗ 目录不存在: {project_dir}[/]")
        sys.exit(1)

    graph = _build_graph(project_dir, refresh=args.refresh)

    # 额外统计
    jsp_nodes = [n for n in graph.g.nodes if graph.is_jsp(n)]
    action_nodes = [n for n in graph.g.nodes if graph.is_action(n)]
    isolated = list(nx.isolates(graph.g))

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
    project_dir = _get_project_dir(args.dir)
    if not os.path.isdir(project_dir):
        console.print(f"[red]✗ 目录不存在: {project_dir}[/]")
        sys.exit(1)

    graph = _build_graph(project_dir, refresh=args.refresh)
    matches = graph.fuzzy_find(args.keyword, limit=30)

    if not matches:
        console.print(f"[yellow]⚠ 未找到匹配 '{args.keyword}' 的节点[/]")
        return

    console.print(f"\n[bold]🔍 匹配 '{args.keyword}' 的节点 ({len(matches)}):[/]")
    for m in matches:
        tag = graph.node_type_label(m)
        color = "cyan" if tag == "JSP" else "yellow"
        console.print(f"  [{color}][{tag}] {m}[/{color}]")


def cmd_check(args) -> None:
    """调试命令：直接输出单个文件的正则匹配结果"""
    from parser.source_scanner import _scan_file, ScanResult
    
    project_dir = _get_project_dir(args.dir)
    file_path = args.file
    if not os.path.isabs(file_path):
        file_path = os.path.join(project_dir, file_path)
    
    if not os.path.exists(file_path):
        console.print(f"[red]✗ 文件不存在: {file_path}[/]")
        return

    console.print(Panel(f"正在诊断文件: [bold cyan]{file_path}[/]", title="[bold]🛠️ 提取器调试[/]"))
    
    res = ScanResult()
    _scan_file(file_path, project_dir, res)
    
    table = Table(title="提取到的关系")
    table.add_column("类型", style="magenta")
    table.add_column("目标路径", style="green")
    
    for jsp, actions in res.jump_map.items():
        for a in actions:
            table.add_row("Jump (Action)", a)
            
    for jsp, incs in res.include_map.items():
        for i in incs:
            table.add_row("Include (JSP)", i)
            
    console.print(table)


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
    elif args.command == "check":
        cmd_check(args)


if __name__ == "__main__":
    main()

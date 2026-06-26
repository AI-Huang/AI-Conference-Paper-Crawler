#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Terminal (TUI) crawl-speed dashboard built on the monitor base.

Renders a live, self-refreshing panel using rich. It is a thin presentation
layer over :class:`CrawlStatsCollector`; all statistics come from the base.

Run::

    uv run python -m ai_conference_paper_crawler.monitor.tui --interval 5
"""

import argparse
import time
from collections import deque

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .collector import CrawlStatsCollector

_SPARK = " ▁▂▃▄▅▆▇█"


def _fmt_duration(seconds):
    """Format a number of seconds as ``H:MM:SS`` (or ``MM:SS``)."""
    if seconds is None:
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _sparkline(values, width=40):
    """Render recent values as a unicode sparkline."""
    if not values:
        return ""
    recent = list(values)[-width:]
    lo, hi = min(recent), max(recent)
    span = (hi - lo) or 1.0
    return "".join(
        _SPARK[min(len(_SPARK) - 1, int((v - lo) / span * (len(_SPARK) - 1)))]
        for v in recent
    )


def _render(stats, rate_history):
    """Build the rich renderable for one frame from a Stats snapshot."""
    rate_color = "green" if stats.rate_avg > 0 else "yellow"

    head = Table.grid(expand=True)
    head.add_column(justify="left")
    head.add_column(justify="right")
    head.add_row(
        Text("AI Conference Paper Crawler — 实时爬取速度", style="bold cyan"),
        Text(time.strftime("%Y-%m-%d %H:%M:%S"), style="dim"),
    )

    body = Table.grid(padding=(0, 2))
    body.add_column(justify="right", style="bold")
    body.add_column(justify="left")
    body.add_row("已抓取总数", f"[bold white]{stats.total:,}[/]")
    body.add_row("本轮新增", f"+{stats.delta} / {stats.interval_s:.1f}s")
    body.add_row(
        "速度 items/min",
        f"瞬时 [bold {rate_color}]{stats.rate_instant:.1f}[/]  "
        f"平均 [bold]{stats.rate_avg:.1f}[/]  "
        f"EMA [bold]{stats.rate_ema:.1f}[/]",
    )
    body.add_row("已运行", _fmt_duration(stats.elapsed_s))
    if stats.target:
        pct = (stats.total / stats.target * 100.0) if stats.target else 0.0
        body.add_row(
            "目标 / 进度",
            f"{stats.target:,}  ({pct:.1f}%)  ETA {_fmt_duration(stats.eta_s)}",
        )
    if stats.abstract_pct is not None:
        body.add_row(
            "abstract 覆盖", f"{stats.with_abstract:,} ({stats.abstract_pct:.1f}%)"
        )
    body.add_row("PDF 落地", f"{stats.with_local_path:,} ({stats.local_path_pct:.1f}%)")
    body.add_row("速度趋势", Text(_sparkline(rate_history), style=rate_color))

    groups = Table(title="按会议 / 年份", title_style="dim", expand=True, box=None)
    groups.add_column("会议", style="cyan")
    groups.add_column("数量", justify="right")
    for name, n in list(stats.per_group.items())[:12]:
        groups.add_row(name, f"{n:,}")

    return Panel(
        Group(head, Text(""), body, Text(""), groups),
        border_style=rate_color,
        title="[bold]crawl monitor[/]",
        subtitle=f"[dim]refresh {stats.interval_s:.0f}s · Ctrl-C 退出[/]",
    )


def run_tui(interval=5.0, target=None, window=12, persist=True):
    """Run the live terminal dashboard until interrupted."""
    rate_history = deque(maxlen=60)
    with CrawlStatsCollector(
        target=target, window=window, persist=persist
    ) as collector:
        # Seed the sparkline with the real crawl history (from papers.scraped_at)
        # so it reaches back to the start of the crawl, then fall back to the
        # monitor's own persisted samples if no papers are stored yet.
        seed = collector.load_paper_history() or collector.load_history(
            limit=rate_history.maxlen
        )
        for sample in seed[-rate_history.maxlen :]:
            rate_history.append(sample["ema"])
        with Live(auto_refresh=False, screen=False) as live:
            try:
                while True:
                    collector.poll()
                    stats = collector.stats()
                    rate_history.append(stats.rate_ema)
                    live.update(_render(stats, rate_history), refresh=True)
                    time.sleep(interval)
            except KeyboardInterrupt:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Live crawl-speed TUI dashboard")
    parser.add_argument("--interval", type=float, default=5.0, help="refresh seconds")
    parser.add_argument(
        "--target", type=int, default=None, help="expected total for ETA"
    )
    parser.add_argument("--window", type=int, default=12, help="rolling avg samples")
    parser.add_argument(
        "--no-persist",
        dest="persist",
        action="store_false",
        help="do not write samples to crawl_speed_history",
    )
    parser.set_defaults(persist=True)
    args = parser.parse_args(argv)
    run_tui(
        interval=args.interval,
        target=args.target,
        window=args.window,
        persist=args.persist,
    )


if __name__ == "__main__":
    main()

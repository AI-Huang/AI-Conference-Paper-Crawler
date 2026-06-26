#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live terminal dashboard for crawl speed, headlined by papers/second.

A stdlib-only renderer (no extra dependencies) that owns the polling cadence and
repaints an in-place dashboard each tick. The headline metric is **papers per
second**; papers/min, totals, coverage and ETA are shown as supporting context.

Run it::

    python -m ai_conference_paper_crawler.monitor            # default 2s cadence
    python -m ai_conference_paper_crawler.monitor --interval 5 --target 4068
"""

import shutil
import time
from datetime import timedelta

from .collector import CrawlStatsCollector

_CLEAR = "\033[2J\033[H"  # clear screen + home cursor
_HIDE_CURSOR = "\033[?25l"
_SHOW_CURSOR = "\033[?25h"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"


def _fmt_duration(seconds):
    """Render a second count as a compact ``H:MM:SS`` (or ``MM:SS``) string."""
    if seconds is None:
        return "—"
    return str(timedelta(seconds=int(max(0, seconds))))


def _sparkline(values, width=None):
    """Render a unicode sparkline for a sequence of numbers."""
    blocks = "▁▂▃▄▅▆▇█"
    nums = [v for v in values if v is not None]
    if not nums:
        return ""
    if width:
        nums = nums[-width:]
    lo, hi = min(nums), max(nums)
    span = (hi - lo) or 1.0
    return "".join(blocks[int((v - lo) / span * (len(blocks) - 1))] for v in nums)


def render(stats, history, *, paused=False):
    """Build the dashboard text for one frame from a :class:`Stats` snapshot."""
    cols = shutil.get_terminal_size((80, 24)).columns
    bar = "─" * min(cols, 60)

    title = " AI-Conference-Paper-Crawler · Live Speed Board "
    lines = [
        f"{_BOLD}{_CYAN}{title}{_RESET}",
        f"{_DIM}{bar}{_RESET}",
    ]

    # Headline: papers per second.
    pps = stats.rate_ema_s or stats.rate_avg_s
    lines.append(
        f"{_BOLD}{_GREEN}{pps:>8.3f}{_RESET} {_BOLD}papers/sec{_RESET}"
        f"   {_DIM}(instant {stats.rate_instant_s:.3f} · "
        f"avg {stats.rate_avg_s:.3f}){_RESET}"
    )
    lines.append(
        f"{_DIM}≈ {_RESET}{stats.rate_ema:>8.1f} {_DIM}papers/min"
        f"   (avg {stats.rate_avg:.1f}/min){_RESET}"
    )
    lines.append(f"{_DIM}{bar}{_RESET}")

    # Totals and progress.
    lines.append(
        f"  total      {_BOLD}{stats.total:>8,}{_RESET}"
        f"   {_DIM}(+{stats.delta} in {stats.interval_s:.1f}s){_RESET}"
    )
    if stats.target:
        pct = stats.total / stats.target * 100.0 if stats.target else 0.0
        lines.append(
            f"  target     {stats.target:>8,}   {_YELLOW}{pct:5.1f}%{_RESET}"
            f"   {_DIM}ETA {_fmt_duration(stats.eta_s)}{_RESET}"
        )
    lines.append(f"  elapsed    {_fmt_duration(stats.elapsed_s):>8}")
    lines.append(
        f"  pdf saved  {stats.with_local_path:>8,}"
        f"   {_DIM}{stats.local_path_pct:.1f}%{_RESET}"
    )
    if stats.with_abstract is not None:
        lines.append(
            f"  abstracts  {stats.with_abstract:>8,}"
            f"   {_DIM}{stats.abstract_pct:.1f}%{_RESET}"
        )

    # Trend sparkline of papers/sec.
    spark = _sparkline([s for s in history], width=min(cols, 50))
    if spark:
        lines.append(f"{_DIM}{bar}{_RESET}")
        lines.append(f"  trend  {_GREEN}{spark}{_RESET} {_DIM}papers/sec{_RESET}")

    # Per conference/year breakdown (top rows).
    if stats.per_group:
        lines.append(f"{_DIM}{bar}{_RESET}")
        top = sorted(stats.per_group.items(), key=lambda kv: kv[1], reverse=True)
        for name, n in top[:8]:
            lines.append(f"  {name:<20}{n:>8,}")

    lines.append(f"{_DIM}{bar}{_RESET}")
    state = f"{_YELLOW}paused{_RESET}" if paused else f"{_GREEN}live{_RESET}"
    lines.append(f"{_DIM}  {state}{_DIM} · Ctrl-C to quit{_RESET}")
    return "\n".join(lines)


def run(*, interval=2.0, target=None, window=12, ema_alpha=0.3):
    """Poll the DB on a fixed cadence and repaint the dashboard until Ctrl-C."""
    history = []
    print(_HIDE_CURSOR, end="", flush=True)
    try:
        with CrawlStatsCollector(
            target=target, window=window, ema_alpha=ema_alpha
        ) as collector:
            while True:
                collector.poll()
                stats = collector.stats()
                history.append(stats.rate_ema_s or stats.rate_avg_s)
                history = history[-200:]
                frame = render(stats, history)
                print(_CLEAR + frame, end="", flush=True)
                time.sleep(max(0.5, interval))
    except KeyboardInterrupt:
        pass
    finally:
        print(_SHOW_CURSOR)

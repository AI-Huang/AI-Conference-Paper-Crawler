#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI entry for the live crawl-speed dashboard (papers/second headline).

Usage::

    python -m ai_conference_paper_crawler.monitor
    python -m ai_conference_paper_crawler.monitor --interval 5 --target 4068
"""

import argparse

from .terminal import run


def main():
    parser = argparse.ArgumentParser(
        description="Live terminal dashboard: papers crawled per second."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="seconds between DB polls / repaints (default: 2)",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=None,
        help="expected total paper count, used to show progress and ETA",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=12,
        help="number of recent samples for the rolling average (default: 12)",
    )
    parser.add_argument(
        "--ema-alpha",
        type=float,
        default=0.3,
        help="EMA smoothing factor 0-1; higher reacts faster (default: 0.3)",
    )
    args = parser.parse_args()

    run(
        interval=args.interval,
        target=args.target,
        window=args.window,
        ema_alpha=args.ema_alpha,
    )


if __name__ == "__main__":
    main()

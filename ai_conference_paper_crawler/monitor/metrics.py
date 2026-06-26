#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Metric data structures shared by every crawl-speed dashboard renderer.

The collector produces a :class:`Snapshot` (raw counts at a point in time) and
derives a :class:`Stats` (totals + rates + coverage). ``Stats.to_dict()`` is the
single serialization contract consumed by both the terminal (TUI) and web
dashboards, and by the web JSON API.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, Optional


@dataclass
class Snapshot:
    """Raw counts sampled from the database at one instant."""

    ts: float  # epoch seconds
    total: int
    with_local_path: int
    with_abstract: Optional[int] = None
    # {"CVPR 2026": 4068, ...} — optional per conference/year breakdown.
    per_group: Dict[str, int] = field(default_factory=dict)


@dataclass
class Stats:
    """Derived metrics ready for rendering. Serializable via :meth:`to_dict`."""

    ts: float
    total: int
    delta: int  # rows added since the previous snapshot
    interval_s: float  # seconds between the last two snapshots
    elapsed_s: float  # seconds since the collector started
    started_total: int  # row count when the collector started

    rate_instant: float  # items/min over the last interval
    rate_avg: float  # items/min over the rolling window
    rate_ema: float  # exponentially smoothed items/min

    rate_instant_s: float  # items/sec over the last interval
    rate_avg_s: float  # items/sec over the rolling window
    rate_ema_s: float  # exponentially smoothed items/sec

    with_local_path: int
    local_path_pct: float
    with_abstract: Optional[int] = None
    abstract_pct: Optional[float] = None

    target: Optional[int] = None
    eta_s: Optional[float] = None  # seconds to reach target at rate_avg

    per_group: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

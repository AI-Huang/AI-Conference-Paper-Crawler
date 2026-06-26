#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crawl-speed monitoring base shared by the terminal and web dashboards."""

from .collector import CrawlStatsCollector
from .metrics import Snapshot, Stats
from .terminal import render, run

__all__ = ["CrawlStatsCollector", "Snapshot", "Stats", "render", "run"]

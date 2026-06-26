#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Renderer-agnostic crawl-speed collector (the dashboard base).

Polls the MySQL ``papers`` table on demand, keeps a bounded rolling history of
snapshots, and derives speed metrics. Both the terminal and web dashboards build
on this single class so the statistics logic lives in exactly one place.

Typical use (a renderer owns the cadence, e.g. every 5s)::

    from ai_conference_paper_crawler.monitor import CrawlStatsCollector

    collector = CrawlStatsCollector(target=4068)
    while True:
        collector.poll()
        stats = collector.stats()
        render(stats.to_dict())
        time.sleep(5)
"""

import time
from collections import deque

from ai_conference_paper_crawler.services import MySQLService

from .metrics import Snapshot, Stats


class CrawlStatsCollector:
    """Sample the ``papers`` table and compute crawl-speed statistics.

    Args:
        service: a :class:`MySQLService`; one is created if omitted.
        window: number of recent snapshots used for the rolling average rate.
            With a 5s cadence, ``window=12`` averages over ~1 minute.
        ema_alpha: smoothing factor (0-1) for the EMA rate; higher reacts faster.
        target: optional expected total used to estimate ETA.
        track_groups: also collect a per conference/year breakdown each poll.
        persist: when True, append every sampled :class:`Stats` to the MySQL
            ``crawl_speed_history`` table so the speed curve survives restarts.
    """

    def __init__(
        self,
        service=None,
        *,
        window=12,
        ema_alpha=0.3,
        target=None,
        track_groups=True,
        persist=False,
    ):
        self.service = service or MySQLService()
        self.history = deque(maxlen=max(2, window))
        self.ema_alpha = ema_alpha
        self.target = target
        self.track_groups = track_groups
        self.persist = persist
        self.last_persist_error = None

        self._has_abstract = None  # detected lazily on first poll
        self._speed_schema_ready = False
        self._start_ts = None
        self._start_total = None
        self._ema = None

    # -- detection ------------------------------------------------------------

    def _detect_columns(self, conn):
        """Detect optional columns once so the base tolerates schema drift."""
        if self._has_abstract is not None:
            return
        with conn.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM papers")
            cols = {row["Field"] for row in cursor.fetchall()}
        self._has_abstract = "abstract" in cols

    # -- sampling -------------------------------------------------------------

    def poll(self) -> Snapshot:
        """Query the DB once and append a fresh snapshot to the history."""
        conn = self.service.connect()
        self._detect_columns(conn)

        abstract_expr = (
            "SUM(abstract IS NOT NULL AND abstract <> '')"
            if self._has_abstract
            else "NULL"
        )
        agg_sql = (
            "SELECT COUNT(*) AS total, "
            "SUM(local_path IS NOT NULL) AS with_local_path, "
            f"{abstract_expr} AS with_abstract "
            "FROM papers"
        )
        with conn.cursor() as cursor:
            cursor.execute(agg_sql)
            row = cursor.fetchone()

        per_group = {}
        if self.track_groups:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT conference, year, COUNT(*) AS n FROM papers "
                    "GROUP BY conference, year ORDER BY n DESC"
                )
                for r in cursor.fetchall():
                    per_group[f"{r['conference']} {r['year']}"] = int(r["n"])

        snapshot = Snapshot(
            ts=time.time(),
            total=int(row["total"] or 0),
            with_local_path=int(row["with_local_path"] or 0),
            with_abstract=(
                int(row["with_abstract"] or 0) if self._has_abstract else None
            ),
            per_group=per_group,
        )

        if self._start_ts is None:
            self._start_ts = snapshot.ts
            self._start_total = snapshot.total

        self.history.append(snapshot)
        self._update_ema()
        if self.persist:
            self._record(conn)
        return snapshot

    def _record(self, conn):
        """Append the current derived Stats to the speed-history table.

        Persistence is a monitoring side effect: a transient failure must not
        kill the live dashboard, so errors are captured rather than raised.
        """
        try:
            if not self._speed_schema_ready:
                self.service.ensure_speed_schema()
                self._speed_schema_ready = True
            self.service.record_speed(self.stats())
            self.last_persist_error = None
        except Exception as exc:  # non-fatal for the dashboard
            self.last_persist_error = str(exc)

    def _update_ema(self):
        if len(self.history) < 2:
            return
        prev, last = self.history[-2], self.history[-1]
        dt = max(1e-9, last.ts - prev.ts)
        instant = (last.total - prev.total) / dt * 60.0
        if self._ema is None:
            self._ema = instant
        else:
            self._ema = self.ema_alpha * instant + (1 - self.ema_alpha) * self._ema

    # -- derivation -----------------------------------------------------------

    def stats(self) -> Stats:
        """Compute derived metrics from the current history. Poll first."""
        if not self.history:
            raise RuntimeError("call poll() before stats()")

        last = self.history[-1]
        prev = self.history[-2] if len(self.history) >= 2 else last
        oldest = self.history[0]

        interval_s = max(0.0, last.ts - prev.ts)
        delta = last.total - prev.total
        rate_instant = (delta / interval_s * 60.0) if interval_s > 0 else 0.0

        window_s = max(0.0, last.ts - oldest.ts)
        rate_avg = (
            (last.total - oldest.total) / window_s * 60.0 if window_s > 0 else 0.0
        )

        elapsed_s = max(0.0, last.ts - (self._start_ts or last.ts))

        eta_s = None
        if self.target and rate_avg > 0 and self.target > last.total:
            eta_s = (self.target - last.total) / rate_avg * 60.0

        total = last.total or 0
        local_path_pct = (last.with_local_path / total * 100.0) if total else 0.0
        abstract_pct = None
        if last.with_abstract is not None and total:
            abstract_pct = last.with_abstract / total * 100.0

        return Stats(
            ts=last.ts,
            total=total,
            delta=delta,
            interval_s=interval_s,
            elapsed_s=elapsed_s,
            started_total=self._start_total or 0,
            rate_instant=round(rate_instant, 2),
            rate_avg=round(rate_avg, 2),
            rate_ema=round(self._ema or 0.0, 2),
            rate_instant_s=round(rate_instant / 60.0, 4),
            rate_avg_s=round(rate_avg / 60.0, 4),
            rate_ema_s=round((self._ema or 0.0) / 60.0, 4),
            with_local_path=last.with_local_path,
            local_path_pct=round(local_path_pct, 2),
            with_abstract=last.with_abstract,
            abstract_pct=round(abstract_pct, 2) if abstract_pct is not None else None,
            target=self.target,
            eta_s=round(eta_s, 1) if eta_s is not None else None,
            per_group=dict(last.per_group),
        )

    # -- lifecycle ------------------------------------------------------------

    def load_history(self, limit=500, since=None):
        """Return persisted speed samples (oldest first) for seeding a chart.

        Each item is ``{t, total, delta, instant, avg, ema}``. Returns an empty
        list if the history table is missing or unreadable.
        """
        try:
            self.service.ensure_speed_schema()
            self._speed_schema_ready = True
            return self.service.load_speed_history(limit=limit, since=since)
        except Exception as exc:  # history is best-effort
            self.last_persist_error = str(exc)
            return []

    def close(self):
        self.service.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

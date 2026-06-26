#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MySQL service for persisting paper metadata.

Connection settings are read from the environment (loaded from ``.env`` by the
Scrapy settings module), so credentials never live in source control:

    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE

The service is a thin wrapper over PyMySQL that creates the target database and
the ``papers`` table on demand and upserts :class:`PaperItem`-shaped records
(see ``.agile/req/database-schema.md``).

Example::

    from ai_conference_paper_crawler.services import MySQLService

    with MySQLService() as db:
        db.ensure_schema()
        db.upsert_paper({
            "paper_id": "a1b2...",
            "conference": "CVPR",
            "year": 2017,
            "title": "Example Paper",
            "authors": ["A. Author"],
            "pdf_url": "https://.../Example.pdf",
        })
"""

import json
import os
from datetime import datetime, timezone

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

# Ensure DB credentials from .env are available even when this service is used
# outside the Scrapy runtime (e.g. standalone scripts). override=True lets the
# project's .env win over stale shell variables from other projects.
load_dotenv(override=True)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id    VARCHAR(64)  NOT NULL,
    conference  VARCHAR(32)  NOT NULL,
    year        SMALLINT     NOT NULL,
    title       TEXT         NOT NULL,
    authors     JSON         NULL,
    pdf_url     VARCHAR(1024) NOT NULL,
    local_path  VARCHAR(1024) NULL,
    source_page VARCHAR(1024) NULL,
    scraped_at  DATETIME     NOT NULL,
    PRIMARY KEY (paper_id),
    KEY idx_conf_year (conference, year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_CREATE_SPEED_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS crawl_speed_history (
    id              BIGINT       NOT NULL AUTO_INCREMENT,
    ts              DOUBLE       NOT NULL,
    recorded_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total           INT          NOT NULL,
    delta           INT          NOT NULL DEFAULT 0,
    rate_instant    DOUBLE       NOT NULL DEFAULT 0,
    rate_avg        DOUBLE       NOT NULL DEFAULT 0,
    rate_ema        DOUBLE       NOT NULL DEFAULT 0,
    with_local_path INT          NULL,
    with_abstract   INT          NULL,
    PRIMARY KEY (id),
    KEY idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_INSERT_SPEED_SQL = """
INSERT INTO crawl_speed_history
    (ts, total, delta, rate_instant, rate_avg, rate_ema,
     with_local_path, with_abstract)
VALUES
    (%(ts)s, %(total)s, %(delta)s, %(rate_instant)s, %(rate_avg)s, %(rate_ema)s,
     %(with_local_path)s, %(with_abstract)s)
"""

_UPSERT_SQL = """
INSERT INTO papers
    (paper_id, conference, year, title, authors, pdf_url,
     local_path, source_page, scraped_at)
VALUES
    (%(paper_id)s, %(conference)s, %(year)s, %(title)s, %(authors)s, %(pdf_url)s,
     %(local_path)s, %(source_page)s, %(scraped_at)s)
ON DUPLICATE KEY UPDATE
    conference  = VALUES(conference),
    year        = VALUES(year),
    title       = VALUES(title),
    authors     = VALUES(authors),
    pdf_url     = VALUES(pdf_url),
    local_path  = VALUES(local_path),
    source_page = VALUES(source_page),
    scraped_at  = VALUES(scraped_at)
"""


class MySQLService:
    """Manage a MySQL connection and persist paper metadata."""

    def __init__(
        self,
        host=None,
        port=None,
        user=None,
        password=None,
        database=None,
    ):
        self.host = host or os.environ.get("MYSQL_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("MYSQL_PORT", 3306))
        self.user = user or os.environ.get("MYSQL_USER", "root")
        self.password = (
            password if password is not None else os.environ.get("MYSQL_PASSWORD", "")
        )
        self.database = database or os.environ.get(
            "MYSQL_DATABASE", "ai_conference_paper_crawler"
        )
        self._conn = None

    # -- connection lifecycle -------------------------------------------------

    def connect(self):
        """Open the connection, creating the target database if missing."""
        if self._conn is not None and self._conn.open:
            return self._conn

        # Connect without a database first so we can create it on demand.
        server = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            charset="utf8mb4",
            autocommit=True,
        )
        try:
            with server.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self.database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        finally:
            server.close()

        self._conn = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )
        return self._conn

    def close(self):
        """Close the connection if open."""
        if self._conn is not None and self._conn.open:
            self._conn.close()
        self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # -- schema & writes ------------------------------------------------------

    def ensure_schema(self):
        """Create the ``papers`` table if it does not already exist."""
        conn = self.connect()
        with conn.cursor() as cursor:
            cursor.execute(_CREATE_TABLE_SQL)
        conn.commit()

    def ensure_speed_schema(self):
        """Create the ``crawl_speed_history`` table if it does not exist."""
        conn = self.connect()
        with conn.cursor() as cursor:
            cursor.execute(_CREATE_SPEED_TABLE_SQL)
        conn.commit()

    def record_speed(self, stats):
        """Persist one crawl-speed sample.

        Accepts a :class:`~..monitor.metrics.Stats` (anything with
        ``to_dict``) or a plain dict shaped like ``Stats.to_dict()``.
        """
        data = stats.to_dict() if hasattr(stats, "to_dict") else dict(stats)
        params = {
            "ts": float(data.get("ts") or 0.0),
            "total": int(data.get("total") or 0),
            "delta": int(data.get("delta") or 0),
            "rate_instant": float(data.get("rate_instant") or 0.0),
            "rate_avg": float(data.get("rate_avg") or 0.0),
            "rate_ema": float(data.get("rate_ema") or 0.0),
            "with_local_path": data.get("with_local_path"),
            "with_abstract": data.get("with_abstract"),
        }
        conn = self.connect()
        with conn.cursor() as cursor:
            cursor.execute(_INSERT_SPEED_SQL, params)
        conn.commit()

    def upsert_paper(self, record):
        """Insert or update a single paper record. Returns affected row count."""
        conn = self.connect()
        with conn.cursor() as cursor:
            count = cursor.execute(_UPSERT_SQL, self._normalize(record))
        conn.commit()
        return count

    def upsert_papers(self, records):
        """Insert or update many records in one transaction. Returns the count."""
        rows = [self._normalize(r) for r in records]
        if not rows:
            return 0
        conn = self.connect()
        with conn.cursor() as cursor:
            count = cursor.executemany(_UPSERT_SQL, rows)
        conn.commit()
        return count

    # -- reads ----------------------------------------------------------------

    def get_paper(self, paper_id):
        """Return a single paper row as a dict, or ``None`` if absent."""
        conn = self.connect()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM papers WHERE paper_id = %s", (paper_id,))
            return cursor.fetchone()

    def load_speed_history(self, limit=500, since=None):
        """Return persisted speed samples in chronological (ascending) order.

        Each item is a render-ready dict: ``{t, total, delta, instant, avg,
        ema}``. ``limit`` caps how many of the most recent rows are returned;
        ``since`` (epoch seconds) optionally restricts to newer samples.
        """
        conn = self.connect()
        clauses, params = [], []
        if since is not None:
            clauses.append("ts >= %s")
            params.append(float(since))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT ts, total, delta, rate_instant, rate_avg, rate_ema "
                f"FROM crawl_speed_history{where} ORDER BY ts DESC LIMIT %s",
                params,
            )
            rows = cursor.fetchall()
        rows.reverse()  # oldest first for charting
        return [
            {
                "t": float(r["ts"]),
                "total": int(r["total"]),
                "delta": int(r["delta"]),
                "instant": float(r["rate_instant"]),
                "avg": float(r["rate_avg"]),
                "ema": float(r["rate_ema"]),
            }
            for r in rows
        ]

    def load_paper_history(self, bucket_seconds=60, ema_alpha=0.3, since=None):
        """Reconstruct the crawl-speed curve from ``papers.scraped_at``.

        Unlike :meth:`load_speed_history` (which only has rows from when the
        monitor was running), this derives the *actual* crawl timeline from when
        each paper was stored, so a dashboard can show history reaching back to
        the start of the crawl. Papers are grouped into ``bucket_seconds`` time
        buckets; each item is a render-ready dict ``{t, total, delta, instant,
        avg, ema}`` where ``t`` is the bucket-start epoch (UTC) and rates are in
        items/min.
        """
        bucket = max(1, int(bucket_seconds))
        # TIMESTAMPDIFF treats scraped_at (stored as a UTC wall-clock DATETIME)
        # as UTC, yielding a true epoch regardless of the server time zone.
        epoch_expr = "TIMESTAMPDIFF(SECOND, '1970-01-01 00:00:00', scraped_at)"
        clauses = ["scraped_at IS NOT NULL"]
        params = [bucket, bucket]
        if since is not None:
            clauses.append(f"{epoch_expr} >= %s")
            params.append(float(since))
        where = " AND ".join(clauses)
        conn = self.connect()
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT FLOOR({epoch_expr} / %s) * %s AS bucket, COUNT(*) AS n "
                f"FROM papers WHERE {where} GROUP BY bucket ORDER BY bucket",
                params,
            )
            rows = cursor.fetchall()

        out, cumulative, ema = [], 0, None
        for r in rows:
            n = int(r["n"])
            cumulative += n
            instant = n / bucket * 60.0
            ema = (
                instant if ema is None else ema_alpha * instant + (1 - ema_alpha) * ema
            )
            out.append(
                {
                    "t": float(r["bucket"]),
                    "total": cumulative,
                    "delta": n,
                    "instant": round(instant, 2),
                    "avg": round(instant, 2),
                    "ema": round(ema, 2),
                }
            )
        return out

    def count_papers(self, conference=None, year=None):
        """Count stored papers, optionally filtered by conference/year."""
        conn = self.connect()
        clauses, params = [], []
        if conference:
            clauses.append("conference = %s")
            params.append(conference)
        if year:
            clauses.append("year = %s")
            params.append(year)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS n FROM papers{where}", params)
            return cursor.fetchone()["n"]

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _normalize(record):
        """Coerce a record dict into the parameters expected by the upsert SQL."""
        authors = record.get("authors")
        if authors is not None and not isinstance(authors, str):
            authors = json.dumps(authors, ensure_ascii=False)

        scraped_at = record.get("scraped_at")
        if not scraped_at:
            scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(scraped_at, datetime):
            scraped_at = scraped_at.strftime("%Y-%m-%d %H:%M:%S")

        return {
            "paper_id": record["paper_id"],
            "conference": record["conference"],
            "year": int(record["year"]) if record.get("year") is not None else 0,
            "title": record.get("title") or "",
            "authors": authors,
            "pdf_url": record["pdf_url"],
            "local_path": record.get("local_path"),
            "source_page": record.get("source_page"),
            "scraped_at": scraped_at,
        }

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

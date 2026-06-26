#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Item pipelines for the ai_conference_paper_crawler project."""

import hashlib
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import pymysql
from scrapy.pipelines.files import FilesPipeline


class CvfFilesPipeline(FilesPipeline):
    """Download paper PDFs into ``FILES_STORE/<conference>/<year>/<filename>.pdf``.

    Downloads only happen when the item carries ``file_urls`` (the spider sets
    them only in ``--download`` mode), so by default this pipeline is a no-op.
    """

    def file_path(self, request, response=None, info=None, *, item=None):
        item = item or {}
        filename = os.path.basename(urlparse(request.url).path)
        parts = [str(item.get(key)) for key in ("conference", "year") if item.get(key)]
        parts.append(filename)
        return os.path.join(*parts)


class MySQLPipeline:
    """Upsert each ``PaperRecord`` into a MySQL ``papers`` table.

    Connection settings are read from ``MYSQL_*`` (env-driven via ``.env``).
    Runs after :class:`CvfFilesPipeline`, so ``local_path`` is populated when a
    PDF was downloaded; otherwise it is ``NULL``. ``paper_id = sha1(pdf_url)`` is
    the primary key, so re-crawling overwrites the latest snapshot (NFR-2).
    """

    CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS papers (
            paper_id    CHAR(40)     NOT NULL PRIMARY KEY,
            conference  VARCHAR(32),
            year        INT,
            title       TEXT,
            authors     JSON,
            abstract    MEDIUMTEXT,
            pdf_url     VARCHAR(768),
            local_path  VARCHAR(768),
            source_page VARCHAR(768),
            scraped_at  DATETIME,
            KEY idx_conf_year (conference, year)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """

    UPSERT = """
        INSERT INTO papers
            (paper_id, conference, year, title, authors, abstract,
             pdf_url, local_path, source_page, scraped_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            conference=VALUES(conference), year=VALUES(year),
            title=VALUES(title), authors=VALUES(authors),
            abstract=VALUES(abstract), pdf_url=VALUES(pdf_url),
            local_path=VALUES(local_path), source_page=VALUES(source_page),
            scraped_at=VALUES(scraped_at)
    """

    def __init__(self, host, port, user, password, database):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.conn = None

    @classmethod
    def from_crawler(cls, crawler):
        s = crawler.settings
        return cls(
            host=s.get("MYSQL_HOST", "127.0.0.1"),
            port=s.getint("MYSQL_PORT", 3306),
            user=s.get("MYSQL_USER", "root"),
            password=s.get("MYSQL_PASSWORD", ""),
            database=s.get("MYSQL_DATABASE", "ai_conference_paper_crawler"),
        )

    def open_spider(self, spider=None):
        # Connect without a default db so we can create it if it is missing.
        self.conn = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            charset="utf8mb4",
            autocommit=True,
        )
        with self.conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{self.database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        self.conn.select_db(self.database)
        with self.conn.cursor() as cur:
            cur.execute(self.CREATE_TABLE)
        self._ensure_columns()

    def _ensure_columns(self):
        """Add any columns missing from a table created by an older version."""
        # column name -> DDL fragment used when the column is absent.
        expected = {
            "conference": "VARCHAR(32)",
            "year": "INT",
            "title": "TEXT",
            "authors": "JSON",
            "abstract": "MEDIUMTEXT",
            "pdf_url": "VARCHAR(768)",
            "local_path": "VARCHAR(768)",
            "source_page": "VARCHAR(768)",
            "scraped_at": "DATETIME",
        }
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name='papers'",
                (self.database,),
            )
            existing = {row[0].lower() for row in cur.fetchall()}
            for name, ddl in expected.items():
                if name not in existing:
                    cur.execute(f"ALTER TABLE papers ADD COLUMN `{name}` {ddl}")

    def close_spider(self, spider=None):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def process_item(self, item, spider=None):
        pdf_url = item.get("pdf_url") or next(iter(item.get("file_urls") or []), "")
        files = item.get("files") or []
        local_path = files[0]["path"] if files else None
        scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        row = (
            hashlib.sha1(pdf_url.encode("utf-8")).hexdigest(),
            item.get("conference"),
            item.get("year"),
            item.get("title"),
            json.dumps(item.get("authors") or [], ensure_ascii=False),
            item.get("abstract") or "",
            pdf_url,
            local_path,
            item.get("source_page"),
            scraped_at,
        )
        with self.conn.cursor() as cur:
            cur.execute(self.UPSERT, row)
        return item

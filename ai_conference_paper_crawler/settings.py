#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scrapy settings for the ai_conference_paper_crawler project."""

import os

from dotenv import load_dotenv

# Load environment variables from a local .env file (git-ignored) so secrets
# such as DB credentials stay out of the source tree. override=True lets this
# project's .env win over any stale shell variables from other projects.
load_dotenv(override=True)

BOT_NAME = "ai_conference_paper_crawler"

SPIDER_MODULES = ["ai_conference_paper_crawler.spiders"]
NEWSPIDER_MODULE = "ai_conference_paper_crawler.spiders"

# Be a polite crawler.
ROBOTSTXT_OBEY = True
USER_AGENT = "ai_conference_paper_crawler (+https://github.com/AI-Huang/AI-Conference-Paper-Crawler)"
DOWNLOAD_DELAY = 0.5
AUTOTHROTTLE_ENABLED = True
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 4

# Pipelines: download PDFs (only when the item carries file_urls) then persist
# metadata to MySQL. PDFs land under FILES_STORE/<conf>/<year>/<name>.pdf.
ITEM_PIPELINES = {
    "ai_conference_paper_crawler.pipelines.CvfFilesPipeline": 1,
    "ai_conference_paper_crawler.pipelines.MySQLPipeline": 300,
}

# Code-Data separation: keep all runtime data (downloaded papers, HTTP cache)
# out of the source tree under $HOME/Data/<ProjectName>. The repo-local `data/`
# path is a symlink to this directory. Override the base with CVF_DATA_DIR.
DATA_DIR = os.environ.get(
    "CVF_DATA_DIR",
    os.path.join(os.path.expanduser("~"), "Data", "AI-Conference-Paper-Crawler"),
)

# Where downloaded papers are stored. Env-driven so runtime data can be kept
# separate from source code; defaults to <DATA_DIR>/papers.
FILES_STORE = os.environ.get("CVF_FILES_STORE", os.path.join(DATA_DIR, "papers"))

# HTTP response cache. Caches conference/day listing pages so re-runs and
# development iterate without re-hitting the source site (kinder to the server
# and much faster). Env-driven and kept out of the source tree under DATA_DIR.
# Disable with HTTPCACHE_ENABLED=0.
HTTPCACHE_ENABLED = os.environ.get("HTTPCACHE_ENABLED", "1") != "0"
HTTPCACHE_DIR = os.environ.get(
    "HTTPCACHE_DIR", os.path.join(DATA_DIR, ".scrapy", "httpcache")
)
# Cache freshness in seconds (0 = never expire). One week by default.
HTTPCACHE_EXPIRATION_SECS = int(os.environ.get("HTTPCACHE_EXPIRATION_SECS", 604800))
# The CVF site sends no cache headers, so use the Dummy policy: cache every
# response and serve it back until HTTPCACHE_EXPIRATION_SECS elapses.
HTTPCACHE_POLICY = "scrapy.extensions.httpcache.DummyPolicy"
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"
# Don't cache error responses so transient failures are retried next run.
HTTPCACHE_IGNORE_HTTP_CODES = [403, 404, 408, 429, 500, 502, 503, 504]

# MySQL connection. Credentials are env-driven (see .env); never hardcode them.
MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "ai_conference_paper_crawler")

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scrapy settings for the ai_conference_paper_crawler project."""

import os

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

# File downloading pipeline. PDFs are stored under FILES_STORE/<conf>/<name>.pdf
ITEM_PIPELINES = {
    "ai_conference_paper_crawler.pipelines.CvfFilesPipeline": 1,
}

# Where downloaded papers are stored. Env-driven so runtime data can be kept
# separate from source code; defaults to the repo-local (git-ignored) folder.
FILES_STORE = os.environ.get("CVF_FILES_STORE", "papers")

# HTTP response cache. Caches conference/day listing pages so re-runs and
# development iterate without re-hitting the source site (kinder to the server
# and much faster). Env-driven and git-ignored to keep runtime data out of the
# source tree. Disable with HTTPCACHE_ENABLED=0.
HTTPCACHE_ENABLED = os.environ.get("HTTPCACHE_ENABLED", "1") != "0"
HTTPCACHE_DIR = os.environ.get("HTTPCACHE_DIR", "httpcache")
# Cache freshness in seconds (0 = never expire). One week by default.
HTTPCACHE_EXPIRATION_SECS = int(os.environ.get("HTTPCACHE_EXPIRATION_SECS", 604800))
# The CVF site sends no cache headers, so use the Dummy policy: cache every
# response and serve it back until HTTPCACHE_EXPIRATION_SECS elapses.
HTTPCACHE_POLICY = "scrapy.extensions.httpcache.DummyPolicy"
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"
# Don't cache error responses so transient failures are retried next run.
HTTPCACHE_IGNORE_HTTP_CODES = [403, 404, 408, 429, 500, 502, 503, 504]

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

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

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scrapy item definitions for the ai_conference_paper_crawler project."""

import scrapy


class PaperItem(scrapy.Item):
    """A single conference paper PDF to download plus its metadata."""

    conference = scrapy.Field()  # conference key, e.g. "CVPR"
    year = scrapy.Field()  # conference year, e.g. 2017
    title = scrapy.Field()  # paper title (best-effort)
    authors = scrapy.Field()  # list of author names (best-effort)
    abstract = scrapy.Field()  # paper abstract (best-effort, may be empty)
    source_page = scrapy.Field()  # listing page the paper was found on
    pdf_url = scrapy.Field()  # resolved absolute PDF URL (always set)
    file_urls = scrapy.Field()  # consumed by the files pipeline (download mode only)
    files = scrapy.Field()  # populated by the files pipeline

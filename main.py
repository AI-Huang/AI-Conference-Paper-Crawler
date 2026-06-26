#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Date    : Dec-20-20 20:28
# @Author  : Kan Huang (kan.huang@connect.ust.hk)

"""Convenience runner for the ai_conference_paper_crawler Scrapy project.

This keeps ``python main.py`` working. For full control prefer the Scrapy CLI::

    scrapy crawl cvf                            # discover & crawl every conference
    scrapy crawl cvf -a conf=CVPR -a year=2026  # crawl a single edition
"""

import argparse

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from ai_conference_paper_crawler.spiders.cvf import CvfSpider


def main():
    parser = argparse.ArgumentParser(description="Download CVF conference papers.")
    parser.add_argument(
        "--conf", default=None, help="Conference key, e.g. CVPR (omit to discover all)"
    )
    parser.add_argument(
        "--year", default=None, help="Conference year, e.g. 2026 (omit to discover all)"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Also download paper PDFs (default: metadata only, no download)",
    )
    args = parser.parse_args()

    process = CrawlerProcess(get_project_settings())
    process.crawl(CvfSpider, conf=args.conf, year=args.year, download=args.download)
    process.start()


if __name__ == "__main__":
    main()

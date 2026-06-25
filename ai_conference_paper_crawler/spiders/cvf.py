#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Spider for the CVF open-access site (openaccess.thecvf.com).

One spider per website (site family). It discovers what to crawl by parsing the
live site rather than relying on a hardcoded list of conferences/years:

* the site menu (``/`` redirects to ``/menu``) lists every conference page;
* a conference page (e.g. ``/CVPR2026``) lists its ``?day=`` sub-pages or the
  paper ``pdf`` links directly.

Run with::

    scrapy crawl cvf                          # discover & crawl every conference
    scrapy crawl cvf -a conf=CVPR -a year=2026  # crawl a single edition directly
    scrapy crawl cvf -a year=2019               # every conference held in 2019
"""

import re

import scrapy

from ai_conference_paper_crawler.items import PaperItem
from ai_conference_paper_crawler.utils.links import resolve_pdf_url

BASE_URL = "https://openaccess.thecvf.com/"

# A main conference page link, e.g. "CVPR2026" or "/ICCV2019.py". Workshop /
# demo / findings links contain an underscore and are intentionally excluded.
_CONF_LINK_RE = re.compile(r"^/?([A-Za-z]+)(\d{4})(?:\.py)?$")
# Extract (conference, year) from any conference URL.
_CONF_FROM_URL_RE = re.compile(r"/([A-Za-z]+)(\d{4})(?:\.py)?(?:[/?#]|$)")


class CvfSpider(scrapy.Spider):
    """Crawl CVF conference pages, discovering conferences and days dynamically."""

    name = "cvf"
    allowed_domains = ["openaccess.thecvf.com"]

    def __init__(self, conf=None, year=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conf = conf.upper() if conf else None
        self.year = str(year) if year else None

    async def start(self):
        for request in self.start_requests():
            yield request

    def start_requests(self):
        # Direct mode: jump straight to the requested conference page.
        if self.conf and self.year:
            yield scrapy.Request(
                f"{BASE_URL}{self.conf}{self.year}", callback=self.parse_conference
            )
        # Discovery mode: parse the site menu and crawl matching conferences.
        else:
            yield scrapy.Request(BASE_URL, callback=self.parse_menu)

    def parse_menu(self, response):
        """Parse the conference list and follow each matching conference page."""
        for href in response.xpath("//a/@href").getall():
            match = _CONF_LINK_RE.match(href.strip())
            if not match:
                continue
            conf, year = match.group(1).upper(), match.group(2)
            if self.conf and conf != self.conf:
                continue
            if self.year and year != self.year:
                continue
            yield response.follow(href, callback=self.parse_conference)

    def parse_conference(self, response):
        """Yield paper items, following ``?day=`` sub-pages when present."""
        conf, year = self._conf_year_from_url(response.url)

        pdf_links = response.xpath('//a[normalize-space(text())="pdf"]')
        for link in pdf_links:
            href = link.xpath("@href").get()
            if not href:
                continue
            title = link.xpath("ancestor::dd/preceding-sibling::dt[1]//a/text()").get()
            yield PaperItem(
                conference=conf,
                year=int(year) if year else None,
                title=(title or "").strip(),
                source_page=response.url,
                file_urls=[resolve_pdf_url(href)],
            )

        # Multi-day conferences list day sub-pages instead of papers. Prefer the
        # aggregated "?day=all" page when offered; otherwise crawl each day.
        if not pdf_links:
            day_hrefs = response.xpath('//a[contains(@href, "?day=")]/@href').getall()
            all_day = [href for href in day_hrefs if href.endswith("day=all")]
            for href in all_day or day_hrefs:
                yield response.follow(href, callback=self.parse_conference)

    @staticmethod
    def _conf_year_from_url(url):
        """Best-effort extraction of (conference, year) from a conference URL."""
        match = _CONF_FROM_URL_RE.search(url)
        if not match:
            return "", ""
        return match.group(1).upper(), match.group(2)

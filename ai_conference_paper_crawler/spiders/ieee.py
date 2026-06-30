#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Spider for IEEE Xplore conferences via the IEEE Developer API.

Uses the official IEEE Xplore Developer API (ieeexploreapi.ieee.org).
An API key is required — register for free at https://developer.ieee.org/.
Set the key via the ``IEEE_API_KEY`` environment variable (or in ``.env``).

Run with::

    scrapy crawl ieee -a conf=IROS -a year=2023
    scrapy crawl ieee -a conf=IROS                 # all supported IROS years
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

import scrapy

from ai_conference_paper_crawler.items import PaperItem
from ai_conference_paper_crawler.registry import (
    Family,
    RegistryError,
    conferences_by_family,
    get_conference,
    list_url,
)

_API_BASE = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
# IEEE API maximum records per request.
_PAGE_SIZE = 200
# Extract the publication number from an IEEE Xplore proceedings URL.
_PUB_RE = re.compile(r"/xpl/conhome/(\d+)/proceeding")


def _pub_number_from_url(url: str) -> str:
    """Return the numeric publication-number string from an IEEE Xplore URL."""
    m = _PUB_RE.search(url)
    if not m:
        raise ValueError(f"Cannot extract publication number from {url!r}")
    return m.group(1)


class IeeeSpider(scrapy.Spider):
    """Crawl IEEE Xplore conference proceedings via the IEEE Developer API.

    Metadata (title, authors, abstract, PDF URL) is stored for every paper.
    PDFs are downloaded only in ``--download`` mode and require institutional
    access to IEEE Xplore; the downloaded file will be the full-text PDF only
    if your network has a subscription.
    """

    name = "ieee"
    allowed_domains = ["ieeexploreapi.ieee.org"]

    def __init__(self, conf=None, year=None, download=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conf = conf.upper() if conf else None
        self.year = int(year) if year else None
        self.download = str(download).lower() in ("1", "true", "yes", "on")
        self._api_key = ""

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider._api_key = crawler.settings.get("IEEE_API_KEY", "")
        if not spider._api_key:
            spider.logger.warning(
                "IEEE_API_KEY is not configured. "
                "Register for a free key at https://developer.ieee.org/ "
                "and set it via the IEEE_API_KEY environment variable."
            )
        return spider

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    async def start(self):
        for request in self.start_requests():
            yield request

    def start_requests(self):
        if self.conf:
            try:
                conf_obj = get_conference(self.conf)
            except RegistryError as exc:
                self.logger.error(str(exc))
                return
            if conf_obj.family != Family.IEEE:
                self.logger.error(
                    "%s belongs to the %r family, not IEEE. "
                    "Use the appropriate spider instead.",
                    self.conf,
                    conf_obj.family,
                )
                return
            years = [self.year] if self.year else sorted(conf_obj.years)
            for yr in years:
                yield self._page_request(self.conf, yr, page=1)
        else:
            # Crawl all registered IEEE conferences.
            for key in conferences_by_family(Family.IEEE):
                conf_obj = get_conference(key)
                for yr in sorted(conf_obj.years):
                    yield self._page_request(key, yr, page=1)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _page_request(self, conf_key: str, year: int, page: int) -> scrapy.Request:
        """Build a paginated request to the IEEE Developer API."""
        proceedings_url = list_url(conf_key, year)
        pub_num = _pub_number_from_url(proceedings_url)
        start_record = (page - 1) * _PAGE_SIZE + 1
        qs = urlencode(
            {
                "apikey": self._api_key,
                "publication_number": pub_num,
                "max_records": _PAGE_SIZE,
                "start_record": start_record,
            }
        )
        return scrapy.Request(
            f"{_API_BASE}?{qs}",
            callback=self.parse_articles,
            cb_kwargs={
                "conf_key": conf_key,
                "year": year,
                "pub_num": pub_num,
                "page": page,
            },
            headers={"Accept": "application/json"},
        )

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_articles(self, response, conf_key, year, pub_num, page):
        """Parse one page of the IEEE API response, yield items and follow pages."""
        data = response.json()
        total = data.get("total_records", 0)
        articles = data.get("articles") or []

        source_page = f"https://ieeexplore.ieee.org/xpl/conhome/{pub_num}/proceeding"

        for article in articles:
            authors = [
                a.get("full_name", "").strip()
                for a in (article.get("authors") or {}).get("authors") or []
                if a.get("full_name")
            ]
            pdf_url = (article.get("pdf_url") or article.get("html_url") or "").strip()
            item = PaperItem(
                conference=conf_key,
                year=year,
                title=(article.get("title") or "").strip(),
                authors=authors,
                abstract=(article.get("abstract") or "").strip(),
                source_page=source_page,
                pdf_url=pdf_url,
                file_urls=[pdf_url] if self.download and pdf_url else [],
            )
            yield item

        # Follow subsequent pages until all records are fetched.
        fetched_so_far = (page - 1) * _PAGE_SIZE + len(articles)
        if fetched_so_far < total:
            yield self._page_request(conf_key, year, page + 1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the CVF spider (FR-2 / US-002).

The spider discovers conferences and days by parsing live pages, so these tests
feed it representative HTML rather than asserting on any hardcoded list.
"""

import scrapy
from scrapy.http import HtmlResponse, Request

from ai_conference_paper_crawler.items import PaperItem
from ai_conference_paper_crawler.spiders.cvf import CvfSpider


def _response(url, body):
    return HtmlResponse(
        url=url, body=body.encode("utf-8"), encoding="utf-8", request=Request(url=url)
    )


MENU_HTML = """
<div>
  <a href="CVPR2026">CVPR 2026</a>
  <a href="CVPR2026_workshops">CVPR 2026 Workshops</a>
  <a href="CVPR2026_findings">CVPR 2026 Findings</a>
  <a href="ICCV2025">ICCV 2025</a>
  <a href="WACV2026">WACV 2026</a>
  <a href="CVPR2018.py">CVPR 2018</a>
  <a href="./menu_other.html">Other</a>
  <a href="https://www.thecvf.com/">CVF</a>
</div>
"""

PAPER_HTML = """
<dl>
  <dt class="ptitle"><a href="/content_cvpr_2017/html/Ex.html">Example Paper</a></dt>
  <dd>
    [<a href="/content_cvpr_2017/papers/Ex_CVPR_2017_paper.pdf">pdf</a>]
  </dd>
</dl>
"""

# A listing entry whose title is not a link to a detail page: the spider must
# fall back to yielding the item straight from the listing row.
PAPER_NO_DETAIL_HTML = """
<dl>
  <dt class="ptitle"><a>Example Paper</a></dt>
  <dd>
    <form class="authsearch"><a href="#">Listing Author</a></form>
    [<a href="/content_cvpr_2017/papers/Ex_CVPR_2017_paper.pdf">pdf</a>]
  </dd>
</dl>
"""

# A paper detail page: the byline (full author list) lives in #authors//i and
# the abstract in #abstract.
DETAIL_HTML = """
<div id="authors">
  <b>Authors:</b> <i>Alice Author, Bob Builder</i>
</div>
<div id="abstract">
  This is the abstract text.
</div>
"""

DAY_INDEX_HTML = """
<div>
  <a href="/CVPR2018.py?day=2018-06-19">Day 1</a>
  <a href="/CVPR2018.py?day=2018-06-20">Day 2</a>
</div>
"""

DAY_ALL_HTML = """
<div>
  <a href="/CVPR2026?day=2026-06-05">Day 1</a>
  <a href="/CVPR2026?day=2026-06-06">Day 2</a>
  <a href="/CVPR2026?day=all">All Days</a>
</div>
"""


def test_direct_mode_requests_conference_page():
    spider = CvfSpider(conf="cvpr", year=2026)
    requests = list(spider.start_requests())
    assert len(requests) == 1
    assert requests[0].url == "https://openaccess.thecvf.com/CVPR2026"
    assert requests[0].callback == spider.parse_conference


def test_discovery_mode_starts_at_site_root():
    spider = CvfSpider()
    requests = list(spider.start_requests())
    assert len(requests) == 1
    assert requests[0].url == "https://openaccess.thecvf.com/"
    assert requests[0].callback == spider.parse_menu


def test_parse_menu_follows_only_main_conference_links():
    spider = CvfSpider()
    response = _response("https://openaccess.thecvf.com/menu", MENU_HTML)
    followed = {r.url for r in spider.parse_menu(response)}
    assert followed == {
        "https://openaccess.thecvf.com/CVPR2026",
        "https://openaccess.thecvf.com/ICCV2025",
        "https://openaccess.thecvf.com/WACV2026",
        "https://openaccess.thecvf.com/CVPR2018.py",
    }


def test_parse_menu_filters_by_conf_and_year():
    spider = CvfSpider(conf="CVPR")
    response = _response("https://openaccess.thecvf.com/menu", MENU_HTML)
    followed = {r.url for r in spider.parse_menu(response)}
    assert followed == {
        "https://openaccess.thecvf.com/CVPR2026",
        "https://openaccess.thecvf.com/CVPR2018.py",
    }

    spider_year = CvfSpider(year=2026)
    followed_year = {r.url for r in spider_year.parse_menu(response)}
    assert followed_year == {
        "https://openaccess.thecvf.com/CVPR2026",
        "https://openaccess.thecvf.com/WACV2026",
    }


def test_parse_conference_follows_detail_page():
    spider = CvfSpider()
    url = "https://openaccess.thecvf.com/CVPR2017.py"
    results = list(spider.parse_conference(_response(url, PAPER_HTML)))

    # Stage 1: the listing row schedules a follow-up to the paper detail page,
    # carrying the partially-built item via cb_kwargs.
    assert len(results) == 1
    request = results[0]
    assert isinstance(request, scrapy.Request)
    assert request.url == (
        "https://openaccess.thecvf.com/content_cvpr_2017/html/Ex.html"
    )
    assert request.callback == spider.parse_paper

    item = request.cb_kwargs["item"]
    assert isinstance(item, PaperItem)
    assert item["conference"] == "CVPR"
    assert item["year"] == 2017
    assert item["title"] == "Example Paper"
    assert item["source_page"] == url
    assert item["abstract"] == ""
    assert item["pdf_url"] == (
        "https://openaccess.thecvf.com/content_cvpr_2017/papers/Ex_CVPR_2017_paper.pdf"
    )
    # Download is opt-in, so the files pipeline is not triggered by default.
    assert item["file_urls"] == []


def test_parse_paper_enriches_with_authors_and_abstract():
    spider = CvfSpider()
    detail_url = "https://openaccess.thecvf.com/content_cvpr_2017/html/Ex.html"
    partial = PaperItem(
        conference="CVPR",
        year=2017,
        title="Example Paper",
        authors=["Listing Author"],
        abstract="",
        source_page="https://openaccess.thecvf.com/CVPR2017.py",
        pdf_url="https://openaccess.thecvf.com/content_cvpr_2017/papers/Ex.pdf",
        file_urls=[],
    )

    # Stage 2: the detail page supplies the full byline and the abstract.
    items = list(spider.parse_paper(_response(detail_url, DETAIL_HTML), item=partial))
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, PaperItem)
    assert item["authors"] == ["Alice Author", "Bob Builder"]
    assert item["abstract"] == "This is the abstract text."


def test_parse_conference_yields_item_without_detail_link():
    spider = CvfSpider()
    url = "https://openaccess.thecvf.com/CVPR2017.py"
    items = list(spider.parse_conference(_response(url, PAPER_NO_DETAIL_HTML)))

    # No detail link: the item is emitted directly, using the listing-page
    # authors as a fallback.
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, PaperItem)
    assert item["title"] == "Example Paper"
    assert item["authors"] == ["Listing Author"]
    assert item["source_page"] == url


def test_parse_conference_follows_each_day_when_no_all():
    spider = CvfSpider()
    url = "https://openaccess.thecvf.com/CVPR2018.py"
    results = list(spider.parse_conference(_response(url, DAY_INDEX_HTML)))

    assert results and all(isinstance(r, scrapy.Request) for r in results)
    followed = {r.url for r in results}
    assert followed == {
        "https://openaccess.thecvf.com/CVPR2018.py?day=2018-06-19",
        "https://openaccess.thecvf.com/CVPR2018.py?day=2018-06-20",
    }


def test_parse_conference_splits_day_all_into_per_day_pages():
    spider = CvfSpider()
    url = "https://openaccess.thecvf.com/CVPR2026"
    results = list(spider.parse_conference(_response(url, DAY_ALL_HTML)))

    followed = {r.url for r in results}
    # The aggregated "?day=all" page is skipped in favour of smaller, more
    # reliable per-day sub-pages.
    assert followed == {
        "https://openaccess.thecvf.com/CVPR2026?day=2026-06-05",
        "https://openaccess.thecvf.com/CVPR2026?day=2026-06-06",
    }


def test_parse_conference_scopes_to_requested_day():
    spider = CvfSpider(day="2026-06-06")
    url = "https://openaccess.thecvf.com/CVPR2026"
    results = list(spider.parse_conference(_response(url, DAY_ALL_HTML)))

    followed = [r.url for r in results]
    assert followed == ["https://openaccess.thecvf.com/CVPR2026?day=2026-06-06"]


def test_direct_mode_with_day_requests_day_page():
    spider = CvfSpider(conf="cvpr", year=2026, day="2026-06-05")
    requests = list(spider.start_requests())
    assert len(requests) == 1
    assert requests[0].url == "https://openaccess.thecvf.com/CVPR2026?day=2026-06-05"
    assert requests[0].callback == spider.parse_conference

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the IEEE spider (IeeeSpider)."""

import json

import scrapy
import pytest
from scrapy.http import Request, TextResponse

from ai_conference_paper_crawler.items import PaperItem
from ai_conference_paper_crawler.spiders.ieee import IeeeSpider, _pub_number_from_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_response(url, data):
    body = json.dumps(data).encode("utf-8")
    return TextResponse(
        url=url, body=body, encoding="utf-8", request=Request(url=url)
    )


def _make_spider(conf=None, year=None, download=None, api_key="TESTKEY"):
    spider = IeeeSpider(conf=conf, year=year, download=download)
    spider._api_key = api_key
    spider._logger = spider.logger
    return spider


ARTICLE_1 = {
    "title": "Robot Navigation in Dynamic Environments",
    "abstract": "We propose a novel method for robot navigation.",
    "authors": {
        "authors": [
            {"full_name": "Alice Author", "author_order": 1},
            {"full_name": "Bob Builder", "author_order": 2},
        ]
    },
    "pdf_url": "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=10001111",
    "html_url": "https://ieeexplore.ieee.org/document/10001111",
    "article_number": "10001111",
    "publication_year": "2023",
}

ARTICLE_2 = {
    "title": "Sensor Fusion for Autonomous Driving",
    "abstract": "A sensor fusion pipeline for self-driving cars.",
    "authors": {
        "authors": [
            {"full_name": "Carol Chen", "author_order": 1},
        ]
    },
    "pdf_url": "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=10001222",
    "html_url": "https://ieeexplore.ieee.org/document/10001222",
    "article_number": "10001222",
    "publication_year": "2023",
}


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def test_pub_number_from_proceedings_url():
    url = "https://ieeexplore.ieee.org/xpl/conhome/10341341/proceeding"
    assert _pub_number_from_url(url) == "10341341"


def test_pub_number_raises_for_non_ieee_url():
    with pytest.raises(ValueError):
        _pub_number_from_url("https://openaccess.thecvf.com/CVPR2023")


# ---------------------------------------------------------------------------
# start_requests
# ---------------------------------------------------------------------------


def test_direct_mode_single_year_emits_one_request():
    spider = _make_spider(conf="IROS", year=2023)
    requests = list(spider.start_requests())
    assert len(requests) == 1
    req = requests[0]
    assert isinstance(req, scrapy.Request)
    assert "publication_number=10341341" in req.url
    assert "start_record=1" in req.url
    assert "max_records=200" in req.url
    assert "apikey=TESTKEY" in req.url


def test_direct_mode_no_year_emits_request_per_registered_year():
    spider = _make_spider(conf="IROS")
    requests = list(spider.start_requests())
    # IROS has 13 registered years (2013-2025)
    assert len(requests) == 13
    urls = [r.url for r in requests]
    assert any("10341341" in u for u in urls)  # 2023
    assert any("10801613" in u for u in urls)  # 2024
    assert any("11245651" in u for u in urls)  # 2025


def test_no_conf_crawls_all_ieee_conferences():
    spider = _make_spider()
    requests = list(spider.start_requests())
    # At least one request (IROS 2013)
    assert len(requests) >= 1
    assert all(isinstance(r, scrapy.Request) for r in requests)


# ---------------------------------------------------------------------------
# parse_articles — single page (no pagination needed)
# ---------------------------------------------------------------------------


def test_parse_articles_yields_items():
    spider = _make_spider(conf="IROS", year=2023)
    api_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles?apikey=TESTKEY&publication_number=10341341&max_records=200&start_record=1"
    response = _json_response(
        api_url,
        {"total_records": 2, "articles": [ARTICLE_1, ARTICLE_2]},
    )
    results = list(
        spider.parse_articles(
            response,
            conf_key="IROS",
            year=2023,
            pub_num="10341341",
            page=1,
        )
    )

    assert len(results) == 2
    item = results[0]
    assert isinstance(item, PaperItem)
    assert item["conference"] == "IROS"
    assert item["year"] == 2023
    assert item["title"] == "Robot Navigation in Dynamic Environments"
    assert item["authors"] == ["Alice Author", "Bob Builder"]
    assert "novel method" in item["abstract"]
    assert "ieeexplore.ieee.org" in item["pdf_url"]
    assert item["file_urls"] == []  # download mode is off


def test_parse_articles_download_mode_sets_file_urls():
    spider = _make_spider(conf="IROS", year=2023, download="true")
    api_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles?anything"
    response = _json_response(
        api_url,
        {"total_records": 1, "articles": [ARTICLE_1]},
    )
    results = list(
        spider.parse_articles(
            response, conf_key="IROS", year=2023, pub_num="10341341", page=1
        )
    )
    assert len(results) == 1
    item = results[0]
    assert item["file_urls"] == [item["pdf_url"]]


# ---------------------------------------------------------------------------
# parse_articles — pagination
# ---------------------------------------------------------------------------


def test_parse_articles_follows_next_page_when_more_records_remain():
    spider = _make_spider(conf="IROS", year=2023)
    api_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles?anything"
    # Page 1 returns 1 of 2 total records — a second page request should follow.
    response = _json_response(
        api_url,
        {"total_records": 2, "articles": [ARTICLE_1]},
    )
    results = list(
        spider.parse_articles(
            response, conf_key="IROS", year=2023, pub_num="10341341", page=1
        )
    )
    # One item + one follow-up Request
    items = [r for r in results if isinstance(r, PaperItem)]
    requests = [r for r in results if isinstance(r, scrapy.Request)]
    assert len(items) == 1
    assert len(requests) == 1
    assert "start_record=2" in requests[0].url  # page 2 starts at record 2


def test_parse_articles_no_extra_request_when_all_fetched():
    spider = _make_spider(conf="IROS", year=2023)
    api_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles?anything"
    response = _json_response(
        api_url,
        {"total_records": 2, "articles": [ARTICLE_1, ARTICLE_2]},
    )
    results = list(
        spider.parse_articles(
            response, conf_key="IROS", year=2023, pub_num="10341341", page=1
        )
    )
    requests = [r for r in results if isinstance(r, scrapy.Request)]
    assert len(requests) == 0  # both records returned on page 1, no next page


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_parse_articles_handles_empty_response():
    spider = _make_spider(conf="IROS", year=2023)
    api_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles?anything"
    response = _json_response(api_url, {"total_records": 0, "articles": []})
    results = list(
        spider.parse_articles(
            response, conf_key="IROS", year=2023, pub_num="10341341", page=1
        )
    )
    assert results == []


def test_parse_articles_handles_missing_pdf_url():
    article = {
        "title": "No PDF Paper",
        "abstract": "Abstract here.",
        "authors": {"authors": [{"full_name": "Dave Doe", "author_order": 1}]},
        "pdf_url": "",
        "html_url": "https://ieeexplore.ieee.org/document/9999999",
    }
    spider = _make_spider(conf="IROS", year=2023)
    api_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles?anything"
    response = _json_response(api_url, {"total_records": 1, "articles": [article]})
    results = list(
        spider.parse_articles(
            response, conf_key="IROS", year=2023, pub_num="10341341", page=1
        )
    )
    assert len(results) == 1
    # Falls back to html_url when pdf_url is empty
    assert results[0]["pdf_url"] == "https://ieeexplore.ieee.org/document/9999999"


def test_parse_articles_source_page_is_ieee_proceedings():
    spider = _make_spider(conf="IROS", year=2023)
    api_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles?anything"
    response = _json_response(api_url, {"total_records": 1, "articles": [ARTICLE_1]})
    results = list(
        spider.parse_articles(
            response, conf_key="IROS", year=2023, pub_num="10341341", page=1
        )
    )
    assert results[0]["source_page"] == (
        "https://ieeexplore.ieee.org/xpl/conhome/10341341/proceeding"
    )

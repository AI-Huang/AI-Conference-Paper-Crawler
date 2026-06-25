#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Date    : Dec-20-20 20:28
# @Author  : Kan Huang (kan.huang@connect.ust.hk)

"""Link/URL helpers for the crawler.

Conference start URLs now live in the conference registry
(``ai_conference_paper_crawler.registry``); this module keeps the small,
spider-agnostic helpers for resolving and naming downloaded files.
"""

import os
from urllib.parse import urljoin, urlparse

HOST_ROOT = "https://openaccess.thecvf.com/"


def resolve_pdf_url(pdf_href, host_root=HOST_ROOT):
    """Resolve a (possibly relative) pdf href against the host root."""
    return urljoin(host_root, pdf_href)


def filename_from_url(url):
    """Derive a download filename from a URL path."""
    return os.path.basename(urlparse(url).path)

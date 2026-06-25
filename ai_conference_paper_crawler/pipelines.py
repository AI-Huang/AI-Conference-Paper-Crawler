#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Item pipelines for the ai_conference_paper_crawler project."""

import os
from urllib.parse import urlparse

from scrapy.pipelines.files import FilesPipeline


class CvfFilesPipeline(FilesPipeline):
    """Download paper PDFs into ``FILES_STORE/<conference>/<year>/<filename>.pdf``."""

    def file_path(self, request, response=None, info=None, *, item=None):
        item = item or {}
        filename = os.path.basename(urlparse(request.url).path)
        parts = [str(item.get(key)) for key in ("conference", "year") if item.get(key)]
        parts.append(filename)
        return os.path.join(*parts)

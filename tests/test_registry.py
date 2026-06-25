#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the conference registry (FR-1 / US-001)."""

import pytest

from ai_conference_paper_crawler.registry import (
    CONFERENCE_REGISTRY,
    Family,
    UnknownConferenceError,
    UnsupportedYearError,
    available_conferences,
    conferences_by_family,
    get_conference,
    is_supported,
    list_url,
)


def test_lookup_is_case_insensitive():
    assert get_conference("cvpr") is get_conference("CVPR")
    assert get_conference("CvPr").key == "CVPR"


def test_unknown_conference_raises_with_supported_list():
    with pytest.raises(UnknownConferenceError) as exc:
        get_conference("NOPE")
    assert "CVPR" in str(exc.value)


def test_cvf_list_url_follows_template():
    assert list_url("CVPR", 2017) == "https://openaccess.thecvf.com/CVPR2017"
    assert list_url("ICCV", 2019) == "https://openaccess.thecvf.com/ICCV2019"


def test_neurips_list_url_follows_template():
    assert (
        list_url("NeurIPS", 2023)
        == "https://proceedings.neurips.cc/paper_files/paper/2023"
    )


def test_pmlr_uses_year_override():
    assert list_url("ICML", 2023) == "https://proceedings.mlr.press/v202/"


def test_unsupported_year_raises():
    with pytest.raises(UnsupportedYearError):
        list_url("CVPR", 1990)
    with pytest.raises(UnsupportedYearError):
        list_url("ICCV", 2018)  # ICCV is biennial (odd years)


def test_is_supported():
    assert is_supported("CVPR", 2017) is True
    assert is_supported("CVPR", 1990) is False
    assert is_supported("NOPE", 2017) is False


def test_year_accepts_string():
    assert is_supported("CVPR", "2017") is True
    assert list_url("CVPR", "2017") == "https://openaccess.thecvf.com/CVPR2017"


def test_available_conferences_sorted_and_unique():
    confs = available_conferences()
    assert confs == sorted(confs)
    assert len(confs) == len(set(confs))
    assert {"CVPR", "ICCV", "ECCV", "WACV", "NEURIPS", "ICML"} <= set(confs)


def test_conferences_by_family():
    assert set(conferences_by_family(Family.CVF)) == {"CVPR", "ICCV", "ECCV", "WACV"}
    assert conferences_by_family(Family.NEURIPS) == ["NEURIPS"]
    assert conferences_by_family(Family.PMLR) == ["ICML"]


def test_every_registered_year_resolves_to_a_url():
    for conf in CONFERENCE_REGISTRY.values():
        for year in conf.years:
            assert conf.list_url(year).startswith("https://")

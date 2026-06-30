#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conference registry — single source of truth for supported conferences.

FR-1 of the multi-conference crawler (REQ-001 / US-001). Each conference key is
mapped to its site *family*, the set of supported *years*, and the *rule* used to
build the paper-listing URL. CLI argument validation, spider routing, and URL
construction all read from this registry, so adding a new conference is a single
registry edit (NFR-5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Tuple


class Family:
    """Site families that group conferences sharing the same crawling logic."""

    CVF = "cvf"  # openaccess.thecvf.com
    NEURIPS = "neurips"  # proceedings.neurips.cc
    PMLR = "pmlr"  # proceedings.mlr.press
    IEEE = "ieee"  # ieeexplore.ieee.org (via ieeexploreapi.ieee.org Developer API)


class RegistryError(ValueError):
    """Base class for registry lookup failures (CLI maps these to clear errors)."""


class UnknownConferenceError(RegistryError):
    """Raised when a conference key is not present in the registry."""


class UnsupportedYearError(RegistryError):
    """Raised when a conference does not support the requested year."""


@dataclass(frozen=True)
class Conference:
    """Describes how a single conference is located and crawled.

    # Attributes:
        key: conference identifier, e.g. ``"CVPR"`` (compared case-insensitively).
        family: site family the conference belongs to (see ``Family``).
        years: supported years, used for CLI validation.
        url_template: ``str.format`` template accepting ``key``/``key_lower``/``year``
            to build the listing URL. Optional when every year is covered by
            ``url_overrides``.
        url_overrides: per-year explicit URLs that take precedence over the
            template (e.g. PMLR volume pages that do not follow a simple rule).
    """

    key: str
    family: str
    years: Tuple[int, ...]
    url_template: str = ""
    url_overrides: Mapping[int, str] = field(default_factory=dict)

    def supports(self, year) -> bool:
        """Return ``True`` if ``year`` is a supported edition of this conference."""
        return int(year) in self.years

    def list_url(self, year) -> str:
        """Build the paper-listing URL for ``year``.

        Raises ``UnsupportedYearError`` if the year is not supported or no URL
        rule resolves it.
        """
        year = int(year)
        if not self.supports(year):
            raise UnsupportedYearError(
                f"{self.key} does not support year {year}; "
                f"supported years: {sorted(self.years)}"
            )
        if year in self.url_overrides:
            return self.url_overrides[year]
        if not self.url_template:
            raise UnsupportedYearError(f"No URL rule for {self.key} {year}")
        return self.url_template.format(
            key=self.key, key_lower=self.key.lower(), year=year
        )


_CVF_TEMPLATE = "https://openaccess.thecvf.com/{key}{year}"
_NEURIPS_TEMPLATE = "https://proceedings.neurips.cc/paper_files/paper/{year}"

# IEEE Xplore proceedings URL template; the spider extracts the publication
# number from the path to call the IEEE Developer API.
_IEEE_PROCEEDINGS = "https://ieeexplore.ieee.org/xpl/conhome/{pub_num}/proceeding"


def _iros(year: int, pub_num: int) -> str:
    return _IEEE_PROCEEDINGS.format(pub_num=pub_num)


# Registered conferences. Years reflect the editions published by each site
# family; extend a tuple (or add a Conference) to support more editions.
_CONFERENCES: Tuple[Conference, ...] = (
    # CVF family — openaccess.thecvf.com/<KEY><YEAR>
    Conference("CVPR", Family.CVF, tuple(range(2013, 2025)), _CVF_TEMPLATE),
    Conference("ICCV", Family.CVF, (2013, 2015, 2017, 2019, 2021, 2023), _CVF_TEMPLATE),
    Conference("ECCV", Family.CVF, (2018, 2020, 2022, 2024), _CVF_TEMPLATE),
    Conference("WACV", Family.CVF, tuple(range(2020, 2025)), _CVF_TEMPLATE),
    # NeurIPS — proceedings.neurips.cc/paper_files/paper/<YEAR>
    Conference("NeurIPS", Family.NEURIPS, tuple(range(2010, 2024)), _NEURIPS_TEMPLATE),
    # PMLR — proceedings.mlr.press volume pages (no simple year rule).
    Conference(
        "ICML",
        Family.PMLR,
        (2020, 2021, 2022, 2023),
        url_overrides={
            2020: "https://proceedings.mlr.press/v119/",
            2021: "https://proceedings.mlr.press/v139/",
            2022: "https://proceedings.mlr.press/v162/",
            2023: "https://proceedings.mlr.press/v202/",
        },
    ),
    # IEEE family — ieeexplore.ieee.org (crawled via IEEE Developer API).
    # Publication numbers map each IROS year to its IEEE Xplore proceeding.
    # Verify or extend at: https://ieeexplore.ieee.org/browse/conferences/title
    Conference(
        "IROS",
        Family.IEEE,
        (2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023),
        url_overrides={
            2013: _iros(2013, 6696430),
            2014: _iros(2014, 6942228),
            2015: _iros(2015, 7353456),
            2016: _iros(2016, 7759096),
            2017: _iros(2017, 8202183),
            2018: _iros(2018, 8593375),
            2019: _iros(2019, 8959283),
            2020: _iros(2020, 9340924),
            2021: _iros(2021, 9635848),
            2022: _iros(2022, 9981000),
            2023: _iros(2023, 10341341),
        },
    ),
)

#: Canonical registry keyed by upper-cased conference key.
CONFERENCE_REGISTRY: Dict[str, Conference] = {c.key.upper(): c for c in _CONFERENCES}


def get_conference(key) -> Conference:
    """Look up a conference by key (case-insensitive).

    Raises ``UnknownConferenceError`` listing the supported keys when missing.
    """
    try:
        return CONFERENCE_REGISTRY[str(key).upper()]
    except KeyError:
        raise UnknownConferenceError(
            f"Unknown conference {key!r}; supported: {available_conferences()}"
        ) from None


def available_conferences() -> List[str]:
    """Return all registered conference keys, sorted."""
    return sorted(CONFERENCE_REGISTRY)


def conferences_by_family(family: str) -> List[str]:
    """Return the registered conference keys belonging to ``family``, sorted."""
    return sorted(
        key for key, conf in CONFERENCE_REGISTRY.items() if conf.family == family
    )


def is_supported(key, year) -> bool:
    """Return ``True`` if ``key`` is registered and supports ``year``."""
    try:
        return get_conference(key).supports(year)
    except RegistryError:
        return False


def list_url(key, year) -> str:
    """Resolve the listing URL for ``key``/``year`` via the registry.

    Raises ``UnknownConferenceError`` or ``UnsupportedYearError`` for invalid
    combinations so callers (CLI/spiders) can surface a clear message.
    """
    return get_conference(key).list_url(year)

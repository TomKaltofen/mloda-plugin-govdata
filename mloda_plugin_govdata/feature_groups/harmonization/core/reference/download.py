"""Fetch-and-verify seam shared by the reference-table loaders.

Runtime fetch, not packaged: every loader reads through the existing
``DownloadCache`` (offline-first via ``revalidate=False``) and verifies the
downloaded body against the original file's pinned sha256 before caching it,
catching upstream content drift that a mere HTTP 200 would not.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import openpyxl

from mloda_plugin_govdata.feature_groups.govdata.core.cache import DownloadCache, PinMismatchError

from .sources import ReferenceSource


class SourceIntegrityError(PinMismatchError):
    """Raised when a fetched reference file's sha256 does not match its pinned value."""


def fetch_pinned(cache: DownloadCache, source: ReferenceSource, *, revalidate: bool = False) -> Path:
    """The pinned file's path; a cached body with another hash reads as a ``CacheMissError``."""
    try:
        return cache.get_or_download(source.url, revalidate=revalidate, sha256=source.sha256).path
    except PinMismatchError as exc:
        raise SourceIntegrityError(
            f"{source.name}: {exc}; the upstream file may have changed since it was pinned (the cache is unchanged)"
        ) from exc


def load_workbook(path: str | os.PathLike[str]) -> openpyxl.Workbook:
    """Read-only workbook from a stream.

    The cache stores bodies as ``<sha256>.bin``; openpyxl refuses that suffix on a path but not on a stream.
    """
    with Path(path).open("rb") as handle:
        return openpyxl.load_workbook(io.BytesIO(handle.read()), data_only=True, read_only=True)

"""Fetch-and-verify seam shared by the reference-table loaders.

Runtime fetch, not packaged (ADR 0006): every loader reads through the existing
``DownloadCache`` (offline-first via ``revalidate=False``) and verifies the
downloaded body against the original file's pinned sha256, catching upstream
content drift that a mere HTTP 200 would not.
"""

from __future__ import annotations

from pathlib import Path

from mloda_plugin_govdata.feature_groups.govdata.core.cache import DownloadCache

from .sources import ReferenceSource


class SourceIntegrityError(RuntimeError):
    """Raised when a fetched reference file's sha256 does not match its ADR 0006 pin."""


def fetch_pinned(cache: DownloadCache, source: ReferenceSource, *, revalidate: bool = False) -> Path:
    cached = cache.get_or_download(source.url, revalidate=revalidate)
    if source.sha256 is not None and cached.sha256 != source.sha256:
        raise SourceIntegrityError(
            f"{source.name}: downloaded sha256 {cached.sha256} does not match the pinned "
            f"{source.sha256} (url={source.url}); the upstream file may have changed since ADR 0006"
        )
    return cached.path

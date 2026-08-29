"""mloda reader for a GENESIS ``data/tablefile`` selection (ffcsv).

Overrides ``_read_table`` rather than ``_fetch``: the inherited ``_fetch(locator, client)`` seam
(built for a GET-based CKAN reader) never receives ``Options``, but a POST fetch here needs
explicit credentials read from ``Options.context``. ``match_subclass_data_access`` and
``_coerce_locator`` need no override: the generic base already derives them from
``locator_type()`` (see ``BaseGovDataReader``).
"""

from __future__ import annotations

import functools
from pathlib import Path

import pyarrow as pa
from mloda.user import Options

from ..govdata.core.provenance import FetchedPayload, Provenance
from ..govdata.reader import BaseGovDataReader
from .core.api import GenesisClient, fetch_tablefile, tablefile_parameters
from .core.auth import explicit_credentials_from_options
from .core.cache import ParameterCache
from .core.hosts import resolve_host
from .core.parse import parse_ffcsv_zip
from .locator import DestatisLocator


class DestatisReader(BaseGovDataReader[DestatisLocator]):
    """Reads one GENESIS table selection into a typed Arrow table, ffcsv parsed."""

    @classmethod
    def suffix(cls) -> tuple[str, ...]:
        return (".zip",)

    @classmethod
    def locator_type(cls) -> type[DestatisLocator]:
        return DestatisLocator

    @classmethod
    def _tablefile_fields(cls, locator: DestatisLocator) -> dict[str, object]:
        return tablefile_parameters(
            locator.name,
            regionalvariable=locator.regionalvariable,
            regionalkey=locator.regionalkey,
            classifyingvariable1=locator.classifyingvariable1,
            classifyingkey1=locator.classifyingkey1,
            classifyingvariable2=locator.classifyingvariable2,
            classifyingkey2=locator.classifyingkey2,
            classifyingvariable3=locator.classifyingvariable3,
            classifyingkey3=locator.classifyingkey3,
            classifyingvariable4=locator.classifyingvariable4,
            classifyingkey4=locator.classifyingkey4,
            classifyingvariable5=locator.classifyingvariable5,
            classifyingkey5=locator.classifyingkey5,
            contents=locator.contents,
            startyear=locator.startyear,
            endyear=locator.endyear,
            quality=locator.quality,
            language=locator.language,
        )

    @classmethod
    def _fetch_tablefile(cls, locator: DestatisLocator, options: Options | None) -> FetchedPayload:
        """POSTs (or reuses a cached reply for) the selection; credentials resolve lazily on a miss only."""
        host = resolve_host(locator.host)
        explicit = explicit_credentials_from_options(options)
        fields = cls._tablefile_fields(locator)
        cache = ParameterCache(cls.cache_dir)
        with GenesisClient(host, credentials=explicit, lock_dir=cls.cache_dir) as client:
            fetch = functools.partial(fetch_tablefile, client)
            cached = cache.get_or_fetch(host, "data/tablefile", fields, fetch)
        provenance = Provenance(source="genesis", url=host.url("data/tablefile"), parameters=cached.parameters)
        return FetchedPayload(
            path=cached.path, sha256=cached.sha256, retrieved_at=cached.retrieved_at, provenance=provenance
        )

    @classmethod
    def _read_table(cls, locator: DestatisLocator, options: Options | None = None) -> pa.Table:
        payload = cls._fetch_tablefile(locator, options)
        return cls._parse(payload.path, locator, payload.provenance, options)

    @classmethod
    def _parse(
        cls, path: Path, locator: DestatisLocator, provenance: Provenance, options: Options | None = None
    ) -> pa.Table:
        return parse_ffcsv_zip(path.read_bytes())

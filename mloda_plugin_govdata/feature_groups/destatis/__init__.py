"""Destatis GENESIS connector: ``DestatisReader`` reads the table selection a ``DestatisLocator`` names.

GENESIS is the database software and its REST API. ``genesis`` (GENESIS-Online, Destatis) and ``regionalstatistik``
(Regionaldatenbank, run by IT.NRW) are two installations of it, each with its own registration. By convention
``Destatis*`` classes face mloda and ``Genesis*`` classes speak the protocol; ``OPTION_GENESIS_CREDENTIALS`` is an
mloda option despite its name.
"""

from .core.api import (
    GENESIS_ONLINE,
    KNOWN_HOSTS,
    OPERATIONS,
    REGIONALSTATISTIK,
    GenesisClient,
    GenesisHost,
    Operation,
    resolve_host,
)
from .core.auth import (
    OPTION_GENESIS_CREDENTIALS,
    DestatisCredentials,
    credentials_from_options,
    explicit_credentials_from_options,
)
from .core.cache import SELECTION_FIELDS, STALE_AFTER, CachedPayload, ParameterCache, canonical_parameters
from .core.envelope import (
    GenesisEnvelope,
    GenesisIdent,
    GenesisStatus,
    HelloWorldReply,
    LoginCheckReply,
    inspect_response,
    parse_json_reply,
    raise_for_logincheck,
    raise_for_status_block,
)
from .core.errors import (
    GenesisAuthError,
    GenesisBackendError,
    GenesisEmptySelection,
    GenesisError,
    GenesisJobAccepted,
    GenesisMaintenance,
    GenesisResultTooLarge,
    GenesisUnknownEnvelope,
    GenesisUnknownTable,
    MissingCredentialsError,
    WrongHostCredentialsError,
)
from .core.parse import parse_ffcsv_bytes, parse_ffcsv_zip
from .core.redact import redact_json, redact_text, secret_variants
from .locator import DestatisLocator
from .reader import DestatisReader

__all__ = [
    "GENESIS_ONLINE",
    "KNOWN_HOSTS",
    "OPERATIONS",
    "OPTION_GENESIS_CREDENTIALS",
    "REGIONALSTATISTIK",
    "SELECTION_FIELDS",
    "STALE_AFTER",
    "CachedPayload",
    "DestatisCredentials",
    "DestatisLocator",
    "DestatisReader",
    "GenesisAuthError",
    "GenesisBackendError",
    "GenesisClient",
    "GenesisEmptySelection",
    "GenesisEnvelope",
    "GenesisError",
    "GenesisHost",
    "GenesisIdent",
    "GenesisJobAccepted",
    "GenesisMaintenance",
    "GenesisResultTooLarge",
    "GenesisStatus",
    "GenesisUnknownEnvelope",
    "GenesisUnknownTable",
    "HelloWorldReply",
    "LoginCheckReply",
    "MissingCredentialsError",
    "Operation",
    "ParameterCache",
    "WrongHostCredentialsError",
    "canonical_parameters",
    "credentials_from_options",
    "explicit_credentials_from_options",
    "inspect_response",
    "parse_ffcsv_bytes",
    "parse_ffcsv_zip",
    "parse_json_reply",
    "raise_for_logincheck",
    "raise_for_status_block",
    "redact_json",
    "redact_text",
    "resolve_host",
    "secret_variants",
]

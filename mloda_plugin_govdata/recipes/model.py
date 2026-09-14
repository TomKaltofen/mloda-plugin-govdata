"""Recipe file model, fail-fast: the mloda feature array plus links and compliance blocks; never carries credentials."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ..feature_groups.destatis.core.hosts import KNOWN_HOSTS
from ..feature_groups.destatis.core.redact import CREDENTIAL_KEYS, secret_variants

JoinName = Literal["inner", "left", "right", "outer", "append", "union"]

# A key names a credential when it contains one of these (lower-cased) or one of its `_`/`-`/`.`-separated
# words is in CREDENTIAL_KEY_TERMS. Substrings would make "auth" hit "author", hence the two tiers.
CREDENTIAL_KEY_WORDS: tuple[str, ...] = (
    "token",
    "password",
    "passwd",
    "secret",
    "apikey",
    "api_key",
    "credential",
    "bearer",
    "authorization",
)
CREDENTIAL_KEY_TERMS: frozenset[str] = frozenset({"user", "auth", "pwd", "login", "kennung"})
# A run of letters and digits with no separator, long enough to be an API token. The GENESIS token is one
# such run; table codes, slugs, URLs, region keys, and dates carry separators or are shorter, so they pass.
TOKEN_RUN_LENGTH = 24
_TOKEN_RUN = re.compile(rf"[A-Za-z0-9]{{{TOKEN_RUN_LENGTH},}}", re.ASCII)
_KEY_WORDS = re.compile(r"[^a-z0-9]+")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$", re.ASCII)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
# The only places a hash or a credential-named field is legitimate, anchored to their exact paths.
_SHA256_FIELD = re.compile(r"^compliance\.sources\[\d+\]\.sha256$")
_CREDENTIAL_ENV_FIELD = re.compile(r"^compliance\.sources\[\d+\]\.credential_env$")
# Shorter env values are not scanned for (a short user name would match ordinary words).
_MIN_ENV_SECRET_LENGTH = 8


class RecipeError(ValueError):
    """A recipe failed validation or could not be turned into mloda objects."""


def error_summary(exc: ValidationError) -> str:
    """Locations and messages only: pydantic's default text echoes the input, which may be the rejected credential."""
    parts = []
    for error in exc.errors(include_url=False, include_context=False, include_input=False):
        location = ".".join(str(part) for part in error["loc"])
        message = error["msg"].removeprefix("Value error, ")
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts)


def _forbid_extra() -> ConfigDict:
    return ConfigDict(extra="forbid")


class FeatureItem(BaseModel):
    """One object item of the mloda feature array; fields and cross-field rules mirror mloda's ``FeatureConfig``."""

    model_config = _forbid_extra()

    name: str = Field(min_length=1)
    options: dict[str, Any] | None = None
    in_features: list[str] | None = None
    group_options: dict[str, Any] | None = None
    context_options: dict[str, Any] | None = None
    propagate_context_keys: list[str] | None = None
    column_index: int | None = None
    feature_group: str | None = None

    @model_validator(mode="after")
    def _mloda_rules(self) -> FeatureItem:
        if self.options and (self.group_options or self.context_options):
            raise ValueError("options cannot be combined with group_options or context_options")
        if self.propagate_context_keys and not self.context_options:
            raise ValueError("propagate_context_keys needs context_options")
        return self


class JoinSide(BaseModel):
    """One side of a link: the FeatureGroup class name, its key columns, and the node discriminator."""

    model_config = _forbid_extra()

    feature_group: str = Field(min_length=1)
    index: list[str] = Field(min_length=1)
    discriminator: dict[str, Any] | None = None

    @field_validator("index")
    @classmethod
    def _non_empty_columns(cls, value: list[str]) -> list[str]:
        if any(not column for column in value):
            raise ValueError("index columns must be non-empty strings")
        return value


class LinkSpec(BaseModel):
    """A join the feature array cannot express; ``asof`` needs its own config and is not a recipe join."""

    model_config = _forbid_extra()

    join: JoinName
    left: JoinSide
    right: JoinSide


class SourceCompliance(BaseModel):
    """Provenance and license of one data source a recipe reads."""

    model_config = _forbid_extra()

    license: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    dataset_uri: str
    retrieved_at: AwareDatetime
    sha256: str
    modifications: list[str] = Field(default_factory=list)
    credential_env: list[str] = Field(default_factory=list)

    @field_validator("dataset_uri")
    @classmethod
    def _uri_has_a_scheme(cls, value: str) -> str:
        if "://" not in value:
            raise ValueError("dataset_uri must be a URI with a scheme")
        return value

    @field_validator("sha256")
    @classmethod
    def _sha256_shape(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("sha256 must be 64 lower-case hex digits")
        return value

    @field_validator("credential_env")
    @classmethod
    def _env_names_only(cls, value: list[str]) -> list[str]:
        # Positions only: an entry here may be a pasted credential value, which must not reach the message.
        bad = [position for position, name in enumerate(value) if not _ENV_NAME.fullmatch(name)]
        if bad:
            raise ValueError(f"credential_env holds env-var names only (e.g. GENESIS_TOKEN); entries {bad} are not")
        return value


class Compliance(BaseModel):
    """The compliance block: one entry per source, plus free-text notes (census breaks, caveats)."""

    model_config = _forbid_extra()

    sources: list[SourceCompliance] = Field(min_length=1)
    notes: str | None = None


class Recipe(BaseModel):
    """The recipe file. ``features`` stays the raw mloda array so it reaches the loader verbatim."""

    model_config = _forbid_extra()

    features: list[str | dict[str, Any]] = Field(min_length=1)
    links: list[LinkSpec] = Field(default_factory=list)
    compliance: Compliance

    @field_validator("features")
    @classmethod
    def _feature_items(cls, value: list[str | dict[str, Any]]) -> list[str | dict[str, Any]]:
        allowed = set(FeatureItem.model_fields)
        for position, item in enumerate(value):
            if isinstance(item, str):
                if not item:
                    raise ValueError(f"features[{position}]: a feature name must not be empty")
                continue
            unknown = sorted(set(item) - allowed)
            if unknown:
                raise ValueError(
                    f"features[{position}]: unknown key(s) {unknown}; mloda feature items allow {sorted(allowed)}"
                )
            try:
                FeatureItem.model_validate(item)
            except ValidationError as exc:
                raise ValueError(f"features[{position}]: {error_summary(exc)}") from None
        return value

    @field_validator("links")
    @classmethod
    def _no_duplicate_links(cls, value: list[LinkSpec]) -> list[LinkSpec]:
        for position, spec in enumerate(value):
            for earlier in range(position):
                if value[earlier] == spec:
                    raise ValueError(f"links[{position}] repeats links[{earlier}]")
        return value

    @model_validator(mode="after")
    def _no_credentials(self) -> Recipe:
        tree = self.model_dump(mode="json")
        secrets = environment_secrets()
        # Keys first, parents before children, so a message never has to print a key that is itself a secret.
        for parent, key in _keys(tree):
            where = f"{parent}.{key}" if parent else key
            if _credential_named(key) and not _CREDENTIAL_ENV_FIELD.fullmatch(where):
                raise ValueError(f"{where}: {key!r} names a credential; credentials resolve from the environment")
            if _token_shaped(key):
                raise ValueError(f"{parent or 'recipe'}: a key looks like an API token")
            if _matches_secret(key, secrets):
                raise ValueError(
                    f"{parent or 'recipe'}: a key contains a value of a GENESIS credential set in this environment"
                )
        for path, leaf in _leaves(tree):
            if not isinstance(leaf, str):
                continue
            if _token_shaped(leaf) and not (_SHA256_FIELD.fullmatch(path) and _SHA256.fullmatch(leaf)):
                raise ValueError(
                    f"{path}: value looks like an API token ({TOKEN_RUN_LENGTH} or more letters and digits "
                    "without a separator)"
                )
            if _url_carries_credentials(leaf):
                raise ValueError(f"{path}: URL carries credentials in front of the host")
            if _matches_secret(leaf, secrets):
                raise ValueError(f"{path}: contains a value of a GENESIS credential set in this environment")
        return self


def _credential_named(key: str) -> bool:
    lowered = key.lower()
    if lowered in CREDENTIAL_KEYS or any(word in lowered for word in CREDENTIAL_KEY_WORDS):
        return True
    return any(term in CREDENTIAL_KEY_TERMS for term in _KEY_WORDS.split(lowered))


def _token_shaped(value: str) -> bool:
    return any(any(ch.isalpha() for ch in run) and any(ch.isdigit() for ch in run) for run in _TOKEN_RUN.findall(value))


def _url_carries_credentials(value: str) -> bool:
    if "://" not in value:
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return bool(parts.username or parts.password)


def _matches_secret(text: str, secrets: set[str]) -> bool:
    lowered = text.lower()
    return any(secret in lowered for secret in secrets)


def environment_secrets(environ: Mapping[str, str] | None = None) -> set[str]:
    """Lower-cased variants of the GENESIS credential values set in ``environ`` (default: the process env).

    Tokens and passwords are scanned as they are. A user name is scanned only when it is identifier-shaped
    (carries a digit or ``@``): a plain-word user name would match ordinary prose and URLs.
    """
    env = os.environ if environ is None else environ
    found: set[str] = set()
    for host in KNOWN_HOSTS.values():
        for suffix in ("TOKEN", "PASSWORD", "USER"):
            value = env.get(host.env_var(suffix), "").strip()
            if len(value) < _MIN_ENV_SECRET_LENGTH:
                continue
            if suffix == "USER" and "@" not in value and not any(ch.isdigit() for ch in value):
                continue
            found.update(variant.lower() for variant in secret_variants(value))
    return found


def _leaves(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for position, value in enumerate(node):
            yield from _leaves(value, f"{path}[{position}]")
    else:
        yield path, node


def _keys(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Every dict key as (parent path, key), parents before children."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, str(key)
            yield from _keys(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for position, value in enumerate(node):
            yield from _keys(value, f"{path}[{position}]")

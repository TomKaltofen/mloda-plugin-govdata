"""Recipe file model, fail-fast: the mloda feature array plus links and compliance blocks; never carries credentials."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ..feature_groups.destatis.core.auth import ENV_SUFFIXES
from ..feature_groups.destatis.core.hosts import KNOWN_HOSTS
from ..feature_groups.destatis.core.redact import CREDENTIAL_KEYS, secret_variants

JoinName = Literal["inner", "left", "right", "outer", "append", "union"]

# Key names (lower-cased, substring match) that name a credential wherever they appear in a recipe.
CREDENTIAL_KEY_WORDS: tuple[str, ...] = ("token", "password", "passwd", "secret", "apikey", "api_key", "credential")
# A run of letters and digits with no separator, long enough to be an API token. Table codes, slugs, URLs,
# region keys, and dates all carry separators or are shorter, so they pass.
TOKEN_RUN_LENGTH = 24
_TOKEN_RUN = re.compile(rf"[A-Za-z0-9]{{{TOKEN_RUN_LENGTH},}}", re.ASCII)
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$", re.ASCII)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
# Shorter env values are not treated as secrets to scan for (a one-letter user would match everywhere).
_MIN_ENV_SECRET_LENGTH = 8


class RecipeError(ValueError):
    """A recipe failed validation or could not be turned into mloda objects."""


def error_summary(exc: ValidationError) -> str:
    """Locations and messages only: pydantic's default text echoes the input, which may be the rejected credential."""
    parts = []
    for error in exc.errors(include_url=False, include_context=False, include_input=False):
        location = ".".join(str(part) for part in error["loc"])
        parts.append(f"{location}: {error['msg']}" if location else error["msg"])
    return "; ".join(parts)


def _forbid_extra() -> ConfigDict:
    return ConfigDict(extra="forbid")


class FeatureItem(BaseModel):
    """One object item of the mloda feature array; the field set mirrors mloda's ``FeatureConfig``."""

    model_config = _forbid_extra()

    name: str = Field(min_length=1)
    options: dict[str, Any] | None = None
    in_features: list[str] | None = None
    group_options: dict[str, Any] | None = None
    context_options: dict[str, Any] | None = None
    propagate_context_keys: list[str] | None = None
    column_index: int | None = None
    feature_group: str | None = None


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
            raise ValueError(f"dataset_uri must be a URI with a scheme, got {value!r}")
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
        bad = [name for name in value if not _ENV_NAME.fullmatch(name)]
        if bad:
            raise ValueError(f"credential_env holds env-var names only (e.g. GENESIS_TOKEN), not {bad}")
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

    @model_validator(mode="after")
    def _no_credentials(self) -> Recipe:
        tree = self.model_dump(mode="json")
        for path, key in _keys(tree):
            if key != "credential_env" and _credential_named(key):
                raise ValueError(f"{path}: {key!r} names a credential; credentials resolve from the environment")
        for path, leaf in _leaves(tree):
            if isinstance(leaf, str) and not path.endswith(".sha256") and _token_shaped(leaf):
                raise ValueError(
                    f"{path}: value looks like an API token ({TOKEN_RUN_LENGTH} or more letters and digits "
                    "without a separator)"
                )
        secrets = environment_secrets()
        if secrets:
            for path, text in _strings(tree):
                lowered = text.lower()
                if any(secret in lowered for secret in secrets):
                    raise ValueError(f"{path}: contains a value of a GENESIS credential set in this environment")
        return self


def _credential_named(key: str) -> bool:
    lowered = key.lower()
    return lowered in CREDENTIAL_KEYS or any(word in lowered for word in CREDENTIAL_KEY_WORDS)


def _token_shaped(value: str) -> bool:
    return any(any(ch.isalpha() for ch in run) and any(ch.isdigit() for ch in run) for run in _TOKEN_RUN.findall(value))


def environment_secrets(environ: Mapping[str, str] | None = None) -> set[str]:
    """Lower-cased variants of every GENESIS credential value set in ``environ`` (default: the process env)."""
    env = os.environ if environ is None else environ
    found: set[str] = set()
    for host in KNOWN_HOSTS.values():
        for suffix in ENV_SUFFIXES:
            value = env.get(host.env_var(suffix), "").strip()
            if len(value) >= _MIN_ENV_SECRET_LENGTH:
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
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            yield child, str(key)
            yield from _keys(value, child)
    elif isinstance(node, list):
        for position, value in enumerate(node):
            yield from _keys(value, f"{path}[{position}]")


def _strings(node: Any) -> Iterator[tuple[str, str]]:
    """Every string in the tree, keys included."""
    yield from _keys(node)
    for path, leaf in _leaves(node):
        if isinstance(leaf, str):
            yield path, leaf

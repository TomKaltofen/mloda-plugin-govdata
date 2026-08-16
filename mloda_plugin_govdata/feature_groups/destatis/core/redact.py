"""Redaction for captured GENESIS traffic: secrets in any case or URL-encoding, and the echoed credential fields."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote, quote_plus

REDACTED = "<redacted>"

# JSON keys whose values are replaced regardless of content: the ``Parameter`` echo of every
# envelope and the ``Username`` echo of ``logincheck``.
CREDENTIAL_KEYS: frozenset[str] = frozenset({"username", "password"})

# Values a credential field may keep: the guest marker and the server's own masking.
GUEST_MARKER = "GAST"


def _is_public_marker(value: str) -> bool:
    text = value.strip()
    return text == GUEST_MARKER or (bool(text) and set(text) == {"*"})


def secret_variants(secret: str) -> set[str]:
    """The forms a secret can take in traffic: as is, case-flipped, URL-encoded (and case-flipped again)."""
    if not secret:
        return set()
    forms = {secret, quote(secret, safe=""), quote_plus(secret)}
    return {variant for form in forms for variant in (form, form.upper(), form.lower())}


def _pattern(secrets: Iterable[str]) -> re.Pattern[str] | None:
    variants = {variant for secret in secrets for variant in secret_variants(secret)}
    if not variants:
        return None
    # Longest first, so an encoded form is not partially eaten by its shorter plain form.
    ordered = sorted(variants, key=len, reverse=True)
    return re.compile("|".join(re.escape(v) for v in ordered), flags=re.IGNORECASE)


def redact_text(text: str, secrets: Iterable[str], placeholder: str = REDACTED) -> str:
    """Replace every variant of every secret, case-insensitively."""
    pattern = _pattern(secrets)
    return text if pattern is None else pattern.sub(placeholder, text)


def redact_json(value: Any, secrets: Iterable[str], placeholder: str = REDACTED) -> Any:
    """Redact a parsed JSON tree: credential-named keys structurally, every string by content."""
    pattern = _pattern(secrets)

    def credential_value(item: Any) -> Any:
        if isinstance(item, str) and not _is_public_marker(item):
            return placeholder
        return walk(item)

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                key: (credential_value(item) if str(key).lower() in CREDENTIAL_KEYS else walk(item))
                for key, item in node.items()
            }
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, str) and pattern is not None:
            return pattern.sub(placeholder, node)
        return node

    return walk(value)

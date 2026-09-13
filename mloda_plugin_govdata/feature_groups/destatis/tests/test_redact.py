"""Redaction for captured traffic: every case and encoding of a secret, and the echoed credential fields."""

import json
from urllib.parse import quote, quote_plus

from mloda_plugin_govdata.feature_groups.destatis.core.redact import REDACTED, redact_json, redact_text, secret_variants

TOKEN = "AbC123xyzTOKEN9876543210abcdefgh"
PASSWORD = "p4ss w0rd?&=ü"


def _contains_secret(text: str) -> bool:
    lowered = text.lower()
    return any(variant.lower() in lowered for variant in secret_variants(TOKEN) | secret_variants(PASSWORD))


def test_synthetic_payload_is_fully_redacted() -> None:
    payload = {
        "Ident": {"Service": "helloworld", "Method": "logincheck"},
        "Status": f"echo {TOKEN} and {TOKEN.upper()} and {TOKEN.lower()} and {quote(PASSWORD, safe='')}",
        "Username": TOKEN.upper(),
        "Parameter": {"username": TOKEN, "password": PASSWORD, "language": "de"},
        "List": [{"Code": "p", "Content": f"url {quote_plus(PASSWORD)}"}],
    }
    redacted = redact_json(payload, [TOKEN, PASSWORD])
    dumped = json.dumps(redacted, ensure_ascii=False)
    assert not _contains_secret(dumped)
    assert redacted["Username"] == REDACTED
    assert redacted["Parameter"] == {"username": REDACTED, "password": REDACTED, "language": "de"}
    assert redacted["Ident"] == payload["Ident"]
    assert redacted["List"][0]["Code"] == "p"


def test_public_markers_survive_structural_redaction() -> None:
    payload = {"Username": "GAST", "Parameter": {"username": "********************", "password": "*"}}
    assert redact_json(payload, [TOKEN]) == payload


def test_text_redaction_handles_encoded_and_case_flipped_forms() -> None:
    text = f"a={quote(PASSWORD, safe='')}&b={TOKEN.lower()}&c={quote_plus(PASSWORD).upper()}"
    assert not _contains_secret(redact_text(text, [TOKEN, PASSWORD]))
    assert redact_text("nothing here", []) == "nothing here"
    assert redact_text("empty secret keeps text", [""]) == "empty secret keeps text"

"""Capture GENESIS replies as redacted test fixtures (repo tooling, not shipped).

Usage:
    python scripts/capture_genesis_fixtures.py --host genesis --out mloda_plugin_govdata/feature_groups/destatis/tests/fixtures \
        [--table 12411-0015 ...] [--tablefile name=12411-0015 --tablefile format=ffcsv ...] [--guest]

Credentials come from the host's env vars (GENESIS_TOKEN or GENESIS_USER plus GENESIS_PASSWORD;
REGIONALSTATISTIK_* for the second host). With ``--guest`` and no credentials the calls run
unauthenticated, which is how the error envelopes were characterized. Every secret value is
redacted in any case or URL-encoding, and the echoed ``username`` / ``password`` / ``Username``
fields are replaced regardless of content. One NOTICE line per file is appended in ``--out``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

import httpx

from mloda_plugin_govdata.feature_groups.destatis.core.api import KNOWN_HOSTS, GenesisClient
from mloda_plugin_govdata.feature_groups.destatis.core.auth import DestatisCredentials
from mloda_plugin_govdata.feature_groups.destatis.core.envelope import inspect_response
from mloda_plugin_govdata.feature_groups.destatis.core.errors import GenesisError
from mloda_plugin_govdata.feature_groups.destatis.core.redact import redact_json, redact_text


def _parse_pairs(pairs: Sequence[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise SystemExit(f"--tablefile expects key=value, got {pair!r}")
        params[key] = value
    return params


def _classify(response: httpx.Response, endpoint: str) -> str:
    try:
        inspected = inspect_response(response, endpoint)
    except GenesisError as exc:
        return f"{type(exc).__name__}"
    return inspected.kind


def _write(out: Path, name: str, data: bytes) -> str:
    path = out / name
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _notice_line(
    out: Path, host: str, name: str, endpoint: str, params: Mapping[str, str], status: int, sha: str
) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    shown = json.dumps(dict(params), ensure_ascii=False)
    line = (
        f"{name}\n"
        f"Source: GENESIS webservice, host {host}, {endpoint} {shown}, captured {stamp} (HTTP {status}), sha256 {sha}.\n"
        "Redaction: secret values replaced in any case or URL-encoding; username / password / Username fields "
        "replaced regardless of content.\n"
    )
    with (out / "NOTICE").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def capture(
    client: GenesisClient, endpoint: str, params: Mapping[str, str], out: Path, name: str, secrets: Sequence[str]
) -> None:
    response = client.request(endpoint, params)
    kind = _classify(response, endpoint)
    body = response.content
    if body[:4] == b"PK\x03\x04":
        file_name = f"{name}.zip"
        sha = _write(out, file_name, body)
    else:
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
        if payload is None:
            file_name = f"{name}.txt"
            sha = _write(out, file_name, redact_text(body.decode("utf-8", errors="replace"), secrets).encode("utf-8"))
        else:
            file_name = f"{name}.json"
            text = json.dumps(redact_json(payload, secrets), ensure_ascii=False, indent=2) + "\n"
            sha = _write(out, file_name, text.encode("utf-8"))
    shown = {k: redact_text(v, secrets) for k, v in params.items()}
    _notice_line(out, client.host.name, file_name, endpoint, shown, response.status_code, sha)
    print(f"{file_name}: HTTP {response.status_code}, {kind}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", choices=sorted(KNOWN_HOSTS), default="genesis")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--table", action="append", default=[], help="metadata/table for this table code (repeatable)")
    parser.add_argument(
        "--tablefile", action="append", default=[], help="data/tablefile form field key=value (repeatable)"
    )
    parser.add_argument("--language", default="de")
    parser.add_argument("--guest", action="store_true", help="run without credentials when none are configured")
    parser.add_argument("--prefix", default="", help="file name prefix, default: the host name")
    args = parser.parse_args(argv)

    host = KNOWN_HOSTS[args.host]
    credentials = DestatisCredentials.from_env(host)
    if credentials is None and not args.guest:
        print(f"no credentials for {host.name}; set {host.env_var('TOKEN')} or pass --guest", file=sys.stderr)
        return 2
    secrets: tuple[str, ...] = credentials.secrets() if credentials is not None else ()
    prefix = args.prefix or host.name
    args.out.mkdir(parents=True, exist_ok=True)

    with GenesisClient(host, credentials, language=args.language, allow_guest=args.guest) as client:
        capture(client, "helloworld/whoami", {}, args.out, f"{prefix}-whoami", secrets)
        capture(client, "helloworld/logincheck", {}, args.out, f"{prefix}-logincheck", secrets)
        capture(client, "catalogue/qualitysigns", {}, args.out, f"{prefix}-qualitysigns", secrets)
        for code in args.table:
            capture(client, "metadata/table", {"name": code}, args.out, f"{prefix}-metadata-table-{code}", secrets)
        if args.tablefile:
            params = _parse_pairs(args.tablefile)
            name = params.get("name", "unnamed")
            capture(client, "data/tablefile", params, args.out, f"{prefix}-tablefile-{name}", secrets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

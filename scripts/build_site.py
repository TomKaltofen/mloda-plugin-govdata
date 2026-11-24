"""Build the tutorial web pages: one static page per tutorial plus an index (repo tooling, not shipped).

Usage:
    uv run --env-file .env python scripts/build_site.py --out site

Every tutorial runs against the live sources, so this needs network access and ``GENESIS_TOKEN``.
A cell that fails, or a credential in a page, removes ``--out`` again.
"""

from __future__ import annotations

import argparse
import ast
import html
import shutil

# marimo's own export command, a fixed argument list, no shell.
import subprocess  # nosec B404
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from mloda_plugin_govdata.feature_groups.destatis import GENESIS_ONLINE, DestatisCredentials, MissingCredentialsError
from mloda_plugin_govdata.recipes.credential_scan import environment_secrets

TUTORIALS_DIR = Path(__file__).resolve().parents[1] / "tutorials"
REPO_URL = "https://github.com/mloda-ai/mloda-plugin-govdata"


def export(notebook: Path, page: Path) -> int:
    """Run the notebook and write it as one static page; non-zero when a cell failed."""
    command = [sys.executable, "-m", "marimo", "export", "html", str(notebook), "-o", str(page), "-f"]
    return subprocess.run(command, check=False).returncode  # nosec B603


def _first_docstring_line(notebook: Path) -> str | None:
    docstring = ast.get_docstring(ast.parse(notebook.read_text(encoding="utf-8")))
    return docstring.splitlines()[0].strip() if docstring else None


def _index(entries: Sequence[tuple[str, str]]) -> str:
    items = "\n".join(f'<li><a href="{html.escape(page)}">{html.escape(line)}</a></li>' for page, line in entries)
    built = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mloda-plugin-govdata tutorials</title>
<style>body {{ font-family: system-ui, sans-serif; max-width: 44rem; margin: 2rem auto; padding: 0 1rem; }}</style>
</head>
<body>
<h1>mloda-plugin-govdata tutorials</h1>
<p>German open government data as typed tables. Each tutorial is shown with the results it gave.</p>
<ul>
{items}
</ul>
<p>These pages are a snapshot from {built}. The inputs on them do not react: to change a value, run the
notebooks yourself, see the <a href="{REPO_URL}#tutorials-and-demos">README</a>
(auf Deutsch: <a href="{REPO_URL}/blob/main/docs/schnellstart.md">Schnellstart</a>).</p>
<p>Each tutorial ends with the source and the license of its data. The tutorial pages load their viewer,
marimo, from the jsDelivr network.</p>
<p>Funded by the German Federal Ministry of Research, Technology and Space (BMFTR) through the
<a href="https://prototypefund.de">Prototype Fund</a>, supported by the
<a href="https://okfn.de">Open Knowledge Foundation Deutschland</a>. Funding code: 16IS26S11.</p>
</body>
</html>
"""


def build(tutorials: Path, out: Path, secrets: set[str]) -> str | None:
    """Write every page and the index into ``out``; the reason when the result must not be kept."""
    notebooks = sorted(path for path in tutorials.glob("*.py") if not path.name.startswith("_"))
    if not notebooks:
        return f"no tutorials in {tutorials}"
    entries: list[tuple[str, str]] = []
    for notebook in notebooks:
        line = _first_docstring_line(notebook)
        if line is None:
            return f"{notebook.name} has no docstring for its index line"
        page = f"{notebook.stem}.html"
        if export(notebook, out / page) != 0:
            return f"{notebook.name} did not run to the end"
        entries.append((page, line))
    (out / "index.html").write_text(_index(entries), encoding="utf-8")
    for written in sorted(out.iterdir()):
        text = written.read_text(encoding="utf-8", errors="replace").lower()
        if any(secret in text for secret in secrets):
            return f"{written.name} contains a GENESIS credential"  # the file, never the value
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="a new or empty folder for the pages")
    parser.add_argument("--tutorials", type=Path, default=TUTORIALS_DIR, help="the folder with the notebooks")
    args = parser.parse_args(argv)

    # The same cases stop the tutorials that need a token, and a stopped cell does not fail its export.
    try:
        credentials = DestatisCredentials.from_env(GENESIS_ONLINE)
    except (MissingCredentialsError, ValueError):
        credentials = None
    secrets = environment_secrets()
    token = credentials.token if credentials is not None else None
    if token is None or token.lower() not in secrets:
        # A token too short to look for in the pages is refused too.
        print("Set GENESIS_TOKEN: the pages are built with the token and checked for it.", file=sys.stderr)
        return 2
    out: Path = args.out
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        print(f"{out} exists and is not empty; pass a new or empty folder.", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)

    problem: str | None = "the build broke off"
    try:
        problem = build(args.tutorials, out, secrets)
    finally:
        if problem is not None:  # also on an error nobody expected
            shutil.rmtree(out)
            print(f"{problem}; {out} removed.", file=sys.stderr)
    if problem is not None:
        return 1
    print(f"{out}: pages and index written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

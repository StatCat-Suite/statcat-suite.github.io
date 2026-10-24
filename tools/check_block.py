"""Fail when `docs/sites.md` shows a suite block other than the one `mkdocs.yml` uses.

Project sites copy the block from `docs/sites.md`, and this hub builds with the
block in `mkdocs.yml`. The two differ only in how they name the hub's own
assets: the hub lists them by relative path, a project by absolute URL. This
check compares them with those paths rewritten, so the copy the projects take
is always the configuration the hub renders with.

## Usage

    uv run python tools/check_block.py --check   # exit 1 if they differ
"""

import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = "# ── Suite configuration"
END = "# ── End of suite configuration"
SITE = "https://statcat-suite.github.io/"
#: The hub's relative asset paths, as a project names them.
ABSOLUTE = {
    "  - assets/stylesheets/statcat.css": f"  - {SITE}assets/stylesheets/statcat.css",
    "  logo: assets/favicon.svg": f"  logo: {SITE}assets/favicon.svg",
    "  favicon: assets/favicon.svg": f"  favicon: {SITE}assets/favicon.svg",
}


def _trim(lines: list[str]) -> list[str]:
    """Drop leading and trailing blank lines."""
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def hub_block() -> list[str]:
    """The block in `mkdocs.yml`, past its comment header, with asset paths made absolute.

    Returns:
        Its lines.
    """
    lines = (ROOT / "mkdocs.yml").read_text(encoding="utf-8").splitlines()
    body = lines[next(i for i, line in enumerate(lines) if line.startswith(START)) + 1 :]
    body = body[: next(i for i, line in enumerate(body) if line.startswith(END))]
    body = [line for line in body if not line.startswith("#")]
    return _trim([ABSOLUTE.get(line, line) for line in body])


def page_block() -> list[str]:
    """The first YAML block under "## The block" in `docs/sites.md`.

    Returns:
        Its lines.
    """
    lines = (ROOT / "docs" / "sites.md").read_text(encoding="utf-8").splitlines()
    rest = lines[lines.index("## The block") :]
    start = rest.index("```yaml") + 1
    return _trim(rest[start : rest.index("```", start)])


def main() -> int:
    """Print a diff when the two blocks differ; with `--check`, exit 1.

    Returns:
        The process exit status.
    """
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when the blocks differ")
    args = parser.parse_args()
    diff = list(difflib.unified_diff(hub_block(), page_block(), "mkdocs.yml", "docs/sites.md", lineterm=""))
    if not diff:
        print("suite block: docs/sites.md matches mkdocs.yml")  # noqa: T201
        return 0
    print("\n".join(diff))  # noqa: T201
    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())

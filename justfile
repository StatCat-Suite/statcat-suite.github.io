set dotenv-load

default:
    @just --list

# Serve the site locally with live reload
docs-serve:
    uv run mkdocs serve

# Build the site; --strict fails on broken links and pages missing from the nav
docs-build:
    uv run mkdocs build --strict

# Guard: no question headings, no banned hook phrases (CLAUDE.md "Writing style")
check-prose:
    uv run python tools/check_prose.py --check

# Guard: docs/sites.md shows the suite block mkdocs.yml builds with
check-block:
    uv run python tools/check_block.py --check

# The gate: prose and block checks, then the strict build
ci: check-prose check-block docs-build

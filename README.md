# statcat-suite.github.io

The StatCat Suite docs hub, served at https://statcat-suite.github.io/.

It holds the suite overview, the architecture shared by the projects, and the
configuration every project's docs site copies (`docs/sites.md`), including
the stylesheet those sites load from this one
(`docs/assets/stylesheets/statcat.css`).

```bash
uv sync --group dev
just docs-serve    # live preview at http://127.0.0.1:8000/
just ci            # prose check, block check, strict build
```

Pushes to `main` deploy through `.github/workflows/pages.yml`.

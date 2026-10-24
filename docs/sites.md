# Documentation sites

Each project builds and deploys its own docs site from its own repository,
versioned with its code, under one domain:

| Site | URL | Built from |
| --- | --- | --- |
| This hub | `https://statcat-suite.github.io/` | `StatCat-Suite/statcat-suite.github.io` |
| sdmxlib | `https://statcat-suite.github.io/sdmxlib/` | `StatCat-Suite/sdmxlib` |
| statcatlib | `https://statcat-suite.github.io/statcatlib/` | `StatCat-Suite/statcatlib` |
| sdmxlib-rest | `https://statcat-suite.github.io/sdmxlib-rest/` | `StatCat-Suite/sdmxlib-rest` |

GitHub Pages serves the organisation's `statcat-suite.github.io` repository
at the domain root and each project's Pages under its repository name, so the
sites share a domain with no proxy. Search covers one site at a time.

## What every site shares

Every site uses Material for MkDocs with the same configuration block, so the
sites share one look and link back to the hub:

- **One stylesheet,** served by this hub at
  `https://statcat-suite.github.io/assets/stylesheets/statcat.css`. Every site
  lists that URL, so a change to it restyles every site on its next page load.
  It holds the Catppuccin code highlighting, Latte in light mode and Mocha in
  dark mode.
- **One theme block:** the indigo palette with its light and dark toggle, the
  hub's cat logo as both the header logo and the favicon, and the same
  navigation features (tabs, sections, back-to-top, code copy).
- **Links to the hub:** the logo links to the hub (`extra.homepage`), the
  footer names the suite (`copyright`), and the last navigation tab is
  "StatCat Suite".
- **One set of Markdown extensions,** including Mermaid diagrams, so a page
  renders the same on every site.
- **Strict builds** that also fail on a link to a missing heading
  (`validation.links.anchors: warn` with `mkdocs build --strict`).

## The block

Copy this into a project's `mkdocs.yml`, below its `site_*` and `repo_*`
keys, and add the hub to the end of its `nav`. This hub's own `mkdocs.yml`
carries the same block with its stylesheet, logo and favicon given as
relative paths, and is the source this page is kept equal to.

```yaml
validation:
  links:
    anchors: warn

extra_css:
  - https://statcat-suite.github.io/assets/stylesheets/statcat.css

theme:
  name: material
  logo: https://statcat-suite.github.io/assets/favicon.svg
  icon:
    repo: fontawesome/brands/github
  favicon: https://statcat-suite.github.io/assets/favicon.svg
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: indigo
      accent: indigo
      toggle:
        icon: material/weather-sunny
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: indigo
      accent: indigo
      toggle:
        icon: material/weather-night
        name: Switch to light mode
  features:
    - content.code.copy
    - navigation.tabs
    - navigation.sections
    - navigation.top
    - toc.follow

extra:
  homepage: https://statcat-suite.github.io/
  social:
    - icon: fontawesome/brands/github
      link: https://github.com/StatCat-Suite
      name: StatCat Suite on GitHub

copyright: 'Part of the <a href="https://statcat-suite.github.io/">StatCat Suite</a>'

markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.inlinehilite
  - pymdownx.snippets
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
  - pymdownx.tabbed:
      alternate_style: true
  - tables
  - toc:
      permalink: true
```

```yaml
nav:
  # … the project's own pages …
  - StatCat Suite: https://statcat-suite.github.io/
```

A project adds what is its own after the block: its `nav`, plugins such as
`mkdocstrings`, extra Markdown extensions, and `hooks`. A project-specific
stylesheet goes in `extra_css` after the suite's, so it can override it.

## Linking between sites

An API reference generated with `mkdocstrings` publishes an `objects.inv`
inventory at its site root. Another site imports it to link to that project's
API by name:

```yaml
plugins:
  - mkdocstrings:
      handlers:
        python:
          inventories:
            - https://statcat-suite.github.io/sdmxlib/objects.inv
```

`[InternationalString][sdmxlib.InternationalString]` then links to sdmxlib's
page for the class, and every sdmxlib type in a generated signature links
there too.

## Adding a project

1. Copy the block into the project's `mkdocs.yml` and add the hub tab to its
   `nav`.
2. Deploy the site to the repository's GitHub Pages, as statcatlib's
   `.github/workflows/docs.yml` does.
3. Add the project to the table on the [home page](index.md), to the
   `Projects` section of this hub's `nav`, and to the table above.

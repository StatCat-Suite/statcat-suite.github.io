# Project conventions

Every StatCat Suite repository follows these conventions, beside the docs-site
block on [Documentation sites](sites.md). A project copies them from this page,
and a change to one starts here.

## README

A project's README opens with its title, a row of badges, and a note on AI
assistance, in that order.

### Badges

Replace `<pkg>` with the PyPI name, which is also the repository name:

```markdown
[![PyPI](https://img.shields.io/pypi/v/<pkg>)](https://pypi.org/project/<pkg>/)
[![Python](https://img.shields.io/pypi/pyversions/<pkg>)](https://pypi.org/project/<pkg>/)
[![License](https://img.shields.io/pypi/l/<pkg>)](LICENSE)
[![Docs](https://github.com/StatCat-Suite/<pkg>/actions/workflows/docs.yml/badge.svg)](https://statcat-suite.github.io/<pkg>/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
```

The row shows what every project has: a PyPI release, its Python versions and
licence (read from PyPI), the docs workflow, and the two Astral tools every
project builds with. sdmxlib and statcatlib run their tests in a local
`just ci`, so the shared row carries no test or coverage badge. A project whose
tests run on GitHub Actions, as sdmxlib-rest's do, may add its CI badge after
the row.

### AI-use note

The note follows the badges:

```markdown
> **Note:** This library has been written extensively with AI assistance
> (Claude Code). Users who are not comfortable with AI-generated code should
> take that into account before adopting it.
```

It is the one place a project discloses AI assistance. Commits, PRs, issues
and comments carry no byline (see [Commits, PRs and issues](#commits-prs-and-issues)).

## Install instructions

Every install instruction names `uv add` first and `pip install` second, as
the fallback. This covers READMEs, docs pages, and CLI and error messages:

```bash
uv add statcatlib
# or: pip install statcatlib
```

Quote extras, so a shell such as zsh does not expand the brackets:
`uv add 'statcatlib[search]'`. Use `uv add` to add a dependency, not
`uv pip install`.

## Commits, PRs and issues

- **Conventional commits.** git-cliff builds each CHANGELOG from them, one entry
  per commit.
- **No Claude byline.** Commit messages carry no `Co-Authored-By: Claude`
  trailer, and PR descriptions, issues and comments carry no "Generated with
  Claude Code" footer. The README's note discloses AI assistance once for the
  project.
- **Issue references.** Write a GitHub issue or PR in the same repository as
  `GH-N`, and one in another repository as `StatCat-Suite/<repo>#N`.

## The `main` branch and release tags

Each repository protects `main` with a GitHub ruleset:

- No force-push, and `main` cannot be deleted.
- Changes reach `main` only through a pull request. No approval is required,
  since maintainers and their agents share accounts.
- Merge commits only. A squash merge would fold a PR's conventional commits into
  one, and git-cliff would lose the entries. The repositories' settings disable
  squash and rebase merging as well.
- Administrators may bypass a rule when merging a pull request, never to push
  to `main` directly.
- A project whose tests run on GitHub Actions requires them to pass:
  sdmxlib-rest requires `check`, `test` and `test-floors`.

Each library also protects its release tags: a `v*` tag cannot be deleted or
moved. A wrong release is corrected by publishing the next version.

GitHub's organisation-wide rulesets need a paid plan, so the rulesets are set
in each repository. A new repository needs its own.

## Dependencies

Every suite library is pre-1.0, so a minor release may break its dependents.
A project caps each suite dependency below its next minor
(`sdmxlib>=0.72.0,<0.73`), and the pull request that adopts the new minor
raises the cap.

## Linting

Ruff's SLF001 (private-member-access) is off in every project. It cannot see
package boundaries, so a module reading its own package's underscored helpers
is flagged at every site. sdmxlib measured 40 suppressions and found no defect.
Projects do not add `# noqa: SLF001`.

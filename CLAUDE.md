# statcat-suite.github.io

The StatCat Suite docs hub: a Material for MkDocs site served at the root of
https://statcat-suite.github.io/. The project sites (sdmxlib, statcatlib) are
built and deployed from their own repositories and served under their own
paths on the same domain.

## What lives here

- `docs/index.md`, `docs/architecture.md`: what belongs to the suite as a
  whole. Anything one project owns (its guides, API, bundle-format sections)
  stays on that project's site, and the hub links to it.
- `docs/sites.md`: the configuration block every project site copies, and how
  sites link to each other.
- `docs/assets/stylesheets/statcat.css` and `docs/assets/favicon.svg`: served
  to every project site, which list them by absolute URL. A change to either
  restyles every site on its next page load, without a change in any project
  repository, so treat them as a shared interface.

## Rules

- The suite block in `mkdocs.yml` (between the "Suite configuration" markers)
  and the block shown in `docs/sites.md` must stay equal. `just check-block`
  enforces it, rewriting the hub's relative asset paths to the absolute URLs
  the projects use. Change `mkdocs.yml` first, then the page, then each
  project's copy.
- Do not edit the project repositories from here. A change the projects need
  goes in an issue on the project's repository.
- `just ci` is the gate: prose check, block check, `mkdocs build --strict`.
  The Pages workflow runs the same recipe before it deploys.

## Git / GitHub

- git commit/push/merge etc. will NEVER be done without asking.
- The project always uses conventional commits for commit messages.
- The repository is github.com/StatCat-Suite/statcat-suite.github.io; use `gh`
  for the API.
- Write a GitHub issue or PR as `GH-N`, and one in another repository as
  `StatCat-Suite/<repo>#N`.

## Writing style

These rules cover all prose written for this repo: comments, docstrings,
documentation, CHANGELOG and `docs/upgrading.md` entries, commit messages,
issues, PRs and milestones. The section is shared across the StatCat-Suite
repos (GH-58); change it in all three or none.

Write in plain language. State claims directly, in the order the reader
needs them. Use subject-verb-object sentences, concrete nouns, and the
actual number, name, or mechanism instead of an allusion to it.

Follow these rules from Strunk & White:

- Put statements in positive form.
- Use definite, specific, concrete language.
- Omit needless words.

Avoid these constructions everywhere (sentences, headings, titles, lists):

- Contrast by negation: "not X, but Y", "it's not about X, it's about Y",
  "X isn't the problem; Y is". State Y. Mention X only if someone
  actually holds that view.
- Hook clauses that read like half a question: "what X doesn't tell you",
  "the part nobody mentions", "the evidence Y lacks", "why this matters".
  State the fact the clause points at.
- Colon reveals: "The real issue: ...", "Here's the thing: ...",
  "The short version: ...". Drop the setup and write the sentence.
- Punchline structure: ending a sentence or list on a twist, a dramatic
  final item, or a short fragment for emphasis.
- Rhetorical questions that the text then answers.
- Framing work or ideas by what is missing when you can name what is
  present or proposed.

Titles (milestones, issues, PRs, headings):

- Name the deliverable or scope as a plain noun phrase or imperative.
  A reader should know from the title alone what gets merged or decided.
- Use a colon only to separate a component name from the work item
  (e.g. "Query DSL: add DuckDB backend"), never to introduce a hook.

Examples:

```text
Bad:  Conformance evidence: what the green checks do not prove
Good: Conformance: add negative and edge-case test fixtures

Bad:  Query DSL: a second backend, and the evidence the first one lacks
Good: Query DSL: add second backend; add validation tests for SQL backend

Bad:  The green checks tell you less than you'd think.
Good: The green checks only cover valid inputs; there are no tests
      for malformed DSDs or constraint violations.

Bad:  The problem isn't performance — it's correctness.
Good: The cache returns stale codelists after a version bump.

Bad:  Here's what the benchmark doesn't show: cold-start latency.
Good: The benchmark measures warm queries only; cold-start latency
      is untested.
```

Before finishing, reread the output. Rewrite any sentence that delays its
point, contrasts with a claim nobody made, or alludes to a fact instead of
stating it.


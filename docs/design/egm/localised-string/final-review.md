# Goldfish Review Report

**Target:** `concepts_brief.md` (lines 1–268), LocalisedString design brief
**Mode:** REVIEW, final pass before the suite-level RFC
**Reviewers:** egm-design, egm-codebase-details, egm-zoom-out, egm-comprehension,
egm-implementation-readiness, egm-structural, egm-style (one instance each; all
seven completed)
**Code read:** sdmxlib `feat/gh-280-language-tags` at `9955927`
(`99559276d71f02f2c606cf23c954928645018995`, read from
`.git/refs/heads/feat/gh-280-language-tags`; this session cannot run shell
commands, so `git rev-parse` was not run). statcatlib `src/` as on `main`
`4d4eebe`; working tree `docs/gh-88-lowercase-tags` at `f443534`.

**Counts:** 5 Blocking, 11 Major, 18 Minor.

**Verdict:** decisions 1–9 are consistent with one another. The brief cannot go
out as an RFC yet. Four things need settling before implementing agents can
start without returning with questions:

- how a msgspec value type validates its tag;
- the exact `Mapping` API;
- which migration gates catch the breaks that msgspec makes silent;
- a staging order that does not depend on the unmerged hub.

**Unverified by any reviewer (no code could be run):**

- the lookup benchmark figures (79/92/190/224/303 ns; 25/27 ns). Neither bench
  script saves output.
- the instance sizes (32/48/64 bytes).
- whether pyrefly flags `==` between `LocalisedString` and `str`.
- the runtime behaviour of user-defined dunders on a frozen msgspec Struct.
  The design reviewer read the strings in msgspec 0.22.0's compiled `_core`
  and its `.pyi`. msgspec refuses user-defined `__init__` and `__new__` and
  generates `__eq__`, `__hash__`, `__repr__`, `__copy__` and `__match_args__`.
  No reviewer found anything that forbids `__bool__`, `__str__` or
  `__format__`.
- the sdmx1 and pysdmx naming claims.

**Evidence paths:** the brief's `../localised-string-notes.md`,
`../bench_lookup.py` and `../bench_lookup_fair.py` resolve to
`scratchpad/egm/`. The files are one level higher:
`localised-string-notes.md`,
`bench_lookup.py`, `bench_lookup_fair.py`.
The notes cite a `bench_istring.py` that exists nowhere.

---

## Blocking

### B1. The value type has no specified construction or validation - Severity: Blocker
* **Reviewer Lens:** design, implementation-readiness, codebase-details
* **Affected Scope:** lines 29–31, 40, 77–82, 187; decision 6; Staging step 1
* **Discrepancy Description:** PR 308's `LocalizedText.lang` runs
  `normalize_tag` through an attrs converter (sdmxlib `model/istring.py:77-92`).
  Two things depend on it:
  - sdmxlib D7 (`docs/design/language-tags.md:202`) promises it;
  - `tests/unit/test_language_tags.py:207-213` asserts
    `LocalizedText("Annuel", "FR") == LocalizedText("Annuel", "fr")`, and line
    507 lists the constructor in the D3 refusal test.

  msgspec Structs cannot define `__init__` or `__new__`. A `__post_init__`
  runs on every construction, and that includes every lazy lookup. It can
  normalise only through `msgspec.structs.force_setattr`. A validating
  `__post_init__` has precedent in `OverlayText` (`bundle/_overlay.py:135,
  161`).

  The 92 ns and 32-byte figures come from `VStruct(msgspec.Struct,
  frozen=True, gc=False)` with no validation (`bench_lookup.py:38`). The brief
  says only "frozen `msgspec.Struct`". Staging step 1 therefore drops a
  guarantee that the brief's own migration step (statcatlib's copy of the D3
  test) relies on.
* **Rationale & Recommendation:** add to decision 6 a "Construction" paragraph
  that names one mechanism:
  > `LocalisedString` is `msgspec.Struct, frozen=True, gc=False` (both fields
  > `str`, so no reference cycles). Public construction normalises `lang`
  > [in `__post_init__` via `force_setattr` / or: does not normalise, and
  > `lang` is `Annotated[str, msgspec.Meta(pattern=...)]` so decode
  > validates]. Lookups build values from stored, already-normalised keys
  > [through the same path / a private unchecked path].

  Re-run the lookup benchmark on the class as specified, and put that figure
  in the Performance table. Rewrite D7 line 202 and test lines 207-213 and 507
  to match. Add a first-commit test of `bool`, `str`, `format`, `==` against
  `str`, `hash`, `repr` and `msgspec.json.encode` on msgspec 0.22.

### B2. The migration gates miss the breaks that msgspec makes silent - Severity: Blocker
* **Reviewer Lens:** codebase-details, design, implementation-readiness, zoom-out
* **Affected Scope:** lines 146–169 (Migration), Goals line 196–197
* **Discrepancy Description:** the brief says the migration "turns silent
  changes into failures" through strict pyrefly, a grep audit and one golden
  test. Three gaps defeat that.
  - **Encoding.** msgspec encodes a Struct natively as `{"text","lang"}`, so a
    value that reaches an sdmxlib encoder produces valid but wrong JSON
    instead of a `TypeError`. The encoders are `bundle/_canonical.py:50`
    (`Encoder(order="sorted")`) and `sdmx_json/_dto.py:337`, `writer.py:328`.
    Affected sites:
    - `_canonical.py:82` (`dict(value.items())`) would change every bundle
      fingerprint;
    - `_data_common.py:441` writes into `entry: dict[str, object]`, which
      pyrefly cannot check;
    - `_data_common.py:181, 386, 776-788` behave the same way.
  - **`x or fallback`.** Both repos set `implicit-bool = false`: sdmxlib
    `pyrefly.toml:78` (557 findings) and statcatlib `pyrefly.toml:60` (347
    findings). pyrefly does not report these sites.
  - **`== "text"`.** Neither repo configures a non-overlapping-equality rule,
    so pyrefly likely misses these comparisons (not verified by a run).
  - **The grep audit has no end point.** `.get(` also matches every
    `dict.get` and every lxml `child.get(XML_LANG, ...)`.

  pyrefly catches only sinks typed `str`: `storage/writers.py:291, 348`,
  statcatlib `store.py:748, 1162, 1171`, and `_canonical.py:82` through its
  `_Plain` return type.
* **Rationale & Recommendation:** replace the paragraph at lines 165–169 with
  this text:
  > The migration PR carries a call-site table: file:line, old expression, new
  > expression, and what catches it (pyrefly, a named test, or the audit). An
  > audit run sets `SDMXLIB_ISTRING_AUDIT=1`, which makes
  > `__getitem__`/`get`/`items` raise, and runs the full test suite to
  > enumerate read sites. Rows that pyrefly cannot catch each name a test:
  > - SDMX-JSON structure and data writer output validates against
  >   `tests/schemas/sdmx_json` on the round-trip fixtures
  >   (`tests/unit/test_roundtrip_complete.py`,
  >   `tests/integration/test_roundtrip_real_world.py`);
  > - `values[*].name`, `name`/`names` and `description`/`descriptions` in
  >   data messages are strings;
  > - `structure_frame(...)["concept"].dtype == pl.String`;
  > - statcatlib `sources/sdmx.py:115` handles an agency named `""`.
  >
  > The canonical form does not change: `_canonical.py:82` becomes
  > `value.as_dict()`, `CANONICAL_FORM` stays `"1"`, and the existing goldens
  > in `tests/unit/test_canonical_json.py:58` pass unregenerated. pyrefly's
  > `implicit-bool` stays off, and no step depends on it.

### B3. The `InternationalString` API is not specified to signatures - Severity: Blocker
* **Reviewer Lens:** implementation-readiness, design, comprehension
* **Affected Scope:** lines 32–36, decision 3, "Raw views"
* **Discrepancy Description:**
  - **Current class.** It does not subclass `Mapping` (`istring.py:116`).
    `items()` returns an `Iterator` (line 273), an incompatible override of
    `Mapping.items`. There is no `keys()` or `values()`. `__eq__` returns
    `NotImplemented` for non-`InternationalString` operands (lines 311–314).
  - **Registration.** pyrefly cannot see `Mapping.register()`, so the class
    must inherit. Inheriting `Mapping` sets `__hash__ = None` unless the class
    re-defines it.
  - **Views.** The mixin views call `__getitem__` per key, which re-normalises
    every stored tag. Round 1 M1 said to avoid exactly that cost.
  - **`get` signature.** typeshed's `Mapping.get` overloads are
    positional-only. The brief writes `get("fr", default=None)` at line 33 and
    calls it positionally at line 159, so it does not say which form it
    intends. A keyword-only default would be an incompatible override.
  - **Constructors.** `of(pairs: Mapping[str, str])` (lines 95–113) iterates
    `pairs.items()`. Once the class is itself a `Mapping[str,
    LocalisedString]`, `InternationalString.of(other)` would store Structs as
    text without an error. `to_istring` (line 330) accepts only `dict`.
  - **Other gaps.** `pick()` with no arguments and the fate of `langs` are
    undecided. Line 34 says `items()` yields `LocalisedString`; it yields
    pairs.
* **Rationale & Recommendation:** add a "Public API (normative)" section with:
  - full signatures: inherit `collections.abc.Mapping[str, LocalisedString]`;
    `__getitem__(lang, /)`; typeshed's two `get` overloads, positional default;
    `pick(*langs)` (zero args raises `TypeError`); `keys`/`values`/`items`
    views that read `_data` directly without re-normalising; `as_dict() ->
    dict[str, str]`; `__eq__` true only against `InternationalString`;
    `__hash__` kept;
  - `of()` and `to_istring` accepting `InternationalString | Mapping[str,
    str]` and refusing non-`str` values;
  - a before/after table (see M4).

  The implementation-readiness reviewer drafted this block in full; it can be
  pasted into the brief.

### B4. Decision 4 contradicts three of the proposals - Severity: Blocker
* **Reviewer Lens:** comprehension, design, zoom-out
* **Affected Scope:** line 37, decision 4 (lines 217–218), "Raw views", "Query
  DSL", line 159
* **Discrepancy Description:** "Every public lookup returns `LocalisedString`;
  none returns `str`" conflicts with three things the brief also proposes:
  - `as_dict() -> dict[str, str]` stays public;
  - DSL projections yield text;
  - `get(tag, default)` returns the caller's default, which can be a `str`.

  The brief also does not list which methods count as lookups. Open cases:
  Polars frames, `Row`, `.frame()`, `batch_labels`, `.select()`/`.scalars()`,
  and facet labels.
* **Rationale & Recommendation:** reword decision 4 and line 37:
  > Every per-tag accessor on `InternationalString` returns `LocalisedString`:
  > `[]`, `get`, `pick`, `values()`, and the values of `items()`. Bulk and
  > columnar outputs return text and carry the tag separately: `as_dict()`,
  > Polars frames, DSL projections and statcatlib projection columns.

  Follow it with a method / before / after table covering both repos.

### B5. Staging is out of order, and the RFC has no contract or acceptance section - Severity: Blocker
* **Reviewer Lens:** zoom-out, structural, implementation-readiness, design
* **Affected Scope:** lines 222–223 (decision 8), 247–258 (Sequencing,
  Staging)
* **Discrepancy Description:**
  - **The hub dependency.** Staging 1 rewrites sdmxlib D7 in PR 308 so that it
    points at a hub page, and step 2 publishes that page. The page waits on
    statcat-suite.github.io GH-12, which is unmerged. The text that assigns the
    JSON form to statcatlib is sdmxlib `docs/design/language-tags.md:39-40`
    (Non-goals) and `:331-335` (Cross-repo contract), as well as D7.
  - **PR 90.** statcatlib PR 90 (`f443534`) is about to merge text that
    contradicts decisions 1, 6 and 8. statcatlib `docs/design/language-tags.md`
    decision 14 (lines 201–209) says "attrs frozen class" and gives statcatlib
    the JSON form. Findings 8 and 12 (lines 99, 112) and slices 3–4 (lines
    225–228) name `LocalizedText`.
  - **Slices.** The brief says statcatlib adopts both changes "in slice 3"
    (line 250) and also gives slices 3 and 4 the work (lines 179, 257).
    statcatlib's RFC puts the return-type change in slice 4.
  - **Staging and Sequencing disagree.** Staging step 1 puts "value type" in
    PR 308; Sequencing puts only the rename there.
  - **Promised sections are missing.** Staging step 2 promises a "cross-repo
    contract section" that this document lacks. There are no acceptance
    criteria, and the benchmark gates have no numbers (line 191).
* **Rationale & Recommendation:**
  1. Replace Sequencing and Staging with one stage table. Each row gives the
     repo, PR, version, acceptance checks and rollback.
     - **Stage 0.** Amend PR 90 before it merges: decision 14 names
       `LocalisedString(text, lang)`, drops "attrs frozen", and records the
       JSON form as a suite contract. Findings 8 and 12 and slices 3–4 use the
       new name.
     - **Stage 1.** PR 308: the rename and the msgspec type (after B1 is
       decided). D7 states the JSON form inline as a suite contract. Update
       `docs/upgrading.md:33, 52-54`, `model/EGM.md:94, 119`, Non-goals 39–40
       and the exports at `model/__init__.py:96, 208` and
       `sdmxlib/__init__.py:172, 345`.
     - **Stage 2.** The sdmxlib lookup-API PR.
     - **Stage 3.** The hub page. It adds the hub link to sdmxlib D7 and to
       statcatlib decision 14.
     - **Stage 4.** statcatlib raises its upper bound on sdmxlib in a PR of its
       own.
     - **Stage 5.** statcatlib slice 4.
     - **Rollback, every stage.** No storage, `SCHEMA_VERSION` or
       `CANONICAL_FORM` change, so a revert needs no rebuild.
  2. Add `## Cross-repo contract`: the JSON form, the alias rule, what `lang`
     means, the error types, and which repo owns which name.
  3. Add `## Acceptance criteria` with numbers:
     - `get`/`[]`/`pick` each make at most N Python-level calls (deterministic
       cProfile, as in `tests/bench/test_bundle_reads.py`);
     - `values()`/`items()` make zero `normalize_tag` calls;
     - a same-process ratio gate, `get("fr")` ≤ 1.3× the `str` baseline on
       1,000,000 strings, median of 5 (round 1 M1 proposed 1.3×);
     - the canonical goldens pass unregenerated;
     - `tag_alias(t) == _language_slug(t)` for every stored tag;
     - every statcatlib `lang`/`langs` parameter refuses a malformed tag.

---

## Major

### M1. Some evidence is broken, missing or measured differently - Severity: Major
* **Reviewer Lens:** codebase-details, design, zoom-out, structural
* **Affected Scope:** lines 11–16, 51–75
* **Discrepancy Description:**
  - **Paths.** The evidence paths are wrong (see the header), and
    `bench_istring.py` is missing. The round 2 critiques are not on disk.
  - **Recorded output.** No output was saved for the lookup numbers.
  - **Table rows.** The rows were measured differently:
    - the 303 ns row comes from `bench_lookup.py` (real `pick`);
    - the other rows come from `bench_lookup_fair.py` (a free function closing
      over `_data`), so the 79 ns "`str` (today)" row is not today's `get`
      method;
    - the attrs row has no converter;
    - the struct row uses `gc=False`, which the 32-byte size depends on.
  - **The hoisted figures.** The 25/27 ns pair compares a method call that
    builds a list against inlined `_data.get` (`bench_lookup.py:76-84` vs
    100), so the two numbers are not comparable. The comparison is also moot,
    because `_text` stays `str`.
  - **Miss rate.** Only 60% of strings hold `fr`, so the 13 ns average is
    about 22 ns per value actually built.
  - **Hub links.** The hub copy would link scratchpad paths.
* **Rationale & Recommendation:** commit `bench_lookup*.py` and their raw
  output (Python version, machine) to sdmxlib `tests/bench/` or to
  `docs/design/egm/localised-string/` before the hub copy, and link them.
  Label the rows "attrs `@frozen`, no converter" and "free-function `get`".
  Mark the 303 ns row's source. Drop the 25/27 ns sentence or re-measure it.
  State the miss rate.

### M2. The identifier alias function is unspecified - Severity: Major
* **Reviewer Lens:** implementation-readiness, design, codebase-details,
  zoom-out
* **Affected Scope:** lines 41–42, 123–144, decision 7
* **Discrepancy Description:**
  - **Undefined function.** The brief gives no name, signature, module, export
    or behaviour for empty input.
  - **Scope wording.** Decision 7 says "inside a Python identifier", but the
    motivating names are output column names (`Label.column`,
    `query/_expr.py:1239`; `polars.label`, `polars.py:287, 300-303, 353`) and
    persisted Lance table names.
  - **Unlisted renames.** Adopting the alias renames user-visible columns:
    `name_fr-ca` becomes `name_fr_ca` and `REF_AREA_label_fr-ca` becomes
    `REF_AREA_label_fr_ca`. Neither appears in Migration.
  - **Persisted names.** `_language_slug` already names Lance tables
    (`lance.py:1280`) and `index.json` keys (`lance.py:1051, 1169`). The alias
    must produce byte-identical output for every stored tag, or existing
    indexes are orphaned.
  - **Empty input.** `lance.py:1260` calls the slug on `""`, which a
    normalising alias would refuse.
  - **Reversibility.** "Reversible" holds only when the base name is known:
    `name-en` is a well-formed tag, so `short_name_en` is ambiguous.
  - **The hyphen hint.** Line 138 presents the hint as current behaviour.
    Today's message is generic (`istring.py:73`), so the hint is new work.
* **Rationale & Recommendation:** add this text:
  > `sdmxlib.tag_alias(lang: str) -> str` in `model/istring.py`, exported as
  > `sl.tag_alias`, returns `normalize_tag(lang).replace("-", "_")` and raises
  > as `normalize_tag` does. No public inverse.
  >
  > Adopters: `Label.column` and `projected_name`, the `polars.label` suffix,
  > `Row` attributes, and statcatlib `_language_slug`. Rows with an empty
  > `lang` are refused at ingest.
  >
  > Test: `tag_alias(t) == _language_slug(t)` for every well-formed `t`.

  Restate decision 7 as "every generated name that joins a base name and a
  tag". Add the column renames to Migration. Reword line 138 as a change: "its
  error gains a hyphen suggestion". Write "reversible given the base name".

### M3. The Errors proposal reverses sdmxlib D3 without saying so - Severity: Major
* **Reviewer Lens:** design, zoom-out, codebase-details, comprehension,
  implementation-readiness
* **Affected Scope:** lines 244–246
* **Discrepancy Description:**
  - **What D3 says.** `[]` with a malformed tag raises `KeyError` chained from
    `ValueError`, "so `try/except KeyError` callers keep working"
    (`docs/design/language-tags.md:154`). The code implements it at
    `istring.py:207-210`, and a test asserts it (`test_language_tags.py:469-471`).
  - **What the proposal changes.** `get` and `pick` already raise
    `ValueError`, and `in` already returns `False`. The proposal therefore
    changes only `[]`.
  - **What breaks.** A `ValueError` from `[]` escapes code that catches only
    `KeyError`: `ChainMap`, `str.format_map`, the `Mapping` mixins and generic
    `except KeyError` handlers.
  - **What goes unstated.** For a malformed tag, `in` returns `False` while
    `get` raises. That breaks the usual `Mapping` invariant between the two,
    and the brief does not record it.
* **Rationale & Recommendation:** see the Errors recommendation below. Whatever
  the owner picks, the text must say whether it amends D3.

### M4. The API change has no examples, and references are undefined - Severity: Major
* **Reviewer Lens:** comprehension, style
* **Affected Scope:** lines 27–42, 149, 159–163, 168, 173–179, 223, 236
* **Discrepancy Description:**
  - **No examples.** The brief has no before/after code.
  - **The old `get` is never described.** Line 159 says `s.get("fr", "en")`
    "now returns the default" without stating that PR 308's `get(*langs)` is
    variadic, which makes `"en"` a fallback tag today. The cookbook bullet
    cannot be followed without that fact.
  - **Undefined references:** B2, D3, D7, "statcatlib decision 6", "slices 3
    and 4", "gap list", `_from_normalized`, `_text`, `emit_pair`,
    `copy=False`, "six-lens Goldfish round".
  - **Misread "private".** `_text` is already private (`istring.py:242`), so
    "become private" misreads.
* **Rationale & Recommendation:** add a "Before and after" code block under
  the Overview. It should cover `[]`, `get` with one argument, `get` with two
  arguments, `items()` and `pick`, plus one statcatlib site (`concept.label`
  or `batch_labels`). The comprehension reviewer drafted one.
  - Add one sentence on the old `get(*langs)`.
  - Define each reference inline in one clause, e.g. "D3 in sdmxlib's
    language-tags RFC" and "slice 4: the breaking lookup change".
  - In Raw views, name only `emit_pair` (used at `_dto.py:99`) and
    `as_dict(copy=False)` (used at `_rules.py:213` and
    `sdmx_json/metadata.py:139`).

### M5. The document structure does not fit an RFC - Severity: Major
* **Reviewer Lens:** structural
* **Affected Scope:** whole document
* **Discrepancy Description:**
  - **Repetition.** Each decision appears three times (Overview 29–42, Goals
    187–195, Decisions 209–224), and its reasoning sits about 150 lines away.
  - **Decisions inside the analysis.** Analysis makes decisions that are not
    in the list: "msgspec is chosen" (77), "owner accepts the breakage" (165),
    the `document` rename (182), and `title__lang` argued as settled (131–135).
  - **Proposals cannot be cited.** They are unnumbered.
  - **Migration is filed under Analysis.** It is really a Breaking changes
    section.
  - **Missing sections.** There is no Alternatives considered and no Risks
    section.
  - **Status.** The Status line says "Brainstorm brief".
  - **Review history.** Neither house RFC has such a section.
  - **Template headings.** "Goals vs. Non-Goals" and "Key Decisions & Staging
    for Next Steps".
* **Rationale & Recommendation:** reorder as:
  1. Problem
  2. Goals
  3. Non-goals
  4. Evidence
  5. Decisions D1–D8, each with its reasoning
  6. Proposals P1–P7
  7. Alternatives considered (stored values, `__slots__`/attrs, NamedTuple,
     Rust, `label`/`locale`, variadic `get`)
  8. Risks and mitigations
  9. Breaking changes and migration
  10. Cross-repo contract
  11. Acceptance criteria
  12. Staging

  Also:
  - Turn the Overview into a problem statement.
  - Status: "RFC for team feedback, from an EGM brainstorm (two review rounds;
    nine decisions settled, seven proposals open)", with a separate "Based on"
    line.
  - Fold Review history into Status, with a link to the committed EGM reports.
  - Move decision 9 (a process statement) into Status.

### M6. Some cited facts and line numbers are wrong - Severity: Major
* **Reviewer Lens:** codebase-details, design, comprehension
* **Affected Scope:** lines 22, 87, 95, 100–101, 143, 155, 159–163, 180–182,
  223, 246
* **Discrepancy Description and edits:**
  - **Line 180, search text.** `CodeHit.text` is not `"<name> | <description>"`.
    That form is `ConceptHit.text` (`store.py:1302`, split at 1400–1409). Code
    rows join dataset title, dimension and code labels, altLabels, context and
    footnotes (`store.py:4138-4159`). Edit: "the search `text` column holds a
    composite search document: concept rows are `"<name> | <description>"`
    and code rows join title, dimension and code labels, altLabels, context
    and footnotes."
  - **Line 22.** The IM span is lines 1392–1404 (1385 belongs to `+name`;
    1405 is VersionableArtefact).
  - **Lines 100–101.** Line 3521 is `TextMeasureValue` and 3591 is
    `TextAttributeValue`, the reverse of the brief's order. Both name the
    multilingual collection: line 3951 says the content "may contain the text
    in multiple languages". This bullet therefore supports `Annotation.text`
    more than `LocalisedString.text`. Reword it to "the IM names multilingual
    text values `text`", or drop it.
  - **Line 87.** `LocalisedUri` has no `locale` attribute in the IM table
    (1357–1362). List `LocalisedString`, `LocalisedMemberValue` (5162) and
    `DatePatternMap` (4497).
  - **Line 95.** The Lance `text` column appears both as precedent for `text`
    and as a rename target (line 182). Drop it from the precedent list.
  - **Line 143.** `lance.py:941` should be 942 (the call site is 1202).
    `TextIndex.languages` (1210–1213) also returns slugs.
  - **Line 155.** `store.py:748` (`_istring_to_map`) has 24 callers. Its body
    becomes `s.as_dict()`, and the callers do not change.
  - **Lines 159–163.** `hierarchies.md:105` uses `node.id`. `name.get("en",
    "")` raises only when `en` is absent. Most FREQ and NACE IDs are one
    letter or digit, so they raise `ValueError` instead of returning another
    language's text. Edit: "raises `ValueError` when `en` is absent;
    `name.get("en", code.id)` raises for one-letter IDs and returns another
    language's text for two-letter IDs such as `CA`."
  - **Line 223.** The text that assigns the JSON form to statcatlib is sdmxlib
    Non-goals 39–40 and Cross-repo contract 331–335, as well as D7.
  - **Line 246.** `MissingTranslationError` does not exist yet (statcatlib RFC
    decision 7). Write "will subclass".

### M7. The call-site inventory is incomplete and unsized - Severity: Major
* **Reviewer Lens:** codebase-details, design, zoom-out
* **Affected Scope:** lines 148–163
* **Discrepancy Description:** the inventory misses these sites:
  - **Writer loops:** `formats/sdmx_ml/_header.py:104`,
    `sdmx_ml30/metadata.py:87`, `sdmx_ml/_v3_writer.py:772, 776`,
    `sdmx_ml21/writer.py:155, 159`, `model/_rules.py:148`.
  - **Other sdmxlib code:** `_data_common.py:173` (`_first_text` feeding
    `_parse_iso_duration`).
  - **Docs:** `docs/building_tutorial.md:64` (`name.get("de", "en")  # falls
    back`), the `istring.py:128` docstring, `docs/upgrading.md:41`,
    `docs/cookbook/registry.md:75`.
  - **`isinstance(..., Mapping)` dispatch** that starts to match:
    `query/_expr.py:1064, 1557, 2387`, `model/version_rewrite.py:235`.
    `_canonical.py:87` is safe because its `InternationalString` case comes
    first.
  - **statcatlib:** `store.py:2425, 2544, 2546` and the defaults at
    4126–4128. The four `lang="en"` defaults cited are 4 of about 27.

  Two inventory entries are also mislabelled or unsized:
  - `polars.py:414-486` writes cell values in `structure_frame`'s `concept`
    column. It does not set column names.
  - Round 1 m5 counted 278 test matches across 78 sdmxlib files, and the
    brief gives no size.
* **Rationale & Recommendation:** add the sites, or write "for example" and
  point to the call-site table from B2. Add one size line: "about N sdmxlib
  and M statcatlib source sites; 278 test-file matches."

### M8. Single-repo work makes the suite RFC larger than it needs to be - Severity: Major
* **Reviewer Lens:** zoom-out
* **Affected Scope:** lines 138–144, 171–182, 191–194, "Raw views",
  "Projection columns"
* **Discrepancy Description:** round 1 limited the suite design to the
  cross-repo surface (`brainstorm-round1.md:435-437`). These items each belong
  to one repo:
  - `Hit.lang` and the `lang="en"` defaults (statcatlib RFC decisions 4 and
    12);
  - the search `document` rename, which affects a persisted Lance column and
    needs a `_MANIFEST_VERSION` decision;
  - the `_language_slug` filter bug;
  - making `emit_pair`/`copy=False` private (statcatlib uses neither);
  - the hint in `normalize_tag`'s error message;
  - the benchmark implementation.

  The "written naming rule" goal duplicates sdmxlib
  `docs/design/query-naming.md`, which already has an "IM name or transparent
  abbreviation" rule and a table of deviations.
* **Rationale & Recommendation:**
  - Cut "### statcatlib" bullets 2–3 and move them to statcatlib handoff
    issues.
  - Replace the naming-rule goal with "sdmxlib handoff: extend
    `docs/design/query-naming.md` with the model rule and its deviations".
    The deviations are `conceptIdentity`→`concept`,
    `localRepresentation`→`representation`, `locale`→`lang`, and
    `label`/`locale`→`text`/`lang`, plus the British-spelling rule.
  - Add the line: "Implementation, fast paths, benchmarks and statcatlib
    search details go to the Staging handoff issues."

### M9. The JSON form depends on which encoder writes it - Severity: Major
* **Reviewer Lens:** implementation-readiness
* **Affected Scope:** line 78, decision 8, Goals line 195
* **Discrepancy Description:**
  - **Producers.** Only msgspec encodes a Struct natively. statcatlib
    serialises with stdlib `json.dumps` (in `store/store.py`, `store/lance.py`
    and `model/dataset.py`), which raises `TypeError` on a Struct. statcatlib
    has no direct msgspec dependency.
  - **Field order.** msgspec writes fields in declaration order (`text`, then
    `lang`). `_canonical.py:50` uses `order="sorted"`, which would write `lang`
    first.
* **Rationale & Recommendation:** add to decision 8:
  > The suite form is produced by `msgspec.json.encode(value)` or
  > `msgspec.structs.asdict(value)`; statcatlib serialises labels through one
  > of these. A test in each repo asserts the exact bytes
  > `{"text":"Population","lang":"en"}`.

  State whether key order is part of the contract.

### M10. Polars and DSL outputs are underspecified - Severity: Major
* **Reviewer Lens:** implementation-readiness, comprehension, design
* **Affected Scope:** "Query DSL", "Projection columns", line 152
* **Discrepancy Description:** the brief does not say:
  - what dtype `structure_frame`'s `concept` column has;
  - whether `Label` stays VARCHAR;
  - whether sdmxlib's DSL or `polars.label` ever emits a `__lang` column;
  - what a `Row` attribute or `.frame()` cell holds.

  `query/accessors.py:598` may promise that model and query "mean the same".
  The design reviewer found that `_compile.py:257` compares DSL with DSL and
  is correct as written.
* **Rationale & Recommendation:** add this text:
  > `structure_frame` reads `.text`; its `concept` column stays `pl.String`. A
  > projected DSL `Label` stays VARCHAR, and sdmxlib's DSL and `polars.label`
  > emit no `__lang` column. `title__lang` is statcatlib-only and holds
  > `LocalisedString.lang`.

  Check `accessors.py:598` in the sdmxlib handoff.

### M11. Some passages break the house writing rules - Severity: Major
* **Reviewer Lens:** style
* **Affected Scope:** lines 1, 7–13, 23, 51, 70, 107–109, 224, 247, 254
* **Discrepancy Description:**
  - **Issue references.** GitHub references use "PR 308", "PR 90" and
    "StatCat-Suite/statcat-suite.github.io#12" instead of `GH-N`. Line 203
    already uses "statcatlib GH-88".
  - **Title.** The title's colon introduces a description where the rule
    expects a work item.
  - **Framing by absence.** Lines 107–109 frame the point by what other
    libraries lack.

  The brief passes `tools/check_prose.py`. Its prose spelling (British prose,
  American identifiers) matches both repos.
* **Rationale & Recommendation:**
  - Write "sdmxlib GH-308", "statcatlib GH-90" and "statcat-suite.github.io
    GH-12".
  - Retitle as "Text model: add LocalisedString per the SDMX Information
    Model".
  - Rewrite lines 107–109 as "sdmx1 stores localised text as a dict named
    `localizations`, with no per-string class. pysdmx's Fusion-JSON string
    uses `{locale, value}`."

---

## Minor

1. **Line 37 and decision 4.** The second clause, "none returns `str`",
   restates the first in negative form. Delete it. B4 supersedes this.
2. **Lines 55–59.** Split the sentence. Replace "pays back" with "is cheaper
   only when each string is looked up four or more times".
3. **Line 77.** "costs 17% per call" needs its comparison: "adds 13 ns (17%)
   per `get()` over `str`".
4. **Line 96.** "reads better" is subjective. Write "replaces IM attribute
   names with shorter or wire names".
5. **Line 102.** "would stutter" is figurative. Show
   `concept.label["en"].label` instead.
6. **Line 121.** "The docs note it" has no antecedent. Name the doc and the
   statement.
7. **Lines 148–149 and 176.** Both are in negative form. Write "most keep
   running with different results" and "Some `lang` values are unnormalised".
8. **Line 157.** Make it conditional: "unless P1 (Truthiness) is accepted".
9. **Line 182.** The rename has no object. Name the column and the field.
   M8 moves this item out of the brief.
10. **Lines 113–114.** `sl.LocalizedString` raises `AttributeError`, and the
    `from` import raises `ImportError`. Say there is no alias, and say why:
    `LocalizedText` was never released.
11. **Alias rationale.** The four-letter `lang` tag is reserved by RFC 5646,
    so the `title_lang` collision is improbable. Give persistence as the main
    reason (Lance table names) and `search_fr_ca__000003` as precedent for
    `__`.
12. **Equality.** Equality includes `lang` (`fr` ≠ `fr-ca`), so state it.
    msgspec's `order=False` makes `sorted(values)` raise; give
    `key=attrgetter("text")`. State that `s["en"] is s["en"]` is false and
    that `cache_hash` is off.
13. **`InternationalString.__repr__`.** It prints `en-t-fr='...'`, which is
    not valid Python (round 1 m3). Decide the repr in this change.
14. **Naming clash.** sdmxlib already has query classes `Localised` and
    `SideLocalised` (`query/accessors.py:76-79`). Mention them, and the
    sentence that tells them apart from `LocalisedString`.
15. **`MissingTranslationError` message.** A `KeyError` subclass repr-quotes
    its message, so override `__str__`. Consider an sdmxlib base class that
    statcatlib subclasses.
16. **Hub fallback.** Say where the RFC lives if statcat-suite.github.io
    GH-12 is still open when Stage 3 starts.
17. **Headings and labels.** Use "Goals" and "Non-goals". Format decision
    labels one way (`**Label.**`). Use one bullet marker. Drop "In-Scope" and
    "Out-of-Scope". Replace "lazy storage" (262) with "values built on lookup".
18. **Cap jump.** statcatlib's cap is `<0.73` (`pyproject.toml:37`) and sdmxlib
    is at 0.78.0. The cap-raising PR crosses breaking minors 0.73–0.78, so say
    so in Staging.

---

## Recommendations on the "Proposed" items

**P1 Truthiness: accept, with a benchmark condition.** Four of the five
reviewers who addressed it accept. With `bool(v) == bool(v.text)`, `x or
fallback` behaves exactly as it does today with `str | None`. Empty text is
real data: `scopes.py:999, 1054`, and FMR's 498,786 codes named `""`
(`_rules.py:141-145`).

The design reviewer dissents on cost: a Python-level `__bool__` adds a call to
every `if v:`. Add a benchmark row for truthiness, and accept only if the
lookup-plus-truthiness ratio stays under the gate. Document two things:
- `pick` still returns a held empty text, so `pick("fr", "en") or x` falls to
  `x` when `fr` is `""`, as `get("fr", "en") or x` does today;
- the presence tests are `in` and `is not None`.

Separately, statcatlib should build `InternationalString()` instead of
`InternationalString(en="")` at `scopes.py:999, 1054`.

**P2 `str` interop: accept.**
- `__str__` returns `self.text`.
- `__format__` must be defined explicitly as `format(self.text, spec)`.
  `object.__format__` raises on a non-empty format spec.
- `repr` stays the generated struct repr, and `== "Annuel"` stays `False`, as
  with `pathlib.Path`.
- Add `== "`, `in (` and `in [` against lookup results to the call-site audit
  (B2). Do not rely on pyrefly here.
- Real `str` sinks (lxml `.text =`, `.encode()`, Polars names) still fail
  loudly.

**P3 Raw views: accept, rescoped.** `as_dict() -> dict[str, str]` stays public,
and B4's rewording of decision 4 covers it. statcatlib's `store.py:748` moves
to it. Making `emit_pair` and `as_dict(copy=False)` private is sdmxlib-internal,
so move it to the sdmxlib handoff and name the private replacement. Drop `_text`
from the list, since it is already private.

**P4 Query DSL: accept.** Projected columns hold text, and the model returns
`LocalisedString`. Say so in the query tutorial and `upgrading.md`. Add the
`Label.column` alias rename to Migration (M2).

**P5 Projection columns: accept the rule here and move the column list to
statcatlib.** The suite contract keeps two parts: `__` is the separator for
non-tag suffixes, and per-language columns use the alias (`title_fr_ca`). The
names `title`/`title__lang` go to statcatlib slice 4, recorded as superseding
the statcatlib RFC's `title_lang` (RFC lines 99, 214). State that sdmxlib emits
no `__lang` column.

**P6 Errors: amend, and keep D3's guarantee.**
- `[]` with a malformed tag raises `InvalidTagError(KeyError, ValueError)`,
  chained from the `normalize_tag` error. This keeps `except KeyError`,
  `ChainMap`, the `Mapping` mixins and `test_language_tags.py:469-471` working,
  and also satisfies `pytest.raises(ValueError)`.
- `get` and `pick` raise the same class, which is a `ValueError`, as today.
- `in` returns `False`. Record that `in` is the one non-raising probe and that
  `get` departs from `Mapping.get` for malformed tags.
- A missing tag raises a `KeyError` subclass that names the requested and held
  tags. statcatlib's `MissingTranslationError` subclasses it.
- If the owner prefers a plain `ValueError` from `[]`, the brief must say that
  it amends D3 (`language-tags.md:154`, lines 307–309) and the test.

**P7 Sequencing: accept with changes.**
- Rename inside PR 308. It is unreleased, so no deprecated `LocalizedText`
  ships.
- Move to msgspec in PR 308 only after B1 is decided.
- Drop "same minor", or declare an explicit sdmxlib release hold (sdmxlib cut
  four releases in two days). statcatlib needs only a release that contains
  both PRs.
- Fix the slice mismatch:
  - either slice 3 keeps statcatlib's public API on `str` through
    `.text`/`as_dict()` and slice 4 exposes `LocalisedString`,
  - or the two slices merge.
- Add Stage 0 (amend PR 90) and decouple PR 308 from the hub (B5).

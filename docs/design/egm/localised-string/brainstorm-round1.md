# LocalisedString: EGM brainstorm, round 1

* **Date:** 2026-10-30
* **Mode:** BRAINSTORM
* **Reviewers:** egm-design, egm-codebase-details, egm-zoom-out,
  egm-comprehension, egm-implementation-readiness, egm-structural (one
  instance each)
* **Concept:** `InternationalString` presents `Mapping[tag, LocalisedString]`
  with `LocalisedString(label, locale)`. Every lookup returns a
  `LocalisedString` and no lookup returns `str`. Storage stays
  `dict[tag, str]` and values are built on lookup.

Unless a path says otherwise, sdmxlib paths are under
`../sdmxlib/src/sdmxlib/` and statcatlib paths are under
`../statcatlib/src/statcatlib/`. "Notes" means
`localised-string-notes.md`, and "bench" means
`bench_istring.py`. The synthesizer checked these lines itself:
`istring.py:92, 116, 213, 225, 242, 273, 277, 294`.

## Summary

All six reviewers accept two parts of the concept: lazy storage
(`dict[tag, str]`, with values built on lookup) and IM names on the value
class. They object to three other parts, which they say need decisions:

1. **`get(*langs)` against `Mapping`.** The concept makes the class a
   `Mapping`, but `get` is variadic over tags. Four of the six reviewers rank
   this Blocking.
2. **Lookups that return objects.** Most current call sites that use the
   result as `str` would break without an error: `or` fallbacks, f-strings,
   `== "text"`, Polars column names and JSON entries. The zoom-out reviewer
   argues the IM does not require this change and that it costs the most.
3. **The `label`/`locale` names.** They reopen the agreed GH-88 JSON form
   `{"text","lang"}`, collide with about 13 statcatlib fields already named
   `label`, and invite POSIX `fr_CA`.

The benchmark does not measure the class PR 308 ships, so its lookup figures
are low. Five reviewers say the same about sequencing: rename the unreleased
`LocalizedText` inside PR 308, and put any return-type change in a separate PR.

## Blocking

### B1. `get(*langs)` conflicts with `Mapping.get(key, default=None)`

* **Lenses:** design, codebase-details, implementation-readiness,
  comprehension
* **Evidence:**
  * `istring.py:213`: `def get(self, *langs: str) -> str | None`.
  * `istring.py:116`: the class does not subclass or register `Mapping`
    today.
  * `istring.py:273`: `items()` returns an `Iterator`, not an `ItemsView`.
    There is no `values()` or `keys()`.
* **What goes wrong:**
  * Generic `Mapping` code reads `s.get("fr", "en")` as "`fr`, with the
    string `en` as the default".
  * `s.get(k, None)` reaches `normalize_tag(None)` and raises `TypeError`.
  * pyrefly reports the override as incompatible.
* **The docs already misuse it:**
  * `.get("en", "")` appears in `docs/cookbook/catalog.md:20`,
    `registry.md:75` and `resolution.md:48`. Under PR 308, `""` raises
    `ValueError`.
  * `.get("en", code.id)` appears in `docs/cookbook/hierarchies.md:105` and
    `inspecting.md:97`. A code ID such as `FR` or `CA` is a well-formed tag,
    so this returns French or Catalan text instead of the ID.
* **Proposed resolution (design, readiness):** pick one of these.
  * Make `get(tag, default=None)` follow `Mapping`. It takes one tag, and an
    absent or malformed tag returns `default`. `pick(*tags)` becomes the only
    fallback-over-tags lookup.
  * Do not subclass or register `Mapping`, keep variadic `get`, and drop the
    `Mapping` claim from the concept.

  Either way, fix the five doc sites.

### B2. An object-valued lookup changes behaviour at most current call sites, and most of the changes raise no error

* **Lenses:** all six
* **Unchanged:** about 10 sdmxlib sites, because they read through the
  str-valued internals:
  * `_text`: `codelist.py:577`, `valuelist.py:89`, `datastructure.py:956`
  * `as_dict` or `emit_pair`: `_rules.py:213`, `sdmx_json/_dto.py:99`,
    `sdmx_json/metadata.py:139`, `convert.py:155, 186`, `storage/writers.py:87`,
    `bundle/_overlay.py:492`
* **Wrong output with no error:**
  * `polars.py:414, 433, 449, 467, 486`: `name.get(lang) or dim.id` becomes a
    Polars column name.
  * `formats/sdmx_json/_data_common.py:181, 386, 441, 776-788`: the value is
    put into JSON entries. `dict(name_attr.items())` feeds JSON.
  * `bundle/_canonical.py:82`: `dict(value.items())` feeds the canonical
    bundle bytes.
* **Writer loops over `items()` that break:**
  * `formats/sdmx_ml/_common.py:1792, 1839`
  * `sdmx_ml/_header.py:104`
  * `sdmx_ml30/metadata.py:87`
  * `storage/writers.py:291, 347`
  * `_rules.py:148`: it calls `text.strip()`.
  * `_data_common.py:173`
* **statcatlib:**
  * `store/store.py:748` builds `{lang: s[lang] for lang in s}` as a DuckDB
    MAP parameter, and about 25 callers use it.
  * `store/store.py:1162, 1171`: `.encode()` and `+=` on the result.
  * `sources/sdmx.py:115`: truthiness.
* **Behaviour that changes:**
  * `== "Annual"` returns `False`.
  * An f-string prints the repr.
  * `sorted` and `json.dumps` raise `TypeError`.
  * `x or fallback` stops falling back for an empty text, because a
    `__slots__` object or a 2-tuple is always truthy. statcatlib does store
    `""`, at `store/scopes.py:999, 1054`.
* **Proposed resolution:** two positions, for the owner to choose between
  (see D1).
  * **Keep the change** (design, readiness, codebase-details):
    * Give the value no `__str__` shortcut.
    * Gate the migration with a strict pyrefly pass plus a grep audit.
    * Move hot loops to `as_dict(copy=False)` or `_text`.
    * Fix `store.py:748` with `s.as_dict()`, which is also faster.
    * Add a golden test for `_canonical.py`.
  * **Narrow the change** (zoom-out):
    * Keep `__getitem__ -> str` and `get -> str | None`.
    * Make `pick()` the IM-typed entry point.
    * Optionally add an iterator that yields `LocalisedString`.

    This keeps the IM names with no break across roughly 400 sites.

## Major

### M1. The benchmark does not measure the class PR 308 ships

* **Lenses:** codebase-details, design, zoom-out, implementation-readiness,
  structural
* **What it skips:**
  * bench `LSAttrs` (lines 21-24) has no converter. The real
    `LocalizedText.lang` has `field(converter=normalize_tag)`
    (`istring.py:92`).
  * The bench does not normalise the requested tag. Real `get` and `pick` do
    (`istring.py:220, 236`).
  * The `Mapping` mixin `values()` and `items()` call `__getitem__` once per
    key, which adds one more normalisation per entry.
* **Effect:** each lookup normalises twice and runs attrs `__init__`. The
  "half the build time" claim compares lazy against eager storage. It does
  not compare the proposal against today's `get() -> str`, which allocates
  nothing.
* **What it leaves out:** parse (`_normalized`), the serialise paths, the
  data-writer per-code loop (`_data_common.py:441`), `sl.polars.label`, and
  a `msgspec.Struct(frozen=True, gc=False)` candidate. msgspec is already a
  dependency.
* **Small corrections:**
  * Memory saving is 26-34% depending on the eager variant, not "about 35%".
  * `DatePatternMap.locale` is at `model/mapping.py:497`, not `:483`.
  * The IM's `LocalisedUri` (IM l.1357-1362) has no `locale` attribute.
  * Parameter counts are about 29 in sdmxlib and 44 in statcatlib, not 34
    and 56.
* **Resolution:**
  * Add a private unchecked constructor for values whose tag is already
    normalised.
  * Override `keys`, `values` and `items` to read `_data` directly.
  * Re-benchmark the real class against today's `get`.
  * Commit the script to sdmxlib's `tests/bench/`. The scratchpad copy will
    not last.
  * Set numeric gates:
    * The `tests/bench/test_bundle_reads.py` call-count bounds stay
      unchanged.
    * `test_parse` and `test_serialize` stay within noise.
    * A new lookup-loop bench stays under a stated budget, for example at
      most 1.3x today's `get`.

### M2. The fast paths contradict "no str shortcut"

* **Lenses:** design, implementation-readiness, zoom-out, codebase-details
* **Evidence:** these return `str` or `dict[str, str]`:
  * `_text`: `istring.py:242`
  * `as_dict`: `istring.py:277`
  * `emit_pair`: `istring.py:294`

  The parse, store-read and serialise paths go through them and make no
  public lookups. The `EMPTY` comment (`istring.py:139-145`) depends on
  callers of `copy=False` and `emit_pair` not mutating the result.
* **Effect:** sdmxlib keeps a `str` shortcut privately. statcatlib cannot use
  private API, so it pays one allocation per lookup.
* **Resolution:**
  * Restate the rule as "no single-label str shortcut in the public lookup
    API".
  * Keep `as_dict()` public as the raw bulk view. Optionally rename it
    `texts()`.
  * Make `emit_pair` and `as_dict(copy=False)` private.
  * Decide whether `_text` goes public. The Polars and data-writer fixes want
    it, and statcatlib's batch paths would too.

### M3. `label`/`locale` names reopen an agreed contract and collide with existing names

* **Lenses:** comprehension, codebase-details, design, zoom-out, structural,
  implementation-readiness
* **The agreed form:** `{"text","lang"}`, recorded in:
  * statcatlib RFC decision 14
    (`../statcatlib/docs/design/language-tags.md:201-209`)
  * sdmxlib design D7 and l.321-337
    (`../sdmxlib/docs/design/language-tags.md:195-208`)
  * GH-88
  * commit f443534
* **Where "label" already appears:**
  * statcatlib fields: `model/skos.py:57, 79, 93, 125`, `dataset.py:131`,
    `quality.py:19, 30`, `licence.py:17`, `spatial.py:17`,
    `temporal.py:20, 33`, `classification.py:18`. These produce
    `concept.label["en"].label`.
  * sdmxlib's query expression `Label` (`query/_expr.py:1209, 1347`) and
    `sl.polars.label`.
* **Problems with "label" and "locale":**
  * `.label` reads oddly on descriptions and annotation texts. The IM itself
    uses `text` for "the localised text values" (`TextAttributeValue`, IM
    l.3521).
  * Python's `locale` module and Babel use POSIX `fr_CA`, which
    `normalize_tag` refuses (`istring.py:56`).
  * The IM's `DatePatternMap.locale` (IM l.4497) is an unvalidated
    `xs:string`, so in sdmxlib one attribute name would carry two contracts.
* **Resolution options:**
  * (a) Use `label`/`locale` everywhere, including JSON. This reopens GH-88.
  * (b) Use `label`/`locale` in Python and keep the JSON as `{"text","lang"}`,
    with the mapping stated once in both docs.
  * (c) Take the IM name for the class only, `LocalisedString(text, lang)`.

  The design reviewer prefers (a). Zoom-out prefers (b). Comprehension
  prefers (c).

  Under any option:
  * Keep the `lang=`/`langs=` parameters.
  * Make the `normalize_tag` error suggest `fr-ca` when it sees `_`.

### M4. `lang` parameters, model fields and IM URI classes

* **Lenses:** all six
* **Evidence:**
  * Wire spellings are `xml:lang`, SDMX-JSON `lang` and `Accept-Language`
    (notes l.26-37).
  * sdmxlib design D3's enumeration test is keyed on parameter names
    `lang`/`langs` (sdmxlib design l.138).
  * `AnnotationURL.lang` (`model/annotations.py:35`) is optional (`None` means
    not localised) and persisted:
    * `convert.py:100, 162, 261` serialise and read the `"lang"` key.
    * `storage/writers.py:344` writes it to the store.
* **Resolution:** all six reviewers agree:
  * Keep `lang=`/`langs=` on about 29 sdmxlib and 44 statcatlib parameters.
  * Leave `AnnotationURL.lang` and `RegionValue.lang`
    (`model/constraint.py:149`) alone. Renaming them changes a persisted key
    and a store column, and still falls short of IM fidelity.
  * Record `InternationalUri`, `LocalisedUri`, `LocalisedMemberValue` and
    `TextAttributeValue` as non-goals. Open a separate issue if a reader ever
    loses data without them.

### M5. Choose the value type on corrected numbers

* **Lenses:** design, implementation-readiness, codebase-details, structural
* **NamedTuple:** reject it.
  * It equals the plain tuple `("a","en")`, unpacks, has length 2 and is
    always truthy.
  * `json` and msgspec encode it as an array, which breaks the agreed object
    form.
* **Plain `__slots__` class:**
  * It needs hand-written `__eq__`, `__hash__`, `__repr__` and
    `__match_args__`.
  * A `__setattr__` guard slows `__init__` again, unless a private factory
    builds the object with `object.__new__`.
* **attrs `@frozen`:**
  * Without the converter on the lazy path it gives eq, hash and
    `__match_args__`.
  * It needs an encoder hook for JSON.
* **msgspec `Struct`:** not measured. It gives eq, hash and `__match_args__`,
  and JSON object encoding.
* **Decisions to state whichever type is chosen:**
  * `__bool__`: always true, or `bool(label)`. See D3.
  * Equality with `str`: return `False` (the default), or raise.
    Comprehension asks for raise.
  * `__str__`/`__format__`: comprehension wants them to return the label so
    `print` keeps working. Design and readiness want no override, so misuse
    shows in review.
  * Ordering.
  * Identity: `s["en"] is s["en"]` is false. Document it.

### M6. The query DSL and the model diverge on `name["en"]`

* **Lenses:** design, codebase-details, implementation-readiness,
  comprehension
* **Evidence:**
  * `query/_compile.py:257` and `accessors.py:598` say `q.code.name["en"]`
    "read[s] the same and mean[s] the same" as the model. That expression
    compiles to a VARCHAR column.
  * The tutorials teach both forms side by side
    (`docs/cookbook/structures_as_frames.md:87`).
* **Resolution:**
  * Either document the difference (a query returns a column of text, the
    model returns a value with its tag) in `upgrading.md` and the query
    tutorial, or add a struct `{label, locale}` accessor to the DSL.
  * Decide before the rename. Fix the two docstrings either way.

### M7. Error messages for a missing or malformed tag

* **Lens:** comprehension
* **Evidence:**
  * `istring.py:207-211` raises a bare `KeyError('de')` for a missing tag.
  * The same lines raise `KeyError('fr_CA')`, chained from a `ValueError`,
    for a malformed tag. A newcomer reads that as "no French text".
  * `pick()` with no arguments returns `None`.
  * `s.pick("fr","en").label` fails with `'NoneType' has no attribute`, and
    this becomes common once `.label` is mandatory.
* **Resolution:**
  * Raise a `KeyError` subclass that names the requested tag and the tags
    held. For an underscore tag, suggest the hyphen form.
  * Align this error with statcatlib's `MissingTranslationError` (RFC
    decision 7).
  * Make an empty `pick()` raise `TypeError`.
  * Document exact-match ordered preference, and show the `or` idiom or add
    `default=`.

### M8. Documents: rewrite D7 inside PR 308 and give each fact one owner

* **Lenses:** structural, zoom-out, design, implementation-readiness
* **Evidence:** `LocalizedText` exists only in unmerged PR 308, yet these
  documents already describe it:
  * sdmxlib design D7 (`docs/design/language-tags.md:195-208`)
  * `docs/upgrading.md:33, 52-54`
  * `src/sdmxlib/model/EGM.md:94, 119`

  statcatlib decision 14 restates sdmxlib internals ("attrs frozen class"),
  which is stale if the type changes.
* **Resolution:**
  * Rewrite D7 in place before merge. Add `LocalizedText(text, lang)` to
    Alternatives considered (l.259-278).
  * Update `upgrading.md` and `EGM.md` in the same PR.
  * In statcatlib, decision 14 links to D7 and keeps only the JSON form.
    Update finding 8, finding 12 and slices 3-4.
  * Post a GH-88 comment that supersedes the earlier one.
  * Fallback if PR 308 merges first: add D8 and mark D7 "Superseded by D8".

  statcatlib's `docs/design/SITEMAP.md:4-6` already places cross-repo designs
  in sdmxlib, so this needs no suite-level document.

### M9. Sequencing and the statcatlib cap

* **Lenses:** implementation-readiness, design, zoom-out, structural
* **Evidence:**
  * PR 308 is unreleased. The CHANGELOG top entry is 0.78.0.
  * House policy is a clean break with no shims (`docs/upgrading.md:6-9`).
  * statcatlib pins `sdmxlib>=0.72.0,<0.73`
    (`../statcatlib/pyproject.toml:35-37`), so the
    slice-3 PR already crosses six breaking minors.
  * Storage and `SCHEMA_VERSION` are unchanged, so no catalog rebuild follows
    from this change.
* **Resolution:** five reviewers agree on this order:
  1. Inside PR 308: rename the class and fields, and add the unchecked
     private constructor.
  2. A separate PR, if D1 keeps the change: lookup return types, `get` and
     `Mapping` conformance, privatising the fast paths, and lookup call-count
     bounds. Ship it in the same sdmxlib minor if possible, so statcatlib
     absorbs both in its one cap-raising PR.

## Minor

* **m1. Spelling.** Public identifiers mostly use -ize: `normalize_tag`,
  `LocalizedText`, the `localized_text` table, `serialize`. Exceptions use
  -ise: the `Localised` query class (`query/_expr.py:1346`) and
  `check_serialisable`. `LocalisedString` beside `normalize_tag` invites
  `sl.LocalizedString` and an `AttributeError`. Write a rule ("IM class names
  keep the IM spelling"). Optionally add a module `__getattr__` that explains
  the spelling.
* **m2. "Follows the IM" overstates it.** The IM says "a collection of
  Localised Strings" (IM l.1392-1395). A `Mapping` keyed by tag, whose
  iteration yields tags, is a Python choice. Describe it as "IM names for
  classes and attributes, Python mapping protocol for access" (design).
* **m3. `InternationalString.__repr__`** prints `en-t-fr='...'`, which is
  invalid Python (statcatlib RFC, smaller points). Fix it while repr is being
  redefined.
* **m4. Rust.** All reviewers agree to leave it out of scope. A PyO3 value
  still allocates one Python object per lookup, so it does not remove the
  measured cost (notes l.83-91). The candidates worth a separate study are
  native parsers and Arrow-held labels with objects built only on lookup.
  Move the notes section to Alternatives considered.
* **m5. Test churn.** 278 matches across 78 sdmxlib test files. Many are
  query-DSL expressions, which do not change. The split was not measured.
* **m6. Stale statcatlib doc.** `docs/api/model.md:577` says "or fallback if
  configured", which contradicts "no default language".
* **m7. `as_dict(copy=False)`.** The bench's `values()` builds a list and
  `tracemalloc` measures build only. Say so beside the numbers.

## Effect on statcatlib's open questions (owner question 4)

* **Projection columns `title` + `title_lang`:** they fit a value split into
  two columns. Use `title_locale` only if the attribute becomes `locale`.
  Keep the suffix and the attribute in one vocabulary.
* **`.values()` return type:** under the concept it is
  `ValuesView[LocalisedString]`. This is the one place eager storage wins
  (0.221 s lazy against 0.052 s eager per million in the notes). Bulk
  projections should read `as_dict()`.
* **`batch_labels`:** `dict[code, LocalisedString | None]` plus the gap list,
  which matches decision 8. Under the zoom-out alternative it stays `str`.
* **Gap reporting:** unaffected.
* **JSON form:** see M3.
* **Single result type:** a single `LocalisedString` type does make
  statcatlib's "labels carry the matched tag" (decision 6) uniform. It does
  not settle finding 12's `Row` / `.scalars()` `str` promises. Slice 4 still
  decides those.

## Handoff to sdmxlib's EGM agent (owner question 5)

Send a revision of D7 in `docs/design/language-tags.md`, with an sdmxlib issue
that links it. Do not send a new RFC. Mirror the existing headings:

1. **Problem:** IM alignment, and D7's divergence from SDMX 3.1 Section 2.
2. **Status of D7:** never released. The files that change are
   `upgrading.md`, `model/EGM.md`, `istring.py` and
   `tests/unit/test_language_tags.py`.
3. **Decisions D7'a-e:**
   * names and attributes
   * `Mapping` protocol and `get`
   * value type and its eq, hash, bool, str and JSON rules
   * the unchecked internal constructor
   * the `lang` parameter policy
4. **Non-goals:** IM URI and member-value classes, parameter renames, the
   JSON form (statcatlib owns it), Rust.
5. **Evidence:** the IM audit table with line references, and the corrected
   benchmark committed with its Python version.
6. **Acceptance criteria:**
   * `Mapping` conformance, if chosen.
   * A counted test that lookup never re-normalises a stored tag.
   * Value equality and hash.
   * `EMPTY` still shared safely (`test_istring_empty_is_shared.py`).
   * pyrefly clean.
   * Every grep-listed call site fixed.
   * A golden canonical-bundle test.
7. **Perf gates:** the numbers from M1.
8. **Migration table:** old to new for `__getitem__`, `get`, `pick`,
   `items`, `values`, `__iter__`, `langs`, `of`, `_from_normalized`,
   `as_dict`, `emit_pair`, `EMPTY` and `LocalizedText`, with a
   Breaking/Additive column.
9. **Cross-repo updates:** statcatlib decision 14, finding 8, finding 12,
   slices 3-4, and GH-88.

The suite-level design fixes only the cross-repo surface: names, the JSON
form, lookup semantics and error types. sdmxlib's EGM run owns the
implementation, the fast paths, the benchmarks and the DSL decision (M6).

## Decisions for the owner

1. **D1. Scope of IM conformance.**
   * (a) Names only: rename the class and fields, and `pick` returns
     `LocalisedString`.
   * (b) Every public lookup returns `LocalisedString`, as in the concept.
2. **D2. `get` and `Mapping`.** Make `get(tag, default=None)` follow
   `Mapping` and keep `pick(*tags)` for fallback, or keep variadic `get` and
   do not claim `Mapping`. Also decide whether to keep both `get` and `pick`.
3. **D3. Empty text.** Does an empty label count as present? Is
   `bool(LocalisedString)` equal to `bool(label)`?
4. **D4. Attribute names.** `label`/`locale` (IM) or `text`/`lang` (wire,
   JSON, parameters).
5. **D5. JSON form.** Keep `{"text","lang"}` or change it to
   `{"label","locale"}` (amend GH-88).
6. **D6. Value type.** attrs frozen, msgspec Struct or `__slots__`, chosen on
   the corrected benchmark. NamedTuple is rejected.
7. **D7. `str` interop on the value.** Should `__str__`/`__format__` return
   the label? Should `== "text"` return `False` or raise? Is ordering defined?
8. **D8. Raw views.** Does `as_dict()` stay public, or is it renamed? Does
   `_text` become public? Do `emit_pair` and `copy=False` become private?
9. **D9. Query DSL asymmetry.** Document it, or add a struct accessor.
10. **D10. Parameters and fields.** Keep `lang=`/`langs=` and
    `AnnotationURL.lang` / `RegionValue.lang` (all six reviewers recommend
    keeping them), or rename them.
11. **D11. Projection column suffix.** `title_lang` or `title_locale`. It
    follows D4.
12. **D12. Spelling rule** for IM-derived class names.
13. **D13. Sequencing.** Rename inside PR 308, then a second PR in the same
    minor (recommended), or put both in PR 308.
14. **D14. Error type.** A shared `KeyError` subclass with
    `MissingTranslationError`, and its wording.
15. **D15. Non-goals.** Record Rust and the IM URI and member-value classes
    as out of scope.

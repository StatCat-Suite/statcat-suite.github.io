# Goldfish Review Report, round 2 (changed parts)

**Target:** `concepts_brief.md`. Scope: lines 58–119 (Before and after, Public API), D6 (177–198), D7 (200–223), D11 (260–276), D12–D14 (278–295), Acceptance criteria (403–423) and Staging (425–442), plus their consistency with the rest of the document.

**Reviewers:** `egm-design`, `egm-implementation-readiness`, `egm-comprehension` and `egm-codebase-details`, one instance each, all in REVIEW mode and read-only. Findings that `final-review.md` raised and the current text has fixed are not repeated.

**Commits read**

| Repository | Ref | Commit |
|---|---|---|
| sdmxlib | `feat/gh-280-language-tags` | `99559276d71f02f2c606cf23c954928645018995` (matches `9955927`) |
| statcatlib | `docs/gh-88-lowercase-tags` | `9ff6ddd260b20f2e72e1dfbd82dbac0fad98083a` |
| statcatlib | `main` | `4d4eebe02791484334dca1e88123d324edaf8806` |

Environment: msgspec 0.22.0 in sdmxlib's `.venv`, CPython 3.14.8 `_collections_abc.py`, sdmxlib `pyproject.toml` version 0.78.0.

Limits on what was verified:
- No reviewer could run code. msgspec and stdlib behaviour was read from source and docstrings.
- Nobody confirmed with git that the working trees are clean.

**Counts after deduplication:** 4 Blocking, 15 Major, 22 Minor.

---

## Blocking

### B1. Stage 1 needs `InvalidTagError`, which Stage 2 introduces, and the stage gates cannot be met
* **Reviewer lens:** design (B1), implementation-readiness (B2, M5)
* **Affected scope:** D6 line 185, D14 lines 291–295, Acceptance 403–423, Staging 430–434
* **Discrepancy:**
  - **The error class arrives a stage late.** D6 is in Stage 1 (#308), and its `__post_init__` raises `InvalidTagError`. That class is defined in D7, which is Stage 2. Today the `_refuses` test (`test_language_tags.py:453-455`) expects `ValueError`.
  - **Stage 1's gate names a category that does not exist.** It reads "Equality, validation and JSON criteria pass", but no criterion is labelled "validation".
  - **Stage 1's JSON criterion cannot run in statcatlib.** It is "asserted in both repositories", and statcatlib cannot import `LocalisedString` until Stage 4.
  - **Stage 2's gate ("All acceptance criteria pass") includes three statcatlib-only criteria:**
    - `tag_alias(t) == _language_slug(t)`. `_language_slug` is private statcatlib code (`lance.py:211-219`).
    - "Every statcatlib `lang` / `langs` parameter refuses a malformed tag".
    - The statcatlib half of the JSON bytes test.
  - **Stage 5's gate ("statcatlib criteria pass") is undefined.**
* **Edit:**
  - In the Stage 1 Content cell, after "D6", add: "and `InvalidTagError(ValueError, KeyError)` (D7, first bullet) as the error `LocalisedString.__post_init__` raises; the `InternationalString` rows of D7 stay in Stage 2". Add the same to D14.
  - Turn Acceptance criteria into a table with the columns Criterion | Repository | Stage | Test (`file::name`) | Runs in. Move these rows to statcatlib Stage 4/5:
    - the statcatlib half of the JSON bytes test;
    - `tag_alias == _language_slug`;
    - the statcatlib `lang` / `langs` parameter criterion.
  - Change each Done-when cell to "the criteria tagged Stage N pass".

### B2. Stage 4 cannot pass `just ci`
* **Reviewer lens:** implementation-readiness (B3)
* **Affected scope:** D14 lines 293–295, Staging lines 433–434
* **Discrepancy:**
  - **The cap raise pulls in the breaking lookups.** D14 has statcatlib wait for one release that contains both sdmxlib stages, so raising the cap in Stage 4 brings in the `LocalisedString`-returning lookups at once.
  - **Two statcatlib sites break immediately:**
    - `store/store.py:748` builds `{lang: s[lang] for lang in s}`, which puts Structs into a DuckDB MAP parameter.
    - `store.py:1162, 1171` call `(... .get("en") or ...).encode()`, which raises `AttributeError`.
  - **The fixes are scheduled one stage too late.** They are listed under Stage 5 (slice 3), so Stage 4's "`just ci` passes" is unreachable.
* **Edit:** replace the Stage 4 Content cell with:

  > Raise the sdmxlib cap to the release containing stages 1–2 and, in the same PR, keep every public return as text: `_istring_to_map` becomes `s.as_dict()`; each `[tag]`/`.get(tag)` read feeding a `str` sink appends `.text` (statcatlib rows of the call-site table); msgspec becomes a direct dependency (D9).

  Start Stage 5 with: "Slice 3 (the rest): `normalize_tag` on request tags and `tag_alias` in `_language_slug`."

### B3. Stage 4 forces a catalog rebuild, which contradicts "every stage reverts without a catalog rebuild"
* **Reviewer lens:** implementation-readiness (B4), codebase-details (m11). Checked by the synthesizer.
* **Affected scope:** Staging line 433, Breaking changes lines 387–388
* **Discrepancy:**
  - **The store schema moved.** sdmxlib `storage/schema.py:203` is `SCHEMA_VERSION = "2.51"`. CHANGELOG line 93 (0.76.0) reads "Store schema 2.51". statcatlib pins `sdmxlib>=0.72.0,<0.73` (`pyproject.toml:37`), which is on schema 2.48.
  - **The rebuild is certain.** statcatlib's `_refuse_sdmx_schema_rebuild` and sdmxlib's `StoreSchemaError` mean Stage 4 rebuilds every catalog, and reverting it rebuilds them again. The Staging cell says only "check … for a forced catalog rebuild", and lines 387–388 say every stage reverts without one.
  - **The release list is wrong.** 0.74.0 (CHANGELOG line 149) has no Breaking Changes section, so "breaking minors 0.73–0.78" is inaccurate.
  - **The target version is not named.** It will be 0.79 or later.
  - **The upgrade work may already exist.** A statcatlib branch `feat/gh-70-sdmxlib-0.76` (`2cb3d7d`) exists, and the user's memory notes that the next release waits on the sdmxlib sharded-bundle integration.
* **Edit:**
  - In Stage 4, replace "this crosses the breaking minors 0.73–0.78, so check sdmxlib's store `SCHEMA_VERSION` for a forced catalog rebuild" with:

    > this crosses the breaking minors 0.73 and 0.75–0.78 (statcatlib GH-70 carries that upgrade and lands first) and sdmxlib's store schema 2.48 → 2.51 (0.76.0), so every statcatlib catalog is rebuilt; the CHANGELOG says so

  - Change lines 387–388 to:

    > This design changes no storage schema, `SCHEMA_VERSION` or `CANONICAL_FORM`, so stages 1–3 and 5 revert without a catalog rebuild; Stage 4 inherits sdmxlib's 2.51 schema, and reverting it rebuilds.

### B4. `TAG_REGEX` does not exist, and msgspec patterns are unanchored
* **Reviewer lens:** implementation-readiness (B1), design (M1), codebase-details (M1). Three of the four lenses raised it.
* **Affected scope:** Public API line 87, D6 lines 188–190, D9
* **Discrepancy:**
  - **No constant has that name.** sdmxlib has `TAG_PATTERN` (`model/istring.py:14-21`). It is written "without its `^` and `$`" and uses `[A-Za-z]`.
  - **msgspec unanchors patterns.** The msgspec 0.22 `Meta` docstring says the pattern "is treated as **unanchored**, meaning the `re.search` method is used". So `Meta(pattern=TAG_PATTERN)` accepts `"fr_CA"`. Decode refuses it today only because `__post_init__` also runs on decode, which contradicts D6's sentence that the `Meta` pattern does the refusing.
  - **The evidence script uses a third pattern.** It is `f"^(?:{TAG_PATTERN.lower()})$"` (`bench_post_init.py:31`). That one is lowercase-only, so `[A-Za-z]` becomes `[a-za-z]`. Decoding `{"lang":"FR"}` is then refused while `LocalisedString("x", "FR")` is accepted, which contradicts D6's "however it was built".
  - **Decode has no length cap before the regex.** `normalize_tag` caps tags at `MAX_TAG_LENGTH = 256` (`istring.py:24-26`).
  - **The implementer must choose name, anchoring and case**, and each choice changes the JSON contract.
* **Edit:**
  - Line 87: `lang: Annotated[str, msgspec.Meta(pattern=TAG_REGEX, max_length=MAX_TAG_LENGTH)]`.
  - In the Public API block, add `TAG_REGEX: Final = rf"^(?:{TAG_PATTERN})$"  # anchored, mixed case; model/istring.py`, and state whether it is exported.
  - Replace lines 188–190 with:

    > `lang` carries `msgspec.Meta(pattern=TAG_REGEX, max_length=MAX_TAG_LENGTH)`. msgspec matches a pattern with `re.search`, so `TAG_REGEX` is `TAG_PATTERN` anchored; it stays mixed case so a decoded `"FR"` passes and `__post_init__` normalises it. msgspec applies `Meta` in `decode` and `convert`, never on construction; `__post_init__` runs on every path.

    If the owner prefers that decode refuse `"FR"`, say so and drop "however it was built".
  - Add these Acceptance rows:
    - decoding `{"text":"x","lang":"fr_CA"}` raises `msgspec.ValidationError`;
    - `{"lang":"FR"}` decodes to `lang == "fr"`;
    - a 10,000-character `lang` is refused.

---

## Major

### M1. D7's `KeyError` rationale contradicts its own table, and the `Mapping` views escape D7
* **Lens:** design (M2), comprehension (M3), implementation-readiness (Minor 2, 3)
* **Scope:** D7 lines 200–212, Public API lines 99–101 and 112–113
* **Discrepancy:**
  - **Stdlib behaviour** (CPython 3.14.8 `_collections_abc.py`):
    - `Mapping.get` (792–797) and `Mapping.__contains__` (799–805) are `try: self[key] except KeyError`.
    - `ItemsView.__contains__` (872–879) catches `KeyError` and returns `False`.
    - The `ItemsView` and `ValuesView` `__iter__` methods call `self._mapping[key]` for every key, which normalises again. That breaks lines 112–113 and the "at most once per distinct tag" criterion.
    - `ChainMap.__getitem__` catches `KeyError` and moves on to the next map. So `ChainMap(s, d)["fr_CA"]` silently falls through, while `"fr_CA" in ChainMap(s, d)` raises.
  - **The stated reason contradicts the table.** D7's reason for subclassing `KeyError` ("so that `Mapping.get`, `ChainMap`, `str.format_map` … treat it as a failed lookup") is the opposite of the table, in which `get` and `in` raise.
  - **`str.format_map` is a poor example.** A found key formats as the struct repr (D11).
  - **`keys()` membership changes with the implementation.** If `keys()` is `self._data.keys()`, then `"FR" in s.keys()` is `False` while `"FR" in s` is `True`, and `"fr_CA" in s.keys()` returns `False` without raising.
* **Edit:**
  - Replace lines 211–212 with:

    > …and a `KeyError` so that `except KeyError` handlers written for a `dict` keep working, as sdmxlib's D3 promised for `[]`. Generic code that catches `KeyError` therefore treats a malformed tag as absent: `ChainMap.__getitem__` moves on to the next map. That is the one exception to the rule above.

  - Change line 201 to "raises from every `InternationalString` operation".
  - Add a Public API bullet:

    > `get` and `__contains__` are written over the stored map and never call `self[lang]` inside `try/except KeyError`. `keys()` returns `KeysView(self)`, so its `in` follows D7. `items()` and `values()` return private view subclasses whose `__iter__` reads the stored map and whose `__contains__` normalises the key and lets `InvalidTagError` and `TypeError` propagate.

  - Add an Acceptance row: `("fr_CA", v) in s.items()` and `"fr_CA" in s.keys()` raise `InvalidTagError`.

### M2. `pick` over several tags with one malformed tag is unspecified
* **Lens:** comprehension (M5), implementation-readiness (Minor 1)
* **Scope:** D7 table, line 203
* **Discrepancy:** Today `pick` normalises lazily (`istring.py:235-239`). So `pick("en", "fr_CA")` returns `en` when `en` is held. The table shows only `pick(tag)` with one tag.
* **Edit:** add under the table: "`pick` normalises every tag before matching, so a malformed or non-`str` tag anywhere in `langs` raises even when an earlier tag is held." If the owner prefers the lazy rule, state that instead.

### M3. The error classes have no home, no signature and no Public API entry
* **Lens:** comprehension (M4), implementation-readiness (M1), design (M8)
* **Scope:** Public API lines 83–110, D7 lines 213–215, Cross-repo contract line 397
* **Discrepancy:**
  - **Names missing from the block:** `MissingTagError` is public (statcatlib subclasses it, and the contract names it) but is absent. So are `sl.LocalisedString`, `TAG_REGEX`, `to_istring`'s signature and `langs`.
  - **No module is named.** sdmxlib has two candidates: `model/errors.py` and `model/istring.py`.
  - **No constructor is given.** statcatlib's `MissingTranslationError` (statcatlib `language-tags.md:175-176`; it does not exist in `src/` yet) needs several requested tags plus an entity and a field, so a single-tag signature would block it.
  - **The seen set and its cap have no names,** but the acceptance tests must reach them.
* **Edit:** append to the Public API block:

  ```python
  # all in sdmxlib/model/istring.py; LocalisedString, InvalidTagError, MissingTagError,
  # tag_alias exported from sdmxlib.model and sdmxlib, listed in both __all__
  class InvalidTagError(ValueError, KeyError):
      def __init__(self, lang: object, /) -> None: ...      # message is normalize_tag's
      def __str__(self) -> str: ...                         # unquoted
  class MissingTagError(KeyError):
      def __init__(self, langs: Sequence[str], held: Sequence[str], /) -> None: ...
      langs: tuple[str, ...]
      held: tuple[str, ...]
      def __str__(self) -> str: ...                         # "no text for 'de'; held: 'en', 'fr'"
  def to_istring(v: InternationalString | Mapping[str, str]) -> InternationalString: ...
  _SEEN_TAGS: set[str]; _SEEN_TAGS_MAX = 1024              # private
  ```

  Line 397: "`InvalidTagError` and `MissingTagError` (D7)".

### M4. `InvalidTagError` prints a quoted message
* **Lens:** implementation-readiness (M2), codebase-details (m2), design (M7)
* **Scope:** D7 lines 209–215
* **Discrepancy:** `ValueError` defines no `__str__` of its own and `KeyError` does, so through the MRO `str(InvalidTagError(msg))` gives `repr(msg)`. D7 overrides `__str__` only on `MissingTagError`.
* **Edit:** in line 209, add "and, like `MissingTagError`, overrides `__str__`, since `KeyError` quotes its message".

### M5. One cause still gives three exception types, against the goal "One rule for errors"
* **Lens:** design (M1, M7)
* **Scope:** Goals line 43, D7, D8 line 230, D6
* **Discrepancy:**
  - **Direct construction and `InternationalString` operations** raise `InvalidTagError`.
  - **`tag_alias` and every other `lang=` parameter** raise plain `ValueError`. `tag_alias` "raises as `normalize_tag` does", and the other parameters follow sdmxlib D3 (`language-tags.md:152`).
  - **`msgspec.json.decode` and `msgspec.convert`** raise `msgspec.ValidationError`, either from the pattern or wrapping the `__post_init__` error. This is inferred from the `_overlay.py:162` docstring, not run.
  - **Consequence:** `except InvalidTagError` misses most of the API. Only `except ValueError` catches every path.
  - **"chained from `normalize_tag`'s message"** is also ambiguous (comprehension m4).
* **Edit:** add to D7:

  > `normalize_tag` raises `InvalidTagError`, so `tag_alias`, every `lang=` parameter and the constructor raise one type; this is compatible, since it is a `ValueError`. msgspec decode and convert raise `msgspec.ValidationError` (a `ValueError`) on either check.

  If the owner keeps `normalize_tag` on `ValueError`, state that split explicitly instead.

### M6. The seen-set cap slows the whole process permanently, and its concurrency reasoning is wrong
* **Lens:** design (M3), implementation-readiness (M7)
* **Scope:** D6 lines 186–187, Risks lines 327–328, Acceptance lines 411–412
* **Discrepancy:**
  - **The slowdown is global and permanent.** Once one input fills the set, every later construction with an unseen tag runs `normalize_tag` for the rest of the process. That costs 145 ns (1.75×), outside the 1.4× goal, and it breaks "at most once per distinct tag".
  - **"Past the cap, every tag is checked" is ambiguous.** It can mean every tag, or every tag that is not in the set.
  - **The concurrency sentence gives the wrong reason.**
    - `set.add` and `in` are atomic, both under the GIL and under 3.13t/3.14t per-object critical sections, and adding is idempotent. That is why no lock is needed.
    - "store the same string" is not the reason.
    - A `len() < cap` check followed by `add` can overshoot the cap by one tag per racing thread.
* **Edit:**
  - Line 186: "When full the set is cleared and refilled, so common tags return to the fast path." Or state the permanent 145 ns cost explicitly.
  - Line 187: "`in` and `add` on a `set` are atomic with or without the GIL, and adding is idempotent, so no lock is needed; a race at the cap overshoots it by at most one tag per thread."
  - Risks: add the slowdown and its mitigation.

### M7. `text` is not type-checked, which `gc=False` relies on
* **Lens:** design (M4)
* **Scope:** D6 lines 177–179, Public API lines 114–116
* **Discrepancy:**
  - **msgspec checks no types on direct construction.** So `LocalisedString(name["fr"], "fr")`, a likely migration slip, is accepted. It encodes as nested JSON, which is the valid-but-wrong output line 350 warns about.
  - **`gc=False` is safe only if both fields are `str`.** A non-`str` `text` could form an uncollectable cycle.
  - **`of()` refuses non-`str` values, but the value type itself does not.**
* **Edit:**
  - Add to D6's first bullet: "`__post_init__` also raises `TypeError` unless `type(self.text) is str`."
  - Re-measure against the 1.4× gate.
  - Add an Acceptance row: `LocalisedString(LocalisedString("a", "en"), "en")` raises `TypeError`.

### M8. The Breaking changes bullet on `get(tag, default)` describes #308, not the new API
* **Lens:** comprehension (M1), design (M5), codebase-details (m8)
* **Scope:** lines 358–364
* **Discrepancy:**
  - **Wrong error type for today.** Today (`9955927`, `istring.py:213-223`) `name.get("en", "")` raises `ValueError`, not `InvalidTagError`, which does not exist yet.
  - **The bullet reads as describing the new API.** After D3 it returns the default, so placed under Breaking changes it contradicts D4 line 168.
  - **The real break is the mixed return type `LocalisedString | str`:**
    - `df.name.get("en", "")[:44]` (`docs/cookbook/catalog.md:20`) raises `TypeError` when `en` is held;
    - `catalog.md:102` prints the repr.
  - **Two cited sites are not misuses:**
    - `docs/upgrading.md:41` reads "`s.get(tag)` raises `ValueError`".
    - `istring.py:128` documents the variadic fallback.
* **Edit:**
  - Replace the first sentence with:

    > Today #308's variadic `get` reads a second argument as a tag, so `name.get("en", "")` raises `ValueError` when `en` is absent and `name.get("en", code.id)` … (Catalan). After D3 both return the default, so the result is `LocalisedString | str`: slicing raises `TypeError` (`catalog.md:20`) and printing writes the repr (`catalog.md:102`).

  - Remove `upgrading.md:41`.
  - List `istring.py:128` separately as "docstring example of the variadic `get`".

### M9. The headers in "Before and after" do not match their columns
* **Lens:** comprehension (M2, m2, m3), design (Minor 10)
* **Scope:** lines 63–78
* **Discrepancy:**
  - **The headers mislabel the columns.** `# Today (sdmxlib#308)` sits over the code column and `# After` over the comment column, yet the comment column holds "today -> after".
  - **Some rows have no "today" value.** Lines 70, 73 and 78 have none.
  - **"the default" (line 66) reads as "the default language".**
  - **Line 74 gives the wrong reason for `False`.** It reads as `False` because `fr_CA` is not held, when the reason that matters is that it is malformed.
  - **Rows are missing for:**
    - `1 in name`;
    - `name["de"]`;
    - `name.get("en", "")`.
* **Edit:**
  - Line 63: `# expression                          # today (sdmxlib#308) -> after`.
  - Line 70: `# AttributeError -> "Annuel"`.
  - Line 78: `# AttributeError -> "Population"`.
  - Line 73: `# n/a -> True`.
  - Line 66: `-> "en" (the default value, as Mapping.get; for fallback use pick)`.
  - Line 74: `# False (malformed, read as absent) -> raises InvalidTagError`.
  - Add these rows:
    - `1 in name  # False -> raises TypeError`;
    - `name["de"]  # KeyError -> raises MissingTagError`;
    - `name.get("en", "")  # raises ValueError -> LocalisedString(text="Annual", lang="en")`.

### M10. The repr is not valid Python, and `__init__`/`to_istring` changes are undecided
* **Lens:** implementation-readiness (M9), design (M6), codebase-details (m12, m13)
* **Scope:** Public API lines 104 and 114–119
* **Discrepancy:**
  - **The repr cannot be evaluated.** `__init__` takes only `**kwargs` (`istring.py:153`), so `InternationalString({"en-t-fr": "…"})` raises `TypeError`.
  - **Today's repr uses the keyword form** (`istring.py:319-321`), so the new dict-form repr is an unlisted change.
  - **`repr(dict)` uses single quotes,** so the example's double quotes are wrong.
  - **`to_istring` changes behaviour unannounced.**
    - Today it returns an `InternationalString` argument unchanged (`istring.py:332`), with no copy.
    - It also passes any non-`dict` `Mapping` through unconverted.
    - "copied by its stored map" changes both.
* **Edit:** choose one option and add it to the block.
  - Either add `def __init__(self, data: Mapping[str, str] | None = None, /, **kwargs: str) -> None: ...  # non-str value: TypeError`,
  - or write line 118 as `prints InternationalString.of({'en-t-fr': '…'})`.

  Then:
  - State whether `to_istring` copies its argument.
  - List the repr and `to_istring` changes in Breaking changes.

### M11. The audit run has no mechanics
* **Lens:** implementation-readiness (M3)
* **Scope:** lines 375–376, Stage 2 line 431
* **Discrepancy:** the text does not say:
  - where the env var is read;
  - which operations it covers (`values()`, `pick`, `in`);
  - how a run that raises can "list" every site;
  - whether the hook is committed;
  - which command runs it;
  - whether statcatlib runs it too.
* **Edit:** replace lines 375–376 with:

  > `model/istring.py` reads `SDMXLIB_ISTRING_AUDIT` once at import. When it is set, `__getitem__`, `get`, `values()` and `items()` append the caller's `file:line` (`sys._getframe(1)`) to `$SDMXLIB_ISTRING_AUDIT_OUT` instead of raising, so one run lists every site. The hook is committed. The run is `SDMXLIB_ISTRING_AUDIT=1 SDMXLIB_ISTRING_AUDIT_OUT=… uv run pytest -m "unit or integration"`, in sdmxlib for Stage 2 and in statcatlib against the sdmxlib branch for Stage 4. The de-duplicated `src/` sites become the call-site table's rows.

### M12. The call-site table's location and scope are not stated
* **Lens:** implementation-readiness (M4), codebase-details (m14)
* **Scope:** lines 373–374, line 431
* **Discrepancy:**
  - It is unstated whether the table is a committed file or the PR description.
  - It is unstated whether statcatlib's rows belong to it.
  - D12 makes `emit_pair` and `as_dict(copy=False)` private, which affects 13 test uses in 4 files the table must include:
    - `tests/support/strategies.py`;
    - `test_properties_core.py`;
    - `test_shared_empty_values.py`;
    - `test_dto.py`.
* **Edit:** "committed as `docs/design/egm/localised-string/call-sites.md` in sdmxlib (Stage 2) and in statcatlib's Stage 4 PR, columns file:line | old | new | caught by"; and add the four test files.

### M13. The benchmark and count criteria cannot be checked mechanically
* **Lens:** implementation-readiness (M5, M6, M7, M8), design (Minor 6)
* **Scope:** Acceptance lines 405–414 and 421
* **Discrepancy:**
  - **The 1.4× baseline no longer exists.** After Stage 2 no `get` returns `str`. The 1.34× figure compares free functions (`bench_post_init.py:42-46`), not the method. The criterion also does not say how the median of five runs is taken.
  - **The bench gate would not gate anything.** `tests/bench/` runs only under `just bench`, and `just ci` runs only `bench and bundle` (`justfile:227-228, 255`). `test_bundle_reads.py` needs `SDMXLIB_BENCH_BUNDLE` (`conftest.py:75-84`).
  - **The headroom is thin.** 1.34× against 1.4× leaves about 4%.
  - **"at most once per distinct tag" passes trivially.** With a warm set it makes zero calls, and the criterion does not say how calls are counted.
  - **"Build time and memory unchanged"** has no baseline and no tolerance.
  - **`tag_alias(t) == _language_slug(t)` becomes a tautology.** Once `_language_slug` adopts `tag_alias`, it compares the function with itself, and "every well-formed `t`" cannot be enumerated.
* **Edit:**
  - **Line 408:** baseline `def base(s): return s._data.get(normalize_tag("fr"))` against `InternationalString.get(s, "fr")`. Time each 5× with `perf_counter` in one process, seen set warm, and assert `median(candidate) <= 1.4 * median(base)`. Mark it `bench and bundle` so `just ci` runs it, and retry once before failing.
  - **Lines 411–412:** "with `_SEEN_TAGS` cleared and `normalize_tag` monkeypatched with a counter, iterating `keys()`, `values()` and `items()` of 1,000 strings over 3 tags calls it at most 3 times".
  - **Line 414:** "`_from_normalized`'s body is unchanged and `EAGER_BYTES_PER_ITEM`/`EAGER_CALLS_PER_ITEM` in `test_bundle_reads.py` pass unchanged".
  - **Line 421:** "statcatlib test: `tag_alias(t) == t.strip().lower().replace("-", "_")` (today's `_language_slug` body, `lance.py:219`, frozen in the test) for every well-formed fixture in `test_language_tags.py` plus every two-letter ASCII pair".
  - **Lines 405–406:** move the preamble under the first criterion only.

### M14. The FMR fact in D11 is reversed
* **Lens:** codebase-details (B1; rated Major here because the wording is wrong and no decision depends on it). Checked by the synthesizer.
* **Scope:** line 274
* **Discrepancy:** `model/_rules.py:142-144` reads: "a strict registry treats it as missing — FMR refused a codelist for 498,786 codes named `""`". FMR refused such a codelist; it did not send one.
* **Edit:**

  > Empty text is real data: a codelist with 498,786 codes named `""` reached FMR, which refused it (`model/_rules.py:141-145`), so …

### M15. `store.py:2425, 2544, 2546` are not `InternationalString` sites
* **Lens:** codebase-details (M2)
* **Scope:** Breaking changes line 366
* **Discrepancy:** `name_map` and `desc_map` come from `fetchone()` (store.py:2422 and 2540). They are DuckDB MAPs returned as Python `dict`s, so the change does not touch them.
* **Edit:** drop them from the list, or move them to the handoff list as "English-first fallback over a stored MAP".

---

## Minor

1. **D7 test lines** (lines 221–223). `test_language_tags.py:469-471` uses `pytest.raises(KeyError)`, which keeps passing.
   - The tests that change are `test_membership_of_a_malformed_tag_or_a_non_str_is_false` (186–189/190) and the `contains` helper (466–467, registered at 503).
   - Lines 161–162 change with D3 and D4.
   - Edit accordingly. (codebase-details m1, design m1)
2. **The amendment to sdmxlib D3 is incomplete** (lines 219–221). The quoted rows are accurate:
   - `language-tags.md:154`: `__getitem__` "raises `KeyError`, chained from the `ValueError`";
   - `language-tags.md:155`: `__contains__` "`False` for a malformed tag or a non-`str`".

   The amendment also has to cover:
   - row 153 (`get(*langs)`, `pick(*langs)`);
   - that design's Breaking changes 307–309;
   - `docs/upgrading.md:39-41`.

   Always write "sdmxlib's language-tags design, its D3" (and likewise its D7 in Stage 1), since this RFC has its own D3 and D7. (codebase-details m3, comprehension m8, design m9)
3. **`in` raising is missing from Breaking changes.** Add a bullet: `tag in name` raises `InvalidTagError` or `TypeError` where it returned `False`. (comprehension m7, design m5)
4. **"Errors follow `dict`" against the `TypeError` row.** `1 in {"a": 1}` is `False` on a `dict`. Add: "Unlike `dict`, a non-`str` tag raises `TypeError` even from `in`." (comprehension m5)
5. **D7 table wording.**
   - The "default" cell should read "`None`, or `default` if given".
   - Introduce `s` as an `InternationalString`, or use `name`. (comprehension m1, m9)
6. **`Meta` also applies on `msgspec.convert`.** The bench comment already says so (`bench_post_init.py:28`). Line 190 should read "on decode and convert, never on construction". (codebase-details m4, design M1)
7. **`msgspec.structs.replace`.** Nobody verified whether it runs `__post_init__`. Add a criterion that `replace(v, lang="FR")` gives `"fr"`, or name `replace` as an exception to "however it was built". (design m7)
8. **Benchmark evidence.**
   - The figures 100/112/145 ns and 1.34× appear only in the scratchpad file `pr308-followup.md:24-27`, which is not in the Evidence list (lines 14–18).
   - "27 ns per `if v:`" (line 320) has no recorded source. `final-review.md` already asked for it to be dropped or re-measured, and `bench_struct_dunders.py:65-67` does not isolate it.
   - (codebase-details m5)
9. **`projected_name` location** (D8 line 239). It is at `query/_expr.py:1241-1252`, and `Label.column` is at 1239. Cite `1231-1252`. (codebase-details m6)
10. **`_istring_to_map`** (line 365). It is defined at `store.py:744-748`, with 27 calls on 25 lines, not 24 callers. (codebase-details m7)
11. **`scopes.py:999, 1054`** build `InternationalString(en=r[1] or "")`, not a literal `en=""`. Reword. (codebase-details m9)
12. **Stage 1 `LocalizedText` sites not listed.**
    - sdmxlib `docs/design/language-tags.md:305` and the D7 body (195–206);
    - `tests/unit/test_language_tags.py:155, 202, 207-213, 507`. Rename the key at 507 to `sdmxlib.model.istring:LocalisedString`;
    - `istring.py:129`;
    - name the file for "Non-goals 39–40" and "Cross-repo contract 331–335" (verified correct).

    (codebase-details m10, implementation-readiness Minor 5)
13. **The `lang` enumeration test** (`test_language_tags.py:528-535`) fails in Stage 2 unless `tag_alias` (and `LocalisedString`) join `_calls`. Say so in D8 or D7. (implementation-readiness Minor 6, design m2)
14. **D12 names no private replacements.** Write `_emit_pair()`, `_backing()`, and "`as_dict()` loses `copy`". Update the `EMPTY` comment (`istring.py:147-150`) and its test. (implementation-readiness Minor 4)
15. **`ABCMeta` cost.** Inheriting `Mapping` makes every `isinstance` miss go through the Python-level `ABCMeta.__instancecheck__`. Sites: `convert.py:185`, `storage/writers.py:2598`, `_canonical.py:81`. The call-count bounds would catch it. Add a Risks line. (design m3, implementation-readiness note)
16. **Equality and protocols.**
    - `s.items() == {"en": ls}.items()` is `True` while `s == {"en": ls}` is `False`.
    - `Mapping` also enables `match s: case {"fr": v}` and `**s`.
    - State both after line 106. (design m4)
17. **`__lang` ownership.** D13 line 289 has sdmxlib's DSL add `__lang`, while Cross-repo line 401 gives the suffix to statcatlib. Line 401 should read "the `__lang` suffix is the suite rule for a column holding the answering tag". (design m8)
18. **Stage 2 is vague.**
    - Name where the evidence goes: bench scripts to sdmxlib `bench/` or `tests/bench/`, notes and EGM reports to `docs/design/egm/localised-string/`.
    - Name the `query-naming.md` content: a "Model classes and fields" section with the D1/D2/D8 rules, plus a deviations row for `label`/`locale` → `text`/`lang`.

    (implementation-readiness Minor 7, 8)
19. **Stage 5 scope.** Slice 4 in statcatlib `language-tags.md:228-232` is broader than this RFC (required `lang`, tuples, gap lists). Its open item still names `title_lang` (lines 99, 217). Say that Stage 5 covers only the `LocalisedString` return and `title__lang`, and that this settles statcatlib's open item. Name the test file and error type for the "every `lang` parameter refuses" criterion. (implementation-readiness Minor 9, codebase-details verified)
20. **D11 wording.**
    - Line 271–272: rewrite as "`pick("fr", "en")` stops at the first tag the string holds even when its text is `""`, and returns `LocalisedString("", "fr")`, which is truthy."
    - Note that `LocalisedString.text` is always a `str`, unlike ElementTree's `.text`, which can be `None`.

    (comprehension m6, design m11)
21. **`structure_frame` cells** (line 344). The frame has an explicit `"concept": pl.String` schema (`polars.py:509-513`), so a `LocalisedString` cell most likely raises on construction rather than writing silently. This was not run. Move it from "keeps running" to "raises". (codebase-details m15)
22. **Undefined terms for a newcomer.** Define each at first use:
    - "seen set";
    - "held tag";
    - "stored map";
    - `_from_normalized` (the private constructor for already-normalised tags);
    - `_language_slug`;
    - `normalize_tag` ("validates a tag and returns its lowercase form");
    - FMR (Fusion Metadata Registry).

    Line 61 and line 118 also show two notations for one value. (comprehension m10, m11)

---

## Verified correct (no edit)

- **`OverlayText` and decode.**
  - `OverlayText` is a `msgspec.Struct(frozen=True, kw_only=True, forbid_unknown_fields=True)` at `bundle/_overlay.py:135`.
  - Its `__post_init__` at 161 calls `normalize_tag`, and its fields are at 157–158.
  - `__post_init__` runs on decode.
- **msgspec 0.22.**
  - It refuses a custom `__init__`/`__new__`.
  - `msgspec.structs.force_setattr` exists and is documented for frozen `__post_init__` use, and it is safe with `str` on a `gc=False` Struct.
  - `order` and `cache_hash` are off by default, so `sorted(values)` raises.
  - `format(v, ">10")` raises `TypeError`.
- **`InternationalString` as it stands.**
  - `__hash__` and `__eq__` are consistent, and both are defined in the class body, which avoids `Mapping`'s `__hash__ = None`.
  - The `EMPTY` comment (1,159,902 strings, ~98% empty annotation texts), `_from_normalized` (179), the "Today" behaviours in Before and after, and the `istring.py:128` docstring are all as stated.
- **D12 and D13 call sites.**
  - D12: `_dto.py:99`, `_rules.py:213`, `sdmx_json/metadata.py:139`.
  - `_canonical.py:50` (sorted encoder) and `:82`.
  - `polars.py:287, 300-303, 353, 414-486`.
  - The `structure_frame` `concept` column is `pl.String`.
- **Stage 1 and repository references.**
  - Stage 1 refs: `docs/upgrading.md:33, 52-54`, `model/EGM.md:94, 119`, `language-tags.md` 39–40 and 331–335.
  - Exports at `model/__init__.py:96, 208` and `sdmxlib/__init__.py:172, 345`, all of which export `LocalizedText`.
  - `docs/design/query-naming.md` exists, and so do `tests/unit/test_canonical_json.py` and the call-count bounds in `test_bundle_reads.py`.
- **statcatlib references.**
  - `lance.py`: 211–219, 942, 1051, 1169, 1260, 1280.
  - `store.py`: 1162, 1171, 1328, 1386.
  - `sources/sdmx.py:115`, and `pyproject.toml:37` (`<0.73`).
  - `implicit-bool = false` in both pyrefly configs.
  - statcatlib Decision 14 is at `language-tags.md:201-212`.
- **`tag_alias`.** It equals today's `_language_slug` body on every well-formed tag.
- **Not verified.** D8 line 245 ("ingest refuses an empty `lang` before that call") was not traced.

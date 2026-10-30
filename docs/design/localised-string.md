# Text model: add LocalisedString per the SDMX Information Model

* **Author:** Gabriel Gellner
* **Date:** 2026-10-30
* **Status:** Built in sdmxlib: Stages 1 and 2 shipped in sdmxlib 0.79.0
  (StatCat-Suite/sdmxlib#308 and StatCat-Suite/sdmxlib#310). statcatlib's
  Stages 4 and 5 are open, as StatCat-Suite/statcatlib#91. The design came
  from an EGM brainstorm: two Goldfish review rounds, a seven-lens final
  review and a four-lens review of the final choices, with every decision
  settled by the owner. A suite design: it
  changes sdmxlib's text model and statcatlib's label API, and lives in the hub
  under `docs/design/`, as GH-12's suite design workflow sets out.
* **Based on:** sdmxlib `feat/gh-280-language-tags` at `9955927`
  (StatCat-Suite/sdmxlib#308, open, unreleased; sdmxlib 0.78.0, store schema
  2.51); statcatlib `main` at `4d4eebe` and `docs/gh-88-lowercase-tags` at
  `9ff6ddd` (StatCat-Suite/statcatlib#90); msgspec 0.22.0; CPython 3.14.8.
* **Evidence:** [`egm/localised-string/`](egm/localised-string/README.md)
  holds the IM audit, the benchmark scripts and the EGM review reports this
  design draws on. StatCat-Suite/sdmxlib#309 (Stage 2) copies the benchmark
  scripts into sdmxlib's `tests/bench/` as gated tests.

## Terms

- **Tag:** a BCP 47 language tag such as `en` or `fr-ca`. `normalize_tag()`
  validates a tag and returns its lowercase form; every stored tag is in
  that form (StatCat-Suite/statcatlib#88).
- **Stored map:** the `dict[str, str]` from tag to text inside an
  `InternationalString`. A **held tag** is a key of that map.
- **`_from_normalized`:** sdmxlib's private constructor for an
  `InternationalString` whose tags are already normalised (the store read
  path).
- **Seen set:** the module-level set of tags `LocalisedString` has already
  checked (D6).
- **`_language_slug`:** statcatlib's function that turns a tag into the
  suffix of a search table name (`store/lance.py:211-219`).
- **FMR:** the Fusion Metadata Registry.

## Problem

SDMX 3.1 Section 2 defines `InternationalString` as "a collection of
Localised Strings" and `LocalisedString` as text in one locale, with
attributes `label` and `locale` (IM text lines 1392–1404).

sdmxlib's `InternationalString` maps a tag to a `str`, and its lookups return
`str`, so a caller cannot tell which language answered.
StatCat-Suite/sdmxlib#308 adds `LocalizedText(text, lang)`, an attrs class
returned only by `pick()`, and keeps `get(*langs)` variadic: `get("fr", "en")`
returns the `fr` text, else the `en` text. That `get` conflicts with
`collections.abc.Mapping.get(key, default)`, and sdmxlib's cookbook already
uses it as a mapping `get` (Breaking changes, below).

statcatlib's language-tags RFC (decision 6) requires every label to carry the
tag that answered, and needs one value type to return.

## Goals

- A value type named after the IM's `LocalisedString`, returned by every
  per-tag accessor on `InternationalString`.
- `InternationalString` as a true `Mapping[str, LocalisedString]`, with
  `pick()` for fallback over several tags.
- One error type for a malformed tag on every path.
- Lookup cost within 1.5× of returning `str`, with build cost and memory
  unchanged.
- One rule for writing a tag inside a generated name.
- One JSON form for a `LocalisedString` across the suite.

## Non-goals

- A Rust or native value type.
- The IM classes `InternationalUri`, `LocalisedUri` and
  `LocalisedMemberValue`.
- Renaming `lang` parameters or persisted `lang` fields.
- Accepting `_` in a tag as input.
- Changing the stored lowercase tag form agreed on StatCat-Suite/statcatlib#88.

## Before and after

```python
name = code.name                      # InternationalString.of({'en': 'Annual', 'fr': 'Annuel'})

# expression                          # today (sdmxlib#308) -> after
name["fr"]                            # "Annuel" -> LocalisedString(text='Annuel', lang='fr')
name["fr"].text                       # AttributeError -> "Annuel"
name["de"]                            # KeyError -> raises MissingTagError
name.get("fr")                        # "Annuel" -> LocalisedString(text='Annuel', lang='fr')
name.get("de", "en")                  # "Annual" (fallback tag) -> "en" (the default value, as in Mapping.get; use pick to fall back)
name.get("en", "")                    # raises ValueError -> LocalisedString(text='Annual', lang='en')
name.pick("de", "en")                 # LocalizedText(...) -> LocalisedString(text='Annual', lang='en')
dict(name.items())                    # {'en': 'Annual', …} -> {'en': LocalisedString(...), …}
name.as_dict()                        # {'en': 'Annual', …} -> unchanged, dict[str, str]
f"{name['fr']}"                       # "Annuel" -> "LocalisedString(text='Annuel', lang='fr')"
name["fr"] == "Annuel"                # True -> False
bool(LocalisedString("", "fr"))       # n/a -> True
"fr_CA" in name                       # False (malformed, read as absent) -> raises InvalidTagError
1 in name                             # False -> raises TypeError

# statcatlib
concept.label["en"]                   # "Population" -> LocalisedString(text='Population', lang='en')
concept.label["en"].text              # AttributeError -> "Population"
```

## Public API

All in `sdmxlib/model/istring.py`. `LocalisedString`, `InvalidTagError`,
`MissingTagError` and `tag_alias` are exported from `sdmxlib.model` and
`sdmxlib` and listed in both `__all__`.

```python
class LocalisedString(msgspec.Struct, frozen=True, gc=False):
    """SDMX IM LocalisedString: `text` is the IM's `label`, `lang` its `locale`."""
    text: str
    lang: str

class InternationalString(collections.abc.Mapping[str, LocalisedString]):
    def __getitem__(self, lang: str, /) -> LocalisedString: ...
    @overload
    def get(self, lang: str, /) -> LocalisedString | None: ...
    @overload
    def get(self, lang: str, default: T, /) -> LocalisedString | T: ...
    def pick(self, *langs: str) -> LocalisedString | None: ...   # zero args: TypeError
    def __contains__(self, lang: object, /) -> bool: ...
    def __iter__(self) -> Iterator[str]: ...                     # held tags
    def __len__(self) -> int: ...
    def keys(self) -> KeysView[str]: ...
    def values(self) -> ValuesView[LocalisedString]: ...
    def items(self) -> ItemsView[str, LocalisedString]: ...
    def as_dict(self) -> dict[str, str]: ...
    @property
    def langs(self) -> list[str]: ...
    @classmethod
    def of(cls, pairs: InternationalString | Mapping[str, str]) -> InternationalString: ...
    def __eq__(self, other: object) -> bool: ...                 # True only against InternationalString
    def __hash__(self) -> int: ...                               # kept; Mapping would set it to None
    def __repr__(self) -> str: ...                               # InternationalString.of({'en-t-fr': '…'})

def normalize_tag(tag: str) -> str: ...                          # raises InvalidTagError, TypeError
def tag_alias(lang: str) -> str: ...
def to_istring(v: InternationalString | Mapping[str, str]) -> InternationalString: ...

class InvalidTagError(ValueError):
    lang: str                                                    # the refused input, truncated to 64 chars

class MissingTagError(KeyError):
    def __init__(self, langs: Sequence[str], held: Sequence[str], /) -> None: ...
    langs: tuple[str, ...]
    held: tuple[str, ...]
    def __str__(self) -> str: ...                                # "no text for 'de'; held: 'en', 'fr'"

_SEEN_TAGS: set[str]                                             # private
_SEEN_TAGS_MAX = 1024                                            # private
```

- `get` and `__contains__` read the stored map directly. Neither calls
  `self[lang]` inside `try/except KeyError`.
- `keys()` returns `KeysView(self)`, so `tag in s.keys()` follows D7.
  `items()` and `values()` return private view subclasses whose `__iter__`
  reads the stored map without normalising a held tag again, and whose
  `__contains__` normalises the key and lets `InvalidTagError` and
  `TypeError` propagate.
- `of()` copies the stored map of an `InternationalString` argument, converts
  any `Mapping[str, str]`, and raises `TypeError` for a non-`str` value, so a
  `LocalisedString` cannot be stored as text. `to_istring` returns an
  `InternationalString` argument unchanged and passes any other mapping to
  `of()`.
- `__repr__` changes from the keyword form (`InternationalString(en='…')`) to
  `InternationalString.of({'en-t-fr': '…'})`, which is valid Python for every
  tag.
- Mapping protocols follow from the base class: `s.items() ==
  {"en": ls}.items()` is true while `s == {"en": ls}` is false;
  `match s: case {"fr": v}` and `**s` work.

## Decisions

**D1. Class name.** sdmxlib names a model class after its IM class unless
there is a stated better reason. The value class is `LocalisedString`, in the
IM's British spelling, as `OrganisationUnit` and `OrganisationSchemeMap` are.
It sits beside `normalize_tag` and the `localized_text` table, which use
American spelling; `from sdmxlib import LocalizedString` raises `ImportError`.
No alias is added, because `LocalizedText` was never released. The query
classes `Localised` and `SideLocalised` (`query/accessors.py:76-79`) are
expressions, and the docstring of `LocalisedString` says so.

**D2. Field names.** A field may take a Pythonic name, with the IM name in
the docstring. `LocalisedString` has `text` and `lang`. Every parameter and
model field holding a tag is `lang` or `langs`; `locale` stays only on
`DatePatternMap`, whose value is a parser locale and is never validated as a
tag. Reasons:

- Persisted names already use `text` and `lang`:
  `sdmx.localized_text(owner_urn, field, lang, text)`
  (`storage/schema.py:371-377`), `OverlayText.lang` and `.text`
  (`bundle/_overlay.py:157-158`) and the canonical annotation URL `"lang"`
  (`model/convert.py:100`).
- sdmxlib already replaces IM attribute names with shorter or wire names:
  `conceptIdentity` → `concept` and `localRepresentation` → `representation`
  (`model/datastructure.py:329-330`), `LocalisedMemberValue.locale` →
  `RegionValue.lang` (`model/constraint.py:149`).
- `label` would give statcatlib `concept.label["en"].label` (13 fields are
  named `label`) and would sit beside the query DSL's `Label`. `locale` reads
  as a POSIX locale (`fr_CA`), which `normalize_tag` refuses.
- sdmx1 stores localised text as a dict named `localizations`, with no
  per-string class. pysdmx's Fusion-JSON string uses `{locale, value}`.

`text` also names a whole multilingual field: `Annotation.text` is an
`InternationalString` (`model/annotations.py:60`), so a caller writes
`ann.text.pick("en").text`. SDMX-JSON makes the same split, `text` for one
string and `texts` for the map (`formats/sdmx_json/structure_values.py:55-56`).
The `LocalisedString` and `Annotation` docstrings each state it.

**D3. `get` follows `Mapping`.** `[]` and `get` take one tag; `get`'s default
is positional, as in typeshed's `Mapping.get` overloads. `pick(*langs)` is
the only lookup that falls back over several tags. `pick()` with no tag raises
`TypeError`.

**D4. Per-tag accessors return `LocalisedString`.** `[]`, `get`, `pick`,
`values()` and the values of `items()` return `LocalisedString`. Bulk and
columnar outputs return text and carry the tag separately: `as_dict()`,
Polars frames, query DSL projections and statcatlib projection columns.
`get`'s default is returned as given.

**D5. Storage.** `InternationalString` keeps its stored map and builds a
`LocalisedString` when an accessor returns it. Storing value objects cost
+0.3 s build time and +66–100 MiB per million strings, and is cheaper only
when each string is looked up four or more times. The store builds many
strings it never reads: about 98% of annotation texts are empty, and one
codelist read builds 1,159,902 strings (`istring.py`, `EMPTY` comment).

**D6. Value type and validation.** `LocalisedString` is a frozen
`msgspec.Struct` with `gc=False`. Every `LocalisedString` holds a `str` text
and a normalised tag however it was built: direct construction,
`msgspec.json.decode`, `msgspec.convert` and `msgspec.structs.replace` all run
`__post_init__`, so `LocalisedString("Annuel", "FR") == name.pick("fr")` and
`replace(v, lang="FR").lang == "fr"`.

`__post_init__`:

1. raises `TypeError` unless `type(self.text) is str`. `gc=False` is safe only
   when both fields are `str`, and msgspec checks no types on direct
   construction, so `LocalisedString(name["fr"], "fr")` would otherwise be
   accepted and encode as nested JSON;
2. returns if `lang` is in the seen set;
3. otherwise calls `normalize_tag(lang)`, which raises `InvalidTagError` for a
   malformed tag; replaces `lang` with `msgspec.structs.force_setattr` when
   its case differs; and adds the normalised tag to the seen set. When the set
   holds `_SEEN_TAGS_MAX` (1,024) tags it is cleared first, so common tags
   return to the fast path after an input with many distinct tags.

`in` and `add` on a `set` are atomic with or without the GIL, and adding is
idempotent, so no lock is needed; a race at the cap overshoots it by at most
one tag per thread.

msgspec wraps an error raised in `__post_init__` during decode or convert in
`msgspec.ValidationError` (a `ValueError`) with the original message: decoding
`{"text":"x","lang":"FR"}` gives `lang='fr'`, and `"fr_CA"` or a 300-character
tag is refused. No `msgspec.Meta` pattern is used: msgspec matches a pattern
with `re.search`, so sdmxlib's unanchored `TAG_PATTERN` accepted `"fr_CA"` and
`"zz zz"`.

Equality and hashing use both fields (`fr` and `fr-ca` differ);
`cache_hash` is off. msgspec generates no ordering, so `sorted(values)`
raises; sort with `key=attrgetter("text")`. Each lookup builds a new object,
so `s["en"] is s["en"]` is false. msgspec refuses a custom `__init__` or
`__new__`, so `__post_init__` is the only construction hook. sdmxlib already
depends on msgspec and validates in `__post_init__` elsewhere (`OverlayText`,
`bundle/_overlay.py:135, 161`).

**D7. Errors follow `dict`.** A malformed tag is a caller bug and raises from
every `InternationalString` operation, as an unhashable key does on a
`dict`:

| Tag, for `name` an `InternationalString` | `name[tag]` | `name.get(tag)` | `name.pick(tag)` | `tag in name` |
|---|---|---|---|---|
| malformed (`"fr_CA"`) | `InvalidTagError` | `InvalidTagError` | `InvalidTagError` | `InvalidTagError` |
| not a `str` (`1`) | `TypeError` | `TypeError` | `TypeError` | `TypeError` |
| well-formed, absent (`"de"`) | `MissingTagError` | `None`, or `default` if given | `None` | `False` |

- `InvalidTagError` is a `ValueError` only. Generic code that catches
  `KeyError` (`ChainMap`, the `Mapping` mixins, `except KeyError` handlers)
  passes it on, as it passes on `dict`'s `TypeError`, so a malformed tag is
  never read as absent.
- `normalize_tag` raises `InvalidTagError`, so the constructor, `tag_alias`
  and every `lang=` parameter raise one type. msgspec decode and convert raise
  `msgspec.ValidationError`, also a `ValueError`. `except ValueError` catches
  every path.
- `pick` normalises every tag before matching, so a malformed or non-`str`
  tag anywhere in `langs` raises even when an earlier tag is held.
- Unlike `dict`, a non-`str` tag raises `TypeError` even from `in`; a `dict`
  returns `False` for a hashable key of another type.
- `MissingTagError(KeyError)` names the requested and held tags and overrides
  `__str__`, since `KeyError` quotes its message. statcatlib's
  `MissingTranslationError` will subclass it.
- `normalize_tag`'s error for an underscore gains a hint naming the hyphen
  form ("did you mean 'fr-ca'?").

This amends sdmxlib's language-tags design, its D3: the `__getitem__` row
(`docs/design/language-tags.md:154`, "raises `KeyError`, chained from the
`ValueError`") becomes `InvalidTagError`, a `ValueError`; the `__contains__`
row (line 155, "`False` for a malformed tag or a non-`str`") becomes
"raises"; and the `get`/`pick` row (line 153), that design's Breaking changes
(lines 307–309) and `docs/upgrading.md:39-41` change with them. The tests that
change are `tests/unit/test_language_tags.py:469-471` (a `KeyError`
expectation), `test_membership_of_a_malformed_tag_or_a_non_str_is_false`
(lines 186–190), the `contains` helper (lines 466–467, registered at 503) and
lines 161–162.

**D8. Tag alias in generated names.** Every generated name that joins a base
name and a tag writes the tag with `-` replaced by `_`: `name_fr_ca`,
`REF_AREA_label_en_t_fr`, `search_fr_ca__000003`. The alias is output only.

- `sl.tag_alias(lang)` returns `normalize_tag(lang).replace("-", "_")` and
  raises as `normalize_tag` does. There is no public inverse. It joins the
  `_calls` list of the `lang` enumeration test
  (`tests/unit/test_language_tags.py:528-535`), as `LocalisedString` does.
- Tags never contain `_`, so the alias is reversible given the base name.
  Tags never contain `--`, so an alias never contains `__`, and `__`
  separates a non-tag suffix (`title__lang`), as statcatlib's search table
  names already do (`search_fr_ca__000003`).
- A bare alias can be a Python keyword (`is` Icelandic, `as` Assamese, `or`
  Odia), so an alias appears only after a base name.
- Adopters: sdmxlib `Label.column` and `projected_name`
  (`query/_expr.py:1231-1252`), the `polars.label` suffix (`polars.py:287,
  300-303, 353`), statcatlib `Row` attributes and statcatlib
  `_language_slug`.
- `_language_slug` names persisted Lance tables (`lance.py:1280`) and
  `index.json` keys (`lance.py:1051, 1169`), so `tag_alias(t)` must equal
  today's `_language_slug(t)` for every stored tag. It does: today's body is
  `t.strip().lower().replace("-", "_")` (`lance.py:219`).
  `lance.py:1260` calls the slug on `""`; Stage 5 traces that call and makes
  ingest refuse an empty `lang` before it.

**D9. JSON form.** A `LocalisedString` serialises as
`{"text": "Population", "lang": "en"}`, with the stored lowercase tag and no
display case, across the suite. It is produced by `msgspec.json.encode(value)`
or `msgspec.structs.asdict(value)`. Key order is part of the contract (`text`,
then `lang`), so a sorted encoder such as `bundle/_canonical.py:50` writes
`as_dict()` output and never a `LocalisedString`. statcatlib serialises with
stdlib `json`, which raises on a Struct, so it converts with
`msgspec.structs.asdict` and adds msgspec as a direct dependency.

**D10. Suite design location.** This design lives in the hub, under
`docs/design/` (GH-12).

**D11. Text is reached through `.text`.** `LocalisedString` follows the
libraries whose objects carry text beside other data: ElementTree, lxml,
requests and httpx all return a repr from `str()` and expose the text as
`.text`. It defines no `__str__`, `__format__` or `__bool__`:

- `str(v)` and `f"{v}"` give the struct repr,
  `LocalisedString(text='Annuel', lang='fr')`.
- `format(v, ">10")` raises `TypeError`, since `object.__format__` refuses a
  non-empty spec.
- `v == "Annuel"` is `False`.
- Every `LocalisedString` is truthy, so `if name.get("fr"):` tests presence,
  matching `get`'s `LocalisedString | None` return.
- `pick("fr", "en")` stops at the first held tag even when its text is `""`,
  and returns `LocalisedString("", "fr")`, which is truthy.
- `LocalisedString.text` is always a `str`, unlike ElementTree's `.text`,
  which can be `None`.

Empty text reaches sdmxlib: a codelist with 498,786 codes named `""` reached
FMR, which refused it (`model/_rules.py:141-145`). `x or fallback` written for
`str` stops falling back on empty text; Breaking changes lists it.

**D12. Raw views.** `as_dict()` stays public, returns a new `dict[str, str]`
and loses its `copy` parameter; it serves serialisers, the canonical bundle
bytes and statcatlib's MAP parameters. `emit_pair()` (used at
`formats/sdmx_json/_dto.py:99`) becomes `_emit_pair()`, and
`as_dict(copy=False)` (used at `model/_rules.py:213` and
`formats/sdmx_json/metadata.py:139`) becomes `_backing()`, both private to
sdmxlib. The `EMPTY` comment (`istring.py:147-150`) and its test name the new
methods.

**D13. Query DSL.** A projected DSL `Label` stays text (VARCHAR); the model
returns `LocalisedString`. A DSL label names one tag, and its column name
carries it (`name_en`, `name_fr_ca`), so sdmxlib's DSL and `polars.label`
emit no tag column. `structure_frame`'s `concept` column stays `pl.String`.
The query tutorial and `docs/upgrading.md` state it. `__lang` is the suite's
suffix for a column holding the answering tag; statcatlib uses it, and a DSL
fallback over several tags, if one is added, uses it too.

**D14. Sequencing.** StatCat-Suite/sdmxlib#308 renames `LocalizedText` and
adopts D6, D9 and `InvalidTagError`, so no `LocalizedText` is released. The
lookup API ships in a second sdmxlib PR. A release between the two carries
the new type beside the `str`-returning lookups, which is additive. statcatlib
adopts it after its own upgrade to sdmxlib 0.76 (StatCat-Suite/statcatlib#70),
which already rebuilds every catalog.

## Alternatives considered

- **Store `LocalisedString` objects.** Rejected (D5): +75–90% build time and
  +35–50% memory per million strings.
- **attrs `@frozen` or a `__slots__` class.** Rejected: 224 ns and 190 ns per
  lookup against 92 ns for a Struct, through the same `get` shape
  (`bench_lookup_fair.py`).
- **`NamedTuple`.** Rejected: it compares equal to plain tuples and encodes
  as a JSON array.
- **A Rust value type.** Rejected: a PyO3 object is still one Python
  allocation per lookup. Native code helps only if labels stay native or in
  the parsers, which are larger designs.
- **`label` and `locale` as field names.** Rejected (D2).
- **A variadic `get`.** Rejected (D3): it breaks `Mapping`.
- **No validation on construction.** Rejected (D6): a hand-built value with
  `"FR"` would differ from the returned one without an error.
- **Normalise on every construction.** Rejected: 145 ns, 1.75× `str`
  (`bench_post_init.py`).
- **A `msgspec.Meta` pattern on `lang`.** Rejected (D6): msgspec applies it
  with `re.search`, and an anchored lowercase pattern would refuse `"FR"`,
  which construction accepts.
- **`InvalidTagError` as both `ValueError` and `KeyError`.** Rejected (D7):
  `Mapping.get`, `ChainMap` and `ItemsView.__contains__` catch `KeyError`, so
  they returned `None` or `False` for `"fr_CA"`.
- **`in` returning `False` for a malformed tag.** Rejected (D7): one rule for
  every operation.
- **`str()` and `format()` returning the text, and truthiness following the
  text.** Rejected (D11): a `str` shortcut that drops the tag, and a
  truthiness rule the comparable libraries do not use. It kept `x or
  fallback` working on empty text.

## Risks and mitigations

- **Silent behaviour changes.** Many call sites keep running with different
  results; see Breaking changes. Mitigation: the audit run and the call-site
  table.
- **Seen-set churn.** An input with more than 1,024 distinct valid tags
  clears the set repeatedly, and each unseen tag costs a full
  `normalize_tag`. Mitigation: clearing returns common tags to the fast path;
  the six surveyed registries send about 30 distinct tags between them.
- **Encoder drift.** A `LocalisedString` reaching a sorted or stdlib encoder
  writes the wrong bytes or raises. Mitigation: D9 and the JSON byte tests.
- **Persisted table names.** A change to `_language_slug`'s output orphans
  existing search indexes. Mitigation: the frozen-body test in Acceptance
  criteria.
- **`isinstance` cost.** Inheriting `Mapping` sends every `isinstance` miss
  through `ABCMeta.__instancecheck__` (`model/convert.py:185`,
  `storage/writers.py:2598`, `bundle/_canonical.py:81`). Mitigation: the
  call-count bounds in `tests/bench/test_bundle_reads.py`.
- **Benchmark drift.** The figures come from one machine and one Python
  (3.14.8). Mitigation: ratio gates measured in one process, retried once.

## Breaking changes and migration

The lookup change breaks sdmxlib's public API and roughly 400 source sites
across both repositories (round 1 estimate), plus 278 test-file matches in 78
sdmxlib files.

Raises where it ran before:

- `structure_frame` builds its frame with an explicit `"concept": pl.String`
  schema (`polars.py:509-513`), so a `LocalisedString` cell raises
  (`polars.py:414-486`).
- `tag in name` raises `InvalidTagError` or `TypeError` where it returned
  `False`.
- `LocalisedString(name["fr"], "fr")` raises `TypeError`.
- `format(value, spec)` raises `TypeError`.

Keeps running with different results:

- SDMX-JSON entries (`formats/sdmx_json/_data_common.py:173, 181, 386, 441,
  776-788`) and writer loops over `items()` (`formats/sdmx_ml/_common.py:1792,
  1839`, `sdmx_ml/_header.py:104`, `sdmx_ml30/metadata.py:87`,
  `sdmx_ml/_v3_writer.py:772, 776`, `sdmx_ml21/writer.py:155, 159`,
  `model/_rules.py:148`, `storage/writers.py:291, 347`) receive a
  `LocalisedString`. msgspec encodes a Struct natively, so an encoder writes
  valid, wrong JSON instead of raising.
- `isinstance(x, Mapping)` starts to match `InternationalString` at
  `query/_expr.py:1064, 1557, 2387` and `model/version_rewrite.py:235`.
- `x or fallback` stops falling back on empty text (D11), for example
  statcatlib `sources/sdmx.py:115`.
- `value == "text"` becomes `False`, and `f"{value}"` writes the repr into
  output (D11).
- Today #308's variadic `get` reads a second argument as a tag, so
  `name.get("en", "")` raises `ValueError` when `en` is absent, and
  `name.get("en", code.id)` raises for a one-letter ID and returns another
  language's text for a two-letter ID such as `CA` (Catalan). After D3 both
  return the default, so the result is `LocalisedString | str`: slicing
  raises `TypeError` (`docs/cookbook/catalog.md:20`) and printing writes the
  repr (`catalog.md:102`). Other cookbook uses: `resolution.md:48`,
  `inspecting.md:97`, `hierarchies.md:105`, `docs/building_tutorial.md:64`,
  `docs/cookbook/registry.md:75`. The `istring.py:128` docstring example of
  the variadic `get` changes too.
- `repr(InternationalString)` changes form, and `of()` copies an
  `InternationalString` argument (Public API).
- Generated names change: `name_fr-ca` → `name_fr_ca` (D8).
- statcatlib: `_istring_to_map` (`store/store.py:744-748`, 27 calls on 25
  lines) becomes `s.as_dict()`; `store.py:1162, 1171` call `.encode()` on a
  lookup result; `store/scopes.py:999, 1054` build
  `InternationalString(en=r[1] or "")`, which stores `""` under `en` and
  becomes an empty `InternationalString` when `r[1]` is empty.

Migration:

- **Audit run.** `model/istring.py` reads `SDMXLIB_ISTRING_AUDIT` once at
  import. When it is set, `__getitem__`, `get`, `pick`, `values()` and
  `items()` append the caller's `file:line` (`sys._getframe(1)`) to
  `$SDMXLIB_ISTRING_AUDIT_OUT` and continue, so one run lists every read site.
  The hook is committed. The run is
  `SDMXLIB_ISTRING_AUDIT=1 SDMXLIB_ISTRING_AUDIT_OUT=<file> uv run pytest -m "unit or integration"`,
  in sdmxlib for Stage 2 and in statcatlib against the Stage 2 branch for
  Stage 4.
- **Call-site table.** The de-duplicated `src/` sites become rows of
  `docs/design/egm/localised-string/call-sites.md`, committed in sdmxlib
  (Stage 2) and in statcatlib's Stage 4 PR, with columns file:line, old
  expression, new expression and what catches it (pyrefly, a named test, or
  the audit). The sdmxlib table includes the 13 test uses of `emit_pair` and
  `as_dict(copy=False)` in `tests/support/strategies.py`,
  `test_properties_core.py`, `test_shared_empty_values.py` and
  `test_dto.py`.
- **Tests for rows pyrefly cannot catch:** SDMX-JSON writer output validates
  against `tests/schemas/sdmx_json` on the round-trip fixtures;
  `structure_frame(...)["concept"].dtype == pl.String`; statcatlib
  `sources/sdmx.py:115` handles an agency named `""`.
- **Canonical form.** `bundle/_canonical.py:82` becomes `value.as_dict()`, so
  `CANONICAL_FORM` stays `"1"` and the goldens in
  `tests/unit/test_canonical_json.py` pass unregenerated.
- pyrefly's `implicit-bool` is off in both repositories, and no step relies
  on it.

The sdmxlib stages change no storage schema, `SCHEMA_VERSION` or
`CANONICAL_FORM`, so each reverts without a catalog rebuild. statcatlib's
move from sdmxlib `<0.73` (store schema 2.48) to 0.76 or later (2.51)
rebuilds every catalog; that belongs to StatCat-Suite/statcatlib#70.

## Cross-repo contract

- `LocalisedString(text, lang)` with the equality, hashing and validation of
  D6.
- The JSON form of D9.
- A tag is `lang` / `langs` everywhere and is always the lowercase form
  `normalize_tag` returns (StatCat-Suite/statcatlib#88).
- `InvalidTagError` and `MissingTagError` (D7); statcatlib's errors subclass
  sdmxlib's.
- `tag_alias` (D8) for every generated name that contains a tag, in both
  repositories, and `__lang` as the suffix of a column holding the answering
  tag (D13).
- sdmxlib owns the value type, the errors and `tag_alias`; statcatlib owns its
  projection columns.

## Acceptance criteria

**sdmxlib, Stage 1 (StatCat-Suite/sdmxlib#308):**

- `LocalisedString("Annuel", "FR") == LocalisedString("Annuel", "fr")`, with
  `_SEEN_TAGS` cleared and with `fr` already in it.
- `msgspec.json.decode(b'{"text":"x","lang":"FR"}', type=LocalisedString).lang == "fr"`;
  decoding `"fr_CA"` raises `msgspec.ValidationError`.
- `msgspec.structs.replace(LocalisedString("a", "fr"), lang="FR").lang == "fr"`.
- `LocalisedString(LocalisedString("a", "en"), "en")` raises `TypeError`;
  `LocalisedString("a", "fr_CA")` raises `InvalidTagError`.
- `msgspec.json.encode(LocalisedString("Population", "en")) ==
  b'{"text":"Population","lang":"en"}'`.
- `str`, `format`, `==` against a `str` and `bool` behave as D11 lists.
- `normalize_tag("fr_CA")` raises `InvalidTagError` whose message names
  `fr-ca`.

**sdmxlib, Stage 2:**

- Every operation in the D7 table raises or returns as listed;
  `("fr_CA", v) in name.items()` and `"fr_CA" in name.keys()` raise
  `InvalidTagError`; `pick("en", "fr_CA")` raises when `en` is held.
- Speed: `base(s) = s._data.get(normalize_tag("fr"))` against
  `InternationalString.get(s, "fr")` on 1,000,000 strings built with
  `_from_normalized`, each timed five times with `perf_counter` in one
  process with the seen set warm; `median(candidate) <= 1.5 * median(base)`
  (measured 1.44×, `bench_final_split.py`). Marked `bench and bundle` so
  `just ci` runs it; retried once before failing.
- With `_SEEN_TAGS` cleared and `normalize_tag` replaced by a counting
  wrapper, iterating `keys()`, `values()` and `items()` of 1,000 strings over
  3 tags calls it at most 3 times.
- `_from_normalized`'s body is unchanged, and `EAGER_BYTES_PER_ITEM` /
  `EAGER_CALLS_PER_ITEM` in `tests/bench/test_bundle_reads.py` pass
  unchanged.
- The canonical goldens pass unregenerated.
- The `lang` enumeration test covers `tag_alias` and `LocalisedString`.

**statcatlib, Stages 4–5:**

- `msgspec.json.encode` of a label gives `{"text":…,"lang":…}` in that order.
- `tag_alias(t) == t.strip().lower().replace("-", "_")` (today's
  `_language_slug` body, frozen in the test) for every well-formed fixture in
  sdmxlib's `test_language_tags.py` plus every two-letter ASCII pair.
- Every statcatlib `lang` / `langs` parameter refuses a malformed tag with
  `InvalidTagError`, enumerated as sdmxlib's test does, in
  `tests/unit/test_language_tags.py`.
- `just ci` passes.

## Staging

| Stage | Repository and PR | Content | Done when |
|---|---|---|---|
| 0 | statcatlib, StatCat-Suite/statcatlib#90 | Decision 14 names `LocalisedString(text, lang)` and the suite JSON form | Done (`9ff6ddd`) |
| 1 | sdmxlib, StatCat-Suite/sdmxlib#308 | Rename to `LocalisedString`; D6; D9; `InvalidTagError`, raised by `normalize_tag`; D9 stated inline in sdmxlib's language-tags design, its D7, as a suite contract | Done (`ddedb45`, sdmxlib 0.79.0) |
| 2 | sdmxlib, StatCat-Suite/sdmxlib#309 | D3, D4, D7, D8, D11–D13; a "Model classes and fields" section in `docs/design/query-naming.md` with the D1, D2 and D8 rules and a deviations row for `label`/`locale` → `text`/`lang`; the hub's bench scripts turned into gated tests in `tests/bench/`; the audit hook and call-site table | Done (StatCat-Suite/sdmxlib#310, `203cbf4`, sdmxlib 0.79.0) |
| 3 | hub | This design and its evidence (D10) | Done (GH-13) |
| 4 | statcatlib, StatCat-Suite/statcatlib#91, after StatCat-Suite/statcatlib#70 | Move to the sdmxlib release containing Stages 1–2; fix every call-site table row (`_istring_to_map`, `store.py:1162, 1171`, `sources/sdmx.py:115`, `scopes.py:999, 1054`) with public returns kept on `.text` / `as_dict()`; add msgspec as a dependency | statcatlib criteria pass |
| 5 | statcatlib, StatCat-Suite/statcatlib#91; slice 4 of its language-tags RFC | Public label APIs return `LocalisedString`; projection columns `title` and `title__lang`, which settles that RFC's open `title_lang` item; ingest refuses an empty `lang` before `lance.py:1260` | statcatlib criteria pass |

Stage 1 also updates every `LocalizedText` site: sdmxlib
`docs/design/language-tags.md` (Non-goals lines 39–40, D7 lines 195–206,
line 305, Cross-repo contract lines 331–335), `docs/upgrading.md:33, 52-54`,
`model/EGM.md:94, 119`, `istring.py:129`, the exports at
`model/__init__.py:96, 208` and `sdmxlib/__init__.py:172, 345`, and
`tests/unit/test_language_tags.py:155, 202, 207-213, 507` (the key at 507
becomes `sdmxlib.model.istring:LocalisedString`).

Slice 4 of statcatlib's language-tags RFC is broader than Stage 5 (required
`lang`, tuples, gap lists); Stage 5 covers only the `LocalisedString` returns
and the projection columns.

Handoff issues: StatCat-Suite/sdmxlib#309 (Stage 2) and
StatCat-Suite/statcatlib#91 (Stages 4–5) list each stage's criteria. statcatlib's issue also carries the single-repository items moved
out of this design: `Hit.lang`'s `"en"` default and fallback
(`store/store.py:1328, 1386`), about 27 `lang="en"` defaults, the legacy
search filter that compares a slug against stored tags (`lance.py:942`), the
English-first fallback over a stored MAP at `store.py:2425, 2544, 2546`, and
the search `text` column and `CodeHit.text` / `ConceptHit.text` fields, which
hold a composite search document.

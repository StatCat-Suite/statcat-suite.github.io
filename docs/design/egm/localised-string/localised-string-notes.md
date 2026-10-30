# LocalisedString: audit and measurements

Working notes for the EGM brainstorm on modelling sdmxlib's multilingual text
after the SDMX Information Model. Collected 2026-10-30.

## 1. Information model audit (SDMX 3.1 Section 2)

Source: `../sdmxlib/tests/schemas/sdmx_im/SDMX_3-1-0_SECTION_2_FINAL.txt`.

| IM class | Attributes | IM text | sdmxlib today |
|---|---|---|---|
| `InternationalString` | (collection) | "a collection of Localised Strings and supports the representation of text in multiple locales" (l. 1392) | `InternationalString`, a map tag → `str` (`src/sdmxlib/model/istring.py`) |
| `LocalisedString` | `label`, `locale` | "text in one locale (locale is similar to language but includes geographic variations such as Canadian French, US English etc.)" (l. 1396–1404) | `LocalizedText(text, lang)`, only in open PR 308 (`feat/gh-280-language-tags`), unreleased; returned by `InternationalString.pick()` |
| `InternationalUri` | (collection) | "a collection of Localised URIs" (l. 1353) | no class; `AnnotationURL` (`model/annotations.py:14`) holds one URL with `lang` |
| `LocalisedUri` | (locale) | "link to an external description in one locale" (l. 1357) | `AnnotationURL.lang` |
| `LocalisedMemberValue` | `value`, `locale` | "the locale that the values must adhere to in the dataset" (l. 5158–5163) | `RegionValue.lang` (`model/constraint.py:149`) |
| `DatePatternMap` | `locale` | "the locale on which the input will be parsed according to the pattern" (l. 4497) | `DatePatternMap.locale` (`model/mapping.py:483`) |
| `TextAttributeValue`, `TextMeasureValue` | `text` | "the localised text values" (l. 3521, 3591) | metadata / data text values |
| constraint `isPartialLanguage` | flag | — | `is_partial_language` |

The IM uses one word, `locale`, for every language-tagged value. sdmxlib uses
`lang` on two IM-modelled fields (`AnnotationURL`, `RegionValue`), `locale` on
one (`DatePatternMap`), and `lang` / `langs` on about 34 function parameters;
statcatlib has about 56 `lang` parameters.

### Wire spellings

| Format | Spelling | Type |
|---|---|---|
| SDMX-ML | `xml:lang` attribute (W3C XML 1.0 §2.12) | `xs:language` |
| SDMX-JSON 2.0/2.1 | `localisedText` object keyed by tag; `lang` property on member values; `contentLanguages` in `meta`; `hreflang` on links | RFC 5646 pattern |
| SDMX-ML and SDMX-JSON `DatePatternMap` | `locale` | `xs:string` / `string`, **not** a language tag |
| SDMX REST | `Accept-Language` header | RFC 7231 language ranges |

So `lang` is the wire spelling (XML, HTTP, SDMX-JSON) and `locale` is the IM
spelling. `DatePatternMap.locale` is the one IM `locale` that is not
validated as a language tag on the wire.

### A naming risk

In Python, `locale` names POSIX locales: the stdlib `locale` module and
Babel's `Locale` use `fr_CA`, with an underscore. `normalize_tag()` refuses
`fr_CA`. A parameter named `locale=` may invite exactly the input sdmxlib
refuses. The IM's own gloss ("similar to language but includes geographic
variations") matches what BCP 47 calls a language tag (`fr-ca`).

## 2. Measurements

Script: `bench_istring.py` beside this file. Python 3.14.8, attrs, 1,000,000
strings built from already-normalised rows (the store read path,
`_from_normalized`): 60% `en`+`fr`, 25% `en` only, 15% empty (shared
`EMPTY`). Then one fallback lookup `get("de", "fr", "en")` per string, then
one full iteration of each string's entries. Median of five runs, seconds.

| Representation | Build | One lookup each | Iterate all | Memory (MiB) |
|---|---|---|---|---|
| **Lazy**: `dict[str, str]`, value built per lookup (attrs frozen; PR 308 today) | 0.40 | 0.150 | 0.221 | 190 |
| Lazy, value is a `__slots__` class | 0.41 | 0.097 | 0.134 | 190 |
| Lazy, value is a `NamedTuple` built with `tuple.__new__` | 0.41 | 0.111 | 0.163 | 190 |
| **Eager**: `dict[str, LocalisedString]`, attrs frozen | 0.77 | 0.062 | 0.052 | 278 |
| Eager, `NamedTuple` | 0.77 | 0.061 | 0.052 | 289 |
| Eager, `__slots__` class | 0.71 | 0.062 | 0.052 | 256 |

Reading:

- Eager storage costs +0.3 s and +66–100 MiB per million strings, +75–90%
  build time and +35–50% memory.
- It saves 0.04–0.09 s per full pass of lookups. Eager pays off only when the
  average string is looked up about four or more times after it is built.
- The store read path builds many strings that are never read (sdmxlib
  reports ~98% of annotation texts empty, and a codelist read building
  1,159,902 strings, `istring.py` `EMPTY` comment). That favours lazy.
- The value type's construction cost matters on the lazy path: a plain
  `__slots__` class is about 35% cheaper per lookup than attrs `@frozen`.

### API shape the lazy variant supports

`InternationalString` can present `Mapping[tag, LocalisedString]` while
storing `dict[tag, str]`: `s["en"]` builds and returns a `LocalisedString`,
`values()` / `items()` yield them, iteration yields tags, `len` and `in` work
on tags. Built values are equal by value, but `s["en"] is s["en"]` is false.

### A Rust extension

`cargo` is installed; `maturin` is not. Not measured. The measured cost is
Python object allocation (the dict, the strings, the value objects). A Rust
type exposed to Python allocates a Python object too, so it would not remove
that cost per string. Native code helps when whole collections stay native
(for example labels held in Arrow columns, with Python objects made only on
lookup) or in the parsers that build the strings. Both are larger designs than
this one.

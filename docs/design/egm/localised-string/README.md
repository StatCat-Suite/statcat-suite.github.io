# Evidence for the LocalisedString suite design

The design is [`../../localised-string.md`](../../localised-string.md). These
files are the record its decisions and figures come from, kept as written
during drafting on 2026-10-30. File references in them name sibling
checkouts as `../sdmxlib` and `../statcatlib`, read at the commits the design
names.

| File | What it holds |
|---|---|
| `localised-string-notes.md` | The SDMX IM audit, wire spellings and the storage benchmark |
| `bench_istring.py` | Storage: `dict[str, str]` against stored value objects |
| `bench_lookup.py`, `bench_lookup_fair.py` | Lookup cost of the value-type candidates on sdmxlib's `InternationalString` |
| `bench_struct_dunders.py` | `msgspec.Struct` with `__bool__`, `__str__`, `__format__` and a validating `__post_init__` |
| `bench_post_init.py` | The cost of `__post_init__` split into the hook and the tag check |
| `bench_final_type.py`, `bench_final_split.py` | The final value type, the `text` type check and `msgspec.structs.replace` |
| `brainstorm-round1.md` | Goldfish brainstorm, six lenses |
| `final-review.md` | Final review, seven lenses |
| `final-review-2.md` | Review of the final choices, four lenses |

The reports were written against drafts, so their line numbers refer to
earlier versions of the design, and some of their findings were resolved
differently. The design is authoritative.

Run a benchmark from an sdmxlib checkout on `feat/gh-280-language-tags`
or later: `uv run python -I <path to script>`. `bench_lookup_fair.py` loads
`bench_lookup.py` from beside itself.

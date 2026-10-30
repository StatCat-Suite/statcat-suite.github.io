"""Lookup cost on PR 308's real InternationalString: str result vs value objects.

1,000,000 strings built with `_from_normalized` (the store read path); mix
60% en+fr, 25% en, 15% empty. Two lookup shapes:

- per-call: the caller passes a tag each time, which is normalised each time
  (public `get` / `pick`);
- hoisted: the tag is normalised once and looked up in every string (the
  `Codelist.code_map` shape, `_text`).
"""

import statistics
import sys
import time

import msgspec
from attrs import frozen

from sdmxlib.model.istring import InternationalString, LocalizedText, normalize_tag

N = 1_000_000


@frozen
class VAttrs:  # attrs frozen, no converter (lang trusted: it came from the store)
    text: str
    lang: str


class VSlots:
    __slots__ = ("lang", "text")

    def __init__(self, text: str, lang: str) -> None:
        self.text = text
        self.lang = lang


class VStruct(msgspec.Struct, frozen=True, gc=False):
    text: str
    lang: str


def rows():
    out = []
    for i in range(N):
        r = i % 20
        if r < 12:
            out.append({"en": f"Label {i}", "fr": f"Libellé {i}"})
        elif r < 17:
            out.append({"en": f"Label {i}"})
        else:
            out.append({})
    return out


def timed(fn, objs):
    ts = []
    for _ in range(5):
        t0 = time.perf_counter()
        fn(objs)
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts)


def get_as(cls):
    def run(objs):
        for s in objs:
            key = normalize_tag("fr")
            v = s._data.get(key)
            if v is not None:
                cls(v, key)

    return run


def hoisted_as(cls):
    def run(objs):
        key = normalize_tag("fr")
        for s in objs:
            v = s._data.get(key)
            if v is not None:
                cls(v, key)

    return run


def main():
    data = rows()
    t0 = time.perf_counter()
    objs = [InternationalString._from_normalized(p) for p in data]
    build = time.perf_counter() - t0
    print(f"python {sys.version.split()[0]}  build {N:,} via _from_normalized: {build:.3f} s\n")

    cases = {
        "per-call, today get() -> str": lambda o: [s.get("fr") for s in o],
        "per-call, today pick() -> LocalizedText (converter)": lambda o: [s.pick("fr") for s in o],
        "per-call, get -> attrs frozen, no converter": get_as(VAttrs),
        "per-call, get -> __slots__": get_as(VSlots),
        "per-call, get -> msgspec Struct": get_as(VStruct),
        "hoisted, today _text() -> str": lambda o: [s._text("fr") for s in o],
        "hoisted, -> attrs frozen, no converter": hoisted_as(VAttrs),
        "hoisted, -> __slots__": hoisted_as(VSlots),
        "hoisted, -> msgspec Struct": hoisted_as(VStruct),
    }
    base = {}
    for name, fn in cases.items():
        t = timed(fn, objs)
        kind = name.split(",")[0]
        base.setdefault(kind, t)
        print(f"{name:52} {t:6.3f} s  {t / N * 1e9:6.0f} ns/lookup  x{t / base[kind]:.2f}")

    hits = sum(1 for s in objs if "fr" in s)
    print(f"\n{hits:,} of {N:,} strings hold 'fr' (objects are built only for hits)")
    print("sizeof:", {c.__name__: sys.getsizeof(c("Annuel", "fr")) for c in (VAttrs, VSlots, VStruct, LocalizedText)})


if __name__ == "__main__":
    main()

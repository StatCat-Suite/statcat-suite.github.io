"""Same harness, three runs: str baseline, seen-set check only, seen-set + text check."""
import statistics, time
import msgspec
from msgspec.structs import force_setattr
from sdmxlib.model.istring import InternationalString, normalize_tag
_SEEN: set[str] = set()
class NoType(msgspec.Struct, frozen=True, gc=False):
    text: str
    lang: str
    def __post_init__(self):
        lang = self.lang
        if lang not in _SEEN:
            n = normalize_tag(lang)
            if n != lang: force_setattr(self, "lang", n)
            _SEEN.add(n)
class WithType(NoType, frozen=True, gc=False):
    def __post_init__(self):
        if type(self.text) is not str: raise TypeError("text must be a str")
        lang = self.lang
        if lang not in _SEEN:
            n = normalize_tag(lang)
            if n != lang: force_setattr(self, "lang", n)
            _SEEN.add(n)
N = 1_000_000
rows = [{"en": f"L{i}", "fr": f"F{i}"} if i % 20 < 12 else ({"en": f"L{i}"} if i % 20 < 17 else {}) for i in range(N)]
objs = [InternationalString._from_normalized(p) for p in rows]
def mk(cls):
    def f(s):
        key = normalize_tag("fr"); v = s._data.get(key)
        return v if cls is None or v is None else cls(v, key)
    return f
for rep in range(3):
    out = []
    for name, cls in (("str", None), ("seen-set", NoType), ("seen-set+type", WithType)):
        f = mk(cls); ts = []
        for _ in range(5):
            a = time.perf_counter(); [f(s) for s in objs]; ts.append(time.perf_counter() - a)
        out.append((name, statistics.median(ts) / N * 1e9))
    b = out[0][1]
    print("  ".join(f"{n} {v:.0f}ns ({v/b:.2f}x)" for n, v in out))

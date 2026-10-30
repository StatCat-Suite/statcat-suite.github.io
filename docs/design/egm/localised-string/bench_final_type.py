"""Final LocalisedString shape: seen-set tag check plus a str check on text.
Also: does msgspec.structs.replace run __post_init__?"""
import statistics, time
import msgspec
from msgspec.structs import force_setattr, replace
from sdmxlib.model.istring import InternationalString, normalize_tag

_SEEN: set[str] = set()
_MAX = 1024

class LS(msgspec.Struct, frozen=True, gc=False):
    text: str
    lang: str
    def __post_init__(self):
        if type(self.text) is not str:
            raise TypeError("text must be a str")
        lang = self.lang
        if lang not in _SEEN:
            n = normalize_tag(lang)
            if n != lang:
                force_setattr(self, "lang", n)
            if len(_SEEN) >= _MAX:
                _SEEN.clear()
            _SEEN.add(n)

print("replace runs __post_init__:", replace(LS("a", "fr"), lang="FR").lang)
try: LS(LS("a", "en"), "en")
except TypeError as e: print("nested text refused:", e)

N = 1_000_000
rows = [{"en": f"L{i}", "fr": f"F{i}"} if i % 20 < 12 else ({"en": f"L{i}"} if i % 20 < 17 else {}) for i in range(N)]
objs = [InternationalString._from_normalized(p) for p in rows]
def base(s): return s._data.get(normalize_tag("fr"))
def cand(s):
    key = normalize_tag("fr"); v = s._data.get(key)
    return None if v is None else LS(v, key)
res = {}
for name, f in (("str baseline", base), ("LocalisedString", cand)):
    ts = []
    for _ in range(5):
        a = time.perf_counter(); [f(s) for s in objs]; ts.append(time.perf_counter() - a)
    res[name] = statistics.median(ts) / N * 1e9
    print(f"{name:16} {res[name]:5.0f} ns")
print(f"ratio {res['LocalisedString'] / res['str baseline']:.2f}x")

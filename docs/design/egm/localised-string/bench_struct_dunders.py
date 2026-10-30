"""Can a frozen msgspec.Struct carry __bool__/__str__/__format__ and a validating
__post_init__, and what does each cost per lookup on PR 308's class?"""
import statistics, sys, time
import msgspec
from msgspec.structs import force_setattr
from sdmxlib.model.istring import InternationalString, normalize_tag

class Plain(msgspec.Struct, frozen=True, gc=False):
    text: str
    lang: str

class Dunders(msgspec.Struct, frozen=True, gc=False):
    text: str
    lang: str
    def __bool__(self): return bool(self.text)
    def __str__(self): return self.text
    def __format__(self, spec): return format(self.text, spec)

class Validated(Dunders, frozen=True, gc=False):
    def __post_init__(self):
        force_setattr(self, "lang", normalize_tag(self.lang))

# behaviour
v = Validated("Annuel", "FR")
print("normalised:", v.lang, "| bool(''):", bool(Validated("", "fr")), "| str:", str(v), "| fmt:", f"{v:>8}|",
      "| == str:", v == "Annuel", "| eq:", v == Validated("Annuel", "fr"), "| hash ok:", hash(v) == hash(Validated("Annuel", "fr")))
print("json:", msgspec.json.encode(v), "| sorted:", msgspec.json.Encoder(order="sorted").encode(v))
try:
    Validated("x", "fr_CA")
except Exception as e:
    print("refuses fr_CA:", type(e).__name__)
print("sizeof:", sys.getsizeof(Plain("a", "fr")), sys.getsizeof(Validated("a", "fr")))

N = 1_000_000
rows = [{"en": f"L{i}", "fr": f"F{i}"} if i % 20 < 12 else ({"en": f"L{i}"} if i % 20 < 17 else {}) for i in range(N)]
objs = [InternationalString._from_normalized(p) for p in rows]

def make(cls, trusted):
    if cls is None:
        def get(s, tag, default=None):
            key = normalize_tag(tag); v = s._data.get(key)
            return default if v is None else v
    elif trusted:  # build from stored key through a path that skips __post_init__
        new = cls.__new__ if False else None
        def get(s, tag, default=None):
            key = normalize_tag(tag); v = s._data.get(key)
            return default if v is None else cls(v, key)
    else:
        def get(s, tag, default=None):
            key = normalize_tag(tag); v = s._data.get(key)
            return default if v is None else cls(v, key)
    return get

def t(fn):
    ts = []
    for _ in range(5):
        a = time.perf_counter(); fn(); ts.append(time.perf_counter() - a)
    return statistics.median(ts) / N * 1e9

cases = {"str": make(None, 0), "Plain struct": make(Plain, 1), "+ dunders": make(Dunders, 1), "+ __post_init__ normalise": make(Validated, 0)}
base = None
for name, g in cases.items():
    ns = t(lambda: [g(s, "fr") for s in objs]); base = base or ns
    print(f"get -> {name:28} {ns:5.0f} ns  x{ns/base:.2f}")
for name, g in [("str", cases["str"]), ("+ dunders", cases["+ dunders"])]:
    ns = t(lambda: [1 for s in objs if g(s, "fr")])
    print(f"get + truthiness -> {name:15} {ns:5.0f} ns")

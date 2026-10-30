"""Split __post_init__ cost: the hook call itself vs the check inside it."""
import statistics, time
from typing import Annotated
import msgspec
from msgspec.structs import force_setattr
from sdmxlib.model.istring import InternationalString, normalize_tag, TAG_PATTERN

class Plain(msgspec.Struct, frozen=True, gc=False):
    text: str
    lang: str

class EmptyHook(Plain, frozen=True, gc=False):
    def __post_init__(self): pass

_SEEN: set[str] = set()
class CachedCheck(Plain, frozen=True, gc=False):
    def __post_init__(self):
        if self.lang not in _SEEN:
            n = normalize_tag(self.lang)
            if n != self.lang:
                force_setattr(self, "lang", n)
            _SEEN.add(n)

class Full(Plain, frozen=True, gc=False):
    def __post_init__(self):
        force_setattr(self, "lang", normalize_tag(self.lang))

# decode-time constraint: msgspec checks Meta only when decoding/converting
class Decoded(msgspec.Struct, frozen=True, gc=False):
    text: str
    lang: Annotated[str, msgspec.Meta(pattern=f"^(?:{TAG_PATTERN.lower()})$")]

print("direct construction skips Meta:", Decoded("x", "FR_CA").lang)
try:
    msgspec.json.decode(b'{"text":"x","lang":"fr_CA"}', type=Decoded)
except msgspec.ValidationError as e:
    print("decode refuses:", str(e)[:60])

N = 1_000_000
rows = [{"en": f"L{i}", "fr": f"F{i}"} if i % 20 < 12 else ({"en": f"L{i}"} if i % 20 < 17 else {}) for i in range(N)]
objs = [InternationalString._from_normalized(p) for p in rows]
def make(cls):
    def get(s, tag, default=None):
        key = normalize_tag(tag); v = s._data.get(key)
        return default if v is None else (v if cls is None else cls(v, key))
    return get
base = None
for name, cls in {"str": None, "Plain": Plain, "empty __post_init__": EmptyHook, "cached check": CachedCheck, "full normalise": Full}.items():
    g = make(cls); ts = []
    for _ in range(5):
        a = time.perf_counter(); [g(s, "fr") for s in objs]; ts.append(time.perf_counter() - a)
    ns = statistics.median(ts) / N * 1e9; base = base or ns
    print(f"{name:22} {ns:5.0f} ns  x{ns/base:.2f}")

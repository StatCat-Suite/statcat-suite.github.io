"""Same-shape comparison: a Mapping-style get(tag) returning str vs value objects."""
import sys
sys.argv = [sys.argv[0]]
import importlib.util, statistics, time
spec = importlib.util.spec_from_file_location("bl", __file__.replace("_fair", ""))
bl = importlib.util.module_from_spec(spec); spec.loader.exec_module(bl)
from sdmxlib.model.istring import InternationalString, normalize_tag

def make(cls):
    if cls is None:
        def get(s, tag, default=None):
            key = normalize_tag(tag)
            v = s._data.get(key)
            return default if v is None else v
    else:
        def get(s, tag, default=None):
            key = normalize_tag(tag)
            v = s._data.get(key)
            return default if v is None else cls(v, key)
    return get

objs = [InternationalString._from_normalized(p) for p in bl.rows()]
base = None
for name, cls in {"str": None, "attrs frozen": bl.VAttrs, "__slots__": bl.VSlots, "msgspec Struct": bl.VStruct}.items():
    g = make(cls)
    t = bl.timed(lambda o: [g(s, "fr") for s in o], objs)
    base = base or t
    print(f"get(tag) -> {name:15} {t / bl.N * 1e9:5.0f} ns/lookup  x{t / base:.2f}")

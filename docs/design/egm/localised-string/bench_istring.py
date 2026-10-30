"""Compare InternationalString representations on a store-read workload.

Workload: build N strings from already-normalised {tag: text} rows (the store
read path, `_from_normalized`), then look each up with a fallback tuple, then
iterate every entry. Mix: 60% en+fr, 25% en only, 15% empty (shared EMPTY).
"""

import gc
import statistics
import sys
import time
import tracemalloc
from typing import NamedTuple

from attrs import frozen

N = 1_000_000


# ── value types ───────────────────────────────────────────────────────────
@frozen
class LSAttrs:
    label: str
    locale: str


class LSTuple(NamedTuple):
    label: str
    locale: str


class LSSlots:
    __slots__ = ("label", "locale")

    def __init__(self, label: str, locale: str) -> None:
        self.label = label
        self.locale = locale


# ── A: today. dict[str, str]; a lookup builds the value type ──────────────
class A:
    __slots__ = ("_d",)

    @classmethod
    def build(cls, pairs):
        o = cls.__new__(cls)
        o._d = {sys.intern(k): v for k, v in pairs.items()}
        return o

    def get(self, *tags):
        d = self._d
        for t in tags:
            v = d.get(t)
            if v is not None:
                return LSAttrs(v, t)
        return None

    def values(self):
        return [LSAttrs(v, k) for k, v in self._d.items()]


# ── B/C/D: eager dict[str, LocalisedString] ───────────────────────────────
def make_eager(ls):
    class Eager:
        __slots__ = ("_d",)

        @classmethod
        def build(cls, pairs):
            o = cls.__new__(cls)
            o._d = {(t := sys.intern(k)): ls(v, t) for k, v in pairs.items()}
            return o

        def get(self, *tags):
            d = self._d
            for t in tags:
                v = d.get(t)
                if v is not None:
                    return v
            return None

        def values(self):
            return list(self._d.values())

    return Eager


B = make_eager(LSAttrs)
C = make_eager(LSTuple)
D = make_eager(LSSlots)


# ── E: tuple-backed attrs-free value built with tuple.__new__ directly ────
_tnew = tuple.__new__


class E(make_eager(LSTuple)):
    __slots__ = ()

    @classmethod
    def build(cls, pairs):
        o = cls.__new__(cls)
        o._d = {(t := sys.intern(k)): _tnew(LSTuple, (v, t)) for k, v in pairs.items()}
        return o


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


def run(cls, data, empty):
    gc.collect()
    t0 = time.perf_counter()
    objs = [cls.build(p) if p else empty for p in data]
    t1 = time.perf_counter()
    for o in objs:
        o.get("de", "fr", "en")
    t2 = time.perf_counter()
    for o in objs:
        o.values()
    t3 = time.perf_counter()
    return t1 - t0, t2 - t1, t3 - t2


def mem(cls, data, empty):
    gc.collect()
    tracemalloc.start()
    objs = [cls.build(p) if p else empty for p in data]
    cur, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del objs
    return cur


def main():
    data = rows()
    variants = {"A str map": A, "B attrs": B, "C NamedTuple": C, "D slots": D, "E tuple.__new__": E}
    print(f"python {sys.version.split()[0]}, N={N:,}")
    print(f"{'variant':16} {'build s':>8} {'get s':>7} {'iter s':>7} {'MiB':>7}")
    for name, cls in variants.items():
        empty = cls.build({})
        times = [run(cls, data, empty) for _ in range(5)]
        b, g, it = (statistics.median(t[i] for t in times) for i in range(3))
        m = mem(cls, data, empty) / 2**20
        print(f"{name:16} {b:8.3f} {g:7.3f} {it:7.3f} {m:7.1f}")


if __name__ == "__main__" and "--lazy" not in sys.argv:
    main()


# ── Lazy variants: dict[str, str], value built at lookup with a cheaper type ─
def make_lazy(ls, fast=False):
    class Lazy(A):
        __slots__ = ()

        def get(self, *tags):
            d = self._d
            for t in tags:
                v = d.get(t)
                if v is not None:
                    return _tnew(LSTuple, (v, t)) if fast else ls(v, t)
            return None

        def values(self):
            if fast:
                return [_tnew(LSTuple, (v, k)) for k, v in self._d.items()]
            return [ls(v, k) for k, v in self._d.items()]

    return Lazy


if __name__ == "__main__" and "--lazy" in sys.argv:
    data = rows()
    for name, cls in {"A attrs (today)": A, "A' slots": make_lazy(LSSlots), "A'' tuple.__new__": make_lazy(LSTuple, fast=True)}.items():
        empty = cls.build({})
        times = [run(cls, data, empty) for _ in range(5)]
        b, g, it = (statistics.median(t[i] for t in times) for i in range(3))
        print(f"{name:18} build {b:.3f}  get {g:.3f}  iter {it:.3f}")

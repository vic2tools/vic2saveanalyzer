#!/usr/bin/env python3
"""
Hold the Rust scanner to the Python parser, save by save.

There are now two implementations of the province scan, which is a liability
unless something proves continuously that they agree. This parses real saves
both ways -- once with `scanner/` and once with it switched off -- and
compares every field of every nation, exactly. Not approximately: the floats
are accumulated in the same order on both sides, so they should match to the
bit, and a tolerance here would hide the very drift this exists to catch.

    python3 testkit/parity.py "/path/to/saves" [how many]

Says nothing and exits 0 when they agree.
"""

import glob
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import fastscan                                            # noqa: E402
import v2parse                                             # noqa: E402
import vic2_analyzer as va                                 # noqa: E402


def normalise(o):
    """
    Sets and defaultdicts compare as their plain equivalents.

    Dictionaries keep their order. Sorting them here is the obvious thing to
    do and it is wrong: several tables downstream sort by a value with a
    stable sort, so two entries of equal size come out in the order the file
    first mentioned them. Sorted away, a scanner that emitted its counts
    alphabetically looked identical here and changed a real report.
    """
    if isinstance(o, dict):
        return [(k, normalise(v)) for k, v in o.items()]
    if isinstance(o, set):
        return sorted(o)
    if isinstance(o, (list, tuple)):
        return [normalise(v) for v in o]
    return o


def really_used(path):
    """
    Whether `analyze_save` got a usable answer out of the binary.

    A scanner that is present but not understood is invisible to every
    other check here: the analyzer falls back to Python, the numbers come
    out identical -- that is the whole point of the fallback -- and the
    only sign is that a cold build takes four times as long. It has
    happened: the Rust half of a protocol change was reverted by accident
    and the Python half shipped without it, so every save was read twice,
    the second time entirely in Python, and every test passed.

    So the fallback is a thing to be told about, not just relied on.
    """
    seen = []
    real = fastscan.collect

    def watched(running):
        got = real(running)
        seen.append(got is not None)
        return got

    fastscan.collect = watched
    try:
        va.analyze_save(path, verbose=False)
    finally:
        fastscan.collect = real
    return bool(seen) and seen[0]


def both_ways(path):
    """One save, parsed with the scanner and without it."""
    v2parse.register_pop_types([])
    fast = va.analyze_save(path, verbose=False)
    real_scan = fastscan.scan
    fastscan.scan = lambda *a, **k: None
    try:
        slow = va.analyze_save(path, verbose=False)
    finally:
        fastscan.scan = real_scan
    return fast, slow


def compare(path):
    """Every difference between the two readings of one save."""
    (fast_meta, fast_nat), (slow_meta, slow_nat) = both_ways(path)
    bad = []
    for key in sorted(set(fast_meta) | set(slow_meta)):
        if normalise(fast_meta.get(key)) != normalise(slow_meta.get(key)):
            bad.append("meta[%s]" % key)
    tags = sorted(set(fast_nat) | set(slow_nat))
    for tag in tags:
        a, b = fast_nat.get(tag, {}), slow_nat.get(tag, {})
        for key in sorted(set(a) | set(b)):
            if normalise(a.get(key)) != normalise(b.get(key)):
                bad.append("%s.%s" % (tag, key))
    return bad, len(tags)


def main():
    where = sys.argv[1] if len(sys.argv) > 1 else "."
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    if fastscan.available() is None:
        print("no scanner built, so nothing to compare; "
              "run `cargo build --release` in scanner/")
        return 0
    files = sorted(glob.glob(os.path.join(where, "*.v2")))[:limit]
    if not files:
        print("no saves in %s" % where)
        return 2
    v2parse.register_pop_types([])
    if not really_used(files[0]):
        print("the scanner at %s is built, and the analyzer could not use\n"
              "its answer -- so every save below was read in Python twice\n"
              "over and the comparison is of Python against itself. Rebuild\n"
              "it: cargo build --release --manifest-path scanner/Cargo.toml"
              % fastscan.available())
        return 1
    worst = 0
    for path in files:
        bad, tags = compare(path)
        name = os.path.basename(path)
        if bad:
            worst = 1
            print("%-26s DIFFERS in %d field(s):" % (name, len(bad)))
            for field in bad[:12]:
                print("      %s" % field)
            if len(bad) > 12:
                print("      ... and %d more" % (len(bad) - 12))
        else:
            print("%-26s identical across %d nations" % (name, tags))
    return worst


if __name__ == "__main__":
    sys.exit(main())

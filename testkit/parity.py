#!/usr/bin/env python3
"""
Hold the Rust scanner to the Python parser, save by save.

There are now two implementations of the province scan, which is a liability
unless something proves continuously that they agree. This parses real saves
both ways -- once with `scanner/` and once with it switched off -- and
compares every field of every nation, exactly. Not approximately: the floats
are accumulated in the same order on both sides, so they should match to the
bit, and a tolerance here would hide the very drift this exists to catch.

    python3 testkit/parity.py ["/path/to/saves"] [how many]

Given no saves it builds one, with `savefmt.furnished` -- two nations,
four cultures, pops of every mobilizable type, provinces cored, colonial,
occupied and built on, and countries with states, factories, reforms, an
army and a navy. That covers sixty-eight of the record's seventy-two
fields, and it means this runs on a machine that has never seen a
Victoria 2 campaign. Real saves are still better when there are any: they
carry shapes nobody thought to write on purpose.

Says nothing and exits 0 when they agree.
"""

import glob
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import fastscan                                            # noqa: E402
import readsave                                            # noqa: E402
import savefmt                                             # noqa: E402
import vic2_analyzer as va                                 # noqa: E402


# Which country lines are reform choices. Only a mod can say, and both
# readers have to be told the same answer or half the country block is dark
# on both sides -- which is agreement about nothing.
REFORMS = ("vote_franschise", "war_policy")


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
    """
    One save, parsed with the scanner and without it.

    Switched off by the argument `analyze_save` has for it, and then checked
    to have stayed off. It used to be switched off by replacing
    `fastscan.scan` -- which `analyze_save` does not call. It calls `start`,
    `head` and `collect`, because it works between the scanner's two halves
    rather than waiting for both. So the "slow" read ran the scanner as well,
    this compared the scanner against itself, and it had been reporting
    "identical across 41 nations" for free.

    That is the failure this whole check exists to notice -- a comparison
    that has quietly stopped comparing -- so the guard below is not
    belt-and-braces. It is the check on the check.
    """
    readsave.PLAIN._replace(reform_keys=REFORMS).apply()
    fast = va.analyze_save(path, verbose=False)

    started = []
    real_start = fastscan.start

    def watched(*a, **k):
        started.append(1)
        return real_start(*a, **k)

    fastscan.start = watched
    try:
        slow = va.analyze_save(path, verbose=False, use_scanner=False)
    finally:
        fastscan.start = real_start
    if started:
        raise AssertionError(
            "the Python-only read started the scanner %d time(s), so this "
            "would have compared the scanner against itself" % len(started))
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
    # Which lines of a country block are reforms is told to both readers,
    # and a run that tells neither leaves that half of the country block dark
    # on both sides -- which is agreement about nothing.
    readsave.PLAIN._replace(reform_keys=REFORMS).apply()

    holding = None
    files = sorted(glob.glob(os.path.join(where, "*.v2")))[:limit]
    if not files:
        holding = tempfile.mkdtemp(prefix="vic2parity")
        files = [savefmt.furnished(os.path.join(holding, "furnished.v2"))]
        print("no saves in %s, so comparing on one built here" % where)
    try:
        return run(files)
    finally:
        if holding:
            shutil.rmtree(holding, ignore_errors=True)


def run(files):
    """[exit code] for the saves given."""
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

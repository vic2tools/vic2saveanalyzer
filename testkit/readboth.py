"""
One save read twice, once through the Rust scanner and once without it, and
every place the two readings differ.

`parity.py`, `awkward.py` and `countries.py` all hold the scanner to the
Python reader this way, so they share the one way of doing it. The two
smaller checks used to switch the scanner off by replacing `fastscan.scan`,
which `analyze_save` does not call, so their "Python" reading went through
the scanner as well and they compared the scanner with itself. `parity.py`
had been fixed for exactly that and the other two had not.
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import fastscan                                            # noqa: E402
import readsave                                            # noqa: E402


def both_ways(path, reading):
    """
    (the scanner's reading, the Python reading) of one save, both read
    the way `reading` says.

    The scanner is switched off with the argument `analyze_save` has for it,
    and then checked to have stayed off. That guard is what this module is
    for: a comparison that has quietly stopped comparing still says the two
    agree.
    """
    fast = readsave.analyze_save(path, reading, verbose=False)

    started = []
    real_start = fastscan.start

    def watched(*a, **k):
        started.append(1)
        return real_start(*a, **k)

    fastscan.start = watched
    try:
        slow = readsave.analyze_save(path, reading, verbose=False,
                                     use_scanner=False)
    finally:
        fastscan.start = real_start
    if started:
        raise AssertionError(
            "the Python-only read started the scanner %d time(s), so this "
            "would have compared the scanner against itself" % len(started))
    return fast, slow


def normalise(o):
    """
    Sets and defaultdicts compare as their plain equivalents.

    Dictionaries keep their order. Sorting them here is the obvious thing to
    do and it is wrong: several tables downstream sort by a value with a
    stable sort, so two entries of equal size come out in the order the file
    first mentioned them. Sorted away, a scanner that emitted its counts
    alphabetically looked identical here and changed a real report.

    A number carries the kind of number it is, because `0 == 0.0` in Python
    and the CSV does not agree. `nation._add_if` exists for exactly this: a
    province with no naval base leaves `naval_base_levels` the int 0 it
    started as, rather than adding a float nought to it and making it 0.0.
    `True` is an int in Python too, and `True` and `1` are two different
    things in a CSV, so a bool is a third kind.
    """
    if isinstance(o, dict):
        return [(k, normalise(v)) for k, v in o.items()]
    if isinstance(o, set):
        return sorted(o)
    if isinstance(o, (list, tuple)):
        return [normalise(v) for v in o]
    if isinstance(o, bool):
        return ("bool", o)
    if isinstance(o, int):
        return ("int", o)
    if isinstance(o, float):
        return ("float", o)
    return o


def differences(fast, slow):
    """
    [(where, the scanner's value, the Python value)] for every field of the
    save's meta and of every nation that the two readings disagree on.
    """
    (fast_meta, fast_nat), (slow_meta, slow_nat) = fast, slow
    out = []
    for key in sorted(set(fast_meta) | set(slow_meta)):
        a, b = fast_meta.get(key), slow_meta.get(key)
        if normalise(a) != normalise(b):
            out.append(("meta[%s]" % key, a, b))
    for tag in sorted(set(fast_nat) | set(slow_nat)):
        a, b = fast_nat.get(tag, {}), slow_nat.get(tag, {})
        for key in sorted(set(a) | set(b)):
            if normalise(a.get(key)) != normalise(b.get(key)):
                out.append(("%s.%s" % (tag, key), a.get(key), b.get(key)))
    return out

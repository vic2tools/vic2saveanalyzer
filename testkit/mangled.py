#!/usr/bin/env python3
"""
Feed the reader damaged saves and check it never crashes.

`edges.py` writes saves that are unusual but well formed. This writes ones
that are broken: a file cut in half, bytes flipped at random, a chunk
missing from the middle, braces rubbed out, digits turned into letters. A
save folder collects these in real life -- a crash while the game was
writing, a bad sector, a sync client copying a file mid-write -- and the
right answer to every one of them is either to read what is there or to
refuse it in a sentence. A stack trace is never the right answer, and it
would take the whole campaign down.

    python3 testkit/mangled.py [path/to/one/save.v2] [how many]

The mutations are seeded, so a failure is reproducible. Each is tried
against both readers, because the Rust one and the Python one meet
different halves of a broken file.
"""

import os
import random
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

SEED = 20260921


def damage(raw, how, rng):
    """One save, broken the way `how` says."""
    b = bytearray(raw)
    if how == "cut in half":
        del b[rng.randrange(len(b) // 4, len(b)):]
    elif how == "bytes flipped":
        for _ in range(60):
            b[rng.randrange(len(b))] = rng.randrange(256)
    elif how == "a piece missing":
        at = rng.randrange(0, max(1, len(b) - 5000))
        del b[at:at + rng.randrange(1, 5000)]
    elif how == "braces rubbed out":
        for _ in range(40):
            at = rng.randrange(len(b))
            if b[at:at + 1] in (b"{", b"}"):
                b[at] = ord(" ")
    elif how == "digits turned to letters":
        for _ in range(200):
            at = rng.randrange(len(b))
            if 48 <= b[at] <= 57:
                b[at] = rng.choice(b"xyz.-e")
    elif how == "the header gone":
        del b[:rng.randrange(1, 300)]
    elif how == "nothing but nulls in the middle":
        at = rng.randrange(0, max(1, len(b) - 9000))
        b[at:at + 8000] = b"\0" * 8000
    return bytes(b)


HOW = ["cut in half", "bytes flipped", "a piece missing", "braces rubbed out",
       "digits turned to letters", "the header gone",
       "nothing but nulls in the middle"]


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else ""
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    if not source or not os.path.isfile(source):
        print(__doc__.strip())
        return 2

    import v2parse
    import readsave
    v2parse.register_pop_types([])

    raw = open(source, "rb").read()
    rng = random.Random(SEED)
    holding = tempfile.mkdtemp(prefix="vic2mangled")
    path = os.path.join(holding, "broken.v2")
    crashes, read, refused = [], 0, 0
    try:
        for how in HOW:
            for _ in range(rounds):
                with open(path, "wb") as fh:
                    fh.write(damage(raw, how, rng))
                try:
                    readsave.analyze_save(path, verbose=False)
                    read += 1
                except (ValueError, OSError):
                    refused += 1            # a sentence, which is allowed
                except BaseException:       # noqa: BLE001
                    crashes.append(
                        (how, traceback.format_exc().strip().splitlines()[-1]))
    finally:
        shutil.rmtree(holding, ignore_errors=True)

    tried = len(HOW) * rounds
    print("  %d damaged saves: %d read, %d refused, %d crashed"
          % (tried, read, refused, len(crashes)))
    if crashes:
        print("\nPROBLEMS:")
        seen = set()
        for how, last in crashes:
            if (how, last) in seen:
                continue
            seen.add((how, last))
            print("  %-28s %s" % (how, last[:80]))
        return 1
    print("\nnothing crashed; every broken save was read or refused")
    return 0


if __name__ == "__main__":
    sys.exit(main())

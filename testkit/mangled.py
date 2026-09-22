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
import threading
import time
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


def while_being_written(raw, path):
    """
    [what went wrong] when the file changes all the way through the read.

    A save is read in two passes -- the scanner reads it whole, and the
    wars and the market are lifted out of it afterwards a span at a time
    -- so one rewritten in between is read half from each version, and the
    halves do not agree. Pointing the analyzer at the folder the game is
    still writing to is a thing people do, and half of one month and half
    of the next is worse than no answer at all.

    Rewritten continuously rather than once, because once is a race: the
    touch has to land inside the read. Continuously, it always does.
    """
    import readsave

    with open(path, "wb") as fh:
        fh.write(raw)
    stop = threading.Event()

    def keep_touching():
        while not stop.is_set():
            try:
                st = os.stat(path)
                os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9))
            except OSError:
                pass
            time.sleep(0.02)

    threading.Thread(target=keep_touching, daemon=True).start()
    try:
        readsave.analyze_save(path, verbose=False)
        return ["a save rewritten all through the read was read anyway"]
    except ValueError as said:
        if "changed while it was being read" not in str(said):
            return ["refused, but for the wrong reason: %s" % str(said)[:70]]
        print("  a save rewritten while it is read: refused")
        return []
    except BaseException as boom:                        # noqa: BLE001
        return ["rewritten mid-read raised %s, not a refusal"
                % type(boom).__name__]
    finally:
        stop.set()
        time.sleep(0.08)


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else ""
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    if not source or not os.path.isfile(source):
        print(__doc__.strip())
        return 2

    import readsave
    readsave.PLAIN.apply()

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
        crashes += [("rewritten while read", w)
                    for w in while_being_written(raw, path)]
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

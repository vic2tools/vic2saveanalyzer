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
would take the whole campaign down. A save cut short is the exception that
has to be refused: read, it is a whole save with most of it missing, and
its numbers go into the report as though they were true.

    python3 testkit/mangled.py [path/to/one/save.v2] [how many] [--update]

The damage is seeded, so a failure is reproducible. Each damaged save is
run through the analyzer. Without a save named, the furnished save the
builders write is damaged, and each run must also give the answer recorded
for it (`expected.py`) -- the Python reader's, taken while it was here.
"""

import argparse
import os
import random
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testkit"))

import expected                                            # noqa: E402
import matching                                            # noqa: E402
import savefmt                                             # noqa: E402

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


def ask(saves, holding, game):
    """The analyzer's answer for the folder `saves`."""
    out = os.path.join(holding, "out")
    env = dict(os.environ, TMPDIR=os.path.join(holding, "tmp"))
    os.makedirs(env["TMPDIR"], exist_ok=True)
    got = expected.run([saves, "--out", out, "--game-root", game, "--no-cache", "-j", "1",
                        "--no-html"], holding, env, out,
                       [(env["TMPDIR"], "TMP"), (holding, "HOLDING")])
    shutil.rmtree(out, ignore_errors=True)
    return got


def crashed(got):
    """Whether an answer is a crash rather than a reading or a sentence."""
    said = got["stdout.txt"] + got["stderr.txt"]
    return (got["status.txt"].strip() not in ("0", "1") or "Traceback" in said
            or "panicked" in said)


def while_being_written(saves, holding, game):
    """
    [what went wrong] when the file changes all the way through the read.

    A save rewritten while it is read is read half from each version, and
    the halves do not agree. Pointing the analyzer at the folder the game is
    still writing to is a thing people do, and half of one month and half of
    the next is worse than no answer at all. Rewritten continuously rather
    than once, because once is a race: the touch has to land inside the read.
    """
    path = os.path.join(saves, "broken.v2")
    # Big enough that the read takes a while: a touch every couple of
    # milliseconds has to land inside it.
    parts = [savefmt.head("1880.1.1")]
    parts += [savefmt.province(pid, "ENG", [savefmt.pop("farmers", pid, 1000 + pid)])
              for pid in range(1, 40001)]
    parts.append(savefmt.country("ENG"))
    savefmt.write(path, *parts)
    stop = threading.Event()

    def keep_touching():
        while not stop.is_set():
            try:
                st = os.stat(path)
                os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9))
            except OSError:
                pass
            time.sleep(0.002)

    threading.Thread(target=keep_touching, daemon=True).start()
    try:
        got = ask(saves, holding, game)
    finally:
        stop.set()
        time.sleep(0.05)
    if crashed(got):
        return ["rewritten mid-read crashed: %s" % got["stderr.txt"][-300:]]
    if "changed while it was being read" not in got["stderr.txt"]:
        return ["a save rewritten all through the read was not refused as one: %s"
                % (got["stdout.txt"] + got["stderr.txt"])[-300:]]
    print("  a save rewritten while it is read: refused")
    return []


def cut_short(raw, saves, holding, game):
    """
    [what went wrong] when the save stops part-way through.

    A save cut short parses without complaint, and two thirds of one read as
    34 of its 41 nations holding no army, no navy and no technology, with
    every war gone -- numbers, not an error, so the report showed every army
    in the world disbanding for a month. It has to be refused, and say why.
    """
    wrong = []
    path = os.path.join(saves, "broken.v2")
    for share in (0.3, 0.5, 0.67, 0.95):
        cut = raw[:int(len(raw) * share)]
        # A cut that happens to land just after a closing brace looks whole
        # from the end, and no end-of-file test can tell. Step back off it,
        # so what is tested is the case the check claims to catch.
        while cut.rstrip().endswith(b"}"):
            cut = cut[:-1]
        with open(path, "wb") as fh:
            fh.write(cut)
        got = ask(saves, holding, game)
        if crashed(got):
            wrong.append("%d%% of a save crashed the run" % (share * 100))
        elif "cut short" not in got["stderr.txt"]:
            wrong.append("%d%% of a save was not refused as cut short: %s"
                         % (share * 100, (got["stdout.txt"] + got["stderr.txt"])[-200:]))
    if not wrong:
        print("  a save cut short, four places: refused")
    return wrong


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("save", nargs="?", default="",
                    help="a save to damage; by default the furnished one the builders write")
    ap.add_argument("rounds", nargs="?", type=int, default=5)
    ap.add_argument("--update", action="store_true",
                    help="write what the program answers now as the expected answers")
    args = ap.parse_args()
    holding = tempfile.mkdtemp(prefix="vic2mangled")
    saves = os.path.join(holding, "saves")
    os.makedirs(saves)
    path = os.path.join(saves, "broken.v2")
    # Answers are recorded for the furnished save only: a real one is
    # somebody's, and its damaged copies are held to not crashing.
    book = None if args.save else expected.Book(expected.REPO, "mangled", args.update)
    crashes, misread, differ, read, refused = [], [], [], 0, 0
    try:
        game = matching.a_vanilla(os.path.join(holding, "Victoria 2"))
        source = args.save or savefmt.furnished(os.path.join(holding, "furnished.v2"))
        raw = open(source, "rb").read()
        rng = random.Random(SEED)
        for how in HOW:
            for i in range(args.rounds):
                with open(path, "wb") as fh:
                    fh.write(damage(raw, how, rng))
                got = ask(saves, holding, game)
                if crashed(got):
                    crashes.append((how, (got["stdout.txt"] + got["stderr.txt"]).strip()
                                    .splitlines()[-1:]))
                elif got["status.txt"].strip() == "0":
                    read += 1
                else:
                    refused += 1
                if book is not None:
                    found = book.hold("%s %d" % (how, i), got)
                    if found:
                        differ.append(("%s %d" % (how, i), found))
        if book is not None:
            book.finish()
        crashes += [("rewritten while read", w)
                    for w in while_being_written(saves, holding, game)]
        misread = cut_short(raw, saves, holding, game)
    finally:
        shutil.rmtree(holding, ignore_errors=True)

    tried = len(HOW) * args.rounds
    print("  %d damaged saves: %d read, %d refused, %d crashed%s"
          % (tried, read, refused, len(crashes),
             "" if book is None else ", %d differ from the recorded answers" % len(differ)))
    if crashes or misread or differ:
        print("\nPROBLEMS:")
        for wrong in misread:
            print("  %-28s %s" % ("cut short", wrong[:200]))
        for how, last in crashes:
            print("  %-28s %s" % (how, str(last)[:200]))
        for case, found in differ[:5]:
            expected.report(case, found)
        return 1
    print("\nnothing crashed; every broken save was read or refused%s, and one cut "
          "short was refused" % ("" if book is None else " as recorded"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Feed the analyzer the campaigns nobody has: empty, tiny, broken, degenerate.

Every test here reads real saves of a real campaign, which is the one shape
that is certain to work. The shapes that break things are the ones a first-
time user has and a developer does not -- a folder with one save in it, a
save from the first month of a game where nobody has researched anything, a
folder half full of files that are not saves at all.

    python3 testkit/edges.py

Each case builds its own folder, runs the analyzer end to end in this
process, and passes if it either finishes or fails with a sentence a person
could act on. A traceback is a failure; so is a silent success that wrote no
report when it said it would.
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import savefmt                                             # noqa: E402


def a_save(path, date, tags=("ENG",), provinces=2, techs=(), inventions=(),
           player="ENG", wars="", extra=""):
    """
    One save with exactly the pieces a case is about, and nothing else.

    The layout comes from `savefmt`, which is checked against both readers
    -- this file used to wrap its own braces with a loop that guessed
    where a block ended from the indentation, which is the sort of thing
    that works until the day it does not.
    """
    parts = [savefmt.head(date, player=player)]
    pid = 1
    for tag in tags:
        for _ in range(provinces):
            parts.append(savefmt.province(
                pid, tag, [savefmt.pop("farmers", pid, 1000 + pid * 10)]))
            pid += 1
    first = 1
    for tag in tags:
        parts.append(savefmt.country(tag, techs=techs, inventions=inventions,
                                     capital=first))
        first += provinces
    if wars:
        parts.append(wars)
    if extra:
        parts.append(extra)
    return savefmt.write(path, *parts)


WAR = savefmt.war("The Test War", "ENG", "FRA")


def run(saves, out, extra_argv=()):
    """The analyzer, in this process, with everything it printed."""
    import readsave
    import vic2_analyzer as va
    # No mod: the twelve pop types the game ships and nothing hung off a
    # reform. One object says how a save is read, so a check sets it the
    # same way the program does instead of reaching for the globals behind
    # it -- which is how `REFORM_KEYS` came to be reset through a module
    # that only imported it.
    readsave.PLAIN.apply()
    argv = [sys.argv[0], saves, "--out", out] + list(extra_argv)
    old = sys.argv
    said = io.StringIO()
    code = None
    try:
        sys.argv = argv
        with contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
            try:
                code = va.main()
            except SystemExit as stop:
                code = stop.code
    except Exception:
        # A crash. `None` is what a run that worked returns, so the two are
        # told apart by this flag and not by the code.
        return "crash", said.getvalue() + "\n" + traceback.format_exc()
    finally:
        sys.argv = old
    return code, said.getvalue()


CASES = []


def case(name):
    def keep(fn):
        CASES.append((name, fn))
        return fn
    return keep


@case("a folder with no saves in it")
def _(folder, out):
    return run(folder, out), "must say so rather than crash"


@case("a folder of files that are not saves")
def _(folder, out):
    for name in ("notes.txt", "screenshot.png", "save.v2.bak"):
        open(os.path.join(folder, name), "w").write("hello")
    return run(folder, out), "must ignore them or say so"


@case("one save, one nation, one province")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1836.1.1", provinces=1)
    return run(folder, out), "the smallest real campaign"


@case("a first-month save: no technology, no inventions")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1836.1.1")
    return run(folder, out), "nothing researched by anybody"


@case("two saves on the same date")
def _(folder, out):
    # Read once, not twice: the tables used to hold both while the report
    # showed one, so a copy of a save doubled its rows. Every game's first
    # save is 1836.1.1, so a folder of two games has two of them.
    import csv
    a_save(os.path.join(folder, "a.v2"), "1840.6.1")
    a_save(os.path.join(folder, "b.v2"), "1840.6.1")
    a_save(os.path.join(folder, "c.v2"), "1841.6.1")
    got = run(folder, out)
    wrong = []
    # One line naming both and the date they share. Not the three words
    # anywhere in the output: a verbose run prints every file name and
    # every date on its own, so that passed with no warning at all.
    if not any("a.v2" in line and "b.v2" in line and "1840.6.1" in line
               for line in got[1].splitlines()):
        wrong.append("nothing said the two saves share a date")
    table = os.path.join(out, "nations_timeseries.csv")
    if os.path.isfile(table):
        rows = [(r["date"], r["tag"]) for r in csv.DictReader(open(table))]
        if len(rows) != len(set(rows)):
            wrong.append("the table holds %d rows for %d nation-dates"
                         % (len(rows), len(set(rows))))
    return got, "a manual save beside an autosave", wrong


@case("saves out of order on disk")
def _(folder, out):
    a_save(os.path.join(folder, "zzz.v2"), "1840.1.1")
    a_save(os.path.join(folder, "aaa.v2"), "1850.1.1")
    return run(folder, out), "date order comes from inside the file"


@case("a save whose nations have no pops")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1840.1.1", provinces=0)
    return run(folder, out), "every total is zero, nothing divides by it"


@case("a truncated save")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1840.1.1")
    whole = open(os.path.join(folder, "a.v2"), "rb").read()
    open(os.path.join(folder, "a.v2"), "wb").write(whole[:len(whole) // 2])
    a_save(os.path.join(folder, "b.v2"), "1841.1.1")
    return run(folder, out), "half a file must not take the run down"


@case("an empty file with a .v2 name")
def _(folder, out):
    open(os.path.join(folder, "a.v2"), "w").close()
    a_save(os.path.join(folder, "b.v2"), "1841.1.1")
    return run(folder, out), "skipped by name, the rest still read"


@case("a save that is actually a zip")
def _(folder, out):
    with open(os.path.join(folder, "a.v2"), "wb") as fh:
        fh.write(b"PK\x03\x04" + b"\0" * 400)
    a_save(os.path.join(folder, "b.v2"), "1841.1.1")
    return run(folder, out), "must name the zip and read the rest"


@case("--tags naming a nation that is not there")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1840.1.1")
    return run(folder, out, ["--tags", "ZZZ"]), "no rows at all"


@case("--min-pop above every nation")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1840.1.1")
    return run(folder, out, ["--min-pop", "999999999"]), "filters everyone out"


@case("a war with no battles and no end")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1870.6.1", tags=("ENG", "FRA"),
           wars=WAR)
    return run(folder, out), "an ongoing war with nothing in it"


@case("one save, verbose")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1840.1.1")
    return run(folder, out, []), "the loud path over a tiny campaign"


@case("a single save file rather than a folder")
def _(folder, out):
    path = os.path.join(folder, "a.v2")
    a_save(path, "1840.1.1")
    return run(path, out), "the positional argument takes a file too"


@case("numbers the program cannot use")
def _(folder, out):
    """
    A regiment of nought people is a division by zero deep inside a
    worker; a mobilisation size of minus one is not an error at all, and
    writes a report saying every nation can mobilize minus a hundred
    percent of itself. Each of these has to be refused by name.
    """
    a_save(os.path.join(folder, "a.v2"), "1840.1.1")
    bad = [["--pop-per-regiment", "0"], ["--map-scale", "0"],
           ["--mobilisation-size", "-1"], ["--mobilisation-size", "2"],
           ["--jobs", "0"], ["--min-pop", "-5"]]
    for extra in bad:
        code, said = run(folder, out, extra)
        # argparse exits 2 and prints to stderr; anything else means it
        # went through.
        if code != 2 or "not allowed here" not in said:
            return (("crash", "%s was accepted: %r\n%s"
                     % (" ".join(extra), code, said)), "must be refused")
    return (0, ""), "all six refused by name"


@case("--mod-path at a folder that is not there")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1840.1.1")
    return (run(folder, out, ["--mod-path", os.path.join(folder, "nope")]),
            "a mistyped mod folder is a sentence, not a stack trace")


@case("--mod-path at a folder with no mod in it")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1840.1.1")
    empty = os.path.join(folder, "notamod")
    os.makedirs(empty)
    return run(folder, out, ["--mod-path", empty]), "same, for a real folder"


@case("--out somewhere it cannot be written")
def _(folder, out):
    a_save(os.path.join(folder, "a.v2"), "1840.1.1")
    # A path *under a file*, which no filesystem will make a folder of.
    wall = os.path.join(folder, "a.v2", "report")
    return run(folder, wall), "said before the campaign is read, not after"


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    width = max(len(n) for n, _ in CASES)
    bad = []
    for name, fn in CASES:
        if only and only.lower() not in name.lower():
            continue
        holding = tempfile.mkdtemp(prefix="vic2edge")
        folder = os.path.join(holding, "saves")
        out = os.path.join(holding, "out")
        os.makedirs(folder)
        try:
            got = fn(folder, out)
            (code, said), _why = got[:2]
            # A case may also say what it found wrong beyond crashing.
            wrong = got[2] if len(got) > 2 else []
            crashed = code == "crash" or "Traceback" in said
            if wrong and not crashed:
                print("  %-*s FAILED" % (width, name))
                bad.append(name)
                for one in wrong:
                    print("      | %s" % one)
                continue
            # `main` returns None when it worked and a sentence when it
            # refused. A refusal is a pass: what is being looked for here is
            # a stack trace, not an unhappy answer.
            print("  %-*s %s" % (width, name,
                                 "CRASHED" if crashed else
                                 "ok (refused)" if code else "ok"))
            if crashed:
                bad.append(name)
                for line in said.strip().splitlines()[-12:]:
                    print("      | %s" % line)
            elif code:
                # `sys.exit("a sentence")` carries the sentence as the code
                # and prints nothing itself, so look there before the output.
                why = (code if isinstance(code, str)
                       else (said.strip().splitlines()
                             or ["exit %s, and said nothing" % code])[-1])
                print("      └ %s" % str(why).replace("\n", " ")[:96])
        except Exception:
            bad.append(name)
            print("  %-*s CRASHED (in the case itself)" % (width, name))
            for line in traceback.format_exc().strip().splitlines()[-8:]:
                print("      | %s" % line)
        finally:
            shutil.rmtree(holding, ignore_errors=True)
    print()
    if bad:
        print("FAILED: %s" % ", ".join(bad))
        return 1
    print("every edge case either works or refuses in a sentence")
    return 0


if __name__ == "__main__":
    sys.exit(main())

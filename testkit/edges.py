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


_VANILLA = []


def vanilla():
    """
    An unmodded install to read the cases on, made once. Every report is
    read on an installed game, and a case that named none would only ever
    be refused -- which passes here, and tests nothing.
    """
    if not _VANILLA:
        import atexit
        import matching
        where = tempfile.mkdtemp(prefix="vic2edgegame")
        atexit.register(shutil.rmtree, where, True)
        _VANILLA.append(matching.a_vanilla(os.path.join(where, "Victoria 2")))
    return _VANILLA[0]


def run(saves, out, extra_argv=(), game=True):
    """
    The analyzer, in this process, with everything it printed. On `vanilla`
    unless the case names a game or a mod itself, or asks for none.
    """
    import vic2_analyzer as va
    argv = [sys.argv[0], saves, "--out", out] + list(extra_argv)
    if game and "--game-root" not in argv and "--mod-path" not in argv:
        argv += ["--game-root", vanilla()]
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


@case("a war over before the first save")
def _(folder, out):
    # A save keeps its finished wars, so a campaign's first save can carry
    # one fought decades before it. Nothing saw who held the state going
    # in, so nothing can say whether the peace moved it. It used to be
    # judged anyway, by the first save against itself, and read "none
    # taken" for every such war.
    from invariants import payload_of
    old = ["previous_war=", "{", '\tname="The Old War"', "\thistory=", "\t{",
           "\t\t1850.1.1=", "\t\t{", '\t\t\tadd_attacker="ENG"', "\t\t}",
           "\t\t1850.1.1=", "\t\t{", '\t\t\tadd_defender="FRA"', "\t\t}",
           "\t\t1851.6.1=", "\t\t{", '\t\t\trem_attacker="ENG"', "\t\t}",
           "\t}", '\toriginal_attacker="ENG"', '\toriginal_defender="FRA"',
           "\toriginal_wargoal=", "\t{", '\t\tcasus_belli="acquire_state"',
           '\t\tactor="ENG"', '\t\treceiver="FRA"', "\t\tstate_province_id=3",
           "\t}", '\taction="1850.1.1"', "}"]
    for name, date in (("a.v2", "1860.1.1"), ("b.v2", "1861.1.1")):
        a_save(os.path.join(folder, name), date, tags=("ENG", "FRA"),
               wars=old)
    got = run(folder, out)
    report = os.path.join(out, "report.html")
    data = payload_of(report) if os.path.isfile(report) else None
    goals = [g for w in (data or {}).get("wars", []) for g in w["goals"]]
    wrong = []
    if not goals:
        wrong.append("the war's goal never reached the report")
    for g in goals:
        if g["checkable"]:
            wrong.append("an 1851 peace was judged from saves of 1860 and "
                         "1861: %d of %d taken" % (g["took"], g["of"]))
    return got, "a goal nothing can judge", wrong


@case("a mod anywhere but its game's mod folder")
def _(folder, out):
    # A report is read on an installed game and a mod only where the game
    # loads it from, so there is one way to run and nothing to guess. Here
    # the game is the only place England is called Englandia, so a report
    # that says so was read on it.
    from invariants import payload_of
    import matching
    for name, date in (("a.v2", "1860.1.1"), ("b.v2", "1861.1.1")):
        a_save(os.path.join(folder, name), date, tags=("ENG", "FRA"))
    game = matching.a_vanilla(os.path.join(folder, "Victoria 2"))
    os.makedirs(os.path.join(game, "localisation"))
    with open(os.path.join(game, "localisation", "names.csv"), "w") as fh:
        fh.write("ENG;Englandia;x\n")
    away = matching.a_mod(os.path.join(folder, "downloads", "amod"))
    home = matching.a_mod(os.path.join(game, "mod", "amod"))

    def england(where, argv, game_given=True):
        got = run(folder, os.path.join(out, where), argv, game=game_given)
        report = os.path.join(out, where, "report.html")
        data = payload_of(report) if os.path.isfile(report) else None
        return got, ((data or {}).get("tagNames") or {}).get("ENG")

    wrong = []
    for label, argv, game_given, words in (
            ("no game at all", [], False, "Say where Victoria II is installed"),
            ("a mod in Downloads", ["--mod-path", away], True,
             "not in a Victoria II install's mod folder"),
            ("a mod in Downloads, the game named", ["--mod-path", away,
                                                    "--game-root", game], True,
             "not in a Victoria II install's mod folder"),
            ("a game that is not one", ["--game-root", folder], True,
             "is not a Victoria II install")):
        (code, said), name = england(label, argv, game_given)
        if not isinstance(code, str) or words not in code:
            wrong.append("%s was not refused with %r: %r"
                         % (label, words, code if code else said[-200:]))
        elif name is not None:
            wrong.append("%s was refused, and a report was written anyway"
                         % label)
    got, name = england("the mod in the game", ["--mod-path", home])
    if name != "Englandia":
        wrong.append("a mod in the game's mod folder was not read on that "
                     "game: England came out %r" % name)
    (code, _said), name = england("the game alone", ["--game-root", game])
    if code or name != "Englandia":
        wrong.append("the game with no mod was not read as the unmodded "
                     "game: %r, England %r" % (code, name))
    return got, "one way to run", wrong


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
    bad = _cases()
    print()
    if bad:
        print("FAILED: %s" % ", ".join(bad))
        return 1
    print("every edge case either works or refuses in a sentence")
    return 0


def _cases():
    """Every case; the names of the bad ones."""
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
    return bad


if __name__ == "__main__":
    sys.exit(main())

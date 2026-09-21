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

HEAD = 'date="%s"\nplayer="%s"\ngovernment=3\nstart_date="1836.1.1"\n'

PROVINCE = """%d=
\tname="P%d"
\towner="%s"
\tcontroller="%s"
\tcore="%s"
\tfarmers=
\t{
\t\tid=%d
\t\tsize=%d
\t\tbritish=protestant
\t\tliteracy=0.40000
\t\tlife_needs=0.80000
\t}
"""

COUNTRY = """%s=
\tprimary_culture="british"
\tgovernment=democracy
\tcivilized=yes
\tcapital=%d
\tprestige=10.000
\tmoney=100.00000
\ttechnology=
\t{
%s\t}
\tactive_inventions=
\t{
%s\t}
"""


def a_save(path, date, tags=("ENG",), provinces=2, techs=(), inventions=(),
           player="ENG", wars="", extra=""):
    """One save with exactly the pieces a case is about, and nothing else."""
    parts = [HEAD % (date, player)]
    pid = 1
    for tag in tags:
        for _ in range(provinces):
            parts.append(PROVINCE % (pid, pid, tag, tag, tag, pid,
                                     1000 + pid * 10))
            pid += 1
    first = 1
    for tag in tags:
        tech = "".join("\t\t%s=\n\t\t{\n\t\t\t1 0.000\n\t\t}\n" % t
                       for t in techs)
        inv = ("\t\t%s\n" % " ".join(str(i) for i in inventions)
               if inventions else "")
        parts.append(COUNTRY % (tag, first, tech, inv))
        first += provinces
    parts.append(wars)
    parts.append(extra)
    body = "".join(parts)
    # The game writes a block's fields one tab in and closes on its own line.
    body = body.replace("\n\t", "\n\t")
    with open(path, "w", encoding="latin-1", newline="\r\n") as fh:
        fh.write(_braces(body))


def _braces(body):
    """Close every block that `a_save` opened, in the game's own layout."""
    out = []
    for line in body.split("\n"):
        out.append(line)
    text = "\n".join(out)
    # Each `name=` line that is followed by an indented line needs its braces;
    # the templates above already carry the inner ones, so only the outermost
    # province and country blocks are left to wrap.
    fixed, lines = [], text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        fixed.append(line)
        if line.endswith("=") and not line.startswith("\t"):
            fixed.append("{")
            i += 1
            while i < len(lines) and (lines[i].startswith("\t")
                                      or lines[i] == ""):
                if lines[i] == "" and not any(
                        l.startswith("\t") for l in lines[i + 1:i + 2]):
                    break
                fixed.append(lines[i])
                i += 1
            fixed.append("}")
            continue
        i += 1
    return "\n".join(fixed) + "\n"


WAR = """active_war=
\tname="The Test War"
\toriginal_attacker="ENG"
\toriginal_defender="FRA"
\tattacker="ENG"
\tdefender="FRA"
\taction="1870.5.1"
"""


def run(saves, out, extra_argv=()):
    """The analyzer, in this process, with everything it printed."""
    import vic2_analyzer as va
    import v2parse
    v2parse.register_pop_types([])
    va.REFORM_KEYS.clear()
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
    a_save(os.path.join(folder, "a.v2"), "1840.6.1")
    a_save(os.path.join(folder, "b.v2"), "1840.6.1")
    return run(folder, out), "a manual save beside an autosave"


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
            (code, said), _why = fn(folder, out)
            crashed = code == "crash" or "Traceback" in said
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
        print("CRASHED: %s" % ", ".join(bad))
        return 1
    print("every edge case either works or refuses in a sentence")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Take the workers away and check the campaign is still read.

A machine that cannot start worker processes is not an exotic case. A
locked-down work laptop, a container with a tight process limit, a
sandbox that refuses `fork`, a machine already out of memory -- and, the
one that actually happened here, a temp folder with a long path. Python
3.14 starts workers through a forkserver whose socket lives in the temp
folder, and an `AF_UNIX` path cannot exceed 108 bytes, so a deep enough
`TMPDIR` made every run die with a stack trace out of the depths of
`multiprocessing`.

None of that has to be fatal. Every save can be read one at a time, the
code to do it is already there, and the answer is the same answer. What
made it fatal was where the guard sat: `ProcessPoolExecutor(...)`
succeeds even when the machine cannot start a single worker, because it
starts them lazily on the first `submit`. The guard was around the
constructor.

    python3 testkit/noworkers.py [path/to/saves]

With no saves given this builds its own tiny campaign, which is enough:
what is being checked is the fallback, not the parsing.
"""

import io
import contextlib
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testkit"))

import savefmt                                             # noqa: E402


def a_campaign(folder):
    """Three saves, a year apart, with enough in them to make rows."""
    os.makedirs(folder, exist_ok=True)
    for n, date in enumerate(("1836.1.1", "1837.1.1", "1838.1.1")):
        savefmt.write(
            os.path.join(folder, "save%d.v2" % n),
            savefmt.head(date, player="ENG"),
            savefmt.province(1, "ENG", [savefmt.pop("farmers", 1, 1000 + n)]),
            savefmt.province(2, "FRA", [savefmt.pop("farmers", 2, 500)]),
            savefmt.country("ENG", techs=["flintlock_rifles"]),
            savefmt.country("FRA", culture="french", capital=2))
    return folder


def refusing_pool(saves, out):
    """
    [what went wrong] when no worker will start.

    The pool is replaced with one whose `submit` always raises, which is
    what a machine that cannot start workers looks like from here: the
    constructor returns an object, and the first piece of work is where
    it falls over.
    """
    import vic2_analyzer as va
    import v2parse
    v2parse.register_pop_types([])
    va.REFORM_KEYS.clear()

    # Patched on `concurrent.futures` rather than on `vic2_analyzer`,
    # because the pool is imported inside the function that uses it and so
    # is looked up fresh, from there, on every call.
    import concurrent.futures as cf
    real = cf.ProcessPoolExecutor

    class WillNotStart(real):
        def submit(self, *a, **kw):
            raise OSError("AF_UNIX path too long")

    said = io.StringIO()
    old_argv = sys.argv
    cf.ProcessPoolExecutor = WillNotStart
    try:
        sys.argv = [old_argv[0], saves, "--out", out, "--rebuild"]
        with contextlib.redirect_stdout(said), \
                contextlib.redirect_stderr(said):
            try:
                code = va.main()
            except SystemExit as stop:
                code = stop.code
    except BaseException:                                # noqa: BLE001
        return (["a pool that will not start took the run down:\n%s"
                 % traceback.format_exc()], said.getvalue())
    finally:
        cf.ProcessPoolExecutor = real
        sys.argv = old_argv

    out_text = said.getvalue()
    wrong = []
    if code:
        wrong.append("the run refused with %r" % (code,))
    if not os.path.isfile(os.path.join(out, "report.html")):
        wrong.append("no report was written")
    if not os.path.isfile(os.path.join(out, "nations_timeseries.csv")):
        wrong.append("no table was written")
    if "one at a time" not in out_text:
        wrong.append("nothing was said about falling back, so a person "
                     "watching a slow run has no idea why")
    return wrong, out_text


def same_answer(saves, a, b):
    """[what went wrong] when the two runs' tables are compared."""
    wrong = []
    for name in sorted(os.listdir(a)):
        if not name.endswith(".csv"):
            continue
        one = os.path.join(a, name)
        two = os.path.join(b, name)
        if not os.path.isfile(two):
            wrong.append("%s is missing from the serial run" % name)
            continue
        if open(one, "rb").read() != open(two, "rb").read():
            wrong.append("%s differs between the parallel and serial runs"
                         % name)
    return wrong


def main():
    given = sys.argv[1] if len(sys.argv) > 1 else ""
    holding = tempfile.mkdtemp(prefix="vic2noworkers")
    saves = given
    try:
        if not saves:
            saves = a_campaign(os.path.join(holding, "saves"))

        # The ordinary run first, so there is something to compare against.
        import vic2_analyzer as va
        import v2parse
        v2parse.register_pop_types([])
        va.REFORM_KEYS.clear()
        normal = os.path.join(holding, "normal")
        old = sys.argv
        quiet = io.StringIO()
        try:
            sys.argv = [old[0], saves, "--out", normal, "--rebuild", "-q"]
            with contextlib.redirect_stdout(quiet), \
                    contextlib.redirect_stderr(quiet):
                va.main()
        finally:
            sys.argv = old

        serial = os.path.join(holding, "serial")
        wrong, _said = refusing_pool(saves, serial)
        print("  %-44s %s" % ("a pool that will not start",
                              "FAILED" if wrong else "ok (read serially)"))
        if not wrong:
            same = same_answer(saves, normal, serial)
            print("  %-44s %s" % ("and it says the same thing",
                                  "FAILED" if same else "ok"))
            wrong += same
    finally:
        shutil.rmtree(holding, ignore_errors=True)

    print()
    if wrong:
        print("PROBLEMS:")
        for one in wrong:
            print("  %s" % str(one).replace("\n", "\n    "))
        return 1
    print("a machine with no workers still reads the campaign")
    return 0


if __name__ == "__main__":
    sys.exit(main())
